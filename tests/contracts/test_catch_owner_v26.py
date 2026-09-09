"""v26公开圈主事实契约：缺史快照可用，旧牌谱兼容，增量不能沿用旧豁免。"""

from dataclasses import replace

import pytest

from hangma_bot.hangma import HangmaRules
from hangma_bot.hangma.catch_play import analyze_catch_play
from hangma_bot.kernel.actions import Discard, Peng, Tile, WindowPhase
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import PublicDiscard, PublicEvent, RulePublicState
from hangma_bot.kernel.serialization import observation_from_json, observation_to_json
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
from hangma_bot.policy.interface import DecisionBudget
from tests.unit.policy.support import make_observation, make_request


def owner_observation(**changes):
    """缺少历史但v26快照直接声明座0为圈主；按公开手牌构造碰机会。"""
    fields = dict(
        snapshot_seq=10, consumed_seq=10, phase="response_peng", seat=0,
        turn_seat=3, responding_seats=(0,), drawn_tile=None,
        my_hand=tuple(Tile(c) for c in "5w 5w 1w 2w 3w 4b 5b 6b 7t 8t 9t 东 白".split()),
        last_discard=PublicDiscard(3, Tile("5w"), 10), history_complete=False,
        rule_state=RulePublicState(Tile("白"), False, 0, True, catch_play_owner_seat=0),
    )
    fields.update(changes)
    return make_observation(**fields)


def test_official_owner_with_no_history_can_claim_without_pending_rule_issue():
    observation = owner_observation()
    rules = HangmaRules(RuleConfig("v26-contract", 1, False))
    context = analyze_catch_play(observation)
    assert (context.owner_seat, context.source, context.issue) == (0, "official-snapshot", None)
    assert rules.validate(observation, Peng(Tile("5w"))).legal
    assert not any(i.area.startswith("catch_play") for i in rules.analyze(observation).issues)
    other = replace(observation, rule_state=replace(observation.rule_state, catch_play_owner_seat=1))
    assert not rules.validate(other, Peng(Tile("5w"))).legal


async def test_v2_consumes_the_same_official_owner_claim_candidates():
    observation = owner_observation()
    rules = HangmaRules(RuleConfig("v26-contract", 1, False))
    request = make_request(observation, rules.analyze(observation), phase=WindowPhase.RESPONSE_PENG)
    plan = await ComparableHeuristicPolicyV2(monotonic=lambda: 0).choose(request, DecisionBudget(1, 2, 3))
    assert "peng:5w" in {c.action_key for c in plan.candidates}
    assert all(rules.validate(observation, c.action).legal for c in plan.candidates)


@pytest.mark.parametrize("owner", [0, 1, 2, 3, None])
def test_owner_roundtrip_and_legacy_missing_field(owner):
    observation = owner_observation(rule_state=RulePublicState(Tile("白"), False, 0, True, owner))
    payload = observation_to_json(observation)
    assert payload["schema_version"] == 1
    assert observation_from_json(payload) == observation
    payload["rule_state"].pop("catch_play_owner_seat", None)
    old = observation_from_json(payload)
    assert old.rule_state.catch_play_owner_seat is None
    assert analyze_catch_play(old).owner_seat is None


@pytest.mark.parametrize("owner", [-1, 4, True, "0", .5])
def test_invalid_normalized_owner_is_rejected(owner):
    with pytest.raises(ValueError):
        RulePublicState(Tile("白"), False, 0, True, owner)


def test_contiguous_relay_transfers_rights_instead_of_reusing_snapshot_owner():
    events = (PublicEvent(11, "tile_drawn", 1),
              PublicEvent(12, "tile_discarded", 1, (Tile("白"),), catch_play=True),
              PublicEvent(13, "tile_drawn", 2))
    context = analyze_catch_play(owner_observation(consumed_seq=13, public_history=events))
    assert (context.owner_seat, context.started_seq) == (1, 12)
    assert context.restricts(0) and not context.restricts(1)


def test_contiguous_nonwhite_owner_discard_closes_circle_after_snapshot():
    events = (PublicEvent(11, "tile_discarded", 0, (Tile("5w"),), catch_play=False),)
    context = analyze_catch_play(owner_observation(consumed_seq=11, public_history=events))
    assert not context.active and context.owner_seat is None


@pytest.mark.parametrize("problem", ["gap", "unknown", "missing_tail"])
def test_unproven_suffix_does_not_extend_snapshot_owner_privilege(problem):
    events = {"gap": (PublicEvent(12, "tile_drawn", 1),),
              "unknown": (PublicEvent(11, "unknown_rule_action", 1),),
              "missing_tail": ()}[problem]
    observation = owner_observation(consumed_seq=12 if problem == "gap" else 11, public_history=events)
    context = analyze_catch_play(observation)
    assert context.owner_seat is None and context.issue
    assert context.restricts(0)


def test_old_history_cannot_override_a_newer_authoritative_owner():
    old = (PublicEvent(2, "tile_discarded", 3, (Tile("白"),), catch_play=True),)
    context = analyze_catch_play(owner_observation(public_history=old))
    assert context.owner_seat == 0 and context.source == "official-snapshot"


def test_no_circle_and_terminal_phase_do_not_grant_stale_owner_rights():
    for observation in (owner_observation(phase="settled"),
                        owner_observation(rule_state=RulePublicState(Tile("白"), False, 0, False, 0))):
        assert not analyze_catch_play(observation).active


def test_conflicting_increment_does_not_resurrect_pre_snapshot_owner():
    events = (PublicEvent(8, "tile_discarded", 2, (Tile("白"),), catch_play=True),
              PublicEvent(9, "pass", 1), PublicEvent(10, "tile_drawn", 0),
              PublicEvent(11, "tile_discarded", 0, (Tile("5w"),), catch_play=True),
              PublicEvent(12, "tile_drawn", 2, (Tile("6w"),)))
    observation = owner_observation(seat=2, turn_seat=2, phase="draw", consumed_seq=12,
                                    drawn_tile=Tile("6w"), public_history=events)
    context = analyze_catch_play(observation)
    assert context.owner_seat is None and context.issue
    assert context.restricts(0) and context.restricts(2)
    rules = HangmaRules(RuleConfig("v26-contract", 1, False))
    assert not rules.validate(observation, Discard(Tile("1w"))).legal


def test_new_continuous_white_suffix_can_recover_after_older_gap():
    events = (PublicEvent(12, "tile_discarded", 2, (Tile("白"),), catch_play=True),
              PublicEvent(13, "tile_drawn", 3))
    context = analyze_catch_play(owner_observation(consumed_seq=13, public_history=events))
    assert (context.owner_seat, context.started_seq, context.issue) == (2, 12, None)


@pytest.mark.parametrize("stale_owner", [None, 0])
def test_inactive_snapshot_then_contiguous_white_starts_circle_and_forces_other_discard(stale_owner):
    """无圈只代表旧快照水位；后续新白已开圈，不能继续允许他家手切。"""
    observation = owner_observation(
        seat=2, turn_seat=2, phase="draw", responding_seats=(), consumed_seq=12,
        drawn_tile=Tile("6w"),
        rule_state=RulePublicState(Tile("白"), False, 0, False, stale_owner),
        public_history=(PublicEvent(11, "tile_discarded", 1, (Tile("白"),), catch_play=True),
                        PublicEvent(12, "tile_drawn", 2, (Tile("6w"),))),
    )
    context = analyze_catch_play(observation)
    assert (context.active, context.owner_seat, context.started_seq) == (True, 1, 11)
    assert context.restricts(2) and not context.restricts(1)
    rules = HangmaRules(RuleConfig("v26-contract", 1, False))
    assert not rules.validate(observation, Discard(Tile("1w"))).legal
    emergency = rules.emergency_action(observation)
    assert emergency is not None and emergency.action == Discard(Tile("6w"))


def test_inactive_snapshot_with_contiguous_ordinary_events_stays_inactive():
    observation = owner_observation(
        consumed_seq=12, rule_state=RulePublicState(Tile("白"), False, 0, False, 0),
        public_history=(PublicEvent(11, "tile_discarded", 3, (Tile("5w"),), catch_play=False),
                        PublicEvent(12, "tile_drawn", 0, (Tile("6w"),))),
    )
    assert not analyze_catch_play(observation).active


@pytest.mark.parametrize("problem", ["gap", "unknown", "missing_tail"])
def test_inactive_snapshot_cannot_prove_no_circle_after_unobserved_changes(problem):
    events = {"gap": (PublicEvent(12, "tile_drawn", 2),),
              "unknown": (PublicEvent(11, "unknown_rule_action", 1),),
              "missing_tail": ()}[problem]
    observation = owner_observation(
        consumed_seq=12 if problem == "gap" else 11, public_history=events,
        rule_state=RulePublicState(Tile("白"), False, 0, False),
    )
    context = analyze_catch_play(observation)
    assert context.owner_seat is None and context.issue
    assert all(context.restricts(seat) for seat in range(4))


def test_new_white_after_gap_recovers_from_inactive_snapshot_without_reviving_old_owner():
    events = (PublicEvent(8, "tile_discarded", 0, (Tile("白"),), catch_play=True),
              PublicEvent(12, "tile_discarded", 1, (Tile("白"),), catch_play=True),
              PublicEvent(13, "tile_drawn", 2))
    context = analyze_catch_play(owner_observation(
        consumed_seq=13, public_history=events,
        rule_state=RulePublicState(Tile("白"), False, 0, False, 0),
    ))
    assert (context.owner_seat, context.started_seq, context.issue) == (1, 12, None)
    assert context.restricts(0)


def test_circle_opened_after_inactive_snapshot_can_close_at_its_owners_next_discard():
    events = [PublicEvent(11, "tile_discarded", 1, (Tile("白"),), catch_play=True)]
    for offset, seat in enumerate((2, 3, 0, 1)):
        events.append(PublicEvent(12 + 2 * offset, "tile_drawn", seat))
        events.append(PublicEvent(13 + 2 * offset, "tile_discarded", seat, (Tile("5w"),), catch_play=seat != 1))
    context = analyze_catch_play(owner_observation(
        consumed_seq=19, public_history=tuple(events),
        rule_state=RulePublicState(Tile("白"), False, 0, False),
    ))
    assert not context.active and context.owner_seat is None and context.issue is None


@pytest.mark.parametrize("phase", ["settled", "finished"])
def test_terminal_snapshot_is_inactive_even_with_newer_white_history(phase):
    observation = owner_observation(
        phase=phase, consumed_seq=11,
        rule_state=RulePublicState(Tile("白"), False, 0, False),
        public_history=(PublicEvent(11, "tile_discarded", 1, (Tile("白"),), catch_play=True),),
    )
    assert not analyze_catch_play(observation).active
