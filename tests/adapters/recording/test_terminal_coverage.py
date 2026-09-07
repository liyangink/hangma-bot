"""终局覆盖必须和结构完整性分开核验，旧日志的缺失不能被补造。"""

import pytest

from hangma_bot.adapters.recording import JsonlAuditSink, validate_run
from hangma_bot.application.contracts import AuditKind
from ._helpers import make_record


@pytest.mark.asyncio
@pytest.mark.parametrize("final", [None, [-24, 58, -17, -17]])
async def test_finished_participant_requires_terminal_for_each_opened_game(tmp_path, final):
    sink = JsonlAuditSink(tmp_path, "run-1")
    sink.emit(make_record(AuditKind.RUN_MANIFEST, {"run_id": "run-1"}))
    sink.emit(make_record(AuditKind.LIFECYCLE_CHANGED, {"event": "game_opened"}, game_id="G1"))
    if final is not None:
        sink.emit(make_record(AuditKind.GAME_FINISHED, {"final_scores": final}, game_id="G1"))
    sink.emit(make_record(AuditKind.LIFECYCLE_CHANGED,
                         {"event": "game_closed", "reason": "removed_from_active_games"}, game_id="G1"))
    sink.emit(make_record(AuditKind.PARTICIPANT_FINISHED, {"reason": "tournament_finished"}))
    await sink.aclose(timeout_seconds=1)
    report = validate_run(sink.run_dir)
    assert report["audit_complete"] is (final is not None)
    missing = [f for f in report["findings"] if f["code"] == "missing_game_final_scores"]
    assert bool(missing) is (final is None)


@pytest.mark.asyncio
async def test_voided_attempt_has_explained_exit_instead_of_invented_scores(tmp_path):
    sink = JsonlAuditSink(tmp_path, "run-1")
    sink.emit(make_record(AuditKind.RUN_MANIFEST, {"run_id": "run-1"}))
    sink.emit(make_record(AuditKind.LIFECYCLE_CHANGED, {"event": "game_opened"}, game_id="G1"))
    sink.emit(make_record(AuditKind.LIFECYCLE_CHANGED,
                         {"event": "stage_attempt_voided", "stage_attempt_id": "st-1", "reason": "stage_crashed"}))
    sink.emit(make_record(AuditKind.LIFECYCLE_CHANGED,
                         {"event": "game_closed", "reason": "stage_crashed"}, game_id="G1"))
    sink.emit(make_record(AuditKind.PARTICIPANT_FINISHED, {"reason": "tournament_finished"}))
    await sink.aclose(timeout_seconds=1)
    report = validate_run(sink.run_dir)
    assert report["audit_complete"]
    assert report["coverage"]["final_scores_by_game"] == {}
    assert report["coverage"]["terminal_coverage"]["explained_exits"] == {"P1/G1": "stage_crashed"}


@pytest.mark.asyncio
async def test_explicit_finalization_timeout_is_incomplete_even_if_process_is_cancelled(tmp_path):
    sink = JsonlAuditSink(tmp_path, "run-1")
    sink.emit(make_record(AuditKind.RUN_MANIFEST, {"run_id": "run-1"}))
    sink.emit(make_record(AuditKind.LIFECYCLE_CHANGED, {"event": "game_opened"}, game_id="G1"))
    sink.emit(make_record(AuditKind.LIFECYCLE_CHANGED,
                         {"event": "game_closed", "reason": "supervisor_shutdown",
                          "terminal_status": "missing", "terminal_detail": "finalization_timeout"}, game_id="G1"))
    sink.emit(make_record(AuditKind.PARTICIPANT_FINISHED, {"reason": "cancelled"}))
    await sink.aclose(timeout_seconds=1)
    report = validate_run(sink.run_dir)
    assert not report["audit_complete"]
    assert report["coverage"]["terminal_coverage"]["missing_final_scores"] == ["P1/G1"]
