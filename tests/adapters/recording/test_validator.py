"""离线验证器测试：用记录器真实生成目录，再注入损坏与污染样本。

干净场景验证“完整可审计”的判定；脏场景覆盖悬空动作尝试、重复键、
阶段尝试混用、损坏行、密文残留与统计口径（409 族、模糊提交、时延分位数）。
"""

import json

import pytest

from hangma_bot.adapters.recording import JsonlAuditSink, validate_run
from hangma_bot.adapters.recording.validator import main as validator_main
from hangma_bot.application.contracts import AuditKind

from recording._helpers import make_record


async def _build_clean_run(base):
    """一次完整可审计的最小运行：manifest、生命周期、观察、决策、提交、终局。"""

    sink = JsonlAuditSink(base, "run-clean")
    sink.emit(make_record(AuditKind.RUN_MANIFEST, {"mode": "test_room", "guide_version": 8}))
    sink.emit(make_record(AuditKind.LIFECYCLE_CHANGED, {"status": "running"}))
    for pid in ("P1", "P2"):
        sink.emit(
            make_record(
                AuditKind.AUTHORITATIVE_STATE,
                {"authoritative_seq": 10},
                participant_id=pid,
                game_id="G-shared",
                round_no=1,
                trigger_seq=10,
            )
        )
    sink.emit(
        make_record(
            AuditKind.DECISION_PLANNED,
            {"decision_id": "d1", "revision": 1, "action_keys": ["peng:1w"], "degraded_reasons": []},
            participant_id="P1",
            game_id="G-shared",
            round_no=1,
            trigger_seq=10,
            decision_id="d1",
        )
    )
    sink.emit(
        make_record(
            AuditKind.SUBMISSION_INTENT,
            {"action_key": "peng:1w", "based_on_authoritative_seq": 10},
            participant_id="P1",
            game_id="G-shared",
            round_no=1,
            trigger_seq=10,
            decision_id="d1",
            attempt_no=1,
            wall_time_unix_ms=1000,
        )
    )
    sink.emit(
        make_record(
            AuditKind.SUBMISSION_OUTCOME,
            {"outcome": "accepted"},
            participant_id="P1",
            game_id="G-shared",
            round_no=1,
            trigger_seq=10,
            decision_id="d1",
            attempt_no=1,
            wall_time_unix_ms=1150,
        )
    )
    # 冗余原始快照携带敏感形态：验证记录端第二道脱敏让扫描保持干净。
    sink.emit(
        make_record(
            AuditKind.RAW_PROTOCOL_STATE,
            {"header": {"Authorization": "Bearer leaktoken99"}},
            participant_id="P1",
            game_id="G-shared",
            round_no=1,
            trigger_seq=10,
        )
    )
    sink.emit(
        make_record(
            AuditKind.GAME_FINISHED,
            {"final_scores": [8, 4, 0, -2]},
            participant_id="P1",
            game_id="G-shared",
        )
    )
    sink.emit(
        make_record(
            AuditKind.PARTICIPANT_FINISHED,
            {"finish_reason": "tournament_finished"},
            participant_id="P1",
        )
    )
    summary = await sink.aclose(timeout_seconds=5.0)
    assert summary.audit_degraded is False
    return base / "runs" / "run-clean"


async def test_clean_run_reports_complete(tmp_path, capsys):
    run_dir = await _build_clean_run(tmp_path)
    report = validate_run(run_dir)

    assert report["audit_complete"] is True
    assert report["ok"] is True
    assert report["secret_scan_clean"] is True
    assert report["violation_count"] == 0
    assert report["corrupt_lines"] == []
    assert report["counts_by_kind"]["submission_intent"] == 1
    assert report["counts_by_kind"]["game_finished"] == 1
    assert report["submissions"]["latency_ms"] == {
        "attempts": 1,
        "p50": 150,
        "p95": 150,
        "p99": 150,
        "max": 150,
    }
    # P1 与 P2 各自记录同一场官方对局：games_total 按身份×场次计数。
    assert report["coverage"]["games_total"] == 2
    assert report["coverage"]["games_finished"] == 1
    assert report["coverage"]["participants_finished"] == 1
    assert report["coverage"]["manifest_present"] is True

    assert validator_main([str(run_dir)]) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["audit_complete"] is True


async def _build_dirty_run(base):
    """故意包含六类缺陷的运行：悬空、重复、孤立、混用、重复终局、降级。"""

    sink = JsonlAuditSink(base, "run-dirty")
    sink.emit(make_record(AuditKind.RUN_MANIFEST, {"mode": "test_room"}))
    sink.emit(make_record(AuditKind.LIFECYCLE_CHANGED, {"status": "running"}))

    def ctx_game(game_id="G1", round_no=1, trigger_seq=10):
        return {
            "participant_id": "P1",
            "game_id": game_id,
            "round_no": round_no,
            "trigger_seq": trigger_seq,
        }

    sink.emit(
        make_record(AuditKind.AUTHORITATIVE_STATE, {"authoritative_seq": 10}, **ctx_game())
    )
    # d1: 正常配对，100ms；d2: 409 族拒绝，300ms；d3: 未发送；d4: 模糊提交，500ms。
    # 按应用层 _outcome_payload 的真实形态使用封闭结果类名。
    scenarios = [
        ("d1", "SubmitAccepted", {}, 1100),
        ("d2", "SubmitRejectedRetryable", {"official_code": "409"}, 1300),
        ("d3", "SubmitNotSent", {"reason": "deadline_passed_after_schedule"}, 1400),
        ("d4", "SubmitAmbiguous", {}, 1500),
    ]
    for decision_id, outcome, extra, outcome_time in scenarios:
        common = {**ctx_game(), "decision_id": decision_id, "attempt_no": 1}
        sink.emit(
            make_record(
                AuditKind.SUBMISSION_INTENT,
                {"action_key": "discard:1w", "based_on_authoritative_seq": 10},
                wall_time_unix_ms=1000,
                **common,
            )
        )
        sink.emit(
            make_record(
                AuditKind.SUBMISSION_OUTCOME,
                {"outcome": outcome, **extra},
                wall_time_unix_ms=outcome_time,
                **common,
            )
        )
    # 官方适配器同键第二条 outcome（双层记录常态，outcome_type 键形态，
    # 同时验证验证器对 outcome_type 的归并回退）。时延仍按 1000→1100 计算。
    sink.emit(
        make_record(
            AuditKind.SUBMISSION_OUTCOME,
            {"outcome_type": "SubmitAccepted", "decision_id": "d1", "attempt_no": 1},
            wall_time_unix_ms=1050,
            **{**ctx_game(), "decision_id": "d1", "attempt_no": 1},
        )
    )
    # d5: 悬空（重复 intent 且无 outcome）。
    dangling_ctx = {**ctx_game(), "decision_id": "d5", "attempt_no": 1}
    sink.emit(
        make_record(
            AuditKind.SUBMISSION_INTENT,
            {"action_key": "peng:2w", "based_on_authoritative_seq": 10},
            wall_time_unix_ms=1600,
            **dangling_ctx,
        )
    )
    sink.emit(
        make_record(
            AuditKind.SUBMISSION_INTENT,
            {"action_key": "peng:2w", "based_on_authoritative_seq": 10},
            wall_time_unix_ms=1601,
            **dangling_ctx,
        )
    )
    # d6: 孤立 outcome（没有 intent）。
    sink.emit(
        make_record(
            AuditKind.SUBMISSION_OUTCOME,
            {"outcome": "accepted"},  # 另一层用规范小写值：两种形态归并到同一桶
            wall_time_unix_ms=1700,
            **{**ctx_game(), "decision_id": "d6", "attempt_no": 1},
        )
    )
    # 同一局混入另一个阶段尝试的记录。
    sink.emit(
        make_record(
            AuditKind.AUTHORITATIVE_STATE,
            {"authoritative_seq": 11},
            stage_attempt_id="st-2",
            **ctx_game(trigger_seq=11),
        )
    )
    # 决策降级样本。
    sink.emit(
        make_record(
            AuditKind.DECISION_PLANNED,
            {
                "decision_id": "d1",
                "revision": 1,
                "action_keys": ["discard:1w"],
                "degraded_reasons": ["peng_family_failed"],
            },
            decision_id="d1",
            **ctx_game(),
        )
    )
    # 同一场次重复终局。
    for _ in range(2):
        sink.emit(
            make_record(
                AuditKind.GAME_FINISHED,
                {"final_scores": [1, 2, 3, 4]},
                game_id="G2",
            )
        )
    summary = await sink.aclose(timeout_seconds=5.0)
    assert summary.audit_degraded is False  # 记录器本身未降级；缺陷由验证器发现
    return base / "runs" / "run-dirty"


async def test_dirty_run_reports_all_findings(tmp_path, capsys):
    run_dir = await _build_dirty_run(tmp_path)

    # 注入一条损坏行与一条携带认证原文的记录（模拟旧版记录器的污染）。
    decisions = run_dir / "participants" / "P1" / "decisions.jsonl"
    with decisions.open("a", encoding="utf-8") as handle:
        handle.write("不是 JSON 的损坏行{{{\n")
    games = run_dir / "participants" / "P1" / "games" / "G1.jsonl"
    leaked = {
        "schema_version": 1,
        "kind": "authoritative_state",
        "context": {
            "run_id": "run-dirty",
            "tournament_id": "t-1",
            "participant_id": "P1",
            "stage_attempt_id": "st-1",
            "game_id": "G1",
            "round_no": 1,
            "trigger_seq": 12,
        },
        "wall_time_unix_ms": 5,
        "monotonic_ns": 5,
        "payload": {"header": {"Authorization": "Bearer realsecret99"}},
    }
    with games.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(leaked, ensure_ascii=False) + "\n")
    # 注入一条未知信封版本的记录。
    wrong_version = dict(leaked)
    wrong_version["schema_version"] = 99
    wrong_version["payload"] = {}
    with games.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(wrong_version, ensure_ascii=False) + "\n")

    report = validate_run(run_dir)
    violations = {
        finding["code"] for finding in report["findings"] if finding["severity"] == "violation"
    }
    warnings = {
        finding["code"] for finding in report["findings"] if finding["severity"] == "warning"
    }

    assert report["audit_complete"] is False
    assert {"dangling_intent", "orphan_outcome"} <= violations
    assert {"stage_attempt_mixing"} <= violations
    assert {"secret_found", "malformed_record"} <= violations
    # 双层记录（应用层与官方适配器各记一次）是正常形态，不再报告；
    # 三条及以上同层重复才会被识别（见 test_validator_assembly_rulings.py）。
    assert "duplicate_intent" not in warnings
    assert "duplicate_outcome" not in warnings
    assert "duplicate_game_finished" not in warnings
    assert report["secret_scan_clean"] is False
    assert len(report["corrupt_lines"]) == 1
    assert report["corrupt_lines"][0]["file"].endswith("decisions.jsonl")

    submissions = report["submissions"]
    assert submissions["outcome_histogram"] == {
        "accepted": 3,
        "ambiguous": 1,
        "not_sent": 1,
        "rejected_retryable": 1,
    }
    assert submissions["rejected_total"] == 1
    assert submissions["ambiguous"] == 1
    assert submissions["not_sent"] == 1
    assert submissions["not_sent_timeouts"] == 1
    assert submissions["latency_ms"]["attempts"] == 4
    assert submissions["latency_ms"]["p50"] == 300
    assert submissions["latency_ms"]["p95"] == 500
    assert submissions["latency_ms"]["p99"] == 500
    assert report["coverage"]["rule_degradations"] == 1

    assert validator_main([str(run_dir)]) == 1
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["audit_complete"] is False


def test_validate_missing_directory_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        validate_run(tmp_path / "nope")
