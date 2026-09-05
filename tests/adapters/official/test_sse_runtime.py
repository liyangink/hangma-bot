"""SSE 帧驱动运行链路集成回归（2026-09-05 接入，配置默认关）。

覆盖：帧到达 → 短拉增量 → 投递窗口；SSE 流终局（RECONNECTS_EXHAUSTED）
→ 永久降级回长轮询并留 sse_degraded 审计；aclose 取消 SSE 任务无悬挂。
默认关闭路径的行为一致性由既有全套件保证（零新代码路径触发）。
"""

from __future__ import annotations

import asyncio
import json

import pytest

from hangma_bot.adapters.official import game as game_module
from hangma_bot.adapters.official.notify import NotifyEndKind, NotifyFrame, NotifyRunResult
from hangma_bot.application.contracts import AuditKind, ObservedActionWindow
from hangma_bot.kernel.actions import WindowPhase

from _official_testkit import (
    FakeAuditSink,
    FakeClock,
    FakeTransport,
    TIMING,
    load_fixture,
    make_audit_context,
)
from hangma_bot.adapters.official.game import OfficialGameSession
from hangma_bot.adapters.official.scheduler import RequestScheduler


class FakeSseClient:
    """测试替身：捕获 on_frame 回调；run 行为由 scenario 控制。"""

    instances = []

    def __init__(self, game_id, transport, *, budget=None, on_frame=None, on_event=None, config=None, **kw):
        self.game_id = game_id
        self.on_frame = on_frame
        self.hang = True
        FakeSseClient.instances.append(self)

    async def run(self) -> NotifyRunResult:
        if getattr(self, "exhaust_immediately", False):
            return NotifyRunResult(kind=NotifyEndKind.RECONNECTS_EXHAUSTED)
        try:
            await asyncio.Event().wait()  # 挂起直到被取消
        except asyncio.CancelledError:
            return NotifyRunResult(kind=NotifyEndKind.CANCELLED)
        raise AssertionError("unreachable")

    async def aclose(self) -> None:
        return None


def _make_session(transport, clock, audit=None):
    return OfficialGameSession(
        game_id="g_room1_batch1",
        transport=transport,
        scheduler=RequestScheduler(clock=clock.monotonic, sleep=_instant_sleep(clock)),
        timing=TIMING,
        monotonic_clock=clock.monotonic,
        wall_clock_unix_ms=clock.wall_ms,
        audit=audit,
        audit_context=make_audit_context,
        retry_sleep=_instant_sleep(clock),
        sse_enabled=True,
    )


def _instant_sleep(clock):
    async def _sleep(seconds):
        clock.advance(seconds)
    return _sleep


class TestSseFrameDriven:
    async def test_frame_wakes_short_poll_and_delivers(self, monkeypatch) -> None:
        FakeSseClient.instances = []
        monkeypatch.setattr(game_module, "SSENotifyClient", FakeSseClient)
        poll_modes = []
        draw_doc = load_fixture("state_response_snapshot_draw.json")

        def handler(*, method, path, json_body=None, params=None, long_poll=False):
            poll_modes.append(("POST" if method == "POST" else "GET", long_poll))
            return 200, json.dumps(draw_doc)

        transport = FakeTransport()
        transport.handler = handler
        clock = FakeClock()
        session = _make_session(transport, clock)

        async def fire_frame_soon():
            await asyncio.sleep(0.02)
            assert FakeSseClient.instances, "SSE 任务应已启动"
            await FakeSseClient.instances[0].on_frame(_Frame(seq=101))  # 回调为协程（notify 以 await 调用）

        task = asyncio.create_task(fire_frame_soon())
        window = await asyncio.wait_for(session.next_item(), timeout=2)
        await task

        assert isinstance(window, ObservedActionWindow)
        assert window.window_key.phase is WindowPhase.DRAW
        # 帧驱动路径：本轮 GET 必须是短拉（long_poll=False）
        gets = [m for m in poll_modes if m[0] == "GET"]
        assert gets and all(not lp for _, lp in gets), gets
        await session.aclose("done")

    async def test_frame_raw_recorded_as_audit_sse_frame(self, monkeypatch) -> None:
        FakeSseClient.instances = []
        monkeypatch.setattr(game_module, "SSENotifyClient", FakeSseClient)
        draw_doc = load_fixture("state_response_snapshot_draw.json")
        transport = FakeTransport()
        transport.handler = lambda **kw: (200, json.dumps(draw_doc))
        clock = FakeClock()
        audit = FakeAuditSink()
        session = _make_session(transport, clock, audit=audit)

        async def fire_frame_soon():
            await asyncio.sleep(0.02)
            assert FakeSseClient.instances, "SSE 任务应已启动"
            await FakeSseClient.instances[0].on_frame(
                NotifyFrame(seq=101, closed=False, raw='{"seq": 101}')
            )

        task = asyncio.create_task(fire_frame_soon())
        window = await asyncio.wait_for(session.next_item(), timeout=2)
        await task

        assert isinstance(window, ObservedActionWindow)
        frames = [
            record
            for record in audit.records
            if record.kind == AuditKind.RAW_PROTOCOL_STATE
            and record.payload.get("source") == "sse_frame"
        ]
        assert frames, "帧到达应产生 sse_frame 审计原文记录"
        payload = frames[0].payload
        assert payload["endpoint"] == "GET /api/games/{}/notify".format(session.game_id)
        assert payload["seq"] == 101
        assert payload["closed"] is False
        assert payload["raw"] == '{"seq": 101}'
        await session.aclose("done")

    async def test_exhausted_stream_degrades_to_long_poll_with_audit(self, monkeypatch) -> None:
        FakeSseClient.instances = []

        class ExhaustedClient(FakeSseClient):
            exhaust_immediately = True

        monkeypatch.setattr(game_module, "SSENotifyClient", ExhaustedClient)
        draw_doc = load_fixture("state_response_snapshot_draw.json")
        poll_modes = []

        def handler(*, method, path, json_body=None, params=None, long_poll=False):
            poll_modes.append(long_poll)
            return 200, json.dumps(draw_doc)

        transport = FakeTransport()
        transport.handler = handler
        clock = FakeClock()

        class AuditCollector:
            def __init__(self):
                self.records = []

            def emit(self, record):
                self.records.append(record)

        audit = AuditCollector()
        session = _make_session(transport, clock, audit=audit)

        window = await asyncio.wait_for(session.next_item(), timeout=2)
        assert isinstance(window, ObservedActionWindow)
        assert any(p is True for p in poll_modes), "降级后必须回退长轮询"
        kinds = [r.kind for r in audit.records]
        assert AuditKind.PROTOCOL_RECOVERED in kinds
        degraded = [r for r in audit.records if r.payload.get("trigger") == "sse_degraded"]
        assert degraded and degraded[0].payload["reason"] == "reconnects_exhausted"
        assert not session._sse_healthy
        await session.aclose("done")

    async def test_aclose_cancels_sse_task(self, monkeypatch) -> None:
        FakeSseClient.instances = []
        monkeypatch.setattr(game_module, "SSENotifyClient", FakeSseClient)
        transport = FakeTransport()
        transport.handler = lambda **kw: (200, json.dumps(load_fixture("state_response_pending.json")))
        clock = FakeClock()
        session = _make_session(transport, clock)

        consume = asyncio.create_task(session.next_item())
        await asyncio.sleep(0.05)
        assert session._sse_task is not None and not session._sse_task.done()
        await session.aclose("test")
        await asyncio.wait_for(consume, timeout=2)
        assert session._sse_task.done(), "aclose 后 SSE 任务不得悬挂"


class _Frame:
    """最小帧对象（notify.NotifyFrame 同构：seq + closed）。"""

    def __init__(self, seq, closed=False):
        self.seq = seq
        self.closed = closed
