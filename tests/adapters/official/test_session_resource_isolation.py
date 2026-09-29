"""同用户共享state额度；每场连接槽、局部重试及非state冷却隔离。"""
import asyncio
import json

import pytest

from hangma_bot.adapters.official import participant
from hangma_bot.adapters.official.errors import NotFoundError, RateLimitedError
from hangma_bot.adapters.official.game import OfficialGameSession
from hangma_bot.adapters.official.scheduler import Priority, RequestKind, RequestScheduler
from hangma_bot.adapters.official.transport import TransportConfig
from hangma_bot.application.contracts import ObservedActionWindow, SessionBootstrap
from _official_testkit import FakeClock, FakeTransport, instant_sleep, load_fixture, make_game_session, TIMING
from test_tournament_session import _initialize_handler, TARGET
from test_sync_repair_regressions import snapshot


async def test_control_concurrency_does_not_block_open_game(monkeypatch):
    clock, transport = FakeClock(), FakeTransport()
    _initialize_handler(transport)
    discovery = transport.handler
    transport.handler = lambda **kw: (200, json.dumps(snapshot(100, turn=2, drawn="7w"))) if "/games/" in kw["path"] else discovery(**kw)
    monkeypatch.setattr(participant, "OfficialTransport", lambda *a, **kw: transport)
    control = RequestScheduler(clock=clock.monotonic, sleep=instant_sleep(clock), max_concurrent=1)
    session = participant.OfficialTournamentSession(token="test-only", transport_config=TransportConfig(
        base_url="https://example.invalid", insecure_hosts=frozenset()), monotonic_clock=clock.monotonic,
        wall_clock_unix_ms=clock.wall_ms, scheduler=control)
    assert isinstance(await session.initialize(TARGET), SessionBootstrap)
    held = await control.acquire(Priority.BACKGROUND, request_kind=RequestKind.OTHER)
    try:
        item = await asyncio.wait_for(session.open_game("g-isolated").next_item(), .1)
        assert isinstance(item, ObservedActionWindow)
    finally:
        held.release()
        await session.aclose()


async def test_tournament_gone_cooldown_yields_to_game_action_window(monkeypatch):
    """后台详情冷却交还控制槽和事件循环；场次动作窗仍可先交付。"""

    clock, transport = FakeClock(), FakeTransport()
    _initialize_handler(transport)
    discovery = transport.handler
    calls = {"detail": 0}
    sleeping, resume = asyncio.Event(), asyncio.Event()

    def handler(**kw):
        if "/games/" in kw["path"]:
            return 200, json.dumps(snapshot(100, turn=2, drawn="7w"))
        if kw["path"] == "/api/tournaments/t_test_room_1":
            calls["detail"] += 1
            if calls["detail"] == 2:
                raise NotFoundError(404, "TOURNAMENT_GONE", "tournament unavailable")
            if calls["detail"] > 2:
                return 200, json.dumps(load_fixture("tournament_stage_open.json"))
        return discovery(**kw)

    async def sleep(seconds):
        if seconds == 2.0:
            sleeping.set()
            await resume.wait()
        else:
            await instant_sleep(clock)(seconds)

    transport.handler = handler
    monkeypatch.setattr(participant, "OfficialTransport", lambda *a, **kw: transport)
    session = participant.OfficialTournamentSession(
        token="test-only",
        transport_config=TransportConfig(base_url="https://example.invalid", insecure_hosts=frozenset()),
        monotonic_clock=clock.monotonic,
        wall_clock_unix_ms=clock.wall_ms,
        retry_sleep=sleep,
    )
    assert isinstance(await session.initialize(TARGET), SessionBootstrap)
    background = asyncio.create_task(session.next_update())
    try:
        await asyncio.wait_for(sleeping.wait(), .1)
        item = await asyncio.wait_for(session.open_game("g-isolated").next_item(), .1)
        assert isinstance(item, ObservedActionWindow)
        resume.set()
        await asyncio.wait_for(background, .1)
    finally:
        resume.set()
        background.cancel()
        await session.aclose()


async def test_user_state_429_does_not_cool_other_games_state_queries():
    clock, transport = FakeClock(), FakeTransport()
    owner = RequestScheduler(clock=clock.monotonic, sleep=instant_sleep(clock))
    times = []
    def handler(**kw):
        times.append(clock.monotonic())
        if "/slow/" in kw["path"]:
            raise RateLimitedError(429, "RATE_LIMITED", "slow", 5)
        return 200, json.dumps(snapshot(100, turn=2, drawn="7w"))
    transport.handler = handler
    slow = OfficialGameSession(transport=transport, game_id="slow", timing=TIMING,
        monotonic_clock=clock.monotonic, wall_clock_unix_ms=clock.wall_ms,
        scheduler=owner.for_game("slow", max_games=4), max_get_retries=0)
    fast = make_game_session(transport=transport, clock=clock, game_id="fast",
                            scheduler=owner.for_game("fast", max_games=4))
    try:
        await slow.next_item()
        assert isinstance(await fast.next_item(), ObservedActionWindow)
        assert times[1] == times[0], "另一桌的 GET 不等待被拒请求的五秒 Retry-After"
    finally:
        await slow.aclose("test")
        await fast.aclose("test")


async def test_state_slot_reserves_concurrency_for_action_and_other_game():
    clock = FakeClock()
    owner = RequestScheduler(clock=clock.monotonic, sleep=instant_sleep(clock))
    first = owner.for_game("a", max_games=4)
    other = owner.for_game("b", max_games=4)
    poll = await first.acquire(Priority.POLL, request_kind=RequestKind.STATE)
    action = await first.acquire(Priority.ACTION, request_kind=RequestKind.OTHER)
    peer = await other.acquire(Priority.POLL, request_kind=RequestKind.STATE)
    assert first.active_count == 2 and other.active_count == 1
    action.release()
    poll.release()
    peer.release()


async def test_reopening_same_game_does_not_reset_rate_allowance():
    clock = FakeClock()
    owner = RequestScheduler(clock=clock.monotonic, sleep=instant_sleep(clock))
    for _ in range(17):
        channel = owner.for_game("same-game", max_games=4)
        lease = await channel.acquire(Priority.POLL)
        lease.release()
    assert clock.monotonic() == pytest.approx(1001.0)


@pytest.mark.parametrize('max_games', [1, 4, 7, 8, 10, 16])
async def test_shared_state_rates_bound_user_total_without_static_game_caps(max_games):
    clock = FakeClock(start=0)
    owner = RequestScheduler(clock=clock.monotonic, sleep=instant_sleep(clock))
    starts = []
    for _ in range(4):
        for game in range(max_games):
            scheduler = owner.for_game(str(game), max_games=max_games)
            lease = await scheduler.acquire(Priority.POLL)
            starts.append((game, clock.monotonic()))
            lease.release()
    for game, start in starts:
        in_window = [(g, at) for g, at in starts if start - 1e-8 <= at < start + 1 - 1e-8]
        assert len(in_window) <= 16
    if max_games == 1:
        assert starts[-1][1] == starts[0][1] == 0  # 单场可借全部余量，无2/s硬上限。
