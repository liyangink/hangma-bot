"""指南 v27 的入口兼容门：按完整审查条目放行，未知变更先于参赛副作用拒绝。

来源为 2026-09-09 同步的官方完整指南快照。只替换网络构造并注入假时钟，
通过赛事会话公开接口验证测试房、测试赛事、正式赛事和自由赛的身份边界。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from _official_testkit import FakeClock, FakeTransport, instant_sleep, load_fixture
from hangma_bot.adapters.official import auto_match, participant
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


GUIDE_V27 = Path(__file__).parents[3] / "doc/references/official-guide-version-v27.json"
SCOPED_MODES = (RuntimeMode.TEST_ROOM, RuntimeMode.TEST_TOURNAMENT, RuntimeMode.OFFICIAL_TOURNAMENT)
MODES = (*SCOPED_MODES, RuntimeMode.AUTO_MATCH)


def make_session(monkeypatch, mode, *, restore=False):
    """保持生产会话装配；返回可变官方响应脚本以驱动阶段边界。"""
    clock, transport = FakeClock(), FakeTransport()
    is_auto = mode is RuntimeMode.AUTO_MATCH
    room_id = "r_auto_v27" if is_auto else "t_test_room_1"
    detail = load_fixture("tournament_detail.json")
    detail["tournament_id"] = room_id
    if is_auto:
        detail["status"] = "registering"
        detail["config"].update(Kind="auto", M=10, Rounds=8)
        detail["my_games"] = []
    script = {
        "guide": json.loads(GUIDE_V27.read_text(encoding="utf-8")),
        "detail": detail,
        "me": {"user_id": "u_player_a", "tournament_id": "" if is_auto else room_id,
               "active_games": []},
        "match_error": None,
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
            return 200, "{}"
        if path == "/api/match":
            assert is_auto and not restore and method == "POST"
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
        transport_config=TransportConfig(base_url="https://guide-review.invalid", insecure_hosts=frozenset()),
        monotonic_clock=clock.monotonic,
        wall_clock_unix_ms=clock.wall_ms,
        retry_sleep=instant_sleep(clock),
    )
    target = RuntimeTarget(mode=mode, expected_tournament_id="" if is_auto and not restore else room_id,
                           known_guide_version=27)
    return session, target, transport, script


@pytest.mark.parametrize("mode", MODES, ids=lambda mode: mode.value)
async def test_reviewed_v27_initializes_supported_entry(monkeypatch, mode):
    session, target, transport, script = make_session(monkeypatch, mode)
    try:
        result = await session.initialize(target)
        assert isinstance(result, SessionBootstrap), result
        assert result.guide.version == 27
        assert not result.guide.has_unknown_breaking_change
        assert sum(call.path == "/api/match" for call in transport.calls) == (mode is RuntimeMode.AUTO_MATCH)
    finally:
        await session.aclose()


@pytest.mark.parametrize("mode", MODES, ids=lambda mode: mode.value)
@pytest.mark.parametrize("change", ("new_same_version", "rewritten_reviewed_entry"))
async def test_unknown_breaking_stops_before_identity_or_participation(monkeypatch, mode, change):
    session, target, transport, script = make_session(monkeypatch, mode)
    if change == "new_same_version":
        script["guide"]["changes"].append({
            "version": 27, "type": "breaking", "summary": "同版本新增未审查参赛约束",
        })
    else:
        reviewed = next(item for item in script["guide"]["changes"] if item["version"] == 24)
        reviewed["detail"] += "\n同一条目新增未审查的入口限制"
    try:
        result = await session.initialize(target)
        assert isinstance(result, ParticipantTerminal)
        assert result.reason is ParticipantTerminalReason.INCOMPATIBLE_GUIDE
        assert [(call.method, call.path) for call in transport.calls] == [
            ("GET", "/portal/api/guide/version")]
    finally:
        await session.aclose()


@pytest.mark.parametrize("unknown", (False, True))
async def test_v27_stage_boundary_rechecks_before_ready(monkeypatch, unknown):
    session, target, transport, script = make_session(monkeypatch, RuntimeMode.OFFICIAL_TOURNAMENT)
    try:
        boot = await session.initialize(target)
        assert isinstance(boot, SessionBootstrap)
        script["detail"] = load_fixture("tournament_stage_open.json")
        update = await session.next_update()
        assert not isinstance(update, ParticipantTerminal)
        assert update.stage != boot.initial_snapshot.stage
        if unknown:
            script["guide"]["changes"].append({
                "version": 27, "type": "breaking", "summary": "同版本阶段间新增未知约束",
            })
        transport.calls.clear()
        result = await session.ready(update.stage)
        if unknown:
            assert isinstance(result, ParticipantTerminal)
            assert result.reason is ParticipantTerminalReason.INCOMPATIBLE_GUIDE
            assert all(call.method == "GET" for call in transport.calls)
        else:
            assert result.status is OperationStatus.ACCEPTED
            assert sum(call.method == "POST" for call in transport.calls) == 1
    finally:
        await session.aclose()


@pytest.mark.parametrize("mode", MODES, ids=lambda mode: mode.value)
async def test_v27_review_keeps_scoped_and_global_credentials_separate(monkeypatch, mode):
    session, target, transport, script = make_session(monkeypatch, mode)
    script["me"]["tournament_id"] = "t_other" if mode is RuntimeMode.AUTO_MATCH else ""
    try:
        result = await session.initialize(target)
        assert isinstance(result, ParticipantTerminal)
        assert result.reason is ParticipantTerminalReason.TARGET_MISMATCH
        assert all(call.method == "GET" for call in transport.calls)
    finally:
        await session.aclose()


async def test_auto_match_portal_binding_required_is_permanent_and_explained(monkeypatch):
    session, target, transport, script = make_session(monkeypatch, RuntimeMode.AUTO_MATCH)
    error = ForbiddenError(403, "PORTAL_BINDING_REQUIRED", "portal binding required")
    assert error.official_code == "PORTAL_BINDING_REQUIRED"
    script["match_error"] = error
    try:
        result = await session.initialize(target)
        assert isinstance(result, ParticipantTerminal)
        assert result.reason is ParticipantTerminalReason.TARGET_MISMATCH
        assert "PORTAL_BINDING_REQUIRED" in result.detail
        assert "门户「我的 AI 身份」" in result.detail
        assert sum(call.path == "/api/match" for call in transport.calls) == 1
    finally:
        await session.aclose()


async def test_auto_match_v27_restore_does_not_require_unobservable_portal_binding(monkeypatch):
    """/api/me 不提供绑定字段；已有 room_id 恢复只核验房间，不新调 match。"""
    session, target, transport, script = make_session(monkeypatch, RuntimeMode.AUTO_MATCH, restore=True)
    try:
        result = await session.initialize(target)
        assert isinstance(result, SessionBootstrap), result
        assert result.tournament_id == target.expected_tournament_id
        assert all(call.method == "GET" for call in transport.calls)
    finally:
        await session.aclose()
