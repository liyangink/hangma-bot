"""实测公开字段进入规则的回归；依据 2026-09-06 v17 测试房归档。

实测：seq2012 摸牌 data.gang_replenish=true；他家摸牌保留事件但 tile 为空。
catch_play=True 的四座位作用范围未实测，不在此构造官方语义。
"""
from dataclasses import replace

import pytest

from hangma_bot.hangma.observation_rules import (
    compare_observation_transition,
    enrich_observation,
)
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.observation import PlayerObservation, PublicEvent, RulePublicState


def observation(**changes):
    values = dict(
        game_id="live-facts", seat=0, round_no=7, snapshot_seq=2011,
        consumed_seq=2011, phase="draw", dealer_seat=3, turn_seat=0,
        responding_seats=(),
        my_hand=tuple(Tile(x) for x in ("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "2b", "3b", "东")),
        drawn_tile=Tile("东"), discards=((), (), (), ()), melds=((), (), (), ()),
        hand_counts=(14, 13, 13, 13), last_discard=None, remaining_tile_count=40,
        scores=(0, 0, 0, 0), rule_state=RulePublicState(Tile("白"), False, 0, False),
        public_history=(),
    )
    values.update(changes)
    return PlayerObservation(**values)


@pytest.mark.parametrize("flag", [True, False])
def test_current_draw_explicit_source_does_not_require_previous_gang_event(flag):
    current = PublicEvent(2012, "tile_drawn", 0, (Tile("东"),), gang_replenish=flag)
    obs = observation(consumed_seq=2012, public_history=(current,))
    assert obs.history_complete is False
    assert enrich_observation(obs).gang_draw is flag


def test_old_or_other_seat_source_is_not_applied_to_current_draw():
    own = PublicEvent(2012, "tile_drawn", 0, (Tile("东"),), gang_replenish=True)
    assert enrich_observation(observation(consumed_seq=2013, public_history=(own,))).gang_draw is None
    other = replace(own, seat=1, tiles=())
    assert enrich_observation(observation(consumed_seq=2012, public_history=(other,))).gang_draw is None
    assert enrich_observation(observation(consumed_seq=2012, public_history=(replace(own, tiles=(Tile("北"),)),))).gang_draw is None


def test_masked_other_draw_retains_facts_and_confirms_own_chain_unchanged():
    other = PublicEvent(2012, "tile_drawn", 1)
    before = observation(phase="response_chi", turn_seat=1, drawn_tile=None)
    after = replace(before, phase="draw", consumed_seq=2012, public_history=(other,))
    result = compare_observation_transition(before, (other,), after)
    assert not any(x.startswith("god_mismatch:") for x in result)
    assert not any(x.startswith("not_checked:chain_count:") for x in result)
    assert enrich_observation(after).public_history == (other,)
    assert enrich_observation(after).rule_state == before.rule_state
    wrong = replace(after, rule_state=replace(after.rule_state, chain_count=1))
    assert any(x.startswith("god_mismatch:chain_count:") for x in compare_observation_transition(before, (other,), wrong))


def test_confirmed_draw_source_conflict_is_reported_without_overwriting_snapshot():
    draw = PublicEvent(2012, "tile_drawn", 0, (Tile("东"),), gang_replenish=True)
    before = observation(drawn_tile=None)
    after = replace(before, drawn_tile=Tile("东"), consumed_seq=2012, gang_draw=False, public_history=(draw,))
    result = compare_observation_transition(before, (draw,), after)
    assert any(x.startswith("god_mismatch:gang_draw:") for x in result)
    assert after.gang_draw is False
    good = replace(after, gang_draw=True)
    assert not any(x.startswith("god_mismatch:gang_draw:") for x in compare_observation_transition(before, (draw,), good))


@pytest.mark.parametrize("catch_flag", [True, False, None])
def test_other_discard_catch_flag_is_preserved_without_assigning_own_scope(catch_flag):
    discard = PublicEvent(2012, "tile_discarded", 1, (Tile("白"),), catch_play=catch_flag)
    before = observation(phase="draw", turn_seat=1, drawn_tile=None)
    after = replace(before, phase="response_peng", consumed_seq=2012, public_history=(discard,))
    enriched = enrich_observation(after)
    assert enriched.public_history[0].catch_play is catch_flag
    assert enriched.rule_state.catch_play is False
    assert any(x.startswith("not_checked:catch_play:") for x in compare_observation_transition(before, (discard,), enriched))
