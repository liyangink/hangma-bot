"""通过完整参赛者入口复现：活跃列表先退场，场次终局稍后到达。"""

from __future__ import annotations

import asyncio

import pytest

from fakes import (
    FakeGameSession,
    FakeTournamentSession,
    InMemoryAuditSink,
    build_runtime,
    make_bootstrap,
    make_config,
    make_observation,
    make_snapshot,
    make_window,
    wait_for_condition,
)
from hangma_bot.application.contracts import (
    AuditKind, GameFailed, GameFinished, ParticipantTerminal, ParticipantTerminalReason,
    TournamentStatus,
    SubmissionCancelledBeforeSend,
)
from hangma_bot.application.deadline import ManualClock


class QueuedGameSession(FakeGameSession):
    """条目由测试显式放行；记录消费者取消，模拟两个端点的到达顺序。"""

    def __init__(self):
        super().__init__()
        self.incoming = asyncio.Queue()
        self.reading = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.read_calls = 0

    async def next_item(self):
        self.read_calls += 1
        self.reading.set()
        try:
            return await self.incoming.get()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise


class ControlledSleep:
    """使用可推进单调时钟触发等待，不消耗真实秒数。"""

    def __init__(self, clock):
        self.clock = clock
        self.pending = []

    async def __call__(self, seconds):
        event = asyncio.Event()
        entry = (self.clock.now() + seconds, event)
        self.pending.append(entry)
        try:
            await event.wait()
        finally:
            self.pending.remove(entry)

    def advance(self, seconds):
        self.clock.advance(seconds)
        for deadline, event in self.pending:
            if deadline <= self.clock.now():
                event.set()


def _events(sink, event):
    return [r for r in sink.records if r.kind is AuditKind.LIFECYCLE_CHANGED
            and r.payload.get("event") == event]


async def _cancel(task):
    if not task.done():
        task.cancel()
    await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("end_status", [TournamentStatus.RUNNING, TournamentStatus.FINISHED])
async def test_late_terminal_is_collected_without_acting_after_removal(end_status):
    """复现 ef9b：先退出 active_games，再收到旧窗口和 seq1739 的终局。"""

    game = QueuedGameSession()
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=["g1"])),
        updates=[
            make_snapshot(end_status, my_games=["g1"], active_games=[]),
            make_snapshot(TournamentStatus.FINISHED),
        ],
        game_factory=lambda gid: game,
    )
    runtime, sink, *_ = build_runtime(session=session)
    task = asyncio.create_task(runtime.run())
    try:
        await game.reading.wait()
        session.grant_updates(1)
        await game.cancelled.wait()
        # 退场后的可行动快照也只能用于同步，不能继续触发策略或提交。
        game.incoming.put_nowait(make_window(make_observation(game_id="g1")))
        game.incoming.put_nowait(GameFinished("g1", (-24, 58, -17, -17), 1739))
        await wait_for_condition(lambda: game.closed)
        session.grant_updates(1)
        await task
        finals = [r for r in sink.records if r.kind is AuditKind.GAME_FINISHED]
        assert [r.payload["final_scores"] for r in finals] == [[-24, 58, -17, -17]]
        assert game.submitted == []
        assert session.closed
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_timeout_is_explicit_and_other_game_keeps_acting():
    clock = ManualClock()
    sleep = ControlledSleep(clock)
    games = {g: QueuedGameSession() for g in ("g1", "g2")}
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=list(games))),
        updates=[make_snapshot(TournamentStatus.RUNNING, my_games=list(games), active_games=["g2"]),
                 make_snapshot(TournamentStatus.FINISHED)],
        game_factory=games.__getitem__,
    )
    runtime, sink, *_ = build_runtime(session=session, clock=clock, sleep=sleep)
    task = asyncio.create_task(runtime.run())
    try:
        await games["g1"].reading.wait()
        session.grant_updates(1)
        await wait_for_condition(lambda: len(sleep.pending) == 1)
        games["g2"].incoming.put_nowait(make_window(make_observation(game_id="g2")))
        await wait_for_condition(lambda: len(games["g2"].submitted) == 1)
        assert not games["g1"].closed
        sleep.advance(5)
        await wait_for_condition(lambda: games["g1"].closed)
        closed = _events(sink, "game_closed")[0]
        assert closed.payload["terminal_status"] == "missing"
        assert closed.payload["terminal_detail"] == "finalization_timeout"
        assert games["g1"].submitted == []
        games["g2"].incoming.put_nowait(GameFinished("g2", (3, -1, -1, -1), 1740))
        await wait_for_condition(lambda: games["g2"].closed)
        session.grant_updates(1)
        await task
        assert sleep.pending == []
    finally:
        await _cancel(task)


@pytest.mark.asyncio
async def test_shutdown_collects_games_in_parallel_without_renewing_old_deadline():
    clock = ManualClock()
    sleep = ControlledSleep(clock)
    games = {g: QueuedGameSession() for g in ("g1", "g2", "g3", "g4")}
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=list(games)),
                                 config=make_config(max_games=4)),
        updates=[make_snapshot(TournamentStatus.RUNNING, my_games=list(games), active_games=["g2", "g3", "g4"]),
                 make_snapshot(TournamentStatus.FINISHED)],
        game_factory=games.__getitem__,
    )
    runtime, sink, *_ = build_runtime(session=session, clock=clock, sleep=sleep)
    task = asyncio.create_task(runtime.run())
    try:
        await games["g1"].reading.wait()
        session.grant_updates(1)
        await wait_for_condition(lambda: len(sleep.pending) == 1)
        sleep.advance(2)
        session.grant_updates(1)
        await wait_for_condition(lambda: len(sleep.pending) == 4)
        sleep.advance(3)
        await wait_for_condition(lambda: games["g1"].closed)
        assert not any(g.closed for key, g in games.items() if key != "g1")
        sleep.advance(2)
        await task
        assert all(g.closed for g in games.values())
        assert len(_events(sink, "game_finalization_started")) == 4
        assert all(g.submitted == [] for g in games.values())
        assert sleep.pending == []
    finally:
        await _cancel(task)


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["stage_crashed", "authentication_failed", "tournament_void"])
async def test_hard_stop_aborts_already_running_finalization(reason):
    clock = ManualClock()
    sleep = ControlledSleep(clock)
    game = QueuedGameSession()
    if reason == "stage_crashed":
        ending = make_snapshot(TournamentStatus.RUNNING, my_games=["g1"], active_games=[], crashed=True)
    else:
        ending = ParticipantTerminal(ParticipantTerminalReason(reason), None, "测试终止")
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=["g1"])),
        updates=[make_snapshot(TournamentStatus.RUNNING, my_games=["g1"], active_games=[]),
                 ending, make_snapshot(TournamentStatus.FINISHED)],
        game_factory=lambda gid: game,
    )
    runtime, sink, *_ = build_runtime(session=session, clock=clock, sleep=sleep)
    task = asyncio.create_task(runtime.run())
    try:
        await game.reading.wait()
        session.grant_updates(1)
        await wait_for_condition(lambda: len(sleep.pending) == 1)
        session.grant_updates(1)
        await wait_for_condition(lambda: game.closed)
        session.grant_updates(1)
        await task
        assert game.read_calls == 2  # 原消费者一次，收尾一次；取消后不再读。
        assert not [r for r in sink.records if r.kind is AuditKind.GAME_FINISHED]
        assert _events(sink, "game_closed")[0].payload["terminal_detail"] == reason
        assert sleep.pending == []
    finally:
        await _cancel(task)


@pytest.mark.asyncio
@pytest.mark.parametrize("crash_new_stage", [False, True])
async def test_late_result_keeps_original_stage_attempt(crash_new_stage):
    clock = ManualClock()
    sleep = ControlledSleep(clock)
    games = {g: QueuedGameSession() for g in ("g1", "g2")}
    updates = [make_snapshot(TournamentStatus.RUNNING, stage_no=2, my_games=list(games), active_games=["g2"])]
    if crash_new_stage:
        updates.append(make_snapshot(TournamentStatus.RUNNING, stage_no=2, active_games=[], crashed=True))
    updates.append(make_snapshot(TournamentStatus.FINISHED))
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, stage_no=1, my_games=["g1"])),
        updates=updates,
        game_factory=games.__getitem__,
    )
    runtime, sink, *_ = build_runtime(session=session, clock=clock, sleep=sleep)
    task = asyncio.create_task(runtime.run())
    try:
        await games["g1"].reading.wait()
        session.grant_updates(1)
        await wait_for_condition(lambda: session.game_opens == ["g1", "g2"])
        if crash_new_stage:
            session.grant_updates(1)
            await wait_for_condition(lambda: games["g2"].closed)
            assert not games["g1"].closed  # 新阶段作废不能取消上一有效阶段的迟到结果。
        for gid, game in games.items():
            if game.closed:
                continue
            game.incoming.put_nowait(GameFinished(gid, (3, -1, -1, -1), 1739))
        await wait_for_condition(lambda: all(g.closed for g in games.values()))
        session.grant_updates(1)
        await task
        starts = {r.context.game_id: r.context.stage_attempt_id for r in _events(sink, "game_opened")}
        finals = {r.context.game_id: r.context.stage_attempt_id for r in sink.records if r.kind is AuditKind.GAME_FINISHED}
        assert starts["g1"] != starts["g2"]
        assert finals == ({"g1": starts["g1"]} if crash_new_stage else starts)
    finally:
        await _cancel(task)


@pytest.mark.asyncio
@pytest.mark.parametrize("recoverable", [True, False])
async def test_finalization_retries_only_recoverable_read_failures(recoverable):
    clock = ManualClock()
    sleep = ControlledSleep(clock)
    game = QueuedGameSession()
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=["g1"])),
        updates=[make_snapshot(TournamentStatus.FINISHED)], game_factory=lambda gid: game,
    )
    runtime, sink, *_ = build_runtime(session=session, clock=clock, sleep=sleep)
    task = asyncio.create_task(runtime.run())
    try:
        await game.reading.wait()
        session.grant_updates(1)
        await game.cancelled.wait()
        game.incoming.put_nowait(GameFailed("g1", recoverable, "read_failure"))
        game.incoming.put_nowait(GameFinished("g1", (3, -1, -1, -1), 1739))
        if recoverable:
            await wait_for_condition(lambda: len(sleep.pending) == 2)
            sleep.advance(0.5)
        await task
        finals = [r for r in sink.records if r.kind is AuditKind.GAME_FINISHED]
        assert len(finals) == int(recoverable)
        assert session.game_opens == ["g1"]
        assert game.submitted == []
        assert sleep.pending == []
    finally:
        await _cancel(task)


@pytest.mark.asyncio
@pytest.mark.parametrize("before_send", [False, True])
async def test_external_cancel_classifies_post_and_collects_terminal(before_send):
    class InflightGame(QueuedGameSession):
        def __init__(self):
            super().__init__()
            self.submitting = asyncio.Event()
            self.submit_cancelled = asyncio.Event()

        async def submit(self, attempt):
            self.submitted.append(attempt)
            self.submitting.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                self.submit_cancelled.set()
                if before_send:
                    raise SubmissionCancelledBeforeSend() from None
                raise

    clock = ManualClock()
    sleep = ControlledSleep(clock)
    game = InflightGame()
    game.incoming.put_nowait(make_window(make_observation(game_id="g1")))
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=["g1"])),
        game_factory=lambda gid: game,
    )
    runtime, sink, *_ = build_runtime(session=session, clock=clock, sleep=sleep)
    task = asyncio.create_task(runtime.run())
    try:
        await game.submitting.wait()
        task.cancel()
        await game.submit_cancelled.wait()
        game.incoming.put_nowait(GameFinished("g1", (3, -1, -1, -1), 1739))
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(game.submitted) == 1
        outcomes = [r for r in sink.records if r.kind is AuditKind.SUBMISSION_OUTCOME]
        assert len(outcomes) == 1
        assert outcomes[0].payload["outcome"] == ("SubmitNotSent" if before_send else "SubmitAmbiguous")
        assert outcomes[0].payload["reason"] == ("cancelled_before_send" if before_send else "cancelled_in_flight")
        kinds = [r.kind for r in sink.records]
        assert kinds.index(AuditKind.GAME_FINISHED) < kinds.index(AuditKind.PARTICIPANT_FINISHED)
        assert game.closed and session.closed and sleep.pending == []
    finally:
        await _cancel(task)


@pytest.mark.asyncio
async def test_real_http_session_resumes_after_cancel_and_records_live_terminal():
    """真实传输、同步器、终局投影接线；只有网络后端使用内存响应。"""
    import json
    from pathlib import Path
    import httpx
    from hangma_bot.adapters.official.game import OfficialGameSession
    from hangma_bot.adapters.official.scheduler import RequestScheduler
    from hangma_bot.adapters.official.transport import OfficialTransport, TransportConfig
    from hangma_bot.application.contracts import AuditContext

    fixture = Path(__file__).resolve().parents[2] / "fixtures/official/v20/graceful-finalization/finished-b0.json"
    finished = json.loads(fixture.read_text())
    game_id = finished["snapshot"]["game_id"]
    entered, cancelled = asyncio.Event(), asyncio.Event()
    seen = []
    clock = ManualClock()
    sink = InMemoryAuditSink()
    sleep = ControlledSleep(clock)

    async def handler(request):
        seen.append((request.method, request.url.path))
        if len(seen) == 1:
            entered.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                cancelled.set()
                raise
        return httpx.Response(200, json=finished)

    async def advance_sleep(seconds):
        clock.advance(seconds)
        await asyncio.sleep(0)

    transport = OfficialTransport(
        "graceful-test-dummy", TransportConfig(base_url="https://diagnostic.invalid", insecure_hosts=frozenset()),
        transport_handler=httpx.MockTransport(handler),
    )
    scheduler = RequestScheduler(clock=clock.now, sleep=advance_sleep).for_game(game_id, max_games=4)
    game = OfficialGameSession(
        game_id=game_id, transport=transport, scheduler=scheduler, timing=make_config().timing,
        monotonic_clock=clock.now, wall_clock_unix_ms=clock.unix_ms, audit=sink,
        audit_context=lambda: AuditContext(run_id=runtime.run_id, tournament_id="t1", participant_id="p1"),
        retry_sleep=advance_sleep,
    )
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=[game_id])),
        updates=[make_snapshot(TournamentStatus.FINISHED)], game_factory=lambda gid: game,
    )
    runtime, *_ = build_runtime(session=session, sink=sink, clock=clock, sleep=sleep)
    task = asyncio.create_task(runtime.run())
    try:
        await entered.wait()
        session.grant_updates(1)
        await cancelled.wait()
        await asyncio.wait_for(task, 1)
        assert seen == [("GET", f"/api/games/{game_id}/state")] * 2
        finals = [r for r in sink.records if r.kind is AuditKind.GAME_FINISHED]
        assert len(finals) == 2  # 适配器、应用层各记一次相同权威事实。
        assert all(r.payload["final_scores"] == [-24, 58, -17, -17] for r in finals)
        assert _events(sink, "game_closed")[0].payload["terminal_status"] == "finished"
        raw = [r for r in sink.records if r.payload.get("source") == "state_response"]
        assert len(raw) == 2  # 首次 GET 取消仍留审计，第二次保留真实终局正文。
        assert game.closed and sleep.pending == []
    finally:
        await _cancel(task)
        await game.aclose("test_cleanup")
        await transport.aclose()
