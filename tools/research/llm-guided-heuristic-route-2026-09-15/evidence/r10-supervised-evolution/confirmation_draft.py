"""独立确认的纯分析原型：只验输入与计算，不运行桌赛、不批准发布。

复用 C2 的根内配对聚合，使用原方案固定样本 Hoeffding 下界。调用者必须
在运行前保存 registration_digest，并从独立执行器提供 execution_identity。
本模块不能证明预登记时间、来源台账真实或随机根独立；正式执行接线仍待完成。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

TOOLS = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/tools')
sys.path.insert(0, str(TOOLS))
import sitin_archive as archive


def digest(value: Any) -> str:
    """严格 JSON 的规范摘要；非有限数直接报错，不写文件。"""
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def analysis_identity() -> dict:
    """绑定此分析器与被调用的纯统计模块，供预登记冻结。"""
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (Path(__file__), Path(archive.__file__))}


def _require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def _number(value: Any, label: str) -> float:
    _require(type(value) in (int, float) and math.isfinite(value),
             label + " 必须是有限数，布尔值不算数值")
    return float(value)


def _text(value: Any, label: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()), label + " 缺失")
    return value


def _sha(value: Any, label: str) -> str:
    _require(isinstance(value, str) and len(value) == 64
             and all(char in "0123456789abcdef" for char in value), label + " 非 SHA256")
    return value


def validate_registration(plan: Mapping[str, Any], *, frozen_digest: str,
                          source_ledger: Sequence[Mapping[str, Any]]) -> dict:
    """核验冻结配置与运行前来源台账；错误抛 ValueError，零副作用。

    roots 声明每个独立随机根及 H/M 情景。independence_id 必须来自生成器的
    随机抽样身份；换名字或换对手不会把同一随机根变成独立根。当前版要求
    H/M 各使用不同根且数量相等，遇到共享根直接拒绝，不按两份样本计算。
    source_ledger 为运行前完整台账；exposures 记录生成、选择、诊断等既往消费。
    """
    _require(digest(plan) == frozen_digest, "预登记摘要漂移")
    _require(plan.get("schema") == "sitin-confirmation-analysis-draft/1", "预登记版本不支持")
    _require(plan.get("analysis_identity") == analysis_identity(), "分析实现漂移")
    _require(plan.get("source_ledger_digest") == digest(source_ledger), "来源台账漂移")
    _require(plan.get("metric") == "group_advance_v1", "目标不支持")
    _require(plan.get("direction") == "higher_is_better", "方向不支持")
    _require(_number(plan.get("null_threshold"), "零假设阈值") == 0, "零假设须为不优于 V2")
    effect = _number(plan.get("minimum_effect"), "最小有意义改善")
    _require(0 <= effect < 1, "最小有意义改善越界")
    _require(plan.get("method") == "one_sided_hoeffding_root_lower_v1", "分析方法不支持")
    _require(plan.get("stopping") == "fixed_complete_no_optional_stopping", "停止规则不支持")
    _require(plan.get("mixture_weights") == {"H": 0.5, "M": 0.5}, "必须 H/M 等权")
    _require(plan.get("seats") == [0, 1, 2, 3]
             and all(type(x) is int for x in plan["seats"]), "必须完整四换座")
    tables = plan.get("tables_per_arm")
    _require(type(tables) is int and tables > 0, "每臂桌数无效")
    for field in ("candidate_id", "baseline_id", "execution_identity", "stage_format_identity"):
        _text(plan.get(field), field)
    _require(plan["candidate_id"] != plan["baseline_id"], "不能自比较后宣称改善")

    # 有限批次误报预算在看数前一次冻结；真正的消耗顺序由后续持久账本保证。
    campaign = plan.get("multiplicity", {})
    _text(campaign.get("campaign_id"), "确认活动身份")
    allocations = campaign.get("allocations")
    _require(isinstance(allocations, list) and bool(allocations), "缺少跨候选显著性分配")
    alphas = [_number(a, "显著性分配") for a in allocations]
    _require(all(0 < a <= 0.05 for a in alphas) and math.fsum(alphas) <= 0.05,
             "活动总误报预算超过 0.05 或分配无效")
    slot = campaign.get("slot")
    _require(type(slot) is int and 0 <= slot < len(alphas), "确认预算槽无效")
    alpha = _number(plan.get("alpha"), "单次显著性")
    _require(alpha == alphas[slot], "显著性与活动分配不符")

    roots = plan.get("roots")
    _require(isinstance(roots, list) and bool(roots), "缺少冻结根清单")
    _require(type(plan.get("n_roots")) is int and plan["n_roots"] == len(roots), "固定样本量不符")
    seen_ids, seen_contents, seen_draws = set(), set(), set()
    by_id = {}
    ledger_contents, ledger_draws = set(), set()
    for item in source_ledger:
        root_id = _text(item.get("source_root_id"), "台账根身份")
        _require(root_id not in by_id, "来源台账重复身份")
        content = _sha(item.get("root_content_digest"), "台账根内容摘要")
        draw = _text(item.get("independence_id"), "台账随机抽样身份")
        _require(content not in ledger_contents and draw not in ledger_draws,
                 "来源台账内容或随机根别名重复")
        ledger_contents.add(content)
        ledger_draws.add(draw)
        _require(isinstance(item.get("exposures"), list), "台账消费记录缺失")
        _require(item.get("usage") in archive.ROOT_USAGES, "台账用途未知")
        _require(item.get("opponent_mix") in ("H", "M"), "台账情景未知或缺失")
        by_id[root_id] = item
    for root in roots:
        root_id = _text(root.get("source_root_id"), "根身份")
        content = _sha(root.get("root_content_digest"), "根内容摘要")
        draw = _text(root.get("independence_id"), "随机抽样身份")
        _require(root_id not in seen_ids and content not in seen_contents and draw not in seen_draws,
                 "重复根、内容别名或共享随机根")
        seen_ids.add(root_id); seen_contents.add(content); seen_draws.add(draw)
        _require(root.get("opponent_mix") in ("H", "M"), "根情景未知")
        item = by_id.get(root_id)
        _require(item is not None and item["root_content_digest"] == content
                 and item["independence_id"] == draw, "根与台账身份不符")
        _require(item["opponent_mix"] == root["opponent_mix"], "根情景与台账不符")
        _require(item["usage"] == "confirmation" and not item["exposures"],
                 "确认根已有开发或确认消费")
    counts = {mix: sum(r["opponent_mix"] == mix for r in roots) for mix in ("H", "M")}
    _require(counts["H"] == counts["M"] and counts["H"] > 0, "H/M 独立根数量必须均衡")
    return {"alpha": alpha, "minimum_effect": effect, "counts": counts}


def analyze(plan: Mapping[str, Any], samples: Sequence[Mapping[str, Any]], *,
            frozen_digest: str, source_ledger: Sequence[Mapping[str, Any]],
            execution_identity: str) -> dict:
    """核验全量四换座双臂输入，再给出保守下界；不是赛事发布许可。

    执行器需独立传入冻结的运行身份，并事先验证原始桌赛、积分与 U 的关系。
    本函数只消费终端 U 区间，不重新实现赛事计分；输入不完整即拒绝整批，
    不删除失败样本后计算。全部结果均标 release_eligible=False。
    """
    config = validate_registration(plan, frozen_digest=frozen_digest, source_ledger=source_ledger)
    _require(execution_identity == plan["execution_identity"], "运行身份漂移")
    roots = {r["source_root_id"]: r for r in plan["roots"]}
    expected_cells = {(root, seat) for root in roots for seat in plan["seats"]}
    seen = set()
    for sample in samples:
        root_id = sample.get("source_root_id")
        _require(root_id in roots, "出现未预登记根")
        seat = sample.get("focal_anchor_seat")
        _require(type(seat) is int and seat in plan["seats"], "座位身份无效")
        cell = (root_id, seat)
        _require(cell not in seen, "重复座位行")
        seen.add(cell)
        root = roots[root_id]
        _require(sample.get("root_content_digest") == root["root_content_digest"]
                 and sample.get("opponent_mix") == root["opponent_mix"], "样本根身份漂移")
        _require(sample.get("scenario") == "normal" and sample.get("root_usage") == "confirmation",
                 "必须是完整自然确认阶段")
        _require(sample.get("candidate_id") == plan["candidate_id"]
                 and sample.get("self_comparison", False) is False, "样本候选身份错误")
        _require(sample.get("completeness") == "complete" and sample.get("invalid", False) is False
                 and not sample.get("invalid_reasons"), "样本执行不完整")
        expected = sample.get("root_expected")
        _require(digest(expected) == digest({"seats": 4, "arms": ["baseline", "candidate"],
                             "tables_per_arm": plan["tables_per_arm"]}), "赛程清单漂移")
        arms = sample.get("arms", {})
        _require(set(arms) == {"baseline", "candidate"}, "双臂不完整")
        for label, identity in (("baseline", plan["baseline_id"]), ("candidate", plan["candidate_id"])):
            arm = arms[label]
            _require(arm.get("candidate_id") == identity, "单臂身份漂移")
            _require(arm.get("status") == "complete" and arm.get("usable") is True
                     and not arm.get("error"), "单臂执行失败")
            low = _number(arm.get("u_low"), "U 下界")
            high = _number(arm.get("u_high"), "U 上界")
            _require(0 <= low <= high <= 1, "U 区间越界或颠倒")
            if arm.get("u") is not None:
                point = _number(arm["u"], "U 点值")
                _require(low <= point <= high, "U 点值不在区间内")
    _require(seen == expected_cells, "固定样本未完成，缺根或缺座位；禁止中途分析")
    stats = archive.paired_stage_statistics(samples)
    panels = stats["by_candidate"][plan["candidate_id"]]["panels"]["normal"]["panels"]
    rows = [row for mix in ("H", "M") for row in panels[mix]["root_rows"]]
    _require(len(rows) == plan["n_roots"] and all(p["manifest_complete"] for p in panels.values()),
             "聚合器整根完整性检查失败")
    mean_low = math.fsum(row["d_low"] for row in rows) / len(rows)
    penalty = math.sqrt(2 * math.log(1 / config["alpha"]) / len(rows))
    lower = mean_low - penalty
    significant = lower > 0
    # 更强的实际意义判据：下界而非点估计也达到预登记最小改善。
    meaningful = lower >= config["minimum_effect"]
    return {"schema": "sitin-confirmation-analysis-result-draft/1",
            "registration_digest": frozen_digest, "samples_digest": digest(samples),
            "n_independent_roots": len(rows), "roots_per_mix": config["counts"],
            "mean_lower_delta": mean_low, "hoeffding_penalty": penalty,
            "lower_confidence_bound": lower, "alpha": config["alpha"],
            "statistical_pass": significant, "minimum_effect_pass": meaningful,
            "analysis_status": "PASS_ANALYSIS_ONLY" if significant and meaningful else "INCONCLUSIVE",
            "release_eligible": False, "root_rows": rows,
            "limitations": ["未接入原始桌赛和目标计算校验", "未接入持久确认消费与显著性支出账本",
                            "未验证实际赛事赛制与发布可靠性门禁", "不能由该结果宣称候选可发布"]}
