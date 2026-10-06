"""已知无鸣牌兴趣的响应期单事件：下一步非我方行动时暂缓一次取态。

只用公开会话入口、HTTP次数和随后真正可碰窗口验收；不将SSE水位当事件内容。
这对应真实零规划前无兴趣响应的+1帧仍买快照、占用共享额度的路径。
"""
from __future__ import annotations

import asyncio
import copy
import json

import pytest

from _official_testkit import FakeAuditSink, FakeClock, FakeTransport, TIMING, load_fixture, make_audit_context
from hangma_bot.adapters.official import game as game_module
from hangma_bot.adapters.official.game import OfficialGameSession
from hangma_bot.adapters.official.notify import NotifyEndKind, NotifyFrame, NotifyRunResult
from hangma_bot.adapters.official.scheduler import RequestScheduler
from hangma_bot.application.contracts import ObservedActionWindow


class Notify:
    """仅传递测试给出的公开水位，状态事实必须由HTTP获取。"""
    instances = []

    def __init__(self, game_id, transport, *, on_frame, **kwargs):
        self.on_frame = on_frame
        self.instances.append(self)

    async def run(self):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return NotifyRunResult(kind=NotifyEndKind.CANCELLED)

    async def aclose(self):
        pass


async def settle():
    """只让任务登记／处理立即事件，不推进单调时钟或响应期限。"""
    for _ in range(40):
        await asyncio.sleep(0)


@pytest.mark.parametrize("case,expected_first_requests", [
    ("ordinary", 1), ("interesting", 2), ("own_next", 2),
    ("catch_play", 2), ("jump_two", 2), ("reserve_wall", 2),
])
@pytest.mark.asyncio
async def test_skip_only_single_uninteresting_step_then_read_next_offer(monkeypatch, case, expected_first_requests):
    """省掉无关一步，但同周期下一未知帧必须取态，不能漏真正新碰窗。"""
    Notify.instances.clear()
    monkeypatch.setattr(game_module, "SSENotifyClient", Notify)
    clock, audit, transport = FakeClock(), FakeAuditSink(), FakeTransport()
    first = load_fixture("state_response_snapshot_peng.json")
    first["seq"] = 120
    snap = first["snapshot"]
    snap.update(seq=120, turn=0, seat=2, responding_seats=[1, 2, 3],
                last_discard={"seat": 0, "tile": "发", "seq": 120},
                window_deadline_ms=clock.wall_ms() + 1000)
    snap["my_hand"][-2:] = ["9w", "9w"]
    snap["discards"][0] = ["发"]
    if case == "interesting":
        snap["my_hand"][-2:] = ["发", "发"]
    if case == "own_next":
        snap["turn"] = 1
        snap["last_discard"]["seat"] = 1
        snap["discards"][0] = []
        snap["discards"][1] = ["发"]
        snap["responding_seats"] = [0, 2, 3]
    if case == "catch_play":
        snap["god"]["catch_play"] = True
    if case == "reserve_wall":
        snap["wall_remaining"] = 14
    middle = copy.deepcopy(first)
    middle["seq"] = middle["snapshot"]["seq"] = 121
    middle["snapshot"].update(phase="draw", turn=3, responding_seats=[], drawn_tile=None)
    middle["snapshot"]["hand_counts"][3] = 14
    second = copy.deepcopy(first)
    second["seq"] = second["snapshot"]["seq"] = 123 if case == "jump_two" else 122
    second["snapshot"].update(turn=3, responding_seats=[0, 1, 2],
        last_discard={"seat": 3, "tile": "9w", "seq": second["seq"]},
        window_deadline_ms=clock.wall_ms() + 1000)
    second["snapshot"]["discards"][3] = ["9w"]
    state = {"document": first}
    transport.handler = lambda **kwargs: (200, json.dumps(state["document"]))
    session = OfficialGameSession(game_id="g-step", transport=transport,
        scheduler=RequestScheduler(clock=clock.monotonic), timing=TIMING,
        monotonic_clock=clock.monotonic, wall_clock_unix_ms=clock.wall_ms,
        audit=audit, audit_context=make_audit_context, sse_enabled=True, sse_snapshot_first=True)
    consumer = None
    try:
        assert isinstance(await session.next_item(), ObservedActionWindow)
        consumer = asyncio.create_task(session.next_item())
        await settle()
        state["document"] = middle
        water = 122 if case == "jump_two" else 121
        await Notify.instances[0].on_frame(NotifyFrame(seq=water, closed=False, raw=json.dumps({"seq": water})))
        await settle()
        assert len(transport.calls) == expected_first_requests
        state["document"] = second
        await Notify.instances[0].on_frame(NotifyFrame(seq=second["seq"], closed=False,
            raw=json.dumps({"seq": second["seq"]})))
        item = await asyncio.wait_for(consumer, .5)
        assert isinstance(item, ObservedActionWindow)
        assert item.observation.last_discard.tile.code == "9w"
        assert item.window_key.trigger_seq == second["seq"]
        assert len(transport.calls) == expected_first_requests + 1
    finally:
        if consumer is not None and not consumer.done():
            consumer.cancel()
        if consumer is not None:
            await asyncio.gather(consumer, return_exceptions=True)
        await session.aclose("test_complete")
