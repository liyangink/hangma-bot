"""现场修复后的串行补领：409较新事件、短预算、单次失败与取消。"""

import asyncio
import copy

import pytest

from _official_testkit import FakeAuditSink, FakeClock, FakeTransport, load_fixture, make_game_session
from hangma_bot.adapters.official.errors import ConflictError, RateLimitedError, UncertainTransportError
from hangma_bot.adapters.official.scheduler import Priority, RequestScheduler
from hangma_bot.application.contracts import (
    ActionAttempt, ObservedActionWindow, SubmitNotSent, SubmitRejectedNoRefresh,
    SubmitRejectedRetryable,
)
from hangma_bot.kernel.actions import Peng, Tile


class BudgetTransport(FakeTransport):
    """通过公开 request 参数记录整次请求预算；不访问传输内部状态。"""

    def __init__(self):
        super().__init__()
        self.request_budgets = []

    async def request(self, *args, **kwargs):
        self.request_budgets.append(kwargs.get("request_budget_sec"))
        return await super().request(*args, **kwargs)


def _draw_snapshot(seq, *, turn=2, deadline_ms=None):
    doc = load_fixture("state_response_snapshot_draw.json")
    doc["seq"] = seq
    doc["snapshot"]["turn"] = turn
    if turn != 2:
        doc["snapshot"]["drawn_tile"] = None
    if deadline_ms is not None:
        doc["snapshot"]["window_deadline_ms"] = deadline_ms
    return doc


def _script(transport, entries):
    import json
    pending = list(entries)

    def handler(*, method, params=None, long_poll=False, **kwargs):
        assert pending, "出现计划之外的请求，补领不得循环或隐式重发"
        expected_method, expected_seq, expected_long_poll, response = pending.pop(0)
        assert method == expected_method
        assert (params or {}).get("seq") == expected_seq
        assert long_poll is expected_long_poll
        if isinstance(response, Exception):
            raise response
        return 200, json.dumps(response)

    transport.handler = handler
    return pending


def _peng_attempt(window, clock, *, remaining=0.8, attempt_no=1):
    return ActionAttempt(
        decision_id="backfill-proof", attempt_no=attempt_no, plan_revision=1,
        window_key=window.window_key, based_on_authoritative_seq=window.authoritative_seq,
        action=Peng(Tile("2w")), action_key="peng:2w",
        latest_send_at_monotonic=clock.monotonic() + remaining,
    )


async def test_409_backfill_newer_events_closes_retry_path_before_next_candidate():
    clock, transport = FakeClock(), BudgetTransport()
    initial = load_fixture("state_response_snapshot_peng.json")
    refreshed = copy.deepcopy(initial)
    refreshed["seq"] = 121
    pending = _script(transport, [
        ("GET", 0, True, initial),
        ("POST", None, False, ConflictError(409, "INVALID_ACTION", "not executed")),
        ("GET", 0, False, refreshed),
        ("GET", 120, False, {"events": [
            {"seq": 121, "type": "pass", "seat": 0, "tile": ""},
            {"seq": 122, "type": "peng", "seat": 3, "tile": "2w"},
        ]}),
    ])
    session = make_game_session(transport=transport, clock=clock)
    try:
        window = await asyncio.wait_for(session.next_item(), 1)
        outcome = await session.submit(_peng_attempt(window, clock))
        assert isinstance(outcome, SubmitRejectedNoRefresh)
        assert outcome.reason == "newer_events_pending"
        assert outcome.latest_local_seq == 121
        assert 0 < transport.request_budgets[-1] <= 0.100001
        again = await session.submit(_peng_attempt(window, clock, attempt_no=2))
        assert isinstance(again, SubmitNotSent)
        assert sum(call.method == "POST" for call in transport.calls) == 1
        assert not pending
    finally:
        await session.aclose("test_done")


@pytest.mark.parametrize("failure", [
    RateLimitedError(429, "RATE_LIMITED", "backfill limited", retry_after_seconds=1),
    UncertainTransportError("timeout:ReadTimeout"),
])
async def test_optional_backfill_failure_happens_once_and_keeps_authoritative_snapshot(failure):
    clock, transport, audit = FakeClock(), BudgetTransport(), FakeAuditSink()
    pending = _script(transport, [
        ("GET", 0, True, _draw_snapshot(120, turn=0)),
        ("GET", 120, True, _draw_snapshot(121)),
        ("GET", 120, False, failure),
    ])
    session = make_game_session(transport=transport, clock=clock, audit=audit)
    try:
        window = await asyncio.wait_for(session.next_item(), 1)
        assert isinstance(window, ObservedActionWindow)
        assert window.authoritative_seq == 121
        assert window.observation.drawn_tile == Tile("5w")
        assert window.observation.history_complete is False
        assert "history_gap_snapshot" in window.observation.observation_issues
        assert 0 < transport.request_budgets[-1] <= 0.100001
        assert len(transport.calls) == 3 and not pending
        assert sum(call.method == "POST" for call in transport.calls) == 0
        assert any(row.payload.get("history_backfill") == "unavailable" for row in audit.records)
    finally:
        await session.aclose("test_done")


async def test_official_window_with_300ms_remaining_skips_optional_backfill():
    clock, transport, audit = FakeClock(), BudgetTransport(), FakeAuditSink()
    pending = _script(transport, [
        ("GET", 0, True, _draw_snapshot(120, turn=0)),
        ("GET", 120, True, _draw_snapshot(121, deadline_ms=clock.wall_ms() + 300)),
    ])
    session = make_game_session(transport=transport, clock=clock, audit=audit)
    try:
        window = await asyncio.wait_for(session.next_item(), 1)
        assert isinstance(window, ObservedActionWindow)
        assert window.authoritative_seq == 121
        assert window.expires_at_monotonic == pytest.approx(clock.monotonic() + 0.3)
        assert window.observation.history_complete is False
        assert len(transport.calls) == 2 and not pending
        assert any(row.payload.get("history_backfill") == "budget_unavailable" for row in audit.records)
    finally:
        await session.aclose("test_done")


async def test_409_with_50ms_original_send_budget_skips_backfill_without_official_deadline():
    clock, transport, audit = FakeClock(), BudgetTransport(), FakeAuditSink()
    initial = load_fixture("state_response_snapshot_peng.json")
    refreshed = copy.deepcopy(initial)
    refreshed["seq"] = 121
    pending = _script(transport, [
        ("GET", 0, True, initial),
        ("POST", None, False, ConflictError(409, "INVALID_ACTION", "not executed")),
        ("GET", 0, False, refreshed),
    ])
    session = make_game_session(transport=transport, clock=clock, audit=audit)
    try:
        window = await asyncio.wait_for(session.next_item(), 1)
        outcome = await session.submit(_peng_attempt(window, clock, remaining=0.05))
        assert isinstance(outcome, SubmitRejectedRetryable)
        assert outcome.refreshed_window.observation.history_complete is False
        assert len(transport.calls) == 3 and not pending
        assert any(row.payload.get("history_backfill") == "budget_unavailable" for row in audit.records)
    finally:
        await session.aclose("test_done")


async def test_caller_cancellation_during_backfill_propagates_and_releases_only_slot():
    import json
    clock, transport = FakeClock(), BudgetTransport()
    entered, exited = asyncio.Event(), asyncio.Event()
    scheduler = RequestScheduler(clock=clock.monotonic, max_concurrent=1, poll_interval=0)
    calls = 0

    async def handler(*, method, params=None, long_poll=False, **kwargs):
        nonlocal calls
        calls += 1
        assert method == "GET"
        if calls == 1:
            assert params == {"seq": 0}
            return 200, json.dumps(_draw_snapshot(120, turn=0))
        if calls == 2:
            assert params == {"seq": 120} and long_poll
            return 200, json.dumps(_draw_snapshot(121))
        assert calls == 3 and params == {"seq": 120} and not long_poll
        entered.set()
        try:
            await asyncio.Future()
        finally:
            exited.set()

    transport.handler = handler
    session = make_game_session(transport=transport, clock=clock, scheduler=scheduler)
    task = asyncio.create_task(session.next_item())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert exited.is_set()
        assert calls == 3
        # max_concurrent=1：若取消漏释放，公开acquire便不会成功。
        lease = await asyncio.wait_for(scheduler.acquire(Priority.ACTION, deadline_monotonic=clock.monotonic() + 0.1), 0.2)
        lease.release()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await session.aclose("test_done")
