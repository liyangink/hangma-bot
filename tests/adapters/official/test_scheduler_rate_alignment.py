"""真实公开调度器的每用户请求额度回归；假时钟不产生真实等待。"""

import pytest

from _official_testkit import FakeClock, instant_sleep
from hangma_bot.adapters.official.scheduler import Priority, RequestScheduler


@pytest.mark.parametrize("priorities", [
    [Priority.POLL] * 17,
    [Priority.RECOVERY, Priority.POLL] * 8 + [Priority.RECOVERY],
])
async def test_default_state_limit_never_grants_seventeen_in_one_second(priorities):
    """普通轮询和恢复共用每用户16/s额度，不能由突发桶+持续回填叠出第17次。"""
    clock = FakeClock(start=0.0)
    scheduler = RequestScheduler(clock=clock.monotonic, sleep=instant_sleep(clock), poll_interval=0.0)
    granted = []
    for priority in priorities:
        lease = await scheduler.acquire(priority)
        granted.append(clock.monotonic())
        lease.release()
    assert granted[16] - granted[0] >= 1.0, granted


async def test_state_rolling_window_stays_bounded_across_multiple_refills():
    clock = FakeClock(start=0.0)
    scheduler = RequestScheduler(clock=clock.monotonic, sleep=instant_sleep(clock), poll_interval=0.0)
    granted = []
    for _ in range(70):
        lease = await scheduler.acquire(Priority.POLL)
        granted.append(clock.monotonic())
        lease.release()
    assert all(sum(at - 1.0 < value <= at for value in granted) <= 16 for at in set(granted))


async def test_other_endpoints_neither_spend_state_quota_nor_wait_for_state_refill():
    from hangma_bot.adapters.official.scheduler import RequestKind

    clock = FakeClock(start=0.0)
    scheduler = RequestScheduler(clock=clock.monotonic, sleep=instant_sleep(clock), poll_interval=0.0)
    for _ in range(40):
        (await scheduler.acquire(Priority.BACKGROUND, request_kind=RequestKind.OTHER)).release()
    for _ in range(16):
        (await scheduler.acquire(Priority.POLL, request_kind=RequestKind.STATE)).release()
    assert clock.monotonic() == 0.0
    for _ in range(40):
        (await scheduler.acquire(Priority.ACTION, deadline_monotonic=.01, request_kind=RequestKind.OTHER)).release()
    assert clock.monotonic() == 0.0
    (await scheduler.acquire(Priority.POLL, request_kind=RequestKind.STATE)).release()
    assert clock.monotonic() == 1.0


async def test_quota_blocked_recovery_cannot_block_other_endpoint_and_cancellation_cleans_queue():
    import asyncio
    from hangma_bot.adapters.official.scheduler import RequestKind

    clock = FakeClock(start=0.0)
    waiting = asyncio.Event()

    async def pause(seconds):
        waiting.set()
        await asyncio.Future()

    scheduler = RequestScheduler(clock=clock.monotonic, sleep=pause, poll_interval=0.0)
    for _ in range(16):
        (await scheduler.acquire(Priority.POLL)).release()
    blocked = asyncio.create_task(scheduler.acquire(Priority.RECOVERY, request_kind=RequestKind.STATE))
    await asyncio.wait_for(waiting.wait(), .2)
    try:
        # BACKGROUND 比 RECOVERY 优先级低，但后者的 state 额度未就绪；独立端点不应排死。
        other = await asyncio.wait_for(scheduler.acquire(Priority.BACKGROUND, request_kind=RequestKind.OTHER), .2)
        other.release()
        assert clock.monotonic() == 0.0
    finally:
        blocked.cancel()
        with pytest.raises(asyncio.CancelledError):
            await blocked
    assert scheduler.active_count == 0
    (await scheduler.acquire(Priority.ACTION, request_kind=RequestKind.OTHER)).release()


async def test_state_deadline_is_not_extended_until_next_rate_window():
    from hangma_bot.adapters.official.scheduler import DeadlineExceeded, RequestKind

    clock = FakeClock(start=0.0)
    scheduler = RequestScheduler(clock=clock.monotonic, sleep=instant_sleep(clock), poll_interval=0.0)
    for _ in range(16):
        (await scheduler.acquire(Priority.POLL)).release()
    with pytest.raises(DeadlineExceeded):
        await scheduler.acquire(Priority.RECOVERY, deadline_monotonic=.1, request_kind=RequestKind.STATE)
    assert clock.monotonic() == .1
    assert scheduler.active_count == 0
    (await scheduler.acquire(Priority.ACTION, deadline_monotonic=.11, request_kind=RequestKind.OTHER)).release()


class NoJitter:
    """通过公开 rng 注入去掉抖动，直接验证官方等待下界。"""

    def uniform(self, lower, upper):
        return 0.0


@pytest.mark.parametrize("retry_after", [None, float('inf'), float('nan'), -1.0])
async def test_missing_or_invalid_retry_after_waits_full_second(retry_after):
    from hangma_bot.adapters.official.scheduler import RequestKind

    clock = FakeClock(start=0.0)
    scheduler = RequestScheduler(clock=clock.monotonic, sleep=instant_sleep(clock), jitter_rng=NoJitter())
    scheduler.note_rate_limited(retry_after)
    assert scheduler.cooldown_remaining == 1.0
    (await scheduler.acquire(Priority.ACTION, request_kind=RequestKind.OTHER)).release()
    assert clock.monotonic() == 1.0


async def test_valid_retry_after_zero_is_preserved_when_local_state_quota_is_free():
    from hangma_bot.adapters.official.scheduler import RequestKind

    clock = FakeClock(start=0.0)
    scheduler = RequestScheduler(clock=clock.monotonic, sleep=instant_sleep(clock), jitter_rng=NoJitter())
    scheduler.note_rate_limited(0.0)
    assert scheduler.cooldown_remaining == 0.0
    (await scheduler.acquire(Priority.ACTION, request_kind=RequestKind.OTHER)).release()
    assert clock.monotonic() == 0.0


async def test_retry_after_never_precedes_local_state_window_or_shortens_existing_cooldown():
    from hangma_bot.adapters.official.scheduler import RequestKind

    clock = FakeClock(start=0.0)
    scheduler = RequestScheduler(clock=clock.monotonic, sleep=instant_sleep(clock), jitter_rng=NoJitter())
    for _ in range(16):
        (await scheduler.acquire(Priority.POLL)).release()
    clock.advance(.25)
    scheduler.note_rate_limited(.1, request_kind=RequestKind.STATE)
    assert scheduler.cooldown_remaining == .75
    scheduler.note_rate_limited(3.0, request_kind=RequestKind.STATE)
    clock.advance(.1)
    scheduler.note_rate_limited(.1, request_kind=RequestKind.STATE)
    assert scheduler.cooldown_remaining == pytest.approx(2.9)


async def test_action_deadline_still_applies_during_local_other_429_cooldown():
    from hangma_bot.adapters.official.scheduler import DeadlineExceeded, RequestKind

    clock = FakeClock(start=0.0)
    scheduler = RequestScheduler(clock=clock.monotonic, sleep=instant_sleep(clock), jitter_rng=NoJitter())
    scheduler.note_rate_limited(None)
    with pytest.raises(DeadlineExceeded):
        await scheduler.acquire(Priority.ACTION, deadline_monotonic=.1, request_kind=RequestKind.OTHER)
    assert clock.monotonic() == .1
    assert scheduler.active_count == 0


async def test_distinct_users_have_independent_state_windows():
    clock = FakeClock(start=0.0)
    first = RequestScheduler(clock=clock.monotonic, sleep=instant_sleep(clock))
    second = RequestScheduler(clock=clock.monotonic, sleep=instant_sleep(clock))
    for scheduler in (first, second):
        for _ in range(16):
            (await scheduler.acquire(Priority.POLL)).release()
    assert clock.monotonic() == 0.0


async def test_b1_actual_fast_state_response_rhythm_cannot_recreate_rate_overrun():
    """b1白虎429前18条响应的相对时序作为负载节奏；不是声称掌握精确发包时点。"""
    clock = FakeClock(start=0.0)
    scheduler = RequestScheduler(clock=clock.monotonic, sleep=instant_sleep(clock))
    # 2026-09-06 b1：首条到429相隔353.139ms，17次200后为429。
    relative_ms = [0, 12.907, 39.521, 51.448, 85.865, 96.728, 138.812,
                   149.56, 183.985, 199.182, 209.324, 220.64, 252.592,
                   265.523, 294.39, 310.207, 342.699, 353.139]
    actual = []
    for i, desired_ms in enumerate(relative_ms):
        clock.advance(max(0.0, desired_ms / 1000 - clock.monotonic()))
        priority = Priority.RECOVERY if i % 2 else Priority.POLL
        (await scheduler.acquire(priority)).release()
        actual.append(clock.monotonic())
    assert actual[16] >= 1.0
    assert all(sum(at - 1.0 < value <= at for value in actual) <= 16 for at in actual)


async def test_ready_requests_keep_priority_across_state_and_other_with_shared_slot():
    import asyncio
    from hangma_bot.adapters.official.scheduler import RequestKind

    clock = FakeClock(start=0.0)

    async def yield_only(seconds):
        await asyncio.sleep(0)

    scheduler = RequestScheduler(clock=clock.monotonic, sleep=yield_only, max_concurrent=1)
    holder = await scheduler.acquire(Priority.POLL)
    background = asyncio.create_task(scheduler.acquire(Priority.BACKGROUND, request_kind=RequestKind.OTHER))
    await asyncio.sleep(0)
    recovery = asyncio.create_task(scheduler.acquire(Priority.RECOVERY, request_kind=RequestKind.STATE))
    await asyncio.sleep(0)
    action = asyncio.create_task(scheduler.acquire(Priority.ACTION, request_kind=RequestKind.OTHER))
    await asyncio.sleep(0)
    holder.release()
    a = await asyncio.wait_for(action, .2)
    assert not recovery.done() and not background.done()
    a.release()
    r = await asyncio.wait_for(recovery, .2)
    assert not background.done()
    r.release()
    b = await asyncio.wait_for(background, .2)
    b.release()
    assert scheduler.active_count == 0
