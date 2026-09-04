"""生命周期验收：报名、到位、多阶段、淘汰、重赛作废、新增场次与终态。"""

from __future__ import annotations

import asyncio

import pytest

from fakes import (
    DISCARD_3W,
    InMemoryAuditSink,
    PASS,
    FakeGameSession,
    FakePolicy,
    FakeRules,
    FakeTournamentSession,
    SequencedIds,
    build_runtime,
    make_bootstrap,
    make_config,
    make_snapshot,
    make_target,
    make_window,
    make_observation,
)
from hangma_bot.application.contracts import (
    GuideVersion,
    OperationStatus,
    ParticipantTerminal,
    ParticipantTerminalReason,
    ReadyResult,
    RegistrationResult,
    RuntimeMode,
    RuntimeTarget,
    TournamentStatus,
)

pytestmark = pytest.mark.asyncio


def _finished_snapshot():
    return make_snapshot(TournamentStatus.FINISHED)


async def test_registering_register_then_first_ready_then_running():
    """阶段 1 生命周期：registering 报名 → 报名成功 → 首次 ready → 等待 running。

    stage_no 为 None 且无 stage_open 确认点：报名成功后必须立即到位，
    到位确认以 (stage_no, stage_role) 身份键记录，None 不再充当未确认哨兵。
    """

    from fakes import wait_for_condition

    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.REGISTERING)),
        updates=[
            make_snapshot(TournamentStatus.RUNNING, my_games=["g1"]),
            _finished_snapshot(),
        ],
        game_factory=lambda gid: FakeGameSession(items=[]),
    )
    runtime, sink, *_ = build_runtime(session=session)
    run_task = asyncio.create_task(runtime.run())
    # 报名成功 → 首次 ready 全程无需放行 update。
    await wait_for_condition(lambda: "ready" in sink.lifecycle_events())
    assert session.register_calls == 1
    assert [(s.stage_no, s.observed_revision) for s in session.ready_calls] == [(None, 1)]
    session.grant_updates(1)  # RUNNING(g1)
    await wait_for_condition(lambda: session.game_opens == ["g1"])
    session.grant_updates(1)  # FINISHED
    terminal = await run_task

    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED


async def test_test_room_boot_on_finished_reuses_register_ready():
    """测试房间跨轮复用：启动时房间已 finished → 幂等报名 + ready 开启下一轮。

    打完本轮后再次 finished 是该身份正常终态（下一轮由进程重启承接）。
    """

    from fakes import wait_for_condition

    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.FINISHED)),
        updates=[
            make_snapshot(TournamentStatus.RUNNING, revision=2, my_games=["g1"]),
            make_snapshot(TournamentStatus.FINISHED, revision=3),
        ],
        game_factory=lambda gid: FakeGameSession(items=[]),
    )
    runtime, sink, *_ = build_runtime(
        session=session, target=make_target(mode=RuntimeMode.TEST_ROOM)
    )
    run_task = asyncio.create_task(runtime.run())
    # 冷启动于 finished 房：幂等报名 → 首次 ready（无需放行 update）。
    await wait_for_condition(lambda: len(session.ready_calls) >= 1)
    assert session.register_calls == 1
    session.grant_updates(1)  # RUNNING(g1)
    await wait_for_condition(lambda: session.game_opens == ["g1"])
    session.grant_updates(1)  # FINISHED：本轮完成 → 正常终态
    terminal = await run_task

    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    assert [(s.stage_no, s.observed_revision) for s in session.ready_calls] == [(None, 1)]
    assert session.register_calls == 1  # 已报名令牌幂等：只报名一次


async def test_test_room_finished_after_round_is_terminal():
    """测试房间本进程已打完一轮后 finished：正常终态，不再 ready 下一轮。"""

    from fakes import wait_for_condition

    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.REGISTERING)),
        updates=[
            make_snapshot(TournamentStatus.RUNNING, revision=2, my_games=["g1"]),
            _finished_snapshot(),
        ],
        game_factory=lambda gid: FakeGameSession(items=[]),
    )
    runtime, sink, *_ = build_runtime(
        session=session, target=make_target(mode=RuntimeMode.TEST_ROOM)
    )
    run_task = asyncio.create_task(runtime.run())
    await wait_for_condition(lambda: "ready" in sink.lifecycle_events())  # 阶段 1 首次 ready
    session.grant_updates(1)  # RUNNING(g1)
    await wait_for_condition(lambda: session.game_opens == ["g1"])
    session.grant_updates(1)  # FINISHED
    terminal = await run_task

    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    assert len(session.ready_calls) == 1  # 打完一轮后零追加 ready


async def test_test_room_finished_repeat_snapshot_no_duplicate_ready():
    """同一轮 finished 的重复快照不重复 ready：身份键确认后幂等。"""

    from fakes import wait_for_condition

    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.FINISHED)),
        updates=[
            make_snapshot(TournamentStatus.FINISHED, revision=2),
            make_snapshot(TournamentStatus.RUNNING, revision=3),
            make_snapshot(TournamentStatus.CLOSED, revision=4),
        ],
    )
    runtime, sink, *_ = build_runtime(
        session=session, target=make_target(mode=RuntimeMode.TEST_ROOM)
    )
    run_task = asyncio.create_task(runtime.run())
    await wait_for_condition(lambda: len(session.ready_calls) >= 1)
    session.grant_updates(1)  # 仍是 FINISHED（同轮重复快照）
    for _ in range(20):
        await asyncio.sleep(0)
    assert len(session.ready_calls) == 1  # 身份键已确认：零追加 ready
    session.grant_updates(2)  # RUNNING + CLOSED
    terminal = await run_task
    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_CLOSED


async def test_official_tournament_finished_at_startup_is_terminal():
    """正式赛事（非测试房间）启动即 finished：立即终态，不报名不到位。"""

    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.FINISHED))
    )
    runtime, sink, *_ = build_runtime(
        session=session,
        target=make_target(mode=RuntimeMode.OFFICIAL_TOURNAMENT),
    )
    terminal = await runtime.run()

    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    assert session.register_calls == 0
    assert session.ready_calls == []


async def test_register_once_then_finish_with_game():
    """报名幂等只触发一次；my_games 出现即开场次；finished 正常退出。"""

    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.REGISTERING)),
        updates=[
            make_snapshot(TournamentStatus.RUNNING, my_games=["g1"]),
            _finished_snapshot(),
        ],
        game_factory=lambda gid: FakeGameSession(
            items=[make_window(make_observation(game_id=gid))]
        ),
    )
    session.grant_updates(1)  # 先放行 RUNNING，让场次与窗口就绪
    runtime, sink, *_ = build_runtime(session=session)
    import asyncio

    from fakes import wait_for_condition

    run_task = asyncio.create_task(runtime.run())
    await wait_for_condition(lambda: session.opened_games["g1"].drained)
    session.grant_updates(1)  # 窗口处理完后再放行终态
    terminal = await run_task

    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    assert session.register_calls == 1
    assert session.game_opens == ["g1"]
    assert session.closed is True
    assert "registered" in sink.lifecycle_events()
    assert any(kind.value == "participant_finished" for kind in sink.kinds())


async def test_ready_per_stage_and_new_attempt_ids():
    """每个新阶段重新到位；阶段尝试标识逐次生成且互不相同。"""

    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.STAGE_DONE)),
        updates=[
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=1, revision=1, qualified=True),
            make_snapshot(TournamentStatus.RUNNING, stage_no=1, my_games=["g1"]),
            make_snapshot(TournamentStatus.STAGE_DONE, stage_no=1, revision=1),
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=2, revision=2, qualified=True),
            make_snapshot(TournamentStatus.RUNNING, stage_no=2, my_games=["g2"]),
            _finished_snapshot(),
        ],
        game_factory=lambda gid: FakeGameSession(items=[]),
    )
    runtime, sink, *_ = build_runtime(session=session)
    import asyncio

    from fakes import wait_for_condition

    run_task = asyncio.create_task(runtime.run())
    # 到位是后台任务：按事件步进放行，避免快照消费与到位完成竞态。
    session.grant_updates(1)  # STAGE_OPEN(1)
    await wait_for_condition(lambda: "ready" in sink.lifecycle_events())
    session.grant_updates(1)  # RUNNING(g1)
    await wait_for_condition(lambda: session.game_opens == ["g1"])
    session.grant_updates(2)  # STAGE_DONE + STAGE_OPEN(2)
    await wait_for_condition(lambda: len(session.ready_calls) >= 2)
    session.grant_updates(2)  # RUNNING(g2) + FINISHED
    terminal = await run_task

    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    assert [(s.stage_no, s.observed_revision) for s in session.ready_calls] == [
        (1, 1),
        (2, 2),
    ]
    attempts = [
        payload["stage_attempt_id"]
        for payload in (
            record.payload
            for record in sink.records
            if record.kind.value == "lifecycle_changed"
            and record.payload["event"] == "stage_attempt_started"
        )
    ]
    assert len(attempts) == 2
    assert attempts[0] != attempts[1]
    assert session.game_opens == ["g1", "g2"]


async def test_stage_open_qualified_false_is_normal_elimination():
    """stage_open + qualified=false 是正常淘汰，不是故障，也不到位。"""

    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.STAGE_DONE)),
        updates=[make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=1, revision=1, qualified=False)],
    )
    session.grant_updates(1)
    runtime, sink, *_ = build_runtime(session=session)
    terminal = await runtime.run()

    assert terminal.reason is ParticipantTerminalReason.ELIMINATED
    assert session.ready_calls == []
    assert session.game_opens == []


async def test_ready_not_qualified_rejection_becomes_elimination():
    """到位被名单外拒绝（409 NOT_QUALIFIED）转换为正常淘汰。"""

    session = FakeTournamentSession(
        bootstrap=make_bootstrap(
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=1, revision=1, qualified=True)
        ),
        ready_results=[
            ReadyResult(status=OperationStatus.REJECTED, official_code="NOT_QUALIFIED")
        ],
    )
    runtime, sink, *_ = build_runtime(session=session)
    terminal = await runtime.run()

    assert terminal.reason is ParticipantTerminalReason.ELIMINATED
    assert "NOT_QUALIFIED" in terminal.detail


async def test_empty_active_games_is_not_terminal():
    """active_games/my_games 为空只是阶段空窗，不退出。"""

    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=[])),
        updates=[
            make_snapshot(TournamentStatus.RUNNING, stage_no=1, my_games=[]),
            _finished_snapshot(),
        ],
    )
    session.grant_updates(2)
    runtime, sink, *_ = build_runtime(session=session)
    terminal = await runtime.run()

    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    assert session.game_opens == []


async def test_stage_crashed_voids_attempt_and_rediscovers_new_game():
    """stage_crashed 作废旧尝试并关闭旧场次；新尝试发现新 game_id。"""

    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.STAGE_DONE)),
        updates=[
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=1, revision=1, qualified=True),
            make_snapshot(TournamentStatus.RUNNING, stage_no=1, my_games=["g1"]),
            make_snapshot(
                TournamentStatus.RUNNING,
                stage_no=1,
                revision=1,
                crashed=True,
                my_games=["g1"],
                active_games=[],
            ),
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=1, revision=2, qualified=True),
            make_snapshot(TournamentStatus.RUNNING, stage_no=1, my_games=["g2"]),
            _finished_snapshot(),
        ],
        game_factory=lambda gid: FakeGameSession(items=[]),
    )
    session.grant_updates(6)
    runtime, sink, *_ = build_runtime(session=session)
    terminal = await runtime.run()

    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    assert "stage_attempt_voided" in sink.lifecycle_events()
    assert session.opened_games["g1"].close_reasons == ["stage_crashed"]
    assert session.game_opens == ["g1", "g2"]
    attempts = [
        record.payload["stage_attempt_id"]
        for record in sink.records
        if record.kind.value == "lifecycle_changed"
        and record.payload["event"] == "stage_attempt_started"
    ]
    assert len(attempts) == 2 and attempts[0] != attempts[1]


async def test_game_discovery_and_removal_follow_active_games():
    """新增 game_id 动态建会话；从 active_games 消失即回收，历史不驱动编排。"""

    session = FakeTournamentSession(
        bootstrap=make_bootstrap(
            make_snapshot(TournamentStatus.RUNNING, my_games=["g1"])
        ),
        updates=[
            make_snapshot(
                TournamentStatus.RUNNING, stage_no=1, my_games=["g1", "g2"], active_games=["g1", "g2"]
            ),
            # g1 完结：active 收缩，但累计历史 my_games 仍包含 g1。
            make_snapshot(
                TournamentStatus.RUNNING, stage_no=1, my_games=["g1", "g2"], active_games=["g2"]
            ),
            _finished_snapshot(),
        ],
        game_factory=lambda gid: FakeGameSession(items=[]),
    )
    runtime, sink, *_ = build_runtime(session=session)
    import asyncio

    from fakes import wait_for_condition

    run_task = asyncio.create_task(runtime.run())
    session.grant_updates(1)  # 双场快照：g2 开场
    from fakes import wait_for_condition as _wait

    await _wait(lambda: session.game_opens == ["g1", "g2"])
    session.grant_updates(1)  # active 收缩：g1 回收
    await wait_for_condition(
        lambda: session.opened_games["g1"].close_reasons == ["removed_from_active_games"]
    )
    session.grant_updates(1)  # FINISHED
    terminal = await run_task

    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    assert "g2" in session.opened_games
    assert session.opened_games["g2"].closed  # 运行结束时统一回收


async def test_concurrency_capped_by_config_m():
    """my_games 超过 config.M 时按确定性排序截断并留痕。"""

    session = FakeTournamentSession(
        bootstrap=make_bootstrap(
            make_snapshot(TournamentStatus.RUNNING, my_games=["g1", "g2", "g3"]),
            config=make_config(max_games=2),
        ),
        updates=[_finished_snapshot()],
    )
    session.grant_updates(1)
    runtime, sink, *_ = build_runtime(session=session)
    terminal = await runtime.run()

    assert session.game_opens == ["g1", "g2"]
    truncation = [
        record
        for record in sink.records
        if record.kind.value == "protocol_recovered"
        and record.payload.get("area") == "game_reconcile"
    ]
    assert truncation and "config.M" in truncation[0].payload["reason"]


async def test_initialize_terminal_returned_directly():
    """初始化返回参赛者终态时不再报名、到位或开场次。"""

    terminal = ParticipantTerminal(
        reason=ParticipantTerminalReason.AUTHENTICATION_FAILED,
        last_snapshot=None,
        detail="401",
    )
    session = FakeTournamentSession(bootstrap=terminal)
    runtime, sink, *_ = build_runtime(session=session)
    result = await runtime.run()

    assert result is terminal
    assert session.register_calls == 0
    assert session.game_opens == []
    assert session.closed is True


async def test_incompatible_guide_versions_rejected():
    """低于已适配版本或标记未知破坏性变化都进入不兼容终态。"""

    older = FakeTournamentSession(
        bootstrap=make_bootstrap(
            make_snapshot(TournamentStatus.REGISTERING), guide_version=7
        )
    )
    runtime, _sink, *_ = build_runtime(session=older)
    terminal = await runtime.run()
    assert terminal.reason is ParticipantTerminalReason.INCOMPATIBLE_GUIDE

    breaking = FakeTournamentSession(
        bootstrap=make_bootstrap(
            make_snapshot(TournamentStatus.REGISTERING), guide_version=9, breaking=True
        )
    )
    runtime2, _sink2, *_ = build_runtime(session=breaking, target=make_target(known_guide_version=8))
    terminal2 = await runtime2.run()
    assert terminal2.reason is ParticipantTerminalReason.INCOMPATIBLE_GUIDE


async def test_target_mismatch_is_terminal():
    """平台返回的赛事号与目标不一致时安全退出。"""

    session = FakeTournamentSession(
        bootstrap=make_bootstrap(
            make_snapshot(TournamentStatus.REGISTERING), tournament_id="other"
        )
    )
    runtime, _sink, *_ = build_runtime(session=session)
    terminal = await runtime.run()

    assert terminal.reason is ParticipantTerminalReason.TARGET_MISMATCH
    assert session.register_calls == 0


async def test_update_terminal_propagates_and_closes_games():
    """next_update 给出参赛者终态时传播并回收场次会话。"""

    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=["g1"])),
        updates=[
            ParticipantTerminal(
                reason=ParticipantTerminalReason.AUTHENTICATION_FAILED,
                last_snapshot=None,
                detail="token 失效",
            )
        ],
        game_factory=lambda gid: FakeGameSession(items=[]),
    )
    session.grant_updates(1)
    runtime, sink, *_ = build_runtime(session=session)
    terminal = await runtime.run()

    assert terminal.reason is ParticipantTerminalReason.AUTHENTICATION_FAILED
    assert session.opened_games["g1"].closed is True


async def test_register_rejection_backoff_then_terminal():
    """报名持续被拒绝时按有界退避重试，耗尽转永久故障终态。"""

    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.REGISTERING)),
        register_results=[
            RegistrationResult(status=OperationStatus.REJECTED, official_code="X1"),
            RegistrationResult(status=OperationStatus.REJECTED, official_code="X2"),
            RegistrationResult(status=OperationStatus.REJECTED, official_code="X3"),
            RegistrationResult(status=OperationStatus.REJECTED, official_code="X4"),
            RegistrationResult(status=OperationStatus.REJECTED, official_code="X5"),
        ],
    )
    runtime, sink, *_ = build_runtime(session=session)
    terminal = await runtime.run()

    assert terminal.reason is ParticipantTerminalReason.FATAL_PROTOCOL_ERROR
    assert session.register_calls == 5
    recovered = [
        record.payload
        for record in sink.records
        if record.kind.value == "protocol_recovered" and record.payload.get("area") == "register"
    ]
    assert len(recovered) == 4  # 4 次退避后第 5 次拒绝耗尽预算


async def test_active_games_is_authority_history_ignored():
    """active_games 是编排权威；my_games 历史绝不驱动开场。"""

    session = FakeTournamentSession(
        bootstrap=make_bootstrap(
            make_snapshot(
                TournamentStatus.RUNNING,
                stage_no=1,
                my_games=["g-old", "g-new"],
                active_games=["g-new"],
            )
        ),
        updates=[_finished_snapshot()],
    )
    session.grant_updates(1)
    runtime, sink, *_ = build_runtime(session=session)
    terminal = await runtime.run()
    assert session.game_opens == ["g-new"]

    # 阶段空窗：历史非空、活跃为空，不开场也不退出。
    idle = FakeTournamentSession(
        bootstrap=make_bootstrap(
            make_snapshot(
                TournamentStatus.STAGE_DONE,
                stage_no=1,
                my_games=["g-old"],
                active_games=[],
            )
        ),
        updates=[
            make_snapshot(
                TournamentStatus.RUNNING, stage_no=1, my_games=["g-old"], active_games=[]
            ),
            _finished_snapshot(),
        ],
    )
    idle.grant_updates(2)
    runtime2, _sink2, *_ = build_runtime(session=idle)
    terminal2 = await runtime2.run()
    assert idle.game_opens == []
    assert terminal2.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED


async def test_same_stage_revision_bump_single_ready_and_attempt():
    """同一阶段的修订号变化不重新到位、不轮换阶段尝试标识。"""

    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.STAGE_DONE)),
        updates=[
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=1, revision=1, qualified=True),
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=1, revision=2, qualified=True),
            make_snapshot(TournamentStatus.RUNNING, stage_no=1, my_games=["g1"]),
            _finished_snapshot(),
        ],
        game_factory=lambda gid: FakeGameSession(items=[]),
    )
    runtime, sink, *_ = build_runtime(session=session)
    import asyncio

    from fakes import wait_for_condition

    run_task = asyncio.create_task(runtime.run())
    session.grant_updates(1)  # STAGE_OPEN(rev1)
    await wait_for_condition(lambda: "ready" in sink.lifecycle_events())
    session.grant_updates(1)  # STAGE_OPEN(rev2)：修订号变化
    for _ in range(20):
        await asyncio.sleep(0)
    session.grant_updates(2)  # RUNNING + FINISHED
    terminal = await run_task

    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    assert [(s.stage_no, s.observed_revision) for s in session.ready_calls] == [(1, 1)]
    attempts = [
        record.payload["stage_attempt_id"]
        for record in sink.records
        if record.kind.value == "lifecycle_changed"
        and record.payload["event"] == "stage_attempt_started"
    ]
    assert len(attempts) == 1


async def test_ready_dispatched_then_snapshot_advances_keeps_captured_stage():
    """NF4 定向回归：ready 任务在派发时点捕获阶段身份。

    交错刻画：ready 任务已派发（捕获 (stage_no=1, revision=1)）、首次执行前
    快照被推进到同阶段新修订 (1, rev2)——首次 ready 必须仍按派发时点的捕获
    身份发出，而不是在任务开头重读快照把已派发命令静默丢弃（旧实现会在
    此处把命令换成 rev2 甚至因状态变化直接放弃）。

    本用例直接构造 supervisor 并手动推进两帧快照：公开运行时的任务 FIFO
    调度无法确定性产生「派发后、协程首执行前快照推进」的交错（协程步骤
    恒早于后续快照消费），因此对派发机制做白盒级定向验证；STALE 收敛路径
    由 test_ready_stale_stage_waits_not_elimination 覆盖。
    """

    from hangma_bot.application.audit import AuditTrail
    from hangma_bot.application.deadline import BudgetPolicy, ManualClock
    from hangma_bot.application.decision_loop import RuntimeServices
    from hangma_bot.application.tournament_supervisor import (
        SupervisionPolicy,
        TournamentSupervisor,
    )
    from fakes import FakePolicy, FakeRules, InMemoryAuditSink, SequencedIds, make_fake_sleep

    bootstrap = make_bootstrap(
        make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=1, revision=1, qualified=True)
    )
    session = FakeTournamentSession(bootstrap=bootstrap)
    clock = ManualClock()
    sink = InMemoryAuditSink()
    trail = AuditTrail(
        sink, run_id="r-nf4", tournament_id="t1", participant_id="p1", clock=clock
    )
    supervisor = TournamentSupervisor(
        bootstrap=bootstrap,
        session=session,
        services=RuntimeServices(
            rules=FakeRules(candidates=(DISCARD_3W, PASS), emergency=PASS),
            policy=FakePolicy(),
            audit=trail,
            clock=clock,
            ids=SequencedIds(),
            budget_policy=BudgetPolicy(),
        ),
        supervision=SupervisionPolicy(),
        sleep=make_fake_sleep(),
        mode=RuntimeMode.TEST_TOURNAMENT,
    )

    # 1) 启动快照处理：末尾派发 ready 任务，派发时点捕获 (1, rev1)。
    await supervisor._handle_snapshot(bootstrap.initial_snapshot)
    assert session.ready_calls == []  # 任务尚未执行
    # 2) 任务首次执行前，快照被推进到同阶段新修订 (1, rev2)。
    await supervisor._handle_snapshot(
        make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=1, revision=2, qualified=True)
    )
    # 3) 让派发的 ready 任务执行：首次 ready 必须携带捕获身份 (1, rev1)；
    # 确认后身份键生效，不得出现第二次到位。
    from fakes import wait_for_condition

    await wait_for_condition(lambda: len(session.ready_calls) >= 1)
    for _ in range(10):
        await asyncio.sleep(0)
    assert [(s.stage_no, s.observed_revision) for s in session.ready_calls] == [(1, 1)]
    assert "ready" in sink.lifecycle_events()


async def test_ready_stale_stage_waits_not_elimination():
    """STALE_STAGE 拒绝是阶段竞态，不是淘汰；等新快照后重新到位。"""

    session = FakeTournamentSession(
        bootstrap=make_bootstrap(
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=1, revision=1, qualified=True)
        ),
        ready_results=[
            ReadyResult(status=OperationStatus.REJECTED, official_code="STALE_STAGE"),
        ],
        updates=[
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=1, revision=2, qualified=True),
            _finished_snapshot(),
        ],
    )
    runtime, sink, *_ = build_runtime(session=session)
    import asyncio

    from fakes import wait_for_condition

    run_task = asyncio.create_task(runtime.run())
    session.grant_updates(1)  # 新阶段快照触发重新到位
    await wait_for_condition(lambda: len(session.ready_calls) >= 2)
    session.grant_updates(1)
    terminal = await run_task

    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    assert [(s.stage_no, s.observed_revision) for s in session.ready_calls] == [(1, 1), (1, 2)]


async def test_ready_unknown_rejection_bounded_then_fatal():
    """未知拒绝码按有界退避重试，耗尽转永久故障而非误判淘汰。"""

    session = FakeTournamentSession(
        bootstrap=make_bootstrap(
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=1, revision=1, qualified=True)
        ),
        ready_results=[
            ReadyResult(status=OperationStatus.REJECTED, official_code="TOURNAMENT_STARTED")
        ] * 5,
    )
    runtime, sink, *_ = build_runtime(session=session)
    terminal = await runtime.run()

    assert terminal.reason is ParticipantTerminalReason.FATAL_PROTOCOL_ERROR
    assert session.ready_calls and all(
        s.stage_no == 1 for s in session.ready_calls
    )


async def test_register_exception_retries_then_succeeds():
    """register 瞬时异常有界重试，恢复后正常报名并入审计。"""

    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.REGISTERING)),
        register_results=[
            RuntimeError("报名请求超时"),
            RegistrationResult(status=OperationStatus.ACCEPTED),
        ],
        updates=[_finished_snapshot()],
    )
    runtime, sink, *_ = build_runtime(session=session)
    import asyncio

    from fakes import wait_for_condition

    run_task = asyncio.create_task(runtime.run())
    await wait_for_condition(lambda: "registered" in sink.lifecycle_events())
    session.grant_updates(1)
    terminal = await run_task

    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    assert session.register_calls == 2
    assert any(
        record.payload.get("area") == "register"
        for record in sink.records
        if record.kind.value == "protocol_recovered"
    )


async def test_register_exception_exhausts_to_terminal():
    """register 持续异常耗尽预算后进入永久终态，不静默悬挂。"""

    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.REGISTERING)),
        register_results=[RuntimeError("持续故障")] * 6,
    )
    runtime, sink, *_ = build_runtime(session=session)
    terminal = await runtime.run()

    assert terminal.reason is ParticipantTerminalReason.FATAL_PROTOCOL_ERROR
    assert session.register_calls == 5  # 4 次退避后第 5 次耗尽


async def test_ready_exception_retries_then_succeeds():
    """ready 瞬时异常有界重试，不升级为身份终态。"""

    session = FakeTournamentSession(
        bootstrap=make_bootstrap(
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=1, revision=1, qualified=True)
        ),
        ready_results=[
            RuntimeError("到位请求超时"),
            ReadyResult(status=OperationStatus.ACCEPTED),
        ],
        updates=[_finished_snapshot()],
    )
    runtime, sink, *_ = build_runtime(session=session)
    import asyncio

    from fakes import wait_for_condition

    run_task = asyncio.create_task(runtime.run())
    await wait_for_condition(lambda: "ready" in sink.lifecycle_events())
    session.grant_updates(1)
    terminal = await run_task

    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    assert len(session.ready_calls) == 2


async def test_elimination_short_circuits_before_reconcile():
    """名单外淘汰终态确定后不再生成阶段尝试或开场次。"""

    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.STAGE_DONE)),
        updates=[
            make_snapshot(
                TournamentStatus.STAGE_OPEN,
                stage_no=1,
                revision=1,
                qualified=False,
                my_games=["g1"],
                active_games=["g1"],  # 陈旧的活跃列表不得诱导开场
            )
        ],
    )
    session.grant_updates(1)
    runtime, sink, *_ = build_runtime(session=session)
    terminal = await runtime.run()

    assert terminal.reason is ParticipantTerminalReason.ELIMINATED
    assert session.game_opens == []
    assert "stage_attempt_started" not in sink.lifecycle_events()



async def test_late_first_ready_rejection_stops_when_running_arrives():
    """阶段 1 首次 ready 迟到被拒（赛事已推进）：退避等待后重新评估，

    状态已 running 即停止到位，不把迟到拒绝重试成永久终态。
    """

    release = asyncio.Event()
    delays = []

    async def gated_sleep(seconds: float) -> None:
        delays.append(seconds)
        if not release.is_set():
            await release.wait()

    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.REGISTERING)),
        ready_results=[
            ReadyResult(status=OperationStatus.REJECTED, official_code="TOURNAMENT_STARTED")
        ],
        updates=[
            make_snapshot(TournamentStatus.RUNNING, my_games=["g1"]),
            _finished_snapshot(),
        ],
        game_factory=lambda gid: FakeGameSession(items=[]),
    )
    runtime, sink, *_ = build_runtime(session=session, sleep=gated_sleep)
    run_task = asyncio.create_task(runtime.run())

    from fakes import wait_for_condition

    await wait_for_condition(lambda: len(delays) >= 1)  # 首次 ready 被拒进入退避
    assert len(session.ready_calls) == 1
    session.grant_updates(1)  # RUNNING：到位命令已过期
    await wait_for_condition(lambda: session.game_opens == ["g1"])
    release.set()  # 放行退避睡眠：重新评估后不得再发第二次 ready
    for _ in range(20):
        await asyncio.sleep(0)
    assert len(session.ready_calls) == 1  # 迟到拒绝零追加重试
    session.grant_updates(1)  # FINISHED
    terminal = await run_task
    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED


async def test_register_retry_waits_before_next_call():
    """报名重试必须真正等待退避延迟，而不是瞬时烧完预算。"""

    import asyncio

    release = asyncio.Event()
    delays = []

    async def gated_sleep(seconds: float) -> None:
        delays.append(seconds)
        if not release.is_set():
            await release.wait()

    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.REGISTERING)),
        register_results=[
            RuntimeError("瞬时故障"),
            RegistrationResult(status=OperationStatus.ACCEPTED),
        ],
        updates=[_finished_snapshot()],
    )
    runtime, sink, *_ = build_runtime(session=session, sleep=gated_sleep)
    run_task = asyncio.create_task(runtime.run())

    from fakes import wait_for_condition

    await wait_for_condition(lambda: len(delays) >= 1)
    for _ in range(20):  # 延迟未释放：不得发起第二次报名
        await asyncio.sleep(0)
    assert session.register_calls == 1
    release.set()
    await wait_for_condition(lambda: "registered" in sink.lifecycle_events())
    assert session.register_calls == 2
    session.grant_updates(1)
    terminal = await run_task
    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED


async def test_ready_hang_times_out_then_recovers():
    """ready 永不返回时由应用层超时打断，按有界恢复重试。"""

    import asyncio

    from hangma_bot.application.tournament_supervisor import SupervisionPolicy

    class ReadyHangsThenAccepts(FakeTournamentSession):
        def __init__(self, **kwargs) -> None:
            super().__init__(**kwargs)
            self.ready_calls = []

        async def ready(self, expected_stage):
            self.ready_calls.append(expected_stage)
            if len(self.ready_calls) == 1:
                await asyncio.Future()  # 模拟适配器缺陷挂起
            return ReadyResult(status=OperationStatus.ACCEPTED)

    session = ReadyHangsThenAccepts(
        bootstrap=make_bootstrap(
            make_snapshot(TournamentStatus.STAGE_OPEN, stage_no=1, revision=1, qualified=True)
        ),
        updates=[_finished_snapshot()],
    )
    runtime, sink, *_ = build_runtime(
        session=session,
        supervision=SupervisionPolicy(ready_call_timeout_seconds=0.05),
    )
    run_task = asyncio.create_task(runtime.run())

    from fakes import wait_for_condition

    await wait_for_condition(lambda: "ready" in sink.lifecycle_events())
    assert len(session.ready_calls) == 2  # 挂起被超时打断后重试成功
    recovered = [
        record.payload
        for record in sink.records
        if record.kind.value == "protocol_recovered"
        and record.payload.get("area") == "ready"
    ]
    assert recovered and "到位调用异常" in recovered[0]["reason"]
    session.grant_updates(1)
    terminal = await run_task
    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED

