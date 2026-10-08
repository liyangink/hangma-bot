"""G237：只在数牌备选中测试 R18 v2 的自然宽面评分反转。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from dataclasses import replace
import math
import time

import g193_early_shape_policy as g193
import g232_base_width_inversion as g232
import g235_all_window_route_conflict as g235


POLICY_ID = "action_value_v1:research:g237-numeric-inversion-v1"


def _numeric_discard(key: str) -> bool:
    """动作键使用生产 `discard:牌码`，仅接受三门数牌。"""
    if not key.startswith("discard:"):
        return False
    code = key.split(":", 1)[1]
    return len(code) == 2 and code[0] in "123456789" and code[1] in "wbt"


def select(request, plan) -> tuple[str | None, dict]:
    """在已合法动作中选一次数牌宽面反转；所有未知回退父代。"""
    observation = request.observation
    if (request.window_key.phase.value != "draw" or observation.drawn_tile is None
            or observation.gang_draw is True or request.rejected_attempts
            or any("action_value_failed" in reason for reason in plan.degraded_reasons)):
        return None, {"reason": "not_clean_normal_draw"}
    if not plan.candidates:
        return None, {"reason": "empty_parent_plan"}
    parent_key = plan.candidates[0].action_key
    if (not parent_key.startswith("discard:") or parent_key == "discard:白"):
        return None, {"reason": "parent_not_nonwhite_discard"}
    legal = {item.action_key: item for item in request.rules.legal_candidates}
    ranked = {item.action_key: item for item in plan.candidates}
    if (len(legal) != len(request.rules.legal_candidates)
            or len(ranked) != len(plan.candidates)
            or parent_key not in legal or set(legal) != set(ranked)
            or "hu" in legal):
        return None, {"reason": "candidate_identity_or_hu"}
    parent = legal[parent_key].facts
    if (parent is None or type(parent.standard_shanten_after) is not int
            or parent.standard_shanten_after not in (1, 2, 3)):
        return None, {"reason": "parent_shape_unknown_or_outside"}
    parent_width = g232.width(parent.standard_useful_tiles)
    parent_combined = g232.width(parent.useful_tiles)
    parent_parts = g235._parts(ranked[parent_key])
    if (parent_width is None or parent_combined is None or parent_parts is None
            or type(parent.shanten_after) is not int
            or type(parent.seven_pairs_shanten_after) is not int):
        return None, {"reason": "parent_route_or_score_unknown"}
    choices = []
    for item in plan.candidates[1:]:
        key = item.action_key
        if not _numeric_discard(key):
            continue
        facts = legal[key].facts
        if (facts is None or type(facts.standard_shanten_after) is not int
                or facts.standard_shanten_after != parent.standard_shanten_after):
            continue
        width = g232.width(facts.standard_useful_tiles)
        combined = g232.width(facts.useful_tiles)
        parts = g235._parts(item)
        if (width is None or combined is None or parts is None
                or type(facts.shanten_after) is not int
                or type(facts.seven_pairs_shanten_after) is not int):
            continue
        if (width[0] <= parent_width[0] or width[1] <= parent_width[1]
                or facts.shanten_after > parent.shanten_after
                or combined[1] < parent_combined[1]
                or facts.seven_pairs_shanten_after > parent.seven_pairs_shanten_after
                or parts["risk_units"] > parent_parts["risk_units"] + 1e-8
                or (parent.baotou_after is True and facts.baotou_after is not True)):
            continue
        delta_base = parts["base_score"] - parent_parts["base_score"]
        delta_river = parts["river_part"] - parent_parts["river_part"]
        delta_style = parts["style_part"] - parent_parts["style_part"]
        total = item.total_score - ranked[parent_key].total_score
        if (not math.isfinite(total) or delta_base <= 1e-8
                or total > 1e-8
                or total - delta_river - delta_style <= 1e-8):
            continue
        choices.append((key, width, round(-total, 8), facts))
    if not choices:
        return None, {"reason": "no_guarded_numeric_inversion"}
    key, width, gap, facts = min(choices, key=lambda row: (
        row[2], -row[1][0], -row[1][1], row[0]))
    return key, {
        "reason": "numeric_width_score_inversion",
        "parent_action": parent_key, "candidate_action": key,
        "parent_standard_width": list(parent_width),
        "candidate_standard_width": list(width),
        "parent_standard_shanten": parent.standard_shanten_after,
        "candidate_standard_shanten": facts.standard_shanten_after,
        "parent_seven_pairs_shanten": parent.seven_pairs_shanten_after,
        "candidate_seven_pairs_shanten": facts.seven_pairs_shanten_after,
        "parent_baotou_after": parent.baotou_after,
        "candidate_baotou_after": facts.baotou_after,
        "score_gap": gap,
        "eligible_numeric_alternatives": len(choices),
    }


class NumericInversionPolicy:
    """离线候选仅重排生产合法动作；父代完整计划始终作为保底。"""

    policy_id = POLICY_ID

    def __init__(self, baseline, metrics: list[dict]) -> None:
        self.baseline, self.metrics = baseline, metrics
        self.max_operations = getattr(baseline, "max_operations", None)

    async def choose(self, request, budget):
        """异常、未知或不在范围内均原样返回冻结 R18 v2 计划。"""
        plan = await self.baseline.choose(request, budget)
        started = time.perf_counter()
        try:
            key, evidence = select(request, plan)
        except Exception as exc:
            key = None
            evidence = {"reason": "selector_exception", "error_type": type(exc).__name__}
        elapsed_ms = (time.perf_counter() - started) * 1000
        if key is None:
            if evidence["reason"] == "selector_exception":
                self.metrics.append({"decision_id": request.decision_id,
                                     "status": "fallback", **evidence,
                                     "elapsed_ms": round(elapsed_ms, 3)})
            return plan
        selected = next((item for item in plan.candidates
                         if item.action_key == key), None)
        if selected is None:
            self.metrics.append({"decision_id": request.decision_id,
                                 "status": "fallback", "reason": "selected_not_in_plan"})
            return plan
        ordered = (selected,) + tuple(item for item in plan.candidates
                                      if item.action_key != key)
        ranked = tuple(replace(item, rank=index + 1,
                               reasons=item.reasons + (("G237 数牌宽面评分反转",)
                                                       if index == 0 else ()))
                       for index, item in enumerate(ordered))
        self.metrics.append({"decision_id": request.decision_id,
                             "status": "adopted", **evidence,
                             "elapsed_ms": round(elapsed_ms, 3)})
        return replace(plan, candidates=ranked)


def research_parent_factory(monotonic):
    """两臂共用当前规则绑定的冻结 R18 v2 算法源码及工作量限额。"""
    return g193.research_parent_factory(monotonic)


def policy_factory(metrics: list[dict]):
    """供同牌山完整桌面板装配候选策略。"""

    def build(monotonic):
        return NumericInversionPolicy(research_parent_factory(monotonic), metrics)

    return build
