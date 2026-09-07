"""隔离与恢复验收：单场故障不扩散、有界重试、权威重开与轮询恢复。"""

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
    GameFailed,
    GameFinished,
    ParticipantTerminalReason,
    SubmitAccepted,
    SubmitFatal,
    TournamentStatus,
)

pytestmark = pytest.mark.asyncio


async def test_unrecoverable_game_failure_is_isolated():
    """单场不可恢复故障不影响其他场的窗口处理。"""

    games = {
        "g1": FakeGameSession(
            items=[GameFailed(game_id="g1", recoverable=False, reason="协议错误")]
        ),
        "g2": FakeGameSession(items=[make_window(make_observation(game_id="g2", seq=20))]),
    }
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=["g1", "g2"])),
        updates=[make_snapshot(TournamentStatus.FINISHED)],
        game_factory=lambda gid: games[gid],
    )
    runtime, sink, *_ = build_runtime(session=session)
    run_task = asyncio.create_task(runtime.run())
    await wait_for_condition(lambda: games["g2"].drained)
    session.grant_updates(1)
    terminal = await run_task

    assert terminal.reason.value == "tournament_finished"
    assert len(games["g2"].submitted) == 1  # g2 完成了动作窗口
    ended = [
        record.payload
        for record in sink.records
        if record.kind.value == "lifecycle_changed"
        and record.payload["event"] == "game_ended"
    ]
    assert any(item["game_id"] == "g1" and item["status"] == "unrecoverable_failure" for item in ended)


async def test_recoverable_game_failure_rediscovers_fresh_session():
    """可恢复故障关闭旧会话并按 active_games 权威重开新会话。"""

    first = FakeGameSession(
        items=[GameFailed(game_id="g1", recoverable=True, reason="seq 缺口")]
    )
    second = FakeGameSession(items=[make_window(make_observation(game_id="g1", seq=30))])
    queue = {"g1": [first, second]}
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=["g1"])),
        updates=[make_snapshot(TournamentStatus.RUNNING, stage_no=1, my_games=["g1"]), make_snapshot(TournamentStatus.FINISHED)],
        game_factory=lambda gid: queue[gid].pop(0),
    )
    session.grant_updates(1)  # 只放行第一条 RUNNING，先观察重开过程
    runtime, sink, *_ = build_runtime(session=session)

    # 用任务并发驱动 run，并在过程中断言重开完成。
    run_task = asyncio.create_task(runtime.run())
    await wait_for_condition(lambda: len(session.game_opens) >= 2)
    await wait_for_condition(lambda: len(second.submitted) >= 1)
    assert first.closed and first.close_reasons == ["task_ended"]
    session.grant_updates(1)  # 放行 FINISHED
    terminal = await run_task

    assert terminal.reason.value == "tournament_finished"
    assert session.game_opens == ["g1", "g1"]
    rediscover = [
        record.payload
        for record in sink.records
        if record.kind.value == "protocol_recovered"
        and record.payload.get("area") == "game_reconcile"
    ]
    assert any("权威重开" in item["reason"] for item in rediscover)


async def test_item_exception_backoff_then_rediscover_fresh_session():
    """next_item 连续异常按有界退避重试，耗尽后交回监督层用全新会话重开。"""

    failing = FakeGameSession(items=[RuntimeError("连接抖动")] * 4)
    finished = FakeGameSession(
        items=[GameFinished(game_id="g1", final_scores=(0, 0, 0, 0), authoritative_seq=30)]
    )
    healthy = FakeGameSession(items=[make_window(make_observation(game_id="g2", seq=20))])
    queue = {"g1": [failing, finished], "g2": [healthy]}
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=["g1", "g2"])),
        updates=[make_snapshot(TournamentStatus.FINISHED)],
        game_factory=lambda gid: queue[gid].pop(0),
    )
    runtime, sink, *_ = build_runtime(session=session)
    run_task = asyncio.create_task(runtime.run())

    def _g1_finished() -> bool:
        return any(
            record.kind.value == "lifecycle_changed"
            and record.payload.get("event") == "game_ended"
            and record.payload.get("game_id") == "g1"
            and record.payload.get("status") == "finished"
            for record in sink.records
        )

    await wait_for_condition(lambda: healthy.drained and _g1_finished())
    session.grant_updates(1)
    terminal = await run_task

    assert len(healthy.submitted) == 1
    assert session.game_opens == ["g1", "g2", "g1"]  # g1 用全新会话重开后终局
    session_recovered = [
        record.payload
        for record in sink.records
        if record.kind.value == "protocol_recovered"
        and record.payload.get("area") == "game_session"
    ]
    assert len(session_recovered) == 4  # 3 次退避 + 1 次交回重开


async def test_fatal_in_one_game_terminates_identity_and_closes_others():
    """一场 SubmitFatal 结束整个身份，其余场次也被回收。"""

    fatal_game = FakeGameSession(
        items=[make_window(make_observation(game_id="g1", seq=10))],
        submit_handler=lambda attempt: SubmitFatal(official_code=None, reason="协议级错误"),
    )
    other = FakeGameSession(items=[])
    games = {"g1": fatal_game, "g2": other}
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=["g1", "g2"])),
        game_factory=lambda gid: games[gid],
    )
    runtime, sink, *_ = build_runtime(session=session)
    terminal = await runtime.run()

    assert terminal.reason.value == "fatal_protocol_error"
    assert other.closed


async def test_poll_error_recovers_then_exhausts():
    """赛事轮询异常先有界恢复；持续失败转永久故障终态。"""

    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=[])),
        updates=[
            RuntimeError("GET 超时"),
            make_snapshot(TournamentStatus.RUNNING, stage_no=1, my_games=["g1"]),
        ],
        game_factory=lambda gid: FakeGameSession(items=[]),
    )
    session.grant_updates(2)
    runtime, sink, *_ = build_runtime(session=session)
    # 初始无场次：g1 能开场次即证明轮询错误已被有界恢复。
    run_task = asyncio.create_task(runtime.run())
    await wait_for_condition(lambda: len(session.game_opens) == 1)
    run_task.cancel()
    try:
        await run_task
    except asyncio.CancelledError:
        pass
    assert any(
        record.payload.get("area") == "tournament_poll"
        for record in sink.records
        if record.kind.value == "protocol_recovered"
    )

    exhausting = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=[])),
        updates=[RuntimeError("GET 5xx")] * 6,
    )
    exhausting.grant_updates(6)
    runtime2, sink2, *_ = build_runtime(session=exhausting)
    terminal2 = await runtime2.run()
    assert terminal2.reason.value == "fatal_protocol_error"


async def test_game_finished_recorded_with_scores():
    """场次终局进入审计并正常结束该场任务。"""

    finished_payload = GameFinished(
        game_id="g1", final_scores=(10, 0, -5, -5), authoritative_seq=42
    )
    game = FakeGameSession(
        items=[
            make_window(make_observation(game_id="g1", seq=10)),
            finished_payload,
        ]
    )
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=["g1"])),
        updates=[make_snapshot(TournamentStatus.FINISHED)],
        game_factory=lambda gid: game,
    )
    runtime, sink, *_ = build_runtime(session=session)
    run_task = asyncio.create_task(runtime.run())

    def _game_finished_audited() -> bool:
        return any(record.kind.value == "game_finished" for record in sink.records)

    await wait_for_condition(_game_finished_audited)
    session.grant_updates(1)
    terminal = await run_task

    assert terminal.reason.value == "tournament_finished"
    finished = [
        record
        for record in sink.records
        if record.kind.value == "game_finished"
    ]
    assert finished[0].payload["final_scores"] == [10, 0, -5, -5]
    assert finished[0].payload["authoritative_seq"] == 42

async def test_finished_game_not_reopened_before_authority_removal():
    """终局场次在权威列表移除前不重开（陈旧快照窗口）。"""

    finished_payload = GameFinished(
        game_id="g1", final_scores=(10, 0, -5, -5), authoritative_seq=42
    )
    game = FakeGameSession(
        items=[
            make_window(make_observation(game_id="g1", seq=10)),
            finished_payload,
        ]
    )
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(
            make_snapshot(TournamentStatus.RUNNING, my_games=["g1"], active_games=["g1"])
        ),
        updates=[make_snapshot(TournamentStatus.FINISHED)],
        game_factory=lambda gid: game,
    )
    runtime, sink, *_ = build_runtime(session=session)
    import asyncio

    from fakes import wait_for_condition

    run_task = asyncio.create_task(runtime.run())

    def _game_finished_audited() -> bool:
        return any(record.kind.value == "game_finished" for record in sink.records)

    await wait_for_condition(_game_finished_audited)
    for _ in range(20):  # 终局后若干事件循环步，不得出现第二次开场
        await asyncio.sleep(0)
    assert session.game_opens == ["g1"]
    session.grant_updates(1)
    terminal = await run_task
    assert terminal.reason.value == "tournament_finished"
    assert session.game_opens == ["g1"]


async def test_reopen_backoff_escalates_then_abandons():
    """同场持续可恢复故障：退避升级、预算耗尽后放弃而不是无限重开。"""

    def failing_factory(gid):
        return FakeGameSession(
            items=[GameFailed(game_id=gid, recoverable=True, reason="持续故障")],
        )

    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=["g1"])),
        updates=[make_snapshot(TournamentStatus.FINISHED)],
        game_factory=failing_factory,
    )
    runtime, sink, *_policy, _rules, _clock, _ids, sleep = build_runtime(session=session)
    import asyncio

    from fakes import wait_for_condition

    run_task = asyncio.create_task(runtime.run())

    def _abandoned() -> bool:
        return any(
            record.kind.value == "protocol_recovered"
            and "放弃该场" in str(record.payload.get("reason", ""))
            for record in sink.records
        )

    await wait_for_condition(_abandoned)
    session.grant_updates(1)
    terminal = await run_task

    assert terminal.reason.value == "tournament_finished"
    assert len(session.game_opens) == 6  # 首开 + 5 次重开（预算 5 次）
    assert sleep.delays == [0.5, 1.0, 2.0, 4.0, 8.0]  # 指数升级


async def test_poll_backoff_delays_next_request():
    """轮询退避必须真正阻塞下一次 next_update，而不是只挂一个唤醒。"""

    import asyncio

    release = asyncio.Event()
    delays = []

    async def barrier_sleep(seconds: float) -> None:
        delays.append(seconds)
        if not release.is_set():
            await release.wait()

    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=[])),
        updates=[RuntimeError("GET 超时"), make_snapshot(TournamentStatus.FINISHED)],
    )
    runtime, sink, *_ = build_runtime(session=session, sleep=barrier_sleep)
    run_task = asyncio.create_task(runtime.run())

    from fakes import wait_for_condition

    session.grant_updates(1)  # 触发第一次轮询异常
    await wait_for_condition(lambda: len(delays) >= 1)
    for _ in range(20):  # 门未释放：不得发起第二次轮询
        await asyncio.sleep(0)
    assert session.next_update_calls == 1

    release.set()
    await wait_for_condition(lambda: session.next_update_calls >= 2)
    session.grant_updates(1)  # 放行 FINISHED
    terminal = await run_task
    assert terminal.reason.value == "tournament_finished"


async def test_open_game_failure_isolated_per_game():
    """单场 open_game 异常不终止身份：其他场照常启动，故障场有界放弃。"""

    def factory(gid):
        if gid == "g1":
            raise RuntimeError("开场失败")
        return FakeGameSession(items=[make_window(make_observation(game_id="g2", seq=20))])

    session = FakeTournamentSession(
        bootstrap=make_bootstrap(
            make_snapshot(TournamentStatus.RUNNING, my_games=["g1", "g2"])
        ),
        updates=[make_snapshot(TournamentStatus.FINISHED)],
        game_factory=factory,
    )
    runtime, sink, *_ = build_runtime(session=session)
    import asyncio

    from fakes import wait_for_condition

    run_task = asyncio.create_task(runtime.run())
    await wait_for_condition(
        lambda: session.opened_games["g2"].drained
        and session.game_open_attempts.count("g1") >= 6
    )
    session.grant_updates(1)
    terminal = await run_task

    assert terminal.reason.value == "tournament_finished"
    assert session.game_opens == ["g2"]
    assert len(session.opened_games["g2"].submitted) == 1
    assert session.game_open_attempts.count("g1") == 6  # 首试 + 5 次退避


async def test_fatal_terminal_not_overwritten_by_same_batch_update():
    """身份级致命终态与赛事完赛更新同批到达时首写优先。"""

    import asyncio

    from fakes import make_target, InMemoryAuditSink, FakePolicy, FakeRules, SequencedIds, ManualClock, make_fake_sleep, FakeGameSession, FakeTournamentSession, make_bootstrap, make_snapshot, make_window, make_observation, wait_for_condition
    from hangma_bot.application.contracts import SubmitFatal, TournamentStatus
    from hangma_bot.application.participant_runtime import ParticipantRuntime

    class ReleaseOnFatalSession(FakeTournamentSession):
        """第一条 next_update 等到致命提交发生时同步返回完赛快照。"""

        def __init__(self, **kwargs) -> None:
            super().__init__(**kwargs)
            self._release = asyncio.Future()

        def release_finished(self) -> None:
            if not self._release.done():
                self._release.set_result(make_snapshot(TournamentStatus.FINISHED))

        async def next_update(self):
            self.next_update_calls += 1
            if self.next_update_calls == 1:
                return await self._release
            await asyncio.Future()

    fatal_game = FakeGameSession(
        items=[make_window(make_observation(game_id="g1", seq=10))],
        submit_handler=lambda attempt: SubmitFatal(
            official_code="401", reason="unauthorized"
        ),
    )
    session = ReleaseOnFatalSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=["g1"])),
        game_factory=lambda gid: fatal_game,
    )

    def handler(attempt):
        session.release_finished()  # 与致命结果同拍释放完赛更新
        return SubmitFatal(official_code="401", reason="unauthorized")

    fatal_game._handler = handler
    runtime, sink, *_ = build_runtime(session=session)
    run_task = asyncio.create_task(runtime.run())
    terminal = await run_task

    assert terminal.reason.value == "authentication_failed"  # 首写优先


async def test_cancel_flushes_audit_and_closes_sink():
    """外部取消：会话与审计 sink 都被关闭，终态记录尽力写入。"""

    game = FakeGameSession(items=[])  # 无条目：任务挂在长轮询上
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=["g1"])),
        game_factory=lambda gid: game,
    )
    runtime, sink, *_ = build_runtime(session=session)
    run_task = asyncio.create_task(runtime.run())

    from fakes import wait_for_condition

    await wait_for_condition(lambda: session.game_opens == ["g1"])
    run_task.cancel()
    try:
        await run_task
        raised = False
    except asyncio.CancelledError:
        raised = True
    assert raised
    assert session.closed is True
    assert sink.closed is True
    assert any(
        record.kind.value == "participant_finished" for record in sink.records
    )
    assert game.closed is True


async def test_two_games_concurrent_windows_no_starvation():
    """两场窗口同时在途：第一场等待第二场到达，证明无串行饥饿。"""

    from fakes import BarrierPolicy

    games = {
        "g1": FakeGameSession(items=[make_window(make_observation(game_id="g1", seq=10))]),
        "g2": FakeGameSession(items=[make_window(make_observation(game_id="g2", seq=20))]),
    }
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(
            make_snapshot(TournamentStatus.RUNNING, my_games=["g1", "g2"])
        ),
        updates=[make_snapshot(TournamentStatus.FINISHED)],
        game_factory=lambda gid: games[gid],
    )
    runtime, sink, *_ = build_runtime(session=session, policy=BarrierPolicy())
    import asyncio

    from fakes import wait_for_condition

    run_task = asyncio.create_task(runtime.run())
    # 两场都排干说明两窗口并发完成；若串行，第一个 choose 会永远等待。
    await wait_for_condition(
        lambda: games["g1"].drained and games["g2"].drained, limit=2000
    )
    session.grant_updates(1)
    terminal = await run_task

    assert terminal.reason.value == "tournament_finished"
    assert len(games["g1"].submitted) == 1
    assert len(games["g2"].submitted) == 1



async def test_crash_cancels_inflight_ready_accept_path():
    """crash 取消在途 ready（迟到 ACCEPTED 路径）：重赛立即重新到位。"""

    import asyncio

    from hangma_bot.application.contracts import OperationStatus, ReadyResult

    class ReadyGateSession(FakeTournamentSession):
        def __init__(self, **kwargs) -> None:
            super().__init__(**kwargs)
            self.gate = asyncio.Future()

        async def ready(self, expected_stage):
            self.ready_calls.append(expected_stage)
            if len(self.ready_calls) == 1:
                return await self.gate  # 挂起模拟在途请求，直到被 crash 取消
            return ReadyResult(status=OperationStatus.ACCEPTED)

    session = ReadyGateSession(
        bootstrap=make_bootstrap(
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=1, revision=1, qualified=True)
        ),
        updates=[
            make_snapshot(TournamentStatus.RUNNING, stage_no=1, revision=1, my_games=["g1"]),
            make_snapshot(
                TournamentStatus.RUNNING,
                stage_no=1,
                revision=1,
                crashed=True,
                my_games=["g1"],
                active_games=[],
            ),
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=1, revision=2, qualified=True),
            make_snapshot(TournamentStatus.RUNNING, stage_no=1, revision=2, my_games=["g2"]),
            make_snapshot(TournamentStatus.FINISHED),
        ],
        game_factory=lambda gid: FakeGameSession(items=[]),
    )
    runtime, sink, *_ = build_runtime(session=session)
    run_task = asyncio.create_task(runtime.run())

    from fakes import wait_for_condition

    await wait_for_condition(lambda: len(session.ready_calls) >= 1)
    session.grant_updates(2)  # RUNNING(g1) + crashed
    await wait_for_condition(lambda: "stage_attempt_voided" in sink.lifecycle_events())
    # 旧命令被取消回收：gate 释放后无任务消费，也不会污染新尝试。
    # 显式取消屏障：旧命令已被回收，迟到结果无从抵达。
    await wait_for_condition(lambda: session.gate.cancelled())
    for _ in range(10):
        await asyncio.sleep(0)
    session.grant_updates(3)  # STAGE_OPEN(rev2) + RUNNING(g2) + FINISHED
    await wait_for_condition(lambda: len(session.ready_calls) >= 2)
    terminal = await run_task

    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    assert [(s.stage_no, s.observed_revision) for s in session.ready_calls] == [(1, 1), (1, 2)]
    attempts = [
        record.payload["stage_attempt_id"]
        for record in sink.records
        if record.kind.value == "lifecycle_changed"
        and record.payload["event"] == "stage_attempt_started"
    ]
    assert len(attempts) == 2 and attempts[0] != attempts[1]


async def test_late_register_rejection_after_running_discarded():
    """开赛后迟到的报名拒绝不重试、不升级终态，编排交给权威快照。"""

    import asyncio

    from hangma_bot.application.contracts import OperationStatus, RegistrationResult

    class RegisterGateSession(FakeTournamentSession):
        def __init__(self, **kwargs) -> None:
            super().__init__(**kwargs)
            self.gate = asyncio.Future()

        async def register(self):
            self.register_calls += 1
            if self.register_calls == 1:
                return await self.gate
            return RegistrationResult(status=OperationStatus.ACCEPTED)

    session = RegisterGateSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.REGISTERING)),
        updates=[
            make_snapshot(TournamentStatus.RUNNING, stage_no=1, my_games=["g1"]),
            make_snapshot(TournamentStatus.FINISHED),
        ],
        game_factory=lambda gid: FakeGameSession(items=[]),
    )
    runtime, sink, *_ = build_runtime(session=session)
    run_task = asyncio.create_task(runtime.run())

    from fakes import wait_for_condition

    await wait_for_condition(lambda: session.register_calls >= 1)
    session.grant_updates(1)  # 开赛：报名已无必要
    await wait_for_condition(lambda: session.game_opens == ["g1"])
    # 迟到 TOURNAMENT_STARTED 拒绝抵达：必须丢弃且不重试
    session.gate.set_result(
        RegistrationResult(
            status=OperationStatus.REJECTED, official_code="TOURNAMENT_STARTED"
        )
    )
    await wait_for_condition(
        lambda: any(
            record.kind.value == "protocol_recovered"
            and "停止报名" in str(record.payload.get("reason", ""))
            for record in sink.records
        )
    )
    for _ in range(10):
        await asyncio.sleep(0)
    assert session.register_calls == 1  # 没有烧退避预算
    session.grant_updates(1)
    terminal = await run_task
    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED


async def test_sink_close_failure_marks_audit_degraded():
    """审计 sink 关闭失败必须反映为运行级 audit_degraded。"""

    class BoomCloseSink(InMemoryAuditSink):
        async def aclose(self, timeout_seconds: float):
            raise RuntimeError("flush 失败")

    game = FakeGameSession(items=[make_window(make_observation(game_id="g1", seq=10))])
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=["g1"])),
        updates=[make_snapshot(TournamentStatus.FINISHED)],
        game_factory=lambda gid: game,
    )
    sink = BoomCloseSink()
    runtime, _sink, *_ = build_runtime(session=session, sink=sink)
    run_task = asyncio.create_task(runtime.run())

    from fakes import wait_for_condition

    await wait_for_condition(lambda: game.drained)
    session.grant_updates(1)
    terminal = await run_task
    assert terminal.reason.value == "tournament_finished"
    assert runtime.audit_degraded is True


async def test_no_task_leak_after_multiple_updates():
    """多轮快照更新后不残留 wake waiter 等悬空任务。"""

    import asyncio

    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=[])),
        updates=[
            make_snapshot(TournamentStatus.STAGE_DONE, stage_no=1),
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=2, revision=2, qualified=True),
            make_snapshot(TournamentStatus.RUNNING, stage_no=2, my_games=["g1"]),
            make_snapshot(TournamentStatus.FINISHED),
        ],
        game_factory=lambda gid: FakeGameSession(items=[]),
    )
    runtime, sink, *_ = build_runtime(session=session)
    baseline = set(asyncio.all_tasks())
    run_task = asyncio.create_task(runtime.run())
    session.grant_updates(4)
    terminal = await run_task

    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    # 结构化关闭修复后无需额外让步：runtime 返回即全部子任务已回收。
    current = asyncio.current_task()
    leftover = {
        task
        for task in asyncio.all_tasks()
        if task is not current and task not in baseline and not task.done()
    }
    assert not leftover, "残留任务: {}".format(leftover)



async def test_crash_cancels_inflight_ready_not_qualified_path():
    """crash 取消在途 ready（NOT_QUALIFIED 路径）：不淘汰身份，重赛重新到位。"""

    import asyncio

    from hangma_bot.application.contracts import OperationStatus, ReadyResult

    class ReadyGateSession(FakeTournamentSession):
        def __init__(self, **kwargs) -> None:
            super().__init__(**kwargs)
            self.gate = asyncio.Future()

        async def ready(self, expected_stage):
            self.ready_calls.append(expected_stage)
            if len(self.ready_calls) == 1:
                return await self.gate
            return ReadyResult(status=OperationStatus.ACCEPTED)

    session = ReadyGateSession(
        bootstrap=make_bootstrap(
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=1, revision=1, qualified=True)
        ),
        updates=[
            make_snapshot(TournamentStatus.RUNNING, stage_no=1, revision=1, my_games=["g1"]),
            make_snapshot(
                TournamentStatus.RUNNING,
                stage_no=1,
                revision=1,
                crashed=True,
                my_games=["g1"],
                active_games=[],
            ),
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=1, revision=2, qualified=True),
            make_snapshot(TournamentStatus.FINISHED),
        ],
        game_factory=lambda gid: FakeGameSession(items=[]),
    )
    runtime, sink, *_ = build_runtime(session=session)
    run_task = asyncio.create_task(runtime.run())

    from fakes import wait_for_condition

    await wait_for_condition(lambda: len(session.ready_calls) >= 1)
    session.grant_updates(2)  # RUNNING + crashed
    await wait_for_condition(lambda: "stage_attempt_voided" in sink.lifecycle_events())
    # 旧命令被取消回收：迟到的 NOT_QUALIFIED 无任务消费，不会淘汰当前身份。
    # 显式取消屏障：旧命令已被回收，迟到结果无从抵达。
    await wait_for_condition(lambda: session.gate.cancelled())
    session.grant_updates(2)  # STAGE_OPEN(rev2) + FINISHED
    await wait_for_condition(lambda: len(session.ready_calls) >= 2)
    terminal = await run_task
    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED


async def test_register_backoff_prechecks_status_before_next_post():
    """退避等待期间赛事开赛：醒来后不再多打一笔报名。"""

    import asyncio

    release = asyncio.Event()

    async def gated_sleep(seconds: float) -> None:
        if not release.is_set():
            await release.wait()

    class RegisterRaisesOnce(FakeTournamentSession):
        async def register(self):
            self.register_calls += 1
            raise RuntimeError("瞬时故障")

    session = RegisterRaisesOnce(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.REGISTERING)),
        updates=[
            make_snapshot(TournamentStatus.RUNNING, stage_no=1, my_games=["g1"]),
            make_snapshot(TournamentStatus.FINISHED),
        ],
        game_factory=lambda gid: FakeGameSession(items=[]),
    )
    runtime, sink, *_ = build_runtime(session=session, sleep=gated_sleep)
    run_task = asyncio.create_task(runtime.run())

    from fakes import wait_for_condition

    await wait_for_condition(lambda: session.register_calls >= 1)  # 首笔异常入退避
    session.grant_updates(1)  # 退避期间开赛
    await wait_for_condition(lambda: session.game_opens == ["g1"])
    release.set()  # 退避醒来：循环顶预检应直接停止
    await wait_for_condition(
        lambda: any(
            record.kind.value == "protocol_recovered"
            and record.payload.get("area") == "register"
            for record in sink.records
        )
    )
    for _ in range(10):
        await asyncio.sleep(0)
    assert session.register_calls == 1
    session.grant_updates(1)
    terminal = await run_task
    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED


async def test_rejected_key_mismatch_excludes_attempt_key():
    """适配器拒绝键与尝试键不一致时按尝试键排除，不重发已拒动作。"""

    import asyncio

    from fakes import make_refreshed_window
    from hangma_bot.application.contracts import SubmitRejectedRetryable

    base_window = make_window(make_observation(game_id="g1", seq=10))
    counter = {"n": 0}

    def handler(attempt):
        counter["n"] += 1
        if counter["n"] == 1:
            return SubmitRejectedRetryable(
                official_code="CONFLICT",
                rejected_action_key="pass",  # 故意回传与尝试不一致的键
                refreshed_window=make_refreshed_window(base_window, seq=11),
            )
        return SubmitAccepted(official_code="200", authoritative_seq=12)

    from fakes import build_runtime as _br

    game = FakeGameSession(
        items=[base_window], submit_handler=handler,
    )
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=["g1"])),
        updates=[make_snapshot(TournamentStatus.FINISHED)],
        game_factory=lambda gid: game,
    )
    runtime, sink, *_ = _br(session=session)
    run_task = asyncio.create_task(runtime.run())

    from fakes import wait_for_condition

    await wait_for_condition(lambda: game.drained)
    session.grant_updates(1)
    terminal = await run_task

    assert [a.action_key for a in game.submitted] == ["discard:3w", "pass"]
    recovered = [
        record.payload
        for record in sink.records
        if record.kind.value == "protocol_recovered"
    ]
    assert any("拒绝键不一致" in str(item.get("reasons")) for item in recovered)


async def test_cancel_during_initialize_audited():
    """初始化期间被取消也要留下运行审计而不是零记录。"""

    import asyncio

    class InitHangs(FakeTournamentSession):
        async def initialize(self, target):
            await asyncio.Future()

    session = InitHangs(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.REGISTERING))
    )
    sink = InMemoryAuditSink()
    runtime, _sink, *_ = build_runtime(session=session, sink=sink)
    run_task = asyncio.create_task(runtime.run())
    for _ in range(10):
        await asyncio.sleep(0)
    run_task.cancel()
    try:
        await run_task
        raised = False
    except asyncio.CancelledError:
        raised = True
    assert raised
    kinds = [kind.value for kind in sink.kinds()]
    assert "run_manifest" in kinds
    assert "participant_finished" in kinds
    assert sink.closed is True



async def test_late_ready_rejection_burns_no_budget():
    """迟到拒绝不消耗新尝试的重试预算：max=1 时新尝试仍有一次重试。"""

    import asyncio

    from hangma_bot.application.contracts import OperationStatus, ReadyResult
    from hangma_bot.application.tournament_supervisor import SupervisionPolicy

    class ReadyGateSession(FakeTournamentSession):
        def __init__(self, **kwargs) -> None:
            super().__init__(**kwargs)
            self.gate = asyncio.Future()

        async def ready(self, expected_stage):
            self.ready_calls.append(expected_stage)
            if len(self.ready_calls) == 1:
                return await self.gate
            return ReadyResult(
                status=OperationStatus.REJECTED, official_code="TEMP"
            )

    session = ReadyGateSession(
        bootstrap=make_bootstrap(
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=1, revision=1, qualified=True)
        ),
        updates=[
            make_snapshot(TournamentStatus.RUNNING, stage_no=1, revision=1, my_games=["g1"]),
            make_snapshot(
                TournamentStatus.RUNNING,
                stage_no=1,
                revision=1,
                crashed=True,
                my_games=["g1"],
                active_games=[],
            ),
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=1, revision=2, qualified=True),
        ],
        game_factory=lambda gid: FakeGameSession(items=[]),
    )
    runtime, sink, *_ = build_runtime(
        session=session,
        supervision=SupervisionPolicy(ready_max_attempts=1),
    )
    run_task = asyncio.create_task(runtime.run())

    from fakes import wait_for_condition

    await wait_for_condition(lambda: len(session.ready_calls) >= 1)
    session.grant_updates(2)  # RUNNING + crashed
    await wait_for_condition(lambda: "stage_attempt_voided" in sink.lifecycle_events())
    # 迟到 TEMP 拒绝：必须判废且不烧唯一预算
    # 显式取消屏障：旧命令已被回收，迟到结果无从抵达。
    await wait_for_condition(lambda: session.gate.cancelled())
    session.grant_updates(1)  # STAGE_OPEN(rev2)
    # 新尝试的 TEMP 获得一次退避重试后再 TEMP，才按预算耗尽终止。
    terminal = await run_task
    assert terminal.reason is ParticipantTerminalReason.FATAL_PROTOCOL_ERROR
    assert [(s.stage_no, s.observed_revision) for s in session.ready_calls] == [
        (1, 1),
        (1, 2),
        (1, 2),
    ]



async def test_crash_resets_ready_budget():
    """crash 作废重置到位预算：新尝试的首次失败不继承旧账。"""

    import asyncio

    from hangma_bot.application.contracts import OperationStatus, ReadyResult
    from hangma_bot.application.tournament_supervisor import SupervisionPolicy

    class ReadyGateSession(FakeTournamentSession):
        def __init__(self, **kwargs) -> None:
            super().__init__(**kwargs)
            self.gate = asyncio.Future()

        async def ready(self, expected_stage):
            self.ready_calls.append(expected_stage)
            if len(self.ready_calls) == 2:
                return await self.gate  # 第二笔在途时发生 crash
            return ReadyResult(
                status=OperationStatus.REJECTED, official_code="TEMP"
            )

    session = ReadyGateSession(
        bootstrap=make_bootstrap(
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=1, revision=1, qualified=True)
        ),
        updates=[
            make_snapshot(TournamentStatus.RUNNING, stage_no=1, revision=1, my_games=["g1"]),
            make_snapshot(
                TournamentStatus.RUNNING,
                stage_no=1,
                revision=1,
                crashed=True,
                my_games=["g1"],
                active_games=[],
            ),
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=1, revision=2, qualified=True),
        ],
        game_factory=lambda gid: FakeGameSession(items=[]),
    )
    runtime, sink, *_ = build_runtime(
        session=session,
        supervision=SupervisionPolicy(ready_max_attempts=1),
    )
    run_task = asyncio.create_task(runtime.run())

    from fakes import wait_for_condition

    await wait_for_condition(lambda: len(session.ready_calls) >= 2)
    session.grant_updates(2)  # RUNNING + crashed（重置预算）
    await wait_for_condition(lambda: "stage_attempt_voided" in sink.lifecycle_events())
    # 显式取消屏障：旧命令已被回收，迟到结果无从抵达。
    await wait_for_condition(lambda: session.gate.cancelled())
    session.grant_updates(1)  # STAGE_OPEN(rev2)
    terminal = await run_task
    assert terminal.reason is ParticipantTerminalReason.FATAL_PROTOCOL_ERROR
    # 旧尝试耗掉一次预算；crash 重置后新尝试获得自己的一次重试。
    assert [(s.stage_no, s.observed_revision) for s in session.ready_calls] == [
        (1, 1),
        (1, 1),
        (1, 2),
        (1, 2),
    ]



async def test_stage_transition_discards_late_not_qualified():
    """阶段迁移后旧 ready 的迟到 NOT_QUALIFIED 判废：不淘汰、继续到位新阶段。"""

    import asyncio

    from hangma_bot.application.contracts import OperationStatus, ReadyResult

    class ReadyGateSession(FakeTournamentSession):
        def __init__(self, **kwargs) -> None:
            super().__init__(**kwargs)
            self.gate = asyncio.Future()

        async def ready(self, expected_stage):
            self.ready_calls.append(expected_stage)
            if len(self.ready_calls) == 1:
                # shield 建模不可取消的迟到响应：本地取消不连带取消结果源。
                return await asyncio.shield(self.gate)
            return ReadyResult(status=OperationStatus.ACCEPTED)

    session = ReadyGateSession(
        bootstrap=make_bootstrap(
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=1, revision=1, qualified=True)
        ),
        updates=[
            make_snapshot(TournamentStatus.STAGE_DONE, stage_no=1, revision=1),
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=2, revision=2, qualified=True),
            make_snapshot(TournamentStatus.FINISHED),
        ],
        game_factory=lambda gid: FakeGameSession(items=[]),
    )
    runtime, sink, *_ = build_runtime(session=session)
    run_task = asyncio.create_task(runtime.run())

    from fakes import wait_for_condition

    await wait_for_condition(lambda: len(session.ready_calls) >= 1)
    session.grant_updates(2)  # 阶段推进到 stage2 确认窗口
    await wait_for_condition(
        lambda: any(
            record.kind.value == "authoritative_state"
            and record.payload.get("stage_no") == 2
            for record in sink.records
        )
    )
    # stage1 旧请求迟到 NOT_QUALIFIED：权威已是 stage2 名单内，必须判废
    session.gate.set_result(
        ReadyResult(status=OperationStatus.REJECTED, official_code="NOT_QUALIFIED")
    )
    await wait_for_condition(lambda: len(session.ready_calls) >= 2)
    await wait_for_condition(lambda: "ready" in sink.lifecycle_events())
    session.grant_updates(1)
    terminal = await run_task

    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    assert [(s.stage_no, s.observed_revision) for s in session.ready_calls] == [
        (1, 1),
        (2, 2),
    ]


async def test_stage_transition_late_accepted_keeps_current_attempt():
    """阶段迁移后旧 ready 的迟到 ACCEPTED 判废：不得回写当前尝试标识。"""

    import asyncio

    from hangma_bot.application.contracts import OperationStatus, ReadyResult

    class ReadyGateSession(FakeTournamentSession):
        """旧命令永远迟到；新阶段命令返回 ACCEPTED（不受 gate 影响）。"""

        def __init__(self, **kwargs) -> None:
            super().__init__(**kwargs)
            self.gate = asyncio.Future()

        async def ready(self, expected_stage):
            self.ready_calls.append(expected_stage)
            if expected_stage.stage_no == 1:
                return await self.gate  # stage1 命令挂起，直到被迁移取消
            return ReadyResult(status=OperationStatus.ACCEPTED)

    game = FakeGameSession(items=[make_window(make_observation(game_id="g2", seq=20))])
    session = ReadyGateSession(
        bootstrap=make_bootstrap(
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=1, revision=1, qualified=True)
        ),
        updates=[
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=2, revision=2, qualified=True),
            make_snapshot(TournamentStatus.RUNNING, stage_no=2, revision=2, my_games=["g2"]),
            make_snapshot(TournamentStatus.FINISHED),
        ],
        game_factory=lambda gid: game,
    )
    runtime, sink, *_ = build_runtime(session=session)
    run_task = asyncio.create_task(runtime.run())

    from fakes import wait_for_condition

    await wait_for_condition(lambda: len(session.ready_calls) >= 1)
    session.grant_updates(2)  # stage2 确认窗口 + 开跑（主循环生成 sa-2 并开 g2）
    await wait_for_condition(lambda: game.drained)
    await wait_for_condition(lambda: len(session.ready_calls) >= 2)  # stage2 已到位
    session.grant_updates(1)
    terminal = await run_task

    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    attempts = [
        (record.payload["stage_no"], record.payload["stage_attempt_id"])
        for record in sink.records
        if record.kind.value == "lifecycle_changed"
        and record.payload["event"] == "stage_attempt_started"
    ]
    assert attempts == [(2, attempts[0][1])]  # 只有 stage2 尝试，未被回写
    intents = [
        record for record in sink.records if record.kind.value == "submission_intent"
    ]
    assert intents and intents[0].context.stage_attempt_id == attempts[0][1]



async def test_stage_transition_releases_ready_worker():
    """旧 ready 挂起时阶段迁移：取消旧命令并立即发出新阶段到位。"""

    import asyncio

    from hangma_bot.application.contracts import OperationStatus, ReadyResult

    class ReadyHangsForever(FakeTournamentSession):
        async def ready(self, expected_stage):
            self.ready_calls.append(expected_stage)
            if len(self.ready_calls) == 1:
                await asyncio.Future()  # 旧命令永远挂起，直到被取消
            return ReadyResult(status=OperationStatus.ACCEPTED)

    game = FakeGameSession(items=[make_window(make_observation(game_id="g2", seq=20))])
    session = ReadyHangsForever(
        bootstrap=make_bootstrap(
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=1, revision=1, qualified=True)
        ),
        updates=[
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=2, revision=2, qualified=True),
            make_snapshot(TournamentStatus.RUNNING, stage_no=2, revision=2, my_games=["g2"]),
            make_snapshot(TournamentStatus.FINISHED),
        ],
        game_factory=lambda gid: game,
    )
    runtime, sink, *_ = build_runtime(session=session)
    run_task = asyncio.create_task(runtime.run())

    from fakes import wait_for_condition

    await wait_for_condition(lambda: len(session.ready_calls) >= 1)
    # 旧 stage1 命令仍挂起：快照推进到 stage2 确认窗口并直接开跑
    session.grant_updates(2)
    await wait_for_condition(lambda: game.drained)
    # stage2 到位必须已被发出（旧命令被取消释放了 worker）
    await wait_for_condition(lambda: len(session.ready_calls) >= 2)
    session.grant_updates(1)
    terminal = await run_task

    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    assert [(s.stage_no, s.observed_revision) for s in session.ready_calls] == [
        (1, 1),
        (2, 2),
    ]



async def test_stage_transition_to_unqualified_stage_never_readies():
    """迁移到名单外阶段（qualified=false）：不发起该阶段到位，按正常淘汰退出。"""

    import asyncio

    class ReadyHangsForever(FakeTournamentSession):
        async def ready(self, expected_stage):
            self.ready_calls.append(expected_stage)
            await asyncio.Future()

    session = ReadyHangsForever(
        bootstrap=make_bootstrap(
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=1, revision=1, qualified=True)
        ),
        updates=[
            make_snapshot(
                TournamentStatus.STAGE_OPEN, stage_no=2, revision=2, qualified=False
            ),
        ],
    )
    runtime, sink, *_ = build_runtime(session=session)
    run_task = asyncio.create_task(runtime.run())

    from fakes import wait_for_condition

    await wait_for_condition(lambda: len(session.ready_calls) >= 1)
    session.grant_updates(1)  # 迁移到 stage2 名单外
    terminal = await run_task

    assert terminal.reason is ParticipantTerminalReason.ELIMINATED
    assert [(s.stage_no, s.observed_revision) for s in session.ready_calls] == [(1, 1)]



async def test_running_of_new_stage_reattributes_attempt_before_open():
    """stage2 开跑而其确认响应仍在途：开场前必须生成 stage2 尝试标识。"""

    import asyncio

    from hangma_bot.application.contracts import OperationStatus, ReadyResult

    class ReadyFirstInstantThenHangs(FakeTournamentSession):
        def __init__(self, **kwargs) -> None:
            super().__init__(**kwargs)

        async def ready(self, expected_stage):
            self.ready_calls.append(expected_stage)
            if expected_stage.stage_no == 1:
                return ReadyResult(status=OperationStatus.ACCEPTED)
            await asyncio.Future()  # stage2 确认响应在途挂起

    game = FakeGameSession(items=[make_window(make_observation(game_id="g2", seq=20))])
    session = ReadyFirstInstantThenHangs(
        bootstrap=make_bootstrap(
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=1, revision=1, qualified=True)
        ),
        updates=[
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=2, revision=2, qualified=True),
            make_snapshot(TournamentStatus.RUNNING, stage_no=2, revision=2, my_games=["g2"]),
            make_snapshot(TournamentStatus.FINISHED),
        ],
        game_factory=lambda gid: game,
    )
    runtime, sink, *_ = build_runtime(session=session)
    run_task = asyncio.create_task(runtime.run())

    from fakes import wait_for_condition

    def _stage1_attempt_started() -> bool:
        return any(
            record.kind.value == "lifecycle_changed"
            and record.payload.get("event") == "stage_attempt_started"
            and record.payload.get("stage_no") == 1
            for record in sink.records
        )

    # 先等 stage1 确认完成（sa-1 已生成），再推进 stage2——这是被测交错的前提。
    await wait_for_condition(_stage1_attempt_started)
    session.grant_updates(1)  # 放行 STAGE_OPEN(2)：发出 stage2 到位命令
    await wait_for_condition(lambda: len(session.ready_calls) >= 2)  # stage2 命令在途
    session.grant_updates(1)  # 放行 RUNNING(stage2)：开 g2 前必须生成 sa-2
    await wait_for_condition(lambda: game.drained)
    session.grant_updates(1)
    terminal = await run_task

    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    attempts = [
        (record.payload["stage_no"], record.payload["stage_attempt_id"])
        for record in sink.records
        if record.kind.value == "lifecycle_changed"
        and record.payload["event"] == "stage_attempt_started"
    ]
    assert [stage_no for stage_no, _ in attempts] == [1, 2]
    intents = [
        record for record in sink.records if record.kind.value == "submission_intent"
    ]
    assert intents and intents[0].context.stage_attempt_id == attempts[1][1]



async def test_stage_transition_resets_ready_budget():
    """普通阶段迁移同样重置到位预算：新阶段不继承旧阶段的退避消耗。"""

    import asyncio

    from hangma_bot.application.contracts import OperationStatus, ReadyResult
    from hangma_bot.application.tournament_supervisor import SupervisionPolicy

    class ReadyTempThenHangs(FakeTournamentSession):
        def __init__(self, **kwargs) -> None:
            super().__init__(**kwargs)
            self.gate = asyncio.Future()

        async def ready(self, expected_stage):
            self.ready_calls.append(expected_stage)
            if len(self.ready_calls) == 2:
                return await self.gate  # 第二笔在途时发生阶段迁移
            return ReadyResult(
                status=OperationStatus.REJECTED, official_code="TEMP"
            )

    session = ReadyTempThenHangs(
        bootstrap=make_bootstrap(
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=1, revision=1, qualified=True)
        ),
        updates=[
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=2, revision=2, qualified=True),
        ],
    )
    runtime, sink, *_ = build_runtime(
        session=session,
        supervision=SupervisionPolicy(ready_max_attempts=1),
    )
    run_task = asyncio.create_task(runtime.run())

    from fakes import wait_for_condition

    await wait_for_condition(lambda: len(session.ready_calls) >= 2)
    session.grant_updates(1)  # stage1 → stage2 迁移（预算随之重置）
    terminal = await run_task

    assert terminal.reason is ParticipantTerminalReason.FATAL_PROTOCOL_ERROR
    # 旧阶段合法消耗一次预算；迁移重置后新阶段获得自己的一次重试。
    assert [(s.stage_no, s.observed_revision) for s in session.ready_calls] == [
        (1, 1),
        (1, 1),
        (2, 2),
        (2, 2),
    ]



async def test_cancel_with_inflight_ready_no_resurrection():
    """关闭期间取消在途 ready：done 回调不得复活 worker、无任务泄漏。"""

    import asyncio

    class ReadyHangsForever(FakeTournamentSession):
        async def ready(self, expected_stage):
            self.ready_calls.append(expected_stage)
            await asyncio.Future()

    session = ReadyHangsForever(
        bootstrap=make_bootstrap(
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=1, revision=1, qualified=True)
        ),
    )
    sink = InMemoryAuditSink()
    runtime, _sink, *_ = build_runtime(session=session, sink=sink)
    baseline = set(asyncio.all_tasks())
    run_task = asyncio.create_task(runtime.run())

    from fakes import wait_for_condition

    await wait_for_condition(lambda: len(session.ready_calls) >= 1)
    run_task.cancel()
    try:
        await run_task
        raised = False
    except asyncio.CancelledError:
        raised = True
    assert raised
    for _ in range(10):  # 让取消与回调落地
        await asyncio.sleep(0)
    # 在途 ready 被取消且不复活：到位调用数恒为 1
    assert len(session.ready_calls) == 1
    assert session.closed is True
    assert sink.closed is True
    current = asyncio.current_task()
    leftover = {
        task
        for task in asyncio.all_tasks()
        if task is not current and task not in baseline and not task.done()
    }
    assert not leftover, "残留任务: {}".format(leftover)



async def test_shutdown_waits_for_slow_side_task_cleanup():
    """被取消的到位协程做异步清理时，监督器必须等它完成才返回。"""

    import asyncio

    cleanup_gate = asyncio.Event()

    class ReadyCleansUpSlowly(FakeTournamentSession):
        async def ready(self, expected_stage):
            self.ready_calls.append(expected_stage)
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                await cleanup_gate.wait()  # 模拟取消处理中的异步清理
                raise

    session = ReadyCleansUpSlowly(
        bootstrap=make_bootstrap(
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=1, revision=1, qualified=True)
        ),
    )
    sink = InMemoryAuditSink()
    runtime, _sink, *_ = build_runtime(session=session, sink=sink)
    run_task = asyncio.create_task(runtime.run())

    from fakes import wait_for_condition

    await wait_for_condition(lambda: len(session.ready_calls) >= 1)
    run_task.cancel()
    for _ in range(20):  # 清理门未开：runtime 不得提前返回
        await asyncio.sleep(0)
    assert not run_task.done()
    cleanup_gate.set()
    try:
        await run_task
        raised = False
    except asyncio.CancelledError:
        raised = True
    assert raised
    assert len(session.ready_calls) == 1  # 无复活
    assert sink.closed is True



async def test_crash_reported_during_stage_done():
    """官方典型形态：stage_done 期间上报 crashed——作废尝试且不重开历史场。"""

    import asyncio

    session = FakeTournamentSession(
        bootstrap=make_bootstrap(
            make_snapshot(TournamentStatus.RUNNING, stage_no=1, my_games=["g1"])
        ),
        updates=[
            make_snapshot(
                TournamentStatus.STAGE_DONE,
                stage_no=1,
                revision=1,
                crashed=True,
                my_games=["g1"],
                active_games=[],
            ),
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=1, revision=2, qualified=True),
            make_snapshot(TournamentStatus.FINISHED),
        ],
        ready_results=[
            __import__("hangma_bot.application.contracts", fromlist=["ReadyResult"]).ReadyResult(
                status=__import__("hangma_bot.application.contracts", fromlist=["OperationStatus"]).OperationStatus.ACCEPTED
            ),
        ],
        game_factory=lambda gid: FakeGameSession(items=[]),
    )
    runtime, sink, *_ = build_runtime(session=session)
    run_task = asyncio.create_task(runtime.run())

    from fakes import wait_for_condition

    session.grant_updates(1)  # 放行 crashed 的 stage_done 快照
    await wait_for_condition(
        lambda: "stage_attempt_voided" in sink.lifecycle_events()
    )
    # 关闭经由后台清理任务异步落地。
    await wait_for_condition(
        lambda: session.opened_games["g1"].close_reasons == ["stage_crashed"]
    )
    session.grant_updates(2)
    terminal = await run_task
    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    assert session.game_opens == ["g1"]  # 崩溃后未重开旧场



async def test_crashed_snapshot_with_active_games_never_resurrects():
    """崩溃快照即使仍列 active_games 也不得借关闭回调复活旧阶段场次。"""

    import asyncio

    session = FakeTournamentSession(
        bootstrap=make_bootstrap(
            make_snapshot(TournamentStatus.RUNNING, stage_no=1, my_games=["g1"], active_games=["g1"])
        ),
        updates=[
            make_snapshot(
                TournamentStatus.RUNNING,
                stage_no=1,
                revision=1,
                crashed=True,
                my_games=["g1"],
                active_games=["g1"],  # 平台尚未收缩 active 列表
            ),
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=1, revision=2, qualified=True),
            make_snapshot(TournamentStatus.RUNNING, stage_no=1, revision=2, my_games=["g2"]),
            make_snapshot(TournamentStatus.FINISHED),
        ],
        game_factory=lambda gid: FakeGameSession(items=[]),
    )
    runtime, sink, *_ = build_runtime(session=session)
    run_task = asyncio.create_task(runtime.run())

    from fakes import wait_for_condition

    session.grant_updates(1)  # 崩溃快照
    await wait_for_condition(
        lambda: session.opened_games["g1"].close_reasons == ["stage_crashed"]
    )
    for _ in range(20):  # 关闭回调与对账落地后仍不得重开 g1
        await asyncio.sleep(0)
    assert session.game_opens == ["g1"]
    session.grant_updates(3)  # 新尝试 + g2 + FINISHED
    terminal = await run_task
    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    assert session.game_opens == ["g1", "g2"]


async def test_game_failed_reason_sanitized_in_audit():
    """GameFailed.reason 携带凭证样式文本时入审计前必须脱敏。"""

    game = FakeGameSession(
        items=[
            GameFailed(
                game_id="g1",
                recoverable=False,
                reason="Authorization: Bearer TOPSECRETabcdef0123456789",
            )
        ]
    )
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=["g1"])),
        updates=[make_snapshot(TournamentStatus.FINISHED)],
        game_factory=lambda gid: game,
    )
    runtime, sink, *_ = build_runtime(session=session)
    run_task = asyncio.create_task(runtime.run())

    from fakes import wait_for_condition

    def _ended() -> bool:
        return any(
            record.kind.value == "lifecycle_changed"
            and record.payload.get("event") == "game_ended"
            for record in sink.records
        )

    await wait_for_condition(_ended)
    session.grant_updates(1)
    terminal = await run_task
    assert terminal.reason.value == "tournament_finished"

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
            assert "topsecret" not in low
            assert "bearer " not in low



async def test_slow_aclose_blocks_same_id_reopen_until_complete():
    """旧会话 aclose 在途时同 game_id 不得重开；关闭完成后方可重建。"""

    import asyncio

    aclose_gate = asyncio.Event()
    aclose_started = asyncio.Event()  # 显式证明 aclose 已进入在途状态

    class SlowCloseSession(FakeGameSession):
        async def aclose(self, reason: str) -> None:
            aclose_started.set()
            await aclose_gate.wait()  # 模拟受门控的慢关闭
            await super().aclose(reason)

    first = SlowCloseSession(items=[])
    queue = {"g1": [first, FakeGameSession(items=[])]}
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(
            make_snapshot(TournamentStatus.RUNNING, stage_no=1, my_games=["g1"], active_games=["g1"])
        ),
        updates=[
            make_snapshot(
                TournamentStatus.RUNNING,
                stage_no=1,
                revision=1,
                crashed=True,
                my_games=["g1"],
                active_games=["g1"],
            ),
            make_snapshot(
                TournamentStatus.RUNNING,
                stage_no=2,
                revision=2,
                my_games=["g1"],
                active_games=["g1"],  # 新尝试仍列同一场：关闭完成前不得重开
            ),
        ],
        game_factory=lambda gid: queue[gid].pop(0),
    )
    runtime, sink, *_ = build_runtime(session=session)
    run_task = asyncio.create_task(runtime.run())

    from fakes import wait_for_condition

    session.grant_updates(1)  # crashed：g1 进入慢关闭
    await wait_for_condition(lambda: len(session.game_opens) >= 1)
    await aclose_started.wait()  # 屏障：aclose 确认在途后再放下一张快照
    session.grant_updates(1)  # 新尝试快照（非 crashed）仍列 g1
    for _ in range(20):  # 旧 aclose 被门控：同 ID 不得重开
        await asyncio.sleep(0)
    assert session.game_opens == ["g1"]

    aclose_gate.set()  # 旧关闭完成：唤醒对账后才允许重建
    await wait_for_condition(lambda: len(session.game_opens) >= 2)
    run_task.cancel()
    try:
        await run_task
    except asyncio.CancelledError:
        pass
    assert session.game_opens == ["g1", "g1"]
    assert first.close_reasons == ["stage_crashed"]



async def test_short_bearer_token_redacted_in_audit():
    """两段式 Authorization Bearer 头的短凭证也必须整段脱敏。"""

    from hangma_bot.application.audit import audit_text

    assert "abc123" not in audit_text("Authorization: Bearer abc123").lower()
    assert "abc123" not in audit_text("bearer abc123").lower()
    assert "abc123" not in audit_text("token=abc123").lower()

    game = FakeGameSession(
        items=[
            GameFailed(
                game_id="g1",
                recoverable=True,
                reason="Authorization: Bearer abc123",
            )
        ]
    )
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=["g1"])),
        updates=[make_snapshot(TournamentStatus.FINISHED)],
        game_factory=lambda gid: game,
    )
    runtime, sink, *_ = build_runtime(session=session)
    run_task = asyncio.create_task(runtime.run())

    from fakes import wait_for_condition

    await wait_for_condition(lambda: game.closed)
    session.grant_updates(1)
    terminal = await run_task
    assert terminal.reason.value == "tournament_finished"

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
            assert "abc123" not in text.lower()



async def test_policy_slow_cancellation_does_not_block_emergency():
    """策略捕获取消做慢清理：硬截止立即放弃并提交紧急保底。"""

    import asyncio

    from fakes import DISCARD_3W, FakePolicy, FakeRules, PASS

    release = asyncio.Event()

    fake_rules_singleton = FakeRules(candidates=(DISCARD_3W,), emergency=PASS)

    class SlowCleanupPolicy(FakePolicy):
        async def choose(self, request, budget):
            self.calls.append(request)
            self.budgets.append(budget)
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                await release.wait()  # 模拟慢清理：取消后仍耗时收尾
                raise

    game = FakeGameSession(items=[make_window(make_observation(game_id="g1", seq=10))])
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=["g1"])),
        updates=[make_snapshot(TournamentStatus.FINISHED)],
        game_factory=lambda gid: game,
    )
    runtime, sink, *_ = build_runtime(
        session=session,
        policy=SlowCleanupPolicy(),
        rules=fake_rules_singleton,
    )
    run_task = asyncio.create_task(runtime.run())

    from fakes import wait_for_condition

    # 策略仍在慢清理（未释放）：紧急保底必须已完成提交
    await wait_for_condition(lambda: len(game.submitted) >= 1 and not release.is_set())
    assert game.submitted[0].action_key == "pass"
    release.set()
    session.grant_updates(1)
    terminal = await run_task
    assert terminal.reason.value == "tournament_finished"


async def test_crash_cancels_hung_ready_worker():
    """同阶段重赛：crash 取消挂起的旧 ready，新尝试立即到位。"""

    import asyncio

    from hangma_bot.application.contracts import OperationStatus, ReadyResult

    class ReadyHangsThenAccepts(FakeTournamentSession):
        async def ready(self, expected_stage):
            self.ready_calls.append(expected_stage)
            if len(self.ready_calls) == 1:
                await asyncio.Future()  # 挂起直到被 crash 取消
            return ReadyResult(status=OperationStatus.ACCEPTED)

    session = ReadyHangsThenAccepts(
        bootstrap=make_bootstrap(
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=1, revision=1, qualified=True)
        ),
        updates=[
            make_snapshot(
                TournamentStatus.RUNNING, stage_no=1, revision=1,
                crashed=True, my_games=["g1"], active_games=[],
            ),
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=1, revision=2, qualified=True),
            make_snapshot(TournamentStatus.FINISHED),
        ],
        game_factory=lambda gid: FakeGameSession(items=[]),
    )
    runtime, sink, *_ = build_runtime(session=session)
    run_task = asyncio.create_task(runtime.run())

    from fakes import wait_for_condition

    await wait_for_condition(lambda: len(session.ready_calls) >= 1)
    session.grant_updates(2)  # crashed + STAGE_OPEN(rev2)
    # 旧 worker 已被取消：新尝试的到位立即发出，不被 30 秒超时阻塞
    await wait_for_condition(lambda: len(session.ready_calls) >= 2)
    session.grant_updates(1)
    terminal = await run_task
    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    assert [(s.stage_no, s.observed_revision) for s in session.ready_calls] == [(1, 1), (1, 2)]


async def test_authority_removal_revokes_stale_reopen():
    """场次从 active 移除即撤销旧重开任务；重现时按全新场次立即开场。"""

    import asyncio

    blocking_release = asyncio.Event()

    async def gated_sleep(seconds: float) -> None:
        if not blocking_release.is_set():
            await blocking_release.wait()  # 冻结旧重开延迟

    first = FakeGameSession(
        items=[GameFailed(game_id="g1", recoverable=True, reason="瞬时故障")]
    )
    second = FakeGameSession(items=[])
    queue = {"g1": [first, second]}
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(
            make_snapshot(TournamentStatus.RUNNING, my_games=["g1"], active_games=["g1"])
        ),
        updates=[
            make_snapshot(
                TournamentStatus.RUNNING, stage_no=1,
                my_games=[], active_games=[],  # 权威移除：撤销在途重开
            ),
            make_snapshot(
                TournamentStatus.RUNNING, stage_no=1,
                my_games=["g1"], active_games=["g1"],  # 重现：不得被旧延迟挡住
            ),
        ],
        game_factory=lambda gid: queue[gid].pop(0),
    )
    runtime, sink, *_ = build_runtime(session=session, sleep=gated_sleep)
    run_task = asyncio.create_task(runtime.run())

    from fakes import wait_for_condition

    # 故障后旧重开任务被冻结；等待旧会话完成回收（关闭不受冻结影响）
    await wait_for_condition(
        lambda: session.game_opens == ["g1"] and first.closed
    )
    session.grant_updates(1)
    # 移除快照已处理（场次已由回收路径移除，不再产生 game_closed 事件，
    # 权威移除的实际效果是撤销在途重开任务）。
    await wait_for_condition(
        lambda: any(
            record.kind.value == "authoritative_state"
            and record.payload.get("active_games") == []
            for record in sink.records
        )
    )
    session.grant_updates(1)  # 重现：旧延迟仍冻结，但开场必须立即发生
    await wait_for_condition(lambda: len(session.game_opens) >= 2)
    blocking_release.set()
    run_task.cancel()
    try:
        await run_task
    except asyncio.CancelledError:
        pass


async def test_basic_and_cookie_authorization_redacted():
    """非 Bearer Authorization 与 Cookie 头的短凭证同样整段脱敏。"""

    from hangma_bot.application.audit import audit_text

    for text in (
        "Authorization: Basic abc123",
        "Cookie: session=abc123",
        "Authorization: Bearer abc123",
        "token=abc123",
    ):
        out = audit_text(text)
        assert "abc123" not in out.lower(), (text, out)

    game = FakeGameSession(
        items=[
            GameFailed(
                game_id="g1",
                recoverable=False,
                reason="Cookie: session=abc123 Authorization: Basic abc123",
            )
        ]
    )
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=["g1"])),
        updates=[make_snapshot(TournamentStatus.FINISHED)],
        game_factory=lambda gid: game,
    )
    runtime, sink, *_ = build_runtime(session=session)
    run_task = asyncio.create_task(runtime.run())

    from fakes import wait_for_condition

    def _ended() -> bool:
        return any(
            record.kind.value == "lifecycle_changed"
            and record.payload.get("event") == "game_ended"
            for record in sink.records
        )

    await wait_for_condition(_ended)
    session.grant_updates(1)
    terminal = await run_task
    assert terminal.reason.value == "tournament_finished"

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
            assert "abc123" not in text.lower()



async def test_cancel_during_policy_choose_no_leak():
    """外部取消发生在等待策略期间：策略任务被回收，无残留。"""

    import asyncio

    from fakes import DISCARD_3W, FakePolicy, FakeRules, PASS, InMemoryAuditSink

    started = asyncio.Event()

    class HungPolicy(FakePolicy):
        async def choose(self, request, budget):
            self.calls.append(request)
            self.budgets.append(budget)
            started.set()
            await asyncio.Future()

    game = FakeGameSession(items=[make_window(make_observation(game_id="g1", seq=10))])
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=["g1"])),
        game_factory=lambda gid: game,
    )
    sink = InMemoryAuditSink()
    runtime, _sink, *_ = build_runtime(
        session=session,
        sink=sink,
        policy=HungPolicy(),
        rules=FakeRules(candidates=(DISCARD_3W,), emergency=PASS),
    )
    baseline = set(asyncio.all_tasks())
    run_task = asyncio.create_task(runtime.run())
    await started.wait()
    run_task.cancel()
    try:
        await run_task
        raised = False
    except asyncio.CancelledError:
        raised = True
    assert raised
    current = asyncio.current_task()
    leftover = {
        task
        for task in asyncio.all_tasks()
        if task is not current and task not in baseline and not task.done()
    }
    assert not leftover, "残留任务: {}".format(leftover)



async def test_retired_ready_slow_cleanup_awaited_at_shutdown():
    """被取代的旧 ready 慢清理：新命令立即启动，收尾由 shutdown 等待。"""

    import asyncio

    from hangma_bot.application.contracts import OperationStatus, ReadyResult

    cleanup_started = asyncio.Event()
    release = asyncio.Event()

    class SlowCleanupReady(FakeTournamentSession):
        async def ready(self, expected_stage):
            self.ready_calls.append(expected_stage)
            if len(self.ready_calls) == 1:
                try:
                    await asyncio.Future()
                except asyncio.CancelledError:
                    cleanup_started.set()
                    await release.wait()  # 被取代后的慢异步清理
                    raise
            return ReadyResult(status=OperationStatus.ACCEPTED)

    session = SlowCleanupReady(
        bootstrap=make_bootstrap(
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=1, revision=1, qualified=True)
        ),
        updates=[
            make_snapshot(
                TournamentStatus.RUNNING, stage_no=1, revision=1,
                crashed=True, my_games=["g1"], active_games=[],
            ),
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=1, revision=2, qualified=True),
            make_snapshot(TournamentStatus.FINISHED),
        ],
        game_factory=lambda gid: FakeGameSession(items=[]),
    )
    runtime, sink, *_ = build_runtime(session=session)
    baseline = set(asyncio.all_tasks())
    run_task = asyncio.create_task(runtime.run())

    from fakes import wait_for_condition

    await wait_for_condition(lambda: len(session.ready_calls) >= 1)
    session.grant_updates(2)  # crash（退役旧命令）+ STAGE_OPEN(rev2)
    await wait_for_condition(lambda: len(session.ready_calls) >= 2)  # 新命令已启动
    await wait_for_condition(lambda: cleanup_started.is_set())
    session.grant_updates(1)  # FINISHED：终态已到但 shutdown 等待旧任务收尾
    for _ in range(20):
        await asyncio.sleep(0)
    assert not run_task.done()  # 旧 ready 慢清理未完成：runtime 不得返回
    release.set()
    terminal = await run_task
    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    current = asyncio.current_task()
    leftover = {
        task
        for task in asyncio.all_tasks()
        if task is not current and task not in baseline and not task.done()
    }
    assert not leftover, "残留任务: {}".format(leftover)



async def test_stale_reopen_cancel_cannot_pop_new_generation():
    """被撤销的旧重开协程不得误删新一代映射：新延迟在途时不重复开场。"""

    import asyncio
    from hangma_bot.application.tournament_supervisor import SupervisionPolicy

    gates = []

    async def gated_sleep(seconds: float) -> None:
        gate = asyncio.Event()
        gates.append(gate)
        try:
            await gate.wait()
        except asyncio.CancelledError:
            await gate.wait()  # 慢取消：取消传播被门控冻结
            raise

    def failing_factory_session():
        return FakeGameSession(
            items=[GameFailed(game_id="g1", recoverable=True, reason="瞬时")]
        )

    queue = {"g1": [failing_factory_session(), failing_factory_session(), FakeGameSession(items=[])]}
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(
            make_snapshot(TournamentStatus.RUNNING, my_games=["g1"], active_games=["g1"])
        ),
        updates=[
            make_snapshot(TournamentStatus.RUNNING, stage_no=1, my_games=[], active_games=[]),  # 移除：撤销第一代
            make_snapshot(TournamentStatus.RUNNING, stage_no=1, my_games=["g1"], active_games=["g1"]),  # 重现
            make_snapshot(TournamentStatus.RUNNING, stage_no=1, my_games=["g1"], active_games=["g1"]),  # 再次快照：不得重复开场
        ],
        game_factory=lambda gid: queue[gid].pop(0),
    )
    runtime, sink, *_ = build_runtime(
        session=session, sleep=gated_sleep,
        # 本例的门专门冻结重开退避；终局等待由独立的收尾时序测试覆盖。
        supervision=SupervisionPolicy(game_finalization_timeout_seconds=0),
    )
    run_task = asyncio.create_task(runtime.run())

    from fakes import wait_for_condition

    # 第一代故障 → 冻结的重开延迟
    await wait_for_condition(lambda: len(gates) >= 1 and len(session.game_opens) >= 1)
    session.grant_updates(1)  # 移除：撤销第一代（取消传播被 gate1 冻结）
    await wait_for_condition(
        lambda: any(
            record.kind.value == "authoritative_state"
            and record.payload.get("active_games") == []
            for record in sink.records
        )
    )
    session.grant_updates(1)  # 重现：第二代会话故障 → 新一代冻结延迟
    await wait_for_condition(lambda: len(session.game_opens) >= 2 and len(gates) >= 2)
    # 释放第一代取消：旧协程不得误删新一代映射
    gates[0].set()
    for _ in range(20):
        await asyncio.sleep(0)
    session.grant_updates(1)  # 再次快照：新延迟仍在途 → 不得第三次开场
    for _ in range(20):
        await asyncio.sleep(0)
    assert session.game_opens == ["g1", "g1"]
    # 释放新一代延迟：按正常节奏允许第三次开场
    gates[1].set()
    await wait_for_condition(lambda: len(session.game_opens) >= 3)
    run_task.cancel()
    try:
        await run_task
    except asyncio.CancelledError:
        pass
    assert session.game_opens == ["g1", "g1", "g1"]



async def test_revoked_reopen_slow_cleanup_awaited_at_shutdown():
    """被撤销的重开任务慢收尾：前台继续，shutdown 等待其完成。"""

    import asyncio

    release = asyncio.Event()

    async def slow_cancel_sleep(seconds: float) -> None:
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            await release.wait()  # 撤销后的慢异步收尾
            raise

    failing = FakeGameSession(
        items=[GameFailed(game_id="g1", recoverable=True, reason="瞬时")]
    )
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(
            make_snapshot(TournamentStatus.RUNNING, my_games=["g1"], active_games=["g1"])
        ),
        updates=[
            make_snapshot(TournamentStatus.RUNNING, stage_no=1, my_games=[], active_games=[]),
            make_snapshot(TournamentStatus.FINISHED),
        ],
        game_factory=lambda gid: failing,
    )
    runtime, sink, *_ = build_runtime(session=session, sleep=slow_cancel_sleep)
    run_task = asyncio.create_task(runtime.run())

    from fakes import wait_for_condition

    # 故障 → 重开延迟挂起（冻结）→ 等重开计划确立后再放行移除快照
    await wait_for_condition(
        lambda: any(
            record.kind.value == "protocol_recovered"
            and record.payload.get("area") == "game_reconcile"
            and record.payload.get("game_id") == "g1"
            for record in sink.records
        )
    )
    session.grant_updates(1)
    await wait_for_condition(
        lambda: any(
            record.kind.value == "authoritative_state"
            and record.payload.get("active_games") == []
            for record in sink.records
        )
    )
    session.grant_updates(1)  # FINISHED：终态已到但 shutdown 等待撤销任务收尾
    for _ in range(20):
        await asyncio.sleep(0)
    assert not run_task.done()
    release.set()
    terminal = await run_task
    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED



async def test_runtime_waits_for_deadline_abandoned_policy_cleanup():
    """硬截止放弃的策略任务：提交不等它，运行出口等待其慢收尾。"""

    import asyncio

    from fakes import DISCARD_3W, FakePolicy, FakeRules, PASS, InMemoryAuditSink

    release = asyncio.Event()

    class SlowCleanupPolicy(FakePolicy):
        async def choose(self, request, budget):
            self.calls.append(request)
            self.budgets.append(budget)
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                await release.wait()  # 硬截止后的慢收尾
                raise

    game = FakeGameSession(items=[make_window(make_observation(game_id="g1", seq=10))])
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=["g1"])),
        updates=[make_snapshot(TournamentStatus.FINISHED)],
        game_factory=lambda gid: game,
    )
    sink = InMemoryAuditSink()
    runtime, _sink, *_ = build_runtime(
        session=session,
        sink=sink,
        policy=SlowCleanupPolicy(),
        rules=FakeRules(candidates=(DISCARD_3W,), emergency=PASS),
    )
    baseline = set(asyncio.all_tasks())
    run_task = asyncio.create_task(runtime.run())

    from fakes import wait_for_condition

    # 硬截止生效：紧急保底提交不等待策略收尾
    await wait_for_condition(lambda: len(game.submitted) >= 1 and not release.is_set())
    session.grant_updates(1)  # FINISHED：终态已到但出口等待被弃任务的收尾
    for _ in range(20):
        await asyncio.sleep(0)
    assert not run_task.done()
    release.set()
    terminal = await run_task
    assert terminal.reason.value == "tournament_finished"
    current = asyncio.current_task()
    leftover = {
        task
        for task in asyncio.all_tasks()
        if task is not current and task not in baseline and not task.done()
    }
    assert not leftover, "残留任务: {}".format(leftover)



async def test_cancel_during_policy_choose_no_local_wait():
    """吞首次取消的病态策略：取消分支不得就地等待（R3 区分性回归）。"""

    import asyncio

    from fakes import DISCARD_3W, FakePolicy, FakeRules, PASS, InMemoryAuditSink
    from hangma_bot.application.tournament_supervisor import SupervisionPolicy

    cleanup_started = asyncio.Event()
    choose_started = asyncio.Event()

    class SwallowFirstCancelPolicy(FakePolicy):
        async def choose(self, request, budget):
            self.calls.append(request)
            self.budgets.append(budget)
            choose_started.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                cleanup_started.set()
                await asyncio.Future()  # 吞掉首次取消后永久挂起

    game = FakeGameSession(items=[make_window(make_observation(game_id="g1", seq=10))])
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=["g1"])),
        game_factory=lambda gid: game,
    )
    sink = InMemoryAuditSink()
    runtime, _sink, *_ = build_runtime(
        session=session,
        sink=sink,
        policy=SwallowFirstCancelPolicy(),
        rules=FakeRules(candidates=(DISCARD_3W,), emergency=PASS),
        supervision=SupervisionPolicy(audit_flush_seconds=0),
    )
    baseline = set(asyncio.all_tasks())
    run_task = asyncio.create_task(runtime.run())

    from fakes import wait_for_condition

    # 屏障：策略确已启动后再取消，避免空转路径让旧实现也通过。
    await choose_started.wait()
    run_task.cancel()
    for _ in range(30):  # 让取消传播与零时限出口回收落地
        await asyncio.sleep(0)
        if cleanup_started.is_set() and run_task.done():
            break
    # 旧实现（就地 await choose_task）会永久悬挂：此处断言零时限出口仍返回。
    assert cleanup_started.is_set()
    assert run_task.done()
    try:
        await run_task
        raised = False
    except asyncio.CancelledError:
        raised = True
    assert raised
    for _ in range(30):
        await asyncio.sleep(0)
    current = asyncio.current_task()
    leftover = {
        task
        for task in asyncio.all_tasks()
        if task is not current and task not in baseline and not task.done()
    }
    assert not leftover, "残留任务: {}".format(leftover)
