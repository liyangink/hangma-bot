"""十场真实会话的合成协议压力夹具；只替换网络和时间，不实现第二套麻将规则。

本人为座2；其他三家响应阶段按预定墙钟推进，不调用客户端缓发。各场
没有未来牌墙，阶段脚本不是完整牌局，也不用于比较策略得分。
"""

import asyncio
from collections import Counter
from dataclasses import replace
import json

from _official_testkit import FakeAuditSink
from _virtual_clock import VirtualClock
from test_default_state_budget import GAMES, default_session
from test_sync_repair_regressions import event, snapshot

from hangma_bot.adapters.official import participant
from hangma_bot.adapters.official.errors import ConflictError, RateLimitedError, UncertainTransportError
from hangma_bot.application.contracts import (
    ActionAttempt, ObservedActionWindow, RuntimeMode, SessionBootstrap,
    SubmitAccepted, SubmitAmbiguous, SubmitNotSent, SubmitRejectedRetryable,
    SubmitRejectedNoRefresh,
)
from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.kernel.actions import Chi, Discard, Pass, Peng, Tile, WindowPhase, action_key


class ConcurrentClock(VirtualClock):
    """统一推进并发等待；每次推进前留足真实会话多层异步回调的零时轮转。"""

    def wall_ms(self):
        """由同一个总时刻换算Unix毫秒，不逐次截断小步长而累积假钟差。"""
        return 1_750_000_000_000 + round(self.monotonic() * 1000)

    async def run(self, awaitable):
        task = asyncio.create_task(awaitable)
        for _ in range(10000):
            for _ in range(80):
                await asyncio.sleep(0)
            if task.done():
                return task.result()
            self.waiting = [(when, f) for when, f in self.waiting if not f.done()]
            assert self.waiting, "十场夹具死锁，无可推进的网络或计时等待"
            nearest = min(when for when, f in self.waiting)
            self.advance(max(0, nearest - self.monotonic()))
            for when, future in self.waiting:
                if when <= self.monotonic() + 1e-10 and not future.done():
                    future.set_result(None)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        raise AssertionError("十场夹具未在有界虚拟时间内结束")


class ScriptedServer:
    """固定协议时间线：场0/1摸牌、场2动作故障、场3—8碰转吃、场9断序恢复。

    所有时间均为从测试开始计的虚拟单调秒；快照截止换算成 Unix 毫秒。
    phase 截止在建模时固定，绝不因客户端晚查询而延长。POST按服务器
    当前阶段和截止验收，读取预算由假传输实际执行，而非只记录参数。
    """

    def __init__(self, clock, transport, *, latency, stagger, cooldown, ambiguous, slow_boundary):
        self.clock, self.transport = clock, transport
        self.latency, self.stagger = latency, stagger
        self.cooldown, self.ambiguous = cooldown, ambiguous
        self.slow_boundary = slow_boundary
        self.slow_injected = False
        self.original_request = transport.request
        self.gets, self.posts = Counter(), Counter()
        self.active, self.max_active = Counter(), Counter()
        self.exchanges, self.attempts, self.windows = [], {}, []
        self.cancelled, self.timeouts, self.faults = [], [], []
        self.cooldown_until = None
        self.epochs = {g: 2.0 + i * stagger for i, g in enumerate(GAMES)}
        self.draw_at = {g: 1 + i * stagger + latency + .12 for i, g in enumerate(GAMES[:2])}
        self.accepted = []

    def state(self, game):
        """按当前时刻生成权威阶段；每次查询不重开吃碰窗口。"""
        i, now = GAMES.index(game), self.clock.monotonic()
        peng_end = self.epochs[game]
        if i in (0, 1):
            initial = self.gets[game] == 1
            doc = snapshot(100 if initial else 101, turn=1 if initial else 2,
                           drawn="" if initial else "7w",
                           phase="response_chi" if initial else "draw",
                           discard={"seat": 1, "tile": "4t", "seq": 100})
            # 我方已过的吃阶段到点进入正常摸牌；该阶段切换本身无事件。
            end = self.draw_at[game] if initial else self.draw_at[game] + 3
        elif i == 9:
            initial = self.gets[game] == 1
            doc = snapshot(100 if initial else 103, turn=1 if initial else 2,
                           drawn="" if initial else "7w")
            end = 7.0
        else:
            phase = "response_peng" if now < peng_end else "response_chi"
            end = peng_end if phase == "response_peng" else peng_end + 1
            is_draw = now >= peng_end + 1
            if is_draw:
                phase, end = "draw", peng_end + 4
            doc = snapshot(102 if is_draw else 100, turn=2 if is_draw else 1,
                           phase=phase, drawn="7w" if is_draw else "",
                           discard={"seat": 1, "tile": "4t", "seq": 100},
                           responders=() if is_draw else (2,))
        body = doc["snapshot"]
        body["my_hand"] = ["1w", "2w", "3w", "4w", "5w", "6w", "7w",
                           "3t", "4t", "4t", "5t", "白", "东"]
        body["melds"] = [[], [], [], []]
        body["discards"] = [[], ["4t"], [], []]
        body["hand_counts"] = [13, 13, 14 if body["drawn_tile"] else 13, 13]
        body["god"] = {"baotou": False, "chain_count": 0, "catch_play": False,
                       "god_discarder_seat": -1}
        body["window_deadline_ms"] = 1_750_000_000_000 + round(end * 1000)
        return doc

    async def handle(self, *, method, path, params=None, json_body=None, **kwargs):
        game = path.split("/")[3]
        i = GAMES.index(game)
        if method == "POST":
            self.posts[game] += 1
            attempted = self.attempts[game]
            start = self.clock.monotonic()
            assert start < attempted.latest_send_at_monotonic, "超过本地发送截止仍发POST"
            current = self.state(game)["snapshot"]
            assert current["phase"] == attempted.window_key.phase.value, "对已迁移阶段发POST"
            await self.clock.sleep(self.latency)
            if i == 2:
                self.faults.append((game, "ambiguous" if self.ambiguous else "409", self.clock.monotonic()))
                if self.ambiguous:
                    raise UncertainTransportError("injected_action_reply_lost")
                raise ConflictError(409, "INVALID_ACTION", "injected_explicit_rejection")
            assert self.clock.wall_ms() < current["window_deadline_ms"], "POST到达服务器时窗口已过期"
            self.accepted.append((game, json_body["action"], start, self.clock.monotonic()))
            return 200, '{"ok":true}'

        self.gets[game] += 1
        number = self.gets[game]
        if i in (0, 1) and number == 2:
            assert params["seq"] == 100
            await self.clock.sleep(max(self.latency, self.draw_at[game] - self.clock.monotonic()))
            return 200, json.dumps({"seq": 101, "gap": False,
                                   "events": [event(101, "tile_drawn", seat=2, tile="7w")]})
        if i == 9 and number == 2:
            assert params["seq"] == 100
            await self.clock.sleep(self.latency)
            if self.cooldown:
                self.cooldown_until = self.clock.monotonic() + 2.8
                self.faults.append((game, "429", self.clock.monotonic()))
                raise RateLimitedError(429, "RATE_LIMITED", "injected_state_cooldown", 2.8)
            self.faults.append((game, "gap", self.clock.monotonic()))
            return 200, json.dumps({"seq": 103, "gap": True,
                                   "events": [event(103, "tile_drawn", seat=2, tile="7w")]})
        if 3 <= i <= 8 and params["seq"] != 0:
            # 官方碰转吃本身没有事件；旧长轮询须由真实边界定时器取消。
            await asyncio.Future()
        if (i == 3 and self.slow_boundary and not self.slow_injected
                and self.state(game)["snapshot"]["phase"] == "response_chi"):
            self.slow_injected = True
            await self.clock.sleep(1.0)  # 故意超过剩余读预算，由假传输实际中止。
        await self.clock.sleep(self.latency)
        return 200, json.dumps(self.state(game))

    async def request(self, method, path, **kwargs):
        """记录真实请求入口并执行虚拟读超时，取消清理占用原连接直到完成。"""
        game = path.split("/")[3]
        key = (game, method)
        self.active[key] += 1
        self.max_active[key] = max(self.max_active[key], self.active[key])
        assert self.active[key] == 1, "同场出现重复在途GET或POST"
        row = {"game": game, "method": method, "start": self.clock.monotonic(),
               "seq": (kwargs.get("params") or {}).get("seq"),
               "budget": kwargs.get("request_budget_sec")}
        self.exchanges.append(row)
        pending = asyncio.create_task(self.original_request(method, path, **kwargs))
        timer = None
        try:
            budget = kwargs.get("request_budget_sec")
            if budget is None:
                return await pending
            timer = asyncio.create_task(self.clock.sleep(budget))
            done, _ = await asyncio.wait((pending, timer), return_when=asyncio.FIRST_COMPLETED)
            if pending in done:
                return pending.result()
            self.timeouts.append((game, self.clock.monotonic()))
            raise UncertainTransportError("injected_read_timeout")
        except asyncio.CancelledError:
            self.cancelled.append((game, self.clock.monotonic()))
            # 网络取消并非瞬时；真实调度必须等此清理完成才复用state槽。
            await self.clock.sleep(.04)
            raise
        finally:
            pending.cancel()
            if timer is not None:
                timer.cancel()
            await asyncio.gather(pending, *((timer,) if timer is not None else ()), return_exceptions=True)
            row["end"] = self.clock.monotonic()
            self.active[key] -= 1


async def run_scenario(monkeypatch, *, latency=.04, stagger=0, cooldown=False,
                       ambiguous=False, pacing=True, slow_boundary=False):
    """运行真实默认赛事入口与十场会话；生产规则复核动作，仅读内存审计。"""
    clock, audit = ConcurrentClock(), FakeAuditSink()
    if not pacing:
        original = participant.OfficialGameSession

        def without_pacing(**kwargs):
            return original(**kwargs, discard_pacing_enabled=False)

        monkeypatch.setattr(participant, "OfficialGameSession", without_pacing)
    # 固定退避附加抖动，仅用于429注入重现；不替换调度器或消费假额度。
    monkeypatch.setattr("hangma_bot.adapters.official.scheduler.random.Random.uniform", lambda self, a, b: a)
    session, target, transport = default_session(monkeypatch, clock, RuntimeMode.TEST_ROOM, audit=audit)
    bootstrap = await clock.run(session.initialize(target))
    assert isinstance(bootstrap, SessionBootstrap) and bootstrap.config.max_games == 10
    server = ScriptedServer(clock, transport, latency=latency, stagger=stagger,
                            cooldown=cooldown, ambiguous=ambiguous, slow_boundary=slow_boundary)
    transport.handler = server.handle
    transport.request = server.request
    games = [session.open_game(g) for g in GAMES]
    outcomes = {}

    async def attempt(game, window, action, number=1):
        from hangma_bot.hangma import HangmaRules
        from hangma_bot.kernel.config import RuleConfig
        assert HangmaRules(RuleConfig("concurrent-test", 1, False)).validate(window.observation, action).legal
        budget = BudgetPolicy().build(window.received_at_monotonic, window.timeout_seconds,
                                      window.expires_at_monotonic)
        request = ActionAttempt(
            decision_id="concurrent-" + game.game_id, attempt_no=number, plan_revision=1,
            window_key=window.window_key, based_on_authoritative_seq=window.authoritative_seq,
            action=action, action_key=action_key(action), latest_send_at_monotonic=budget.latest_send_at_monotonic)
        server.attempts[game.game_id] = request
        outcome = await game.submit(request)
        outcomes.setdefault(game.game_id, []).append(type(outcome).__name__ + ":" + getattr(outcome, "reason", ""))
        return request, outcome

    async def observe(game):
        window = await game.next_item()
        assert isinstance(window, ObservedActionWindow), window
        server.windows.append({"game": game.game_id, "phase": window.window_key.phase.value,
                               "received": clock.monotonic(), "expires": window.expires_at_monotonic})
        return window

    async def actor(i, game):
        if stagger:
            # 越过默认一秒新账保护后再错峰，否则启动保护会把错峰重新合并。
            await clock.sleep(1 + i * stagger)
        window = await observe(game)
        if i == 2:
            await clock.sleep(.2)  # 本场固定处理时间；在其他场缓发期间提交已知动作。
            request, outcome = await attempt(game, window, Peng(Tile("4t")))
            if ambiguous:
                assert isinstance(outcome, SubmitAmbiguous), outcome
                repeated = await game.submit(replace(request, attempt_no=2))
                assert isinstance(repeated, SubmitNotSent), repeated
                outcomes[game.game_id].append(type(repeated).__name__ + ":" + repeated.reason)
            elif isinstance(outcome, SubmitRejectedRetryable):
                assert outcome.refreshed_window.window_key == window.window_key
                assert outcome.refreshed_window.expires_at_monotonic <= window.expires_at_monotonic
            else:
                assert isinstance(outcome, SubmitRejectedNoRefresh), outcome
                assert outcome.reason == "conflict_refresh_unavailable"
            return
        if window.window_key.phase is WindowPhase.RESPONSE_PENG:
            _, outcome = await attempt(game, window, Pass())
            assert isinstance(outcome, SubmitNotSent) and outcome.reason == "pass_deferred_until_chi"
            window = await observe(game)
        action = (Chi(tuple(Tile(c) for c in ("3t", "4t", "5t")))
                  if window.window_key.phase is WindowPhase.RESPONSE_CHI else Discard(Tile("7w")))
        _, outcome = await attempt(game, window, action)
        assert isinstance(outcome, SubmitAccepted), outcome

    async def work():
        tasks = [asyncio.create_task(actor(i, game)) for i, game in enumerate(games)]
        try:
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await session.aclose()

    await clock.run(work())
    return server, audit, outcomes


def rolling_peak(exchanges):
    """按纳秒归一化计实际GET的左开右闭滚动秒，排除浮点整秒边界舍入误差。"""
    times = [round(row["start"] * 1_000_000_000) for row in exchanges if row["method"] == "GET"]
    return max(sum(at - 1_000_000_000 < t <= at for t in times) for at in times)


def verify_safety(server, audit):
    """用传输入口与公开审计交叉核对，而非读取调度器私有账或动作门。"""
    assert rolling_peak(server.exchanges) == 16, "必须实际打满额度且不得超额"
    assert set(server.gets) == set(GAMES)
    assert all(v == 0 for v in server.active.values())
    assert all(v == 1 for v in server.max_active.values())
    assert all(v == 1 for v in server.posts.values())
    records = [r for r in audit.records if "/api/games/" in r.payload.get("endpoint", "")]
    started = [r for r in records if r.payload.get("phase") == "started"]
    finished = [r for r in records if r.payload.get("phase") == "finished"]
    assert len(started) == len(finished) == len(server.exchanges)
    assert Counter(r.payload["request_id"] for r in started) == Counter(r.payload["request_id"] for r in finished)
    assert len({r.payload["request_id"] for r in started}) == len(started)
    assert Counter((r.context.game_id, r.payload["method"], round(r.monotonic_ns)) for r in started) == Counter(
        (r["game"], r["method"], int(r["start"] * 1_000_000_000)) for r in server.exchanges)
    timings = [r.payload["request_timing"] for r in started if r.payload["method"] == "GET"]
    assert all(t["latest_start_monotonic"] is None or
               t["transport_started_at_monotonic"] < t["latest_start_monotonic"] for t in timings)
    assert any(t["queued_at_monotonic"] >= 1 and
               t["transport_started_at_monotonic"] - t["queued_at_monotonic"] > .1 for t in timings), (
        "除新账一秒保护外，必须实际出现运行中的额度排队")
    # 对已经入队且最终发出的明确期限查询，不允许反过来服务更晚的期限。
    known = [t for t in timings if t["latest_start_monotonic"] is not None]
    for current in known:
        assert not any(other["queued_at_monotonic"] <= current["transport_started_at_monotonic"]
                       and other["transport_started_at_monotonic"] > current["transport_started_at_monotonic"] + 1e-9
                       and other["latest_start_monotonic"] < current["latest_start_monotonic"] - 1e-9
                       for other in known), "明确截止查询发生优先级倒置"
