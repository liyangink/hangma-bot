"""SSE 帧驱动运行链路集成回归（2026-09-05 接入，配置默认关）。

覆盖：帧到达 → 短拉增量 → 投递窗口；SSE 流终局（RECONNECTS_EXHAUSTED）
→ 返回可恢复故障，不切回长轮询；aclose 取消 SSE 任务无悬挂。
默认关闭路径的行为一致性由既有全套件保证（零新代码路径触发）。
"""

from __future__ import annotations

import asyncio
import json

import pytest

from hangma_bot.adapters.official import game as game_module
from hangma_bot.adapters.official.errors import AuthError, ForbiddenError, NotFoundError
from hangma_bot.adapters.official.notify import NotifyEndKind, NotifyFrame, NotifyRunResult
from hangma_bot.application.contracts import ActionAttempt, AuditKind, GameFailed, GameFinished, ObservedActionWindow, SubmitAccepted
from hangma_bot.kernel.actions import Discard, Tile, WindowPhase

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

    async def test_exhausted_stream_fails_without_long_poll(self, monkeypatch) -> None:
        FakeSseClient.instances = []

        class ExhaustedClient(FakeSseClient):
            exhaust_immediately = True

        monkeypatch.setattr(game_module, "SSENotifyClient", ExhaustedClient)
        draw_doc = load_fixture("state_response_snapshot_draw.json")
        draw_doc["snapshot"]["turn"] = 1  # 他家行动，我方无待交付窗口
        draw_doc["snapshot"]["drawn_tile"] = None
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

        failure = await asyncio.wait_for(session.next_item(), timeout=2)
        assert isinstance(failure, GameFailed)
        assert failure.recoverable
        assert poll_modes and not any(poll_modes), "SSE 模式不得回退长轮询"
        kinds = [r.kind for r in audit.records]
        assert AuditKind.PROTOCOL_RECOVERED in kinds
        degraded = [r for r in audit.records if r.payload.get("trigger") == "sse_degraded"]
        assert degraded and degraded[0].payload["reason"] == "reconnects_exhausted"
        assert not session._sse_healthy
        await session.aclose("done")

    @pytest.mark.parametrize("error_type,recoverable", [
        (AuthError, False), (ForbiddenError, False), (NotFoundError, True),
    ])
    async def test_terminal_stream_preserves_failure_classification(
        self, monkeypatch, error_type, recoverable
    ) -> None:
        """通知端点永久认证错误不能让监督层反复重建场次。"""

        class TerminalClient(FakeSseClient):
            async def run(self):
                return NotifyRunResult(
                    kind=NotifyEndKind.TERMINAL,
                    error=error_type(401, None, "fixture"),
                )

        FakeSseClient.instances = []
        monkeypatch.setattr(game_module, "SSENotifyClient", TerminalClient)
        snapshot = load_fixture("state_response_snapshot_draw.json")
        snapshot["snapshot"]["turn"] = 1
        snapshot["snapshot"]["drawn_tile"] = None
        calls = []

        def handler(*, method, path, json_body=None, params=None, long_poll=False):
            calls.append(long_poll)
            return 200, json.dumps(snapshot)

        transport = FakeTransport()
        transport.handler = handler
        session = _make_session(transport, FakeClock())
        failure = await asyncio.wait_for(session.next_item(), timeout=2)
        assert isinstance(failure, GameFailed)
        assert failure.recoverable is recoverable
        assert failure.reason == "sse_terminal:" + error_type.__name__
        assert calls and not any(calls)
        await session.aclose("done")

    @pytest.mark.parametrize("frame_seq", [121, 123])
    async def test_frame_during_response_phase_reads_incremental(self, monkeypatch, frame_seq) -> None:
        """有我方鸣牌兴趣时即使帧 +3 也读增量；收帧不等于看门狗到时。"""

        FakeSseClient.instances = []
        monkeypatch.setattr(game_module, "SSENotifyClient", FakeSseClient)
        peng = load_fixture("state_response_snapshot_peng.json")
        peng["snapshot"]["responding_seats"] = [0, 3]
        finished = load_fixture("state_response_finished.json")
        calls = []

        def handler(*, method, path, json_body=None, params=None, long_poll=False):
            calls.append((params["seq"], long_poll))
            return 200, json.dumps(peng if len(calls) == 1 else finished)

        transport = FakeTransport()
        transport.handler = handler
        clock = FakeClock()
        session = _make_session(transport, clock)

        async def fire_frame():
            await asyncio.sleep(0.02)
            await FakeSseClient.instances[0].on_frame(_Frame(seq=frame_seq))

        emitter = asyncio.create_task(fire_frame())
        await asyncio.wait_for(session.next_item(), timeout=2)
        await emitter
        assert calls[:2] == [(0, False), (120, False)]
        await session.aclose("done")

    async def test_plain_discard_timeout_group_waits_for_next_relevant_frame(self, monkeypatch) -> None:
        """已知普通弃牌后的一帧 +3 可暂缓读；后续歧义帧从已消费游标补齐。"""

        FakeSseClient.instances = []
        monkeypatch.setattr(game_module, "SSENotifyClient", FakeSseClient)
        peng = load_fixture("state_response_snapshot_peng.json")
        peng["snapshot"]["turn"] = 3
        peng["snapshot"]["responding_seats"] = [0, 1]
        peng["snapshot"]["last_discard"] = {"seat": 3, "tile": "9b", "seq": 120}
        events = {"seq": 124, "gap": False, "events": [
            {"seq": seq, "type": "timeout", "seat": seat, "tile": "",
             "data": {"kind": "response", "window": "peng"}, "ts": 0}
            for seq, seat in ((121, 0), (122, 1), (123, 2))
        ] + [{"seq": 124, "type": "pass", "seat": 0, "tile": "", "data": None, "ts": 0}]}
        calls = []

        def handler(*, method, path, json_body=None, params=None, long_poll=False):
            calls.append((params["seq"], long_poll))
            return 200, json.dumps(peng if len(calls) == 1 else events)

        transport = FakeTransport()
        transport.handler = handler
        audit = FakeAuditSink()
        session = _make_session(transport, FakeClock(), audit=audit)
        consume = asyncio.create_task(session.next_item())
        for _ in range(100):
            if calls and FakeSseClient.instances:
                break
            await asyncio.sleep(0)
        assert calls == [(0, False)]
        await FakeSseClient.instances[0].on_frame(_Frame(seq=123))
        for _ in range(100):
            await asyncio.sleep(0)
        assert calls == [(0, False)], "纯碰窗走满不得拉状态"
        await FakeSseClient.instances[0].on_frame(_Frame(seq=124))
        for _ in range(100):
            if len(calls) >= 2:
                break
            await asyncio.sleep(0)
        assert calls[:2] == [(0, False), (120, False)]
        assert any(record.payload.get("sse_skip_verification") == "verified"
                   and record.payload.get("skip_kind") == "peng_timeout"
                   for record in audit.records)
        assert any(record.payload.get("request_timing", {}).get("query_purpose") == "sse_frame"
                   and record.payload["request_timing"]["scheduler_priority"] == "DISCARD_WATCH"
                   for record in audit.records)
        await session.aclose("done")
        await asyncio.wait_for(consume, timeout=2)

    async def test_skipped_timeout_silence_uses_short_snapshot_probe(self, monkeypatch) -> None:
        """碰窗 +3 后没有任何新帧，短探针仍对齐权威状态；不挂长轮询。"""

        FakeSseClient.instances = []
        monkeypatch.setattr(game_module, "SSENotifyClient", FakeSseClient)
        monkeypatch.setattr(game_module, "_SSE_PHASE_PROBE_SEC", 0.01)
        peng = load_fixture("state_response_snapshot_peng.json")
        peng["snapshot"].update({
            "turn": 3, "responding_seats": [0, 1],
            "last_discard": {"seat": 3, "tile": "9b", "seq": 120},
        })
        finished = load_fixture("state_response_finished.json")
        calls = []

        def handler(*, method, path, json_body=None, params=None, long_poll=False):
            calls.append((params["seq"], long_poll))
            return 200, json.dumps(peng if len(calls) == 1 else finished)

        transport = FakeTransport()
        transport.handler = handler
        audit = FakeAuditSink()
        session = _make_session(transport, FakeClock(), audit=audit)
        consume = asyncio.create_task(session.next_item())
        for _ in range(100):
            if calls and FakeSseClient.instances:
                break
            await asyncio.sleep(0)
        await FakeSseClient.instances[0].on_frame(_Frame(seq=123))
        result = await asyncio.wait_for(consume, timeout=2)
        assert isinstance(result, GameFinished)
        assert calls == [(0, False), (0, False)]
        assert any(record.payload.get("sse_skip_verification") == "unobservable"
                   and record.payload.get("filter_active") is True
                   for record in audit.records)
        await session.aclose("done")

    async def test_accepted_plain_discard_echo_does_not_read_state(self, monkeypatch) -> None:
        """本人普通弃牌已获 POST 接受；回显和随后的 +3 不各占一次 GET。"""

        FakeSseClient.instances = []
        monkeypatch.setattr(game_module, "SSENotifyClient", FakeSseClient)
        draw = load_fixture("state_response_snapshot_draw.json")
        finished = load_fixture("state_response_finished.json")
        calls = []

        def handler(*, method, path, json_body=None, params=None, long_poll=False):
            calls.append((method, params["seq"] if params else None, long_poll))
            if method == "POST":
                return 200, "{}"
            return 200, json.dumps(draw if sum(c[0] == "GET" for c in calls) == 1 else finished)

        transport = FakeTransport()
        transport.handler = handler
        session = _make_session(transport, FakeClock())
        window = await asyncio.wait_for(session.next_item(), timeout=2)
        assert isinstance(window, ObservedActionWindow)
        attempt = ActionAttempt(
            decision_id="d-sse-echo", attempt_no=1, plan_revision=1,
            window_key=window.window_key, based_on_authoritative_seq=window.window_key.trigger_seq,
            action=Discard(Tile("5w")), action_key="discard:5w", latest_send_at_monotonic=1005.0,
        )
        assert isinstance(await session.submit(attempt), SubmitAccepted)
        consume = asyncio.create_task(session.next_item())
        await FakeSseClient.instances[0].on_frame(_Frame(seq=102))
        for _ in range(100):
            await asyncio.sleep(0)
        assert [c for c in calls if c[0] == "GET"] == [("GET", 0, False)]
        await FakeSseClient.instances[0].on_frame(_Frame(seq=105))
        for _ in range(100):
            await asyncio.sleep(0)
        assert [c for c in calls if c[0] == "GET"] == [("GET", 0, False)]
        await FakeSseClient.instances[0].on_frame(_Frame(seq=106))
        await asyncio.wait_for(consume, timeout=2)
        assert [c for c in calls if c[0] == "GET"][:2] == [("GET", 0, False), ("GET", 101, False)]
        await session.aclose("done")

    async def test_opponent_draw_after_confirmed_chi_timeout_waits_for_discard(self, monkeypatch) -> None:
        """吃窗走满已由状态确认且下个摸牌者为他家时，单帧摸牌不占 GET。"""

        FakeSseClient.instances = []
        monkeypatch.setattr(game_module, "SSENotifyClient", FakeSseClient)
        chi = load_fixture("state_response_snapshot_peng.json")
        chi["snapshot"].update({
            "phase": "response_chi", "turn": 3, "responding_seats": [0],
            "last_discard": {"seat": 3, "tile": "9b", "seq": 120},
        })
        timeout = {"seq": 121, "gap": False, "events": [
            {"seq": 121, "type": "timeout", "seat": 0, "tile": "",
             "data": {"kind": "response", "window": "chi"}, "ts": 0}]}
        after_draw = {"seq": 123, "gap": False, "events": [
            {"seq": 122, "type": "tile_drawn", "seat": 0, "tile": "", "data": None, "ts": 0},
            {"seq": 123, "type": "tile_discarded", "seat": 0, "tile": "8b", "data": {}, "ts": 0},
        ]}
        calls = []

        def handler(*, method, path, json_body=None, params=None, long_poll=False):
            calls.append(params["seq"])
            return 200, json.dumps({0: chi, 120: timeout, 121: after_draw}[params["seq"]])

        transport = FakeTransport()
        transport.handler = handler
        session = _make_session(transport, FakeClock())
        consume = asyncio.create_task(session.next_item())
        for _ in range(100):
            if calls and FakeSseClient.instances:
                break
            await asyncio.sleep(0)
        await FakeSseClient.instances[0].on_frame(_Frame(seq=121))
        for _ in range(100):
            if len(calls) >= 2:
                break
            await asyncio.sleep(0)
        assert calls == [0, 120]
        await FakeSseClient.instances[0].on_frame(_Frame(seq=122))
        for _ in range(100):
            await asyncio.sleep(0)
        assert calls == [0, 120]
        await FakeSseClient.instances[0].on_frame(_Frame(seq=123))
        for _ in range(100):
            if len(calls) >= 3:
                break
            await asyncio.sleep(0)
        assert calls[:3] == [0, 120, 121]
        await session.aclose("done")
        await asyncio.wait_for(consume, timeout=2)

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
