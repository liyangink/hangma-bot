"""公开计算接缝回归：完整回信已收到后，解码迟到不能误杀空闲子进程。"""
import asyncio
import threading

import pytest

from hangma_bot.application.audit_codec import decision_plan_from_json
from hangma_bot.application.deadline import ManualClock
from hangma_bot.application.decision_compute import (
    BoundedDecisionCompute, DecisionComputeError, DecisionComputeSettings,
)
from hangma_bot.policy.interface import DecisionBudget
from test_compute_unsent_deadline import DeadlineEchoFactory, request, until


@pytest.mark.asyncio
async def test_received_late_result_retains_healthy_worker_and_original_next_budget():
    """在公开计划解码入口暂停父侧线程；旧结果丢弃、同一进程继续服务。

    线程分析钩子只注入父侧解码延迟，不修改服务私有字段或替换网络/计算。
    到达该入口时服务已读完完整响应字节；子进程已经等待下一请求。
    """
    entered, release = threading.Event(), threading.Event()
    previous = threading.getprofile()

    def gate(frame, event, arg):
        if event == 'call' and frame.f_code is decision_plan_from_json.__code__ and not entered.is_set():
            entered.set()
            if not release.wait(2):
                raise AssertionError('测试解码闸门未释放')

    threading.setprofile(gate)
    clock = ManualClock(wait_scale=1.0)
    factory = DeadlineEchoFactory()
    compute = BoundedDecisionCompute(factory, execution_id=factory.execution_id,
        clock=clock, settings=DecisionComputeSettings(workers=1, max_pending=1,
            abandon_grace_seconds=.04, max_restarts=0, startup_seconds=2))
    try:
        await compute.start()
        task = asyncio.create_task(compute.choose(request('reply-received'),
            DecisionBudget(100.15, 100.30, 100.40)))
        await until(entered.is_set)
        clock.advance(.4)
        with pytest.raises(DecisionComputeError, match='^DEADLINE$'):
            await task
        await asyncio.sleep(.10)  # 超过真实回收宽限；等待本次故障注入触发。
        during = compute.snapshot()
        assert during['active'] == during['owned'] == during['transport_inflight'] == 1
        assert during['live_processes'] == during['ready'] == 1
        release.set()
        await until(lambda: compute.snapshot()['owned'] == 0)
        original = DecisionBudget(101.1, 102.1, 102.2)
        plan = await compute.choose(request('next-after-decode'), original)
        assert plan.decision_id == 'next-after-decode'
        assert plan.candidates[0].score_parts[0].value == original.fallback_deadline_monotonic
        final = compute.snapshot()
        assert final['discarded'] == final['completed'] == final['process_starts'] == 1
        assert final['faults'] == final['restarts'] == final['policy_failures'] == 0
    finally:
        release.set()
        await compute.close()
        threading.setprofile(previous)
    closed = compute.snapshot()
    for key in ('live_processes', 'ready', 'active', 'pending', 'owned', 'current',
                'transport_inflight', 'transport_threads_alive', 'late_reap_inflight', 'late_reap_threads_alive'):
        assert closed[key] == 0, key
