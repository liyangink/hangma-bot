"""调度器测试：优先级、令牌桶、429 冷却与并发上限。"""
from __future__ import annotations

import asyncio

from hangma_bot.adapters.official.scheduler import Priority, RequestScheduler

from _official_testkit import FakeClock, instant_sleep


def _scheduler(clock: FakeClock, **kw) -> RequestScheduler:
    defaults = dict(
        rate_per_second=8.0,
        clock=clock.monotonic,
        sleep=instant_sleep(clock),
        poll_interval=0.0,
    )
    defaults.update(kw)
    return RequestScheduler(**defaults)


async def test_burst_tokens_then_throttle() -> None:
    """令牌桶：突发 8 个立即授予，第 9 个等待令牌回填。"""

    clock = FakeClock()
    scheduler = _scheduler(clock)
    for _ in range(8):
        lease = await asyncio.wait_for(scheduler.acquire(Priority.POLL), timeout=2)
        lease.release()
    # 令牌已耗尽（release 只还并发槽不还令牌）：第 9 个需要 fake 时钟推进
    task = asyncio.create_task(scheduler.acquire(Priority.POLL))
    await asyncio.sleep(0.05)  # instant_sleep 会推进假时钟直到令牌回填
    lease = await asyncio.wait_for(task, timeout=2)
    lease.release()


async def test_priority_preemption() -> None:
    """动作请求优先于背景刷新，即使背景先排队。"""

    clock = FakeClock()
    scheduler = _scheduler(clock, rate_per_second=1.0, burst=1.0)
    lease = await asyncio.wait_for(scheduler.acquire(Priority.BACKGROUND), timeout=2)
    # 背景持有唯一令牌；动作与另一个背景任务排队
    background = asyncio.create_task(scheduler.acquire(Priority.BACKGROUND))
    await asyncio.sleep(0.02)
    action = asyncio.create_task(scheduler.acquire(Priority.ACTION))
    await asyncio.sleep(0.02)
    lease.release()  # 释放并发槽；令牌需要回填
    clock.advance(2.0)  # 回填令牌
    first = await asyncio.wait_for(action, timeout=2)
    assert first.priority is Priority.ACTION  # 动作先于先排队的背景请求
    first.release()
    second = await asyncio.wait_for(background, timeout=5)
    second.release()


async def test_default_rate_matches_v11_16_per_second() -> None:
    """指南 v11：默认限速 16/s/用户聚合（8/s → 16/s），突发 16 个立即授予。"""

    clock = FakeClock()
    scheduler = RequestScheduler(
        clock=clock.monotonic, sleep=instant_sleep(clock), poll_interval=0.0
    )
    for _ in range(16):
        lease = await asyncio.wait_for(scheduler.acquire(Priority.POLL), timeout=2)
        lease.release()
    # 第 17 个需等滚动1秒窗口让出额度，不能在62.5ms回填时突破16/s
    task = asyncio.create_task(scheduler.acquire(Priority.POLL))
    await asyncio.sleep(0.05)  # instant_sleep 推进假时钟直到令牌回填
    lease = await asyncio.wait_for(task, timeout=2)
    lease.release()


async def test_rate_limit_cooldown_blocks_new_grants() -> None:
    """429 冷却期内不授予；冷却结束后恢复。"""

    clock = FakeClock()
    scheduler = _scheduler(clock)
    scheduler.note_rate_limited(0.5)
    assert scheduler.cooldown_remaining > 0
    task = asyncio.create_task(scheduler.acquire(Priority.POLL))
    await asyncio.sleep(0.05)  # instant_sleep 按冷却时长推进假时钟
    lease = await asyncio.wait_for(task, timeout=2)
    lease.release()
    assert scheduler.cooldown_remaining == 0


async def test_non_finite_retry_after_never_freezes_token() -> None:
    """W2-1 回归：畸形 Retry-After（inf/nan/负值）不得把冷却推成永久挂起。"""

    clock = FakeClock()
    scheduler = _scheduler(clock)
    for bad in (float("inf"), float("nan"), -3.0):
        scheduler.note_rate_limited(bad)
        remaining = scheduler.cooldown_remaining
        assert 1.0 <= remaining <= 1.25  # 缺有效头至少冷却完整1s窗口，绝不为 inf
    # 冷却结束后许可照常授予（Token 未被冻结）
    task = asyncio.create_task(scheduler.acquire(Priority.POLL))
    await asyncio.sleep(0.05)  # instant_sleep 按冷却时长推进假时钟
    lease = await asyncio.wait_for(task, timeout=2)
    lease.release()
    assert scheduler.cooldown_remaining == 0


async def test_concurrent_slot_limit() -> None:
    clock = FakeClock()
    scheduler = _scheduler(clock, rate_per_second=100, burst=100, max_concurrent=2)
    a = await asyncio.wait_for(scheduler.acquire(Priority.POLL), timeout=2)
    b = await asyncio.wait_for(scheduler.acquire(Priority.POLL), timeout=2)
    assert scheduler.active_count == 2
    third = asyncio.create_task(scheduler.acquire(Priority.POLL))
    await asyncio.sleep(0.05)
    assert not third.done(), "并发槽未释放前不应授予第三个"
    a.release()
    lease = await asyncio.wait_for(third, timeout=2)
    lease.release()
    b.release()


async def test_acquire_cancellation_releases_waiter() -> None:
    """等待中的请求被取消后，不影响后续授予。"""

    clock = FakeClock()
    scheduler = _scheduler(clock, rate_per_second=1.0, burst=1.0)
    lease = await asyncio.wait_for(scheduler.acquire(Priority.POLL), timeout=2)
    cancelled = asyncio.create_task(scheduler.acquire(Priority.POLL))
    await asyncio.sleep(0.02)
    cancelled.cancel()
    try:
        await cancelled
    except asyncio.CancelledError:
        pass
    lease.release()
    clock.advance(2.0)
    fresh = await asyncio.wait_for(scheduler.acquire(Priority.ACTION), timeout=2)
    fresh.release()
