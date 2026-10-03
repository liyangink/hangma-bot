"""公开计算接缝回归：未向子进程发送的过期输入不能消耗健康进程。"""
import asyncio
from dataclasses import dataclass, replace
import os
import threading

import pytest
from fakes import DISCARD_3W, FakePolicy, FakeRules, make_competition, make_observation, make_window
from hangma_bot.application.deadline import ManualClock
from hangma_bot.application.decision_compute import (
    BoundedDecisionCompute, DecisionComputeError, DecisionComputeSettings, PreparedDecisionPolicy,
)
from hangma_bot.policy.interface import DecisionBudget, DecisionRequest, ScorePart


class PackingGateText(str):
    """只在可信请求序列化时等待测试闸门；子进程收到的是普通字符串。"""
    started = threading.Event()
    release = threading.Event()
    def __reduce__(self):
        self.started.set()
        if not self.release.wait(2):
            raise AssertionError('测试编码闸门未释放')
        return str, (str(self),)


class DeadlineEchoPolicy:
    """合成控制策略只回显预算；不运行候选牌型或评分公式。"""
    async def choose(self, request, budget):
        plan = await FakePolicy().choose(request, budget)
        return replace(plan, candidates=tuple(replace(c, score_parts=(
            ScorePart('original_deadline', budget.fallback_deadline_monotonic),
            ScorePart('child_pid', float(os.getpid())),
        )) for c in plan.candidates))


@dataclass(frozen=True)
class DeadlineEchoFactory:
    """可spawn的合成工厂；明确身份且不携带官方端口或凭证。"""
    execution_id: str = 't145-unsent-deadline-public-v1'
    def __call__(self):
        return PreparedDecisionPolicy(DeadlineEchoPolicy(), self.execution_id)


def request(name):
    observation = make_observation(game_id=name)
    return DecisionRequest(observation, make_competition(),
        FakeRules(candidates=[DISCARD_3W]).analyze(observation), name,
        observation.snapshot_seq, make_window(observation).window_key, ())


async def until(predicate):
    async def wait():
        while not predicate():
            await asyncio.sleep(.005)
    await asyncio.wait_for(wait(), 2)


@pytest.mark.asyncio
async def test_untransmitted_expired_request_keeps_worker_for_next_original_budget():
    """首请求到期留住编码所有权；第二请求用同一健康进程及其自身原预算。"""
    PackingGateText.started.clear()
    PackingGateText.release.clear()
    clock = ManualClock(wait_scale=1.0)
    factory = DeadlineEchoFactory()
    compute = BoundedDecisionCompute(factory, execution_id=factory.execution_id,
        clock=clock, settings=DecisionComputeSettings(workers=1, max_pending=1,
            abandon_grace_seconds=.04, max_restarts=0, startup_seconds=2))
    await compute.start()
    try:
        first = request('before-send-expired')
        first = replace(first, competition=replace(first.competition,
            tournament_id=PackingGateText('public-input-encoding-gate')))
        task = asyncio.create_task(compute.choose(first, DecisionBudget(100.02, 100.04, 100.06)))
        await until(PackingGateText.started.is_set)
        clock.advance(.1)
        with pytest.raises(DecisionComputeError, match='^DEADLINE$'):
            await task
        await asyncio.sleep(.10)  # 短时等待实际回收计时器；超过原取消宽限。
        during = compute.snapshot()
        assert during['active'] == during['owned'] == during['transport_inflight'] == 1
        assert during['ready'] == during['live_processes'] == 1
        PackingGateText.release.set()
        await until(lambda: compute.snapshot()['active'] == compute.snapshot()['owned'] == 0)
        original = DecisionBudget(101.1, 102.1, 102.2)
        plan = await compute.choose(request('next-valid'), original)
        assert plan.decision_id == 'next-valid'
        assert plan.candidates[0].score_parts[0].value == original.fallback_deadline_monotonic
        assert plan.candidates[0].score_parts[1].value != os.getpid()
        final = compute.snapshot()
        assert final['process_starts'] == final['completed'] == 1
        assert final['faults'] == final['restarts'] == final['policy_failures'] == 0
        assert final['owned'] == final['current'] == 0
    finally:
        PackingGateText.release.set()
        await compute.close()
    closed = compute.snapshot()
    for key in ('live_processes', 'ready', 'active', 'pending', 'owned', 'current',
                'transport_inflight', 'transport_threads_alive', 'late_reap_inflight', 'late_reap_threads_alive'):
        assert closed[key] == 0, key
