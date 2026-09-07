"""真实传输公开入口回归：成功、取消和赛事请求均有原始审计。"""
import asyncio
import json

import httpx
import pytest

from _official_testkit import FakeAuditSink, FakeClock, make_game_session
from test_sync_repair_regressions import snapshot
from hangma_bot.adapters.official.transport import OfficialTransport, TransportConfig


@pytest.mark.parametrize("cancel_in_flight", [False, True])
async def test_every_server_seen_state_request_has_a_raw_audit_record(cancel_in_flight):
    clock, audit = FakeClock(), FakeAuditSink()
    entered = asyncio.Event()
    server_seen = []

    async def handler(request):
        server_seen.append(str(request.url))
        entered.set()
        if cancel_in_flight:
            await asyncio.Future()
        return httpx.Response(200, json=snapshot(100, turn=2, drawn="7w"))

    transport = OfficialTransport("diagnostic-dummy", TransportConfig(
        base_url="https://diagnostic.invalid", insecure_hosts=frozenset()),
        transport_handler=httpx.MockTransport(handler))
    session = make_game_session(transport=transport, clock=clock, audit=audit)
    task = asyncio.create_task(session.next_item())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        if cancel_in_flight:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        else:
            await asyncio.wait_for(task, 1)
    finally:
        await session.aclose("diagnostic_complete")
        await transport.aclose()
    raw = [r for r in audit.records if r.payload.get("source") == "state_response"]
    assert len(server_seen) == 1
    assert len(raw) == len(server_seen), (
        f"HTTP端已看到{len(server_seen)}次state请求，但只有{len(raw)}条原始审计；"
        f"cancel_in_flight={cancel_in_flight}")


async def test_tournament_discovery_and_ready_have_original_http_audit(monkeypatch):
    """公开初始化/报名/到位入口；只替换传输构造的网络后端，不读私有状态。"""
    from _official_testkit import FakeTransport, make_audit_context
    from test_tournament_session import _initialize_handler, TARGET
    from hangma_bot.adapters.official import participant
    from hangma_bot.application.contracts import SessionBootstrap
    clock, audit, fixture_transport = FakeClock(), FakeAuditSink(), FakeTransport()
    _initialize_handler(fixture_transport)
    seen = []
    async def handler(request):
        seen.append(request.method + " " + request.url.path)
        if request.method == "POST":
            return httpx.Response(200, json={"ok": True})
        code, text = fixture_transport.handler(method=request.method, path=request.url.path)
        return httpx.Response(code, text=text)
    config = TransportConfig(base_url="https://diagnostic.invalid", insecure_hosts=frozenset())
    transport = OfficialTransport("diagnostic-dummy", config, transport_handler=httpx.MockTransport(handler))
    monkeypatch.setattr(participant, "OfficialTransport", lambda *args, **kwargs: transport)
    session = participant.OfficialTournamentSession(token="diagnostic-dummy", transport_config=config,
        monotonic_clock=clock.monotonic, wall_clock_unix_ms=clock.wall_ms,
        audit=audit, audit_context=make_audit_context)
    try:
        initialized = await session.initialize(TARGET)
        assert isinstance(initialized, SessionBootstrap)
        await session.register()
        await session.ready(initialized.initial_snapshot.stage)
    finally:
        await session.aclose()
    raw = [r for r in audit.records if "raw" in r.payload]
    assert len(seen) == 6
    assert len(raw) == len(seen), f"六次赛事HTTP调用均已成功，但原文审计只有{len(raw)}条：{seen}"


async def test_cancelled_http_request_still_consumes_production_state_quota():
    """反证：漏审计不等于漏扣额度；取消后下一请求仍受14/s节奏约束。"""
    from _official_testkit import instant_sleep
    from hangma_bot.adapters.official.scheduler import RequestScheduler
    clock, audit = FakeClock(start=0), FakeAuditSink()
    entered = asyncio.Event()
    starts = []
    async def handler(request):
        starts.append(clock.monotonic())
        if len(starts) == 1:
            entered.set()
            await asyncio.Future()
        return httpx.Response(200, json=snapshot(100, turn=2, drawn="7w"))
    transport = OfficialTransport("diagnostic-dummy", TransportConfig(
        base_url="https://diagnostic.invalid", insecure_hosts=frozenset()),
        transport_handler=httpx.MockTransport(handler))
    scheduler = RequestScheduler(clock=clock.monotonic, sleep=instant_sleep(clock), rate_per_second=14, burst=1)
    session = make_game_session(transport=transport, clock=clock, audit=audit, scheduler=scheduler)
    first = asyncio.create_task(session.next_item())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        first.cancel()
        await asyncio.gather(first, return_exceptions=True)
        await session.next_item()
        assert len(starts) == 2 and starts[1] - starts[0] >= 1/14 - 1e-9
    finally:
        first.cancel()
        await asyncio.gather(first, return_exceptions=True)
        await session.aclose("probe_complete")
        await transport.aclose()
