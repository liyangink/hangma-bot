"""SSE 长时间无帧时，恢复后的状态探针仍需发现一秒非 pass 响应窗。"""

from __future__ import annotations

import asyncio
from collections import Counter
import json

import pytest

from _concurrent_adapter_harness import ConcurrentClock
from _official_testkit import FakeAuditSink, FakeTransport, TIMING, load_fixture, make_audit_context
from _official_testkit import make_game_session
from test_sync_repair_regressions import event, snapshot
from hangma_bot.adapters.official import game as game_module
from hangma_bot.adapters.official.errors import UncertainTransportError
from hangma_bot.adapters.official.game import OfficialGameSession
from hangma_bot.adapters.official.notify import NotifyFrame
from hangma_bot.adapters.official.scheduler import (
    DEFAULT_PRODUCTION_STATE_BURST,
    DEFAULT_PRODUCTION_STATE_MIN_SPACING_SEC,
    DEFAULT_STATE_ARRIVAL_GUARD_SEC,
    RequestScheduler,
)
from hangma_bot.application.contracts import GameFailed, GameFinished, ObservedActionWindow
from hangma_bot.hangma import HangmaRules
from hangma_bot.kernel.actions import WindowPhase
from hangma_bot.kernel.config import RuleConfig


class _SilentNotify:
    """模拟已建立但三十秒不再收到数据帧的 SSE 流。"""

    def __init__(self, game_id, transport, **kwargs):
        self.game_id = game_id

    async def run(self):
        await asyncio.Event().wait()

    async def aclose(self):
        pass


async def test_silent_sse_and_transient_get_error_must_not_lose_peng(monkeypatch):
    """十桌共用 state 额度；GET 恢复后仍应看见真实的一秒碰窗。"""

    clock = ConcurrentClock()
    # asyncio.wait_for 也使用同一假单调钟，不花真实三十秒等待。
    monkeypatch.setattr(asyncio.get_running_loop(), "time", clock.monotonic)
    monkeypatch.setattr(game_module, "SSENotifyClient", _SilentNotify)
    root = RequestScheduler(
        rate_per_second=16, burst=DEFAULT_PRODUCTION_STATE_BURST,
        state_arrival_guard_sec=DEFAULT_STATE_ARRIVAL_GUARD_SEC,
        state_min_spacing_sec=DEFAULT_PRODUCTION_STATE_MIN_SPACING_SEC,
        clock=clock.monotonic, sleep=clock.sleep, poll_interval=0,
    )
    transport = FakeTransport()
    target = "silent_game_0"
    calls = Counter()
    get_times = []
    baseline = snapshot(100, turn=1, phase="draw", drawn="")
    live_peng = load_fixture("state_response_snapshot_peng.json")
    live_peng["seq"] = 101
    live_peng["snapshot"].update(
        seq=101, turn=1, phase="response_peng", responding_seats=[2],
        last_discard={"seat": 1, "tile": "2w", "seq": 101},
        window_deadline_ms=clock.wall_ms() + 3800,
    )
    after_peng = snapshot(102, turn=1, phase="draw", drawn="")
    finished = load_fixture("state_response_finished.json")
    # 单独用正式规则与会话入口证明脚本中的碰窗确有合法非 pass 候选。
    control_clock = ConcurrentClock()
    control_clock.advance(2.8)
    control_transport = FakeTransport()
    control_transport.handler = lambda **kwargs: (200, json.dumps(live_peng))
    control = make_game_session(transport=control_transport, clock=control_clock)
    try:
        legal_window = await control.next_item()
        assert isinstance(legal_window, ObservedActionWindow)
        assert legal_window.window_key.phase is WindowPhase.RESPONSE_PENG
        legal_keys = {item.action_key for item in HangmaRules(
            RuleConfig("sse-gap-regression", 1, False)).analyze(
                legal_window.observation).legal_candidates}
        assert "peng:2w" in legal_keys
    finally:
        await control.aclose("test_complete")

    def handler(*, method, path, **kwargs):
        assert method == "GET"
        game = path.split("/")[3]
        calls[game] += 1
        now = clock.monotonic()
        if game == target:
            get_times.append(round(now, 3))
        if game == target and calls[game] == 2:
            raise UncertainTransportError("injected_transient_get_failure")
        if now >= 30:
            return 200, json.dumps(finished)
        if game == target and 2.8 <= now < 3.8:
            return 200, json.dumps(live_peng)
        if game == target and now >= 3.8:
            return 200, json.dumps(after_peng)
        return 200, json.dumps(baseline)

    transport.handler = handler
    audit = FakeAuditSink()
    sessions = [
        OfficialGameSession(
            game_id=f"silent_game_{i}", transport=transport,
            scheduler=root.for_game(f"silent_game_{i}", max_games=10),
            timing=TIMING, monotonic_clock=clock.monotonic,
            wall_clock_unix_ms=clock.wall_ms, audit=audit,
            audit_context=make_audit_context, retry_sleep=clock.sleep,
            sse_enabled=True, sse_snapshot_first=True,
        )
        for i in range(10)
    ]

    async def ticker():
        while clock.monotonic() < 40:
            await clock.sleep(.1)

    async def collect():
        tasks = [asyncio.create_task(session.next_item()) for session in sessions]
        timer = asyncio.create_task(ticker())
        try:
            return await asyncio.gather(*tasks)
        finally:
            timer.cancel()
            await asyncio.gather(timer, return_exceptions=True)

    try:
        result = await clock.run(collect())
        assert all(isinstance(item, GameFinished) for item in result[1:])
        assert calls[target] >= 3
        assert any(
            record.payload.get("error_type") == "UncertainTransportError"
            for record in audit.records
            if record.kind.value == "http_request"
        )
        assert isinstance(result[0], ObservedActionWindow), (
            f"合法 peng:2w 响应窗 2.8–3.8 秒未交付；目标桌 GET 发起时刻 {get_times}"
        )
        assert result[0].window_key.phase is WindowPhase.RESPONSE_PENG
        assert result[0].received_at_monotonic < 3.8
    finally:
        for session in sessions:
            await session.aclose("test_complete")


async def test_authoritative_watermark_ahead_of_silent_sse_reconnects(monkeypatch):
    """旧流静默而 /state 已前进时，新流的后续帧应及时唤醒真实碰窗。"""

    clock = ConcurrentClock()
    monkeypatch.setattr(asyncio.get_running_loop(), "time", clock.monotonic)

    class _ReconnectingNotify:
        opens = 0

        def __init__(self, game_id, transport, *, on_frame, **kwargs):
            self.on_frame = on_frame

        async def run(self):
            _ReconnectingNotify.opens += 1
            if _ReconnectingNotify.opens == 1:
                await self.on_frame(NotifyFrame(seq=100))
                await asyncio.Event().wait()
            else:
                await self.on_frame(NotifyFrame(seq=101))
                await clock.sleep(max(0, 2.9 - clock.monotonic()))
                await self.on_frame(NotifyFrame(seq=102))
                await asyncio.Event().wait()

        async def aclose(self):
            pass

    monkeypatch.setattr(game_module, "SSENotifyClient", _ReconnectingNotify)
    transport = FakeTransport()
    baseline = snapshot(100, turn=1, phase="draw", drawn="")
    advanced = snapshot(101, turn=1, phase="draw", drawn="")
    live_peng = load_fixture("state_response_snapshot_peng.json")
    live_peng["seq"] = 102
    live_peng["snapshot"].update(
        seq=102, turn=1, phase="response_peng", responding_seats=[2],
        last_discard={"seat": 1, "tile": "2w", "seq": 102},
        window_deadline_ms=clock.wall_ms() + 3900,
    )
    after_peng = snapshot(103, turn=1, phase="draw", drawn="")
    finished = load_fixture("state_response_finished.json")
    get_times = []

    def handler(*, method, **kwargs):
        assert method == "GET"
        now = clock.monotonic()
        get_times.append(round(now, 3))
        if now >= 6:
            return 200, json.dumps(finished)
        if 2.9 <= now < 3.9:
            return 200, json.dumps(live_peng)
        if now >= 3.9:
            return 200, json.dumps(after_peng)
        if now >= 2:
            return 200, json.dumps(advanced)
        return 200, json.dumps(baseline)

    transport.handler = handler
    session = OfficialGameSession(
        game_id="stale_stream_game", transport=transport,
        scheduler=RequestScheduler(clock=clock.monotonic, sleep=clock.sleep).for_game(
            "stale_stream_game", max_games=10),
        timing=TIMING, monotonic_clock=clock.monotonic,
        wall_clock_unix_ms=clock.wall_ms, retry_sleep=clock.sleep,
        sse_enabled=True, sse_snapshot_first=True,
    )

    async def ticker():
        while clock.monotonic() < 7:
            await clock.sleep(.1)

    async def scenario():
        timer = asyncio.create_task(ticker())
        try:
            return await session.next_item()
        finally:
            timer.cancel()
            await asyncio.gather(timer, return_exceptions=True)

    try:
        result = await clock.run(scenario())
        assert _ReconnectingNotify.opens >= 2, (
            f"/state 已见 seq=101 而旧 SSE 停在 seq=100；GET 发起时刻 {get_times}"
        )
        assert isinstance(result, ObservedActionWindow)
        assert result.window_key.phase is WindowPhase.RESPONSE_PENG
        assert result.received_at_monotonic < 3.9
    finally:
        await session.aclose("test_complete")


async def test_active_silent_sse_reconnects_even_before_state_watermark_advances(monkeypatch):
    """活动桌水位暂相等时，旧流半开也不能永久等待首个漏送事件。"""

    clock = ConcurrentClock()
    monkeypatch.setattr(asyncio.get_running_loop(), "time", clock.monotonic)

    class _HalfOpenNotify:
        opens = 0

        def __init__(self, game_id, transport, *, on_frame, **kwargs):
            self.on_frame = on_frame

        async def run(self):
            _HalfOpenNotify.opens += 1
            await self.on_frame(NotifyFrame(seq=100))
            if _HalfOpenNotify.opens >= 2:
                await clock.sleep(max(0, 8.7 - clock.monotonic()))
                await self.on_frame(NotifyFrame(seq=102))
            await asyncio.Event().wait()

    monkeypatch.setattr(game_module, "SSENotifyClient", _HalfOpenNotify)
    transport = FakeTransport()
    baseline = snapshot(100, turn=1, phase="draw", drawn="")
    live = load_fixture("state_response_snapshot_peng.json")
    live["seq"] = 102
    live["snapshot"].update(
        seq=102, turn=1, phase="response_peng", responding_seats=[2],
        last_discard={"seat": 1, "tile": "2w", "seq": 102},
        window_deadline_ms=clock.wall_ms() + 9600,
    )
    after = snapshot(102, turn=1, phase="draw", drawn="")
    finished = load_fixture("state_response_finished.json")
    get_times = []
    audit = FakeAuditSink()

    def handler(*, method, **kwargs):
        assert method == "GET"
        now = clock.monotonic()
        get_times.append(round(now, 3))
        doc = (finished if now >= 12 else after if now >= 9.6
               else live if now >= 8.4 else baseline)
        return 200, json.dumps(doc)

    transport.handler = handler
    session = OfficialGameSession(
        game_id="equal_watermark_game", transport=transport,
        scheduler=RequestScheduler(clock=clock.monotonic, sleep=clock.sleep).for_game(
            "equal_watermark_game", max_games=10),
        timing=TIMING, monotonic_clock=clock.monotonic,
        wall_clock_unix_ms=clock.wall_ms, retry_sleep=clock.sleep,
        audit=audit, audit_context=make_audit_context,
        sse_enabled=True, sse_snapshot_first=True,
    )

    async def ticker():
        while clock.monotonic() < 13:
            await clock.sleep(.1)

    async def scenario():
        timer = asyncio.create_task(ticker())
        try:
            return await session.next_item()
        finally:
            timer.cancel()
            await asyncio.gather(timer, return_exceptions=True)

    try:
        result = await clock.run(scenario())
        assert _HalfOpenNotify.opens >= 2
        assert isinstance(result, ObservedActionWindow), (
            f"GET={get_times}; 帧={[(r.payload.get('seq'), r.payload.get('source')) for r in audit.records if r.payload.get('source') == 'sse_frame']}"
        )
        assert result.window_key.phase is WindowPhase.RESPONSE_PENG
        assert result.received_at_monotonic < 9.6
    finally:
        await session.aclose("test_complete")


async def test_equal_watermark_healthy_pause_over_30s_never_degrades(monkeypatch):
    """权威与通知水位都不前进的长暂停至多探测一次，不能耗尽故障额度。"""

    clock = ConcurrentClock()
    monkeypatch.setattr(asyncio.get_running_loop(), "time", clock.monotonic)

    class _PausedNotify:
        opens = 0

        def __init__(self, game_id, transport, *, on_frame, **kwargs):
            self.on_frame = on_frame

        async def run(self):
            _PausedNotify.opens += 1
            await self.on_frame(NotifyFrame(seq=100))
            await asyncio.Event().wait()

    monkeypatch.setattr(game_module, "SSENotifyClient", _PausedNotify)
    transport, audit = FakeTransport(), FakeAuditSink()
    baseline = snapshot(100, turn=1, phase="draw", drawn="")
    finished = load_fixture("state_response_finished.json")
    transport.handler = lambda **kwargs: (200, json.dumps(
        finished if clock.monotonic() >= 35 else baseline))
    session = OfficialGameSession(
        game_id="healthy_pause_game", transport=transport,
        scheduler=RequestScheduler(clock=clock.monotonic, sleep=clock.sleep).for_game(
            "healthy_pause_game", max_games=10),
        timing=TIMING, monotonic_clock=clock.monotonic,
        wall_clock_unix_ms=clock.wall_ms, retry_sleep=clock.sleep,
        audit=audit, audit_context=make_audit_context,
        sse_enabled=True, sse_snapshot_first=True,
    )

    async def scenario():
        async def ticker():
            while clock.monotonic() < 38:
                await clock.sleep(.1)

        timer = asyncio.create_task(ticker())
        try:
            return await session.next_item()
        finally:
            timer.cancel()
            await asyncio.gather(timer, return_exceptions=True)

    try:
        result = await clock.run(scenario())
        reconnects = [r for r in audit.records
                      if r.payload.get("trigger") == "sse_stale_reconnect"]
        assert isinstance(result, GameFinished)
        assert _PausedNotify.opens == 2  # 同水位 8 秒静默仅作一次预防性换流
        assert len(reconnects) == 1
        assert reconnects[0].payload["reason"] == "active_frame_silence"
        assert not any(r.payload.get("reason") == "stale_reconnects_exhausted"
                       for r in audit.records)
    finally:
        await session.aclose("test_complete")


async def test_repeated_old_frames_cannot_hide_confirmed_watermark_lag(monkeypatch):
    """旧 seq 重复帧虽是新字节，却不能把权威领先的时钟一直归零。"""

    clock = ConcurrentClock()
    monkeypatch.setattr(asyncio.get_running_loop(), "time", clock.monotonic)

    class _RepeatedOldNotify:
        opens = 0

        def __init__(self, game_id, transport, *, on_frame, **kwargs):
            self.on_frame = on_frame

        async def run(self):
            _RepeatedOldNotify.opens += 1
            if _RepeatedOldNotify.opens == 1:
                await self.on_frame(NotifyFrame(seq=0))
                while True:
                    await clock.sleep(.4)
                    await self.on_frame(NotifyFrame(seq=0))
            await self.on_frame(NotifyFrame(seq=1))
            await asyncio.Event().wait()

    monkeypatch.setattr(game_module, "SSENotifyClient", _RepeatedOldNotify)
    transport, audit = FakeTransport(), FakeAuditSink()
    baseline = snapshot(0, turn=1, phase="draw", drawn="")
    advanced = snapshot(1, turn=1, phase="draw", drawn="")
    finished = load_fixture("state_response_finished.json")

    def handler(**kwargs):
        now = clock.monotonic()
        return 200, json.dumps(finished if now >= 8 else advanced if now >= 2 else baseline)

    transport.handler = handler
    session = OfficialGameSession(
        game_id="repeated_old_frame_game", transport=transport,
        scheduler=RequestScheduler(clock=clock.monotonic, sleep=clock.sleep).for_game(
            "repeated_old_frame_game", max_games=10),
        timing=TIMING, monotonic_clock=clock.monotonic,
        wall_clock_unix_ms=clock.wall_ms, retry_sleep=clock.sleep,
        audit=audit, audit_context=make_audit_context,
        sse_enabled=True, sse_snapshot_first=True,
    )

    async def scenario():
        async def ticker():
            while clock.monotonic() < 10:
                await clock.sleep(.1)

        timer = asyncio.create_task(ticker())
        try:
            return await session.next_item()
        finally:
            timer.cancel()
            await asyncio.gather(timer, return_exceptions=True)

    try:
        result = await clock.run(scenario())
        assert isinstance(result, GameFinished)
        assert _RepeatedOldNotify.opens >= 2
        assert any(r.payload.get("reason") == "watermark_lag"
                   for r in audit.records
                   if r.payload.get("trigger") == "sse_stale_reconnect")
    finally:
        await session.aclose("test_complete")


async def test_two_failed_stale_reconnects_degrade_instead_of_polling_forever(monkeypatch):
    """同水位健康探测不占额度；其后权威持续领先两次才上交故障。"""

    clock = ConcurrentClock()
    monkeypatch.setattr(asyncio.get_running_loop(), "time", clock.monotonic)

    class _StillSilentNotify:
        opens = 0

        def __init__(self, game_id, transport, *, on_frame, **kwargs):
            self.on_frame = on_frame

        async def run(self):
            _StillSilentNotify.opens += 1
            await self.on_frame(NotifyFrame(seq=100))
            await asyncio.Event().wait()

    monkeypatch.setattr(game_module, "SSENotifyClient", _StillSilentNotify)
    transport = FakeTransport()
    audit = FakeAuditSink()
    transport.handler = lambda **kwargs: (200, json.dumps(snapshot(
        100 if clock.monotonic() < 9 else 101,
        turn=1, phase="draw", drawn="")))
    session = OfficialGameSession(
        game_id="exhausted_stale_game", transport=transport,
        scheduler=RequestScheduler(clock=clock.monotonic, sleep=clock.sleep).for_game(
            "exhausted_stale_game", max_games=10),
        timing=TIMING, monotonic_clock=clock.monotonic,
        wall_clock_unix_ms=clock.wall_ms, retry_sleep=clock.sleep,
        audit=audit, audit_context=make_audit_context,
        sse_enabled=True, sse_snapshot_first=True,
    )

    async def ticker():
        while clock.monotonic() < 26:
            await clock.sleep(.1)

    async def scenario():
        timer = asyncio.create_task(ticker())
        try:
            return await session.next_item()
        finally:
            timer.cancel()
            await asyncio.gather(timer, return_exceptions=True)

    try:
        result = await clock.run(scenario())
        reconnects = [r.payload for r in audit.records
                      if r.payload.get("trigger") == "sse_stale_reconnect"]
        assert _StillSilentNotify.opens == 4
        assert [r["reason"] for r in reconnects] == [
            "active_frame_silence", "watermark_lag", "watermark_lag"]
        assert [r["attempt_no"] for r in reconnects[1:]] == [1, 2]
        assert isinstance(result, GameFailed)
        assert result.recoverable
        assert result.reason == "sse_stale_reconnects_exhausted"
    finally:
        await session.aclose("test_complete")


async def test_separate_silent_episodes_each_get_a_fresh_reconnect_budget(monkeypatch):
    """每次新帧追上权威水位后，后续独立静默重新获得两次重连额度。"""

    clock = ConcurrentClock()
    monkeypatch.setattr(asyncio.get_running_loop(), "time", clock.monotonic)

    class _RecoveringNotify:
        opens = 0

        def __init__(self, game_id, transport, *, on_frame, **kwargs):
            self.on_frame = on_frame

        async def run(self):
            _RecoveringNotify.opens += 1
            await self.on_frame(NotifyFrame(seq=99 + _RecoveringNotify.opens))
            await asyncio.Event().wait()

    monkeypatch.setattr(game_module, "SSENotifyClient", _RecoveringNotify)
    audit = FakeAuditSink()
    transport = FakeTransport()
    finished = load_fixture("state_response_finished.json")

    def handler(**kwargs):
        now = clock.monotonic()
        if now >= 29:
            return 200, json.dumps(finished)
        seq = 100 + min(int(now // 8), 3)
        return 200, json.dumps(snapshot(seq, turn=1, phase="draw", drawn=""))

    transport.handler = handler
    session = OfficialGameSession(
        game_id="separate_stale_episodes", transport=transport,
        scheduler=RequestScheduler(clock=clock.monotonic, sleep=clock.sleep).for_game(
            "separate_stale_episodes", max_games=10),
        timing=TIMING, monotonic_clock=clock.monotonic,
        wall_clock_unix_ms=clock.wall_ms, retry_sleep=clock.sleep,
        audit=audit, audit_context=make_audit_context,
        sse_enabled=True, sse_snapshot_first=True,
    )

    async def ticker():
        while clock.monotonic() < 40:
            await clock.sleep(.1)

    async def scenario():
        timer = asyncio.create_task(ticker())
        try:
            return await session.next_item()
        finally:
            timer.cancel()
            await asyncio.gather(timer, return_exceptions=True)

    try:
        result = await clock.run(scenario())
        reconnects = [r for r in audit.records
                      if r.payload.get("trigger") == "sse_stale_reconnect"]
        assert isinstance(result, GameFinished)
        assert _RecoveringNotify.opens >= 4
        assert len(reconnects) >= 3
        assert [r.payload["attempt_no"] for r in reconnects[:3]] == [1, 1, 1]
    finally:
        await session.aclose("test_complete")


async def test_continuous_uncertain_get_does_not_extend_recovery_probes_past_20s(monkeypatch):
    """连续间歇 GET 不确定只能占用首次故障起算的二十秒加密额度。"""

    clock = ConcurrentClock()
    monkeypatch.setattr(asyncio.get_running_loop(), "time", clock.monotonic)
    monkeypatch.setattr(game_module, "SSENotifyClient", _SilentNotify)
    audit, transport, calls = FakeAuditSink(), FakeTransport(), Counter()
    baseline = snapshot(100, turn=1, phase="draw", drawn="")
    finished = load_fixture("state_response_finished.json")
    failures = []

    def handler(**kwargs):
        calls["get"] += 1
        now = clock.monotonic()
        if calls["get"] % 3 == 2:
            failures.append(now)
            raise UncertainTransportError("injected_recurrent_get_failure")
        return 200, json.dumps(finished if now >= 36 else baseline)

    transport.handler = handler
    session = OfficialGameSession(
        game_id="bounded_get_recovery", transport=transport,
        scheduler=RequestScheduler(clock=clock.monotonic, sleep=clock.sleep).for_game(
            "bounded_get_recovery", max_games=10),
        timing=TIMING, monotonic_clock=clock.monotonic,
        wall_clock_unix_ms=clock.wall_ms, retry_sleep=clock.sleep,
        audit=audit, audit_context=make_audit_context,
        sse_enabled=True, sse_snapshot_first=True,
    )

    async def ticker():
        while clock.monotonic() < 37:
            await clock.sleep(.1)

    async def scenario():
        timer = asyncio.create_task(ticker())
        try:
            return await session.next_item()
        finally:
            timer.cancel()
            await asyncio.gather(timer, return_exceptions=True)

    try:
        result = await clock.run(scenario())
        starts = [r.payload for r in audit.records
                  if r.kind.value == "http_request" and r.payload.get("phase") == "started"]
        recovery_at = [r["request_timing"]["transport_started_at_monotonic"] for r in starts
                       if r["request_timing"].get("query_purpose") == "sse_recovery_probe"]
        ordinary_at = [r["request_timing"]["transport_started_at_monotonic"] for r in starts
                       if r["request_timing"].get("query_purpose") == "sse_silence_probe"]
        assert isinstance(result, GameFinished)
        assert failures and failures[-1] > failures[0] + 30
        assert recovery_at and max(recovery_at) <= failures[0] + 20.2
        assert any(at > failures[0] + 21 for at in ordinary_at)
    finally:
        await session.aclose("test_complete")


@pytest.mark.parametrize("authoritative_ahead", [False, True])
async def test_repeated_old_frames_do_not_cancel_bounded_get_recovery_probes(
    monkeypatch, authoritative_ahead,
):
    """GET 不确定后重复旧帧即使等于旧权威水位，也不得取消恢复探针。"""

    clock = ConcurrentClock()
    monkeypatch.setattr(asyncio.get_running_loop(), "time", clock.monotonic)

    class _RepeatingOldNotify:
        def __init__(self, game_id, transport, *, on_frame, **kwargs):
            self.on_frame = on_frame

        async def run(self):
            await self.on_frame(NotifyFrame(seq=100))
            while True:
                await clock.sleep(.25)
                await self.on_frame(NotifyFrame(seq=100))

    monkeypatch.setattr(game_module, "SSENotifyClient", _RepeatingOldNotify)
    transport, audit, calls = FakeTransport(), FakeAuditSink(), Counter()
    finished = load_fixture("state_response_finished.json")
    history = {"seq": 101, "gap": False,
               "events": [event(101, "pass", seat=1)]}
    failures = []

    def handler(**kwargs):
        calls["get"] += 1
        now = clock.monotonic()
        if calls["get"] == 1:
            return 200, json.dumps(snapshot(
                101 if authoritative_ahead else 100, turn=1, phase="draw", drawn=""))
        if calls["get"] == 2:
            failures.append(now)
            raise UncertainTransportError("injected_get_failure")
        return 200, json.dumps(
            finished if now >= 25 else history if authoritative_ahead else
            snapshot(100, turn=1, phase="draw", drawn=""))

    transport.handler = handler
    session = OfficialGameSession(
        game_id="old_frames_during_get_recovery", transport=transport,
        scheduler=RequestScheduler(clock=clock.monotonic, sleep=clock.sleep).for_game(
            "old_frames_during_get_recovery", max_games=10),
        timing=TIMING, monotonic_clock=clock.monotonic,
        wall_clock_unix_ms=clock.wall_ms, retry_sleep=clock.sleep,
        audit=audit, audit_context=make_audit_context,
        sse_enabled=True, sse_snapshot_first=True,
    )

    async def scenario():
        async def ticker():
            while clock.monotonic() < 27:
                await clock.sleep(.1)

        timer = asyncio.create_task(ticker())
        try:
            return await session.next_item()
        finally:
            timer.cancel()
            await asyncio.gather(timer, return_exceptions=True)

    try:
        result = await clock.run(scenario())
        starts = [r.payload["request_timing"] for r in audit.records
                  if r.kind.value == "http_request" and r.payload.get("phase") == "started"]
        recovery_at = [r["transport_started_at_monotonic"] for r in starts
                       if r.get("query_purpose") == "sse_recovery_probe"]
        ordinary_at = [r["transport_started_at_monotonic"] for r in starts
                       if r.get("query_purpose") == "sse_silence_probe"]
        assert isinstance(result, GameFinished)
        assert failures
        assert len(recovery_at) >= 10
        assert max(recovery_at) <= failures[0] + 20.2
        assert any(at > failures[0] + 21 for at in ordinary_at)
    finally:
        await session.aclose("test_complete")


async def test_historical_events_alone_do_not_prove_sse_stream_is_stale(monkeypatch):
    """旧历史批次不代表当前权威水位，不能据此换掉尚活动的 SSE。"""

    clock = ConcurrentClock()
    monkeypatch.setattr(asyncio.get_running_loop(), "time", clock.monotonic)

    class _QuietNotify:
        opens = 0

        def __init__(self, game_id, transport, *, on_frame, **kwargs):
            self.on_frame = on_frame

        async def run(self):
            _QuietNotify.opens += 1
            await self.on_frame(NotifyFrame(seq=100))
            await asyncio.Event().wait()

    monkeypatch.setattr(game_module, "SSENotifyClient", _QuietNotify)
    audit, transport, calls = FakeAuditSink(), FakeTransport(), Counter()
    finished = load_fixture("state_response_finished.json")
    history = {"seq": 100, "gap": False,
               "events": [event(100, "pass", seat=1)]}

    def handler(**kwargs):
        calls["get"] += 1
        if clock.monotonic() >= 14:
            return 200, json.dumps(finished)
        if calls["get"] == 1:
            return 200, json.dumps(snapshot(100, turn=1, phase="draw", drawn=""))
        return 200, json.dumps(history)

    transport.handler = handler
    session = OfficialGameSession(
        game_id="history_is_not_authority", transport=transport,
        scheduler=RequestScheduler(clock=clock.monotonic, sleep=clock.sleep).for_game(
            "history_is_not_authority", max_games=10),
        timing=TIMING, monotonic_clock=clock.monotonic,
        wall_clock_unix_ms=clock.wall_ms, retry_sleep=clock.sleep,
        audit=audit, audit_context=make_audit_context,
        sse_enabled=True, sse_snapshot_first=True,
    )

    async def ticker():
        while clock.monotonic() < 16:
            await clock.sleep(.1)

    async def scenario():
        timer = asyncio.create_task(ticker())
        try:
            return await session.next_item()
        finally:
            timer.cancel()
            await asyncio.gather(timer, return_exceptions=True)

    try:
        result = await clock.run(scenario())
        assert isinstance(result, GameFinished)
        assert calls["get"] >= 5
        assert _QuietNotify.opens == 1
        assert not any(r.payload.get("trigger") == "sse_stale_reconnect"
                       for r in audit.records)
    finally:
        await session.aclose("test_complete")


async def test_ten_recovering_games_keep_shared_state_budget(monkeypatch):
    """十桌同时进入短探针后，实际发起仍受生产滚动额度与间距约束。"""

    clock = ConcurrentClock()
    monkeypatch.setattr(asyncio.get_running_loop(), "time", clock.monotonic)
    monkeypatch.setattr(game_module, "SSENotifyClient", _SilentNotify)
    root = RequestScheduler(
        rate_per_second=16, burst=DEFAULT_PRODUCTION_STATE_BURST,
        state_arrival_guard_sec=DEFAULT_STATE_ARRIVAL_GUARD_SEC,
        state_min_spacing_sec=DEFAULT_PRODUCTION_STATE_MIN_SPACING_SEC,
        clock=clock.monotonic, sleep=clock.sleep, poll_interval=0,
    )
    transport, audit = FakeTransport(), FakeAuditSink()
    calls = Counter()
    baseline = snapshot(100, turn=1, phase="draw", drawn="")
    finished = load_fixture("state_response_finished.json")

    def handler(*, method, path, **kwargs):
        assert method == "GET"
        game = path.split("/")[3]
        calls[game] += 1
        if calls[game] == 2:
            raise UncertainTransportError("injected_transient_get_failure")
        return 200, json.dumps(finished if clock.monotonic() >= 12 else baseline)

    transport.handler = handler
    sessions = [
        OfficialGameSession(
            game_id=f"recovery_game_{i}", transport=transport,
            scheduler=root.for_game(f"recovery_game_{i}", max_games=10),
            timing=TIMING, monotonic_clock=clock.monotonic,
            wall_clock_unix_ms=clock.wall_ms, retry_sleep=clock.sleep,
            audit=audit, audit_context=make_audit_context,
            sse_enabled=True, sse_snapshot_first=True,
        )
        for i in range(10)
    ]

    async def ticker():
        while clock.monotonic() < 13:
            await clock.sleep(.1)

    async def scenario():
        timer = asyncio.create_task(ticker())
        try:
            return await asyncio.gather(*(session.next_item() for session in sessions))
        finally:
            timer.cancel()
            await asyncio.gather(timer, return_exceptions=True)

    try:
        results = await clock.run(scenario())
        assert all(isinstance(item, GameFinished) for item in results)
        starts = [r.payload["request_timing"] for r in audit.records
                  if r.kind.value == "http_request" and r.payload.get("phase") == "started"
                  and r.payload.get("method") == "GET"]
        sent = sorted(row["transport_started_at_monotonic"] for row in starts)
        largest = max(sum(start <= at < start + 1.05 for at in sent) for start in sent)
        waits = [row["granted_at_monotonic"] - row["queued_at_monotonic"]
                 for row in starts]
        assert largest <= 16
        assert max(waits) < 1.0
        assert len(sent) >= 100
    finally:
        for session in sessions:
            await session.aclose("test_complete")
