"""指南 v30 的入口兼容门：v29 功能开关按指纹放行，未知变更先于参赛副作用拒绝。

来源为 2026-09-10 同步的官方完整指南快照（doc/references/official-guide-version-v30.json）。
本批审查覆盖：

- v28（changed）：胡大牌榜排序链变更——纯门户展示，零协议影响；
- v29（breaking）：新增全服功能开关，关闭后 /api/match 新匹配与测试房「重开下一轮」
  一律 403 FEATURE_DISABLED（永久条件；后者此前是 409 房态类）；
- v30（changed）：他人 name 全面收口为 AI 昵称、空则空串——本 bot 按 user_id 作稳定身份。

只替换网络构造并注入假时钟，通过赛事会话公开接口验证。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from _official_testkit import FakeClock, FakeTransport, instant_sleep, load_fixture
from hangma_bot.adapters.official import auto_match, participant
from hangma_bot.adapters.official.dto import KNOWN_GUIDE_VERSION
from hangma_bot.adapters.official.errors import ForbiddenError
from hangma_bot.adapters.official.transport import TransportConfig
from hangma_bot.application.contracts import (
    OperationStatus,
    ParticipantTerminal,
    ParticipantTerminalReason,
    RuntimeMode,
    RuntimeTarget,
    SessionBootstrap,
)


GUIDE_V30 = Path(__file__).parents[3] / "doc/references/official-guide-version-v30.json"
SCOPED_MODES = (RuntimeMode.TEST_ROOM, RuntimeMode.TEST_TOURNAMENT, RuntimeMode.OFFICIAL_TOURNAMENT)
MODES = (*SCOPED_MODES, RuntimeMode.AUTO_MATCH)


def make_session(monkeypatch, mode):
    """保持生产会话装配；返回可变官方响应脚本以驱动阶段边界与 403 分支。"""
    clock, transport = FakeClock(), FakeTransport()
    is_auto = mode is RuntimeMode.AUTO_MATCH
    # 非自动匹配路径沿用它 fixture 里 rules.json 的锦标赛 id，否则归属校验会先失败。
    room_id = "r_auto_v30" if is_auto else "t_test_room_1"
    detail = load_fixture("tournament_detail.json")
    detail["tournament_id"] = room_id
    if is_auto:
        detail["status"] = "registering"
        detail["config"].update(Kind="auto", M=10, Rounds=8)
        detail["my_games"] = []
    script = {
        "guide": json.loads(GUIDE_V30.read_text(encoding="utf-8")),
        "detail": detail,
        "me": {"user_id": "u_player_a", "tournament_id": "" if is_auto else room_id,
               "active_games": []},
        "match_error": None,
        "ready_error": None,
    }

    def handler(*, method, path, **kwargs):
        if path == "/portal/api/guide/version":
            return 200, json.dumps(script["guide"])
        if path == "/api/me":
            return 200, json.dumps(script["me"])
        if path == "/api/tournaments/me/rules":
            assert not is_auto
            return 200, json.dumps(load_fixture("rules.json"))
        if path == "/api/tournaments/" + room_id:
            return 200, json.dumps(script["detail"])
        if path == "/api/tournaments/me/ready":
            assert not is_auto and method == "POST"
            if script["ready_error"] is not None:
                raise script["ready_error"]
            return 200, "{}"
        if path == "/api/match":
            assert is_auto and method == "POST"
            if script["match_error"] is not None:
                raise script["match_error"]
            return 200, json.dumps({"room_id": room_id, "round_no": 1})
        raise AssertionError("意外请求：{} {}".format(method, path))

    transport.handler = handler
    module = auto_match if is_auto else participant
    monkeypatch.setattr(module, "OfficialTransport", lambda token, config: transport)
    constructor = module.OfficialAutoMatchSession if is_auto else module.OfficialTournamentSession
    session = constructor(
        token="fake-token-do-not-log",
        transport_config=TransportConfig(base_url="https://guide-review.invalid",
                                         insecure_hosts=frozenset()),
        monotonic_clock=clock.monotonic,
        wall_clock_unix_ms=clock.wall_ms,
        retry_sleep=instant_sleep(clock),
    )
    target = RuntimeTarget(mode=mode, expected_tournament_id="" if is_auto else room_id,
                           known_guide_version=KNOWN_GUIDE_VERSION)
    return session, target, transport, script


@pytest.mark.parametrize("mode", MODES, ids=lambda mode: mode.value)
async def test_reviewed_v30_initializes_supported_entry(monkeypatch, mode):
    """v28/v29/v30 审查后，四条入口都能正常初始化（v29 已按指纹放行）。"""
    session, target, transport, script = make_session(monkeypatch, mode)
    try:
        result = await session.initialize(target)
        assert isinstance(result, SessionBootstrap), result
        assert result.guide.version == 30
        assert not result.guide.has_unknown_breaking_change
        assert sum(call.path == "/api/match" for call in transport.calls) == (mode is RuntimeMode.AUTO_MATCH)
    finally:
        await session.aclose()


@pytest.mark.parametrize("mode", MODES, ids=lambda mode: mode.value)
@pytest.mark.parametrize("change", ("new_same_version", "rewritten_v29_entry"))
async def test_unreviewed_breaking_stops_before_participation(monkeypatch, mode, change):
    """同版本新增 breaking、或已审查的 v29 条目被改写，都必须先于任何参赛动作拒绝。"""
    session, target, transport, script = make_session(monkeypatch, mode)
    if change == "new_same_version":
        script["guide"]["changes"].append({
            "version": 30, "type": "breaking", "summary": "同版本新增未审查参赛约束",
        })
    else:
        reviewed = next(item for item in script["guide"]["changes"] if item["version"] == 29)
        reviewed["detail"] += "\n同一条目新增未审查的入口限制"
    try:
        result = await session.initialize(target)
        assert isinstance(result, ParticipantTerminal)
        assert result.reason is ParticipantTerminalReason.INCOMPATIBLE_GUIDE
        assert [(call.method, call.path) for call in transport.calls] == [
            ("GET", "/portal/api/guide/version")]
    finally:
        await session.aclose()


async def test_auto_match_feature_disabled_is_permanent_and_explained(monkeypatch):
    """v29 关闭自由匹配：403 FEATURE_DISABLED 必须是永久终态，且不与绑定问题混淆。"""
    session, target, transport, script = make_session(monkeypatch, RuntimeMode.AUTO_MATCH)
    script["match_error"] = ForbiddenError(403, "FEATURE_DISABLED", "free match disabled")
    try:
        result = await session.initialize(target)
        assert isinstance(result, ParticipantTerminal)
        assert result.reason is ParticipantTerminalReason.MATCHING_UNAVAILABLE
        assert "FEATURE_DISABLED" in result.detail
        assert "平台已关闭自由匹配" in result.detail
        assert "PORTAL_BINDING_REQUIRED" not in result.detail
        # 永久条件不得重试
        assert sum(call.path == "/api/match" for call in transport.calls) == 1
    finally:
        await session.aclose()


async def test_test_room_reopen_feature_disabled_is_permanent(monkeypatch):
    """v29 关闭自建测试房：already-finished 房「重开下一轮」的 ready 403 也必须明确终态。"""
    session, target, transport, script = make_session(monkeypatch, RuntimeMode.TEST_ROOM)
    boot = await session.initialize(target)
    assert isinstance(boot, SessionBootstrap)
    script["ready_error"] = ForbiddenError(403, "FEATURE_DISABLED", "test rooms disabled")
    try:
        transport.calls.clear()
        result = await session.ready(boot.initial_snapshot.stage)
        assert isinstance(result, ParticipantTerminal)
        assert result.reason is ParticipantTerminalReason.MATCHING_UNAVAILABLE
        assert "平台已关闭自建测试房" in result.detail
        assert sum(call.method == "POST" for call in transport.calls) == 1
    finally:
        await session.aclose()
