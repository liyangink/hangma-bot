"""权威刷新回归：409与短窗口均不额外查询旧历史。"""

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


async def test_409_refresh_uses_authoritative_snapshot_without_history_request():
    clock, transport = FakeClock(), BudgetTransport()
    initial = load_fixture("state_response_snapshot_peng.json")
    refreshed = copy.deepcopy(initial)
    refreshed["seq"] = 121
    pending = _script(transport, [
        ("GET", 0, True, initial),
        ("POST", None, False, ConflictError(409, "INVALID_ACTION", "not executed")),
        ("GET", 0, False, refreshed),
    ])
    session = make_game_session(transport=transport, clock=clock)
    try:
        window = await session.next_item()
        outcome = await session.submit(_peng_attempt(window, clock))
        assert isinstance(outcome, SubmitRejectedRetryable)
        assert outcome.refreshed_window.authoritative_seq == 121
        assert len(transport.calls) == 3 and not pending
        assert transport.request_budgets[-1] <= .8
    finally:
        await session.aclose("test")


@pytest.mark.parametrize("remaining", [.05, .3, 3.0])
async def test_snapshot_window_is_delivered_without_spending_budget_on_history(remaining):
    clock, transport, audit = FakeClock(), BudgetTransport(), FakeAuditSink()
    pending = _script(transport, [
        ("GET", 0, True, _draw_snapshot(120, turn=0)),
        ("GET", 120, True, _draw_snapshot(125, deadline_ms=clock.wall_ms() + int(remaining * 1000))),
    ])
    session = make_game_session(transport=transport, clock=clock, audit=audit)
    try:
        window = await session.next_item()
        assert isinstance(window, ObservedActionWindow)
        assert window.expires_at_monotonic == pytest.approx(clock.monotonic() + remaining)
        assert not window.observation.history_complete
        assert "history_gap_snapshot" not in window.observation.observation_issues
        assert len(transport.calls) == 2 and not pending
        assert not any(r.payload.get("history_backfill") or r.payload.get("history_recovery") for r in audit.records)
    finally:
        await session.aclose("test")
