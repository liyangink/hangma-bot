"""组装波回归：验证器对 2026-09-04 契约收口与双层记录形态的判定。

覆盖三个真实运行事实，锁定验证器口径：

1. 官方适配器按契约不生产 stage_attempt_id（接口协议第 7.1 节），
   同一场缺失与非空共存是双层记录常态，不是阶段尝试混用；
   两个及以上不同非空值才是混用（中断尝试混入有效成绩）。
2. SubmitRejectedNoRefresh 计入显式拒绝族（rejected_total）。
3. 双层 GAME_FINISHED 的终局分数一致性：一致才进入终局分数汇总，
   不一致只报告 warning，不猜测哪一层正确。
"""

from __future__ import annotations

import json

import pytest

from hangma_bot.adapters.recording import JsonlAuditSink, validate_run
from hangma_bot.application.contracts import AuditKind

from recording._helpers import make_record


async def _build_layer_run(base, *, conflicting_scores: bool = False) -> None:
    """构造带双层记录的一次最小完整运行（应用层 + 官方适配器形态）。"""

    sink = JsonlAuditSink(base, "run-layers")
    sink.emit(make_record(AuditKind.RUN_MANIFEST, {"mode": "test_room", "guide_version": 8}))
    sink.emit(make_record(AuditKind.LIFECYCLE_CHANGED, {"event": "status_changed", "from": None, "to": "running"}))
    # 应用层赛事快照（监督层形态，无场上下文）。
    sink.emit(
        make_record(
            AuditKind.AUTHORITATIVE_STATE,
            {"status": "running", "stage_no": 1, "active_games": ["G1"]},
            stage_attempt_id="st-1",
        )
    )
    # 应用层场次事实（带 stage_attempt_id）与官方适配器双层记录
    # （无 stage_attempt_id：适配器契约禁止生成该标识）。
    sink.emit(
        make_record(
            AuditKind.AUTHORITATIVE_STATE,
            {"authoritative_seq": 10},
            stage_attempt_id="st-1",
            game_id="G1",
            round_no=1,
            trigger_seq=10,
        )
    )
    sink.emit(
        make_record(
            AuditKind.AUTHORITATIVE_STATE,
            {
                "seq": 10,
                "phase": "draw",
                "turn": 0,
                "window": {"game_id": "G1", "round_no": 1, "trigger_seq": 10, "phase": "draw", "seat": 0},
            },
            stage_attempt_id=None,
            game_id="G1",
            round_no=1,
            trigger_seq=10,
        )
    )
    # 一次完整动作尝试：应用层 intent/outcome 成对。
    sink.emit(
        make_record(
            AuditKind.SUBMISSION_INTENT,
            {"action_key": "discard:1w", "based_on_authoritative_seq": 10},
            stage_attempt_id="st-1",
            game_id="G1",
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
            stage_attempt_id="st-1",
            game_id="G1",
            round_no=1,
            trigger_seq=10,
            decision_id="d1",
            attempt_no=1,
            wall_time_unix_ms=1100,
        )
    )
    # 双层终局：应用层（带 stage_attempt_id）与适配器（不带）。
    sink.emit(
        make_record(
            AuditKind.GAME_FINISHED,
            {"final_scores": [8, 4, 0, -2], "authoritative_seq": 42},
            stage_attempt_id="st-1",
            game_id="G1",
        )
    )
    adapter_scores = [7, 4, 0, -1] if conflicting_scores else [8, 4, 0, -2]
    sink.emit(
        make_record(
            AuditKind.GAME_FINISHED,
            {"final_scores": adapter_scores, "seq": 42},
            stage_attempt_id=None,
            game_id="G1",
        )
    )
    sink.emit(
        make_record(
            AuditKind.PARTICIPANT_FINISHED,
            {"reason": "tournament_finished", "detail": "赛事进入终态 finished"},
        )
    )
    summary = await sink.aclose(timeout_seconds=5.0)
    assert summary.audit_degraded is False


async def test_adapter_layer_without_stage_attempt_is_not_mixing(tmp_path):
    """缺失 stage_attempt_id 与非空共存是双层记录常态，不得判为混用。"""

    await _build_layer_run(tmp_path)
    run_dir = tmp_path / "runs" / "run-layers"
    report = validate_run(run_dir)

    violation_codes = {f["code"] for f in report["findings"] if f["severity"] == "violation"}
    assert report["audit_complete"] is True
    assert "stage_attempt_mixing" not in violation_codes
    # 终局分数一致：进入按身份的汇总，供测试房间入口汇总最终分。
    assert report["coverage"]["final_scores_by_game"] == {"P1/G1": [8, 4, 0, -2]}


async def test_two_distinct_stage_attempts_still_flagged(tmp_path):
    """同一局出现两个不同非空 stage_attempt_id 仍是不变量违规。"""

    await _build_layer_run(tmp_path)
    games_path = tmp_path / "runs" / "run-layers" / "participants" / "P1" / "games" / "G1.jsonl"
    stray = {
        "schema_version": 1,
        "kind": "authoritative_state",
        "context": {
            "run_id": "run-layers",
            "tournament_id": "t-1",
            "participant_id": "P1",
            "stage_attempt_id": "st-2",
            "game_id": "G1",
            "round_no": 1,
            "trigger_seq": 11,
        },
        "wall_time_unix_ms": 5,
        "monotonic_ns": 5,
        "payload": {"authoritative_seq": 11},
    }
    with games_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(stray, ensure_ascii=False) + "\n")

    report = validate_run(tmp_path / "runs" / "run-layers")
    violation_codes = {f["code"] for f in report["findings"] if f["severity"] == "violation"}
    assert report["audit_complete"] is False
    assert "stage_attempt_mixing" in violation_codes


async def test_conflicting_double_layer_scores_only_warn(tmp_path):
    """双层终局分数不一致：warning 级报告，不进入分数汇总。"""

    await _build_layer_run(tmp_path, conflicting_scores=True)
    report = validate_run(tmp_path / "runs" / "run-layers")

    warning_codes = {f["code"] for f in report["findings"] if f["severity"] == "warning"}
    assert "game_finished_score_mismatch" in warning_codes
    assert report["audit_complete"] is True  # warning 不改变完整判定
    assert report["coverage"]["final_scores_by_game"] == {}


async def test_rejected_no_refresh_joins_rejected_family(tmp_path):
    """2026-09-04 契约收口：rejected_no_refresh 计入显式拒绝族统计。"""

    sink = JsonlAuditSink(tmp_path, "run-no-refresh")
    sink.emit(make_record(AuditKind.RUN_MANIFEST, {"mode": "test_room"}))
    sink.emit(make_record(AuditKind.LIFECYCLE_CHANGED, {"event": "status_changed", "from": None, "to": "running"}))
    for decision_id, outcome, extra in (
        ("d1", "SubmitAccepted", {}),
        ("d2", "SubmitRejectedRetryable", {"official_code": "409"}),
        # 应用层生产形态：封闭结果类名 + 刷新失败时的本地序号。
        ("d3", "SubmitRejectedNoRefresh", {"official_code": "429", "latest_local_seq": 10, "reason": "official_rate_limited"}),
        # 记录器规范词表形态同样归并。
        ("d4", "rejected_no_refresh", {}),
    ):
        common = {
            "participant_id": "P1",
            "game_id": "G1",
            "round_no": 1,
            "trigger_seq": 10,
            "decision_id": decision_id,
            "attempt_no": 1,
        }
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
                wall_time_unix_ms=1100,
                **common,
            )
        )
    sink.emit(
        make_record(
            AuditKind.PARTICIPANT_FINISHED,
            {"reason": "tournament_finished", "detail": "赛事进入终态 finished"},
        )
    )
    summary = await sink.aclose(timeout_seconds=5.0)
    assert summary.audit_degraded is False

    report = validate_run(tmp_path / "runs" / "run-no-refresh")
    submissions = report["submissions"]
    assert submissions["outcome_histogram"]["rejected_no_refresh"] == 2
    assert submissions["rejected_total"] == 3  # retryable + no_refresh × 2
    assert report["audit_complete"] is True


async def test_three_or_more_same_layer_records_flagged_as_duplicate(tmp_path):
    """双层各记一次不报告；三条及以上同层重复才识别（接口协议第 7.1 节）。"""

    sink = JsonlAuditSink(tmp_path, "run-dups")
    sink.emit(make_record(AuditKind.RUN_MANIFEST, {"mode": "test_room"}))
    sink.emit(make_record(AuditKind.LIFECYCLE_CHANGED, {"event": "status_changed", "from": None, "to": "running"}))
    common = {
        "participant_id": "P1",
        "game_id": "G1",
        "round_no": 1,
        "trigger_seq": 10,
        "decision_id": "d1",
        "attempt_no": 1,
    }
    sink.emit(
        make_record(
            AuditKind.SUBMISSION_INTENT,
            {"action_key": "discard:1w", "based_on_authoritative_seq": 10},
            wall_time_unix_ms=1000,
            **common,
        )
    )
    for _ in range(3):
        sink.emit(
            make_record(
                AuditKind.SUBMISSION_OUTCOME,
                {"outcome": "accepted"},
                wall_time_unix_ms=1100,
                **common,
            )
        )
    sink.emit(
        make_record(
            AuditKind.PARTICIPANT_FINISHED,
            {"reason": "tournament_finished", "detail": "赛事进入终态 finished"},
        )
    )
    summary = await sink.aclose(timeout_seconds=5.0)
    assert summary.audit_degraded is False

    report = validate_run(tmp_path / "runs" / "run-dups")
    warning_codes = {f["code"] for f in report["findings"] if f["severity"] == "warning"}
    assert "duplicate_outcome" in warning_codes
    assert report["audit_complete"] is True  # 重复只提示，不改变完整判定


if __name__ == "__main__":
    pytest.main([__file__])
