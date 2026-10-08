"""坐隐：按**规则可枚举**生成的触发窗口集（构造集，**不是统计样本**）。

## 为什么必须有这个工具

实测事实（2026-09-15，**已按对抗性复核更正**）：真实语料
`datasets/derived/auto-match-2026-09-06/decisions.jsonl` 共 3343 行，
**原始** `chain_count` 直方图是 `{0: 3342, 1: 1}`——**语料里确实有链状态，不是 0**。
但本语料**没有任何一行带 `chain_piao` 键**，而 `engine.py:87` 对
「`chain_count > 0` 且 `chain_piao` 为空」会记 RuleIssue 使窗口 `DEGRADED`，
**于是每一个链状态窗口都会被降级排除**。

> **我第一版写的是"`chain_count` 全部为 0（直方图 {0: 3249}）"，那是错的**：
> 它把直方图建在"规则分析完整的窗口"这个**已被链状态过滤过的子集**上，
> 于是**在构造上只能得 0**——结论由测量方式决定，而不是由数据决定。
> 现在的实现把"原始覆盖"与"门禁可用窗口"**分开统计**（见 `coverage_of_corpus`）。

**修正后的结论方向不变、理由全换**：链路径候选在这份语料上**没有可用触发面**，
不是因为"没有链状态"，而是因为**链状态一律不可用**（观察编码器不落 `chain_piao`，
规则层无法核验该链，只能降级）。
**由此得到一条可执行的修复方向**：让决策记录落盘 `chain_piao`，
链状态窗口就能变成可用样本——这比"另造一份语料"更精确。

这个结论**不能**读成"该候选没有用"：真实语料之所以没有链状态，一部分原因是
**现策略本身没有开链的动机**（V1/V2 评分里根本没有链这一项）。用这份语料判定
链路径候选，等于用"没有开过链的对局"去否定"开链的价值"——循环论证。

用户此前已裁定正确的覆盖性口径：**按规则可枚举的场景判断，不拿小语料的频率当结论**
（组合覆盖 / t-wise，见划分设计 §7.1）。本工具就是那个口径的最小落地。

## 做法：真实窗口做骨架，只改写规则状态

1. 从真实语料里挑**骨架窗口**：手牌、牌河、副露、`phase`、`window_key` 全部保留，
   因此合法候选由真实 `HangmaRules.analyze` 产出，不是手写的；
2. 只替换观察里的规则状态（`chain_count` / `baotou` / `chain_piao`），
   按**规则可枚举的网格**取值；
3. 用生产编码器 `decision_request_to_json` 重新落盘，格式与真实语料一致，
   于是门禁与调度器可以直接读它。

## 边界（必须与产物一起引用，否则会变成"用构造数据当证据"）

1. 这是**构造的触发集**，不是分布抽样。**禁止**用它做效应估计、候选排序、
   淘汰或晋级声明——本项目已有两次"决策级信号看起来有增益"的教训（README §4）。
2. 它的用途只有两条：① 证明**接线到达候选**（DESIGN §7 第 2.2b 步）；
   ② 给门禁一个**能触发**的作用面，用来把"语料无触发面"与"候选恒为 0"分开。
3. **准入记录仍以真实语料为准**。触发集上的门禁结果一律标注为"非准入证据"。
4. 骨架窗口的**规则一致性**由 `HangmaRules.analyze` 复算保证；改写后的规则状态
   与骨架的历史并不自洽（例如链次数来自规则网格而不是真实历史），
   这不影响"接线与势差形状"的验证，但**决定**了它不能当效果证据。
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
import collections
import dataclasses
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

REPO = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, REPO / "src")))
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from hangma_bot.application.audit_codec import (  # noqa: E402
    decision_budget_to_json,
    decision_request_from_json,
    decision_request_to_json,
)
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.hangma.interface import RuleCompleteness  # noqa: E402
from hangma_bot.kernel.actions import Tile  # noqa: E402
from hangma_bot.kernel.config import RuleConfig  # noqa: E402
from hangma_bot.kernel.observation import RulePublicState  # noqa: E402
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2  # noqa: E402
from hangma_bot.policy.interface import DecisionRequest  # noqa: E402


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _project_file(_PROJECT_ROOT, _HERE / (name + ".py")))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


recompute = _load("sitin_m4_recompute")
gates = _load("sitin_gates")

#: 规则可枚举的规则状态网格。
#: chain_count 取官方 `chain.count` 值域 0—6 的代表点；`baotou` 决定"打白是飘还是断链"；
#: `chain_piao` 必须 ≤ chain_count（工程校验），且**链非零时必须给值**，
#: 否则 `HangmaRules` 会记 RuleIssue 使窗口降级、被门禁排除。
TRIGGER_STATES: Tuple[Tuple[int, bool, Optional[int]], ...] = (
    (0, False, None),
    (0, True, 0),
    (1, False, 0),
    (1, True, 1),
    (2, False, 0),
    (2, True, 2),
    (3, True, 3),
    (6, True, 3),
)

#: 骨架窗口要覆盖的**翻转位点**。
#:
#: 为什么按"位点"而不是按 phase 挑（2026-09-15 实测修正）：
#: 势差塑形的安全保证同时限制了它的**行为可达面**——同一状态内，所有不改变链的
#: 动作得到**同一个**平移，它们的相对次序**在结构上不可能变**。于是候选只可能在
#: 三类位点上改选：
#:   ① 杠候选与基线首选竞争（链 +1 把它抬起来）；
#:   ② 爆头态下"打白（飘）"与普通弃牌竞争（飘 +1、其余按断链扣）；
#:   ③ 声明 scope 内的动作类别在窗口里根本不出现（不产生任何位点）。
#: 初版骨架只要求"含吃碰/含杠"，结果 draw_only 骨架手里**一张白都没有**，
#: 飘分支在结构上不可达，14 个触发窗口全部零改选——那不是候选的问题，
#: 是骨架没选到位点。
SKELETON_SHAPES: Mapping[str, Mapping[str, Any]] = {
    # ① 有杠候选，且基线首选**不是**那个杠（否则本来就选对了，无从翻转）
    "gang_competes": {"kinds": ("discard", "gang"), "first_not_kind": "gang"},
    # ② 手里有财神且可以打它，基线首选不是打财神（爆头态下打白才构成飘）
    "wealth_discard_available": {"kinds": ("discard",), "has_wealth": True,
                                 "first_not_key": "discard:白"},
    # 响应窗口（吃/碰候选存在即可）：对链族是"零位点"——吃碰不改链，恒 0；
    # 对鸣牌族（M4/等待条件）才是位点，因此本集合可被多个族共用。
    "response_claim": {"kinds": ("chi", "peng")},
    "draw_only": {"kinds": ("discard",), "first_not_kind": None},
}


def _kinds(keys: Sequence[str]) -> set:
    return {recompute._kind(key) for key in keys}


def pick_skeletons(rows: Sequence[Mapping[str, Any]], ruleset: str = "v26",
                   per_shape: int = 3) -> Dict[str, List[Dict[str, Any]]]:
    """从真实语料里各挑一个**翻转位点**骨架；只做筛选，不改写任何内容。

    需要跑一次基线策略来读它的首选动作——"位点"的定义里就包含"基线在这个动作上
    并不是已经选对了"。这一步只读，不产生任何效果证据。
    """

    from hangma_bot.application.deadline import ManualClock
    from hangma_bot.bootstrap import build_decision_codec
    from hangma_bot.offline.evaluate import translate_budget

    rules = HangmaRules(RuleConfig(ruleset_version=ruleset, base_score=1,
                                   you_cai_bi_kao=False))
    codec = build_decision_codec()
    clock = ManualClock(start_monotonic=100.0)
    baseline = ComparableHeuristicPolicyV2(monotonic=clock.now)

    found: Dict[str, List[Dict[str, Any]]] = {shape: [] for shape in SKELETON_SHAPES}
    for row in rows:
        payload = row.get("request")
        if not isinstance(payload, Mapping):
            continue
        try:
            recorded = codec["decode_request"](payload)
            analysis = rules.analyze(recorded.observation)
        except Exception:
            continue
        if analysis.completeness is RuleCompleteness.DEGRADED or not analysis.legal_candidates:
            continue
        if all(len(items) >= per_shape for items in found.values()):
            break
        keys = [c.action_key for c in analysis.legal_candidates]
        kinds = _kinds(keys)
        pending = {shape: spec for shape, spec in SKELETON_SHAPES.items()
                   if len(found[shape]) < per_shape}
        if not pending:
            continue
        # 需要首选动作的位点才跑基线；不需要的直接跳过，省时间。
        needs_first = any(spec.get("first_not_kind") is not None
                          or spec.get("first_not_key") is not None
                          for spec in pending.values())
        first_key = None
        if needs_first:
            try:
                budget = translate_budget(
                    codec["decode_budget"](row.get("budget"),
                                           row.get("budget_origin_monotonic", 0.0)),
                    row.get("budget_origin_monotonic", 0.0), 100.0)
                request = DecisionRequest(
                    observation=recorded.observation, competition=recorded.competition,
                    rules=analysis, decision_id=recorded.decision_id,
                    trigger_seq=recorded.trigger_seq, window_key=recorded.window_key,
                    rejected_attempts=())
                plan = asyncio.run(baseline.choose(request, budget))
                first_key = recompute._first_key(plan)
            except Exception:
                continue
        hand_codes = [tile.code for tile in recorded.observation.my_hand]
        for shape, spec in pending.items():
            if not all(item in kinds for item in spec.get("kinds", ())):
                continue
            if spec.get("has_wealth") and not any(
                    code == recorded.observation.rule_state.wealth_god.code
                    for code in hand_codes):
                continue
            if spec.get("first_not_kind") is not None:
                if recompute._kind(first_key) == spec["first_not_kind"]:
                    continue
            if spec.get("first_not_key") is not None:
                if first_key == spec["first_not_key"]:
                    continue
            found[shape].append(dict(row))
    return found


def build_trigger_rows(rows: Sequence[Mapping[str, Any]], ruleset: str = "v26",
                       per_shape: int = 3,
                       ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """按（骨架 × 规则状态网格）生成触发集；返回 (行, 生成报告)。

    **每个位点取多个骨架**：单个骨架的翻转位点很窄（例如某个杠本来就排在首位，
    候选再怎么加也翻不动），只取一个会得到"看起来零改选"的假象。
    实测：每形态 1 个骨架时 16 行、改选 1；扩到 3 个才有足够的位点覆盖。
    """

    skeletons = pick_skeletons(rows, ruleset=ruleset, per_shape=per_shape)
    out: List[Dict[str, Any]] = []
    for shape, picked in sorted(skeletons.items()):
        for index, row in enumerate(picked):
            recorded = decision_request_from_json(row["request"])
            for chain_count, baotou, chain_piao in TRIGGER_STATES:
                observation = dataclasses.replace(
                    recorded.observation,
                    chain_piao=chain_piao,
                    rule_state=RulePublicState(
                        wealth_god=Tile(recorded.observation.rule_state.wealth_god.code),
                        baotou=baotou,
                        chain_count=chain_count,
                        catch_play=recorded.observation.rule_state.catch_play,
                        catch_play_owner_seat=(
                            recorded.observation.rule_state.catch_play_owner_seat),
                    ),
                )
                rewritten = dataclasses.replace(recorded, observation=observation)
                out.append({
                    "trigger_grid": {"shape": shape, "skeleton_index": index,
                                     "chain_count": chain_count,
                                     "baotou": baotou, "chain_piao": chain_piao},
                    "base_decision_id": row.get("decision_id"),
                    "base_hand_id": row.get("hand_id"),
                    "request": decision_request_to_json(rewritten),
                    "budget": row.get("budget"),
                    "budget_origin_monotonic": row.get("budget_origin_monotonic", 0.0),
                })
    report = {"skeletons": {shape: [row.get("decision_id") for row in picked]
                            for shape, picked in sorted(skeletons.items())},
              "skeletons_per_shape": per_shape,
              "grid_rows": len(out),
              "states": [list(item) for item in TRIGGER_STATES]}
    return out, report


def coverage_of_corpus(rows: Sequence[Mapping[str, Any]], ruleset: str = "v26"
                       ) -> Dict[str, Any]:
    """真实语料的规则状态覆盖：回答"语料到底有没有**可用**触发面"。

    这是本工具最重要的诊断输出——价值族② 的"零改选"必须能与
    "语料没有链状态"区分开，否则门禁的理由是错的。

    **必须分两层报**（2026-09-15 按对抗性复核更正）：
      `raw_*`    —— 直接读观察得到的原始覆盖，**不做任何过滤**；
      `usable_*` —— 再经 `HangmaRules.analyze`（完整且有合法候选）后的门禁可用窗口。
    只报后者会把"被规则层降级排除"误读成"数据里不存在"。
    """

    rules = HangmaRules(RuleConfig(ruleset_version=ruleset, base_score=1,
                                   you_cai_bi_kao=False))
    # ★ 两个量必须**分开统计**（2026-09-15 修正，由对抗性复核撞出）：
    #
    # 初版只统计"规则分析完整且有合法候选"的窗口，把 `chain_count` 直方图建在那个子集上。
    # 而 `engine.py:87` 对「`chain_count > 0` 且 `chain_piao` 为空」会记 RuleIssue 使窗口 DEGRADED——
    # 本语料**没有任何一行带 `chain_piao` 键**，于是**任何链状态窗口都会被降级排除**，
    # 直方图**在构造上只能得 0**。实测原始数据是 3343 行里 `{0: 3342, 1: 1}`，不是 0。
    # 把"原始覆盖"与"门禁可用窗口"混成一个量，就会得出一个由测量方式决定的假结论。
    raw_rows = 0
    raw_chain_hist: collections.Counter = collections.Counter()
    raw_baotou_true = 0
    raw_piao_known = 0
    usable = 0
    usable_chain_hist: collections.Counter = collections.Counter()
    degraded_with_chain = 0
    for row in rows:
        payload = row.get("request")
        if not isinstance(payload, Mapping):
            continue
        try:
            recorded = decision_request_from_json(payload)
        except Exception:
            continue
        observation = recorded.observation
        state = observation.rule_state
        raw_rows += 1
        raw_chain_hist[state.chain_count] += 1
        if state.baotou:
            raw_baotou_true += 1
        if observation.chain_piao is not None:
            raw_piao_known += 1
        try:
            analysis = rules.analyze(observation)
        except Exception:
            continue
        if analysis.completeness is RuleCompleteness.DEGRADED or not analysis.legal_candidates:
            if state.chain_count > 0:
                degraded_with_chain += 1
            continue
        usable += 1
        usable_chain_hist[state.chain_count] += 1
    raw_nonzero = raw_rows - raw_chain_hist.get(0, 0)
    usable_nonzero = usable - usable_chain_hist.get(0, 0)
    if raw_nonzero and not usable_nonzero:
        verdict = ("语料**含**链状态 {0} 个，但它们**全部**被规则分析降级排除"
                   "（本语料无一行记录 `chain_piao`）⇒ 链路径候选在本语料上**没有可用触发面**。"
                   "注意这不是『没有链状态』。").format(raw_nonzero)
    elif not raw_nonzero:
        verdict = "语料确实不含链状态"
    else:
        verdict = "语料含可用链状态"
    return {"raw_windows": raw_rows,
            "raw_chain_count_histogram": {str(k): v
                                          for k, v in sorted(raw_chain_hist.items())},
            "raw_chain_count_nonzero": raw_nonzero,
            "raw_baotou_true": raw_baotou_true,
            "raw_chain_piao_known": raw_piao_known,
            "usable_windows": usable,
            "usable_chain_count_histogram": {str(k): v for k, v in
                                             sorted(usable_chain_hist.items())},
            "usable_chain_count_nonzero": usable_nonzero,
            "degraded_windows_with_chain": degraded_with_chain,
            "verdict": verdict}


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="坐隐：规则可枚举触发窗口集（构造集）")
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", required=True, help="触发集 JSONL")
    ap.add_argument("--report", required=True, help="生成报告 JSON")
    ap.add_argument("--corpus-limit", type=int, default=4000)
    ap.add_argument("--skeletons-per-shape", type=int, default=3)
    args = ap.parse_args(argv)

    rows = gates.load_corpus(Path(args.corpus), limit=args.corpus_limit)
    coverage = coverage_of_corpus(rows)
    trigger_rows, report = build_trigger_rows(
        rows, per_shape=args.skeletons_per_shape)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        for row in trigger_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    report["corpus_coverage"] = coverage
    report["note"] = ("触发集是**构造集**：只用于证明接线到达候选与提供可触发作用面；"
                      "禁止用于效应估计、排序或晋级声明；准入仍以真实语料为准。")
    Path(args.report).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"corpus_coverage": coverage, "grid_rows": len(trigger_rows)},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
