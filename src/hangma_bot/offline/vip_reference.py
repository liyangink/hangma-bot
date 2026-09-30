"""VIP 离线配对实验的冻结基础续打者；不参与线上策略闭环。"""

from __future__ import annotations

from functools import lru_cache

from hangma_bot.hangma.action_families import WALL_RESERVE_TILES
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
    """只消费依法可见观察与同源合法牌效，不读取完整模拟世界。

    ``shape_white_hold`` 仅是离线标签敏感性参考者：双白、尚有正常
    摸牌空间且保留非白听牌/一向听出口时，暂缓低于四番的当前胡。
    它没有校准等待风险，不得用作线上策略或强度结论。
    """

    if mode == "r18_frozen":
        return _choose_frozen_r18(rules, decision)
    observation = decision.observation
    candidates = rules.analyze(observation).legal_candidates
    if observation.phase.startswith("response_"):
        return Pass()
    win_candidate = next((item for item in candidates if isinstance(item.action, Hu)), None)
    if (mode == "shape_white_hold" and win_candidate is not None
            and _white_count(observation) >= 2
            and observation.remaining_tile_count is not None
            and observation.remaining_tile_count > WALL_RESERVE_TILES):
        candidates = rules.analyze(
            observation, value_limits=ValueAnalysisLimits(max_expansions=8192),
        ).legal_candidates
        win_candidate = next((item for item in candidates
                              if isinstance(item.action, Hu)), None)
    discards = [item for item in candidates if isinstance(item.action, Discard)]
    if win_candidate is not None:
        if mode != "shape_white_hold" or not _defer_low_fan_hu(
            observation, win_candidate, discards,
        ):
            return win_candidate.action
    if mode == "first_discard":
        return discards[0].action
    if mode not in ("shape", "shape_white_hold"):
        raise ValueError("未知参考续打者")

    if mode == "shape_white_hold":
        # 双白机会层只改变离线参考续打：能弃别张时不主动弃白。
        nonwhite = [item for item in discards if item.action.tile.code != "白"]
        if nonwhite and _white_count(observation) >= 2:
            discards = nonwhite

    def shape_key(item):
        facts = item.facts
        if facts is None or facts.shanten_after is None:
            raise ValueError("基础牌效参考者缺规则模块动作后牌效")
        return (facts.shanten_after,
                -sum(tile.remaining_estimate for tile in facts.useful_tiles),
                item.action_key)

    return min(discards, key=shape_key).action


def _white_count(observation) -> int:
    """只数本座依法可见的实持白板；公开白板和未来摸牌不计。"""

    return sum(tile.code == "白" for tile in observation.my_hand) + (
        observation.drawn_tile is not None and observation.drawn_tile.code == "白"
    )


def _defer_low_fan_hu(observation, win_candidate, discards) -> bool:
    """离线正控：只在有规则同源保留出口时延后低番胡。"""

    if (_white_count(observation) < 2
            or observation.remaining_tile_count is None
            or observation.remaining_tile_count <= WALL_RESERVE_TILES):
        return False
    settlement = (win_candidate.value_facts.immediate_settlement
                  if win_candidate.value_facts is not None else None)
    if settlement is None:
        facts = win_candidate.value_facts
        raise ValueError(
            "双白参考续打者的合法当前胡缺同源结算: " +
            ("无价值载荷" if facts is None else
             f"coverage={facts.coverage.value} issues={facts.issues}")
        )
    if settlement.fan >= 4:
        return False
    return any(
        item.action.tile.code != "白" and item.facts is not None
        and item.facts.shanten_after is not None
        and 0 <= item.facts.shanten_after <= 1
        for item in discards
    )
