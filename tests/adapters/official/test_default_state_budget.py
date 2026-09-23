"""测试房、测试赛事、正式赛事和自由赛的默认state调度装配回归。

仅替换OfficialTransport构造以隔离网络，故意不注入RequestScheduler；由真实
initialize/open_game创建场次。连续权威快照用于制造可观察查询，不模拟牌型强度。
"""

from __future__ import annotations

import asyncio
import json
from collections import Counter

import pytest

from _official_testkit import FakeAuditSink, FakeTransport, load_fixture, make_audit_context
from _virtual_clock import VirtualClock

from hangma_bot.adapters.official import auto_match, participant
from hangma_bot.adapters.official.transport import TransportConfig
from hangma_bot.adapters.official.scheduler import Priority
from hangma_bot.application.contracts import ObservedActionWindow, RuntimeMode, RuntimeTarget, SessionBootstrap


MODES = (
    RuntimeMode.TEST_ROOM,
    RuntimeMode.TEST_TOURNAMENT,
    RuntimeMode.OFFICIAL_TOURNAMENT,
    RuntimeMode.AUTO_MATCH,
)
GAMES = tuple("g-default-{}".format(index) for index in range(10))


class DispatchTransport(FakeTransport):
    """通过公开request参数记录各端点的实际发起时刻，单位为虚拟单调秒。"""

    def __init__(self, clock):
        super().__init__()
        self.clock = clock
        self.dispatches = []

    async def request(self, method, path, **kwargs):
        self.dispatches.append((self.clock.monotonic(), method, path, (kwargs.get("params") or {}).get("seq")))
        return await super().request(method, path, **kwargs)


def state_sends(transport):
    return [entry for entry in transport.dispatches if entry[1] == "GET" and entry[2].endswith("/state")]


def default_session(monkeypatch, clock, mode, *, audit=None):
    """保留真实默认调度器装配，只替换网络构造并注入时钟和等待函数。"""
    transport = DispatchTransport(clock)
    audit = FakeAuditSink() if audit is None else audit
    is_auto = mode is RuntimeMode.AUTO_MATCH
    room_id = "r_auto_default" if is_auto else "t_test_room_1"
    fetched = Counter()
    joined = False
    rules = load_fixture("rules.json")
    rules["config"].update(M=10, Rounds=8)
    detail = load_fixture("tournament_detail.json")
    detail["config"].update(M=10, Rounds=8)
    detail["my_games"] = list(GAMES)
    if is_auto:
        detail["tournament_id"] = room_id
        detail["config"]["Kind"] = "auto"

    def handler(*, method, path, params=None, **kwargs):
        nonlocal joined
        if path == "/portal/api/guide/version":
            return 200, json.dumps({"version": 15, "updated_at": "2026-09-05", "changes": []})
        if path == "/api/me":
            active = GAMES if not is_auto or joined else ()
            return 200, json.dumps({"user_id": "u_player_a", "tournament_id": "" if is_auto else room_id,
                                    "active_games": [{"game_id": game} for game in active]})
        if path == "/api/match":
            assert is_auto and method == "POST"
            joined = True
            return 200, json.dumps({"room_id": room_id, "round_no": 1, "config": {"M": 10, "Rounds": 8}})
        if path == "/api/tournaments/me/rules":
            assert not is_auto
            return 200, json.dumps(rules)
        if path == "/api/tournaments/" + room_id:
            return 200, json.dumps(detail)
        if path.startswith("/api/games/") and path.endswith("/state"):
            assert method == "GET"
            game_id = path.split("/")[3]
            assert game_id in GAMES
            fetched[game_id] += 1
            # 每次给出不同单局的完整观察，使next_item恰好产出一次新窗口；
            # 这里关注HTTP装配和计时，不以这些快速跳转宣称真实牌局轨迹。
            doc = load_fixture("state_response_snapshot_draw.json")
            doc["seq"] = 100 + fetched[game_id]
            doc["snapshot"]["round_no"] = fetched[game_id]
            return 200, json.dumps(doc)
        raise AssertionError("意外请求：{} {}".format(method, path))

    transport.handler = handler
    module = auto_match if is_auto else participant
    monkeypatch.setattr(module, "OfficialTransport", lambda token, config: transport)
    constructor = module.OfficialAutoMatchSession if is_auto else module.OfficialTournamentSession
    session = constructor(
        token="fake-token-do-not-log",
        transport_config=TransportConfig(base_url="https://10.240.169.190:18080",
                                         insecure_hosts=frozenset({"10.240.169.190"})),
        monotonic_clock=clock.monotonic, wall_clock_unix_ms=clock.wall_ms,
        retry_sleep=clock.sleep, audit=audit,
        audit_context=lambda: make_audit_context(tournament_id=room_id),
    )
    target = RuntimeTarget(mode=mode, expected_tournament_id="" if is_auto else room_id,
                           known_guide_version=15)
    return session, target, transport


@pytest.mark.parametrize("mode", MODES, ids=lambda mode: mode.value)
async def test_m10_default_scheduler_leaves_a_nearby_permit_for_first_discard_watch(monkeypatch, mode):
    """生产四入口同刻十场请求时，预期他家弃牌的查询不应被整秒额度空档阻断。"""
    clock = VirtualClock()
    session, _, _ = default_session(monkeypatch, clock, mode)
    root = session._scheduler  # 核对真实默认装配；本测试仍只经公开 acquire 发请求。
    games = [root.for_game(str(i), max_games=10) for i in range(10)]

    async def query(scope, priority):
        async with await scope.acquire(priority):
            return clock.monotonic()

    async def settle():
        for _ in range(300):
            await asyncio.sleep(0)

    def advance(seconds):
        clock.advance(seconds)
        for due, future in clock.waiting:
            if due <= clock.monotonic() + 1e-10 and not future.done():
                future.set_result(None)
        clock.waiting = [(due, future) for due, future in clock.waiting if not future.done()]

    ordinary = [asyncio.create_task(query(games[i % 10], Priority.POLL)) for i in range(16)]
    watch = None
    try:
        await settle()
        advance(1.0)  # 新建用户账的一秒保护到期，十场同时进入轮询。
        await settle()
        advance(.1)
        await settle()
        watch = asyncio.create_task(query(games[6], Priority.DISCARD_WATCH))
        await settle()
        advance(.2)
        await settle()
        assert watch.done(), "首次弃牌查询不应因先前十场突发而等待近一秒"
        assert watch.result() <= 1.3
    finally:
        for task in ordinary + ([watch] if watch is not None else []):
            if not task.done():
                task.cancel()
        await asyncio.gather(*(ordinary + ([watch] if watch is not None else [])), return_exceptions=True)
        await session.aclose()


@pytest.mark.parametrize("mode", MODES, ids=lambda mode: mode.value)
async def test_default_entry_waits_one_initial_second_then_allows_bounded_fast_queries(monkeypatch, mode):
    clock = VirtualClock()
    session, target, transport = default_session(monkeypatch, clock, mode)
    try:
        bootstrap = await clock.run(session.initialize(target))
        assert isinstance(bootstrap, SessionBootstrap), bootstrap
        assert bootstrap.config.max_games == 10
        assert clock.monotonic() == 0.0, "建账保护不得延迟初始化控制请求"
        assert not state_sends(transport)
        if mode is RuntimeMode.AUTO_MATCH:
            match = [call for call in transport.dispatches if call[2] == "/api/match"]
            assert len(match) == 1 and match[0][0] == 0.0, "首次入席POST不等待state启动保护"

        game = session.open_game(GAMES[0])
        first = await clock.run(game.next_item())
        assert isinstance(first, ObservedActionWindow)
        assert state_sends(transport)[0][0] == pytest.approx(1.0)
        second = await clock.run(game.next_item())
        assert isinstance(second, ObservedActionWindow)
        assert second.window_key != first.window_key
        assert [sent[0] for sent in state_sends(transport)] == [1.0, 1.0], (
            "相邻增量与快照需要两笔即刻许可，不能恢复每场固定间隔")

        await game.aclose("reopen_test")
        reopened = session.open_game(GAMES[0])
        assert reopened is not game
        assert isinstance(await clock.run(reopened.next_item()), ObservedActionWindow)
        assert [sent[0] for sent in state_sends(transport)] == pytest.approx([1.0, 1.0, 1.0]), (
            "关闭重开单场不能重新建账；首次增量与快照可使用有限突发余量")
    finally:
        await session.aclose()


@pytest.mark.parametrize("mode", MODES, ids=lambda mode: mode.value)
async def test_default_entry_shares_sixteen_sends_and_keeps_account_when_game_reopens(monkeypatch, mode):
    clock = VirtualClock()
    session, target, transport = default_session(monkeypatch, clock, mode)
    try:
        bootstrap = await clock.run(session.initialize(target))
        assert isinstance(bootstrap, SessionBootstrap), bootstrap
        games = [session.open_game(game_id) for game_id in GAMES]
        for index in range(16):
            observed = await clock.run(games[index % len(games)].next_item())
            assert isinstance(observed, ObservedActionWindow)
        assert [sent[0] for sent in state_sends(transport)] == pytest.approx(
            [1.0] * 4 + [1.0 + (index - 3) / 16 for index in range(4, 16)]), (
            "生产默认装配应只保留四笔即刻许可，随后按共享16/s平滑发放")

        await games[0].aclose("quota_reopen_test")
        reopened = session.open_game(GAMES[0])
        assert reopened is not games[0]
        assert isinstance(await clock.run(reopened.next_item()), ObservedActionWindow)
        sends = state_sends(transport)
        assert len(sends) == 17
        assert sends[-1][0] == pytest.approx(2.05), "重开场次不得清除用户已发记录，提前发出第17笔"
        assert sends[-1][3] == 0, "重建场次以权威快照恢复，额度账独立保留"

        # 滚动账已恢复；刚重开的同场继续使用用户共享的长期平滑间隔，
        # 不能因场次重开而重新领取一笔即刻额度。
        assert isinstance(await clock.run(reopened.next_item()), ObservedActionWindow)
        times = [sent[0] for sent in state_sends(transport)]
        assert times[-1] == pytest.approx(2.05 + 1 / 14.5)
        assert all(sum(at - 1.0 < value <= at for value in times) <= 16 for at in times)
    finally:
        await session.aclose()
