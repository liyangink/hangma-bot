"""分牌型进张审计契约：未知与已知空集合不同，历史请求不得被补算。"""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from hangma_bot.application.audit_codec import (
    candidate_facts_from_json,
    candidate_facts_to_json,
    decision_request_from_json,
    decision_request_to_json,
)
from hangma_bot.hangma.interface import CandidateFactKind, CandidateFacts, UsefulTileFact


FIELDS = ("standard_useful_tiles", "seven_pairs_useful_tiles")
FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/policy/one-draw-value/B.json"


def facts():
    """只提供已存在的综合与分牌型向听，不隐式生成分牌型进张。"""
    return CandidateFacts(
        CandidateFactKind.HAND_PROGRESS, 1,
        useful_tiles=(UsefulTileFact("3w", 2),),
        standard_shanten_after=1, seven_pairs_shanten_after=2,
    )


@pytest.mark.parametrize("field", FIELDS)
def test_known_empty_and_unknown_remain_distinct(field):
    original = facts()
    payload = candidate_facts_to_json(original)
    assert field not in payload
    assert getattr(candidate_facts_from_json(payload), field) is None
    payload[field] = None
    assert candidate_facts_from_json(payload) == original
    payload[field] = []
    restored = candidate_facts_from_json(payload)
    assert getattr(restored, field) == ()
    assert candidate_facts_to_json(restored)[field] == []
    assert restored != original


def test_new_collections_distances_and_note_roundtrip_together():
    original = replace(
        facts(),
        standard_useful_tiles=(UsefulTileFact("1w", 0), UsefulTileFact("3w", 2)),
        seven_pairs_useful_tiles=(UsefulTileFact("白", 4),),
        pattern_progress_note="保留已知的分牌型进张事实",
    )
    payload = candidate_facts_to_json(original)
    assert payload["codec_version"] == 1
    restored = candidate_facts_from_json(json.loads(json.dumps(payload)))
    assert restored == original
    assert restored.standard_shanten_after == 1
    assert restored.seven_pairs_shanten_after == 2
    assert restored.useful_tiles == (UsefulTileFact("3w", 2),)


@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("bad_value", [
    True, "[]", {}, 0, (), [None], ["1w"], [{}],
    [{"code": "1w"}], [{"remaining_estimate": 2}],
    [{"code": 1, "remaining_estimate": 2}],
    [{"code": "invalid", "remaining_estimate": 2}],
    [{"code": "1w", "remaining_estimate": True}],
    [{"code": "1w", "remaining_estimate": "2"}],
    [{"code": "1w", "remaining_estimate": 2.0}],
    [{"code": "1w", "remaining_estimate": -1}],
    [{"code": "1w", "remaining_estimate": 5}],
])
def test_bad_collection_payload_is_rejected(field, bad_value):
    payload = candidate_facts_to_json(facts())
    payload[field] = bad_value
    with pytest.raises(ValueError):
        candidate_facts_from_json(payload)


@pytest.mark.parametrize("bad_value", [True, 0, [], {}])
def test_note_is_optional_text_and_rejects_other_types(bad_value):
    payload = candidate_facts_to_json(facts())
    payload["pattern_progress_note"] = bad_value
    with pytest.raises(ValueError):
        candidate_facts_from_json(payload)


def test_explicit_null_note_stays_unknown_and_empty_text_is_preserved():
    payload = candidate_facts_to_json(facts())
    assert "pattern_progress_note" not in payload
    payload["pattern_progress_note"] = None
    assert candidate_facts_from_json(payload) == facts()
    payload["pattern_progress_note"] = ""
    assert candidate_facts_to_json(candidate_facts_from_json(payload))["pattern_progress_note"] == ""


@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("kind,shanten", [
    (CandidateFactKind.WIN, -1),
    (CandidateFactKind.NOT_APPLICABLE, None),
    (CandidateFactKind.ANALYSIS_FAILED, None),
])
def test_even_empty_known_collection_requires_hand_progress(field, kind, shanten):
    payload = candidate_facts_to_json(CandidateFacts(kind, shanten))
    payload[field] = []
    with pytest.raises(ValueError):
        candidate_facts_from_json(payload)


def test_historical_request_and_extended_full_request_roundtrip():
    row = json.loads(FIXTURE.read_text())
    historical = decision_request_from_json(row["request_event"]["payload"]["request"])
    historical_payload = decision_request_to_json(historical)
    for candidate in historical_payload["rules"]["legal_candidates"]:
        if candidate["facts"] is not None:
            assert all(field not in candidate["facts"] for field in (*FIELDS, "pattern_progress_note"))
    assert decision_request_from_json(json.loads(json.dumps(historical_payload))) == historical
    source = next(c for c in historical.rules.legal_candidates
                  if c.facts and c.facts.fact_kind is CandidateFactKind.HAND_PROGRESS)
    changed = replace(source, facts=replace(
        source.facts,
        standard_shanten_after=1, seven_pairs_shanten_after=2,
        standard_useful_tiles=(UsefulTileFact("1w", 4),),
        seven_pairs_useful_tiles=(),
        pattern_progress_note="七对推进牌已知为空",
    ))
    request = replace(historical, rules=replace(
        historical.rules,
        legal_candidates=tuple(changed if c is source else c for c in historical.rules.legal_candidates),
        emergency_candidate=changed,
    ))
    assert decision_request_from_json(json.loads(json.dumps(decision_request_to_json(request)))) == request
