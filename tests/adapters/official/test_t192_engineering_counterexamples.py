"""只读工程复核的公开接口反例；不修改被审副本、不访问网络/真实凭证。"""

import asyncio
import copy
import json

import httpx
import pytest

from _official_testkit import FakeAuditSink, FakeClock, FakeTransport, TIMING, load_fixture, make_audit_context
from hangma_bot.adapters.official import game as game_module
from hangma_bot.adapters.official.game import OfficialGameSession
from hangma_bot.adapters.official.notify import NotifyEndKind, NotifyFrame, NotifyRunResult
from hangma_bot.adapters.official.scheduler import RequestScheduler
from hangma_bot.adapters.official.transport import OfficialTransport, TransportConfig
from hangma_bot.application.contracts import ObservedActionWindow


async def settle():
    for _ in range(60):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_first_close_does_not_cancel_an_already_closing_state_request_again():
    """外部先取消next_item，HTTP异步finally已开始，再aclose不能二次打断。"""
    started, closing, release, ended = (asyncio.Event() for _ in range(4))
    clock, audit = FakeClock(), FakeAuditSink()

    async def handler(request):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            closing.set()
            await release.wait()
            ended.set()
        return httpx.Response(200, json=load_fixture("state_response_snapshot_peng.json"))

    transport = OfficialTransport("fixture-only", TransportConfig(base_url="https://platform.invalid",
        insecure_hosts=frozenset()), transport_handler=httpx.MockTransport(handler))
    session = OfficialGameSession(game_id="g-already-closing", transport=transport,
        scheduler=RequestScheduler(clock=clock.monotonic), timing=TIMING,
        monotonic_clock=clock.monotonic, wall_clock_unix_ms=clock.wall_ms,
        audit=audit, audit_context=make_audit_context)
    consumer, closer = asyncio.create_task(session.next_item()), None
    try:
        await asyncio.wait_for(started.wait(), .5)
        consumer.cancel()
        await asyncio.wait_for(closing.wait(), .5)
        closer = asyncio.create_task(session.aclose("while_request_finally"))
        await settle()
        assert not closer.done(), "aclose二次cancel中断已开始的HTTP finally，提前返回"
        release.set()
        await asyncio.gather(consumer, closer, return_exceptions=True)
        assert ended.is_set(), "owned请求的异步关闭没有完成"
    finally:
        release.set()
        await asyncio.gather(*(task for task in (consumer, closer) if task is not None), return_exceptions=True)
        await session.aclose("test_complete")
        await transport.aclose()


class Notify:
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


@pytest.mark.asyncio
async def test_consumed_events_must_not_reuse_stale_response_snapshot_to_skip_new_discard(monkeypatch):
    """支持的SSE增量对照路径中，旧响应快照不能证明当前仍在响应期。"""
    Notify.instances.clear()
    monkeypatch.setattr(game_module, "SSENotifyClient", Notify)
    clock, audit, transport = FakeClock(), FakeAuditSink(), FakeTransport()
    first = load_fixture("state_response_snapshot_peng.json")
    first["seq"] = first["snapshot"]["seq"] = 120
    snap = first["snapshot"]
    snap.update(turn=0, seat=2, responding_seats=[1, 2, 3],
        hand_counts=[13, 13, 13, 13], last_discard={"seat": 0, "tile": "发", "seq": 120},
        window_deadline_ms=clock.wall_ms() + 1000)
    snap["my_hand"][-2:] = ["9w", "9w"]
    snap["discards"] = [["发"], [], [], []]
    ts = clock.wall_ms() // 1000
    events = [dict(seq=121 + index, type="timeout", seat=seat,
        data={"kind": "response", "window": "peng"}, ts=ts) for index, seat in enumerate((1, 2, 3))]
    events += [dict(seq=124, type="timeout", seat=1, data={"kind": "response", "window": "chi"}, ts=ts),
        dict(seq=125, type="tile_drawn", seat=1, data={}, ts=ts)]
    progressed = dict(seq=125, events=events)
    new_events = dict(seq=126, events=[dict(seq=126, type="tile_discarded", seat=1, tile="9w", data={}, ts=ts)])
    offer = copy.deepcopy(first)
    offer["seq"] = offer["snapshot"]["seq"] = 126
    offer["snapshot"].update(turn=1, responding_seats=[2, 3, 0], wall_remaining=35,
        last_discard={"seat": 1, "tile": "9w", "seq": 126})
    offer["snapshot"]["discards"][1] = ["9w"]
    stage = {"value": "initial"}

    def handler(**kwargs):
        if stage["value"] == "initial":
            doc = first
        elif stage["value"] == "progress":
            doc = progressed
        else:
            doc = offer if kwargs.get("params", {}).get("seq") == 0 else new_events
        return 200, json.dumps(doc)

    transport.handler = handler
    session = OfficialGameSession(game_id="g-stale", transport=transport,
        scheduler=RequestScheduler(clock=clock.monotonic), timing=TIMING,
        monotonic_clock=clock.monotonic, wall_clock_unix_ms=clock.wall_ms,
        audit=audit, audit_context=make_audit_context, sse_enabled=True, sse_snapshot_first=False)
    consumer = None
    try:
        assert isinstance(await session.next_item(), ObservedActionWindow)
        consumer = asyncio.create_task(session.next_item())
        await settle()
        stage["value"] = "progress"
        await Notify.instances[0].on_frame(NotifyFrame(seq=125))
        await settle()
        assert len(transport.calls) == 2
        assert transport.calls[1].params["seq"] == 120
        stage["value"] = "offer"
        await Notify.instances[0].on_frame(NotifyFrame(seq=126))
        await settle()
        assert len(transport.calls) >= 3, "旧snapshot仍为response_peng，误跳过新的可碰弃牌水位126"
        item = await asyncio.wait_for(consumer, .5)
        assert isinstance(item, ObservedActionWindow)
        assert item.window_key.trigger_seq == 126
        assert item.observation.last_discard.tile.code == "9w"
    finally:
        if consumer is not None and not consumer.done():
            consumer.cancel()
        if consumer is not None:
            await asyncio.gather(consumer, return_exceptions=True)
        await session.aclose("test_complete")
