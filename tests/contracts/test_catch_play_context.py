"""抓打圈身份与生存期的公开契约；合成窗口不代表官方已开放该响应权。"""

from dataclasses import FrozenInstanceError

import pytest

from hangma_bot.hangma import HangmaRules
from hangma_bot.hangma.catch_play import analyze_catch_play
from hangma_bot.kernel.actions import Peng, Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import PublicDiscard, PublicEvent, RulePublicState
from tests.unit.policy.support import make_observation


def event(seq, kind, seat, tile=None, **fields):
    """构造已可见事件；摸牌牌值留空，不向观察加入他家暗牌。"""
    return PublicEvent(
        seq=seq,
        kind=kind,
        seat=seat,
        tiles=() if tile is None else (Tile(tile),),
        **fields,
    )


def observation_with(history, *, active=True, **overrides):
    """以快照旗标为权威，历史完整性和消费水位可单独构造边界。"""
    fields = dict(
        snapshot_seq=10,
        consumed_seq=history[-1].seq,
        history_complete=False,
        public_history=tuple(history),
        rule_state=RulePublicState(Tile("白"), False, 0, active),
    )
    fields.update(overrides)
    return make_observation(**fields)


A_WHITE_B_WHITE = (
    event(10, "tile_discarded", 0, "白", catch_play=True),
    event(11, "tile_drawn", 1),
    event(12, "tile_discarded", 1, "白", catch_play=True),
)
THROUGH_A_NEXT_DISCARD = A_WHITE_B_WHITE + (
    event(13, "tile_drawn", 2),
    event(14, "tile_discarded", 2, "2b", catch_play=True),
    event(15, "tile_drawn", 3),
    event(16, "tile_discarded", 3, "3b", catch_play=True),
    event(17, "tile_drawn", 0),
    event(18, "tile_discarded", 0, "4b", catch_play=True),
)


def test_relay_changes_owner_and_start_to_the_latest_white_and_context_is_frozen():
    context = analyze_catch_play(observation_with(A_WHITE_B_WHITE))

    assert context.active
    assert context.owner_seat == 1
    assert context.started_seq == 12
    assert context.issue is None
    assert [context.restricts(seat) for seat in range(4)] == [True, False, True, True]
    with pytest.raises(FrozenInstanceError):
        context.owner_seat = 0


def test_former_owner_normal_discard_does_not_end_the_relay_circle():
    context = analyze_catch_play(observation_with(THROUGH_A_NEXT_DISCARD))

    assert (context.active, context.owner_seat, context.started_seq) == (True, 1, 12)
    assert context.restricts(0)
    assert not context.restricts(1)


def test_latest_owner_normal_discard_with_authoritative_false_clears_context():
    history = THROUGH_A_NEXT_DISCARD + (
        event(19, "tile_drawn", 1),
        event(20, "tile_discarded", 1, "5b", catch_play=False),
    )
    context = analyze_catch_play(observation_with(history, active=False))

    assert (context.active, context.owner_seat, context.started_seq, context.issue) == (False, None, None, None)
    assert not any(context.restricts(seat) for seat in range(4))


@pytest.mark.parametrize("phase", ["deal", "settled", "finished", "ended", "match_end"])
def test_nonplaying_phase_does_not_carry_active_circle_rights(phase):
    """终态 god 可能保留上一动作值；有效动作上下文归零且不改原报文事实。"""
    observation = observation_with(A_WHITE_B_WHITE, phase=phase)
    context = analyze_catch_play(observation)

    assert not context.active and context.owner_seat is None and context.started_seq is None
    assert observation.rule_state.catch_play is True


def test_same_owner_second_white_renews_the_start_seq():
    history = THROUGH_A_NEXT_DISCARD + (
        event(19, "tile_drawn", 1),
        event(20, "tile_discarded", 1, "白", catch_play=True),
    )
    context = analyze_catch_play(observation_with(history))

    assert (context.active, context.owner_seat, context.started_seq) == (True, 1, 20)
    assert context.issue is None


def test_other_and_owner_draws_concealed_gangs_and_replacements_do_not_end_circle():
    history = (
        event(10, "tile_discarded", 0, "白", catch_play=True),
        event(11, "tile_drawn", 1),
        event(12, "gang", 1, "北", detail_kind="an"),
        event(13, "tile_drawn", 1, gang_replenish=True),
        event(14, "tile_discarded", 1, "2b", catch_play=True),
        event(15, "tile_drawn", 2),
        event(16, "tile_discarded", 2, "3b", catch_play=True),
        event(17, "tile_drawn", 3),
        event(18, "tile_discarded", 3, "4b", catch_play=True),
        event(19, "tile_drawn", 0),
        event(20, "gang", 0, "东", detail_kind="an"),
        event(21, "tile_drawn", 0, gang_replenish=True),
    )
    context = analyze_catch_play(observation_with(history))

    assert (context.active, context.owner_seat, context.started_seq) == (True, 0, 10)
    assert not context.restricts(0)
    assert context.issue is None


@pytest.mark.parametrize("case", ["gap", "stale_tail", "unknown_event", "owner_discard_conflict", "no_white"])
def test_unproven_active_owner_stays_unknown_and_restricts_every_seat(case):
    white = event(10, "tile_discarded", 0, "白", catch_play=True)
    overrides = {}
    if case == "gap":
        history = (white, event(12, "tile_drawn", 1))
    elif case == "stale_tail":
        history = (white, event(11, "tile_drawn", 1))
        overrides["consumed_seq"] = 12
    elif case == "unknown_event":
        history = (white, event(11, "unrecognized_rule_transition", None), event(12, "tile_drawn", 1))
    elif case == "owner_discard_conflict":
        history = (
            white,
            event(11, "tile_drawn", 1),
            event(12, "tile_discarded", 1, "2b", catch_play=True),
            event(13, "tile_drawn", 2),
            event(14, "tile_discarded", 2, "3b", catch_play=True),
            event(15, "tile_drawn", 3),
            event(16, "tile_discarded", 3, "4b", catch_play=True),
            event(17, "tile_drawn", 0),
            event(18, "tile_discarded", 0, "5b", catch_play=True),
        )
    else:
        history = (event(10, "tile_drawn", 1),)
    context = analyze_catch_play(observation_with(history, **overrides))

    assert context.active
    assert context.owner_seat is None
    assert context.started_seq is None
    assert context.issue
    assert all(context.restricts(seat) for seat in range(4))


def test_missing_consumed_seq_uses_snapshot_seq_as_current_watermark():
    context = analyze_catch_play(observation_with(A_WHITE_B_WHITE, snapshot_seq=12, consumed_seq=None))

    assert (context.owner_seat, context.started_seq, context.issue) == (1, 12, None)


def test_gap_before_latest_white_does_not_invalidate_its_continuous_suffix():
    history = (
        event(2, "tile_discarded", 2, "1b", catch_play=False),
        event(10, "tile_discarded", 0, "白", catch_play=True),
        event(11, "tile_drawn", 1),
    )
    context = analyze_catch_play(observation_with(history))

    assert (context.owner_seat, context.started_seq, context.issue) == (0, 10, None)


@pytest.mark.parametrize("seat,members,expected", [
    (2, (0, 1, 2), {"pass", "peng:5w"}),
    (0, (0, 1, 2), {"pass"}),
    (2, (0, 1), set()),
])
def test_public_rules_honor_known_owner_only_inside_the_supplied_response_window(seat, members, expected):
    """合成权威响应成员只验证本地机制，不是官方会向圈主开窗的证据。"""
    history = (
        event(10, "tile_discarded", 2, "白", catch_play=True),
        event(11, "tile_drawn", 3),
        event(12, "tile_discarded", 3, "5w", catch_play=True),
    )
    observation = observation_with(
        history,
        seat=seat,
        phase="response_peng",
        turn_seat=3,
        responding_seats=members,
        my_hand=tuple(Tile(code) for code in "5w 5w 1w 2w 3w 4b 5b 6b 7t 8t 9t 东 白".split()),
        discards=((), (), (Tile("白"),), (Tile("5w"),)),
        last_discard=PublicDiscard(3, Tile("5w"), 12),
    )
    rules = HangmaRules(RuleConfig("catch-play-context-contract", 1, False))

    analysis = rules.analyze(observation)

    assert {candidate.action_key for candidate in analysis.legal_candidates} == expected
    assert rules.validate(observation, Peng(Tile("5w"))).legal is ("peng:5w" in expected)
