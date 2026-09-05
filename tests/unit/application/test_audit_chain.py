"""审计链验收：信封顺序、关联键完整、降级标记与脱敏。"""

from __future__ import annotations

import asyncio

import pytest

from fakes import (
    FakeGameSession,
    FakeTournamentSession,
    InMemoryAuditSink,
    build_runtime,
    make_bootstrap,
    make_observation,
    make_refreshed_window,
    make_snapshot,
    make_window,
    wait_for_condition,
)
from hangma_bot.application.contracts import (
    ParticipantTerminal,
    ParticipantTerminalReason,
    SubmitAccepted,
    SubmitRejectedRetryable,
    TournamentStatus,
)

pytestmark = pytest.mark.asyncio


def _records_of(sink, kind_value: str):
    return [record for record in sink.records if record.kind.value == kind_value]


async def _drive(runtime, session, condition, grants: int = 1):
    """后台运行 runtime，条件满足后再放行终态更新，消除调度竞态。"""

    run_task = asyncio.create_task(runtime.run())
    await wait_for_condition(condition)
    session.grant_updates(grants)
    return await run_task


async def test_manifest_and_participant_finished_bracket_run():
    """运行以 RUN_MANIFEST 开始、PARTICIPANT_FINISHED 结束、producer_summary 收尾。

    audit-plus-v1（2026-09-05）：关闭前 AuditTrail 发射一次
    LIFECYCLE_CHANGED(area=audit, event=producer_summary) 作为关闭证据，
    因此最后一条记录是 lifecycle_changed 而非 participant_finished。
    """

    game = FakeGameSession(items=[make_window(make_observation(game_id="g1", seq=10))])
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=["g1"])),
        updates=[make_snapshot(TournamentStatus.FINISHED)],
        game_factory=lambda gid: game,
    )
    runtime, sink, *_ = build_runtime(session=session)
    terminal = await _drive(runtime, session, lambda: game.drained)

    assert terminal.reason.value == "tournament_finished"
    kinds = [kind.value for kind in sink.kinds()]
    assert kinds[0] == "run_manifest"
    assert kinds[-1] == "lifecycle_changed"
    assert kinds[-2] == "participant_finished"
    assert sink.records[-1].payload["event"] == "producer_summary"
    assert "authoritative_state" in kinds


async def test_intent_outcome_pairs_fully_linked():
    """每个 POST 的 intent/outcome 用 decision_id+attempt_no 无歧义配对。"""

    base_window = make_window(make_observation(game_id="g1", seq=10))

    def handler(attempt):
        if len(game.submitted) == 1:
            refreshed = make_refreshed_window(base_window, seq=11)
            return SubmitRejectedRetryable(
                official_code="CONFLICT",
                rejected_action_key=attempt.action_key,
                refreshed_window=refreshed,
            )
        return SubmitAccepted(official_code="200", authoritative_seq=12)

    game = FakeGameSession(
        items=[make_window(make_observation(game_id="g1", seq=10))],
        submit_handler=handler,
    )
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=["g1"])),
        updates=[make_snapshot(TournamentStatus.FINISHED)],
        game_factory=lambda gid: game,
    )
    runtime, sink, *_ = build_runtime(session=session)
    terminal = await _drive(runtime, session, lambda: game.drained)

    intents = _records_of(sink, "submission_intent")
    outcomes = _records_of(sink, "submission_outcome")
    assert len(intents) == 2 and len(outcomes) == 2
    for intent, outcome in zip(intents, outcomes):
        assert intent.context.decision_id == outcome.context.decision_id
        assert intent.context.attempt_no == outcome.context.attempt_no
        for field in (
            "run_id",
            "tournament_id",
            "participant_id",
            "stage_attempt_id",
            "game_id",
            "round_no",
            "trigger_seq",
            "decision_id",
            "attempt_no",
        ):
            assert getattr(intent.context, field) is not None
    # 同一窗口的两次尝试共享 decision_id，但 attempt_no 递增。
    assert intents[0].context.decision_id == intents[1].context.decision_id
    assert [i.context.attempt_no for i in intents] == [1, 2]

    # 顺序约束：intent1 < outcome1 < intent2 < outcome2。
    positions = {id(record): index for index, record in enumerate(sink.records)}
    assert positions[id(intents[0])] < positions[id(outcomes[0])]
    assert positions[id(outcomes[0])] < positions[id(intents[1])]
    assert positions[id(intents[1])] < positions[id(outcomes[1])]


async def test_sink_exception_never_blocks_submission():
    """审计写入失败不阻塞动作，但运行被标记 audit_degraded。"""

    sink = InMemoryAuditSink(fail=True)
    game = FakeGameSession(items=[make_window(make_observation(game_id="g1", seq=10))])
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=["g1"])),
        updates=[make_snapshot(TournamentStatus.FINISHED)],
        game_factory=lambda gid: game,
    )
    runtime, _sink, *_ = build_runtime(session=session, sink=sink)
    terminal = await _drive(runtime, session, lambda: game.drained)

    assert len(game.submitted) == 1
    assert terminal.reason.value == "tournament_finished"
    assert runtime.audit_degraded is True
    assert sink.closed is True


async def test_degraded_receipt_marks_runtime():
    """回执声明降级同样置位 audit_degraded。"""

    sink = InMemoryAuditSink(degraded=True)
    game = FakeGameSession(items=[make_window(make_observation(game_id="g1", seq=10))])
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=["g1"])),
        updates=[make_snapshot(TournamentStatus.FINISHED)],
        game_factory=lambda gid: game,
    )
    runtime, _sink, *_ = build_runtime(session=session, sink=sink)
    terminal = await _drive(runtime, session, lambda: game.drained)

    assert runtime.audit_degraded is True
    assert runtime.last_audit_summary.audit_degraded is True


async def test_no_token_material_in_audit_payloads():
    """信封与载荷不得出现 Token/Authorization 痕迹。"""

    game = FakeGameSession(items=[make_window(make_observation(game_id="g1", seq=10))])
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=["g1"])),
        updates=[make_snapshot(TournamentStatus.FINISHED)],
        game_factory=lambda gid: game,
    )
    runtime, sink, *_ = build_runtime(session=session)
    terminal = await _drive(runtime, session, lambda: game.drained)

    def _scan(value):
        if isinstance(value, dict):
            for item in value.values():
                yield from _scan(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                yield from _scan(item)
        elif isinstance(value, str):
            yield value

    for record in sink.records:
        for text in _scan(record.payload):
            low = text.lower()
            assert "token" not in low
            assert "authorization" not in low
            assert "bearer" not in low


async def test_lifecycle_records_stage_attempt_and_game_events():
    """stage_attempt/game 生命周期事件进入审计链。"""

    game = FakeGameSession(items=[make_window(make_observation(game_id="g1", seq=10))])
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=["g1"])),
        updates=[make_snapshot(TournamentStatus.FINISHED)],
        game_factory=lambda gid: game,
    )
    runtime, sink, *_ = build_runtime(session=session)
    terminal = await _drive(runtime, session, lambda: game.drained)

    events = sink.lifecycle_events()
    assert "stage_attempt_started" in events
    assert "game_opened" in events
    finished = _records_of(sink, "participant_finished")
    assert finished[0].payload["reason"] == "tournament_finished"

async def test_early_exit_paths_close_sink_and_audit():
    """初始化异常/终态/目标错配都关闭 sink、写终态记录、关会话。"""

    class InitRaises(FakeTournamentSession):
        async def initialize(self, target):
            raise RuntimeError("连接失败")

    failing = InitRaises(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.REGISTERING))
    )
    sink1 = InMemoryAuditSink()
    runtime1, _s1, *_ = build_runtime(session=failing, sink=sink1)
    terminal1 = await runtime1.run()
    assert terminal1.reason.value == "fatal_protocol_error"
    assert failing.closed is True
    assert sink1.closed is True
    assert any(
        record.kind.value == "participant_finished" for record in sink1.records
    )

    terminal_init = ParticipantTerminal(
        reason=ParticipantTerminalReason.AUTHENTICATION_FAILED,
        last_snapshot=None,
        detail="401",
    )
    rejected = FakeTournamentSession(bootstrap=terminal_init)
    sink2 = InMemoryAuditSink()
    runtime2, _s2, *_ = build_runtime(session=rejected, sink=sink2)
    terminal2 = await runtime2.run()
    assert terminal2 is terminal_init
    assert sink2.closed is True
    kinds2 = [kind.value for kind in sink2.kinds()]
    assert "run_manifest" in kinds2  # 直接终态早退同样生成 manifest
    assert any(
        record.kind.value == "participant_finished" for record in sink2.records
    )

    mismatched = FakeTournamentSession(
        bootstrap=make_bootstrap(
            make_snapshot(TournamentStatus.REGISTERING), tournament_id="other"
        )
    )
    sink3 = InMemoryAuditSink()
    runtime3, _s3, *_ = build_runtime(session=mismatched, sink=sink3)
    terminal3 = await runtime3.run()
    assert terminal3.reason is ParticipantTerminalReason.TARGET_MISMATCH
    assert sink3.closed is True
    kinds3 = [k.value for k in sink3.kinds()]
    assert "run_manifest" in kinds3
    assert "participant_finished" in kinds3


async def test_token_scan_covers_exception_paths():
    """异常文本进入审计前经过截断与凭证脱敏。"""

    secret_leak = RuntimeError(
        "GET https://api.example.com/me?token=deadbeefcafebabe0123456789abcdef failed"
    )
    game = FakeGameSession(
        items=[make_window(make_observation(game_id="g1", seq=10))],
        submit_handler=lambda attempt: secret_leak,
    )
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=["g1"])),
        updates=[make_snapshot(TournamentStatus.FINISHED)],
        game_factory=lambda gid: game,
    )
    runtime, sink, *_ = build_runtime(session=session)
    terminal = await _drive(
        runtime, session, lambda: game.drained
    )
    assert len(game.submitted) == 1

    def _scan(value):
        if isinstance(value, dict):
            for item in value.values():
                yield from _scan(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                yield from _scan(item)
        elif isinstance(value, str):
            yield value

    for record in sink.records:
        for text in _scan(record.payload):
            low = text.lower()
            # 凭证值必须被替换为占位符；键名保留是可接受的。
            assert "deadbeef" not in low
            assert "bearer " not in low
            if "token=" in low:
                assert "token=<redacted>" in low

