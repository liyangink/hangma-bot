"""坐隐 2.1a 重算驱动：在同一批记录观察上用**当前规则**补齐事实，测量 M4。

背景（见 MECHANISM-RATE-FINDINGS.md）：项目既有决策语料录于 Pass 等待事实
引入之前，其中 `Pass` 候选的 `fact_kind` 全是 `NOT_APPLICABLE`，导致 M4
需要的等待牌效恒为 None，改选率必然是 0。

本驱动：**读记录的观察 → 用当前规则重算候选与事实 → 在同一输入上
比较 V2（基线）与 M4（候选）**。两个策略看到**完全相同**的重算输入。

**REVIEW-6 更正的三个口径问题**（本版 v2 已修）：

  S6-1-a 窗口分类：v1 以"候选里存在吃碰杠"定义鸣牌窗口，把**自摸暗杠与补杠**
         混进响应窗口（它们没有响应 Pass）。v2 分开统计：
           - `response_windows`：吃/碰/明杠且存在 Pass 候选；
           - `self_draw_gang_windows`：暗杠/补杠，无 Pass，默认不参与分差；
           - `other_windows`：其余。
  S6-1-b 分差口径：v1 用 `total_score` 的**前两名之差**，该值**恒非负**，
         无法表达"鸣牌已经领先 Pass"，也违反生产接口
         （`RankedCandidate.total_score`："跨优先层不能用此字段重新排序"）。
         v2 改为**同一可信层内：最佳受影响动作 − 最佳未受影响退路(Pass)**，
         并显式分层报告（跨层、缺退路、有合法胡）。
  S6-3   可追溯性：v2 输出**逐 β 全量明细**、**逐条排除记录（ID + 原因）**、
         输入文件哈希、规则配置、基线权重、候选参数与源码指纹；
         输入不匹配时**硬失败**，不再静默跳过。

**边界**：决策级信号**只作机制达成诊断，不得作适应度排序**（README §4.2）。
本工具**不测量效果大小**——语料没有"改选之后这局变成多少分"的结果，
分差小不等于改对了。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/tools'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import asyncio
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

REPO = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, REPO / "src")))

from hangma_bot.application.deadline import ManualClock  # noqa: E402
from hangma_bot.bootstrap import build_decision_codec  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.hangma.interface import RuleCompleteness  # noqa: E402
from hangma_bot.kernel.actions import Chi, Gang, Hu, Pass, Peng  # noqa: E402
from hangma_bot.kernel.config import RuleConfig  # noqa: E402
from hangma_bot.offline.evaluate import translate_budget  # noqa: E402
from hangma_bot.policy.evaluation_v1 import build_context  # noqa: E402
from hangma_bot.policy.evaluation_v2 import score_candidates  # noqa: E402
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2  # noqa: E402
from hangma_bot.policy.interface import DecisionRequest  # noqa: E402
from hangma_bot.policy.weights_v1 import DEFAULT_WEIGHTS_V1  # noqa: E402

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "sitin_m4_policy", _project_file(_PROJECT_ROOT, Path(__file__).resolve().parent / "sitin_m4_policy.py"))
m4mod = importlib.util.module_from_spec(_spec)
sys.modules["sitin_m4_policy"] = m4mod
assert _spec.loader is not None
_spec.loader.exec_module(m4mod)

NEW_ORIGIN = 100.0
SCHEMA = "sitin-m4-recompute/2"

# β 扫描：M4 幅度对等待牌效的敏感度。**这只是行为覆盖扫描**，不是效果证据。
BETA_SWEEP = (0.5, 1.0, 2.0, 5.0, 10.0, 20.0)

RESPONSE_MELD_KINDS = ("chi", "peng", "gang")


def _kind(key: Optional[str]) -> str:
    return key.split(":")[0] if key else "none"


def _sha256_file(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_fingerprints() -> Dict[str, Optional[str]]:
    """参与本次重算的源码指纹，供产物可追溯（REVIEW-6 S6-3）。"""

    src = _project_file(_PROJECT_ROOT, REPO / "src" / "hangma_bot")
    return {
        "driver": _sha256_file(Path(__file__)),
        "m4_policy_file": _sha256_file(Path(__file__).with_name("sitin_m4_policy.py")),
        "m4_policy_fingerprint": m4mod.source_fingerprint(),
        "evaluation_v2": _sha256_file(src / "policy" / "evaluation_v2.py"),
        "evaluation_v1": _sha256_file(src / "policy" / "evaluation_v1.py"),
        "weights_v1": _sha256_file(src / "policy" / "weights_v1.py"),
        "heuristic_v2": _sha256_file(src / "policy" / "heuristic_v2.py"),
    }


async def _no_deadline() -> None:
    """重算驱动没有实时预算；评分层的截止回调是空操作。"""

    return None


def _first_key(plan) -> Optional[str]:
    return plan.candidates[0].action_key if plan.candidates else None


def _plan_order_keys(plan) -> List[str]:
    """按计划 rank 顺序的 action_key 列表；**不做数值重排**。"""

    return [c.action_key for c in sorted(plan.candidates, key=lambda c: c.rank)]


def window_class(keys: Sequence[str]) -> str:
    """窗口分类（S6-1-a）。只看规则候选，不看评分。"""

    kinds = {_kind(k) for k in keys}
    has_meld = bool(kinds & set(RESPONSE_MELD_KINDS))
    has_pass = "pass" in kinds
    if has_meld and has_pass:
        return "response"
    if "gang" in kinds and not has_pass:
        return "self_draw_gang"
    if has_meld:
        return "meld_without_pass"
    return "other"


def tier_gap(scored: Sequence[Any], scope=("chi", "peng")) -> Dict[str, Any]:
    """同层"最佳受影响动作 − 最佳未受影响退路"（S6-1-b）。

    受影响 = `scope` 内的吃/碰；未受影响退路 = `Pass`。
    **只在同一 priority 层内比较**；跨层或缺失时不给分差值，只给原因。

    输入是评分层的 `ScoredCandidate`（带 `priority`），不是计划里的
    `RankedCandidate`——计划**有意不暴露可信层级**，因此分层比较必须回到评分层。
    """

    scored = [c for c in scored if c.total is not None]
    affected = [c for c in scored if _kind(c.action_key) in scope]
    fallback = [c for c in scored if _kind(c.action_key) == "pass"]
    has_hu = any(_kind(c.action_key) == "hu" for c in scored)
    out: Dict[str, Any] = {"has_hu": has_hu,
                           "affected_n": len(affected), "fallback_n": len(fallback),
                           "best_affected": None, "best_fallback": None,
                           "gap": None, "reason": None}
    if not affected or not fallback:
        out["reason"] = "no_affected" if not affected else "no_pass_fallback"
        return out
    bm = max(affected, key=lambda c: (c.total, c.action_key))
    bp = max(fallback, key=lambda c: (c.total, c.action_key))
    out["best_affected"] = {"key": bm.action_key, "score": bm.total}
    out["best_fallback"] = {"key": bp.action_key, "score": bp.total}
    # 生产排序层：priority 是可信层级。跨层比较需要分层，不能直接用分差。
    if bm.priority != bp.priority:
        out["reason"] = "cross_tier"
        return out
    out["gap"] = round(bm.total - bp.total, 3)
    return out


def measure(rows: Sequence[Mapping[str, Any]], ruleset: str, betas=BETA_SWEEP,
            input_path: Optional[Path] = None) -> Dict[str, Any]:
    codec = build_decision_codec()
    decode_request = codec["decode_request"]
    decode_budget = codec["decode_budget"]
    rule_config = RuleConfig(ruleset_version=ruleset, base_score=1, you_cai_bi_kao=False)
    rules = HangmaRules(rule_config)

    clock = ManualClock(start_monotonic=NEW_ORIGIN)
    baseline = ComparableHeuristicPolicyV2(monotonic=clock.now)
    # 每个 β 一个**独立实例**，参数不可变，互不干扰（S6-2）。
    candidates = {b: m4mod.M4OpportunityCostPolicy(
        monotonic=clock.now, params=m4mod.M4Params(beta=b)) for b in betas}
    ablation = m4mod.M4OpportunityCostPolicy(monotonic=clock.now, enabled=False)

    excluded: List[Dict[str, Any]] = []
    per_beta = {b: {"changed": 0, "affected_to_fallback": 0, "fallback_to_affected": 0,
                    "changed_same_kind": 0, "other_changed": 0,
                    "changed_decisions": []} for b in betas}
    response_records: List[Dict[str, Any]] = []
    class_counts = {"response": 0, "self_draw_gang": 0, "meld_without_pass": 0, "other": 0}
    audit_mismatch = 0
    first_mismatch = 0
    plan_scored_mismatch = 0
    analysed = 0
    natural_values: List[int] = []

    def exclude(index: int, decision_id: Any, reason: str, detail: str = "") -> None:
        excluded.append({"row_index": index, "decision_id": decision_id,
                         "reason": reason, "detail": detail})

    for index, row in enumerate(rows):
        payload = row.get("request")
        if not isinstance(payload, Mapping):
            exclude(index, row.get("decision_id"), "no_request_payload",
                    "行不含 request；旧机制工具在此静默跳过（REVIEW-6 S6-3）")
            continue
        try:
            recorded = decode_request(payload)
        except Exception as exc:
            exclude(index, row.get("decision_id"), "decode_failed", repr(exc))
            continue
        try:
            recorded_budget = decode_budget(
                row.get("budget"), row.get("budget_origin_monotonic", 0.0))
            budget = translate_budget(
                recorded_budget, row.get("budget_origin_monotonic", 0.0), NEW_ORIGIN)
        except Exception as exc:
            exclude(index, recorded.decision_id, "budget_failed", repr(exc))
            continue
        try:
            analysis = rules.analyze(recorded.observation)
        except Exception as exc:
            exclude(index, recorded.decision_id, "analyze_failed", repr(exc))
            continue
        if analysis.completeness is RuleCompleteness.DEGRADED:
            exclude(index, recorded.decision_id, "rules_degraded",
                    "; ".join("{0}:{1}".format(i.area, i.reason) for i in analysis.issues))
            continue
        if not analysis.legal_candidates:
            exclude(index, recorded.decision_id, "no_legal_candidate", "")
            continue

        request = DecisionRequest(
            observation=recorded.observation,
            competition=recorded.competition,
            rules=analysis,
            decision_id=recorded.decision_id,
            trigger_seq=recorded.trigger_seq,
            window_key=recorded.window_key,
            rejected_attempts=(),
        )
        try:
            plan_baseline = asyncio.run(baseline.choose(request, budget))
            plan_ablation = asyncio.run(ablation.choose(request, budget))
            plans = {b: asyncio.run(policy.choose(request, budget))
                     for b, policy in candidates.items()}
            # 分层比较必须回到评分层：计划有意不暴露 priority（S6-1-b）。
            scored_baseline = asyncio.run(score_candidates(
                tuple(analysis.legal_candidates), build_context(recorded.observation),
                DEFAULT_WEIGHTS_V1, _no_deadline))
        except Exception as exc:
            exclude(index, recorded.decision_id, "choose_failed", repr(exc))
            continue

        analysed += 1
        keys = [c.action_key for c in analysis.legal_candidates]
        klass = window_class(keys)
        class_counts[klass] += 1

        key_baseline = _first_key(plan_baseline)
        key_ablation = _first_key(plan_ablation)
        # 消融检查：关闭后必须与基线首选一致，**且审计说明也要一致**（S6-3）。
        if key_ablation != key_baseline:
            first_mismatch += 1
        if tuple(plan_ablation.degraded_reasons) != tuple(plan_baseline.degraded_reasons):
            audit_mismatch += 1

        natural = m4mod.natural_draw_value(tuple(analysis.legal_candidates))
        gap_info = tier_gap(scored_baseline)
        # 交叉核对：评分层推出的首选必须与计划首选一致，否则分差口径与计划脱节。
        scored_order = sorted(scored_baseline,
                              key=lambda c: (c.priority, -c.total, c.action_key))
        if scored_order and scored_order[0].action_key != key_baseline:
            plan_scored_mismatch += 1
        if natural is not None and natural > 0 and klass == "response":
            natural_values.append(int(natural))

        changed_at: Dict[str, List[str]] = {}
        for b, plan in plans.items():
            key_b = _first_key(plan)
            if key_b == key_baseline:
                continue
            stats = per_beta[b]
            stats["changed"] += 1
            stats["changed_decisions"].append({
                "row_index": index, "decision_id": recorded.decision_id,
                "from": key_baseline, "to": key_b,
                "from_kind": _kind(key_baseline), "to_kind": _kind(key_b),
                "window_class": klass, "waiting_tiles": natural,
            })
            kf, kt = _kind(key_baseline), _kind(key_b)
            if kf in ("chi", "peng") and kt == "pass":
                stats["affected_to_fallback"] += 1
            elif kf == "pass" and kt in ("chi", "peng"):
                stats["fallback_to_affected"] += 1
            elif kf == kt:
                stats["changed_same_kind"] += 1
            else:
                stats["other_changed"] += 1
            if klass == "response":
                changed_at.setdefault("response", []).append(b)

        # 只有响应窗口才进入诊断记录（S6-1-a）。
        if klass == "response":
            min_beta = None
            if gap_info["gap"] is not None and gap_info["gap"] > 0 and natural and natural > 0:
                min_beta = round(gap_info["gap"] * m4mod.DEFAULT_PARAMS.natural_ref / natural, 3)
            response_records.append({
                "row_index": index,
                "decision_id": recorded.decision_id,
                "hand_id": row.get("hand_id"),
                "run_id": row.get("run_id"),
                "split_group_id": row.get("split_group_id"),
                "window_key": _jsonable(recorded.window_key),
                "waiting_tiles": natural,
                "baseline_first": key_baseline,
                "baseline_first_kind": _kind(key_baseline),
                "gap": gap_info,
                "min_beta_to_flip": min_beta,
                "changed_betas": sorted(changed_at.get("response", []),
                                        key=lambda x: BETA_SWEEP.index(x)),
            })

    def q(values: Sequence[float], frac: float) -> Optional[float]:
        if not values:
            return None
        s = sorted(values)
        return round(float(s[min(int(frac * (len(s) - 1)), len(s) - 1)]), 2)

    response_n = class_counts["response"]
    gaps = [r["gap"]["gap"] for r in response_records if r["gap"]["gap"] is not None]
    flippable = [r["min_beta_to_flip"] for r in response_records
                 if r["min_beta_to_flip"] is not None]
    affected_first = [r for r in response_records
                      if r["baseline_first_kind"] in ("chi", "peng")]
    affected_first_gaps = [r["gap"]["gap"] for r in affected_first
                           if r["gap"]["gap"] is not None]

    per_beta_out = []
    for b in betas:
        st = per_beta[b]
        per_beta_out.append({
            "beta": b,
            "params": candidates[b].params.to_json(),
            "identity": candidates[b].candidate_identity(),
            "effective_tile_multiplier":
                round(candidates[b].params.effective_tile_multiplier(
                    DEFAULT_WEIGHTS_V1.effective_tile), 4),
            "response_windows": response_n,
            "changed": st["changed"],
            "changed_share_of_response": round(st["changed"] / response_n, 4) if response_n else None,
            "affected_to_fallback": st["affected_to_fallback"],
            "fallback_to_affected": st["fallback_to_affected"],
            "changed_same_kind": st["changed_same_kind"],
            "other_changed": st["other_changed"],
            "changed_decisions": st["changed_decisions"],
        })

    return {
        "schema": SCHEMA,
        "inputs": {
            "path": str(input_path) if input_path else None,
            "sha256": _sha256_file(input_path) if input_path else None,
            "rows": len(rows),
            "analysed": analysed,
            "excluded": len(excluded),
        },
        "rules": {"ruleset_version": ruleset,
                  "rule_config": {"base_score": 1, "you_cai_bi_kao": False}},
        "baseline": {"name": "weighted_heuristic_v2",
                     "weights": {k: getattr(DEFAULT_WEIGHTS_V1, k)
                                 for k in ("shanten_step", "effective_tile", "gang_bonus",
                                           "claim_risk_peng", "claim_risk_chi")}},
        "source_fingerprints": source_fingerprints(),
        "candidates": [{"beta": b, "params": candidates[b].params.to_json(),
                        "identity": candidates[b].candidate_identity()} for b in betas],
        "ablation": {"name": "sitin_m4_opportunity_cost(enabled=False)",
                     "first_choice_mismatch": first_mismatch,
                     "audit_reasons_mismatch": audit_mismatch,
                     "expected": "两者都应为 0"},
        "cross_check": {"plan_vs_scored_first_mismatch": plan_scored_mismatch,
                        "expected": 0},
        "window_classes": class_counts,
        "response": {
            "n": response_n,
            "with_waiting_tiles": len(natural_values),
            "waiting_tiles": {"n": len(natural_values), "min": min(natural_values) if natural_values else None,
                              "q25": q(natural_values, 0.25), "median": q(natural_values, 0.50),
                              "q75": q(natural_values, 0.75),
                              "max": max(natural_values) if natural_values else None},
            "gap_same_tier_best_affected_minus_pass": {
                "n": len(gaps), "min": min(gaps) if gaps else None,
                "q10": q(gaps, 0.10), "q25": q(gaps, 0.25), "median": q(gaps, 0.50),
                "q75": q(gaps, 0.75), "max": max(gaps) if gaps else None,
                "le_0": sum(1 for g in gaps if g <= 0),
                "le_5": sum(1 for g in gaps if g <= 5),
                "le_10": sum(1 for g in gaps if g <= 10),
                "le_20": sum(1 for g in gaps if g <= 20),
                "le_50": sum(1 for g in gaps if g <= 50),
            },
            "gap_unavailable_reasons": _tally(
                [r["gap"]["reason"] for r in response_records if r["gap"]["gap"] is None]),
            "baseline_first_is_affected": len(affected_first),
            "baseline_first_affected_gap": {
                "n": len(affected_first_gaps),
                "median": q(affected_first_gaps, 0.50),
                "le_5": sum(1 for g in affected_first_gaps if g <= 5),
                "le_10": sum(1 for g in affected_first_gaps if g <= 10),
                "le_20": sum(1 for g in affected_first_gaps if g <= 20),
            },
            "min_beta_to_flip": {
                "n": len(flippable),
                "min": min(flippable) if flippable else None,
                "q25": q(flippable, 0.25), "median": q(flippable, 0.50),
                "q75": q(flippable, 0.75), "max": max(flippable) if flippable else None,
                "le_2": sum(1 for x in flippable if x <= 2),
                "le_20": sum(1 for x in flippable if x <= 20),
                "gt_20": sum(1 for x in flippable if x > 20),
            },
        },
        "per_beta": per_beta_out,
        "response_windows": response_records,
        "excluded_records": excluded,
    }


def _tally(values: Sequence[Any]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for v in values:
        out[str(v)] = out.get(str(v), 0) + 1
    return out


def _jsonable(value: Any) -> Any:
    if hasattr(value, "to_json"):
        return value.to_json()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="坐隐 2.1a M4 重算驱动")
    ap.add_argument("--input", required=True,
                    help="决策语料 jsonl（每行含 request）")
    ap.add_argument("--out", required=True, help="输出目录")
    ap.add_argument("--ruleset", default="v26")
    ap.add_argument("--betas", default=",".join(str(b) for b in BETA_SWEEP))
    args = ap.parse_args(argv)

    input_path = Path(args.input)
    rows = []
    with input_path.open() as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    betas = tuple(float(x) for x in args.betas.split(",") if x.strip())
    result = measure(rows, args.ruleset, betas, input_path=input_path)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "recompute.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=False), encoding="utf-8")
    with (out / "response-windows.jsonl").open("w", encoding="utf-8") as handle:
        for rec in result["response_windows"]:
            handle.write(json.dumps(rec, ensure_ascii=False) + "\n")
    with (out / "excluded.jsonl").open("w", encoding="utf-8") as handle:
        for rec in result["excluded_records"]:
            handle.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(json.dumps(_summary(result), ensure_ascii=False, indent=2))
    return 0


def _summary(result: Mapping[str, Any]) -> Dict[str, Any]:
    r = result["response"]
    return {
        "inputs": result["inputs"],
        "window_classes": result["window_classes"],
        "ablation": result["ablation"],
        "response_windows": r["n"],
        "with_waiting_tiles": r["with_waiting_tiles"],
        "gap": r["gap_same_tier_best_affected_minus_pass"],
        "gap_unavailable": r["gap_unavailable_reasons"],
        "min_beta_to_flip": r["min_beta_to_flip"],
        "per_beta": [{k: v for k, v in row.items() if k != "changed_decisions"}
                     for row in result["per_beta"]],
    }


if __name__ == "__main__":
    raise SystemExit(main())
