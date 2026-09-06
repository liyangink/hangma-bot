"""延后补史的公开会话回归：补旧游标、只修历史、动作优先与取消。

均为独立协议脚本，不将其当成官方规则样本；单调时钟通过 FakeClock 控制。
"""

import asyncio
import copy
import inspect
import json

import pytest

from _official_testkit import FakeClock, FakeTransport, load_fixture, make_game_session
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
        ), "欠账补领应使用旧事件游标，不得使用已超前的牌面水位"
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


def _prefix(initial, current):
    return [
        ("GET", 0, True, initial),
        ("GET", 120, True, current),
        ("GET", 120, False, UncertainTransportError("timeout:ReadTimeout")),
        ("POST", None, False, {"ok": True}),
    ]


async def _first_window_and_accept(session, transport, clock):
    first = await asyncio.wait_for(session.next_item(), 1)
    assert isinstance(first, ObservedActionWindow)
    assert first.authoritative_seq == 122
    assert first.observation.drawn_tile == Tile("5w")
    assert first.observation.history_complete is False
    assert "history_gap_snapshot" in first.observation.observation_issues
    assert len(transport.calls) == 3, "补领失败应先交付现有动作，不在同一轮重试"
    assert 0 < transport.request_budgets[2] <= 0.100001
    assert isinstance(await session.submit(_attempt(first, clock)), SubmitAccepted)
    clock.advance(1.0)
    return first


def _assert_latest_without_replaying_history(window, latest):
    assert isinstance(window, ObservedActionWindow)
    obs = window.observation
    assert window.authoritative_seq == obs.consumed_seq == 124
    assert obs.drawn_tile == Tile("7b")
    assert obs.my_hand == tuple(Tile(x) for x in latest["snapshot"]["my_hand"])
    assert obs.discards == tuple(tuple(Tile(x) for x in row) for row in latest["snapshot"]["discards"])
    assert obs.remaining_tile_count == 39
    history = {event.seq: event for event in obs.public_history}
    assert set(history) >= {121, 122, 123, 124}
    assert len(obs.public_history) == len(history), "重叠旧事件只能入历史一次"
    assert history[121].tiles == (Tile("9t"),)
    assert history[122].tiles == (Tile("5w"),)


async def test_failed_immediate_backfill_is_retried_after_accepted_action_without_replaying_board():
    clock, transport = FakeClock(), BudgetTransport()
    initial, current, latest = _snapshots(clock)
    latest["events"] = copy.deepcopy(NEW_EVENTS)
    pending = _script(transport, _prefix(initial, current) + [
        ("GET", 120, False, {"events": copy.deepcopy(OLD_EVENTS)}),
        ("GET", 122, True, latest),
    ])
    session = make_game_session(transport=transport, clock=clock)
    try:
        await _first_window_and_accept(session, transport, clock)
        second = await asyncio.wait_for(session.next_item(), 1)
        _assert_latest_without_replaying_history(second, latest)
        assert 0 < transport.request_budgets[4] <= 0.100001
        assert not pending
    finally:
        await session.aclose("test_done")


@pytest.mark.parametrize("response_kind", ["newer_events", "newer_snapshot"])
async def test_deferred_backfill_must_consume_newer_authority_before_delivering(response_kind):
    clock, transport = FakeClock(), BudgetTransport()
    initial, current, latest = _snapshots(clock)
    if response_kind == "newer_events":
        suffix = [
            ("GET", 120, False, {"events": copy.deepcopy(OLD_EVENTS + NEW_EVENTS)}),
            ("GET", 0, False, latest),
        ]
    else:
        latest["events"] = copy.deepcopy(OLD_EVENTS + NEW_EVENTS)
        suffix = [("GET", 120, False, latest)]
    pending = _script(transport, _prefix(initial, current) + suffix)
    session = make_game_session(transport=transport, clock=clock)
    try:
        await _first_window_and_accept(session, transport, clock)
        second = await asyncio.wait_for(session.next_item(), 1)
        _assert_latest_without_replaying_history(second, latest)
        assert not pending
    finally:
        await session.aclose("test_done")


async def test_window_with_only_300ms_remaining_is_delivered_before_history_recovery():
    clock, transport = FakeClock(), BudgetTransport()
    initial, current, _ = _snapshots(clock)
    current["snapshot"]["window_deadline_ms"] = clock.wall_ms() + 300
    pending = _script(transport, [
        ("GET", 0, True, initial),
        ("GET", 120, True, current),
    ])
    session = make_game_session(transport=transport, clock=clock)
    try:
        window = await asyncio.wait_for(session.next_item(), 1)
        assert isinstance(window, ObservedActionWindow)
        assert window.authoritative_seq == 122
        assert window.expires_at_monotonic == pytest.approx(clock.monotonic() + .3)
        assert window.observation.history_complete is False
        assert len(transport.calls) == 2 and not pending
    finally:
        await session.aclose("test_done")


async def test_cancellation_during_deferred_backfill_propagates_and_releases_scheduler():
    clock, transport = FakeClock(), BudgetTransport()
    initial, current, _ = _snapshots(clock)
    entered, exited = asyncio.Event(), asyncio.Event()

    async def block_backfill():
        entered.set()
        try:
            await asyncio.Future()
        finally:
            exited.set()

    pending = _script(transport, _prefix(initial, current) + [
        ("GET", 120, False, block_backfill),
    ])
    scheduler = RequestScheduler(clock=clock.monotonic, max_concurrent=1, poll_interval=0)
    session = make_game_session(transport=transport, clock=clock, scheduler=scheduler)
    task = None
    try:
        await _first_window_and_accept(session, transport, clock)
        task = asyncio.create_task(session.next_item())
        waiter = asyncio.create_task(entered.wait())
        done, _ = await asyncio.wait({task, waiter}, timeout=1, return_when=asyncio.FIRST_COMPLETED)
        if task in done:
            await task  # 当前缺陷会请求错误游标，直接保留明确红例。
        assert entered.is_set(), "next_item 应进入有界旧游标补领"
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert exited.is_set()
        lease = await asyncio.wait_for(scheduler.acquire(Priority.ACTION, deadline_monotonic=clock.monotonic() + .1), .2)
        lease.release()
        assert not pending
    finally:
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if 'waiter' in locals():
            waiter.cancel()
            await asyncio.gather(waiter, return_exceptions=True)
        await session.aclose("test_done")


async def test_repeated_history_failures_back_off_stop_after_three_and_keep_normal_polling():
    clock, transport = FakeClock(), BudgetTransport()
    initial, current, latest = _snapshots(clock)
    current["snapshot"]["window_deadline_ms"] = clock.wall_ms() + 10_000
    latest["snapshot"]["window_deadline_ms"] = clock.wall_ms() + 11_000
    latest["events"] = copy.deepcopy(NEW_EVENTS)

    def pending_after(seconds):
        def response():
            clock.advance(seconds)
            return {"pending": True}
        return response

    failure = UncertainTransportError("timeout:ReadTimeout")
    pending = _script(transport, _prefix(initial, current) + [
        ("GET", 120, False, failure),
        ("GET", 122, True, pending_after(.1)),
        ("GET", 122, True, pending_after(.3)),  # 未到退避点时只正常poll
        ("GET", 120, False, failure),
        ("GET", 122, True, pending_after(.6)),
        ("GET", 120, False, failure),
        ("GET", 122, True, pending_after(2.0)),
        ("GET", 122, True, pending_after(2.0)),  # 三次后即使退避到期也不再补
        ("GET", 122, True, latest),
    ])
    session = make_game_session(transport=transport, clock=clock)
    try:
        await _first_window_and_accept(session, transport, clock)
        second = await asyncio.wait_for(session.next_item(), 1)
        assert isinstance(second, ObservedActionWindow)
        assert second.authoritative_seq == 124
        assert second.observation.history_complete is False
        short_indexes = [i for i, call in enumerate(transport.calls)
                         if call.method == "GET" and call.params == {"seq": 120} and not call.long_poll]
        assert len(short_indexes) == 4  # 首次即时补领一次 + 延后三次
        assert all(0 < transport.request_budgets[i] <= .100001 for i in short_indexes)
        assert not pending
    finally:
        await session.aclose("test_done")


async def test_snapshot_only_recovery_cannot_clear_missing_history_in_closure():
    from _official_testkit import FakeAuditSink

    clock, transport, audit = FakeClock(), BudgetTransport(), FakeAuditSink()
    initial, current, latest = _snapshots(clock)
    latest["events"] = copy.deepcopy(NEW_EVENTS)
    pending = _script(transport, _prefix(initial, current) + [
        ("GET", 120, False, copy.deepcopy(current)),  # 仍只有当前权威牌面
        ("GET", 122, True, latest),
    ])
    session = make_game_session(transport=transport, clock=clock, audit=audit)
    try:
        await _first_window_and_accept(session, transport, clock)
        second = await asyncio.wait_for(session.next_item(), 1)
        assert isinstance(second, ObservedActionWindow)
        assert second.observation.history_complete is False
        assert "history_gap_snapshot" in second.observation.observation_issues
        assert not any(e.seq in (121, 122) for e in second.observation.public_history)
        assert not pending
    finally:
        await session.aclose("test_done")
    closure = [row.payload for row in audit.records if "history_closure" in row.payload]
    assert len(closure) == 1
    assert closure[0]["history_complete"] is False
    assert [121, 122] in closure[0]["missing_ranges"]


@pytest.mark.parametrize("mode", ["unsubmitted", "ambiguous"])
async def test_unsubmitted_or_ambiguous_window_never_runs_deferred_history(mode):
    from hangma_bot.application.contracts import SubmitAmbiguous

    clock, transport = FakeClock(), BudgetTransport()
    initial, current, _ = _snapshots(clock)
    entered = asyncio.Event()

    async def normal_poll():
        entered.set()
        await asyncio.Future()

    prefix = _prefix(initial, current)[:3]
    if mode == "ambiguous":
        prefix.append(("POST", None, False, UncertainTransportError("timeout:ReadTimeout")))
    pending = _script(transport, prefix + [("GET", 122, True, normal_poll)])
    session = make_game_session(transport=transport, clock=clock)
    task = None
    waiter = None
    try:
        first = await asyncio.wait_for(session.next_item(), 1)
        assert isinstance(first, ObservedActionWindow)
        if mode == "ambiguous":
            assert isinstance(await session.submit(_attempt(first, clock)), SubmitAmbiguous)
        clock.advance(1.0)
        task = asyncio.create_task(session.next_item())
        waiter = asyncio.create_task(entered.wait())
        done, _ = await asyncio.wait({task, waiter}, timeout=1, return_when=asyncio.FIRST_COMPLETED)
        if task in done:
            await task
        assert entered.is_set(), "应继续正常权威查询，不运行可选旧史补领"
        short_calls = [call for call in transport.calls if call.method == "GET" and not call.long_poll]
        assert len(short_calls) == 1  # 仅首次即时补领；next_item不再调用旧游标
        assert not pending
    finally:
        for active in (task, waiter):
            if active is not None:
                active.cancel()
                await asyncio.gather(active, return_exceptions=True)
        await session.aclose("test_done")
