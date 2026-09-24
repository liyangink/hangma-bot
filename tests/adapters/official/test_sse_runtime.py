"""SSE 帧驱动运行链路集成回归（2026-09-05 接入，配置默认关）。

覆盖：帧到达 → 权威快照 → 投递窗口，以及旧增量路径的跳帧文法对照；SSE 流终局（RECONNECTS_EXHAUSTED）
→ 返回可恢复故障，不切回长轮询；aclose 取消 SSE 任务无悬挂。
默认关闭路径的行为一致性由既有全套件保证（零新代码路径触发）。
"""

from __future__ import annotations

import asyncio
import json

import pytest

from hangma_bot.adapters.official import game as game_module
from hangma_bot.adapters.official.errors import AuthError, ForbiddenError, NotFoundError, RateLimitedError
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
from hangma_bot.adapters.official.scheduler import Priority, RequestScheduler


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


def _make_session(transport, clock, audit=None, *, snapshot_first=False):
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
        sse_snapshot_first=snapshot_first,
    )


def _instant_sleep(clock):
    async def _sleep(seconds):
        clock.advance(seconds)
    return _sleep


class TestSseFrameDriven:
    async def test_frame_reads_one_full_snapshot_and_delivers_draw_window(self, monkeypatch) -> None:
        """默认 SSE 路径从通知直接取完整观察，不再串联增量与补救快照。"""

        FakeSseClient.instances = []
        monkeypatch.setattr(game_module, "SSENotifyClient", FakeSseClient)
        waiting = load_fixture("state_response_snapshot_draw.json")
        waiting["snapshot"].update({"turn": 1, "drawn_tile": None})
        draw = load_fixture("state_response_snapshot_draw.json")
        draw["seq"] = waiting["seq"] + 1
        draw["snapshot"]["seq"] = draw["seq"]
        calls = []

        def handler(*, method, path, json_body=None, params=None, long_poll=False):
            calls.append((params["seq"], long_poll))
            return 200, json.dumps(waiting if len(calls) == 1 else draw)

        transport = FakeTransport()
        transport.handler = handler
        session = _make_session(transport, FakeClock(), snapshot_first=True)
        pending = asyncio.create_task(session.next_item())
        for _ in range(100):
            if calls and FakeSseClient.instances:
                break
            await asyncio.sleep(0)
        assert calls == [(0, False)]
        await FakeSseClient.instances[0].on_frame(_Frame(seq=draw["seq"]))

        window = await asyncio.wait_for(pending, timeout=2)
        assert isinstance(window, ObservedActionWindow)
        assert window.window_key.phase is WindowPhase.DRAW
        assert calls == [(0, False), (0, False)]
        await session.aclose("done")

    async def test_snapshot_first_marks_skipped_events_unobservable(self, monkeypatch) -> None:
        """跳帧后直接取快照时，未附事件明细不得误报为文法验证通过。"""

        FakeSseClient.instances = []
        monkeypatch.setattr(game_module, "SSENotifyClient", FakeSseClient)
        peng = load_fixture("state_response_snapshot_peng.json")
        peng["snapshot"].update({
            "turn": 3, "responding_seats": [0, 1],
            "last_discard": {"seat": 3, "tile": "9b", "seq": 120},
        })
        finished = load_fixture("state_response_finished.json")
        transport = FakeTransport()
        transport.handler = lambda **kw: (200, json.dumps(
            peng if len(transport.calls) == 1 else finished))
        audit = FakeAuditSink()
        session = _make_session(transport, FakeClock(), audit=audit, snapshot_first=True)
        consume = asyncio.create_task(session.next_item())
        for _ in range(100):
            if transport.calls and FakeSseClient.instances:
                break
            await asyncio.sleep(0)
        assert len(transport.calls) == 1
        await FakeSseClient.instances[0].on_frame(_Frame(seq=123))
        for _ in range(100):
            await asyncio.sleep(0)
        assert len(transport.calls) == 1, "已甄别的 +3 帧不应查询状态"
        await FakeSseClient.instances[0].on_frame(_Frame(seq=124))

        result = await asyncio.wait_for(consume, timeout=2)
        assert isinstance(result, GameFinished)
        assert [(call.params["seq"], call.long_poll) for call in transport.calls] == [
            (0, False), (0, False)]
        assert any(record.payload.get("sse_skip_verification") == "unobservable"
                   and record.payload.get("skip_kind") == "peng_timeout"
                   for record in audit.records)
        await session.aclose("done")

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

    @pytest.mark.parametrize("frame_seq", [121, 122, 123])
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
                   and record.payload["request_timing"]["scheduler_priority"] == "RECOVERY"
                   for record in audit.records)
        await session.aclose("done")
        await asyncio.wait_for(consume, timeout=2)

    async def test_confirmed_peng_timeouts_also_skip_opponent_chi_timeout_and_draw(self, monkeypatch) -> None:
        """已权威读过三条碰超时，后续 +2 他家摸牌仍无需再占一次状态额度。"""

        FakeSseClient.instances = []
        monkeypatch.setattr(game_module, "SSENotifyClient", FakeSseClient)
        peng = load_fixture("state_response_snapshot_peng.json")
        peng["snapshot"].update({
            "turn": 3, "responding_seats": [0, 1],
            "last_discard": {"seat": 3, "tile": "2w", "seq": 120},
        })
        triple = {"seq": 123, "gap": False, "events": [
            {"seq": seq, "type": "timeout", "seat": seat, "tile": "",
             "data": {"kind": "response", "window": "peng"}, "ts": 0}
            for seq, seat in ((121, 0), (122, 1), (123, 2))
        ]}
        chi = json.loads(json.dumps(peng))
        chi["seq"] = 123
        chi["snapshot"].update({"seq": 123, "phase": "response_chi", "responding_seats": [0]})
        after = {"seq": 126, "gap": False, "events": [
            {"seq": 124, "type": "timeout", "seat": 0, "tile": "",
             "data": {"kind": "response", "window": "chi"}, "ts": 0},
            {"seq": 125, "type": "tile_drawn", "seat": 0, "tile": "", "data": None, "ts": 0},
            {"seq": 126, "type": "tile_discarded", "seat": 0, "tile": "4w",
             "data": {"catch_play": False}, "ts": 0},
        ]}
        calls = []

        def handler(*, method, path, json_body=None, params=None, long_poll=False):
            seq = params["seq"]
            calls.append(seq)
            if seq == 0:
                return 200, json.dumps(peng if calls.count(0) == 1 else chi)
            return 200, json.dumps({120: triple, 123: after}[seq])

        transport = FakeTransport()
        transport.handler = handler
        audit = FakeAuditSink()
        session = _make_session(transport, FakeClock(), audit=audit)
        consume = asyncio.create_task(session.next_item())
        for _ in range(100):
            if calls and FakeSseClient.instances:
                break
            await asyncio.sleep(0)
        assert calls == [0]
        await FakeSseClient.instances[0].on_frame(_Frame(seq=123))
        for _ in range(100):
            if 120 in calls:
                break
            await asyncio.sleep(0)
        assert 120 in calls
        before = len(calls)
        await FakeSseClient.instances[0].on_frame(_Frame(seq=125))
        for _ in range(100):
            await asyncio.sleep(0)
        assert len(calls) == before
        await FakeSseClient.instances[0].on_frame(_Frame(seq=126))
        for _ in range(100):
            if 123 in calls:
                break
            await asyncio.sleep(0)
        assert 123 in calls
        assert any(record.payload.get("sse_skip_reason") == "chi_timeout_opponent_draw"
                   and record.payload.get("sse_skip_basis") == "authoritative_peng_timeouts"
                   for record in audit.records)
        assert any(record.payload.get("sse_skip_verification") == "verified"
                   and record.payload.get("skip_kind") == "chi_timeout_opponent_draw"
                   for record in audit.records)
        await session.aclose("done")
        await asyncio.wait_for(consume, timeout=2)

    async def test_incremental_discard_skips_atomic_peng_and_opponent_draw(self, monkeypatch) -> None:
        """快照仍在摸牌阶段时，也要凭已消费弃牌与相位跳过 +3、+2。"""

        FakeSseClient.instances = []
        monkeypatch.setattr(game_module, "SSENotifyClient", FakeSseClient)
        base = load_fixture("state_response_snapshot_draw.json")
        base["seq"] = 120
        base["snapshot"].update({"turn": 3, "drawn_tile": None, "hand_counts": [10, 10, 13, 11]})
        discard = {"seq": 121, "gap": False, "events": [
            {"seq": 121, "type": "tile_discarded", "seat": 3, "tile": "9b",
             "data": {"catch_play": False}, "ts": 0}]}
        through_next_discard = {"seq": 127, "gap": False, "events": [
            *({"seq": seq, "type": "timeout", "seat": seat, "tile": "",
               "data": {"kind": "response", "window": "peng"}, "ts": 0}
              for seq, seat in ((122, 0), (123, 1), (124, 2))),
            {"seq": 125, "type": "timeout", "seat": 0, "tile": "",
             "data": {"kind": "response", "window": "chi"}, "ts": 0},
            {"seq": 126, "type": "tile_drawn", "seat": 0, "tile": "", "data": None, "ts": 0},
            {"seq": 127, "type": "tile_discarded", "seat": 0, "tile": "8b",
             "data": {"catch_play": False}, "ts": 0},
        ]}
        calls = []

        def handler(*, method, path, json_body=None, params=None, long_poll=False):
            calls.append(params["seq"])
            return 200, json.dumps({0: base, 120: discard, 121: through_next_discard}[params["seq"]])

        transport = FakeTransport()
        transport.handler = handler
        audit = FakeAuditSink()
        session = _make_session(transport, FakeClock(), audit=audit)
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
        first_window = await asyncio.wait_for(consume, timeout=2)
        assert isinstance(first_window, ObservedActionWindow)
        consume = asyncio.create_task(session.next_item())
        await FakeSseClient.instances[0].on_frame(_Frame(seq=124))
        await FakeSseClient.instances[0].on_frame(_Frame(seq=126))
        for _ in range(100):
            await asyncio.sleep(0)
        assert calls == [0, 120]
        await FakeSseClient.instances[0].on_frame(_Frame(seq=127))
        for _ in range(100):
            if len(calls) >= 3:
                break
            await asyncio.sleep(0)
        assert calls[:3] == [0, 120, 121]
        assert {record.payload.get("skip_kind") for record in audit.records
                if record.payload.get("sse_skip_verification") == "verified"} >= {
                    "peng_timeout", "chi_timeout_opponent_draw"}
        await session.aclose("done")
        await asyncio.wait_for(consume, timeout=2)

    @pytest.mark.parametrize("catch_play_known", [True, False])
    async def test_peng_timeout_skip_uses_consumed_discard_when_snapshot_phase_is_stale(
        self, monkeypatch, catch_play_known,
    ) -> None:
        """旧快照阶段可用明确普通弃牌锚定；缺失抓打标记仍须权威查询。"""

        FakeSseClient.instances = []
        monkeypatch.setattr(game_module, "SSENotifyClient", FakeSseClient)
        base = load_fixture("state_response_snapshot_draw.json")
        base["seq"] = 120
        base["snapshot"].update({
            "phase": "response_chi", "turn": 2, "responding_seats": [3],
            "drawn_tile": None, "last_discard": {"seat": 2, "tile": "9t", "seq": 120},
            "hand_counts": [10, 10, 13, 11],
        })
        new_discard = {"seq": 123, "gap": False, "events": [
            {"seq": 121, "type": "timeout", "seat": 3, "tile": "",
             "data": {"kind": "response", "window": "chi"}, "ts": 0},
            {"seq": 122, "type": "tile_drawn", "seat": 3, "tile": "",
             "data": None, "ts": 0},
            {"seq": 123, "type": "tile_discarded", "seat": 3, "tile": "中",
             "data": {"catch_play": False} if catch_play_known else {}, "ts": 0},
        ]}
        after_timeout = {"seq": 127, "gap": False, "events": [
            *({"seq": seq, "type": "timeout", "seat": seat, "tile": "",
               "data": {"kind": "response", "window": "peng"}, "ts": 0}
              for seq, seat in ((124, 0), (125, 1), (126, 2))),
            {"seq": 127, "type": "pass", "seat": 0, "tile": "", "data": None, "ts": 0},
        ]}
        calls = []

        def handler(*, method, path, json_body=None, params=None, long_poll=False):
            calls.append(params["seq"])
            return 200, json.dumps({0: base, 120: new_discard, 123: after_timeout}[params["seq"]])

        transport = FakeTransport()
        transport.handler = handler
        audit = FakeAuditSink()
        session = _make_session(transport, FakeClock(), audit=audit)
        consume = asyncio.create_task(session.next_item())
        for _ in range(100):
            if calls and FakeSseClient.instances:
                break
            await asyncio.sleep(0)
        assert calls == [0]
        await FakeSseClient.instances[0].on_frame(_Frame(seq=123))
        for _ in range(100):
            if len(calls) >= 2:
                break
            await asyncio.sleep(0)
        assert calls == [0, 120]
        await FakeSseClient.instances[0].on_frame(_Frame(seq=126))
        for _ in range(100):
            if not catch_play_known and len(calls) >= 3:
                break
            await asyncio.sleep(0)
        if not catch_play_known:
            assert calls[:3] == [0, 120, 123]
            assert not any(record.payload.get("sse_skip_reason") == "plain_peng_timeout_group"
                           for record in audit.records)
            await session.aclose("done")
            await asyncio.wait_for(consume, timeout=2)
            return
        assert calls == [0, 120], "已知无鸣牌兴趣的 +3 不应因旧快照阶段再查一次"
        await FakeSseClient.instances[0].on_frame(_Frame(seq=127))
        for _ in range(100):
            if len(calls) >= 3:
                break
            await asyncio.sleep(0)
        assert calls[:3] == [0, 120, 123]
        assert any(record.payload.get("sse_skip_verification") == "verified"
                   and record.payload.get("skip_kind") == "peng_timeout"
                   for record in audit.records)
        await session.aclose("done")
        await asyncio.wait_for(consume, timeout=2)

    async def test_unanchored_plus_three_still_reads_authoritative_state(self, monkeypatch) -> None:
        """新连接首帧 +3 可能合并抢占动作；无前置弃牌证据时必须查询。"""

        FakeSseClient.instances = []
        monkeypatch.setattr(game_module, "SSENotifyClient", FakeSseClient)
        base = load_fixture("state_response_snapshot_draw.json")
        base["seq"] = 120
        base["snapshot"].update({"turn": 3, "drawn_tile": None})
        finished = load_fixture("state_response_finished.json")
        calls = []

        def handler(*, method, path, json_body=None, params=None, long_poll=False):
            calls.append(params["seq"])
            return 200, json.dumps(base if len(calls) == 1 else finished)

        transport = FakeTransport()
        transport.handler = handler
        session = _make_session(transport, FakeClock())
        consume = asyncio.create_task(session.next_item())
        for _ in range(100):
            if calls and FakeSseClient.instances:
                break
            await asyncio.sleep(0)
        await FakeSseClient.instances[0].on_frame(_Frame(seq=123))
        result = await asyncio.wait_for(consume, timeout=2)
        assert isinstance(result, GameFinished)
        assert calls == [0, 120]
        await session.aclose("done")

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

    async def test_settled_idle_probe_uses_low_priority(self, monkeypatch) -> None:
        """局间固定停顿独立计时，普通探针不抢真实帧的发送优先级。"""

        FakeSseClient.instances = []
        monkeypatch.setattr(game_module, "SSENotifyClient", FakeSseClient)
        monkeypatch.setattr(game_module, "_SSE_SETTLED_IDLE_POLL_SEC", 0.01)
        settled = load_fixture("state_response_snapshot_draw.json")
        settled["snapshot"].update({"phase": "settled", "turn": 1, "responding_seats": [],
                                     "drawn_tile": None})
        finished = load_fixture("state_response_finished.json")
        calls = []

        def handler(*, method, path, json_body=None, params=None, long_poll=False):
            calls.append((params["seq"], long_poll))
            return 200, json.dumps(settled if len(calls) == 1 else finished)

        transport = FakeTransport()
        transport.handler = handler
        audit = FakeAuditSink()
        session = _make_session(transport, FakeClock(), audit=audit)
        result = await asyncio.wait_for(session.next_item(), timeout=2)
        assert isinstance(result, GameFinished)
        assert calls == [(0, False), (0, False)]
        idle = [record for record in audit.records
                if record.payload.get("request_timing", {}).get("query_purpose") == "sse_settled_probe"]
        assert idle and idle[0].payload["request_timing"]["scheduler_priority"] == "POLL"
        await session.aclose("done")

    async def test_sse_silence_uses_low_priority_snapshot(self, monkeypatch) -> None:
        """活跃阶段两秒无新通知才查一次当前快照，且不挂长轮询。"""

        FakeSseClient.instances = []
        monkeypatch.setattr(game_module, "SSENotifyClient", FakeSseClient)
        monkeypatch.setattr(game_module, "_SSE_SILENCE_POLL_SEC", 0.01)
        monkeypatch.setattr(game_module, "_SSE_STATE_AGE_POLL_SEC", 0.1)
        neutral = load_fixture("state_response_snapshot_draw.json")
        neutral["snapshot"].update({"turn": 1, "drawn_tile": None})
        finished = load_fixture("state_response_finished.json")
        transport = FakeTransport()
        transport.handler = lambda **kw: (200, json.dumps(
            neutral if len(transport.calls) == 1 else finished))
        audit = FakeAuditSink()
        session = _make_session(transport, FakeClock(), audit=audit)

        result = await asyncio.wait_for(session.next_item(), timeout=2)
        assert isinstance(result, GameFinished)
        assert [(call.params["seq"], call.long_poll) for call in transport.calls] == [
            (0, False), (0, False)]
        probe = [record for record in audit.records
                 if record.payload.get("request_timing", {}).get("query_purpose") == "sse_silence_probe"]
        assert probe and probe[0].payload["request_timing"]["scheduler_priority"] == "POLL"
        await session.aclose("done")

    async def test_nearby_own_discard_probe_coalesces_silence_snapshot(self, monkeypatch) -> None:
        """已接受弃牌的短探针将到时，仅发这一笔，避免普通保底紧邻重复。"""

        FakeSseClient.instances = []
        monkeypatch.setattr(game_module, "SSENotifyClient", FakeSseClient)
        monkeypatch.setattr(game_module, "_SSE_SILENCE_POLL_SEC", 0.02)
        monkeypatch.setattr(game_module, "_SSE_STATE_AGE_POLL_SEC", 0.1)
        monkeypatch.setattr(game_module, "_SSE_OWN_DISCARD_PROBE_SEC", 0.025)
        draw = load_fixture("state_response_snapshot_draw.json")
        finished = load_fixture("state_response_finished.json")
        transport = FakeTransport()

        def handler(*, method, **kw):
            if method == "POST":
                return 200, "{}"
            gets = sum(call.method == "GET" for call in transport.calls)
            return 200, json.dumps(draw if gets == 1 else finished)

        transport.handler = handler
        audit = FakeAuditSink()
        session = _make_session(transport, FakeClock(), audit=audit)
        window = await asyncio.wait_for(session.next_item(), timeout=2)
        assert isinstance(window, ObservedActionWindow)
        attempt = ActionAttempt(
            decision_id="d-sse-coalesce", attempt_no=1, plan_revision=1,
            window_key=window.window_key, based_on_authoritative_seq=window.window_key.trigger_seq,
            action=Discard(Tile("5w")), action_key="discard:5w", latest_send_at_monotonic=1005.0,
        )
        assert isinstance(await session.submit(attempt), SubmitAccepted)

        result = await asyncio.wait_for(session.next_item(), timeout=2)
        assert isinstance(result, GameFinished)
        assert sum(call.method == "GET" for call in transport.calls) == 2
        assert any(record.payload.get("request_timing", {}).get("query_purpose")
                   == "sse_own_discard_probe" for record in audit.records)
        assert not any(record.payload.get("request_timing", {}).get("query_purpose")
                       == "sse_silence_probe" for record in audit.records)
        await session.aclose("done")

    async def test_advancing_skipped_frame_preserves_five_second_alignment(self, monkeypatch) -> None:
        """可跳过的新水位重置静默钟，但不能延后权威状态最大陈旧时间。"""

        FakeSseClient.instances = []
        monkeypatch.setattr(game_module, "SSENotifyClient", FakeSseClient)
        monkeypatch.setattr(game_module, "_SSE_SILENCE_POLL_SEC", 0.035)
        monkeypatch.setattr(game_module, "_SSE_STATE_AGE_POLL_SEC", 0.04)
        peng = load_fixture("state_response_snapshot_peng.json")
        peng["snapshot"].update({
            "turn": 3, "responding_seats": [0, 1],
            "last_discard": {"seat": 3, "tile": "9b", "seq": 120},
        })
        finished = load_fixture("state_response_finished.json")
        transport = FakeTransport()
        transport.handler = lambda **kw: (200, json.dumps(
            peng if len(transport.calls) == 1 else finished))
        audit = FakeAuditSink()
        session = _make_session(transport, FakeClock(), audit=audit)
        consume = asyncio.create_task(session.next_item())
        await asyncio.sleep(0.025)
        await FakeSseClient.instances[0].on_frame(_Frame(seq=123))

        result = await asyncio.wait_for(consume, timeout=2)
        assert isinstance(result, GameFinished)
        assert any(record.payload.get("sse_skip_reason") == "plain_peng_timeout_group"
                   for record in audit.records)
        assert any(record.payload.get("request_timing", {}).get("query_purpose")
                   == "sse_state_age_probe" for record in audit.records)
        assert [(call.params["seq"], call.long_poll) for call in transport.calls] == [
            (0, False), (0, False)]
        await session.aclose("done")

    async def test_queued_watchdog_yields_to_new_frame(self, monkeypatch) -> None:
        """普通保底尚未获许可时撤销，帧查询立即按恢复优先级进入同场槽。"""

        FakeSseClient.instances = []
        monkeypatch.setattr(game_module, "SSENotifyClient", FakeSseClient)
        monkeypatch.setattr(game_module, "_SSE_SILENCE_POLL_SEC", 0.01)
        monkeypatch.setattr(game_module, "_SSE_STATE_AGE_POLL_SEC", 0.1)
        neutral = load_fixture("state_response_snapshot_draw.json")
        neutral["snapshot"].update({"turn": 1, "drawn_tile": None})
        finished = load_fixture("state_response_finished.json")
        clock = FakeClock()
        queued = asyncio.Event()
        cancelled = asyncio.Event()

        class BlockingScheduler(RequestScheduler):
            async def acquire(self, priority, *args, **kwargs):
                if priority is Priority.POLL:
                    queued.set()
                    try:
                        await asyncio.Event().wait()
                    except asyncio.CancelledError:
                        cancelled.set()
                        raise
                return await super().acquire(priority, *args, **kwargs)

        transport = FakeTransport()
        transport.handler = lambda **kw: (200, json.dumps(
            neutral if len(transport.calls) == 1 else finished))
        audit = FakeAuditSink()
        session = OfficialGameSession(
            game_id="g_room1_batch1", transport=transport,
            scheduler=BlockingScheduler(clock=clock.monotonic, sleep=_instant_sleep(clock)),
            timing=TIMING, monotonic_clock=clock.monotonic, wall_clock_unix_ms=clock.wall_ms,
            audit=audit, audit_context=make_audit_context,
            retry_sleep=_instant_sleep(clock), sse_enabled=True,
        )
        consume = asyncio.create_task(session.next_item())
        await asyncio.wait_for(queued.wait(), timeout=2)
        await FakeSseClient.instances[0].on_frame(_Frame(seq=101))
        await asyncio.sleep(0)
        assert not cancelled.is_set(), "重复水位不能撤销仍需执行的静默保底"
        await FakeSseClient.instances[0].on_frame(_Frame(seq=102))

        result = await asyncio.wait_for(consume, timeout=2)
        assert isinstance(result, GameFinished)
        assert cancelled.is_set()
        assert [(call.params["seq"], call.long_poll) for call in transport.calls] == [
            (0, False), (0, False)]
        assert any(record.payload.get("request_timing", {}).get("query_purpose") == "sse_frame"
                   for record in audit.records)
        await session.aclose("done")

    async def test_watchdog_429_retry_yields_to_new_frame(self, monkeypatch) -> None:
        """低优先级快照已获 429 且等待重排时，新帧撤销其重试。"""

        FakeSseClient.instances = []
        monkeypatch.setattr(game_module, "SSENotifyClient", FakeSseClient)
        monkeypatch.setattr(game_module, "_SSE_SILENCE_POLL_SEC", 0.01)
        monkeypatch.setattr(game_module, "_SSE_STATE_AGE_POLL_SEC", 0.1)
        neutral = load_fixture("state_response_snapshot_draw.json")
        neutral["snapshot"].update({"turn": 1, "drawn_tile": None})
        finished = load_fixture("state_response_finished.json")
        retry_waiting = asyncio.Event()
        retry_cancelled = asyncio.Event()

        async def blocked_retry(seconds):
            retry_waiting.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                retry_cancelled.set()
                raise

        transport = FakeTransport()

        def handler(**kw):
            if len(transport.calls) == 1:
                return 200, json.dumps(neutral)
            if len(transport.calls) == 2:
                return RateLimitedError(429, "RATE_LIMITED", "retry", 0.2)
            return 200, json.dumps(finished)

        transport.handler = handler
        clock = FakeClock()
        session = OfficialGameSession(
            game_id="g_room1_batch1", transport=transport,
            scheduler=RequestScheduler(clock=clock.monotonic, sleep=_instant_sleep(clock)),
            timing=TIMING, monotonic_clock=clock.monotonic, wall_clock_unix_ms=clock.wall_ms,
            retry_sleep=blocked_retry, sse_enabled=True,
        )
        consume = asyncio.create_task(session.next_item())
        await asyncio.wait_for(retry_waiting.wait(), timeout=2)
        await FakeSseClient.instances[0].on_frame(_Frame(seq=102))

        result = await asyncio.wait_for(consume, timeout=2)
        assert isinstance(result, GameFinished)
        assert retry_cancelled.is_set()
        assert [(call.params["seq"], call.long_poll) for call in transport.calls] == [
            (0, False), (0, False), (0, False)]
        await session.aclose("done")

    @pytest.mark.parametrize("covers_frame", [True, False])
    async def test_sent_watchdog_reuses_result_after_frame(self, monkeypatch, covers_frame) -> None:
        """快照已发则先用其结果；水位落后新帧时才补一次紧急增量。"""

        FakeSseClient.instances = []
        monkeypatch.setattr(game_module, "SSENotifyClient", FakeSseClient)
        monkeypatch.setattr(game_module, "_SSE_SILENCE_POLL_SEC", 0.01)
        monkeypatch.setattr(game_module, "_SSE_STATE_AGE_POLL_SEC", 0.1)
        neutral = load_fixture("state_response_snapshot_draw.json")
        neutral["snapshot"].update({"turn": 1, "drawn_tile": None})
        finished = load_fixture("state_response_finished.json")
        started = asyncio.Event()
        release = asyncio.Event()
        transport = FakeTransport()

        async def handler(**kw):
            if len(transport.calls) == 1:
                return 200, json.dumps(neutral)
            if len(transport.calls) == 2:
                started.set()
                await release.wait()
                if not covers_frame:
                    return 200, json.dumps(neutral)
            return 200, json.dumps(finished)

        transport.handler = handler
        session = _make_session(transport, FakeClock())
        consume = asyncio.create_task(session.next_item())
        await asyncio.wait_for(started.wait(), timeout=2)
        await FakeSseClient.instances[0].on_frame(_Frame(seq=102))
        release.set()

        result = await asyncio.wait_for(consume, timeout=2)
        assert isinstance(result, GameFinished)
        assert [(call.params["seq"], call.long_poll) for call in transport.calls] == (
            [(0, False), (0, False)] if covers_frame else
            [(0, False), (0, False), (101, False)])
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

    async def test_special_action_self_wake_uses_recovery_priority(self, monkeypatch) -> None:
        """本人特殊动作无 SSE 回显时，自唤醒必须及时取得后续权威状态。"""

        FakeSseClient.instances = []
        monkeypatch.setattr(game_module, "SSENotifyClient", FakeSseClient)
        draw = load_fixture("state_response_snapshot_draw.json")
        finished = load_fixture("state_response_finished.json")
        calls = []

        def handler(*, method, path, json_body=None, params=None, long_poll=False):
            calls.append(method)
            if method == "POST":
                return 200, "{}"
            return 200, json.dumps(draw if calls.count("GET") == 1 else finished)

        transport = FakeTransport()
        transport.handler = handler
        audit = FakeAuditSink()
        session = _make_session(transport, FakeClock(), audit=audit)
        window = await asyncio.wait_for(session.next_item(), timeout=2)
        assert isinstance(window, ObservedActionWindow)
        attempt = ActionAttempt(
            decision_id="d-sse-special", attempt_no=1, plan_revision=1,
            window_key=window.window_key, based_on_authoritative_seq=window.window_key.trigger_seq,
            action=Discard(Tile("白")), action_key="discard:白", latest_send_at_monotonic=1005.0,
        )
        assert isinstance(await session.submit(attempt), SubmitAccepted)
        assert isinstance(await asyncio.wait_for(session.next_item(), timeout=2), GameFinished)
        wake = [record.payload["request_timing"] for record in audit.records
                if record.payload.get("request_timing", {}).get("query_purpose") == "sse_self_wake"]
        assert wake and wake[0]["scheduler_priority"] == "RECOVERY"
        assert calls == ["GET", "POST", "GET"]
        await session.aclose("done")

    async def test_incremental_draw_discard_uses_observation_not_stale_snapshot(self, monkeypatch) -> None:
        """本人增量摸牌后旧快照仍是吃窗，普通弃牌无需自唤醒 GET。"""

        FakeSseClient.instances = []
        monkeypatch.setattr(game_module, "SSENotifyClient", FakeSseClient)
        base = load_fixture("state_response_snapshot_draw.json")
        base["snapshot"].update({
            "phase": "response_chi", "turn": 1, "responding_seats": [], "drawn_tile": None,
        })
        draw = {"seq": 102, "gap": False, "events": [
            {"seq": 102, "type": "tile_drawn", "seat": 2, "tile": "1w",
             "data": None, "ts": 0}]}
        calls = []

        def handler(*, method, path, json_body=None, params=None, long_poll=False):
            calls.append((method, params["seq"] if params else None))
            return (200, "{}") if method == "POST" else (200, json.dumps(base if params["seq"] == 0 else draw))

        transport = FakeTransport()
        transport.handler = handler
        session = _make_session(transport, FakeClock())
        consume = asyncio.create_task(session.next_item())
        for _ in range(100):
            if calls and FakeSseClient.instances:
                break
            await asyncio.sleep(0)
        await FakeSseClient.instances[0].on_frame(_Frame(seq=102))
        window = await asyncio.wait_for(consume, timeout=2)
        assert isinstance(window, ObservedActionWindow)
        assert window.observation.phase == "draw"
        attempt = ActionAttempt(
            decision_id="d-stale-snapshot", attempt_no=1, plan_revision=1,
            window_key=window.window_key, based_on_authoritative_seq=window.window_key.trigger_seq,
            action=Discard(Tile("1w")), action_key="discard:1w", latest_send_at_monotonic=1005.0,
        )
        assert isinstance(await session.submit(attempt), SubmitAccepted)
        consume = asyncio.create_task(session.next_item())
        await FakeSseClient.instances[0].on_frame(_Frame(seq=103))
        for _ in range(100):
            await asyncio.sleep(0)
        assert [call for call in calls if call[0] == "GET"] == [("GET", 0), ("GET", 101)]
        await session.aclose("done")
        await asyncio.wait_for(consume, timeout=2)

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
