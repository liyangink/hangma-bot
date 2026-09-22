"""B3 编解码升级契约：followup_branches/family_progress 的审计往返。

依据 contracts/action-value-v1.json scoring_view 字段与 B1 载荷类型
（hangma.interface.FollowupBranchFacts/FamilyProgress）。兼容先例沿用
test_pattern_progress_codec.py：新键仅在非默认时写入；旧 JSON 缺键还原
None/()；语义校验交给 dataclass 构造。
"""

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
from hangma_bot.hangma.interface import (
    CandidateFactKind,
    CandidateFacts,
    FamilyId,
    FamilyProgress,
    FollowupBranchFacts,
    ProgressKind,
    RouteStatus,
    RuleCandidate,
    UsefulTileFact,
)
from hangma_bot.kernel.actions import Discard, Tile

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/policy/one-draw-value/B.json"


def _branch(discard="2b", **overrides):
    base = dict(
        followup_key="peng:2b#2b",
        followup_discard=discard,
        combined_shanten=1,
        standard_shanten_after=1,
        seven_pairs_shanten_after=3,
        useful_tiles=(UsefulTileFact("3b", 3), UsefulTileFact("5b", 2)),
        support_remaining=5,
    )
    base.update(overrides)
    return FollowupBranchFacts(**base)


def _progress(**overrides):
    base = dict(
        family=FamilyId.BRANCH,
        progress=ProgressKind.ADVANCE,
        route_status=RouteStatus.WITNESSED,
        basis="同一等待态分牌型向听距离由唯一规则源计算",
    )
    base.update(overrides)
    return FamilyProgress(**base)


def _payload_facts():
    return CandidateFacts(
        fact_kind=CandidateFactKind.HAND_PROGRESS,
        shanten_after=1,
        best_followup_discard="2b",
        followup_branches=(
            _branch(),
            _branch(
                discard="3b",
                followup_key="peng:2b#3b",
                combined_shanten=2,
                useful_tiles=(),
                support_remaining=0,
            ),
        ),
        family_progress=(
            _progress(),
            _progress(
                family=FamilyId.FOUR_WHITE,
                progress=ProgressKind.RETREAT,
                route_status=RouteStatus.CLOSED_PROVEN,
            ),
        ),
    )


def test_absent_payload_keys_preserve_old_facts_wire_format():
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
    assert restored.followup_branches is None
    assert restored.family_progress == ()
    assert candidate_facts_to_json(restored) == old_payload


def test_default_facts_do_not_write_payload_keys():
    payload = candidate_facts_to_json(
        CandidateFacts(CandidateFactKind.HAND_PROGRESS, 0)
    )
    assert "followup_branches" not in payload
    assert "family_progress" not in payload
    # 已知空 family_progress（等值于默认）同样不写键。
    empty_progress = candidate_facts_to_json(
        CandidateFacts(CandidateFactKind.HAND_PROGRESS, 0, family_progress=())
    )
    assert "family_progress" not in empty_progress
    assert "baotou_after" not in empty_progress


@pytest.mark.parametrize("value", [False, True])
def test_baotou_after_roundtrips_without_losing_false(value):
    """动作后爆头是三态事实；False 不能因真假值判断而从审计记录丢失。"""

    facts = CandidateFacts(
        CandidateFactKind.HAND_PROGRESS, 0, baotou_after=value
    )
    payload = candidate_facts_to_json(facts)
    assert payload["baotou_after"] is value
    assert candidate_facts_from_json(payload) == facts


def test_old_payload_without_baotou_after_restores_unknown():
    payload = candidate_facts_to_json(
        CandidateFacts(CandidateFactKind.HAND_PROGRESS, 0, baotou_after=True)
    )
    payload.pop("baotou_after")
    assert candidate_facts_from_json(payload).baotou_after is None


def test_payload_roundtrip_uses_snake_case_and_string_enums():
    facts = _payload_facts()
    payload = candidate_facts_to_json(facts)
    branch = payload["followup_branches"][0]
    assert set(branch) == {
        "followup_key", "followup_discard", "combined_shanten",
        "standard_shanten_after", "seven_pairs_shanten_after",
        "useful_tiles", "support_remaining",
    }
    entry = payload["family_progress"][0]
    assert set(entry) == {"family", "progress", "route_status", "basis"}
    assert entry["family"] == "branch"
    assert entry["progress"] == "advance"
    assert entry["route_status"] == "witnessed"
    restored = candidate_facts_from_json(json.loads(json.dumps(payload)))
    # 编解码升级后载荷参与相等性：完整往返必须逐字段还原。
    assert restored == facts
    assert restored.followup_branches == facts.followup_branches
    assert restored.family_progress == facts.family_progress


def test_null_and_empty_payload_keys_restore_canonical_defaults():
    payload = candidate_facts_to_json(_payload_facts())
    payload["followup_branches"] = None
    payload["family_progress"] = []
    restored = candidate_facts_from_json(payload)
    assert restored.followup_branches is None
    assert restored.family_progress == ()
    assert restored == CandidateFacts(
        fact_kind=CandidateFactKind.HAND_PROGRESS,
        shanten_after=1,
        best_followup_discard="2b",
    )


@pytest.mark.parametrize("key", ["followup_branches", "family_progress"])
@pytest.mark.parametrize("bad_value", [True, 0, "x", {"a": 1}])
def test_non_list_payload_fails_closed(key, bad_value):
    payload = candidate_facts_to_json(CandidateFacts(CandidateFactKind.HAND_PROGRESS, 0))
    payload[key] = bad_value
    with pytest.raises(ValueError):
        candidate_facts_from_json(payload)


def test_bad_branch_shape_fails_closed():
    payload = candidate_facts_to_json(CandidateFacts(CandidateFactKind.HAND_PROGRESS, 0))
    payload["followup_branches"] = [{"followup_discard": "2b"}]
    with pytest.raises(ValueError):
        candidate_facts_from_json(payload)


def test_bad_family_enum_fails_closed():
    payload = candidate_facts_to_json(CandidateFacts(CandidateFactKind.HAND_PROGRESS, 0))
    payload["family_progress"] = [{
        "family": "not-a-family", "progress": "advance",
        "route_status": "witnessed", "basis": "x",
    }]
    with pytest.raises(ValueError):
        candidate_facts_from_json(payload)


def test_semantic_validation_delegated_to_dataclass():
    # followup_branches 需要 best_followup_discard（吃/碰适用口径）——
    # 编解码不重复规则，交由 CandidateFacts 构造函数拒绝。
    payload = candidate_facts_to_json(CandidateFacts(CandidateFactKind.HAND_PROGRESS, 0))
    payload["followup_branches"] = [
        {
            "followup_key": "discard:1w#2b", "followup_discard": "2b",
            "combined_shanten": 1, "standard_shanten_after": None,
            "seven_pairs_shanten_after": None, "useful_tiles": [],
            "support_remaining": 0,
        }
    ]
    with pytest.raises(ValueError):
        candidate_facts_from_json(payload)


def test_candidate_and_full_request_roundtrip_with_payload():
    facts = _payload_facts()
    rule_candidate = RuleCandidate(
        action=Discard(Tile("2b")),
        action_key="discard:2b",
        evidence=("test",),
        facts=facts,
    )
    restored = rule_candidate_from_json(
        json.loads(json.dumps(rule_candidate_to_json(rule_candidate)))
    )
    assert restored == rule_candidate
    assert restored.facts.followup_branches == facts.followup_branches

    row = json.loads(FIXTURE.read_text())
    request = decision_request_from_json(row["request_event"]["payload"]["request"])
    upgraded = replace(
        request,
        rules=replace(
            request.rules,
            legal_candidates=tuple(
                rule_candidate
                if item.action_key != rule_candidate.action_key
                else rule_candidate
                for item in request.rules.legal_candidates
            ),
        ),
    )
    encoded = decision_request_to_json(upgraded)
    assert any(
        candidate["facts"] and "followup_branches" in candidate["facts"]
        for candidate in encoded["rules"]["legal_candidates"]
    )
    assert decision_request_from_json(json.loads(json.dumps(encoded))) == upgraded


def test_historical_fixture_restores_payload_defaults():
    row = json.loads(FIXTURE.read_text())
    request = decision_request_from_json(row["request_event"]["payload"]["request"])
    for candidate in request.rules.legal_candidates:
        if candidate.facts is not None:
            assert candidate.facts.followup_branches is None
            assert candidate.facts.family_progress == ()
    encoded = decision_request_to_json(request)
    assert all(
        "followup_branches" not in candidate["facts"]
        and "family_progress" not in candidate["facts"]
        for candidate in encoded["rules"]["legal_candidates"]
        if candidate["facts"] is not None
    )
    assert decision_request_from_json(json.loads(json.dumps(encoded))) == request
