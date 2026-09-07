"""真实双层记录的汇总回归：统计动作尝试和规则输入，不把日志条数当业务数。"""

from dataclasses import asdict
import json

import pytest

from hangma_bot.adapters.recording import validate_run
from hangma_bot.application.contracts import AuditKind

from recording._helpers import make_record


def _record(kind, payload, **context):
    return asdict(make_record(kind, payload, **{
        "game_id": "G1", "decision_id": "d1", "attempt_no": 1,
        **context,
    }))


def _validate(tmp_path, records):
    """只经公开验证入口读取严格 JSON 信封；输入文件模拟真实双层生产形态。"""

    (tmp_path / "manifest.json").write_text(json.dumps(asdict(make_record(
        AuditKind.RUN_MANIFEST, {"mode": "test_room"},
    ))))
    (tmp_path / "summary.json").write_text('{"audit_degraded": false}')
    lifecycle = asdict(make_record(AuditKind.LIFECYCLE_CHANGED, {"status": "running"}))
    (tmp_path / "decisions.jsonl").write_text("".join(
        json.dumps(row, ensure_ascii=False) + "\n" for row in [lifecycle, *records]
    ))
    return validate_run(tmp_path)


@pytest.mark.parametrize("outcome,alias,extra", [
    ("accepted", "SubmitAccepted", {}),
    ("rejected_retryable", "SubmitRejectedRetryable", {"official_code": "409"}),
    ("rejected_closed", "SubmitRejectedClosed", {"official_code": "409"}),
    ("rejected_no_refresh", "SubmitRejectedNoRefresh", {"official_code": "429"}),
    ("not_sent", "SubmitNotSent", {"reason": "deadline_passed_after_schedule"}),
    ("ambiguous", "SubmitAmbiguous", {"reason": "network_timeout"}),
    ("fatal", "SubmitFatal", {"official_code": "401"}),
])
def test_dual_layer_outcomes_count_one_attempt(tmp_path, outcome, alias, extra):
    records = [
        _record(AuditKind.SUBMISSION_INTENT, {"action_key": "pass"}),
        _record(AuditKind.SUBMISSION_INTENT, {"action_key": "pass"}, stage_attempt_id=None),
        _record(AuditKind.SUBMISSION_OUTCOME, {"outcome_type": alias, **extra},
                stage_attempt_id=None, wall_time_unix_ms=1100),
        _record(AuditKind.SUBMISSION_OUTCOME, {"outcome": outcome, **extra},
                wall_time_unix_ms=1110),
    ]
    report = _validate(tmp_path, records)
    stats = report["submissions"]
    assert report["audit_complete"] is True
    assert stats["intents"] == stats["outcomes"] == 2
    assert stats["distinct_attempts"] == stats["paired_attempts"] == 1
    assert stats["outcome_histogram"] == {outcome: 1}
    assert stats["outcome_record_histogram"] == {outcome: 2}
    assert stats["rejected_total"] == int(outcome.startswith("rejected_"))
    assert stats["ambiguous"] == int(outcome == "ambiguous")
    assert stats["not_sent"] == stats["not_sent_timeouts"] == int(outcome == "not_sent")
    assert stats["official_code_histogram"] == ({extra["official_code"]: 1} if "official_code" in extra else {})
    assert stats["official_code_record_histogram"] == ({extra["official_code"]: 2} if "official_code" in extra else {})
    assert stats["latency_ms"]["attempts"] == 1
    assert stats["latency_ms"]["max"] == 110


@pytest.mark.parametrize("scope", ["run_id", "tournament_id", "participant_id", "game_id"])
def test_same_decision_id_does_not_pair_across_scope(tmp_path, scope):
    """异场等作用域的孤立 outcome 不能借另一场 intent 伪装完整。"""

    report = _validate(tmp_path, [
        _record(AuditKind.SUBMISSION_INTENT, {"action_key": "pass"}),
        _record(AuditKind.SUBMISSION_OUTCOME, {"outcome": "accepted"}, **{scope: "other"}),
    ])
    assert report["submissions"]["distinct_attempts"] == 2
    assert report["submissions"]["paired_attempts"] == 0
    assert {"dangling_intent", "orphan_outcome"} <= {item["code"] for item in report["findings"]}


@pytest.mark.parametrize("second,field", [
    ({"outcome_type": "SubmitNotSent", "official_code": "409"}, "outcome"),
    ({"outcome_type": "SubmitRejectedRetryable", "official_code": "429"}, "official_code"),
    ({"outcome_type": "SubmitRejectedRetryable", "official_code": "409", "reason": "different"}, "reason"),
])
def test_conflicting_results_remain_explicit_and_are_not_chosen(tmp_path, second, field):
    report = _validate(tmp_path, [
        _record(AuditKind.SUBMISSION_INTENT, {"action_key": "pass"}),
        _record(AuditKind.SUBMISSION_OUTCOME, {
            "outcome": "rejected_retryable", "official_code": "409", "reason": "stale",
        }),
        _record(AuditKind.SUBMISSION_OUTCOME, second, stage_attempt_id=None),
    ])
    stats = report["submissions"]
    assert report["audit_complete"] is False
    assert stats["outcomes"] == 2
    assert stats["outcome_histogram"] == {"conflicting_outcome": 1}
    assert stats["rejected_total"] == 0
    assert stats["official_code_histogram"] == {}
    assert stats["conflicting_attempts"] == 1
    conflict = stats["conflicts"][0]
    assert field in conflict["fields"]
    assert conflict["context"]["game_id"] == "G1"
    assert len(conflict["records"]) == 2
    assert all(record["location"]["line_no"] > 0 for record in conflict["records"])
    assert "submission_outcome_conflict" in {item["code"] for item in report["findings"]}


def test_optional_code_and_text_sequence_have_compatible_representations(tmp_path):
    report = _validate(tmp_path, [
        _record(AuditKind.SUBMISSION_INTENT, {"action_key": "pass"}),
        _record(AuditKind.SUBMISSION_OUTCOME, {
            "outcome": "rejected_retryable", "latest_authoritative_seq": "12",
        }),
        _record(AuditKind.SUBMISSION_OUTCOME, {
            "outcome_type": "SubmitRejectedRetryable", "official_code": "409",
            "latest_authoritative_seq": 12,
        }, stage_attempt_id=None),
    ])
    assert report["audit_complete"] is True
    assert report["submissions"]["outcome_histogram"] == {"rejected_retryable": 1}
    assert report["submissions"]["official_code_histogram"] == {"409": 1}


def test_multiple_attempts_and_repeated_records_keep_distinct_counts(tmp_path):
    records = []
    for attempt, outcome in ((1, "accepted"), (2, "new_official_outcome")):
        records.append(_record(AuditKind.SUBMISSION_INTENT, {"action_key": "pass"}, attempt_no=attempt))
        records.extend(_record(
            AuditKind.SUBMISSION_OUTCOME, {"outcome": outcome}, attempt_no=attempt,
        ) for _ in range(3))
    stats = _validate(tmp_path, records)["submissions"]
    assert stats["distinct_attempts"] == 2
    assert stats["outcomes"] == 6
    assert stats["outcome_histogram"] == {"accepted": 1, "new_official_outcome": 1}
    assert stats["outcome_record_histogram"] == {"accepted": 3, "new_official_outcome": 3}


def test_uncorrelatable_outcome_stays_in_raw_count(tmp_path):
    report = _validate(tmp_path, [
        _record(AuditKind.SUBMISSION_OUTCOME, {"outcome": "accepted"}, decision_id=None),
    ])
    stats = report["submissions"]
    assert report["audit_complete"] is False
    assert stats["outcomes"] == stats["uncorrelatable_outcome_records"] == 1
    assert stats["outcome_record_histogram"] == {"accepted": 1}
    assert stats["outcome_histogram"] == {}


def test_conflicting_fields_in_one_record_are_not_hidden_by_key_preference(tmp_path):
    report = _validate(tmp_path, [
        _record(AuditKind.SUBMISSION_INTENT, {"action_key": "pass"}),
        _record(AuditKind.SUBMISSION_OUTCOME, {
            "outcome": "accepted", "outcome_type": "SubmitNotSent",
        }),
    ])
    assert report["audit_complete"] is False
    assert report["submissions"]["outcome_histogram"] == {"conflicting_outcome": 1}
    assert report["submissions"]["outcome_record_histogram"] == {"conflicting_outcome": 1}


def _input(completeness, issues=None, **context):
    return _record(AuditKind.DECISION_INPUT, {"plan_revision": 1, "request": {"rules": {
        "completeness": completeness, "issues": [] if issues is None else issues,
    }}}, **context)


def test_rules_complete_with_legacy_policy_hint_is_not_rule_degradation(tmp_path):
    report = _validate(tmp_path, [
        _input("complete"),
        _record(AuditKind.DECISION_PLANNED, {"degraded_reasons": [
            "评分兼容视图[legacy-pass-neutral-v1]：原始规则事实不改写",
        ], "rule_completeness": "complete"}),
    ])
    coverage = report["coverage"]
    assert coverage["rule_degradations"] == 0
    assert coverage["rule_analysis"]["complete_decisions"] == 1
    assert coverage["rule_analysis"]["unknown_decisions"] == 0
    assert coverage["plan_diagnostics"]["compatibility_hint_decisions"] == 1
    assert coverage["plan_diagnostics"]["legacy_degraded_reason_records"] == 1


def test_rules_and_issue_counts_deduplicate_decision_revisions_in_each_game(tmp_path):
    issue = {"area": "chain_piao", "reason": "飘次数未知"}
    report = _validate(tmp_path, [
        _input("degraded", [issue, issue]),
        _input("degraded", [issue]),
        _input("complete", game_id="G2"),
        _record(AuditKind.DECISION_PLANNED, {"degraded_reasons": ["策略保底"]}),
        _record(AuditKind.DECISION_PLANNED, {"degraded_reasons": ["策略保底"]}),
        _record(AuditKind.DECISION_PLANNED, {"degraded_reasons": []}, game_id="G2"),
    ])
    coverage = report["coverage"]
    assert coverage["decisions_planned"] == 2
    assert coverage["rule_degradations"] == 1
    assert coverage["rule_analysis"]["input_records"] == 3
    assert coverage["rule_analysis"]["input_decisions"] == 2
    assert coverage["rule_analysis"]["complete_decisions"] == 1
    assert coverage["rule_analysis"]["issue_area_histogram"] == {"chain_piao": 1}
    assert coverage["rule_analysis"]["degradation_examples"][0]["context"]["game_id"] == "G1"
    assert coverage["plan_diagnostics"]["other_hint_decisions"] == 1


def test_missing_legacy_input_is_unknown_even_when_plan_declares_degraded(tmp_path):
    report = _validate(tmp_path, [
        _record(AuditKind.DECISION_PLANNED, {
            "degraded_reasons": ["peng_family_failed"], "rule_completeness": "degraded",
        }),
    ])
    coverage = report["coverage"]
    assert report["audit_complete"] is True
    assert coverage["rule_degradations"] == 0
    assert coverage["rule_analysis"]["unknown_decisions"] == 1
    assert coverage["rule_analysis"]["missing_input_decisions"] == 1
    assert coverage["plan_diagnostics"]["legacy_rule_completeness_histogram"] == {"degraded": 1}


@pytest.mark.parametrize("rules", [
    None, {}, {"completeness": "future", "issues": []},
    {"completeness": "complete", "issues": [{"area": "chain_piao", "reason": "未知"}]},
])
def test_incomplete_rule_input_is_unknown_not_complete(tmp_path, rules):
    report = _validate(tmp_path, [
        _record(AuditKind.DECISION_INPUT, {"request": {"rules": rules}}),
    ])
    coverage = report["coverage"]
    assert coverage["rule_degradations"] == 0
    assert coverage["rule_analysis"]["unknown_decisions"] == 1
    assert coverage["rule_analysis"]["invalid_input_decisions"] == 1


def test_replanning_from_degraded_to_complete_still_counts_one_affected_decision(tmp_path):
    report = _validate(tmp_path, [
        _input("degraded", [{"area": "chain_piao", "reason": "未知"}]),
        _input("complete"),
    ])
    coverage = report["coverage"]
    assert coverage["rule_degradations"] == 1
    assert coverage["rule_analysis"]["complete_decisions"] == 0
