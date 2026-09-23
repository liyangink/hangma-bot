"""用户共享 state 额度的公开接口回归，依据 2026-09-08 指南 v25 与评审方案。

只模拟许可、发送与取消，不连接官方平台。所有额度、截止和冷却时间均使用
手动推进的本机单调时钟秒；短 asyncio 让出仅用于把并发请求放入等待状态。
"""

from __future__ import annotations

import asyncio

import pytest

from hangma_bot.adapters.official.scheduler import (
    DeadlineExceeded,
    Priority,
    RequestKind,
    RequestScheduler,
)


class ControlledClock:
    """时间由测试显式推进，资源释放通知应能在不推进时间时唤醒等待者。"""

    def __init__(self):
        self.now = 0.0
        self.sleepers = []

    def monotonic(self):
        return self.now

    async def sleep(self, seconds):
        future = asyncio.get_running_loop().create_future()
        self.sleepers.append((self.now + max(seconds, 1e-6), future))
        await future

    def advance(self, seconds):
        self.now += seconds
        for due, future in self.sleepers:
            if due <= self.now + 1e-10 and not future.done():
                future.set_result(None)
        self.sleepers = [(due, future) for due, future in self.sleepers if not future.done()]


class NoJitter:
    """冷却测试只检验明确等待下界，不引入随机额外延迟。"""

    def uniform(self, lower, upper):
        return 0.0


def scheduler(clock, **kwargs):
    return RequestScheduler(clock=clock.monotonic, sleep=clock.sleep,
                            jitter_rng=NoJitter(), **kwargs)


async def settle():
    """让已登记任务完成排队；不会推进虚拟时间或真实等待动作窗口。"""
    for _ in range(30):
        await asyncio.sleep(0)


async def cancel_tasks(*tasks):
    for task in tasks:
        if not task.done():
            task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def immediate_lease(scope, **kwargs):
    """测试要求当下可发的请求；短真实超时只负责让错误实现有界失败。"""
    return await asyncio.wait_for(scope.acquire(Priority.POLL, **kwargs), .5)


async def spend(scope, count):
    """通过公开许可接口模拟已发请求；默认 acquire 保持现有自动计次语义。"""
    for _ in range(count):
        (await immediate_lease(scope)).release()


async def test_m10_can_query_same_game_again_without_a_static_one_second_gap():
    clock = ControlledClock()
    root = scheduler(clock)
    active = root.for_game("active", max_games=10)
    await spend(active, 3)
    assert clock.monotonic() == 0.0


async def test_all_games_share_one_rolling_sixteen_request_window():
    clock = ControlledClock()
    root = scheduler(clock)
    games = [root.for_game(str(i), max_games=10) for i in range(10)]
    sends = []
    for index in range(16):
        (await immediate_lease(games[index % len(games)])).release()
        sends.append(clock.monotonic())
    blocked = asyncio.create_task(games[0].acquire(Priority.RECOVERY))
    try:
        await settle()
        assert not blocked.done()
        clock.advance(.999)
        await settle()
        assert not blocked.done(), "整秒前不能由平滑回填提前放出第17笔"
        clock.advance(.001)
        (await asyncio.wait_for(blocked, .5)).release()
        sends.append(clock.monotonic())
        assert sends[-1] == pytest.approx(1.0)
        assert all(sum(at - 1.0 < sent <= at for sent in sends) <= 16 for at in sends)
    finally:
        await cancel_tasks(blocked)


async def test_response_progress_state_query_precedes_ordinary_poll_when_quota_returns():
    """已确认响应进度、对手已摸牌、其他弃牌监听、普通同步依次发放。"""
    clock = ControlledClock()
    root = scheduler(clock)
    games = [root.for_game(str(i), max_games=10) for i in range(10)]
    await spend(games[0], 16)
    order = []

    async def query(scope, priority, label):
        lease = await scope.acquire(priority)
        order.append(label)
        lease.release()

    ordinary = asyncio.create_task(query(games[1], Priority.POLL, "ordinary"))
    await settle()
    watch = asyncio.create_task(query(games[2], Priority.DISCARD_WATCH, "discard_watch"))
    await settle()
    progress = asyncio.create_task(query(games[3], Priority.RECOVERY, "progress"))
    await settle()
    drawn = asyncio.create_task(query(games[4], Priority.DRAW_WATCH, "draw_watch"))
    try:
        await settle()
        assert not ordinary.done() and not watch.done() and not progress.done() and not drawn.done()
        clock.advance(1.0)
        await settle()
        assert order == ["progress", "discard_watch", "draw_watch", "ordinary"]
    finally:
        await cancel_tasks(ordinary, watch, progress, drawn)


async def test_waiting_ordinary_and_watch_join_draw_class_before_starvation():
    """查询等过可服务上限后与新摸牌监听同级，按入队先后发放。"""
    clock = ControlledClock()
    root = scheduler(clock, state_arrival_guard_sec=.25)
    games = [root.for_game(str(i), max_games=10) for i in range(10)]
    await spend(games[0], 16)
    order = []

    async def query(scope, priority, label):
        lease = await scope.acquire(priority)
        order.append(label)
        lease.release()

    ordinary = asyncio.create_task(query(games[1], Priority.POLL, "old-sync"))
    await settle()
    watch = asyncio.create_task(query(games[2], Priority.DISCARD_WATCH, "old-watch"))
    await settle()
    clock.advance(.85)
    drawn = asyncio.create_task(query(games[3], Priority.DRAW_WATCH, "new-draw"))
    try:
        await settle()
        clock.advance(.40)
        await settle()
        assert order == ["old-sync", "old-watch", "new-draw"]
    finally:
        await cancel_tasks(ordinary, watch, drawn)


async def test_fresh_draw_watch_precedes_fresh_general_watch():
    """启动保护结束时，未到晋级年龄的摸牌监听仍优于一般监听。"""
    clock = ControlledClock()
    root = scheduler(clock, state_startup_delay_sec=1.0)
    games = [root.for_game(str(i), max_games=10) for i in range(2)]
    clock.advance(.5)
    order = []

    async def query(scope, priority, label):
        lease = await scope.acquire(priority)
        order.append(label)
        lease.release()

    watch = asyncio.create_task(query(games[0], Priority.DISCARD_WATCH, "general"))
    await settle()
    drawn = asyncio.create_task(query(games[1], Priority.DRAW_WATCH, "drawn"))
    try:
        await settle()
        clock.advance(.5)
        await settle()
        assert order == ["drawn", "general"]
    finally:
        await cancel_tasks(watch, drawn)


async def test_four_distinct_users_have_independent_state_accounts():
    clock = ControlledClock()
    users = [scheduler(clock).for_game("same-game-name", max_games=16) for _ in range(4)]
    for user in users:
        await spend(user, 16)
    assert clock.monotonic() == 0.0, "四个不同身份各自具有16份额度"


async def test_one_pending_state_in_a_game_does_not_block_other_games_or_action_post():
    clock = ControlledClock()
    root = scheduler(clock)
    first = root.for_game("first", max_games=10)
    second = root.for_game("second", max_games=10)
    held_state = await immediate_lease(first)
    same_game = asyncio.create_task(first.acquire(Priority.RECOVERY))
    try:
        await settle()
        assert not same_game.done(), "同场不能同时发起两个state请求"
        (await immediate_lease(second)).release()
        post = await asyncio.wait_for(first.acquire(Priority.ACTION, request_kind=RequestKind.OTHER), .5)
        assert first.active_count == 2
        (await asyncio.wait_for(root.acquire(Priority.BACKGROUND, request_kind=RequestKind.OTHER), .5)).release()
        post.release()
        await settle()
        assert not same_game.done(), "释放POST不能伪装为已有state请求结束"
        held_state.release()
        (await asyncio.wait_for(same_game, .5)).release()
        assert clock.monotonic() == 0.0, "本场槽释放必须主动唤醒，不等轮询计时器"
    finally:
        held_state.release()
        await cancel_tasks(same_game)


async def test_full_state_account_does_not_block_an_action_post():
    clock = ControlledClock()
    root = scheduler(clock)
    first = root.for_game("first", max_games=10)
    await spend(first, 16)
    blocked = asyncio.create_task(first.acquire(Priority.RECOVERY))
    try:
        await settle()
        assert not blocked.done()
        (await asyncio.wait_for(first.acquire(Priority.ACTION, request_kind=RequestKind.OTHER,
                                             deadline_monotonic=.1), .5)).release()
        assert clock.monotonic() == 0.0
    finally:
        await cancel_tasks(blocked)


async def test_other_429_does_not_add_the_unrelated_full_state_account_wait():
    """OTHER明确退避为零时，state已满不能凭空再给POST增加一秒冷却。"""
    clock = ControlledClock()
    root = scheduler(clock)
    active = root.for_game("active", max_games=10)
    await spend(active, 16)
    active.note_rate_limited(0.0, request_kind=RequestKind.OTHER)
    assert active.cooldown_remaining == 0.0
    lease = await asyncio.wait_for(active.acquire(
        Priority.ACTION, request_kind=RequestKind.OTHER, deadline_monotonic=.1), .5)
    lease.release()
    assert clock.monotonic() == 0.0


async def test_new_user_account_waits_one_window_without_delaying_other_endpoints():
    """新账等待旧进程记录过期；同账内重开场次不重新触发启动等待。"""
    clock = ControlledClock()
    root = scheduler(clock, state_startup_delay_sec=1.0)
    active = root.for_game("active", max_games=10)
    pending = asyncio.create_task(active.acquire(Priority.POLL))
    try:
        await settle()
        assert not pending.done()
        (await asyncio.wait_for(root.acquire(Priority.BACKGROUND,
            request_kind=RequestKind.OTHER), .5)).release()
        (await asyncio.wait_for(active.acquire(Priority.ACTION,
            request_kind=RequestKind.OTHER), .5)).release()
        clock.advance(.999)
        await settle()
        assert not pending.done()
        clock.advance(.001)
        (await asyncio.wait_for(pending, .5)).release()
        (await immediate_lease(root.for_game("active", max_games=10))).release()
        assert clock.monotonic() == pytest.approx(1.0)
    finally:
        await cancel_tasks(pending)


async def test_state_429_cools_all_games_of_only_the_same_user():
    clock = ControlledClock()
    root = scheduler(clock)
    first = root.for_game("first", max_games=10)
    second = root.for_game("second", max_games=10)
    other_user = scheduler(clock).for_game("other-user", max_games=10)
    first.note_rate_limited(.5, request_kind=RequestKind.STATE)
    blocked = asyncio.create_task(second.acquire(Priority.POLL))
    try:
        await settle()
        assert not blocked.done()
        (await immediate_lease(other_user)).release()
        for scope in (first, second, root):
            (await asyncio.wait_for(scope.acquire(Priority.ACTION, request_kind=RequestKind.OTHER), .5)).release()
        clock.advance(.499)
        await settle()
        assert not blocked.done()
        clock.advance(.001)
        (await asyncio.wait_for(blocked, .5)).release()
        assert clock.monotonic() == pytest.approx(.5)
    finally:
        await cancel_tasks(blocked)


async def test_other_endpoint_cooldown_and_http_slots_remain_local_to_the_game():
    clock = ControlledClock()
    root = scheduler(clock)
    first = root.for_game("first", max_games=10)
    second = root.for_game("second", max_games=10)
    first.note_rate_limited(.5, request_kind=RequestKind.OTHER)
    blocked = asyncio.create_task(first.acquire(Priority.ACTION, request_kind=RequestKind.OTHER))
    try:
        await settle()
        assert not blocked.done()
        for scope in (second, root):
            (await asyncio.wait_for(scope.acquire(Priority.ACTION, request_kind=RequestKind.OTHER), .5)).release()
        (await immediate_lease(second)).release()
        assert clock.monotonic() == 0.0
        clock.advance(.5)
        (await asyncio.wait_for(blocked, .5)).release()
    finally:
        await cancel_tasks(blocked)


async def test_unsent_reservation_release_does_not_consume_state_quota():
    clock = ControlledClock()
    game = scheduler(clock).for_game("game", max_games=16)
    reserved = await immediate_lease(game, reserve_only=True)
    reserved.release()
    reserved.release()  # 取消和 finally 重叠也不能多退额度。
    await spend(game, 16)
    assert clock.monotonic() == 0.0


async def test_sent_lease_release_does_not_refund_a_request():
    clock = ControlledClock()
    game = scheduler(clock).for_game("game", max_games=16)
    sent = await immediate_lease(game, reserve_only=True)
    sent.mark_sent()
    sent.release()
    await spend(game, 15)
    blocked = asyncio.create_task(game.acquire(Priority.POLL))
    try:
        await settle()
        assert not blocked.done(), "已发HTTP即使取消或失败也不退次数"
        clock.advance(1.0)
        (await asyncio.wait_for(blocked, .5)).release()
    finally:
        await cancel_tasks(blocked)


async def test_request_is_counted_at_mark_sent_instead_of_the_earlier_reservation():
    clock = ControlledClock()
    root = scheduler(clock)
    first = root.for_game("first", max_games=16)
    second = root.for_game("second", max_games=16)
    await spend(first, 15)
    reserved = await immediate_lease(second, reserve_only=True)
    clock.advance(.75)
    reserved.mark_sent()
    reserved.release()
    clock.advance(.25)
    await spend(first, 15)  # 最初15笔在1.0秒过期；0.75秒发出的这一笔仍占额度。
    blocked = asyncio.create_task(first.acquire(Priority.POLL))
    try:
        await settle()
        assert not blocked.done()
        clock.advance(.749)
        await settle()
        assert not blocked.done()
        clock.advance(.001)
        (await asyncio.wait_for(blocked, .5)).release()
        assert clock.monotonic() == pytest.approx(1.75)
    finally:
        await cancel_tasks(blocked)


async def test_unmarked_reservation_holds_capacity_until_cancelled_and_wakes_a_waiter():
    clock = ControlledClock()
    root = scheduler(clock)
    first = root.for_game("first", max_games=16)
    second = root.for_game("second", max_games=16)
    third = root.for_game("third", max_games=16)
    await spend(first, 15)
    reserved = await immediate_lease(second, reserve_only=True)
    blocked = asyncio.create_task(third.acquire(Priority.POLL))
    try:
        await settle()
        assert not blocked.done(), "尚未发出的预占也要防止其他协程重复领取最后一份"
        reserved.release()
        (await asyncio.wait_for(blocked, .5)).release()
        assert clock.monotonic() == 0.0
    finally:
        reserved.release()
        await cancel_tasks(blocked)


async def test_sixteen_unsent_reservations_cannot_expire_as_if_they_were_sent():
    clock = ControlledClock()
    root = scheduler(clock)
    games = [root.for_game(str(index), max_games=16) for index in range(16)]
    reservations = [await immediate_lease(game, reserve_only=True) for game in games]
    # 父调度器也暴露相同的state许可接口；其本地槽没有被子场占用，
    # 因而这里等待只能是用户额度约束，不能由同场单state槽掩盖错误。
    blocked = asyncio.create_task(root.acquire(Priority.POLL))
    try:
        await settle()
        assert not blocked.done()
        clock.advance(1.1)
        await settle()
        assert not blocked.done(), "预占尚未发送，不能按许可时刻加一秒自然退还"
        reservations[0].release()
        (await asyncio.wait_for(blocked, .5)).release()
        assert clock.monotonic() == pytest.approx(1.1)
    finally:
        for lease in reservations:
            lease.release()
        await cancel_tasks(blocked)


async def test_query_dispatch_uses_deadline_before_old_recovery_priority():
    clock = ControlledClock()
    root = scheduler(clock)
    games = [root.for_game(str(i), max_games=10) for i in range(3)]
    await spend(games[0], 16)
    completed = []

    async def take(scope, label, priority, deadline):
        lease = await scope.acquire(priority, deadline_monotonic=deadline)
        completed.append(label)
        lease.release()

    slow = asyncio.create_task(take(games[0], "later-recovery", Priority.RECOVERY, 2.0))
    await settle()
    fast = asyncio.create_task(take(games[1], "earlier-window", Priority.POLL, 1.1))
    unknown = asyncio.create_task(take(games[2], "unknown", Priority.ACTION, None))
    try:
        await settle()
        clock.advance(1.0)
        await asyncio.wait_for(asyncio.gather(slow, fast, unknown), .5)
        assert completed == ["earlier-window", "later-recovery", "unknown"]
    finally:
        await cancel_tasks(slow, fast, unknown)


async def test_equal_deadlines_favor_the_game_that_has_waited_longer_for_service():
    clock = ControlledClock()
    root = scheduler(clock)
    recent = root.for_game("recent", max_games=10)
    unserved = root.for_game("unserved", max_games=10)
    await spend(recent, 16)
    completed = []

    async def take(scope, label):
        lease = await scope.acquire(Priority.POLL, deadline_monotonic=2.0)
        completed.append(label)
        lease.release()

    first = asyncio.create_task(take(recent, "recent"))
    await settle()
    second = asyncio.create_task(take(unserved, "unserved"))
    try:
        await settle()
        clock.advance(1.0)
        await asyncio.wait_for(asyncio.gather(first, second), .5)
        assert completed == ["unserved", "recent"], "同期限不能由刚服务过的场继续按入队先后抢占"
    finally:
        await cancel_tasks(first, second)


async def test_a_new_urgent_query_reorders_existing_quota_waiters():
    clock = ControlledClock()
    root = scheduler(clock)
    waiting_game = root.for_game("waiting", max_games=10)
    urgent_game = root.for_game("urgent", max_games=10)
    await spend(waiting_game, 16)
    completed = []

    async def take(scope, label, deadline):
        lease = await scope.acquire(Priority.POLL, deadline_monotonic=deadline)
        completed.append(label)
        lease.release()

    older = asyncio.create_task(take(waiting_game, "ordinary", None))
    await settle()
    clock.advance(.9)
    urgent = asyncio.create_task(take(urgent_game, "urgent", 1.1))
    try:
        await settle()
        assert not older.done() and not urgent.done()
        clock.advance(.1)
        await asyncio.wait_for(asyncio.gather(older, urgent), .5)
        assert completed == ["urgent", "ordinary"]
    finally:
        await cancel_tasks(older, urgent)


async def test_known_future_boundary_keeps_the_last_credit_from_background_polling():
    clock = ControlledClock()
    root = scheduler(clock)
    ordinary = root.for_game("ordinary", max_games=10)
    boundary = root.for_game("boundary", max_games=10)
    await spend(ordinary, 15)
    hint = boundary.protect_state_query(ready_at_monotonic=.05, latest_start_at_monotonic=.1)
    background = asyncio.create_task(ordinary.acquire(Priority.POLL))
    pending_boundary = asyncio.create_task(boundary.acquire(
        Priority.POLL, deadline_monotonic=.1, not_before_monotonic=.05, reservation=hint))
    try:
        await settle()
        assert not background.done() and not pending_boundary.done()
        clock.advance(.05)
        (await asyncio.wait_for(pending_boundary, .5)).release()
        assert clock.monotonic() == pytest.approx(.05)
        await settle()
        assert not background.done(), "最后一份额度已用于边界，不应把提示和GET重复计费或提前给背景"
        clock.advance(.95)
        (await asyncio.wait_for(background, .5)).release()
    finally:
        hint.cancel()
        await cancel_tasks(background, pending_boundary)


async def test_future_boundary_is_protected_from_the_next_paced_state_gap():
    """普通查询不能占用未来必要查询前唯一可用的平滑发放时机。"""
    clock = ControlledClock()
    root = scheduler(clock, rate_per_second=16, burst=4,
                     state_arrival_guard_sec=.05, state_min_spacing_sec=1 / 14.5)
    ordinary = root.for_game("ordinary", max_games=10)
    boundary = root.for_game("boundary", max_games=10)
    await spend(ordinary, 4)
    for _ in range(12):
        clock.advance(1 / 16)
        await spend(ordinary, 1)
    assert clock.monotonic() == pytest.approx(.75)
    clock.advance(.3)  # 首批四笔于 1.05 秒释放，已进入 14.5/s 平滑阶段。
    hint = boundary.protect_state_query(
        ready_at_monotonic=1.08, latest_start_at_monotonic=1.10)
    background = asyncio.create_task(ordinary.acquire(Priority.POLL))
    pending_boundary = asyncio.create_task(boundary.acquire(
        Priority.POLL, deadline_monotonic=1.10,
        not_before_monotonic=1.08, reservation=hint))
    try:
        await settle()
        assert not background.done(), "先发普通查询会把下一许可推到 1.119 秒，越过必要查询截止"
        clock.advance(.03)
        (await asyncio.wait_for(pending_boundary, .5)).release()
        assert clock.monotonic() == pytest.approx(1.08)
    finally:
        hint.cancel()
        await cancel_tasks(background, pending_boundary)


async def test_future_boundary_is_protected_from_token_refill_gap():
    """突发令牌只剩一枚时，普通 GET 不得令稍后必要查询等到下一次补充。"""
    clock = ControlledClock()
    root = scheduler(clock, rate_per_second=16, burst=1)
    ordinary = root.for_game("ordinary", max_games=10)
    boundary = root.for_game("boundary", max_games=10)
    await spend(ordinary, 1)
    clock.advance(1 / 16)
    hint = boundary.protect_state_query(
        ready_at_monotonic=.09, latest_start_at_monotonic=.10)
    background = asyncio.create_task(ordinary.acquire(Priority.POLL))
    pending_boundary = asyncio.create_task(boundary.acquire(
        Priority.POLL, deadline_monotonic=.10,
        not_before_monotonic=.09, reservation=hint))
    try:
        await settle()
        assert not background.done(), "当前令牌要留给 .09 秒的已知边界"
        clock.advance(.0275)
        (await asyncio.wait_for(pending_boundary, .5)).release()
        assert clock.monotonic() == pytest.approx(.09)
        await settle()
        assert not background.done()
        clock.advance(1 / 16)
        (await asyncio.wait_for(background, .5)).release()
    finally:
        hint.cancel()
        await cancel_tasks(background, pending_boundary)


async def test_cancelled_future_hint_wakes_background_without_waiting_for_its_timer():
    clock = ControlledClock()
    root = scheduler(clock)
    ordinary = root.for_game("ordinary", max_games=10)
    boundary = root.for_game("boundary", max_games=10)
    await spend(ordinary, 15)
    hint = boundary.protect_state_query(ready_at_monotonic=.05, latest_start_at_monotonic=.1)
    background = asyncio.create_task(ordinary.acquire(Priority.POLL))
    try:
        await settle()
        assert not background.done()
        hint.cancel()
        hint.cancel()
        (await asyncio.wait_for(background, .5)).release()
        assert clock.monotonic() == 0.0
    finally:
        hint.cancel()
        await cancel_tasks(background)


async def test_not_before_is_respected_even_when_quota_is_available():
    clock = ControlledClock()
    game = scheduler(clock).for_game("game", max_games=10)
    pending = asyncio.create_task(game.acquire(Priority.POLL, not_before_monotonic=.05,
                                               deadline_monotonic=.1))
    try:
        await settle()
        assert not pending.done()
        clock.advance(.049)
        await settle()
        assert not pending.done()
        clock.advance(.001)
        (await asyncio.wait_for(pending, .5)).release()
        assert clock.monotonic() == pytest.approx(.05)
    finally:
        await cancel_tasks(pending)


async def test_expired_or_cancelled_waiting_queries_never_consume_a_future_credit():
    clock = ControlledClock()
    game = scheduler(clock).for_game("game", max_games=16)
    await spend(game, 16)
    expired = asyncio.create_task(game.acquire(Priority.POLL, deadline_monotonic=.1))
    cancelled = asyncio.create_task(game.acquire(Priority.RECOVERY))
    try:
        await settle()
        cancelled.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancelled
        clock.advance(.1)
        with pytest.raises(DeadlineExceeded):
            await asyncio.wait_for(expired, .5)
        with pytest.raises(DeadlineExceeded):
            await immediate_lease(game, deadline_monotonic=.1)
        clock.advance(.9)
        await spend(game, 16)
        assert clock.monotonic() == pytest.approx(1.0)
        assert game.active_count == 0
    finally:
        await cancel_tasks(expired, cancelled)
