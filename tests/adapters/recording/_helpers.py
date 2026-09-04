"""测试共用工厂：只通过公开契约类型构造审计信封。"""

from __future__ import annotations

from hangma_bot.application.contracts import AuditContext, AuditKind, AuditRecord


def make_record(
    kind: AuditKind,
    payload: dict,
    *,
    run_id: str = "run-1",
    tournament_id: str = "t-1",
    participant_id: str = "P1",
    stage_attempt_id: str | None = "st-1",
    game_id: str | None = None,
    round_no: int | None = None,
    trigger_seq: int | None = None,
    decision_id: str | None = None,
    attempt_no: int | None = None,
    wall_time_unix_ms: int = 1000,
    monotonic_ns: int = 1,
    schema_version: int = 1,
) -> AuditRecord:
    """按默认四身份之一构造一条审计记录；时间字段固定保证时延可断言。"""

    return AuditRecord(
        schema_version=schema_version,
        kind=kind,
        context=AuditContext(
            run_id=run_id,
            tournament_id=tournament_id,
            participant_id=participant_id,
            stage_attempt_id=stage_attempt_id,
            game_id=game_id,
            round_no=round_no,
            trigger_seq=trigger_seq,
            decision_id=decision_id,
            attempt_no=attempt_no,
        ),
        wall_time_unix_ms=wall_time_unix_ms,
        monotonic_ns=monotonic_ns,
        payload=payload,
    )
