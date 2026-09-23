"""十场共享额度的实际场次链：他家摸牌、首次弃牌、权威复核、合法鸣牌提交。"""

import asyncio
import json


from _official_testkit import FakeTransport, TIMING, make_audit_context
from _concurrent_adapter_harness import ConcurrentClock
from test_sync_repair_regressions import event, snapshot

from hangma_bot.adapters.official.game import OfficialGameSession
from hangma_bot.adapters.official.scheduler import (
    DEFAULT_PRODUCTION_STATE_BURST, DEFAULT_STATE_ARRIVAL_GUARD_SEC,
    Priority, RequestScheduler,
)
from hangma_bot.application.contracts import ActionAttempt, ObservedActionWindow, SubmitAccepted
from hangma_bot.hangma import HangmaRules
from hangma_bot.kernel.actions import Peng, Tile, action_key
from hangma_bot.kernel.config import RuleConfig


async def test_m10_burst_keeps_a_legal_peng_sendable_after_first_opponent_discard():
    """普通查询拥入时，首次弃牌查询仍应在原响应截止前完成并提交。"""
    clock, transport = ConcurrentClock(), FakeTransport()
    root = RequestScheduler(
        clock=clock.monotonic, sleep=clock.sleep,
        state_startup_delay_sec=1.0,
        state_arrival_guard_sec=DEFAULT_STATE_ARRIVAL_GUARD_SEC,
        burst=DEFAULT_PRODUCTION_STATE_BURST)
    game_id = "g-burst-response"
    session = OfficialGameSession(
        game_id=game_id, transport=transport,
        scheduler=root.for_game(game_id, max_games=10), timing=TIMING,
        monotonic_clock=clock.monotonic, wall_clock_unix_ms=clock.wall_ms,
        audit_context=make_audit_context, retry_sleep=clock.sleep)
    first = snapshot(100, turn=0)
    response = snapshot(
        102, turn=0, phase="response_peng", river=("东",),
        discard={"seq": 102, "seat": 0, "tile": "东"}, responders=(2,))
    response["snapshot"]["window_deadline_ms"] = clock.wall_ms() + 1900
    requests = posts = 0
    ordinary_tasks = []

    async def ordinary_query(index):
        scope = root.for_game("peer-{}".format(index % 9), max_games=10)
        async with await scope.acquire(Priority.POLL):
            return clock.monotonic()

    async def handler(*, method, path, params=None, **kwargs):
        nonlocal requests, posts
        if method == "POST":
            posts += 1
            return 200, '{"ok":true}'
        assert path == "/api/games/{}/state".format(game_id)
        requests += 1
        if requests == 1:
            assert params["seq"] == 0
            return 200, json.dumps(first)
        if requests == 2:
            assert params["seq"] == 100
            for index in range(16):
                ordinary_tasks.append(asyncio.create_task(ordinary_query(index)))
            for _ in range(80):
                await asyncio.sleep(0)
            return 200, json.dumps({"events": [event(101, "tile_drawn", seat=0)]})
        if requests == 3:
            assert params["seq"] == 101
            return 200, json.dumps({"events": [event(102, "tile_discarded", seat=0, tile="东")]})
        if requests == 4:
            assert params["seq"] == 0
            return 200, json.dumps(response)
        raise AssertionError("不应为单个鸣牌额外拉取状态")

    transport.handler = handler
    try:
        window = await clock.run(session.next_item())
        assert isinstance(window, ObservedActionWindow)
        assert clock.monotonic() < 1.8, "首次弃牌发现过晚会使本地合法碰牌无法提交"
        action = Peng(Tile("东"))
        assert HangmaRules(RuleConfig("burst-response", 1, False)).validate(
            window.observation, action).legal
        attempt = ActionAttempt(
            decision_id="m10-burst-response", attempt_no=1, plan_revision=1,
            window_key=window.window_key, based_on_authoritative_seq=window.authoritative_seq,
            action=action, action_key=action_key(action), latest_send_at_monotonic=1.8)
        assert isinstance(await clock.run(session.submit(attempt)), SubmitAccepted)
        assert posts == 1
    finally:
        for task in ordinary_tasks:
            task.cancel()
        await asyncio.gather(*ordinary_tasks, return_exceptions=True)
        await session.aclose("test_complete")


async def test_m10_continuous_state_queries_are_spaced_and_fair():
    """启动四笔后均匀发送，十场持续竞争不应形成近一秒的许可盲区。"""
    clock = ConcurrentClock()
    root = RequestScheduler(
        clock=clock.monotonic, sleep=clock.sleep,
        burst=4.0, state_arrival_guard_sec=.05,
        state_min_spacing_sec=1 / 14.5)
    starts = []
    waits = []

    async def game(index):
        scope = root.for_game("fair-{}".format(index), max_games=10)
        for _ in range(40):
            queued = clock.monotonic()
            lease = await scope.acquire(Priority.DISCARD_WATCH)
            starts.append(clock.monotonic())
            waits.append(clock.monotonic() - queued)
            lease.release()

    async def traffic():
        await asyncio.gather(*(game(index) for index in range(10)))

    await clock.run(traffic())
    ordered = sorted(starts)
    assert len(ordered) == 400
    assert all(b - a >= 1 / 14.5 - 1e-6 for a, b in zip(ordered[15:], ordered[16:]))
    assert max(waits) < .95
    assert all(sum(t - 1 < x <= t for x in ordered) <= 16 for t in ordered)
