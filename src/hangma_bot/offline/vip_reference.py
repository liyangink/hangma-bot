"""VIP 离线配对实验的冻结基础续打者；不参与线上策略闭环。"""

from __future__ import annotations

from functools import lru_cache

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.actions import Discard, Hu, Pass
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.policy.action_value_policy import build_scoring_view
from hangma_bot.policy.action_value_seeds import ActionValueScorer
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy.r18_integrated_positive_v2 import (
    R18_INTEGRATED_POSITIVE_V2_SOURCE,
)


@lru_cache(maxsize=1)
def _frozen_r18_scorer() -> ActionValueScorer:
    """离线诊断复用同一冻结源码；不得作为新 VIP 策略的线上接管。"""

    return ActionValueScorer("vip-p3-frozen-r18-reference",
                             R18_INTEGRATED_POSITIVE_V2_SOURCE)


def _choose_frozen_r18(rules: HangmaRules, decision):
    """仅按当前玩家观察评分；评分或动作映射失败时显式停止教师账。"""

    limits = ValueAnalysisLimits(max_expansions=8192)
    # 冻结 R18 只消费一次摸牌价值事实；路线前沿的条件投影不参与其评分。
    analysis = rules.analyze(decision.observation, value_limits=limits)
    request = DecisionRequest(
        observation=decision.observation,
        competition=CompetitionContext(
            tournament_id="vip-p3-reference", stage_no=None,
            stage_role=None, stage_total=None, participant_rank=None,
            ranking=(), observed_at_unix_ms=0,
        ),
        rules=analysis,
        decision_id=f"vip-p3-reference:{decision.window_key.trigger_seq}",
        trigger_seq=decision.window_key.trigger_seq,
        window_key=decision.window_key,
        rejected_attempts=(),
    )
    scored = _frozen_r18_scorer().score(
        build_scoring_view(request, value_limits=limits))
    if scored.status != "SCORED" or not scored.entries:
        raise ValueError("冻结 R18 续打者在当前玩家观察无法完整评分")
    top = min(scored.entries, key=lambda item: (-item.score, item.action_key))
    matches = [candidate.action for candidate in analysis.legal_candidates
               if candidate.action_key == top.action_key]
    if len(matches) != 1:
        raise ValueError("冻结 R18 首选不属于同次规则合法候选")
    return matches[0]


def choose_reference_action(rules: HangmaRules, decision, *, mode: str):
    """只消费依法可见观察与同源合法牌效，不读取完整模拟世界。"""

    if mode == "r18_frozen":
        return _choose_frozen_r18(rules, decision)
    candidates = rules.analyze(decision.observation).legal_candidates
    if decision.observation.phase.startswith("response_"):
        return Pass()
    win = next((item.action for item in candidates if isinstance(item.action, Hu)), None)
    if win is not None:
        return win
    discards = [item for item in candidates if isinstance(item.action, Discard)]
    if mode == "first_discard":
        return discards[0].action
    if mode != "shape":
        raise ValueError("未知参考续打者")

    def shape_key(item):
        facts = item.facts
        if facts is None or facts.shanten_after is None:
            raise ValueError("基础牌效参考者缺规则模块动作后牌效")
        return (facts.shanten_after,
                -sum(tile.remaining_estimate for tile in facts.useful_tiles),
                item.action_key)

    return min(discards, key=shape_key).action
