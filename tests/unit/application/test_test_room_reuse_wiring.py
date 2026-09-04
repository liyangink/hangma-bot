"""组合回归：真实官方赛事会话 × TEST_ROOM × finished 冷启动的跨轮复用可达。

评审者复现形态：OfficialTournamentSession（脚本化传输 + tournament_finished
fixture）接入真实 ParticipantRuntime——证明 finished 快照透传后 supervisor 的
register→ready 复用分支在真实适配器形态下可达，而不是只在 Fake 端口测试里成立。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from fakes import build_runtime
from hangma_bot.adapters.official.participant import OfficialTournamentSession
from hangma_bot.adapters.official.scheduler import RequestScheduler
from hangma_bot.adapters.official.transport import TransportConfig, TransportResult
from hangma_bot.application.contracts import ParticipantTerminalReason, RuntimeMode, RuntimeTarget
from hangma_bot.application.deadline import ManualClock

pytestmark = pytest.mark.asyncio

FIXTURES = Path(__file__).parents[2] / "fixtures" / "official" / "v8"
GUIDE_V11 = Path(__file__).parents[3] / "doc" / "references" / "official-guide-version-v11.json"


class ScriptedTransport:
    """最小脚本化传输；handler 按 (method, path) 返回 (status, text)。"""

    def __init__(self) -> None:
        self.calls = []
        self.aclosed = False

    async def request(
        self,
        method: str,
        path: str,
        *,
        json_body=None,
        params=None,
        with_auth: bool = True,
        long_poll: bool = False,
        request_budget_sec=None,
    ):
        self.calls.append((method, path))
        status, text = self.handler(
            method=method, path=path, json_body=json_body, params=params, long_poll=long_poll
        )
        return TransportResult(status=status, text=text)

    async def aclose(self) -> None:
        self.aclosed = True


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


async def test_test_room_finished_cold_boot_reaches_register_ready():
    """TEST_ROOM 冷启动于 finished 房：幂等报名+ready 后进入下一轮并正常完赛。"""

    clock = ManualClock()
    transport = ScriptedTransport()
    register_calls = []
    ready_calls = []
    game_polls = []
    state = {"round_started": False, "running_delivered": False}

    me_idle = _load("me.json")
    me_idle["active_games"] = []
    me_active = _load("me.json")
    running_detail = _load("tournament_detail.json")
    finished_detail = _load("tournament_finished.json")
    game_finished = _load("state_response_finished.json")
    guide_text = GUIDE_V11.read_text(encoding="utf-8")
    rules_text = json.dumps(_load("rules.json"))

    def handler(*, method=None, path=None, json_body=None, params=None, long_poll=None):
        if path == "/portal/api/guide/version":
            return 200, guide_text
        if path == "/api/me":
            doc = me_active if state["round_started"] else me_idle
            return 200, json.dumps(doc)
        if path == "/api/tournaments/me/rules":
            return 200, rules_text
        if path == "/api/tournaments/t_test_room_1":
            # 忠实建模官方语义：finished 房只有在我们 ready 之后才可能开启
            # 下一轮（4 令牌各 ready 一次）；开启后 running 只投递一次，
            # 本轮结束后回到 finished。
            if state["round_started"] and not state["running_delivered"]:
                state["running_delivered"] = True
                return 200, json.dumps(running_detail)
            return 200, json.dumps(finished_detail)
        if path == "/api/tournaments/t_test_room_1/register":
            register_calls.append(json_body)
            return 200, "{}"
        if path == "/api/tournaments/me/ready":
            ready_calls.append(json_body)
            state["round_started"] = True  # 我方 ready 后下一轮开启
            return 200, json.dumps({"ready": True})
        if path.startswith("/api/games/"):
            game_polls.append(params)
            return 200, json.dumps(game_finished)
        raise AssertionError("unexpected {} {}".format(method, path))

    transport.handler = handler

    scheduler = RequestScheduler(
        rate_per_second=1000.0,
        burst=1000.0,
        clock=clock.now,
        sleep=lambda _seconds: asyncio.sleep(0),
        poll_interval=0.0,
    )
    session = OfficialTournamentSession(
        token="fake-token-do-not-log",
        transport_config=TransportConfig(
            base_url="https://10.240.169.190:18080",
            insecure_hosts=frozenset({"10.240.169.190"}),
        ),
        monotonic_clock=clock.now,
        wall_clock_unix_ms=clock.unix_ms,
        scheduler=scheduler,
        retry_sleep=lambda _seconds: asyncio.sleep(0),
    )
    session._transport = transport  # 注入脚本化传输（与官方测试工具箱同法）

    target = RuntimeTarget(
        mode=RuntimeMode.TEST_ROOM,
        expected_tournament_id="t_test_room_1",
        known_guide_version=8,
    )
    runtime, sink, *_ = build_runtime(session=session, target=target, clock=clock)
    terminal = await runtime.run()

    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    assert len(register_calls) == 1  # finished 冷启动 → 幂等报名一次
    assert len(ready_calls) == 1  # 报名成功后首次 ready 开启下一轮
    assert len(game_polls) >= 1  # 下一轮的场次真实开启并轮询
    events = sink.lifecycle_events()
    assert "registered" in events
    assert "ready" in events
    # 会话由运行出口统一关闭
    assert transport.aclosed is True
    assert ("POST", "/api/tournaments/t_test_room_1/register") in transport.calls
    assert ("POST", "/api/tournaments/me/ready") in transport.calls
