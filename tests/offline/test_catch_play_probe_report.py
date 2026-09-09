"""探针报告不能把双层记录或明确拒绝计为成功，也不能从零样本宣布禁令。"""

import json
from pathlib import Path
import runpy

from hangma_bot.application.audit_codec import decision_request_to_json
from hangma_bot.kernel.actions import Pass, Peng, Tile, WindowPhase
from hangma_bot.kernel.observation import PublicEvent, RulePublicState
from tests.unit.policy.support import candidates_for, make_observation, make_request, make_rules


REPORT = runpy.run_path(str(Path(__file__).resolve().parents[2] /
    "review/piao-window-alignment-2026-09-08/summarize_probe.py"))["summarize"]


def write_audit(root, outcome="SubmitAccepted", duplicate_outcome="accepted"):
    observation = make_observation(
        phase="response_peng", responding_seats=(0,), turn_seat=3,
        public_history=(PublicEvent(8, "tile_discarded", 0, (Tile("白"),), catch_play=True),
                        PublicEvent(9, "tile_drawn", 3, ()),
                        PublicEvent(10, "tile_discarded", 3, (Tile("东"),), catch_play=True)),
        rule_state=RulePublicState(Tile("白"), False, 0, True), consumed_seq=10,
    )
    candidates = candidates_for([Pass(), Peng(Tile("东"))])
    request = make_request(observation, make_rules(candidates, candidates[0]), phase=WindowPhase.RESPONSE_PENG)
    context = {"run_id": "run-test", "participant_id": "p-test", "stage_attempt_id": "s-test",
               "game_id": "g1", "round_no": 1, "decision_id": "d1"}
    records = []

    def row(kind, payload, attempt=None):
        records.append({"schema_version": 1, "kind": kind,
                        "context": {**context, "attempt_no": attempt}, "payload": payload})

    row("decision_input", {"request": decision_request_to_json(request), "plan_revision": 1})
    row("submission_intent", {"action_key": "peng:东", "plan_revision": 1}, 1)
    row("submission_intent", {"action_key": "peng:东", "audit_producer": "official_adapter"}, 1)
    row("submission_outcome", {"outcome": outcome}, 1)
    row("submission_outcome", {"outcome_type": duplicate_outcome}, 1)
    (root / "decisions.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))


def test_dual_submission_records_are_one_owner_claim_attempt(tmp_path):
    write_audit(tmp_path)
    report = REPORT(tmp_path)
    assert report["counts"]["observed_windows:owner:response_peng"] == 1
    assert report["counts"]["claim_attempts:owner:accepted"] == 1
    assert report["observed_white_events_lower_bound"] == 1
    assert len(report["claim_cases"]) == 1
    assert not report["read_or_link_issues"]


def test_explicit_rejection_is_not_counted_as_acceptance(tmp_path):
    write_audit(tmp_path, "SubmitRejectedRetryable", "rejected_retryable")
    report = REPORT(tmp_path)
    assert report["counts"]["claim_attempts:owner:rejected_retryable"] == 1
    assert "claim_attempts:owner:accepted" not in report["counts"]


def test_conflicting_or_partial_records_are_reported(tmp_path):
    write_audit(tmp_path, "SubmitAccepted", "rejected_retryable")
    with (tmp_path / "decisions.jsonl").open("a") as stream:
        stream.write('{"kind":')
    report = REPORT(tmp_path)
    assert "claim_attempts:owner:accepted" not in report["counts"]
    assert len(report["read_or_link_issues"]) == 2


def test_empty_audit_does_not_claim_a_platform_rule(tmp_path):
    report = REPORT(tmp_path)
    assert report["counts"] == {} and report["claim_cases"] == []
    assert any("不等于规则禁止" in text for text in report["evidence_limits"])


def test_live_adapter_without_stage_id_links_only_to_unique_application_decision(tmp_path):
    """本次官方实测适配器阶段为空；应用层有阶段，双层结果只计一次。"""
    write_audit(tmp_path)
    path = tmp_path / "decisions.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[2]["context"]["stage_attempt_id"] = None
    rows[4]["context"]["stage_attempt_id"] = None
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    report = REPORT(tmp_path)
    assert report["counts"]["claim_attempts:owner:accepted"] == 1
    assert not report["read_or_link_issues"]
    assert report["claim_cases"][0]["stage_attempt_id"] == "s-test"


def test_missing_stage_does_not_guess_between_two_stage_attempts(tmp_path):
    write_audit(tmp_path)
    path = tmp_path / "decisions.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[4]["context"]["stage_attempt_id"] = None
    duplicate = json.loads(json.dumps(rows[0]))
    duplicate["context"]["stage_attempt_id"] = "s-other"
    rows.append(duplicate)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    report = REPORT(tmp_path)
    assert any(item["issue"] == "提交缺对应决策输入" for item in report["read_or_link_issues"])
