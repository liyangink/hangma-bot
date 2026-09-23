"""普通弃牌缓发的公开会话行为；虚拟时间、假传输，不访问官方平台。"""

import asyncio
import json
from dataclasses import replace

import pytest

from _official_testkit import FakeAuditSink, FakeTransport, TIMING, load_fixture, make_audit_context
from _virtual_clock import VirtualClock
from test_sync_repair_regressions import snapshot

from hangma_bot.adapters.official.game import OfficialGameSession
from hangma_bot.adapters.official.scheduler import Priority, RequestKind, RequestScheduler
from hangma_bot.application.contracts import (
    ActionAttempt, GameFinished, ObservedActionWindow, SubmitAccepted, SubmitNotSent,
    SubmissionCancelledBeforeSend,
)
from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.kernel.actions import Discard, Hu, Tile


async def settle():
    """只让并发任务登记等待，不推进单调时钟。"""
    for _ in range(20):
        await asyncio.sleep(0)


async def finish(task):
    return await asyncio.shield(task)


async def make_draw(*, snapshot_only=False, ts_offset=0, missing_ts=False,
                    chain_count=0, enabled=True, wait=None, receive_delay=.2):
    """先见他家状态，再在0.2秒收到本人正常摸牌；可显式切换恢复/异常输入。"""
    clock = VirtualClock()
    audit, transport = FakeAuditSink(), FakeTransport()
    root = RequestScheduler(clock=clock.monotonic, sleep=clock.sleep)
    scope = root.for_game("pacing", max_games=10)
    initial_ts = clock.wall_ms() // 1000
    post_times = []
    gets = 0

    async def handler(*, method, params, **kwargs):
        nonlocal gets
        if method == "POST":
            post_times.append(clock.monotonic())
            return 200, '{"ok":true}'
        gets += 1
        if snapshot_only or gets == 1:
            doc = snapshot(101, turn=2 if snapshot_only else 0,
                           drawn="7w" if snapshot_only else "")
            doc["snapshot"]["god"].update(chain_count=chain_count, catch_play=False)
            if snapshot_only:
                doc["snapshot"]["window_deadline_ms"] = clock.wall_ms() + 3000
            return 200, json.dumps(doc)
        if gets == 2:
            assert params["seq"] == 101
            await clock.sleep(receive_delay)
            event = {"seq": 102, "type": "tile_drawn", "seat": 2, "tile": "7w", "data": None}
            if not missing_ts:
                event["ts"] = initial_ts + ts_offset
            return 200, json.dumps({"seq": 102, "events": [event], "gap": False})
        assert gets == 3, "等待本身不能增加查询"
        return 200, json.dumps(load_fixture("state_response_finished.json"))

    transport.handler = handler
    session = OfficialGameSession(
        game_id="pacing", transport=transport, scheduler=scope, timing=TIMING,
        monotonic_clock=clock.monotonic, wall_clock_unix_ms=clock.wall_ms,
        audit=audit, audit_context=make_audit_context,
        retry_sleep=(lambda seconds: wait(clock, seconds)) if wait else clock.sleep,
        discard_pacing_enabled=enabled,
    )
    window = await clock.run(session.next_item())
    assert isinstance(window, ObservedActionWindow)
    budget = BudgetPolicy().build(window.received_at_monotonic, window.timeout_seconds,
                                 window.expires_at_monotonic)
    action = Discard(Tile("7w"))
    attempt = ActionAttempt(
        decision_id="discard-pacing", attempt_no=1, plan_revision=1,
        window_key=window.window_key, based_on_authoritative_seq=window.authoritative_seq,
        action=action, action_key="discard:7w", latest_send_at_monotonic=budget.latest_send_at_monotonic)
    return clock, root, scope, session, transport, audit, attempt, post_times


async def pressure(root, used):
    """其他场消费同用户额度，目标场不单独累积虚构压力。"""
    peer = root.for_game("peer", max_games=10)
    while root.state_used_count < used:
        (await peer.acquire(Priority.POLL)).release()


@pytest.mark.parametrize("used,expected", [(0, .7), (9, .7), (10, .7), (16, 1.2)])
async def test_every_normal_discard_waits_half_second_and_quota_congestion_extends_to_one(used, expected):
    clock, root, scope, session, transport, audit, attempt, posts = await make_draw()
    await pressure(root, used)
    try:
        assert isinstance(await clock.run(session.submit(attempt)), SubmitAccepted)
        assert posts == pytest.approx([expected])
        assert [c.params["seq"] for c in transport.calls if c.method == "GET"] == [0, 101]
        assert scope.active_count == 0
        scheduled = [r.payload for r in audit.records if r.payload.get("discard_pacing_status") == "scheduled"]
        assert len(scheduled) == 1
        if scheduled:
            assert scheduled[0]["target_at_monotonic"] == pytest.approx(expected)
            assert scheduled[0]["state_used"] == max(2, used)
    finally:
        await session.aclose("test")


@pytest.mark.parametrize("setup,change,reason", [
    ({"enabled": False}, {}, "disabled"),
    ({"chain_count": 1}, {}, "special_action"),
    ({}, {"attempt_no": 2}, "retry_attempt"),
    ({}, {"action": Discard(Tile("白")), "action_key": "discard:白"}, "special_action"),
    ({}, {"latest_send_at_monotonic": .6}, "insufficient_margin"),
])
async def test_ineligible_or_tight_budget_discard_submits_immediately(setup, change, reason):
    clock, root, scope, session, transport, audit, attempt, posts = await make_draw(**setup)
    await pressure(root, 10)
    started = clock.monotonic()
    try:
        outcome = await clock.run(session.submit(replace(attempt, **change)))
        assert isinstance(outcome, SubmitAccepted), outcome
        assert posts == pytest.approx([started])
        assert any(r.payload.get("discard_pacing_status") == "skipped"
                   and r.payload.get("reason") == reason for r in audit.records)
    finally:
        await session.aclose("test")


async def test_snapshot_draw_also_gets_half_second_when_deadline_allows():
    clock, root, scope, session, transport, audit, attempt, posts = await make_draw(snapshot_only=True)
    try:
        assert isinstance(await clock.run(session.submit(attempt)), SubmitAccepted)
        assert posts == pytest.approx([.5])
        assert any(r.payload.get("discard_pacing_status") == "completed"
                   for r in audit.records)
    finally:
        await session.aclose("test")


async def test_one_second_target_falls_back_to_half_second_when_budget_is_tight():
    clock, root, scope, session, transport, audit, attempt, posts = await make_draw()
    await pressure(root, 16)
    try:
        result = await clock.run(session.submit(replace(attempt, latest_send_at_monotonic=.95)))
        assert isinstance(result, SubmitAccepted)
        assert posts == pytest.approx([.7])
    finally:
        await session.aclose("test")


async def test_computation_that_already_used_one_second_adds_no_wait():
    clock, root, scope, session, transport, audit, attempt, posts = await make_draw()
    clock.advance(1.0)
    await pressure(root, 10)
    try:
        assert isinstance(await clock.run(session.submit(attempt)), SubmitAccepted)
        assert posts == pytest.approx([1.2])
    finally:
        await session.aclose("test")


async def test_hu_is_immediate_even_with_full_state_quota():
    clock, root, scope, session, transport, audit, attempt, posts = await make_draw()
    await pressure(root, 16)
    try:
        outcome = await clock.run(session.submit(replace(attempt, action=Hu(), action_key="hu")))
        assert isinstance(outcome, SubmitAccepted)
        assert posts == pytest.approx([.2])
        assert not any("discard_pacing_status" in r.payload for r in audit.records)
    finally:
        await session.aclose("test")


async def test_wait_holds_no_http_slot_and_still_serializes_own_post():
    clock, root, scope, session, transport, audit, attempt, posts = await make_draw()
    await pressure(root, 10)
    task = asyncio.create_task(session.submit(attempt))
    try:
        await settle()
        assert not task.done() and scope.active_count == 0 and not posts
        peer = root.for_game("peer", max_games=10)
        (await peer.acquire(Priority.ACTION, request_kind=RequestKind.OTHER)).release()
        (await scope.acquire(Priority.POLL)).release()
        duplicate = await session.submit(attempt)
        assert isinstance(duplicate, SubmitNotSent)
        assert clock.monotonic() == pytest.approx(.2)
        assert isinstance(await clock.run(finish(task)), SubmitAccepted)
        assert posts == pytest.approx([.7])
    finally:
        await session.aclose("test")
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("caller_cancel", [False, True])
async def test_close_or_cancellation_during_wait_never_sends_or_marks_ambiguous(caller_cancel):
    clock, root, scope, session, transport, audit, attempt, posts = await make_draw()
    await pressure(root, 10)
    task = asyncio.create_task(session.submit(attempt))
    try:
        await settle()
        if caller_cancel:
            task.cancel()
            with pytest.raises(SubmissionCancelledBeforeSend):
                await task
        else:
            await session.aclose("during_pacing")
            result = await task
            assert isinstance(result, SubmitNotSent) and result.reason == "session_closed"
        assert not posts and scope.active_count == 0
        assert root.state_used_count == 10
        assert not any(r.payload.get("outcome_type") == "SubmitAmbiguous" for r in audit.records)
        assert any(r.payload.get("discard_pacing_status") == "cancelled" for r in audit.records)
    finally:
        await session.aclose("test")


async def test_finished_game_during_wait_is_rechecked_before_post():
    clock, root, scope, session, transport, audit, attempt, posts = await make_draw()
    await pressure(root, 10)
    task = asyncio.create_task(session.submit(attempt))
    try:
        await settle()
        assert isinstance(await session.next_item(), GameFinished)
        result = await clock.run(finish(task))
        assert isinstance(result, SubmitNotSent) and result.reason == "stale_window"
        assert not posts
    finally:
        await session.aclose("test")
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_timer_overshoot_does_not_send_after_original_deadline():
    async def late(clock, seconds):
        clock.advance(seconds + 2.5)

    clock, root, scope, session, transport, audit, attempt, posts = await make_draw(wait=late)
    await pressure(root, 10)
    try:
        result = await session.submit(attempt)
        assert isinstance(result, SubmitNotSent) and result.reason == "deadline_passed"
        assert not posts and scope.active_count == 0
    finally:
        await session.aclose("test")


@pytest.mark.parametrize("setup,expected", [
    ({"missing_ts": True}, .7),
    ({"ts_offset": 2}, .7),
    ({"ts_offset": 2, "receive_delay": 2.3}, 2.3),
])
async def test_pacing_uses_local_watermark_without_server_clock_assumptions(setup, expected):
    """缺失ts仍有本地下界；服务器快2秒、迟到2.3秒不再缓发误过期。"""
    clock, root, scope, session, transport, audit, attempt, posts = await make_draw(**setup)
    await pressure(root, 10)
    try:
        assert isinstance(await clock.run(session.submit(attempt)), SubmitAccepted)
        assert posts == pytest.approx([expected])
    finally:
        await session.aclose("test")


async def test_overshoot_rechecks_tighter_local_bound_even_when_server_clock_is_ahead():
    async def overshoot(clock, seconds):
        clock.advance(seconds + 2.1)

    clock, root, scope, session, transport, audit, attempt, posts = await make_draw(
        ts_offset=2, wait=overshoot)
    await pressure(root, 10)
    try:
        result = await session.submit(replace(attempt, latest_send_at_monotonic=4.5))
        assert clock.monotonic() == pytest.approx(2.8)
        assert isinstance(result, SubmitNotSent) and result.reason == "deadline_passed"
        assert not posts
    finally:
        await session.aclose("test")
