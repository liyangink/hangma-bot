"""动作后爆头事实契约：规则层生产，评分视图只做逐动作投影。"""

from __future__ import annotations

import pytest

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import CandidateFactKind, CandidateFacts, ValueAnalysisLimits
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import PlayerObservation, PublicDiscard, RulePublicState
from hangma_bot.policy.action_value_policy import build_scoring_view

from .support import make_request


RULES = HangmaRules(RuleConfig("baotou-after-contract", 1, False))
FOUR_MELDS = "1w 2w 3w 4w 5w 6w 7w 8w 9w 1b 2b 3b"


def _tiles(codes: str):
    return tuple(Tile(code) for code in codes.split())


def _observation(
    hand: str,
    draw: str | None = None,
    *,
    baotou: bool,
    response: str | None = None,
) -> PlayerObservation:
    """构造本人依法可见的摸牌或碰响应窗口；手牌不含单列摸牌。"""

    holding = _tiles(hand)
    rivers = [(), (), (), ()]
    phase = "draw"
    turn = 0
    responding = ()
    last_discard = None
    if response is not None:
        phase = "response_peng"
        turn = 3
        responding = (0,)
        rivers[turn] = (Tile(response),)
        last_discard = PublicDiscard(turn, Tile(response), 10)
    return PlayerObservation(
        game_id="baotou-after",
        seat=0,
        round_no=1,
        snapshot_seq=10,
        consumed_seq=10,
        phase=phase,
        dealer_seat=0,
        turn_seat=turn,
        responding_seats=responding,
        my_hand=holding,
        drawn_tile=Tile(draw) if draw else None,
        discards=tuple(rivers),
        melds=((), (), (), ()),
        hand_counts=tuple(len(holding) + bool(draw) if seat == 0 else 13 for seat in range(4)),
        last_discard=last_discard,
        remaining_tile_count=60,
        scores=(0, 0, 0, 0),
        rule_state=RulePublicState(Tile("白"), baotou, 0, False),
        public_history=(),
        chain_piao=0,
    )


def _facts_and_view(observation: PlayerObservation):
    analysis = RULES.analyze(observation, value_limits=ValueAnalysisLimits())
    view = build_scoring_view(make_request(observation, analysis))
    facts = {
        candidate.action_key: candidate.facts.baotou_after
        for candidate in analysis.legal_candidates
        if candidate.facts is not None
    }
    projected = {action.action_key: action.baotou_after for action in view.actions}
    mapped = {
        action["action_key"]: action["baotou_after"]
        for action in view.candidate_view()["actions"]
    }
    assert projected == facts
    assert mapped == facts
    return facts


def test_discard_recomputes_baotou_and_hu_is_terminal_unknown():
    """弃牌按弃后暗牌重算；胡是终局，不能把动作前状态冒充动作后值。"""

    facts = _facts_and_view(
        _observation(FOUR_MELDS + " 白", "白", baotou=True)
    )
    assert facts["discard:白"] is True
    assert facts["hu"] is None


def test_ordinary_discards_can_keep_or_leave_baotou():
    """同一窗口的不同弃牌可产生不同爆头后态。"""

    facts = _facts_and_view(
        _observation(FOUR_MELDS + " 白", "5t", baotou=True)
    )
    assert facts["discard:白"] is False
    assert facts["discard:5t"] is True


def test_peng_and_pass_inherit_authoritative_before_state():
    """真实响应窗口先证明动作存在，再核验碰与过都继承动作前爆头。"""

    facts = _facts_and_view(
        _observation(
            "5w 5w 1t 1t 2t 2t 3t 3t 4t 5t 6t 7t 8t",
            baotou=True,
            response="5w",
        )
    )
    assert "peng:5w" in facts and "pass" in facts
    assert facts["peng:5w"] is True
    assert facts["pass"] is True


def test_concealed_gang_inherits_authoritative_before_state():
    """真实暗杠候选继承爆头；补牌后的下一状态由摸牌规则另行更新。"""

    facts = _facts_and_view(
        _observation(
            "9w 9w 9w 9w 1t 2t 3t 4t 5t 6t 7t 8t 9t",
            "白",
            baotou=True,
        )
    )
    assert "gang:concealed:9w" in facts
    assert facts["gang:concealed:9w"] is True


def test_without_value_analysis_fact_is_unknown_not_recomputed_in_policy():
    """规则层未生产进展载荷时，policy 必须透传未知，不能自行重算。"""

    observation = _observation(FOUR_MELDS + " 白", "5t", baotou=True)
    analysis = RULES.analyze(observation)
    view = build_scoring_view(make_request(observation, analysis))
    assert all(action.baotou_after is None for action in view.actions)


@pytest.mark.parametrize("invalid", [0, 1, "true", object()])
def test_candidate_facts_rejects_non_boolean_baotou_after(invalid):
    with pytest.raises(ValueError, match="baotou_after"):
        CandidateFacts(
            fact_kind=CandidateFactKind.HAND_PROGRESS,
            shanten_after=0,
            baotou_after=invalid,
        )
