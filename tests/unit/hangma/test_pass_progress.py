"""通过唯一规则公开接口验证过牌的等待口径、公开计数和降级边界。"""

from dataclasses import replace

import pytest

from hangma_bot.hangma.interface import CandidateFactKind, RuleCompleteness
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.observation import PublicDiscard, PublicMeld
from tests.unit.hangma.test_candidate_facts import make_observation, _rules


def response(**kw):
    """构造已听 4t/白的等待手牌；触发 4t 已进入座位 2 的公开牌河。"""
    fields = dict(phase="response_peng", responding_seats=(0,), turn_seat=2,
                  last_discard=PublicDiscard(2, Tile("4t"), 9),
                  discards=((), (), (Tile("4t"),), ()))
    fields.update(kw)
    return make_observation(**fields)


@pytest.mark.parametrize("phase", ["response_peng", "response_chi"])
def test_pass_waits_without_claiming_or_discarding(phase):
    obs = response(phase=phase, turn_seat=3, last_discard=PublicDiscard(3, Tile("4t"), 9),
                   discards=((), (), (), (Tile("4t"),)))
    rules = _rules()
    analysis = rules.analyze(obs)
    facts = next(c.facts for c in analysis.legal_candidates if c.action_key == "pass")
    assert facts.fact_kind is CandidateFactKind.HAND_PROGRESS
    assert facts.shanten_after == 0
    useful = {u.code: u.remaining_estimate for u in facts.useful_tiles}
    assert useful["4t"] == 2  # 手牌一张 + 牌河一张；不重复扣 last_discard。
    assert useful["白"] == 4
    assert facts.best_followup_discard is None and not facts.replacement_draw_unknown
    assert rules.emergency_action(obs).facts is None
    assert rules.validate(obs, analysis.emergency_candidate.action).legal


@pytest.mark.parametrize("meld_kind, tiles", [("chi", ("1b", "2b", "3b")), ("gang_concealed", ("1b",)*4)])
def test_open_or_concealed_meld_counts_as_one_waiting_block(meld_kind, tiles):
    meld = PublicMeld(0, meld_kind, tuple(Tile(c) for c in tiles), None)
    obs = response(hand_codes=("1w","2w","3w","4w","5w","6w","7w","8w","9w","4t"),
                   melds=((meld,), (), (), ()))
    facts = next(c.facts for c in _rules().analyze(obs).legal_candidates if c.action_key == "pass")
    assert facts.fact_kind is CandidateFactKind.HAND_PROGRESS
    assert facts.shanten_after == 0
    assert {u.code: u.remaining_estimate for u in facts.useful_tiles}["4t"] == 2


def test_exhausted_public_tiles_are_not_counted_as_available():
    obs = response(discards=((Tile("4t"),), (Tile("4t"),), (Tile("4t"),), ()))
    facts = next(c.facts for c in _rules().analyze(obs).legal_candidates if c.action_key == "pass")
    assert {u.code: u.remaining_estimate for u in facts.useful_tiles}["4t"] == 0


@pytest.mark.parametrize("change", [{"drawn_tile": Tile("4t")}, {"my_hand": (Tile("4t"),)}])
def test_bad_waiting_shape_keeps_legal_emergency_pass(change):
    obs = replace(response(), **change)
    rules = _rules()
    analysis = rules.analyze(obs)
    facts = next(c.facts for c in analysis.legal_candidates if c.action_key == "pass")
    assert facts.fact_kind is CandidateFactKind.ANALYSIS_FAILED
    assert facts.shanten_after is None and facts.useful_tiles == ()
    assert analysis.completeness is RuleCompleteness.DEGRADED
    assert any(i.area == "candidate_facts" for i in analysis.issues)
    assert rules.emergency_action(obs).action_key == "pass"
