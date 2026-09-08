"""可选分值事实的端到端契约：旧审计兼容、条件见证及增强故障隔离。"""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from hangma_bot.application.audit_codec import (
    decision_request_from_json, decision_request_to_json,
    rule_candidate_from_json, rule_candidate_to_json,
)
from hangma_bot.hangma import HangmaRules
from hangma_bot.hangma.interface import CandidateValueFacts, ValueAnalysisLimits, ValueCoverage
from hangma_bot.kernel.config import RuleConfig


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/policy/one-draw-value"


def request(case="B"):
    row = json.loads((FIXTURES / (case + ".json")).read_text())
    return decision_request_from_json(row["request_event"]["payload"]["request"])


def rules():
    return HangmaRules(RuleConfig("hangma-mvp-v5-four-white", 1, False))


def test_old_request_keeps_optional_value_absent_and_does_not_gain_facts():
    old = request()
    encoded = decision_request_to_json(old)
    assert all("value_facts" not in candidate for candidate in encoded["rules"]["legal_candidates"])
    assert decision_request_from_json(encoded) == old
    assert rules().analyze(old.observation) == rules().analyze(old.observation, value_limits=None)


def test_conditioned_value_request_roundtrips_all_evidence_without_recomputation():
    old = request()
    current = replace(old, rules=rules().analyze(old.observation, value_limits=ValueAnalysisLimits()))
    assert any(candidate.value_facts.routes for candidate in current.rules.legal_candidates)
    encoded = decision_request_to_json(current)
    assert decision_request_from_json(json.loads(json.dumps(encoded))) == current
    # 消费方看到明确的摸前牌和来源，不把这些条件变成已确认 WinDescription。
    route = next(c.value_facts.routes[0] for c in current.rules.legal_candidates if c.value_facts.routes)
    assert len(route.conditions.pre_draw_hand) == 13 - 3 * route.conditions.meld_count
    assert route.conditions.draw_kind == "normal"


def test_value_failure_does_not_erase_legal_actions_or_emergency(monkeypatch):
    from hangma_bot.hangma import value_analysis

    observation = request().observation
    baseline = rules().analyze(observation)

    def fail(*args, **kwargs):
        raise RuntimeError("injected optional failure")

    monkeypatch.setattr(value_analysis, "attach_value_facts", fail)
    failed = rules().analyze(observation, value_limits=ValueAnalysisLimits())
    assert [replace(c, value_facts=None) for c in failed.legal_candidates] == list(baseline.legal_candidates)
    assert failed.completeness == baseline.completeness
    assert failed.emergency_candidate == baseline.emergency_candidate
    assert all(c.value_facts.coverage is ValueCoverage.UNAVAILABLE for c in failed.legal_candidates)
    assert all("injected optional failure" in c.value_facts.issues[0].reason for c in failed.legal_candidates)


@pytest.mark.parametrize("field,value", [("max_expansions", 0), ("max_expansions", True), ("max_routes_per_candidate", -1)])
def test_analysis_limit_is_a_positive_integer(field, value):
    with pytest.raises(ValueError):
        ValueAnalysisLimits(**{field: value})


def test_missing_coverage_reason_cannot_be_silently_serialized_as_zero_value():
    with pytest.raises(ValueError):
        CandidateValueFacts(coverage=ValueCoverage.PARTIAL)


@pytest.mark.parametrize("mutate", [
    lambda route: route["conditions"].update(baotou="false"),
    lambda route: route["conditions"].update(pre_draw_hand=[]),
    lambda route: route["conditional_settlement"].update(score_delta=[10, 0, 0, 0]),
    lambda route: route.update(useful_tiles=route["useful_tiles"] * 2),
])
def test_invalid_route_payload_fails_closed(mutate):
    analysis = rules().analyze(request().observation, value_limits=ValueAnalysisLimits())
    candidate = next(c for c in analysis.legal_candidates if c.value_facts.routes)
    encoded = rule_candidate_to_json(candidate)
    mutate(encoded["value_facts"]["routes"][0])
    with pytest.raises(ValueError):
        rule_candidate_from_json(encoded)
