"""真实SSE取消收尾回归：场会话关闭返回时，通知HTTP的finally必须已完成。

对应S03第8房notify请求49213行仅started、随后participant_finished的缺口。
注入HTTPX内存传输与可控时钟，不连接平台，不访问任何真实凭据。
"""
from __future__ import annotations

import asyncio
import httpx
import pytest

from _official_testkit import FakeAuditSink, FakeClock, TIMING, load_fixture, make_audit_context
from hangma_bot.adapters.official.game import OfficialGameSession
from hangma_bot.adapters.official.scheduler import RequestScheduler
from hangma_bot.adapters.official.transport import OfficialTransport, TransportConfig
from hangma_bot.application.contracts import ObservedActionWindow


@pytest.mark.asyncio
async def test_close_waits_for_real_sse_http_finally_and_audit_outcome():
    """公开aclose返回即可关审计；SSE请求必须有finished，不能留下异步尾巴。"""
    started, ended = asyncio.Event(), asyncio.Event()
    clock, audit = FakeClock(), FakeAuditSink()
    doc = load_fixture("state_response_snapshot_peng.json")

    async def handler(request):
        if request.url.path.endswith("/notify"):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                # 模拟真实连接取消时异步关闭；至少一次让出是必要收尾，不是延长动作窗。
                await asyncio.sleep(0)
                ended.set()
        return httpx.Response(200, json=doc)

    transport = OfficialTransport("fixture-only", TransportConfig(base_url="https://platform.invalid",
                                                                insecure_hosts=frozenset()),
                                  transport_handler=httpx.MockTransport(handler))
    root = RequestScheduler(clock=clock.monotonic)
    session = OfficialGameSession(game_id="g-close", transport=transport,
        scheduler=root.for_game("g-close", max_games=10), timing=TIMING,
        monotonic_clock=clock.monotonic, wall_clock_unix_ms=clock.wall_ms,
        audit=audit, audit_context=make_audit_context, sse_enabled=True, sse_snapshot_first=True)
    try:
        assert isinstance(await session.next_item(), ObservedActionWindow)
        await asyncio.wait_for(started.wait(), .5)
        await session.aclose("game_finished")
        assert ended.is_set(), "场会话aclose未等待在途SSE关闭，审计可先于HTTP收尾关闭"
        finishes = [r for r in audit.records if r.kind.value == "http_request"
                    and r.payload.get("phase") == "finished"
                    and r.payload.get("endpoint", "").endswith("/notify")]
        assert len(finishes) == 1, "SSE请求必须完成审计配对后才返回aclose"
    finally:
        await session.aclose("test_complete")
        if started.is_set():
            await asyncio.wait_for(ended.wait(), .5)
        # 让取消收尾完成，隔离测试也不遗留真实客户端任务。
        for _ in range(10):
            await asyncio.sleep(0)
        await transport.aclose()


@pytest.mark.parametrize("cancel_caller", [False, True])
@pytest.mark.asyncio
async def test_reentrant_or_cancelled_close_still_drains_sse(cancel_caller):
    """关闭重入或调用者取消均不能二次打断SSE的异步finally。"""
    started, closing, release, ended = (asyncio.Event() for _ in range(4))
    clock, audit = FakeClock(), FakeAuditSink()

    async def handler(request):
        if request.url.path.endswith("/notify"):
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
    scheduler = RequestScheduler(clock=clock.monotonic)
    session = OfficialGameSession(game_id="g-close", transport=transport,
        scheduler=scheduler.for_game("g-close", max_games=10), timing=TIMING,
        monotonic_clock=clock.monotonic, wall_clock_unix_ms=clock.wall_ms,
        audit=audit, audit_context=make_audit_context, sse_enabled=True, sse_snapshot_first=True)
    callers = []
    try:
        assert isinstance(await session.next_item(), ObservedActionWindow)
        await asyncio.wait_for(started.wait(), .5)
        first = asyncio.create_task(session.aclose("game_finished"))
        callers.append(first)
        await asyncio.wait_for(closing.wait(), .5)
        assert not first.done(), "在途收尾未完成时关闭不能返回"
        if cancel_caller:
            first.cancel()
        else:
            callers.append(asyncio.create_task(session.aclose("again")))
        for _ in range(10):
            await asyncio.sleep(0)
        assert not ended.is_set(), "重入／取消调用者不应打断HTTP异步关闭"
        assert not first.done(), "调用者取消也必须先回收本场"
        release.set()
        results = await asyncio.gather(*callers, return_exceptions=True)
        assert ended.is_set()
        assert isinstance(results[0], asyncio.CancelledError) if cancel_caller else results == [None, None]
        finishes = [r for r in audit.records if r.kind.value == "http_request"
                    and r.payload.get("phase") == "finished"
                    and r.payload.get("endpoint", "").endswith("/notify")]
        assert len(finishes) == 1
    finally:
        release.set()
        await session.aclose("test_complete")
        await asyncio.gather(*callers, return_exceptions=True)
        await transport.aclose()
