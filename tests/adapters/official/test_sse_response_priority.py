"""SSE 过期碰窗后的吃窗发现：共享额度竞争和 429 截止回归。"""

from __future__ import annotations

import asyncio
import json

import pytest

from _official_testkit import FakeAuditSink, FakeTransport, TIMING, load_fixture, make_audit_context
from _concurrent_adapter_harness import ConcurrentClock
from hangma_bot.adapters.official import game as game_module
from hangma_bot.adapters.official.errors import RateLimitedError
from hangma_bot.adapters.official.game import OfficialGameSession
from hangma_bot.adapters.official.notify import NotifyEndKind, NotifyFrame, NotifyRunResult
from hangma_bot.adapters.official.scheduler import Priority, RequestScheduler
from hangma_bot.application.contracts import GameFinished, ObservedActionWindow
from hangma_bot.kernel.actions import WindowPhase


class _Notify:
    """只推送测试显式给出的水位，不替代权威牌面。"""

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


def _response(phase: str, seq: int, wall_origin_ms: int) -> dict:
    doc = load_fixture("state_response_snapshot_peng.json")
    doc["seq"] = seq
    snap = doc["snapshot"]
    snap["phase"] = phase
    snap["window_deadline_ms"] = wall_origin_ms + (1000 if phase == "response_peng" else 2000)
    snap["responding_seats"] = [2]
    return doc


async def _setup(monkeypatch, *, rate_limit: bool, next_phase: str = "chi",
                 rate: float = 1.0, guard: float = .2,
                 retry_after: float | None = None):
    _Notify.instances.clear()
    monkeypatch.setattr(game_module, "SSENotifyClient", _Notify)
    clock = ConcurrentClock()
    audit = FakeAuditSink()
    # 一笔 /state 每 1.2 秒；模拟满载时多个场次同时等待下一许可。
    root = RequestScheduler(rate_per_second=rate, burst=rate, state_arrival_guard_sec=guard,
                            clock=clock.monotonic, sleep=clock.sleep)
    transport = FakeTransport()
    origin = clock.wall_ms()
    peng = _response("response_peng", 120, origin)
    chi = _response("response_chi", 121, origin)
    new_peng = _response("response_peng", 122, origin)
    new_peng["snapshot"]["last_discard"] = {"seat": 1, "tile": "2w", "seq": 121}
    new_peng["snapshot"]["window_deadline_ms"] = origin + 2100
    finished = load_fixture("state_response_finished.json")

    def handler(**kwargs):
        if len(transport.calls) == 1:
            return 200, json.dumps(peng)
        if rate_limit and len(transport.calls) == 2:
            return RateLimitedError(429, "RATE_LIMITED", "injected", retry_after)
        if next_phase == "new_peng" and clock.monotonic() < 2.1:
            return 200, json.dumps(new_peng)
        if next_phase == "chi" and clock.monotonic() < 2.0:
            return 200, json.dumps(chi)
        return 200, json.dumps(finished)

    transport.handler = handler
    session = OfficialGameSession(
        game_id="priority_case", transport=transport,
        scheduler=root.for_game("priority_case", max_games=10), timing=TIMING,
        monotonic_clock=clock.monotonic, wall_clock_unix_ms=clock.wall_ms,
        audit=audit, audit_context=make_audit_context, retry_sleep=clock.sleep,
        sse_enabled=True, sse_snapshot_first=True,
    )
    first = await clock.run(session.next_item())
    assert isinstance(first, ObservedActionWindow)
    assert first.window_key.phase is WindowPhase.RESPONSE_PENG
    assert len(_Notify.instances) == 1
    return clock, root, session, audit, transport


async def _advance_and_notify(clock, session):
    clock.advance(.9)  # 旧碰窗的安全取态截止已过，新吃窗尚未截止。
    await _Notify.instances[0].on_frame(NotifyFrame(seq=121, closed=False, raw='{"seq":121}'))
    return await clock.run(session.next_item())


async def test_expired_peng_successor_chi_preempts_older_ordinary_recovery(monkeypatch):
    """另一场先排普通恢复时，已知下一吃窗的一笔权威查询先获许可。"""

    clock, root, session, audit, transport = await _setup(monkeypatch, rate_limit=False)
    peer = root.for_game("ordinary_peer", max_games=10)

    async def ordinary_recovery():
        lease = await peer.acquire(Priority.RECOVERY)
        lease.release()

    try:
        clock.advance(.9)
        peer_task = asyncio.create_task(ordinary_recovery())
        for _ in range(10):
            await asyncio.sleep(0)
        assert root.state_queue_snapshot["ready_state"] == 1
        await _Notify.instances[0].on_frame(NotifyFrame(seq=121, closed=False, raw='{"seq":121}'))
        result = await clock.run(session.next_item())
        assert isinstance(result, ObservedActionWindow)
        assert result.window_key.phase is WindowPhase.RESPONSE_CHI
        assert len(transport.calls) == 2, "到期旧窗不可额外补一笔状态"
        starts = [r.payload["request_timing"] for r in audit.records
                  if r.payload.get("phase") == "started" and r.payload.get("method") == "GET"]
        assert starts[-1]["query_purpose"] == "anticipated_chi_sync"
        assert starts[-1]["latest_start_monotonic"] == pytest.approx(1.75)
        assert starts[-1]["transport_started_at_monotonic"] == pytest.approx(1.2)
    finally:
        if "peer_task" in locals():
            peer_task.cancel()
            await asyncio.gather(peer_task, return_exceptions=True)
        await session.aclose("test_complete")


async def test_anticipated_chi_429_does_not_retry_after_its_start_deadline(monkeypatch):
    """首笔429后继续按共享账和原吃窗预算退避，超时即放弃旧窗。"""

    clock, root, session, audit, transport = await _setup(monkeypatch, rate_limit=True)
    try:
        result = await _advance_and_notify(clock, session)
        assert isinstance(result, GameFinished)
        assert len(transport.calls) == 3, "一笔429、边界后一次现状同步，不重发过期吃窗GET"
        starts = [r.payload["request_timing"] for r in audit.records
                  if r.payload.get("phase") == "started" and r.payload.get("method") == "GET"]
        assert starts[1]["query_purpose"] == "anticipated_chi_sync"
        assert starts[-1]["query_purpose"] == "current_state_sync"
        assert starts[-1]["transport_started_at_monotonic"] >= 2.0
    finally:
        await session.aclose("test_complete")


async def test_anticipated_chi_never_overrides_an_earlier_real_deadline(monkeypatch):
    """相同共享额度中，另一桌更早的真实发起截止仍排在推定吃窗之前。"""

    clock, root, session, audit, transport = await _setup(monkeypatch, rate_limit=False)
    peer = root.for_game("earlier_deadline_peer", max_games=10)
    grants = []

    async def urgent_peer():
        lease = await peer.acquire(Priority.RECOVERY, deadline_monotonic=1.3)
        grants.append(clock.monotonic())
        lease.release()

    try:
        clock.advance(.9)
        peer_task = asyncio.create_task(urgent_peer())
        for _ in range(10):
            await asyncio.sleep(0)
        assert root.state_queue_snapshot["ready_state"] == 1
        await _Notify.instances[0].on_frame(NotifyFrame(seq=121, closed=False, raw='{"seq":121}'))
        result = await clock.run(session.next_item())
        assert isinstance(result, GameFinished)
        assert grants == [pytest.approx(1.2)]
        assert len(transport.calls) == 2, "吃窗截止已过，不能迟发旧查询"
        assert any(r.payload.get("state_query_cancel_reason") == "expired_anticipated_chi"
                   for r in audit.records)
    finally:
        if "peer_task" in locals():
            peer_task.cancel()
            await asyncio.gather(peer_task, return_exceptions=True)
        await session.aclose("test_complete")


async def test_anticipated_chi_query_accepts_unexpected_authoritative_result(monkeypatch):
    """通知水位并非吃牌事实；若权威结果已终局，直接接受而不补发吃窗查询。"""

    clock, root, session, audit, transport = await _setup(
        monkeypatch, rate_limit=False, next_phase="finished")
    try:
        result = await _advance_and_notify(clock, session)
        assert isinstance(result, GameFinished)
        assert len(transport.calls) == 2
        assert any(r.payload.get("request_timing", {}).get("query_purpose") == "anticipated_chi_sync"
                   for r in audit.records)
    finally:
        await session.aclose("test_complete")


async def test_anticipated_chi_expiry_immediately_reads_new_peng_cycle(monkeypatch):
    """429 把旧吃窗预警耗尽后，新弃牌可能已另开碰窗，禁止等待旧吃窗边界。"""

    clock, root, session, audit, transport = await _setup(
        monkeypatch, rate_limit=True, next_phase="new_peng",
        rate=16, guard=0, retry_after=1.0)
    try:
        result = await _advance_and_notify(clock, session)
        assert isinstance(result, ObservedActionWindow)
        assert result.window_key.phase is WindowPhase.RESPONSE_PENG
        assert result.window_key.trigger_seq == 121
        assert clock.monotonic() < 2.0
        assert len(transport.calls) == 3
        assert any(r.payload.get("state_query_cancel_reason") == "expired_anticipated_chi"
                   for r in audit.records)
        starts = [r.payload["request_timing"] for r in audit.records
                  if r.payload.get("phase") == "started" and r.payload.get("method") == "GET"]
        assert starts[-1]["query_purpose"] == "current_state_sync"
        assert starts[-1]["transport_started_at_monotonic"] < 2.0
    finally:
        await session.aclose("test_complete")


async def test_anticipated_chi_stale_peng_200_waits_for_new_authoritative_phase(monkeypatch):
    """优先查询若仍见旧碰窗，不重复交付旧窗；新水位随后仍能发现权威吃窗。"""

    clock, root, session, audit, transport = await _setup(
        monkeypatch, rate_limit=False, rate=16, guard=0)
    old_peng = _response("response_peng", 120, clock.wall_ms())
    # 旧快照的截止必须保持初始时刻，不因重新读取而被测试夹具延长。
    old_peng["snapshot"]["window_deadline_ms"] = clock.wall_ms() + 1000
    chi = _response("response_chi", 122, clock.wall_ms())
    second_seen = asyncio.Event()

    def handler(**kwargs):
        if len(transport.calls) == 2:
            second_seen.set()
            return 200, json.dumps(old_peng)
        return 200, json.dumps(chi)

    transport.handler = handler

    async def announce_chi():
        await second_seen.wait()
        # 让旧权威 200 先被投影；下一个官方通知才打开新查询。
        for _ in range(5):
            await asyncio.sleep(0)
        await _Notify.instances[0].on_frame(
            NotifyFrame(seq=122, closed=False, raw='{"seq":122}'))

    announcement = asyncio.create_task(announce_chi())
    try:
        result = await _advance_and_notify(clock, session)
        await announcement
        assert isinstance(result, ObservedActionWindow)
        assert result.window_key.phase is WindowPhase.RESPONSE_CHI
        assert result.authoritative_seq == 122
        assert len(transport.calls) == 3, "旧权威碰窗不得诱发连续高优先级 GET"
        starts = [r.payload["request_timing"] for r in audit.records
                  if r.payload.get("phase") == "started" and r.payload.get("method") == "GET"]
        assert [s["query_purpose"] for s in starts[1:]] == [
            "anticipated_chi_sync", "current_state_sync"]
        assert all(call.method == "GET" for call in transport.calls)
    finally:
        announcement.cancel()
        await asyncio.gather(announcement, return_exceptions=True)
        await session.aclose("test_complete")
