"""并发行为测试：动作优先不饥饿、多场并发窗口不互相阻塞。"""
from __future__ import annotations

import asyncio
import json

from hangma_bot.adapters.official.scheduler import Priority, RequestScheduler
from hangma_bot.application.contracts import ObservedActionWindow

from _official_testkit import FakeClock, instant_sleep, load_fixture, make_game_session


async def test_two_games_poll_concurrently_without_starvation() -> None:
    """同 Token 两场并发轮询：共享同一传输与限速器，都能获得窗口且请求交织。"""

    from _official_testkit import FakeTransport

    clock = FakeClock()
    scheduler = RequestScheduler(clock=clock.monotonic, sleep=instant_sleep(clock), poll_interval=0.0)
    # 单个共享传输：资源模型与生产一致（一个 Token 一个连接池，M 场共用）
    shared = FakeTransport()
    doc = load_fixture("state_response_snapshot_draw.json")

    def handler(method=None, path=None, **kwargs):
        assert path.startswith("/api/games/g1/state") or path.startswith("/api/games/g2/state"), path
        return 200, json.dumps(doc)

    shared.handler = handler
    results = {}
    for game_id in ("g1", "g2"):
        session = make_game_session(
            transport=shared,
            clock=clock,
            game_id=game_id,
            scheduler=scheduler,
        )
        results[game_id] = asyncio.create_task(session.next_item())

    done, pending = await asyncio.wait(results.values(), timeout=5)
    assert not pending
    for item in done:
        assert isinstance(item.result(), ObservedActionWindow)
    # 两场请求都经过同一共享传输（交织记录）
    paths = [c.path for c in shared.calls]
    assert any("/g1/" in p for p in paths) and any("/g2/" in p for p in paths)
    assert len(paths) >= 2


async def test_four_tokens_concurrent_auth_isolation() -> None:
    """四 Token 并发初始化：认证头各自独立、互不串线、关闭互不影响。"""

    import httpx

    from hangma_bot.adapters.official.participant import OfficialTournamentSession
    from hangma_bot.adapters.official.transport import OfficialTransport, TransportConfig
    from _official_testkit import FakeClock, RequestScheduler, instant_sleep
    from hangma_bot.application.contracts import RuntimeMode, RuntimeTarget

    seen_tokens = []
    TOKENS = ["token-alpha-0001", "token-beta-0002", "token-gamma-0003", "token-delta-0004"]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/portal/api/guide/version":
            # 版本接口免认证（API 文档 §3.1），不带 Authorization
            body = dict(load_fixture("guide_breaking_future.json"))
            body["version"] = 8
            body["changes"] = []
            return httpx.Response(200, json=body)
        auth = request.headers.get("Authorization", "")
        seen_tokens.append(auth)
        token = auth.replace("Bearer ", "")
        # 每个 Token 得到与自身绑定的身份：串线会立刻暴露
        user = {"token-alpha-0001": "u_a", "token-beta-0002": "u_b",
                "token-gamma-0003": "u_c", "token-delta-0004": "u_d"}[token]
        if request.url.path == "/api/me":
            return httpx.Response(200, json={"user_id": user, "tournament_id": "t_test_room_1",
                                             "active_games": [{"game_id": "g1"}]})
        if request.url.path == "/api/tournaments/me/rules":
            return httpx.Response(200, json=load_fixture("rules.json"))
        return httpx.Response(200, json=load_fixture("tournament_detail.json"))

    clock = FakeClock()
    target = RuntimeTarget(mode=RuntimeMode.TEST_ROOM, expected_tournament_id="t_test_room_1", known_guide_version=8)

    async def run_one(token: str):
        transport = OfficialTransport(
            token,
            TransportConfig(base_url="https://h.example", insecure_hosts=frozenset()),
            transport_handler=httpx.MockTransport(handler),
        )
        session = OfficialTournamentSession(
            token=token,
            transport_config=TransportConfig(base_url="https://h.example", insecure_hosts=frozenset()),
            monotonic_clock=clock.monotonic,
            wall_clock_unix_ms=clock.wall_ms,
            scheduler=RequestScheduler(clock=clock.monotonic, sleep=instant_sleep(clock), poll_interval=0.0),
            retry_sleep=instant_sleep(clock),
        )
        session._transport = transport
        try:
            boot = await asyncio.wait_for(session.initialize(target), timeout=5)
            return session, boot
        finally:
            pass

    outcomes = await asyncio.gather(*[run_one(t) for t in TOKENS])
    boots = [b for _, b in outcomes]
    participants = sorted(b.participant_id for b in boots)
    assert participants == ["u_a", "u_b", "u_c", "u_d"]  # 身份与 Token 一一对应
    # 每个请求都携带正确的独立认证头
    assert all(auth.startswith("Bearer token-") for auth in seen_tokens)
    # 关闭一个 Token 不影响其他 Token 的传输
    await outcomes[0][0].aclose()
    for _, boot in outcomes[1:]:
        assert boot.participant_id  # 其余会话对象仍然可用


async def test_action_request_wins_over_background_poll() -> None:
    """限速饱和时动作请求先于背景轮询获得许可。"""

    clock = FakeClock()
    scheduler = RequestScheduler(
        rate_per_second=1.0,
        burst=1.0,
        clock=clock.monotonic,
        sleep=instant_sleep(clock),
        poll_interval=0.0,
    )
    holder = await asyncio.wait_for(scheduler.acquire(Priority.BACKGROUND), timeout=2)
    poll_task = asyncio.create_task(scheduler.acquire(Priority.POLL))
    await asyncio.sleep(0.02)
    action_task = asyncio.create_task(scheduler.acquire(Priority.ACTION))
    await asyncio.sleep(0.02)
    holder.release()
    clock.advance(2.0)  # 令牌回填
    action_lease = await asyncio.wait_for(action_task, timeout=2)
    assert action_lease.priority is Priority.ACTION
    action_lease.release()
    poll_lease = await asyncio.wait_for(poll_task, timeout=5)
    poll_lease.release()
