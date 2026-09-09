"""通过公开 choose 验证等胡收益、风险、前提与完整降级计划。"""

import asyncio
import json
from dataclasses import replace
from pathlib import Path

import pytest

from hangma_bot.application.audit_codec import decision_request_from_json
from hangma_bot.hangma import HangmaRules
from hangma_bot.hangma.interface import CandidateValueFacts, RuleCompleteness, RuleIssue, ValueAnalysisLimits, ValueCoverage
from hangma_bot.kernel.actions import Hu, Pass, Tile, WindowPhase
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import PublicDiscard, PublicMeld
from hangma_bot.policy.errors import PolicyTimeoutError
from hangma_bot.policy.hu_upgrade import HuUpgradePolicy, UpgradeRiskCell
from hangma_bot.policy.interface import DecisionBudget
from hangma_bot.policy.value_one_draw import OneDrawValuePolicy

from .support import make_request, rejected


ROOT = Path(__file__).resolve().parents[2]
RULES = HangmaRules(RuleConfig("hangma-mvp-v5-four-white", 1, False))
BUDGET = DecisionBudget(100, 101, 102)
LOW_RISK = tuple(UpgradeRiskCell(band, threat, .80, .20) for band in range(3) for threat in (False, True))


def historical(name="A"):
    original = decision_request_from_json(json.loads(
        (ROOT / "fixtures/policy/one-draw-value" / (name + ".json")).read_text()
    )["request_event"]["payload"]["request"])
    return replace(original, rules=RULES.analyze(original.observation, value_limits=ValueAnalysisLimits()))


def choose(request, **kwargs):
    return asyncio.run(HuUpgradePolicy(monotonic=lambda: 0, risk_cells=kwargs.pop("risk_cells", LOW_RISK),
                                      **kwargs).choose(request, BUDGET))


def baseline(request):
    return asyncio.run(OneDrawValuePolicy(monotonic=lambda: 0).choose(request, BUDGET))


def replace_candidates(request, transform):
    return replace(request, rules=replace(request.rules, legal_candidates=tuple(transform(c) for c in request.rules.legal_candidates)))


@pytest.mark.parametrize("name,action,gain,future", [("A", "discard:5b", 48, 96), ("F", "discard:白", 20, 40)])
def test_real_visible_cases_compare_risk_adjusted_net_scores(name, action, gain, future):
    request = historical(name)
    old = baseline(request)
    plan = choose(request, risk_version="controlled-test")
    assert isinstance(old.candidates[0].action, Hu)
    assert plan.candidates[0].action_key == action
    assert plan.candidates[0].total_score == pytest.approx(.8 * future - .2 * gain)
    assert "立即胡 {0}".format(gain) in plan.candidates[0].reasons[-1]
    assert "最低净分 {0}".format(future) in plan.candidates[0].reasons[-1]
    assert "controlled-test" in plan.candidates[0].reasons[-1]
    assert plan == choose(request, risk_version="controlled-test")
    assert {c.action_key for c in plan.candidates} == {c.action_key for c in old.candidates}
    assert [c.rank for c in plan.candidates] == list(range(1, len(plan.candidates) + 1))
    assert len({c.action_key for c in plan.candidates}) == len(plan.candidates)
    assert plan.candidates[1].action_key == "hu"
    for item in plan.candidates:
        assert item.total_score == sum(part.value for part in item.score_parts)


@pytest.mark.parametrize("survival,payment", [(0, 0), (.5, 0), (.8, .6), (1, 2)])
def test_same_big_hand_is_declined_when_waiting_risk_or_payment_is_too_high(survival, payment):
    request = historical()
    cells = tuple(UpgradeRiskCell(band, threat, survival, payment) for band in range(3) for threat in (False, True))
    assert choose(request, risk_cells=cells) == baseline(request)


def test_payment_is_already_unconditional_and_not_multiplied_by_failure_rate_twice():
    # .8×96−.6×48=48 < 52.8；错误再乘 .2 会变成 71.04 并诱发等胡。
    request = historical()
    assert choose(request, risk_cells=(UpgradeRiskCell(2, False, .8, .6),)) == baseline(request)


@pytest.mark.parametrize("kwargs", [{"upgrade_weight": 0}, {"risk_cells": ()}, {"risk_cells": (UpgradeRiskCell(0, False, .9, .1),)}])
def test_disabled_or_uncalibrated_group_preserves_exact_baseline(kwargs):
    request = historical()
    assert choose(request, **kwargs) == baseline(request)


@pytest.mark.parametrize("wall", [None, 0, 20, 23])
def test_unknown_or_insufficient_remaining_wall_does_not_decline_hu(wall):
    request = historical()
    request = replace(request, observation=replace(request.observation, remaining_tile_count=wall))
    assert choose(request) == baseline(request)


@pytest.mark.parametrize("wall,band", [(24, 0), (39, 0), (40, 1), (63, 1), (64, 2), (83, 2)])
def test_wall_bands_use_current_visible_remaining_tiles(wall, band):
    request = historical()
    request = replace(request, observation=replace(request.observation, remaining_tile_count=wall))
    assert choose(request, risk_cells=(UpgradeRiskCell(band, False, .8, .2),)).candidates[0].action_key == "discard:5b"
    assert choose(request, risk_cells=(UpgradeRiskCell((band + 1) % 3, False, .8, .2),)) == baseline(request)


@pytest.mark.parametrize("threat_kind", ["white", "three_melds"])
def test_visible_opponent_threat_cannot_use_the_low_threat_cell(threat_kind):
    request = historical()
    obs = request.observation
    if threat_kind == "white":
        rivers = list(obs.discards)
        rivers[1] += (Tile("白"),)
        obs = replace(obs, discards=tuple(rivers))
    else:
        melds = list(obs.melds)
        melds[1] = tuple(PublicMeld(1, "peng", (Tile(code),) * 3, 2) for code in ("1t", "2t", "3t"))
        obs = replace(obs, melds=tuple(melds))
    request = replace(request, observation=obs)
    assert choose(request, risk_cells=(UpgradeRiskCell(2, False, .99, 0),)) == baseline(request)


def test_observation_and_rule_degradation_do_not_decline_hu():
    request = historical()
    request = replace(request, observation=replace(request.observation, observation_issues=("牌河不完整",)))
    assert choose(request) == baseline(request)
    request = historical()
    request = replace(request, rules=replace(request.rules, completeness=RuleCompleteness.DEGRADED))
    assert choose(request) == baseline(request)


@pytest.mark.parametrize("missing", [None,
    CandidateValueFacts(coverage=ValueCoverage.PARTIAL, issues=(RuleIssue("value", "截断"),)),
    CandidateValueFacts(coverage=ValueCoverage.UNAVAILABLE, issues=(RuleIssue("value", "缺失"),)),
    CandidateValueFacts(coverage=ValueCoverage.COMPLETE),
])
@pytest.mark.parametrize("target", ["hu", "discards"])
def test_unknown_present_or_future_value_never_becomes_a_zero_cost_opportunity(missing, target):
    request = historical()
    request = replace_candidates(request, lambda c: replace(c, value_facts=missing)
                                 if (isinstance(c.action, Hu) == (target == "hu")) else c)
    assert choose(request) == baseline(request)


@pytest.mark.parametrize("mutation", ["not_baotou", "replacement", "followup", "overlap"])
def test_future_conditions_cannot_be_relaxed_into_an_any_draw_promise(mutation):
    def change(candidate):
        facts = candidate.value_facts
        if isinstance(candidate.action, Hu) or facts is None or not facts.routes:
            return candidate
        routes = facts.routes
        if mutation == "not_baotou":
            routes = tuple(replace(r, conditions=replace(r.conditions, baotou=False)) for r in routes)
        elif mutation == "replacement":
            routes = tuple(replace(r, conditions=replace(r.conditions, draw_kind="replacement")) for r in routes)
        elif mutation == "followup":
            routes = tuple(replace(r, followup_discard="1w") for r in routes)
        else:
            routes = routes + (routes[0],)
        return replace(candidate, value_facts=replace(facts, routes=routes))
    request = replace_candidates(historical(), change)
    assert choose(request) == baseline(request)


def test_rejected_upgrades_are_not_reintroduced_and_hu_remains_available():
    request = historical()
    request = replace(request, rejected_attempts=(rejected("discard:5b"), rejected("discard:8t")))
    plan = choose(request)
    assert isinstance(plan.candidates[0].action, Hu)
    assert not {"discard:5b", "discard:8t"} & {c.action_key for c in plan.candidates}


def test_duplicate_candidate_cannot_replace_first_valid_facts_or_duplicate_plan():
    request = historical()
    bogus = next(c for c in request.rules.legal_candidates if c.action_key == "discard:5b")
    request = replace(request, rules=replace(request.rules, legal_candidates=request.rules.legal_candidates + (replace(bogus, value_facts=None),)))
    plan = choose(request)
    assert plan.candidates[0].action_key == "discard:5b"
    assert len({c.action_key for c in plan.candidates}) == len(plan.candidates)


def response_request():
    obs = historical().observation
    # 历史官方快照的 my_hand 已包含独立标出的 drawn_tile；不重复加牌。
    hand = list(obs.my_hand)
    hand.remove(Tile("5b"))
    obs = replace(obs, phase="response_peng", my_hand=tuple(hand), drawn_tile=None, turn_seat=1,
                  responding_seats=(0, 2, 3), last_discard=PublicDiscard(1, Tile("1w"), obs.snapshot_seq + 1),
                  rule_state=replace(obs.rule_state, baotou=True), gang_draw=False)
    return make_request(obs, RULES.analyze(obs, value_limits=ValueAnalysisLimits()), phase=WindowPhase.RESPONSE_PENG)


def test_response_keeps_proved_baotou_wait_instead_of_changing_its_hand():
    request = response_request()
    assert any(c.action_key == "peng:1w" for c in request.rules.legal_candidates)
    plan = choose(request)
    assert isinstance(plan.candidates[0].action, Pass)
    assert "保持摸前手牌" in plan.candidates[0].reasons[-1]
    assert set(c.action_key for c in plan.candidates) == set(c.action_key for c in baseline(request).candidates)
    denied = replace(request, rejected_attempts=(rejected("pass"),))
    assert "pass" not in {c.action_key for c in choose(denied).candidates}


@pytest.mark.parametrize("name", list("BCDEGH"))
def test_non_hu_positions_keep_previous_iteration_choices(name):
    request = historical(name)
    assert choose(request) == baseline(request)


def test_timeout_after_baseline_returns_that_complete_plan(monkeypatch):
    request = historical()
    policy = HuUpgradePolicy(monotonic=lambda: 101, risk_cells=LOW_RISK)
    old = baseline(request)
    async def completed(*args):
        return old
    monkeypatch.setattr(policy._baseline, "choose", completed)
    plan = asyncio.run(policy.choose(request, BUDGET))
    assert plan.candidates == old.candidates
    assert "PolicyTimeoutError" in plan.degraded_reasons[-1]


def test_baseline_timeout_propagates_to_application_emergency():
    with pytest.raises(PolicyTimeoutError):
        asyncio.run(HuUpgradePolicy(monotonic=lambda: 103, risk_cells=LOW_RISK).choose(historical(), BUDGET))


def test_cancellation_is_not_swallowed_by_enhancement_fallback(monkeypatch):
    policy = HuUpgradePolicy(monotonic=lambda: 0, risk_cells=LOW_RISK)
    async def cancelled(*args):
        raise asyncio.CancelledError()
    monkeypatch.setattr(policy, "_check_deadline", cancelled)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(policy.choose(historical(), BUDGET))


@pytest.mark.parametrize("kwargs", [
    {"upgrade_weight": True}, {"upgrade_weight": .5}, {"safety_margin": -1}, {"safety_margin": float("nan")},
    {"risk_cells": []}, {"risk_cells": (UpgradeRiskCell(0, False, .8, .2),) * 2}, {"risk_version": ""},
])
def test_invalid_configuration_fails_at_assembly(kwargs):
    with pytest.raises(ValueError):
        HuUpgradePolicy(**kwargs)


@pytest.mark.parametrize("args", [(3, False, .8, .2), (0, 0, .8, .2), (0, False, 1.1, 0),
                                  (0, False, -1, 0), (0, False, True, 0), (0, False, .8, float("inf"))])
def test_invalid_risk_cells_are_rejected(args):
    with pytest.raises(ValueError):
        UpgradeRiskCell(*args)
