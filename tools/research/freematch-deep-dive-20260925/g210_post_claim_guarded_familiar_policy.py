"""G210 离线候选：仅在熟牌重估动作严格扩大已副露普通进张且风险不退时改弃。"""

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
from pathlib import Path
import time

from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.policy.action_value_policy import ActionValuePolicy
from hangma_bot.policy.action_value_seeds import ActionValueScorer
from hangma_bot.policy.r18_integrated_positive_v2 import (
    R18_INTEGRATED_POSITIVE_V2_NAME,
    R18_INTEGRATED_POSITIVE_V2_SOURCE,
)


HERE = Path(__file__).resolve().parent
G88_SOURCE = (_project_file(_PROJECT_ROOT, HERE / "candidates/G88-POST-CLAIM-FAMILIAR-BIAS-V1.py")).read_text(encoding="utf-8")
POLICY_ID = "action_value_v1:research:g210-postclaim-guarded-familiar-v1"


def _width(tiles) -> tuple[int, int] | None:
    """当前玩家可见公开容量中的正容量牌码数与张数。"""
    if tiles is None:
        return None
    values = [item.remaining_estimate for item in tiles]
    if any(type(value) is not int or value < 0 or value > 4 for value in values):
        return None
    return sum(value > 0 for value in values), sum(values)


def _risk(item) -> float | None:
    """读冻结 R18 分量，不把缺失的风险或未知结果当零。"""
    trace = item.score_trace
    if not isinstance(trace, dict) or trace.get("trace_schema") != "sitin-action-score-trace/1":
        return None
    detail = trace.get("detail")
    if not isinstance(detail, dict):
        return None
    risk = detail.get("risk_units")
    if type(risk) not in (int, float) or not math.isfinite(risk) or risk < 0:
        return None
    return float(risk)


def select(request, parent, familiar) -> tuple[str | None, dict]:
    """只用同窗合法事实决定是否采纳 G88 提案；否则保持父代动作顺序。"""
    if request.window_key.phase.value != "draw" or request.rejected_attempts:
        return None, {"reason": "not_normal_draw"}
    observation = request.observation
    if not any(meld.kind in ("chi", "peng")
               for meld in observation.melds[observation.seat]):
        return None, {"reason": "not_claimed"}
    if not parent.candidates or not familiar.candidates:
        return None, {"reason": "empty_plan"}
    parent_key, alt_key = parent.candidates[0].action_key, familiar.candidates[0].action_key
    if parent_key == alt_key:
        return None, {"reason": "same_action"}
    wealth = observation.rule_state.wealth_god.code
    if (not parent_key.startswith("discard:") or not alt_key.startswith("discard:")
            or parent_key == "discard:" + wealth or alt_key == "discard:" + wealth):
        return None, {"reason": "not_two_nonwhite_discards"}
    ranked = {item.action_key: item for item in parent.candidates}
    legal = {item.action_key: item for item in request.rules.legal_candidates}
    if (len(ranked) != len(parent.candidates)
            or len(legal) != len(request.rules.legal_candidates)
            or parent_key not in legal or alt_key not in legal or alt_key not in ranked):
        return None, {"reason": "candidate_identity_mismatch"}
    p, a = legal[parent_key].facts, legal[alt_key].facts
    if p is None or a is None:
        return None, {"reason": "unknown_rule_facts"}
    if (type(p.standard_shanten_after) is not int
            or type(a.standard_shanten_after) is not int
            or p.standard_shanten_after != a.standard_shanten_after):
        return None, {"reason": "standard_shanten_mismatch"}
    p_w, a_w = _width(p.standard_useful_tiles), _width(a.standard_useful_tiles)
    if p_w is None or a_w is None or a_w[0] <= p_w[0] or a_w[1] <= p_w[1]:
        return None, {"reason": "no_strict_width_gain"}
    p_comb, a_comb = _width(p.useful_tiles), _width(a.useful_tiles)
    if (type(p.shanten_after) is not int or type(a.shanten_after) is not int
            or a.shanten_after > p.shanten_after
            or p_comb is None or a_comb is None or a_comb[1] < p_comb[1]):
        return None, {"reason": "combined_regression_or_unknown"}
    if p.baotou_after is True and a.baotou_after is not True:
        return None, {"reason": "baotou_regression"}
    p_risk, a_risk = _risk(ranked[parent_key]), _risk(ranked[alt_key])
    if p_risk is None or a_risk is None or a_risk > p_risk:
        return None, {"reason": "risk_regression_or_unknown"}
    return alt_key, {
        "reason": "strict_postclaim_width_after_familiar_revaluation",
        "parent_action": parent_key, "alternate_action": alt_key,
        "ordinary_shanten": p.standard_shanten_after,
        "ordinary_width_parent": p_w, "ordinary_width_alternate": a_w,
        "risk_units_parent": p_risk, "risk_units_alternate": a_risk,
    }


class GuardedFamiliarPolicy:
    """离线候选包装：R18 先评分，G88 仅提议，规则与风险门独立复核。"""

    policy_id = POLICY_ID

    def __init__(self, parent, familiar, metrics: list[dict]) -> None:
        self.parent = parent
        self.familiar = familiar
        self.metrics = metrics

    async def choose(self, request, budget):
        """返回父代合法计划或仅重排其一个合法弃牌；所有异常回退父代。"""
        parent = await self.parent.choose(request, budget)
        if request.window_key.phase.value != "draw" or request.rejected_attempts:
            return parent
        if not any(meld.kind in ("chi", "peng")
                   for meld in request.observation.melds[request.observation.seat]):
            return parent
        started = time.perf_counter()
        try:
            familiar = await self.familiar.choose(request, budget)
            chosen, evidence = select(request, parent, familiar)
        except Exception as exc:
            chosen = None
            evidence = {"reason": "selector_exception", "error_type": type(exc).__name__}
        elapsed_ms = (time.perf_counter() - started) * 1000
        if chosen is None:
            if evidence["reason"] in ("selector_exception", "candidate_identity_mismatch",
                                       "unknown_rule_facts", "risk_regression_or_unknown"):
                self.metrics.append({"decision_id": request.decision_id,
                                     "status": "fallback", **evidence,
                                     "elapsed_ms": round(elapsed_ms, 3)})
            return parent
        selected = next((item for item in parent.candidates if item.action_key == chosen), None)
        if selected is None:
            self.metrics.append({"decision_id": request.decision_id,
                                 "status": "fallback", "reason": "selected_not_in_parent"})
            return parent
        ordered = (selected,) + tuple(item for item in parent.candidates
                                      if item.action_key != chosen)
        ranked = tuple(replace(item, rank=index + 1,
                               reasons=item.reasons + (("G210 已副露宽进张熟牌交换",)
                                                       if index == 0 else ()))
                       for index, item in enumerate(ordered))
        self.metrics.append({"decision_id": request.decision_id,
                             "status": "adopted", **evidence,
                             "elapsed_ms": round(elapsed_ms, 3)})
        return replace(parent, candidates=ranked)


def parent_factory(monotonic):
    """用当前规则装配冻结 R18 v2 评分源码，不伪称旧发布包摘要。"""
    del monotonic
    return ActionValuePolicy(
        ActionValueScorer(R18_INTEGRATED_POSITIVE_V2_NAME,
                          R18_INTEGRATED_POSITIVE_V2_SOURCE),
        value_limits=ValueAnalysisLimits(),
    )


def policy_factory(metrics: list[dict]):
    """为每个离线阶段隔离父代、G88 提议器及候选指标。"""
    def build(monotonic):
        return GuardedFamiliarPolicy(
            parent_factory(monotonic),
            ActionValuePolicy(
                ActionValueScorer("g88_post_claim_familiar_v1", G88_SOURCE),
                value_limits=ValueAnalysisLimits(),
            ),
            metrics,
        )
    return build
