"""每桌专属计算的公开进程行为；不以扩大共享池冒充桌隔离。"""
import asyncio
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest

from fakes import (DISCARD_3W, FakeGameSession, FakeRules, FakeTournamentSession,
                   InMemoryAuditSink, SequencedIds, build_runtime, make_bootstrap,
                   make_competition, make_config, make_observation, make_snapshot, make_window)
from test_decision_compute import ControlFactory, budget, request, service, wait_snapshot
from test_compute_unsent_deadline import PackingGateText, until
from hangma_bot.application.contracts import (GameFailed, GameFinished,
                                             ParticipantTerminalReason, TournamentStatus)
from hangma_bot.application.audit import AuditTrail
from hangma_bot.application.deadline import BoundedBackoff, BudgetPolicy, ManualClock, SystemClock
from hangma_bot.application.decision_compute import (
    BoundedDecisionCompute, DecisionComputeError, DecisionComputeSettings,
)
from hangma_bot.application.game_task import GameTask, GameTaskStatus
from hangma_bot.application.decision_loop import RuntimeServices, run_action_window
from hangma_bot.policy.interface import DecisionBudget


def dedicated(workers=2, **settings):
    return service(workers=workers, max_pending=0, per_game_workers=True, **settings)


def pid(plan):
    return int(next(p.value for p in plan.candidates[0].score_parts if p.name == 'child_pid'))


def assert_closed(compute):
    state = compute.snapshot()
    for name in ('live_processes', 'owned', 'pending', 'active', 'current',
                 'bound_games', 'releasing_games', 'transport_inflight',
                 'transport_threads_alive', 'late_reap_inflight', 'late_reap_threads_alive'):
        assert state[name] == 0, (name, state)


@pytest.mark.asyncio
async def test_ten_games_keep_ten_distinct_preheated_processes_until_release():
    compute = dedicated(workers=10, startup_seconds=15)
    await compute.start()
    try:
        assert compute.snapshot()['ready'] == 10
        first = await asyncio.gather(*(compute.choose(request(f'fast:first-{i}', f'g{i}'), budget())
                                       for i in range(10)))
        first_pids = list(map(pid, first))
        assert len(set(first_pids)) == 10
        second = await asyncio.gather(*(compute.choose(request(f'fast:second-{i}', f'g{i}', 11), budget())
                                        for i in reversed(range(10))))
        assert list(map(pid, second)) == list(reversed(first_pids))
        assert compute.snapshot()['bound_games'] == 10
        assert compute.snapshot()['process_starts'] == 10
        assert compute.snapshot()['pending'] == 0
        with pytest.raises(DecisionComputeError, match='GAME_CAPACITY'):
            await compute.acquire_game('eleventh')
        await asyncio.gather(*(compute.release_game(f'g{i}') for i in range(10)))
        assert compute.snapshot()['bound_games'] == 0
    finally:
        await compute.close()
    assert_closed(compute)


@pytest.mark.asyncio
async def test_hung_table_never_occupies_other_tables_worker_or_queue():
    compute = dedicated(max_job_seconds=.5, abandon_grace_seconds=.03)
    await compute.start()
    slow = None
    try:
        a_pid = pid(await compute.choose(request('fast:a-before', 'a'), budget()))
        b_pid = pid(await compute.choose(request('fast:b-before', 'b'), budget()))
        assert a_pid != b_pid
        slow = asyncio.create_task(compute.choose(request('hang:a', 'a', 11), budget()))
        await wait_snapshot(compute, 'dispatched', 3)
        started = time.monotonic()
        other = await compute.choose(request('fast:b-during', 'b', 11), budget(.3))
        assert pid(other) == b_pid
        assert time.monotonic() - started < .3
        assert compute.snapshot()['pending'] == 0
        slow.cancel()
        with pytest.raises(asyncio.CancelledError):
            await slow
        await compute.release_game('a')
        await wait_snapshot(compute, 'ready', 2)
        assert pid(await compute.choose(request('fast:b-after', 'b', 12), budget())) == b_pid
    finally:
        if slow is not None and not slow.done():
            slow.cancel()
            await asyncio.gather(slow, return_exceptions=True)
        await compute.close()
    assert_closed(compute)


@pytest.mark.asyncio
async def test_release_waits_old_job_before_rebinding_without_borrowing_another_table():
    compute = dedicated(abandon_grace_seconds=.3)
    await compute.start()
    old = release = None
    try:
        a_pid = pid(await compute.choose(request('fast:a', 'a'), budget()))
        b_pid = pid(await compute.choose(request('fast:b', 'b'), budget()))
        old = asyncio.create_task(compute.choose(request('slow:a', 'a', 11), budget()))
        await wait_snapshot(compute, 'dispatched', 3)
        release = asyncio.create_task(compute.release_game('a'))
        await wait_snapshot(compute, 'releasing_games', 1)
        assert not release.done()
        with pytest.raises(DecisionComputeError, match='GAME_RELEASING'):
            await compute.acquire_game('a')
        with pytest.raises(DecisionComputeError, match='GAME_CAPACITY'):
            await compute.acquire_game('c')
        assert pid(await compute.choose(request('fast:b-during', 'b', 11), budget())) == b_pid
        with pytest.raises(DecisionComputeError, match='GAME_RELEASED'):
            await old
        await release
        assert compute.snapshot()['bound_games'] == 1
        assert pid(await compute.choose(request('fast:c', 'c'), budget())) == a_pid
        assert compute.snapshot()['process_starts'] == 2
        assert compute.snapshot()['releasing_games'] == 0
    finally:
        await compute.close()
        if old is not None:
            await asyncio.gather(old, return_exceptions=True)
        if release is not None:
            await asyncio.gather(release, return_exceptions=True)
    assert_closed(compute)


@pytest.mark.asyncio
async def test_crash_restarts_only_own_slot_and_retains_game_binding():
    compute = dedicated(max_restarts=1)
    await compute.start()
    try:
        a_pid = pid(await compute.choose(request('fast:a', 'a'), budget()))
        b_pid = pid(await compute.choose(request('fast:b', 'b'), budget()))
        with pytest.raises(DecisionComputeError, match='WORKER_FAILED'):
            await compute.choose(request('crash:a', 'a', 11), budget())
        await wait_snapshot(compute, 'ready', 2)
        assert compute.snapshot()['bound_games'] == 2
        assert pid(await compute.choose(request('fast:a-new', 'a', 12), budget())) != a_pid
        assert pid(await compute.choose(request('fast:b-stable', 'b', 11), budget())) == b_pid
        assert compute.snapshot()['restarts'] == 1
    finally:
        await compute.close()
    assert_closed(compute)


@pytest.mark.asyncio
@pytest.mark.parametrize('workers', (1, 2))
async def test_exhausted_dead_slot_rebinds_to_emergency_without_borrowing_live_table(workers):
    """进程崩溃且禁止重启后，新桌仍消费窗口并实际提交合法紧急动作。"""
    compute = dedicated(workers=workers, max_restarts=0)
    await compute.start()
    try:
        await compute.choose(request('fast:a', 'a'), budget())
        b_pid = pid(await compute.choose(request('fast:b', 'b'), budget())) if workers > 1 else None
        with pytest.raises(DecisionComputeError, match='WORKER_FAILED'):
            await compute.choose(request('crash:a', 'a', 11), budget())
        await compute.release_game('a')
        await wait_snapshot(compute, 'live_processes', workers - 1)
        await compute.acquire_game('new-a')
        assert compute.snapshot()['bound_games'] == workers
        with pytest.raises(DecisionComputeError, match='^GAME_WORKER_NOT_READY$'):
            await compute.choose(request('fast:new-a', 'new-a'), budget())
        if workers > 1:
            assert pid(await compute.choose(request('fast:b-stable', 'b', 11), budget())) == b_pid

        clock, sink = SystemClock(), InMemoryAuditSink()
        services = RuntimeServices(rules=FakeRules(candidates=[DISCARD_3W], emergency=DISCARD_3W),
            policy=compute, audit=AuditTrail(sink, run_id='dead-slot-public', tournament_id='t1',
                participant_id='p1', clock=clock), clock=clock, ids=SequencedIds(),
            budget_policy=BudgetPolicy())
        session = FakeGameSession()
        window = make_window(make_observation(game_id='new-a'), received_at=clock.now(), timeout=1)
        result = await run_action_window(session=session, window=window, services=services,
                                         competition=make_competition(), stage_attempt_id=None)
        assert result.outcome_kind == 'accepted'
        assert result.sent_attempts == len(session.submitted) == 1
        assert session.submitted[0].action == DISCARD_3W
        assert compute.snapshot()['process_starts'] == workers
        assert compute.snapshot()['restarts'] == 0
        await compute.release_game('new-a')
    finally:
        await compute.close()
    assert_closed(compute)


@pytest.mark.asyncio
async def test_same_table_new_window_waits_only_its_superseded_job():
    compute = dedicated(abandon_grace_seconds=.3)
    await compute.start()
    old = None
    try:
        a_pid = pid(await compute.choose(request('fast:a', 'a'), budget()))
        b_pid = pid(await compute.choose(request('fast:b', 'b'), budget()))
        old = asyncio.create_task(compute.choose(request('slow:a', 'a', 11), budget()))
        await wait_snapshot(compute, 'dispatched', 3)
        newer = asyncio.create_task(compute.choose(request('fast:a-new', 'a', 12), budget()))
        await wait_snapshot(compute, 'pending', 1)
        assert pid(await compute.choose(request('fast:b', 'b', 11), budget())) == b_pid
        with pytest.raises(DecisionComputeError, match='SUPERSEDED'):
            await old
        assert pid(await newer) == a_pid
    finally:
        await compute.close()
        if old is not None:
            await asyncio.gather(old, return_exceptions=True)
    assert_closed(compute)


def test_per_game_mode_rejects_non_boolean_setting():
    with pytest.raises(ValueError, match='per_game_workers'):
        DecisionComputeSettings(per_game_workers=1)


@pytest.mark.asyncio
async def test_official_capacity_is_checked_before_constructing_game_services():
    compute = dedicated(workers=2)
    session = FakeTournamentSession(bootstrap=make_bootstrap(
        make_snapshot(TournamentStatus.RUNNING, my_games=['g1']), config=make_config(max_games=3)))
    runtime, *_ = build_runtime(session=session, policy=compute)
    try:
        terminal = await runtime.run()
        assert terminal.reason is ParticipantTerminalReason.FATAL_PROTOCOL_ERROR
        assert '官方 config.M' in terminal.detail
        assert session.game_opens == []
        assert session.closed
    finally:
        await compute.close()
    assert_closed(compute)


@pytest.mark.asyncio
async def test_expired_parent_encoding_keeps_own_thread_without_blocking_other_table():
    """控制父侧编码尚未退出的窗口，另一桌仍在原预算内复用自己的PID。"""
    PackingGateText.started.clear()
    PackingGateText.release.clear()
    clock = ManualClock(wait_scale=1)
    compute = BoundedDecisionCompute(ControlFactory(), execution_id='control-source-v1',
        clock=clock, settings=DecisionComputeSettings(workers=2, max_pending=0,
            per_game_workers=True, startup_seconds=2, max_job_seconds=1))
    await compute.start()
    expired = None
    try:
        long_budget = DecisionBudget(101, 102, 102.1)
        b_pid = pid(await compute.choose(request('fast:b-before', 'b'), long_budget))
        gated = request('fast:a-gated', 'a')
        gated = replace(gated, competition=replace(gated.competition,
            tournament_id=PackingGateText('public-parent-encoding-gate')))
        expired = asyncio.create_task(compute.choose(gated, DecisionBudget(100.02, 100.04, 100.06)))
        await until(PackingGateText.started.is_set)
        clock.advance(.1)
        with pytest.raises(DecisionComputeError, match='^DEADLINE$'):
            await expired
        assert compute.snapshot()['active'] == compute.snapshot()['transport_inflight'] == 1
        for seq in (11, 12):
            assert pid(await compute.choose(request(f'fast:b-{seq}', 'b', seq), long_budget)) == b_pid
        assert compute.snapshot()['active'] == compute.snapshot()['transport_inflight'] == 1
        assert compute.snapshot()['pending'] == 0
        PackingGateText.release.set()
        await until(lambda: compute.snapshot()['owned'] == 0)
        await compute.release_game('a')
        assert compute.snapshot()['process_starts'] == 2
        assert compute.snapshot()['faults'] == compute.snapshot()['restarts'] == 0
        assert compute.snapshot()['peak_transport'] <= 2
    finally:
        PackingGateText.release.set()
        await compute.close()
        if expired is not None:
            await asyncio.gather(expired, return_exceptions=True)
    assert_closed(compute)


class RecordingAudit:
    def __init__(self):
        self.records = []

    def emit(self, kind, payload, **context):
        self.records.append((kind, payload, context))


def lifecycle_task(session, started, finished):
    services = SimpleNamespace(audit=RecordingAudit(), compute_game_started=started,
                               compute_game_finished=finished)
    task = GameTask(game_id='g1', session=session, services=services,
                    competition_provider=make_competition, stage_attempt_provider=lambda: 'stage1',
                    item_backoff=BoundedBackoff(), sleep=asyncio.sleep)
    return task, services.audit


@pytest.mark.asyncio
@pytest.mark.parametrize('item,status', [
    (GameFinished('g1', (0, 0, 0, 0), 11), GameTaskStatus.FINISHED),
    (GameFailed(game_id='g1', recoverable=True, reason='断流'), GameTaskStatus.RECOVERABLE_FAILURE),
    (GameFailed(game_id='g1', recoverable=False, reason='永久故障'), GameTaskStatus.UNRECOVERABLE_FAILURE),
])
async def test_game_task_terminal_always_releases_binding(item, status):
    calls = []

    async def started(game):
        calls.append(('acquire', game))

    async def finished(game):
        calls.append(('release', game))

    task, _ = lifecycle_task(FakeGameSession(items=[item]), started, finished)
    assert (await task.run()).status is status
    assert calls == [('acquire', 'g1'), ('release', 'g1')]


@pytest.mark.asyncio
async def test_game_task_repeated_cancellation_waits_for_real_release():
    acquired, releasing, released = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def started(game):
        acquired.set()

    async def finished(game):
        releasing.set()
        await released.wait()

    task, _ = lifecycle_task(FakeGameSession(), started, finished)
    running = asyncio.create_task(task.run())
    await acquired.wait()
    running.cancel()
    await releasing.wait()
    running.cancel()
    await asyncio.sleep(.01)
    assert not running.done()
    released.set()
    with pytest.raises(asyncio.CancelledError):
        await running


@pytest.mark.asyncio
async def test_authoritative_finish_survives_cancellation_during_compute_release():
    """终局已取得时，关闭催促只等待资源回收，不能把官方结果改成未知。"""
    releasing, released = asyncio.Event(), asyncio.Event()

    async def started(game):
        pass

    async def finished(game):
        releasing.set()
        await released.wait()

    task, _ = lifecycle_task(FakeGameSession(items=[GameFinished('g1', (1, 2, 3, 4), 11)]),
                             started, finished)
    running = asyncio.create_task(task.run())
    await releasing.wait()
    running.cancel()
    await asyncio.sleep(.01)
    assert not running.done()
    released.set()
    assert (await running).status is GameTaskStatus.FINISHED


@pytest.mark.asyncio
async def test_game_task_release_failure_is_audited_without_masking_terminal():
    async def started(game):
        pass

    async def finished(game):
        raise DecisionComputeError('GAME_REAP_FAILED')

    task, audit = lifecycle_task(FakeGameSession(items=[GameFinished('g1', (0, 0, 0, 0), 11)]),
                                 started, finished)
    assert (await task.run()).status is GameTaskStatus.FINISHED
    assert any(payload.get('outcome') == 'release_failed' for _, payload, _ in audit.records)


@pytest.mark.asyncio
async def test_game_task_acquire_failure_is_recoverable_and_not_false_release():
    async def started(game):
        raise DecisionComputeError('GAME_CAPACITY')

    async def forbidden(game):
        raise AssertionError('未取得绑定不能释放他桌')

    task, audit = lifecycle_task(FakeGameSession(), started, forbidden)
    assert (await task.run()).status is GameTaskStatus.RECOVERABLE_FAILURE
    assert any(payload.get('outcome') == 'acquire_failed' for _, payload, _ in audit.records)


@pytest.mark.asyncio
async def test_read_only_draining_does_not_acquire_compute_worker():
    async def forbidden(game):
        raise AssertionError('收尾不能申请策略计算')

    task, _ = lifecycle_task(FakeGameSession(items=[GameFinished('g1', (0, 0, 0, 0), 11)]),
                             forbidden, forbidden)
    assert (await task.run(read_only=True)).status is GameTaskStatus.FINISHED
