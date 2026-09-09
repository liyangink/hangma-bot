"""分牌型向听的审计扩展：保留未知、历史格式及完整请求往返。"""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from hangma_bot.application.audit_codec import (
    candidate_facts_from_json,
    candidate_facts_to_json,
    decision_request_from_json,
    decision_request_to_json,
    rule_candidate_from_json,
    rule_candidate_to_json,
)
from hangma_bot.hangma.interface import CandidateFactKind, CandidateFacts


FIELDS = ("standard_shanten_after", "seven_pairs_shanten_after")
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/policy/one-draw-value/B.json"


def historical_request():
    """读取已脱敏的旧审计请求，不调用规则引擎补全事实。"""
    row = json.loads(FIXTURE.read_text())
    return decision_request_from_json(row["request_event"]["payload"]["request"])


def test_absent_pattern_progress_preserves_old_facts_wire_format():
    old_payload = {
        "codec_version": 1,
        "fact_kind": "hand_progress",
        "shanten_after": 0,
        "useful_tiles": [{"code": "1w", "remaining_estimate": 3}],
        "best_followup_discard": None,
        "replacement_draw_unknown": False,
        "completeness": "complete",
        "note": None,
    }
    restored = candidate_facts_from_json(old_payload)
    assert restored.standard_shanten_after is None
    assert restored.seven_pairs_shanten_after is None
    assert candidate_facts_to_json(restored) == old_payload
    assert json.dumps(candidate_facts_to_json(restored)) == json.dumps(old_payload)


@pytest.mark.parametrize("standard,seven_pairs", [(0, 2), (3, 0), (-1, -1), (1, None), (None, 2)])
def test_pattern_progress_and_explicit_unknown_roundtrip(standard, seven_pairs):
    facts = CandidateFacts(
        CandidateFactKind.HAND_PROGRESS,
        shanten_after=0,
        standard_shanten_after=standard,
        seven_pairs_shanten_after=seven_pairs,
    )
    payload = candidate_facts_to_json(facts)
    assert payload["codec_version"] == 1
    assert candidate_facts_from_json(json.loads(json.dumps(payload))) == facts
    for field, value in zip(FIELDS, (standard, seven_pairs)):
        assert (field in payload) is (value is not None)
        if value is None:
            payload[field] = None
    assert candidate_facts_from_json(payload) == facts


@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("bad_value", [True, False, "0", 0.0, [], {}, -2])
def test_invalid_pattern_progress_fails_closed(field, bad_value):
    payload = candidate_facts_to_json(CandidateFacts(CandidateFactKind.HAND_PROGRESS, 0))
    payload[field] = bad_value
    with pytest.raises(ValueError):
        candidate_facts_from_json(payload)


@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("kind,shanten", [
    (CandidateFactKind.WIN, -1),
    (CandidateFactKind.NOT_APPLICABLE, None),
    (CandidateFactKind.ANALYSIS_FAILED, None),
])
def test_pattern_progress_cannot_be_attached_to_other_fact_kinds(field, kind, shanten):
    payload = candidate_facts_to_json(CandidateFacts(kind, shanten))
    payload[field] = 0
    with pytest.raises(ValueError):
        candidate_facts_from_json(payload)


def test_historical_fixture_stays_unknown_without_rule_recalculation():
    request = historical_request()
    facts = [candidate.facts for candidate in request.rules.legal_candidates if candidate.facts]
    assert facts
    assert all(getattr(fact, field) is None for fact in facts for field in FIELDS)
    encoded = decision_request_to_json(request)
    assert all(
        field not in candidate["facts"]
        for candidate in encoded["rules"]["legal_candidates"]
        if candidate["facts"] is not None
        for field in FIELDS
    )
    assert decision_request_from_json(json.loads(json.dumps(encoded))) == request


def test_new_candidate_and_full_request_preserve_both_pattern_distances():
    old = historical_request()
    source = next(
        candidate for candidate in old.rules.legal_candidates
        if candidate.facts and candidate.facts.fact_kind is CandidateFactKind.HAND_PROGRESS
    )
    candidate = replace(source, facts=replace(
        source.facts, standard_shanten_after=0, seven_pairs_shanten_after=2,
    ))
    assert rule_candidate_from_json(json.loads(json.dumps(rule_candidate_to_json(candidate)))) == candidate
    request = replace(old, rules=replace(
        old.rules,
        legal_candidates=tuple(candidate if item is source else item for item in old.rules.legal_candidates),
        emergency_candidate=candidate,
    ))
    assert decision_request_from_json(json.loads(json.dumps(decision_request_to_json(request)))) == request
