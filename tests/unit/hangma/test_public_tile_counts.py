"""官方牌河保留被鸣牌历史；通过公开规则入口检查同一物理牌只计一次。"""

from dataclasses import replace

import pytest

from hangma_bot.hangma.interface import CandidateFactKind, RuleCompleteness
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.observation import PublicEvent, PublicMeld
from tests.unit.hangma.test_candidate_facts import make_observation, _rules
from tests.unit.hangma.test_official_action_chain_trace import trace

from tests.simulation.test_catch_owner_v26 import _after_piao_and_claim


@pytest.mark.parametrize("claim,code,remaining", [("peng", "东", 1), ("chi", "9t", 3)])
def test_called_tile_in_river_and_meld_is_counted_once(claim, code, remaining):
    """136张守恒的公开模拟前缀，鸣牌后的任意听不应少算供牌那一张。"""
    rules, engine, world = _after_piao_and_claim(claim)
    observation = engine.frame(world).decisions[0].observation
    analysis = rules.analyze(observation)
    candidate = next(c for c in analysis.legal_candidates if c.action_key == "discard:白")
    useful = {item.code: item.remaining_estimate for item in candidate.facts.useful_tiles}
    assert useful[code] == remaining


def _facts(analysis, key="discard:白"):
    return next(c.facts for c in analysis.legal_candidates if c.action_key == key)


def test_saved_official_chi_and_concealed_gang_keep_nine_bamboo_available():
    """v18 原始连续快照：被吃9条仍在河中，吃/暗杠后均真实未见3张。"""
    views, _ = trace()
    for seq in (2267, 2269):
        facts = _facts(_rules().analyze(views[seq]))
        assert facts.fact_kind is CandidateFactKind.HAND_PROGRESS
        assert next(u.remaining_estimate for u in facts.useful_tiles if u.code == "9t") == 3


@pytest.mark.parametrize("claim,code,remaining", [("peng", "东", 1), ("chi", "9t", 3)])
def test_snapshot_without_history_uses_meld_or_unique_river_evidence(claim, code, remaining):
    rules, engine, world = _after_piao_and_claim(claim)
    observation = replace(engine.frame(world).decisions[0].observation, public_history=(), history_complete=False)
    facts = _facts(rules.analyze(observation))
    assert next(u.remaining_estimate for u in facts.useful_tiles if u.code == code) == remaining


def test_current_river_invalidates_conflicting_historical_chi_proof():
    """合成矛盾历史不能覆盖当前完整牌河的唯一供牌证据。"""
    rules, engine, world = _after_piao_and_claim("chi")
    obs = engine.frame(world).decisions[0].observation
    history = tuple(replace(e, tiles=(Tile("7t"),))
                    if e.kind == "tile_discarded" and e.seat == 3 and e.tiles == (Tile("9t"),)
                    else e for e in obs.public_history)
    facts = _facts(rules.analyze(replace(obs, public_history=history)))
    assert facts.fact_kind is CandidateFactKind.HAND_PROGRESS
    assert next(u.remaining_estimate for u in facts.useful_tiles if u.code == "9t") == 3


def test_identical_chi_cannot_reuse_one_recorded_discard_twice():
    """缺史同形两次吃不能从只有一张的牌河中扣出两张供牌。"""
    rules, engine, world = _after_piao_and_claim("peng")
    obs = engine.frame(world).decisions[0].observation
    shape = tuple(Tile(c) for c in ("7t", "8t", "9t"))
    meld = PublicMeld(3, "chi", shape, 2)
    obs = replace(obs, melds=(obs.melds[0], (), (), (meld, meld)),
                  discards=(obs.discards[0], obs.discards[1], (Tile("7t"),), ()), public_history=())
    analysis = rules.analyze(obs)
    assert _facts(analysis).fact_kind is CandidateFactKind.ANALYSIS_FAILED
    assert analysis.completeness is RuleCompleteness.DEGRADED
    assert analysis.emergency_candidate is not None


def _ambiguous_chi():
    rules, engine, world = _after_piao_and_claim("chi")
    obs = engine.frame(world).decisions[0].observation
    rivers = list(obs.discards)
    rivers[3] += (Tile("7t"),)  # 上家还曾丢过7条；缺史时不能区分本次吃7条还是9条。
    return rules, replace(obs, discards=tuple(rivers))


@pytest.mark.parametrize("history_problem", ["missing", "gap", "draw_between", "conflict", "future", "old_round"])
def test_unproven_chi_does_not_invent_a_remaining_count(history_problem):
    rules, obs = _ambiguous_chi()
    discard = PublicEvent(5, "tile_discarded", 3, (Tile("9t"),))
    chi = PublicEvent(6, "chi", 0, tuple(Tile(c) for c in ("7t", "8t", "9t")))
    histories = {
        "missing": (),
        "gap": (discard, replace(chi, seq=7)),
        "draw_between": (discard, PublicEvent(6, "tile_drawn", 1), replace(chi, seq=7)),
        "conflict": (discard, replace(discard, tiles=(Tile("7t"),)), chi),
        "future": (replace(discard, seq=20), replace(chi, seq=21)),
        "old_round": (discard, chi, PublicEvent(7, "round_ended", None), PublicEvent(8, "round_started", None)),
    }
    changed = replace(obs, public_history=histories[history_problem], snapshot_seq=10, consumed_seq=10,
                      rule_state=replace(obs.rule_state, catch_play=False, catch_play_owner_seat=None,
                                         chain_count=0), chain_piao=0)
    analysis = rules.analyze(changed)
    assert _facts(analysis).fact_kind is CandidateFactKind.ANALYSIS_FAILED
    assert _facts(analysis).shanten_after is None and not _facts(analysis).useful_tiles
    assert analysis.completeness is RuleCompleteness.DEGRADED
    assert {c.action_key for c in analysis.legal_candidates} == {c.action_key for c in rules.analyze(obs).legal_candidates}
    assert analysis.emergency_candidate is not None


def test_only_candidates_using_uncertain_tiles_degrade_and_hu_stays_available():
    chi = PublicMeld(2, "chi", tuple(Tile(c) for c in ("1w", "2w", "3w")), 1)
    obs = make_observation(drawn_tile=Tile("4t"), melds=((), (), (chi,), ()),
                           discards=((), (Tile("1w"), Tile("2w")), (), ()))
    analysis = _rules().analyze(obs)
    assert _facts(analysis, "discard:1w").fact_kind is CandidateFactKind.ANALYSIS_FAILED
    assert _facts(analysis, "discard:4t").fact_kind is CandidateFactKind.HAND_PROGRESS
    assert _facts(analysis, "hu").fact_kind is CandidateFactKind.WIN


@pytest.mark.parametrize("repeat", [False, True])
def test_identical_chi_shapes_keep_both_distinct_called_tiles(repeat):
    rules, engine, world = _after_piao_and_claim("peng")
    obs = engine.frame(world).decisions[0].observation
    shape = tuple(Tile(c) for c in ("7t", "8t", "9t"))
    meld = PublicMeld(3, "chi", shape, 2)
    history = (PublicEvent(1, "tile_discarded", 2, (Tile("7t"),)), PublicEvent(2, "chi", 3, shape),
               PublicEvent(10, "tile_discarded", 2, (Tile("9t"),)), PublicEvent(11, "chi", 3, shape))
    if repeat:
        history = history[:2] + (history[1],) + history[2:]  # 同一事件重复通知不重复扣牌。
    obs = replace(obs, melds=(obs.melds[0], (), (), (meld, meld)),
                  discards=(obs.discards[0], obs.discards[1], (Tile("7t"), Tile("9t")), ()),
                  public_history=history, snapshot_seq=11, consumed_seq=11)
    facts = _facts(rules.analyze(obs))
    counts = {u.code: u.remaining_estimate for u in facts.useful_tiles}
    assert (counts["7t"], counts["8t"], counts["9t"]) == (2, 2, 2)


@pytest.mark.parametrize("kind", ["gang", "gang_an", "gang_ming", "gang_bu"])
def test_four_exposed_copies_leave_zero_regardless_of_gang_history(kind):
    rules, engine, world = _after_piao_and_claim("peng")
    obs = engine.frame(world).decisions[0].observation
    quad = PublicMeld(0, kind, (Tile("东"),) * 4, None if kind in ("gang", "gang_an") else 1)
    rivers = obs.discards if kind != "gang_an" else (obs.discards[0], (), (), ())
    obs = replace(obs, melds=((quad,), (), (), ()), discards=rivers, public_history=())
    facts = _facts(rules.analyze(obs))
    assert next(u.remaining_estimate for u in facts.useful_tiles if u.code == "东") == 0
