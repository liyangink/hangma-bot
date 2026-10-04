"""AutoMatchRuntime 行为测试（自动房等待/运行/收尾/隔离/取消）。

覆盖（free-match-start.md §5 Fake 验收）：等待开赛不调用 ready、房间终态宽限
收尾、宽限内补抓晚期场次、宽限耗尽记录缺失、closed/404 证据收尾语义（会话
终态透传）、并发场次上限诊断、取消清理与慢审计不阻塞动作路径。测试注入
确定性时钟/替身 sleep（tests/AGENTS.md），不产生真实等待。
"""

from __future__ import annotations

import asyncio
from typing import Callable, List, Optional

import pytest

from hangma_bot.application.auto_match_runtime import AutoMatchRuntime, AutoMatchSettings
from hangma_bot.application.contracts import (
    AuditKind,
    GameFinished,
    ParticipantTerminal,
    ParticipantTerminalReason,
    RuntimeMode,
    RuntimeTarget,
    TournamentStatus,
)

from fakes import (
    FakeGameSession,
    FakeTournamentSession,
    InMemoryAuditSink,
    ManualClock,
    SequencedIds,
    make_bootstrap,
    make_config,
    make_snapshot,
)


def auto_target(*, room_id: str = "", guide: int = 8) -> RuntimeTarget:
    return RuntimeTarget(
        mode=RuntimeMode.AUTO_MATCH,
        expected_tournament_id=room_id,
        known_guide_version=guide,
    )


def running_snapshot(active, my, *, revision: int = 2) -> object:
    return make_snapshot(
        status=TournamentStatus.RUNNING,
        my_games=tuple(my),
        active_games=tuple(active),
        revision=revision,
    )


def finished_snapshot(my, *, revision: int = 3) -> object:
    return make_snapshot(
        status=TournamentStatus.FINISHED,
        my_games=tuple(my),
        active_games=(),
        revision=revision,
    )


def registering_snapshot() -> object:
    return make_snapshot(status=TournamentStatus.REGISTERING, revision=1)


def make_finished_game(game_id: str) -> GameFinished:
    return GameFinished(game_id=game_id, final_scores=(8, 8, 8, 8), authoritative_seq=40)


def auto_events(sink) -> List[str]:
    out = []
    for record in sink.records:
        if record.kind is AuditKind.LIFECYCLE_CHANGED:
            payload = record.payload
            if payload.get("area") == "auto_match" and payload.get("event"):
                out.append(payload["event"])
    return out


def make_advancing_sleep(clock: ManualClock):
    """推进假时钟的 sleep：把 drain 宽限等真实时长压缩为时钟步进 + 让出。"""

    async def _sleep(seconds: float) -> None:
        _sleep.delays.append(seconds)
        clock.advance(max(0.0, seconds))
        await asyncio.sleep(0)

    _sleep.delays = []  # type: ignore[attr-defined]
    return _sleep


def build_auto_runtime(
    *,
    session,
    sink=None,
    target=None,
    settings: Optional[AutoMatchSettings] = None,
    clock: Optional[ManualClock] = None,
    sleep: Optional[Callable[[float], object]] = None,
    ids=None,
    policy=None,
):
    """组装 AutoMatchRuntime（默认替身与 fakes.build_runtime 对齐）。"""

    sink = sink if sink is not None else InMemoryAuditSink()
    clock = clock if clock is not None else ManualClock()
    ids = ids if ids is not None else SequencedIds()
    runtime = AutoMatchRuntime(
        session=session,
        policy=object() if policy is None else policy,  # 无动作窗口时策略不会被调用
        audit_sink=sink,
        target=target if target is not None else auto_target(),
        settings=settings,
        clock=clock,
        ids=ids,
        sleep=sleep if sleep is not None else make_advancing_sleep(clock),
    )
    return runtime, sink


def lifecycle_target_room_events(sink) -> List[str]:
    """participant_finished 记录的 reason 序列（出口语义断言用）。"""

    return [
        r.payload["reason"]
        for r in sink.records
        if r.kind is AuditKind.PARTICIPANT_FINISHED
    ]


@pytest.mark.asyncio
async def test_full_lifecycle_waiting_running_drain_finish() -> None:
    """等待（无 ready）→ 运行并发场次 → 房间 finished 宽限收尾 → 正常终态。

    全程 register/ready 调用数为 0；每场 GAME_FINISHED 保存；终态 reason 为
    tournament_finished。
    """

    bootstrap = make_bootstrap(
        snapshot=registering_snapshot(),
        config=make_config(max_games=2, rounds=1),
    )

    def game_factory(game_id: str):
        return FakeGameSession(items=[make_finished_game(game_id)])

    session = FakeTournamentSession(
        bootstrap=bootstrap,
        updates=[
            running_snapshot(active=["g1", "g2"], my=["g1", "g2"]),
            finished_snapshot(my=["g1", "g2"]),
        ],
        game_factory=game_factory,
    )
    runtime, sink = build_auto_runtime(session=session)
    run_task = asyncio.create_task(runtime.run())
    await wait_till(lambda: "waiting" in auto_events(sink))
    session.grant_updates(1)
    await wait_till(lambda: session.game_opens == ["g1", "g2"])
    session.grant_updates(1)
    terminal = await asyncio.wait_for(run_task, timeout=5)
    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    events = auto_events(sink)
    for expected in ("waiting", "running", "draining", "finished"):
        assert expected in events, "缺少生命周期事件 " + expected + "：" + ",".join(events)
    # 不调用 register/ready。
    assert session.register_calls == 0
    assert session.ready_calls == []
    # 每场结束立即保存 GAME_FINISHED。
    game_finished = [r for r in sink.records if r.kind is AuditKind.GAME_FINISHED]
    assert {r.context.game_id for r in game_finished} == {"g1", "g2"}
    assert all(r.payload["final_scores"] == [8, 8, 8, 8] for r in game_finished)
    # 出口审计。
    assert lifecycle_target_room_events(sink) == ["tournament_finished"]
    assert session.closed


@pytest.mark.asyncio
async def test_late_game_final_recovered_during_drain() -> None:
    """运行期已离开 active 的场次（终局未取）：房间 finished 宽限内补抓成功。"""

    bootstrap = make_bootstrap(snapshot=registering_snapshot(), config=make_config(max_games=2))
    session = FakeTournamentSession(
        bootstrap=bootstrap,
        updates=[
            running_snapshot(active=["g1"], my=["g1", "g2"]),  # g2 已结束但未记录终局
            finished_snapshot(my=["g1", "g2"]),
        ],
        game_factory=lambda gid: FakeGameSession(items=[make_finished_game(gid)]),
    )
    runtime, sink = build_auto_runtime(session=session)
    run_task = asyncio.create_task(runtime.run())
    await wait_till(lambda: "waiting" in auto_events(sink))
    session.grant_updates(1)
    await wait_till(lambda: session.game_opens == ["g1"])
    session.grant_updates(1)
    terminal = await asyncio.wait_for(run_task, timeout=5)
    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    # 补抓 g2 后才收尾；game_opens 顺序 g1（运行期）→ g2（宽限补抓）。
    assert session.game_opens == ["g1", "g2"]
    game_finished = [r for r in sink.records if r.kind is AuditKind.GAME_FINISHED]
    assert {r.context.game_id for r in game_finished} == {"g1", "g2"}
    assert "drain_missing_finals" not in [
        r.payload.get("reason") for r in sink.records if r.kind is AuditKind.PROTOCOL_RECOVERED
    ]


@pytest.mark.asyncio
async def test_drain_grace_expiry_records_missing_final() -> None:
    """场次在宽限内仍未取得终局：宽限耗尽后记录缺失，不伪造终局（终态仍按
    房间 finished 证据收尾，缺失明细进审计）。"""

    clock = ManualClock()
    bootstrap = make_bootstrap(snapshot=registering_snapshot(), config=make_config(max_games=2))
    session = FakeTournamentSession(
        bootstrap=bootstrap,
        updates=[
            running_snapshot(active=["g1"], my=["g1"]),
            finished_snapshot(my=["g1"]),
        ],
        game_factory=lambda gid: FakeGameSession(items=[]),  # 该场永不返回终局
    )
    runtime, sink = build_auto_runtime(session=session, clock=clock)
    run_task = asyncio.create_task(runtime.run())
    await wait_till(lambda: "waiting" in auto_events(sink))
    session.grant_updates(1)
    await wait_till(lambda: session.game_opens == ["g1"])
    session.grant_updates(1)
    await wait_till(lambda: "draining" in auto_events(sink))
    # 推进时钟越过默认 45s 宽限。
    clock.advance(46)
    terminal = await asyncio.wait_for(run_task, timeout=5)
    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    assert "g1" in terminal.detail
    missing_records = [
        r
        for r in sink.records
        if r.kind is AuditKind.PROTOCOL_RECOVERED
        and r.payload.get("reason") == "drain_missing_finals"
    ]
    assert missing_records and missing_records[0].payload["missing_games"] == ["g1"]
    # 缺失场次没有 GAME_FINISHED（不能全记零分或伪装完整）。
    assert not [r for r in sink.records if r.kind is AuditKind.GAME_FINISHED]


@pytest.mark.asyncio
async def test_session_terminal_passthrough() -> None:
    """会话返回分类终态（如房间 404 无完赛证据 → matching_unavailable）时
    运行时原样透传并留出口审计。

    contract-vectors behaviour_cases auto-404-without-finish-evidence：
    结果部分/未知——绝无伪造终局（零 GAME_FINISHED/零零分）或 complete 宣称。
    """

    terminal = ParticipantTerminal(
        reason=ParticipantTerminalReason.MATCHING_UNAVAILABLE,
        last_snapshot=None,
        detail="目标房 404 且无 finished 证据：结果缺失/未知",
    )
    bootstrap = make_bootstrap(snapshot=registering_snapshot(), config=make_config())
    session = FakeTournamentSession(bootstrap=bootstrap, updates=[terminal])
    runtime, sink = build_auto_runtime(session=session)
    run_task = asyncio.create_task(runtime.run())
    await wait_till(lambda: "waiting" in auto_events(sink))
    session.grant_updates(1)
    result = await asyncio.wait_for(run_task, timeout=5)
    assert result is terminal
    assert lifecycle_target_room_events(sink) == ["matching_unavailable"]
    assert "matching_stopped" in auto_events(sink)
    # 向量断言：没有伪造任何 GAME_FINISHED（含零分）与 complete 宣称。
    assert not [r for r in sink.records if r.kind is AuditKind.GAME_FINISHED]
    assert "finished" not in auto_events(sink)
    finished_records = [
        r for r in sink.records if r.kind is AuditKind.PARTICIPANT_FINISHED
    ]
    assert finished_records and "未知" in finished_records[0].payload["detail"]


@pytest.mark.asyncio
async def test_initialize_terminal_early_exit() -> None:
    """初始化返回分类终态（容量/认证等）：早退出口完整留痕，会话被关闭。"""

    class CapacitySession(FakeTournamentSession):
        async def initialize(self, target):  # noqa: ARG002
            self.initialize_calls.append(target)
            return ParticipantTerminal(
                reason=ParticipantTerminalReason.CAPACITY_LIMIT,
                last_snapshot=None,
                detail="MATCH_LIMIT_REACHED：达到同时 16 场上限",
            )

    session = CapacitySession(bootstrap=make_bootstrap(snapshot=registering_snapshot()))
    runtime, sink = build_auto_runtime(session=session)
    terminal = await asyncio.wait_for(runtime.run(), timeout=5)
    assert terminal.reason is ParticipantTerminalReason.CAPACITY_LIMIT
    manifests = [r for r in sink.records if r.kind is AuditKind.RUN_MANIFEST]
    assert manifests and manifests[0].payload["early_exit"] is True
    # audit-plus-v1 声明（审计线反馈修正）：manifest 必须携带 capture_profile，
    # 否则验证器按 legacy 处理（不收紧增强校验）。
    assert manifests[0].payload["capture_profile"] == "audit-plus-v1"
    assert manifests[0].payload["audit_producer"] == "application"
    assert isinstance(manifests[0].payload["source_namespace"], str)
    # 发现模式空目标：身份发现前的记录 tournament_id 占位 "unknown"（信封完整性）。
    assert manifests[0].context.tournament_id == "unknown"
    # 终态事件唯一归应用层（活场双层重复修正）：matching_stopped 与
    # PARTICIPANT_FINISHED 各恰好一次。
    assert auto_events(sink) == ["matching_stopped"]
    assert lifecycle_target_room_events(sink) == ["capacity_limit"]
    assert session.closed


@pytest.mark.asyncio
async def test_cancel_during_running_closes_session() -> None:
    """运行中取消：CancelledError 传出、PARTICIPANT_FINISHED(cancelled) 留痕、
    会话与场次被清理（无泄漏）。"""

    bootstrap = make_bootstrap(snapshot=registering_snapshot(), config=make_config(max_games=2))
    session = FakeTournamentSession(
        bootstrap=bootstrap,
        updates=[running_snapshot(active=["g1"], my=["g1"])],
        game_factory=lambda gid: FakeGameSession(items=[]),
    )
    runtime, sink = build_auto_runtime(session=session)
    run_task = asyncio.create_task(runtime.run())
    await wait_till(lambda: "waiting" in auto_events(sink))
    session.grant_updates(1)
    await wait_till(lambda: session.game_opens == ["g1"])
    run_task.cancel()
    outcome = await asyncio.gather(run_task, return_exceptions=True)
    assert isinstance(outcome[0], asyncio.CancelledError)
    assert lifecycle_target_room_events(sink) == ["cancelled"]
    assert session.closed


@pytest.mark.asyncio
async def test_active_games_over_config_m_diagnostic() -> None:
    """返回场次多于 config.M：显式诊断并只编排能力范围内场次（不静默扩展）。"""

    bootstrap = make_bootstrap(snapshot=registering_snapshot(), config=make_config(max_games=2))
    session = FakeTournamentSession(
        bootstrap=bootstrap,
        updates=[running_snapshot(active=["g1", "g2", "g3"], my=["g1", "g2", "g3"])],
        game_factory=lambda gid: FakeGameSession(items=[make_finished_game(gid)]),
    )
    runtime, sink = build_auto_runtime(session=session)
    run_task = asyncio.create_task(runtime.run())
    await wait_till(lambda: "waiting" in auto_events(sink))
    session.grant_updates(1)
    await wait_till(lambda: len(session.game_opens) == 2)
    diagnostics = [
        r
        for r in sink.records
        if r.kind is AuditKind.PROTOCOL_RECOVERED
        and r.payload.get("reason") == "active_exceeds_config_m"
    ]
    assert diagnostics and diagnostics[0].payload["active_count"] == 3
    assert diagnostics[0].payload["config_max_games"] == 2
    run_task.cancel()
    await asyncio.gather(run_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_slow_degraded_audit_does_not_block_terminal() -> None:
    """审计槽降级不阻塞动作/终态路径；运行结束报告 audit_degraded=True。"""

    bootstrap = make_bootstrap(snapshot=registering_snapshot(), config=make_config(max_games=2))
    session = FakeTournamentSession(
        bootstrap=bootstrap,
        updates=[
            running_snapshot(active=["g1"], my=["g1"]),
            finished_snapshot(my=["g1"]),
        ],
        game_factory=lambda gid: FakeGameSession(items=[make_finished_game(gid)]),
    )
    sink = InMemoryAuditSink(degraded=True)
    runtime, _ = build_auto_runtime(session=session, sink=sink)
    run_task = asyncio.create_task(runtime.run())
    await wait_till(lambda: "waiting" in auto_events(sink))
    session.grant_updates(1)
    session.grant_updates(1)
    terminal = await asyncio.wait_for(run_task, timeout=5)
    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    assert runtime.audit_degraded is True


@pytest.mark.asyncio
async def test_ten_game_concurrency_at_config_m() -> None:
    """config.M=10 的真实十场并发（free-match §5 验收项，不再用 M=2 冒充）：

    运行期按 active_games 一次开满 10 场、每场独立 GameTask/会话；房间
    finished 后宽限收尾，10 场 GAME_FINISHED 全部保存，无缺失诊断。
    """

    game_ids = ["g{:02d}".format(i) for i in range(1, 11)]
    bootstrap = make_bootstrap(
        snapshot=registering_snapshot(),
        config=make_config(max_games=10, rounds=1),
    )
    session = FakeTournamentSession(
        bootstrap=bootstrap,
        updates=[
            running_snapshot(active=game_ids, my=game_ids),
            finished_snapshot(my=game_ids),
        ],
        game_factory=lambda gid: FakeGameSession(items=[make_finished_game(gid)]),
    )
    runtime, sink = build_auto_runtime(session=session)
    run_task = asyncio.create_task(runtime.run())
    await wait_till(lambda: "waiting" in auto_events(sink))
    session.grant_updates(1)
    # 运行期一次开满 config.M=10 场并发（不依赖收尾期补抓）。
    await wait_till(lambda: len(session.game_opens) == 10)
    assert session.game_opens == game_ids
    assert "draining" not in auto_events(sink)  # 开满发生在 running 期
    session.grant_updates(1)
    terminal = await asyncio.wait_for(run_task, timeout=8)
    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    game_finished = [r for r in sink.records if r.kind is AuditKind.GAME_FINISHED]
    assert {r.context.game_id for r in game_finished} == set(game_ids)
    assert len(game_finished) == 10
    assert not [
        r
        for r in sink.records
        if r.kind is AuditKind.PROTOCOL_RECOVERED
        and r.payload.get("reason") == "drain_missing_finals"
    ]
    # 不调用 register/ready。
    assert session.register_calls == 0
    assert session.ready_calls == []
    # 事件序列完整。
    events = auto_events(sink)
    for expected in ("waiting", "running", "draining", "finished"):
        assert expected in events


async def wait_till(condition, *, limit: int = 5000) -> None:
    """事件循环内轮询条件（与 fakes.wait_for_condition 同构，本地复制避免
    修改共享测试文件）。"""

    for _ in range(limit):
        try:
            if condition():
                return
        except (KeyError, IndexError):
            pass
        await asyncio.sleep(0)
    raise AssertionError("等待条件超时")


@pytest.mark.asyncio
async def test_active_removal_during_dedicated_release_preserves_final_without_reopen():
    """权威终局已收到但槽回收未完，active移除不能丢终局或再次开桌。"""
    from hangma_bot.application.decision_compute import BoundedDecisionCompute, DecisionComputeSettings
    from test_decision_compute import ControlFactory
    releasing, released = asyncio.Event(), asyncio.Event()

    class GatedCompute(BoundedDecisionCompute):
        async def release_game(self, game_id):
            releasing.set()
            await released.wait()
            await super().release_game(game_id)

    compute = GatedCompute(ControlFactory(), execution_id="control-source-v1", clock=ManualClock(),
        settings=DecisionComputeSettings(workers=1, max_pending=0, per_game_workers=True, startup_seconds=2))
    bootstrap = make_bootstrap(snapshot=running_snapshot(["g1"], ["g1"]), config=make_config(max_games=1))
    game = FakeGameSession(items=[make_finished_game("g1")])
    session = FakeTournamentSession(bootstrap=bootstrap,
        updates=[running_snapshot([], ["g1"], revision=3), finished_snapshot(["g1"], revision=4)],
        game_factory=lambda gid: game)
    runtime, sink = build_auto_runtime(session=session, policy=compute)
    await compute.start()
    running = asyncio.create_task(runtime.run())
    try:
        await asyncio.wait_for(releasing.wait(), 2)
        session.grant_updates(1)
        await wait_till(lambda: "game_closed" in auto_events(sink))
        released.set()
        await wait_till(lambda: game.closed)
        session.grant_updates(1)
        terminal = await asyncio.wait_for(running, 5)
        assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
        assert session.game_opens == ["g1"]
        assert len([r for r in sink.records if r.kind is AuditKind.GAME_FINISHED]) == 1
        assert compute.snapshot()["bound_games"] == compute.snapshot()["releasing_games"] == 0
    finally:
        released.set()
        if not running.done():
            running.cancel()
        await asyncio.gather(running, return_exceptions=True)
        await compute.close()
