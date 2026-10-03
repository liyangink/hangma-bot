"""计算服务的公开行为验收；进程故障为短时注入，不是候选能力评测。"""
import asyncio
import os
import time
from dataclasses import dataclass, replace

import pytest
from fakes import DISCARD_3W, FakePolicy, FakeRules, make_observation, make_competition, make_window
from hangma_bot.application.audit_codec import decision_plan_to_json
from hangma_bot.application.deadline import SystemClock
from hangma_bot.application.decision_compute import (
    DecisionComputeError, DecisionComputeSettings, PreparedDecisionPolicy,
)
from hangma_bot.bootstrap import build_isolated_decision_policy
from hangma_bot.policy.interface import DecisionBudget, DecisionRequest, ScorePart


class ControlPolicy:
    async def choose(self, request, budget):
        command = request.decision_id.split(':')[0]
        if command == 'crash':
            os._exit(7)
        if command == 'hang':
            while True:
                time.sleep(0.1)
        if command == 'slow':
            await asyncio.sleep(0.12)
        plan = await FakePolicy().choose(request, budget)
        if command == 'large':
            plan = replace(plan, candidates=tuple(replace(c, reasons=('a' * (12 * 1024 * 1024),))
                                                 if i == 0 else c for i, c in enumerate(plan.candidates)))
        if command == 'wrong':
            return replace(plan, decision_id='another-decision')
        # 验证原截止原样抵达子进程；这里是测试证据，不是策略评分公式。
        return replace(plan, candidates=tuple(replace(c, score_parts=(
            ScorePart('original_deadline', budget.fallback_deadline_monotonic),
            ScorePart('child_pid', float(os.getpid())),
        )) for c in plan.candidates))


@dataclass(frozen=True)
class ControlFactory:
    identity: str = 'control-source-v1'
    def __call__(self):
        return PreparedDecisionPolicy(ControlPolicy(), self.identity)


def request(name='fast:1', game='g1', seq=10):
    obs = make_observation(game_id=game, seq=seq)
    return DecisionRequest(obs, make_competition(), FakeRules(candidates=[DISCARD_3W]).analyze(obs),
                           name, seq, make_window(obs).window_key, ())


def budget(seconds=2):
    now = time.monotonic()
    return DecisionBudget(now + seconds * .5, now + seconds, now + seconds + .1)


def service(**kwargs):
    return build_isolated_decision_policy(ControlFactory(), execution_id='control-source-v1',
        clock=SystemClock(), settings=DecisionComputeSettings(workers=kwargs.pop('workers', 1),
        max_pending=kwargs.pop('max_pending', 2), **kwargs))


async def wait_snapshot(compute, key, expected):
    async def wait():
        while compute.snapshot()[key] != expected:
            await asyncio.sleep(.005)
    await asyncio.wait_for(wait(), 3)


@pytest.mark.asyncio
async def test_actual_process_roundtrip_preserves_deadline_and_releases_history():
    compute = service()
    await compute.start()
    try:
        for i in range(30):
            req, original = request(f'fast:{i}'), budget()
            result = await compute.choose(req, original)
            expected = await FakePolicy().choose(req, original)
            assert result.decision_id == expected.decision_id
            assert result.window_key == expected.window_key
            assert [c.action_key for c in result.candidates] == [c.action_key for c in expected.candidates]
            assert result.candidates[0].score_parts[0].value == original.fallback_deadline_monotonic
            assert result.candidates[0].score_parts[1].value != os.getpid()
        await wait_snapshot(compute, 'owned', 0)
        assert compute.snapshot()['current'] == 0
        assert compute.snapshot()['peak_owned'] == 1
    finally:
        await compute.close()
    assert compute.snapshot()['live_processes'] == 0


@pytest.mark.asyncio
async def test_queue_bound_and_edf_without_extending_original_deadline():
    compute = service(max_pending=2)
    await compute.start()
    tasks = []
    try:
        tasks.append(asyncio.create_task(compute.choose(request('slow:a', 'a'), budget())))
        await wait_snapshot(compute, 'dispatched', 1)
        tasks.append(asyncio.create_task(compute.choose(request('slow:b', 'b'), budget(2))))
        tasks.append(asyncio.create_task(compute.choose(request('fast:c', 'c'), budget(1))))
        await wait_snapshot(compute, 'pending', 2)
        with pytest.raises(DecisionComputeError, match='QUEUE_FULL'):
            await compute.choose(request('fast:d', 'd'), budget())
        done = []
        for i, task in enumerate(tasks):
            task.add_done_callback(lambda _task, index=i: done.append(index))
        await asyncio.gather(*tasks)
        assert done == [0, 2, 1]
        assert compute.snapshot()['peak_owned'] == 3
        assert compute.snapshot()['peak_pending'] == 2
    finally:
        await compute.close()


@pytest.mark.asyncio
async def test_pending_deadline_fails_before_dispatch_and_timer_is_responsive():
    compute = service(abandon_grace_seconds=.2)
    await compute.start()
    try:
        slow = asyncio.create_task(compute.choose(request('slow:a', 'a'), budget()))
        await wait_snapshot(compute, 'dispatched', 1)
        begin = time.monotonic()
        with pytest.raises(DecisionComputeError, match='DEADLINE'):
            await compute.choose(request('fast:b', 'b'), budget(.04))
        assert time.monotonic() - begin < .10
        await slow
        assert compute.snapshot()['dispatched'] == 1
        assert compute.snapshot()['owned'] == 0
    finally:
        await compute.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['cancel', 'supersede', 'expire'])
async def test_active_abandoned_reply_never_becomes_current_plan(kind):
    compute = service(abandon_grace_seconds=.3)
    await compute.start()
    try:
        old = asyncio.create_task(compute.choose(request('slow:old'), budget(.05 if kind == 'expire' else 2)))
        await wait_snapshot(compute, 'dispatched', 1)
        if kind == 'cancel':
            old.cancel()
            with pytest.raises(asyncio.CancelledError):
                await old
        elif kind == 'expire':
            with pytest.raises(DecisionComputeError, match='DEADLINE'):
                await old
        new = asyncio.create_task(compute.choose(request('fast:new', seq=11), budget()))
        if kind == 'supersede':
            with pytest.raises(DecisionComputeError, match='SUPERSEDED'):
                await old
        plan = await new
        assert plan.decision_id == 'fast:new'
        assert plan.based_on_authoritative_seq == 11
        assert compute.snapshot()['discarded'] == 1
        assert compute.snapshot()['owned'] == 0
    finally:
        await compute.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['crash', 'hang', 'wrong'])
async def test_worker_failure_restarts_bounded_and_next_request_succeeds(kind):
    compute = service(max_job_seconds=.15, max_restarts=1)
    await compute.start()
    try:
        with pytest.raises(DecisionComputeError, match='WORKER_FAILED'):
            await compute.choose(request(kind + ':1'), budget())
        await wait_snapshot(compute, 'process_starts', 2)
        await wait_snapshot(compute, 'ready', 1)
        result = await compute.choose(request('fast:recovered'), budget())
        assert result.decision_id == 'fast:recovered'
        assert compute.snapshot()['restarts'] == 1
        assert compute.snapshot()['owned'] == 0
    finally:
        await compute.close()
    assert compute.snapshot()['live_processes'] == 0


@pytest.mark.asyncio
async def test_close_busy_and_pending_returns_and_reaps_all_processes():
    compute = service(max_job_seconds=10)
    await compute.start()
    active = asyncio.create_task(compute.choose(request('hang:a', 'a'), budget()))
    await wait_snapshot(compute, 'dispatched', 1)
    pending = asyncio.create_task(compute.choose(request('fast:b', 'b'), budget()))
    await wait_snapshot(compute, 'pending', 1)
    await asyncio.wait_for(compute.close(), 2)
    results = await asyncio.gather(active, pending, return_exceptions=True)
    assert all(isinstance(r, DecisionComputeError) for r in results)
    assert compute.snapshot()['owned'] == compute.snapshot()['current'] == 0
    assert compute.snapshot()['live_processes'] == 0
    await compute.close()


@pytest.mark.asyncio
async def test_start_rejects_wrong_loaded_execution_identity_and_reaps_child():
    compute = build_isolated_decision_policy(ControlFactory('different-source'),
        execution_id='control-source-v1', clock=SystemClock())
    with pytest.raises(DecisionComputeError, match='WORKER_START_FAILED'):
        await compute.start()
    assert compute.snapshot()['live_processes'] == 0


@pytest.mark.asyncio
async def test_ten_simultaneous_games_have_bounded_resources():
    compute = service(workers=2, max_pending=8)
    await compute.start()
    try:
        plans = await asyncio.gather(*(compute.choose(request(f'slow:{i}', f'g{i}'), budget())
                                     for i in range(10)))
        assert len(plans) == 10
        assert compute.snapshot()['completed'] == 10
        assert compute.snapshot()['peak_owned'] <= 10
        assert compute.snapshot()['peak_pending'] <= 8
        assert compute.snapshot()['owned'] == 0
    finally:
        await compute.close()


class HangingPolicy:
    async def choose(self, request, budget):
        await asyncio.Future()


@dataclass(frozen=True)
class HangingFactory:
    def __call__(self):
        return PreparedDecisionPolicy(HangingPolicy(), 'hanging-control-v1')


@pytest.mark.asyncio
async def test_existing_application_submits_emergency_with_original_budget_when_worker_hangs():
    """沿用完整应用窗口循环；计算失败不影响已准备合法动作的实际提交。"""
    from fakes import (FakeGameSession, FakeTournamentSession, build_runtime,
                      make_bootstrap, make_snapshot)
    from hangma_bot.application.contracts import TournamentStatus
    clock = SystemClock()
    compute = build_isolated_decision_policy(HangingFactory(), execution_id='hanging-control-v1',
                                            clock=clock)
    await compute.start()
    obs = make_observation()
    window = make_window(obs, received_at=clock.now(), timeout=.3)
    game = FakeGameSession(items=[window])
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=['g1'])),
        updates=[make_snapshot(TournamentStatus.FINISHED)], game_factory=lambda gid: game)
    runtime, sink, *_ = build_runtime(session=session, policy=compute, clock=clock,
        rules=FakeRules(candidates=[DISCARD_3W], emergency=DISCARD_3W))
    task = asyncio.create_task(runtime.run())
    try:
        async def submitted():
            while len(game.submitted) != 1:
                await asyncio.sleep(.005)
        await asyncio.wait_for(submitted(), 1)
        session.grant_updates()
        await task
        assert compute.snapshot()['dispatched'] == 1
        assert compute.snapshot()['completed'] == 0
        assert game.submitted[0].action_key == 'discard:3w'
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await compute.close()
    assert compute.snapshot()['live_processes'] == 0


class PickleTripwire(str):
    """仅用于证明满队列拒绝发生在序列化前；不会送入子进程。"""
    def __reduce__(self):
        raise AssertionError('不应序列化已被拒绝的请求')


class SlowPickleText(str):
    """人工短暂停顿验证传输任务取消后的所有权，不属于候选算法。"""
    def __reduce__(self):
        time.sleep(.15)
        return str, (str(self),)


@dataclass(frozen=True)
class SlowSpawnFactory:
    """人工短暂停顿发生在Process.start序列化工厂时，用于启动取消验收。"""
    def __reduce__(self):
        time.sleep(.15)
        return ControlFactory, ()


@pytest.mark.asyncio
async def test_full_queue_rejects_without_serializing_request():
    compute = service(max_pending=1)
    await compute.start()
    try:
        active = asyncio.create_task(compute.choose(request('slow:a', 'a'), budget()))
        await wait_snapshot(compute, 'dispatched', 1)
        pending = asyncio.create_task(compute.choose(request('slow:b', 'b'), budget()))
        await wait_snapshot(compute, 'pending', 1)
        extra = request('fast:c', 'c')
        extra = replace(extra, competition=replace(extra.competition, tournament_id=PickleTripwire('tripwire')))
        with pytest.raises(DecisionComputeError, match='QUEUE_FULL'):
            await compute.choose(extra, budget())
        await asyncio.gather(active, pending)
        assert compute.snapshot()['peak_transport'] <= 1
    finally:
        await compute.close()


@pytest.mark.asyncio
async def test_expired_pending_request_is_not_serialized():
    compute = service()
    await compute.start()
    try:
        active = asyncio.create_task(compute.choose(request('slow:a', 'a'), budget()))
        await wait_snapshot(compute, 'dispatched', 1)
        extra = request('fast:b', 'b')
        extra = replace(extra, competition=replace(extra.competition, tournament_id=PickleTripwire('tripwire')))
        with pytest.raises(DecisionComputeError, match='DEADLINE'):
            await compute.choose(extra, budget(.03))
        await active
        assert compute.snapshot()['dispatched'] == 1
    finally:
        await compute.close()


@pytest.mark.asyncio
async def test_encoding_still_owned_after_deadline_until_close_reaps_thread():
    compute = service()
    await compute.start()
    try:
        req = request()
        req = replace(req, competition=replace(req.competition, tournament_id=SlowPickleText('slow-codec')))
        with pytest.raises(DecisionComputeError, match='DEADLINE'):
            await compute.choose(req, budget(.03))
        assert compute.snapshot()['transport_inflight'] == 1
        # 退出回收实际线程future，不能把异步取消当作线程已经结束。
        await asyncio.wait_for(compute.close(), 1)
        assert compute.snapshot()['transport_inflight'] == 0
        assert compute.snapshot()['transport_threads_alive'] == 0
    finally:
        await compute.close()


@pytest.mark.asyncio
async def test_close_during_spawn_settles_start_waiter_and_all_resources():
    compute = build_isolated_decision_policy(SlowSpawnFactory(), execution_id='control-source-v1',
        clock=SystemClock(), settings=DecisionComputeSettings(workers=1))
    starting = asyncio.create_task(compute.start())
    await asyncio.sleep(.02)
    await asyncio.wait_for(asyncio.gather(compute.close(), compute.close()), 2)
    with pytest.raises(DecisionComputeError, match='CLOSED'):
        await asyncio.wait_for(starting, .5)
    assert compute.snapshot()['transport_threads_alive'] == 0
    assert compute.snapshot()['live_processes'] == 0
    assert compute.snapshot()['transport_inflight'] == 0


@pytest.mark.asyncio
async def test_restart_exhaustion_expires_remaining_queue_without_hanging():
    compute = service(max_restarts=0)
    await compute.start()
    try:
        active = asyncio.create_task(compute.choose(request('crash:a', 'a'), budget()))
        queued = asyncio.create_task(compute.choose(request('fast:b', 'b'), budget(.1)))
        results = await asyncio.wait_for(asyncio.gather(active, queued, return_exceptions=True), 1)
        assert all(isinstance(r, DecisionComputeError) for r in results)
        assert compute.snapshot()['owned'] == 0
        assert compute.snapshot()['process_starts'] == 1
    finally:
        await compute.close()


@pytest.mark.asyncio
async def test_large_payload_and_restart_keep_short_timer_responsive():
    compute = service(workers=2, max_pending=8)
    await compute.start()
    lags, running = [], True
    async def pulse():
        while running:
            expected = time.monotonic() + .005
            await asyncio.sleep(.005)
            lags.append(max(0, time.monotonic() - expected))
    ticker = asyncio.create_task(pulse())
    try:
        req = request('large:response', 'big')
        req = replace(req, competition=replace(req.competition, tournament_id='b' * (12 * 1024 * 1024)))
        large = asyncio.create_task(compute.choose(req, budget()))
        crash = asyncio.create_task(compute.choose(request('crash:parallel', 'crash'), budget()))
        result = await asyncio.wait_for(asyncio.gather(large, crash, return_exceptions=True), 3)
        assert not isinstance(result[0], BaseException)
        assert isinstance(result[1], DecisionComputeError)
        assert len(result[0].candidates[0].reasons[0]) == 12 * 1024 * 1024
        await wait_snapshot(compute, 'process_starts', 3)
        await wait_snapshot(compute, 'ready', 2)
        assert compute.snapshot()['peak_transport'] <= 2
        assert max(lags) < .1
    finally:
        await compute.close()
        running = False
        await ticker
    assert compute.snapshot()['transport_threads_alive'] == 0


@pytest.mark.asyncio
async def test_late_spawn_after_failed_close_is_reaped_without_second_close():
    """用短回收上限覆盖真实超时分支，后续不再次close也须自动终止新生子进程。"""
    compute = build_isolated_decision_policy(SlowSpawnFactory(), execution_id='control-source-v1',
        clock=SystemClock(), settings=DecisionComputeSettings(workers=1, startup_seconds=.02,
                                                            resource_reap_seconds=.02))
    with pytest.raises(DecisionComputeError):
        await compute.start()
    assert compute.snapshot()['closed']
    assert compute.snapshot()['late_reap_inflight'] == 1
    async def reaped():
        while any(compute.snapshot()[name] for name in (
                'transport_inflight', 'transport_threads_alive', 'late_reap_inflight',
                'late_reap_threads_alive', 'live_processes')):
            await asyncio.sleep(.005)
    await asyncio.wait_for(reaped(), 1)
    assert compute.snapshot()['owned'] == 0


@pytest.mark.asyncio
async def test_late_encoding_after_failed_close_exits_without_second_close():
    compute = service(resource_reap_seconds=.02)
    await compute.start()
    req = request()
    req = replace(req, competition=replace(req.competition, tournament_id=SlowPickleText('slow-codec')))
    with pytest.raises(DecisionComputeError, match='DEADLINE'):
        await compute.choose(req, budget(.02))
    with pytest.raises(DecisionComputeError):
        await compute.close()
    async def reaped():
        while compute.snapshot()['transport_inflight'] or compute.snapshot()['transport_threads_alive']:
            await asyncio.sleep(.005)
    await asyncio.wait_for(reaped(), 1)
    assert compute.snapshot()['live_processes'] == 0
    assert compute.snapshot()['owned'] == 0
