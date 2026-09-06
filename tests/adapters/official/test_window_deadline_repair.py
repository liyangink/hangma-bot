"""正式会话截止语义回归；注入时钟与传输，禁止真实网络和真实等待。"""
from __future__ import annotations

import asyncio
import json

import pytest

from hangma_bot.adapters.official.errors import ConflictError
from hangma_bot.adapters.official.game import OfficialGameSession
from hangma_bot.adapters.official.scheduler import RequestScheduler
from hangma_bot.application.contracts import ActionAttempt, ObservedActionWindow, SubmitRejectedRetryable
from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.kernel.actions import Peng, Tile, WindowPhase

from _official_testkit import TIMING, instant_sleep, load_fixture


def peng_snapshot(deadline_ms):
    doc = load_fixture("state_response_snapshot_peng.json")
    doc["snapshot"]["window_deadline_ms"] = deadline_ms
    return doc


def scripted(transport, steps):
    queue = list(steps)

    def handler(*, method, params=None, **kwargs):
        assert queue, "意外增加的请求会掩盖事件丢失或刷新风暴"
        expected_method, expected_seq, result = queue.pop(0)
        assert method == expected_method
        if method == "GET":
            assert params["seq"] == expected_seq
        if isinstance(result, Exception):
            raise result
        return 200, json.dumps(result)

    transport.handler = handler
    return queue


def make_session(transport, clock, *, wall_clock=None, timer=None):
    async def unexpired(seconds):
        await asyncio.Future()  # 此组只测试即时网络；未到期计时器由会话取消

    return OfficialGameSession(
        game_id="deadline-test", transport=transport,
        scheduler=RequestScheduler(clock=clock.monotonic, sleep=instant_sleep(clock), poll_interval=0),
        timing=TIMING, monotonic_clock=clock.monotonic,
        wall_clock_unix_ms=wall_clock or clock.wall_ms,
        retry_sleep=timer or unexpired,
    )


def peng_attempt(window, clock):
    return ActionAttempt(
        decision_id="deadline-repair", attempt_no=1, plan_revision=1,
        window_key=window.window_key,
        based_on_authoritative_seq=window.authoritative_seq,
        action=Peng(Tile("2w")), action_key="peng:2w",
        latest_send_at_monotonic=clock.monotonic() + 0.2,
    )


def budget(window):
    return BudgetPolicy().build(window.received_at_monotonic, window.timeout_seconds, window.expires_at_monotonic)


async def test_official_100ms_remaining_bounds_all_decision_deadlines(transport, clock):
    queue = scripted(transport, [("GET", 0, peng_snapshot(clock.wall_ms() + 100))])
    session = make_session(transport, clock)
    try:
        window = await session.next_item()
        assert isinstance(window, ObservedActionWindow)
        assert not window.deadline_is_estimated
        assert window.timeout_seconds == 1.0
        assert window.expires_at_monotonic == pytest.approx(clock.monotonic() + 0.1)
        result = budget(window)
        assert result.latest_send_at_monotonic - clock.monotonic() == pytest.approx(0.085)
        assert result.enhancement_deadline_monotonic <= result.fallback_deadline_monotonic <= result.latest_send_at_monotonic < window.expires_at_monotonic
        assert not queue
    finally:
        await session.aclose("test_completed")


@pytest.mark.parametrize("new_delta_ms,expected_delta", [(900, 0.5), (300, 0.3)])
async def test_409_same_window_deadline_only_tightens(transport, clock, new_delta_ms, expected_delta):
    initial_wall, initial_mono = clock.wall_ms(), clock.monotonic()
    queue = scripted(transport, [
        ("GET", 0, peng_snapshot(initial_wall + 500)),
        ("POST", None, ConflictError(409, "INVALID_ACTION", "rejected")),
        ("GET", 0, peng_snapshot(initial_wall + new_delta_ms)),
    ])
    session = make_session(transport, clock)
    try:
        original = await session.next_item()
        original_budget = budget(original)
        clock.advance(0.1)
        result = await session.submit(peng_attempt(original, clock))
        assert isinstance(result, SubmitRejectedRetryable)
        refreshed = result.refreshed_window
        assert refreshed.window_key == original.window_key
        assert refreshed.expires_at_monotonic == pytest.approx(initial_mono + expected_delta)
        tightened = BudgetPolicy().tighten(original_budget, refreshed.received_at_monotonic, refreshed.timeout_seconds, refreshed.expires_at_monotonic)
        assert tightened.latest_send_at_monotonic <= original_budget.latest_send_at_monotonic
        assert tightened.latest_send_at_monotonic < refreshed.expires_at_monotonic
        assert not queue
    finally:
        await session.aclose("test_completed")


async def test_old_peng_deadline_is_not_reused_for_new_incremental_draw(transport, clock):
    queue = scripted(transport, [
        ("GET", 0, peng_snapshot(clock.wall_ms() + 100)),
        ("GET", 120, {"events": [{"seq": 121, "type": "tile_drawn", "seat": 2, "tile": "7w"}]}),
    ])
    session = make_session(transport, clock)
    try:
        peng = await session.next_item()
        drawn = await session.next_item()
        assert drawn.window_key.phase is WindowPhase.DRAW
        assert drawn.window_key.trigger_seq == 121
        assert drawn.deadline_is_estimated
        assert drawn.expires_at_monotonic == pytest.approx(clock.monotonic() + 3.0)
        assert drawn.expires_at_monotonic > peng.expires_at_monotonic
        assert not queue
    finally:
        await session.aclose("test_completed")


async def test_wall_clock_rollback_does_not_extend_existing_window(transport, clock):
    initial_mono, official_deadline = clock.monotonic(), clock.wall_ms() + 500
    wall_shift = {"ms": 0}
    queue = scripted(transport, [
        ("GET", 0, peng_snapshot(official_deadline)),
        ("POST", None, ConflictError(409, "INVALID_ACTION", "rejected")),
        ("GET", 0, peng_snapshot(official_deadline)),
    ])
    session = make_session(transport, clock, wall_clock=lambda: clock.wall_ms() + wall_shift["ms"])
    try:
        original = await session.next_item()
        clock.advance(0.1)
        wall_shift["ms"] = -10_000
        result = await session.submit(peng_attempt(original, clock))
        assert isinstance(result, SubmitRejectedRetryable)
        assert result.refreshed_window.expires_at_monotonic == pytest.approx(initial_mono + 0.5)
        assert not result.refreshed_window.deadline_is_estimated
        assert not queue
    finally:
        await session.aclose("test_completed")


async def test_simultaneously_completed_poll_and_boundary_keep_received_events(transport, clock):
    timer_completed = []

    async def immediate_timer(seconds):
        timer_completed.append(seconds)
        clock.advance(seconds)

    queue = scripted(transport, [
        ("GET", 0, peng_snapshot(clock.wall_ms() + 100)),
        ("GET", 120, {"events": [{"seq": 121, "type": "tile_drawn", "seat": 2, "tile": "7w"}]}),
    ])
    session = make_session(transport, clock, timer=immediate_timer)
    try:
        await session.next_item()
        window = await session.next_item()
        assert timer_completed, "必须覆盖计时器也已完成的分支"
        assert window.window_key.phase is WindowPhase.DRAW
        assert window.window_key.trigger_seq == 121
        assert window.observation.consumed_seq == 121
        assert any(e.seq == 121 for e in window.observation.public_history)
        assert len(transport.calls) == 2  # 没有丢弃增量后再拉全量
        assert not queue
    finally:
        await session.aclose("test_completed")
