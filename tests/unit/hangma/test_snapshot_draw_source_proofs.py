"""可信零链及跨快照普通摸牌证明；来源冲突和本人待补牌保持未知。"""
from dataclasses import replace

import pytest

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.hangma.observation_rules import enrich_observation, infer_gang_draw, reconcile_observation
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import PlayerObservation, PublicEvent, PublicMeld, RulePublicState


def obs(name):
    """构造公开四家流转的前后态，不包含他家暗牌或未来牌墙。"""
    hand = tuple(Tile(code) for code in ("1w",)*3+("2w",)*3+("3w",)*3+("4w",)*3+("白",))
    waiting = PlayerObservation(
        game_id="snapshot-source-proofs", seat=0, round_no=1,
        snapshot_seq=101, consumed_seq=101, phase="draw", dealer_seat=0,
        turn_seat=1, responding_seats=(), my_hand=hand, drawn_tile=None,
        discards=((Tile("白"), Tile("白")), (), (), ()), melds=((), (), (), ()),
        hand_counts=(13, 13, 13, 13), last_discard=None, remaining_tile_count=60,
        scores=(0, 0, 0, 0), rule_state=RulePublicState(Tile("白"), True, 2, True, 0),
        public_history=(), history_complete=False, chain_piao=2, gang_draw=False,
    )
    if name == "waiting_after_confirmed_piao":
        return waiting
    if name == "ordinary_new_draw":
        # 三家各普通摸切一张，再到本人摸；墙减少四张，公开河据实追加。
        return replace(waiting, snapshot_seq=110, consumed_seq=110, turn_seat=0,
            my_hand=hand+(Tile("5w"),), drawn_tile=Tile("5w"),
            discards=(waiting.discards[0], (Tile("1b"),), (Tile("2b"),), (Tile("3b"),)),
            hand_counts=(14, 13, 13, 13), remaining_tile_count=56, chain_piao=None, gang_draw=None)
    gang = PublicMeld(0, "gang_an", (Tile("9t"),)*4, None)
    pending = replace(waiting, turn_seat=0,
        my_hand=tuple(Tile(code) for code in ("1w",)*3+("2w",)*3+("3w",)*3+("白",)),
        melds=((gang,), (), (), ()), hand_counts=(10, 13, 13, 13),
        discards=((Tile("白"),), (), (), ()), chain_piao=1)
    if name == "gang_pending_draw":
        return pending
    assert name == "gang_replacement_landed"
    return replace(pending, snapshot_seq=102, consumed_seq=102,
        my_hand=pending.my_hand+(Tile("东"),), drawn_tile=Tile("东"),
        hand_counts=(11, 13, 13, 13), remaining_tile_count=59, chain_piao=None, gang_draw=None)


def test_zero_chain_without_history_is_proof_not_default():
    raw = obs("ordinary_new_draw")
    raw = replace(raw, rule_state=replace(raw.rule_state, chain_count=0), chain_piao=None)
    assert raw.gang_draw is None and raw.public_history == () and not raw.history_complete
    enriched = enrich_observation(raw)
    assert (enriched.chain_piao, enriched.gang_draw) == (0, False)
    assert enriched.my_hand == raw.my_hand and enriched.rule_state == raw.rule_state
    assert enriched.public_history == raw.public_history and enriched.history_complete == raw.history_complete
    analysis = HangmaRules(RuleConfig("t134-facts", 1, False)).analyze(raw, route_limits=ValueAnalysisLimits(8192, 128))
    assert raw.gang_draw is None
    assert all(root.gap_kind is None for root in analysis.conditional_roots)
    assert "hu" in {candidate.action_key for candidate in analysis.legal_candidates}


@pytest.mark.parametrize("conflict", ("explicit", "event"))
def test_zero_chain_conflicts_stay_unknown_and_auditable(conflict):
    raw = obs("ordinary_new_draw")
    raw = replace(raw, rule_state=replace(raw.rule_state, chain_count=0), chain_piao=None)
    if conflict == "explicit":
        raw = replace(raw, gang_draw=True)
    else:
        event = PublicEvent(raw.consumed_seq, "tile_drawn", raw.seat, (raw.drawn_tile,), gang_replenish=True)
        raw = replace(raw, public_history=(event,))
    enriched = enrich_observation(raw)
    assert enriched.gang_draw is None
    assert "gang_draw_mismatch:source_or_chain" in enriched.observation_issues
    assert infer_gang_draw(raw) is None
    analysis = HangmaRules(RuleConfig("t134-facts", 1, False)).analyze(raw, route_limits=ValueAnalysisLimits(8192, 128))
    assert all(root.gap_kind is not None for root in analysis.conditional_roots)
    assert any("gang_draw_mismatch" in issue.reason for root in analysis.conditional_roots for issue in root.issues)


def test_positive_chain_without_source_remains_unknown():
    raw = obs("ordinary_new_draw")
    assert raw.rule_state.chain_count > 0
    assert enrich_observation(raw).gang_draw is None


@pytest.mark.parametrize("phase,turn", (("response_peng", 1), ("response_chi", 3), ("draw", 1)))
@pytest.mark.parametrize("known_piao", (True, False))
def test_proven_normal_new_draw_preserves_piao_and_current_history(phase, turn, known_piao):
    before, after = obs("waiting_after_confirmed_piao"), obs("ordinary_new_draw")
    before = replace(before, phase=phase, turn_seat=turn, chain_piao=2 if known_piao else None)
    result = reconcile_observation(before, after)
    assert (result.chain_piao, result.gang_draw) == (2 if known_piao else None, False)
    assert result.public_history == after.public_history == ()
    assert result.history_complete == after.history_complete is False
    assert result.my_hand == after.my_hand and result.rule_state == after.rule_state


def test_own_gang_pending_draw_is_counterexample_not_normal_draw():
    before, after = obs("gang_pending_draw"), obs("gang_replacement_landed")
    assert before.phase == "draw" and before.turn_seat == before.seat and before.drawn_tile is None
    result = reconcile_observation(before, after)
    assert (result.chain_piao, result.gang_draw) == (1, None)


@pytest.mark.parametrize("case", ("unknown_phase", "before_issue", "after_issue", "river", "meld", "chain", "hand", "watermark"))
def test_new_draw_requires_every_fact(case):
    before, after = obs("waiting_after_confirmed_piao"), obs("ordinary_new_draw")
    if case == "unknown_phase":
        before = replace(before, phase="unknown")
    elif case == "before_issue":
        before = replace(before, observation_issues=("gap",))
    elif case == "after_issue":
        after = replace(after, observation_issues=("gap",))
    elif case == "river":
        after = replace(after, discards=(after.discards[0]+(Tile("东"),),)+after.discards[1:])
    elif case == "meld":
        gang = PublicMeld(0, "gang_an", (Tile("9t"),)*4, None)
        after = replace(after, melds=((gang,), (), (), ()))
    elif case == "chain":
        after = replace(after, rule_state=replace(after.rule_state, chain_count=3))
    elif case == "hand":
        after = replace(after, my_hand=after.my_hand[:-1]+(Tile("东"),))
    else:
        after = replace(after, snapshot_seq=before.snapshot_seq, consumed_seq=before.consumed_seq)
    assert reconcile_observation(before, after).gang_draw is None


def test_new_draw_direct_source_conflict_stays_unknown():
    before, after = obs("waiting_after_confirmed_piao"), obs("ordinary_new_draw")
    result = reconcile_observation(before, replace(after, gang_draw=True))
    assert result.gang_draw is None
    assert "gang_draw_mismatch:confirmed_transition" in result.observation_issues


@pytest.mark.parametrize("case", ("no_current_draw", "bad_concealed_shape", "observation_issue"))
def test_zero_chain_proof_requires_trusted_current_draw(case):
    raw = obs("ordinary_new_draw")
    raw = replace(raw, rule_state=replace(raw.rule_state, chain_count=0), chain_piao=None)
    if case == "no_current_draw":
        raw = replace(raw, drawn_tile=None)
    elif case == "bad_concealed_shape":
        raw = replace(raw, my_hand=raw.my_hand[:-2])
    else:
        raw = replace(raw, observation_issues=("god_mismatch:chain_count",))
    assert infer_gang_draw(raw) is None
    assert enrich_observation(raw).gang_draw is None
