"""快照基线的后续轮询：正常轮询补史、保留缺史事实并正确取消。

均为独立协议脚本，不将其当成官方规则样本；单调时钟通过 FakeClock 控制。
"""

import asyncio
import copy
import inspect
import json

import pytest

from _official_testkit import instant_sleep, FakeClock, FakeTransport, load_fixture, make_game_session
from hangma_bot.adapters.official.errors import UncertainTransportError
from hangma_bot.adapters.official.scheduler import Priority, RequestScheduler
from hangma_bot.application.contracts import ActionAttempt, ObservedActionWindow, SubmitAccepted
from hangma_bot.kernel.actions import Discard, Tile


class BudgetTransport(FakeTransport):
    """只记录公开 request 的总请求预算，不依赖会话内部状态。"""

    def __init__(self):
        super().__init__()
        self.request_budgets = []

    async def request(self, *args, **kwargs):
        self.request_budgets.append(kwargs.get("request_budget_sec"))
        return await super().request(*args, **kwargs)


def _snapshots(clock):
    initial = load_fixture("state_response_snapshot_draw.json")
    initial["seq"] = 120
    s = initial["snapshot"]
    s.update(turn=1, drawn_tile=None)
    s["discards"][1] = ["3b", "6w"]
    s["last_discard"] = {"seat": 3, "tile": "东", "seq": 119}
    s["hand_counts"][2] = 13
    current = copy.deepcopy(initial)
    current["seq"] = 122
    s = current["snapshot"]
    s.update(turn=2, drawn_tile="5w", window_deadline_ms=clock.wall_ms() + 3000)
    s["discards"][1].append("9t")
    s["last_discard"] = {"seat": 1, "tile": "9t", "seq": 121}
    s["hand_counts"][2] = 14
    latest = copy.deepcopy(current)
    latest["seq"] = 124
    s = latest["snapshot"]
    s.update(drawn_tile="7b", wall_remaining=39, window_deadline_ms=clock.wall_ms() + 4000)
    s["discards"][2].append("5w")
    s["last_discard"] = {"seat": 2, "tile": "5w", "seq": 123}
    return initial, current, latest


OLD_EVENTS = [
    {"seq": 121, "type": "tile_discarded", "seat": 1, "tile": "9t"},
    {"seq": 122, "type": "tile_drawn", "seat": 2, "tile": "5w"},
]
NEW_EVENTS = [
    {"seq": 123, "type": "tile_discarded", "seat": 2, "tile": "5w"},
    {"seq": 124, "type": "tile_drawn", "seat": 2, "tile": "7b"},
]


def _script(transport, entries):
    pending = list(entries)

    async def handler(*, method, params=None, long_poll=False, **kwargs):
        assert pending, "出现脚本之外的请求；补领不得循环追赶"
        wanted_method, wanted_seq, wanted_long, response = pending.pop(0)
        assert (method, (params or {}).get("seq"), long_poll) == (
            wanted_method, wanted_seq, wanted_long
        ), "快照先交付，后续正常轮询才用缺史游标"
        if isinstance(response, Exception):
            raise response
        if callable(response):
            response = response()
            if inspect.isawaitable(response):
                response = await response
        return 200, json.dumps(response)

    transport.handler = handler
    return pending


def _attempt(window, clock):
    return ActionAttempt(
        decision_id="deferred-history-proof", attempt_no=1, plan_revision=1,
        window_key=window.window_key, based_on_authoritative_seq=window.authoritative_seq,
        action=Discard(Tile("5w")), action_key="discard:5w",
        latest_send_at_monotonic=clock.monotonic() + 1.0,
    )


async def test_accepted_action_precedes_regular_history_recovery():
    clock, transport = FakeClock(), BudgetTransport()
    initial, current, latest = _snapshots(clock)
    latest["events"] = copy.deepcopy(NEW_EVENTS)
    pending = _script(transport, [
        ("GET", 0, True, initial), ("GET", 120, True, current),
        ("POST", None, False, {"ok": True}), ("GET", 120, True, latest),
    ])
    session = make_game_session(transport=transport, clock=clock)
    try:
        first = await session.next_item()
        assert isinstance(await session.submit(_attempt(first, clock)), SubmitAccepted)
        second = await session.next_item()
        assert second.authoritative_seq == 124
        assert second.observation.drawn_tile == Tile("7b")
        assert [e.seq for e in second.observation.public_history] == [123, 124]
        assert second.observation.discards == tuple(tuple(Tile(t) for t in row) for row in latest["snapshot"]["discards"])
        assert not pending
    finally:
        await session.aclose("test")


async def test_regular_history_poll_cancellation_releases_own_slots():
    clock, transport = FakeClock(), BudgetTransport()
    initial, current, _ = _snapshots(clock)
    entered, exited = asyncio.Event(), asyncio.Event()
    async def held():
        entered.set()
        try:
            await asyncio.Future()
        finally:
            exited.set()
    pending = _script(transport, [
        ("GET", 0, True, initial), ("GET", 120, True, current),
        ("POST", None, False, {}), ("GET", 120, True, held),
    ])
    owner = RequestScheduler(clock=clock.monotonic, sleep=instant_sleep(clock), poll_interval=0)
    scheduler = owner.for_game("one", max_games=4)
    session = make_game_session(transport=transport, clock=clock, scheduler=scheduler)
    try:
        first = await session.next_item()
        assert isinstance(await session.submit(_attempt(first, clock)), SubmitAccepted)
        task = asyncio.create_task(session.next_item())
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert exited.is_set() and scheduler.active_count == 0
        assert owner.for_game("other", max_games=4).cooldown_remaining == 0
        assert not pending
    finally:
        await session.aclose("test")


async def test_missing_original_events_are_audited_when_session_closes():
    from _official_testkit import FakeAuditSink
    clock, transport, audit = FakeClock(), BudgetTransport(), FakeAuditSink()
    initial, current, _ = _snapshots(clock)
    pending = _script(transport, [("GET", 0, True, initial), ("GET", 120, True, current)])
    session = make_game_session(transport=transport, clock=clock, audit=audit)
    await session.next_item()
    await session.aclose("test")
    closure = next(r.payload for r in audit.records if r.payload.get("history_closure"))
    assert closure["missing_ranges"] == [[121, 122]]
    assert not closure["history_complete"]
    assert not pending
