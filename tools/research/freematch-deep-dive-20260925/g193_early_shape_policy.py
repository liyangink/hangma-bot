"""G193 离线候选：三向听早期牌形宽面，保留冻结父代风险与近端路线门。"""

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

import g171_pareto_width_policy as old
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.policy.action_value_policy import ActionValuePolicy
from hangma_bot.policy.action_value_seeds import ActionValueScorer
from hangma_bot.policy.evaluation_v1 import build_context
from hangma_bot.policy.r18_integrated_positive_v2 import (
    R18_INTEGRATED_POSITIVE_V2_NAME,
    R18_INTEGRATED_POSITIVE_V2_SOURCE,
)


POLICY_ID = "action_value_v1:research:g193-early-three-shanten-v1"
MAX_PARENT_SCORE_GAP = 4.0
MIN_STANDARD_CAPACITY_GAIN = 3
NONWHITE_HONORS = frozenset("东南西北中发")


def _positive_width(tiles) -> tuple[int, int] | None:
    """只计正的公开未知物理容量，零容量牌码不算可摸进张。"""
    if tiles is None:
        return None
    values = [item.remaining_estimate for item in tiles]
    if any(type(value) is not int or not 0 <= value <= 4 for value in values):
        return None
    return sum(value > 0 for value in values), sum(values)


def select(request, plan) -> tuple[str | None, dict, bool]:
    """仅同窗可见事实；返回一次合法改弃或明确弃权原因。"""
    if request.window_key.phase.value != "draw" or not plan.candidates:
        return None, {"reason": "not_draw_or_empty"}, False
    if request.rejected_attempts:
        return None, {"reason": "previous_attempt_rejected"}, False
    parent_key = plan.candidates[0].action_key
    if not parent_key.startswith("discard:") or parent_key == "discard:白":
        return None, {"reason": "parent_not_nonwhite_discard"}, False
    observation = request.observation
    if observation.melds[observation.seat]:
        return None, {"reason": "own_meld_present"}, False
    if observation.rule_state.baotou or observation.rule_state.chain_count:
        return None, {"reason": "active_baotou_or_chain"}, False
    # 生产评分上下文已处理“my_hand 同时含摸牌与单列 drawn_tile”的官方形态。
    visible_context = build_context(observation)
    white_before = visible_context.wealth_count
    if white_before > 1:
        return None, {"reason": "two_plus_whites"}, False
    ranked = {item.action_key: item for item in plan.candidates}
    legal = {item.action_key: item for item in request.rules.legal_candidates}
    if (len(ranked) != len(plan.candidates)
            or len(legal) != len(request.rules.legal_candidates)
            or parent_key not in legal):
        return None, {"reason": "candidate_identity_mismatch"}, False
    parent = legal[parent_key].facts
    if parent is None or parent.standard_shanten_after != 3:
        return None, {"reason": "parent_not_three_shanten"}, False
    parent_standard = _positive_width(parent.standard_useful_tiles)
    if parent_standard is None:
        return None, {"reason": "parent_standard_unknown"}, False
    broad = []
    for item in plan.candidates[1:]:
        key = item.action_key
        if not key.startswith("discard:") or key == "discard:白" or key not in legal:
            continue
        facts = legal[key].facts
        if facts is None or facts.standard_shanten_after != 3:
            continue
        width = _positive_width(facts.standard_useful_tiles)
        if (width is not None and width[0] > parent_standard[0]
                and width[1] >= parent_standard[1] + MIN_STANDARD_CAPACITY_GAIN):
            broad.append((key, width, facts))
    if not broad:
        return None, {"reason": "no_strict_broad_alternate"}, False
    parent_combined = _positive_width(parent.useful_tiles)
    parent_risk = old._risk(ranked[parent_key])
    if (type(parent.shanten_after) is not int
            or type(parent.seven_pairs_shanten_after) is not int
            or parent_combined is None or parent_risk is None):
        return None, {"reason": "parent_route_or_risk_unknown",
                      "broad_count": len(broad)}, True
    admissible = []
    veto = {"combined_shanten": 0, "combined_capacity": 0,
            "seven_pairs_shanten": 0, "risk_units": 0,
            "score_gap": 0, "unknown": 0}
    for key, width, facts in broad:
        combined = _positive_width(facts.useful_tiles)
        risk = old._risk(ranked[key])
        gap = ranked[parent_key].total_score - ranked[key].total_score
        if (type(facts.shanten_after) is not int
                or type(facts.seven_pairs_shanten_after) is not int
                or combined is None or risk is None
                or not math.isfinite(gap)):
            veto["unknown"] += 1
        elif facts.shanten_after > parent.shanten_after:
            veto["combined_shanten"] += 1
        elif combined[1] < parent_combined[1]:
            veto["combined_capacity"] += 1
        elif facts.seven_pairs_shanten_after > parent.seven_pairs_shanten_after:
            veto["seven_pairs_shanten"] += 1
        elif risk > parent_risk:
            veto["risk_units"] += 1
        elif gap < -1e-8 or gap > MAX_PARENT_SCORE_GAP:
            veto["score_gap"] += 1
        else:
            admissible.append((key, width, combined, risk, gap, facts))
    if not admissible:
        return None, {"reason": "no_guarded_alternate",
                      "broad_count": len(broad), "veto": veto}, True
    def isolated_honor(key: str) -> bool:
        code = key.split(":", 1)[1]
        return (code in NONWHITE_HONORS
                and visible_context.combined_codes.count(code) == 1)

    chosen = min(admissible, key=lambda item: (-item[1][0], -item[1][1],
                                               item[4], -int(isolated_honor(item[0])),
                                               item[0]))
    return chosen[0], {
        "reason": "early_three_shanten_shape",
        "parent_action": parent_key, "alternate_action": chosen[0],
        "white_before": white_before,
        "parent_standard_width": parent_standard,
        "alternate_standard_width": chosen[1],
        "parent_seven_pairs_shanten": parent.seven_pairs_shanten_after,
        "alternate_seven_pairs_shanten": chosen[5].seven_pairs_shanten_after,
        "parent_risk_units": parent_risk,
        "alternate_risk_units": chosen[3],
        "parent_score_gap": chosen[4],
        "alternate_isolated_honor": isolated_honor(chosen[0]),
        "broad_count": len(broad),
        "admissible_count": len(admissible),
    }, True


class EarlyShapePolicy:
    """离线研究包装：父代排序后每个官方单局最多接受一次目标冲突。"""

    policy_id = POLICY_ID

    def __init__(self, baseline, metrics: list[dict]) -> None:
        self.baseline = baseline
        self.metrics = metrics
        self.hand_seen: set[tuple[str, int]] = set()

    async def choose(self, request, budget):
        """不改变合法动作集合；缺事实或异常时原样返回父代计划。"""
        baseline = await self.baseline.choose(request, budget)
        hand_key = (request.window_key.game_id, request.window_key.round_no)
        if hand_key in self.hand_seen:
            return baseline
        started = time.perf_counter()
        try:
            key, evidence, consumed = select(request, baseline)
        except Exception as exc:
            key, consumed = None, False
            evidence = {"reason": "selector_exception", "error_type": type(exc).__name__}
        elapsed_ms = (time.perf_counter() - started) * 1000
        if consumed:
            self.hand_seen.add(hand_key)
        if key is None:
            if consumed or evidence["reason"] in (
                    "selector_exception", "candidate_identity_mismatch"):
                self.metrics.append({"decision_id": request.decision_id,
                                     "status": "guarded_or_fallback", **evidence,
                                     "elapsed_ms": round(elapsed_ms, 3)})
            return baseline
        selected = next((item for item in baseline.candidates
                         if item.action_key == key), None)
        if selected is None:
            self.metrics.append({"decision_id": request.decision_id,
                                 "status": "fallback", "reason": "selected_not_in_plan"})
            return baseline
        ordered = (selected,) + tuple(item for item in baseline.candidates
                                      if item.action_key != key)
        ranked = tuple(replace(item, rank=index + 1,
                               reasons=item.reasons + (("G193 三向听早期牌形",)
                                                       if index == 0 else ()))
                       for index, item in enumerate(ordered))
        self.metrics.append({"decision_id": request.decision_id,
                             "status": "adopted", "action": key,
                             **evidence, "elapsed_ms": round(elapsed_ms, 3)})
        return replace(baseline, candidates=ranked)


def research_parent_factory(monotonic):
    """当前规则上的离线父代；源码/限额同 R18 v2，不冒充旧发布包。"""
    del monotonic
    return ActionValuePolicy(
        ActionValueScorer(R18_INTEGRATED_POSITIVE_V2_NAME,
                          R18_INTEGRATED_POSITIVE_V2_SOURCE),
        value_limits=ValueAnalysisLimits(),
    )


def policy_factory(metrics: list[dict]):
    """只离线装配冻结 R18 v2 算法；当前规则变化后不得冒充旧发布包。"""

    def build(monotonic):
        return EarlyShapePolicy(research_parent_factory(monotonic), metrics)

    return build
