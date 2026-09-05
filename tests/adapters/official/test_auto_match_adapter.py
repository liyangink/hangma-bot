"""OfficialAutoMatchSession 行为测试（自动匹配入席/恢复/收尾协议）。

覆盖（free-match-start.md §5 的 Fake/夹具验收子集）：
- Token 范围错误、等待幂等（无重复 match）、超时归属恢复、永久容量不符、
  MATCH_BUSY/限流重试、404 NO_ROOM_AVAILABLE、全局其他赛事场次隔离、
  register/ready HTTP=0、finished 后 404 合成 closed、未取终局先 404 停止。
测试全部注入假时钟与脚本化假传输（tests/AGENTS.md），不产生真实等待。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable, Dict, List, Optional

import pytest

from hangma_bot.adapters.official.auto_match import (
    DEFAULT_MATCH_BUSY_WAIT_CAP_SEC,
    DEFAULT_MATCH_MAX_ATTEMPTS,
    DEFAULT_MATCH_MIN_INTERVAL_SEC,
    MIN_MATCH_INTERVAL_SEC,
    QUOTA_MAX_CALLS,
    QUOTA_WINDOW_SEC,
    OfficialAutoMatchSession,
)
from hangma_bot.adapters.official.notify import StreamBudget
from hangma_bot.adapters.official.errors import (
    AuthError,
    ConflictError,
    NotFoundError,
    UncertainTransportError,
)
from hangma_bot.adapters.official.game import OfficialGameSession
from hangma_bot.adapters.official.scheduler import RequestScheduler
from hangma_bot.application.contracts import (
    AuditKind,
    GameFinished,
    ObservedActionWindow,
    ParticipantTerminal,
    ParticipantTerminalReason,
    RuntimeMode,
    RuntimeTarget,
    SessionBootstrap,
    StageIdentity,
    TournamentStatus,
)

from _official_testkit import (  # noqa: F401
    FakeClock,
    FakeTransport,
    instant_sleep,
    load_fixture,
)

GUIDE_V15 = {"version": 15, "updated_at": "2026-09-05", "changes": []}


def _guide_doc() -> Dict[str, Any]:
    return dict(GUIDE_V15)


def _me_doc(*, tournament_id: str = "", active_games=()) -> Dict[str, Any]:
    """/api/me 响应：active_games 项为对象形态（官方原样）。"""

    return {
        "user_id": "u_auto_player",
        "tournament_id": tournament_id,
        "active_games": [{"game_id": g} for g in active_games],
    }


def _match_doc(room_id: str = "r_auto_1", round_no: int = 3) -> Dict[str, Any]:
    return {"room_id": room_id, "round_no": round_no, "config": {"M": 10, "Rounds": 8}}


def _room_doc(
    *,
    status: str = "registering",
    kind: Any = "auto",
    my_games=(),
    ranking=(),
    detail_room: str = "r_auto_1",
    m: int = 10,
    rounds: int = 8,
) -> Dict[str, Any]:
    """房间详情响应（自动房形态，2026-09-06 活场实测）：配置内嵌 config 块
    （与 rules 响应同构），kind 位于 config.Kind；自动房无 /rules 端点。"""

    config: Dict[str, Any] = {
        "M": m,
        "Rounds": rounds,
        "BaseScore": 100,
        "YouCaiBiKao": False,
        "PengTimeoutSec": 1,
        "ChiTimeoutSec": 1,
        "DiscardTimeoutSec": 3,
    }
    if kind is not None:
        config["Kind"] = kind
    return {
        "tournament_id": detail_room,
        "status": status,
        "config": config,
        "my_games": list(my_games),
        "ranking": list(ranking),
    }


def _target(*, room_id: str = "", guide: int = 15) -> RuntimeTarget:
    return RuntimeTarget(
        mode=RuntimeMode.AUTO_MATCH,
        expected_tournament_id=room_id,
        known_guide_version=guide,
    )


def make_auto_session(
    *,
    clock: FakeClock,
    transport: FakeTransport,
    audit=None,
    scheduler: Optional[RequestScheduler] = None,
    **kwargs: Any,
) -> OfficialAutoMatchSession:
    """组装会话：假传输注入沿用 testkit 的唯一私有态注入点。"""

    from hangma_bot.adapters.official.transport import TransportConfig

    if scheduler is None:
        scheduler = RequestScheduler(
            clock=clock.monotonic,
            sleep=instant_sleep(clock),
            poll_interval=0.0,
        )
    session = OfficialAutoMatchSession(
        token="fake-token-do-not-log",
        transport_config=TransportConfig(
            base_url="https://10.240.169.190:18080",
            insecure_hosts=frozenset({"10.240.169.190"}),
        ),
        monotonic_clock=clock.monotonic,
        wall_clock_unix_ms=clock.wall_ms,
        audit=audit,
        audit_context=lambda: _official_testkit_audit_context(),
        scheduler=scheduler,
        retry_sleep=instant_sleep(clock),
        **kwargs,
    )
    session._transport = transport  # 测试注入假传输
    return session


def _official_testkit_audit_context():
    from hangma_bot.application.contracts import AuditContext

    return AuditContext(run_id="run-test", tournament_id="r_auto_1", participant_id="u_auto_player")


def discovery_handler(
    transport: FakeTransport,
    *,
    me_active=(),
    match_status: int = 200,
    match_text: Optional[str] = None,
    match_exc: Optional[BaseException] = None,
    room_status: str = "registering",
    match_body: Optional[Dict[str, Any]] = None,
):
    """标准发现模式 handler：guide → me → match → 房间详情（含内嵌 config）。

    自动房无 /rules 端点（活场实测）：请求 /rules 一律 AssertionError。
    记录调用供断言；未知路径抛 AssertionError。
    """

    counts = {"match": 0}
    match_doc = match_body if match_body is not None else _match_doc()
    doc = {
        "counts": counts,
        "call_paths": [],
    }

    def handler(*, method: str, path: str, json_body=None, params=None, long_poll=False):
        doc["call_paths"].append((method, path))
        if path == "/portal/api/guide/version":
            return 200, json.dumps(_guide_doc())
        if path == "/api/me":
            return 200, json.dumps(_me_doc(active_games=me_active))
        if path == "/api/match":
            counts["match"] += 1
            if match_exc is not None:
                raise match_exc
            if match_status != 200:
                return match_status, match_text or "{}"
            return 200, json.dumps(match_doc)
        if path == "/api/tournaments/r_auto_1":
            return 200, json.dumps(_room_doc(status=room_status))
        raise AssertionError("unexpected " + method + " " + path)

    transport.handler = handler
    return doc


def restore_handler(
    transport: FakeTransport,
    *,
    me_active=(),
    room_status: str = "registering",
    room_kind: Any = "auto",
    my_games=(),
    detail_room: Optional[str] = None,
):
    """标准恢复模式 handler（不调用 match）：guide → me → 房间详情（含内嵌 config）。"""

    call_paths: List[str] = []
    room = detail_room if detail_room is not None else "r_auto_1"

    def handler(*, method: str, path: str, json_body=None, params=None, long_poll=False):
        call_paths.append(path)
        if path == "/portal/api/guide/version":
            return 200, json.dumps(_guide_doc())
        if path == "/api/me":
            return 200, json.dumps(_me_doc(active_games=me_active))
        if path == "/api/tournaments/r_auto_1":
            return 200, json.dumps(
                _room_doc(status=room_status, kind=room_kind, my_games=my_games, detail_room=room)
            )
        raise AssertionError("unexpected " + method + " " + path)

    transport.handler = handler
    return call_paths


def lifecycle_events(records) -> List[str]:
    out = []
    for record in records:
        if record.kind is AuditKind.LIFECYCLE_CHANGED:
            payload = record.payload
            if payload.get("area") == "auto_match" and payload.get("event"):
                out.append(payload["event"])
    return out


async def initialize_once(session: OfficialAutoMatchSession, target: RuntimeTarget):
    return await asyncio.wait_for(session.initialize(target), timeout=3)


@pytest.mark.asyncio
async def test_initialize_discovery_success_declares_caps(transport, clock, audit) -> None:
    """空目标 + 无活动场次：POST /api/match（带声明上限）→ 已核实 room 引导。"""

    doc = discovery_handler(transport, room_status="registering")
    session = make_auto_session(
        clock=clock,
        transport=transport,
        audit=audit,
        declared_max_games=10,
        declared_rounds=8,
    )
    outcome = await initialize_once(session, _target())
    assert not isinstance(outcome, ParticipantTerminal)
    assert isinstance(outcome, SessionBootstrap)
    assert outcome.tournament_id == "r_auto_1"
    assert outcome.participant_id == "u_auto_player"
    assert outcome.config.max_games == 10
    assert outcome.config.rounds_per_game == 8
    assert outcome.initial_snapshot.status is TournamentStatus.REGISTERING
    assert doc["counts"]["match"] == 1
    match_calls = [c for c in doc["call_paths"] if c[1] == "/api/match"]
    assert match_calls and match_calls[0][0] == "POST"
    events = lifecycle_events(audit.records)
    assert events[:2] == ["matching_started", "matched"]
    # 声明上限出现在请求体。
    recorded = [c for c in transport.calls if c.path == "/api/match"]
    assert recorded[0].json_body == {"M": 10, "Rounds": 8}
    # 无 register/ready 的 HTTP 调用。
    assert not any("register" in c.path or "ready" in c.path for c in transport.calls)


@pytest.mark.asyncio
async def test_auto_room_has_no_rules_endpoint_config_from_detail(transport, clock, audit) -> None:
    """活场回归（2026-09-06）：自动房没有 /rules 端点（404 NOT_FOUND bad path），
    配置取自房间详情内嵌 config（与 rules 响应同构），initialize 全程不请求
    /rules；kind 位于 config.Kind（真实形态）。"""

    rules_calls: List[str] = []

    def handler(*, method: str, path: str, json_body=None, params=None, long_poll=False):
        if path == "/portal/api/guide/version":
            return 200, json.dumps(_guide_doc())
        if path == "/api/me":
            return 200, json.dumps(_me_doc())
        if path == "/api/match":
            return 200, json.dumps(_match_doc())
        if path == "/api/tournaments/r_auto_1":
            return 200, json.dumps(_room_doc(status="running", kind="auto"))
        if "/rules" in path:
            rules_calls.append(path)
            raise NotFoundError(404, None, '{"code":"NOT_FOUND","message":"bad path"}')
        raise AssertionError("unexpected " + method + " " + path)

    transport.handler = handler
    session = make_auto_session(clock=clock, transport=transport, audit=audit)
    outcome = await initialize_once(session, _target())
    assert isinstance(outcome, SessionBootstrap)
    assert outcome.config.max_games == 10
    assert outcome.config.rounds_per_game == 8
    assert outcome.config.timing.discard_timeout_sec == 3  # 时限来自详情内嵌 config
    assert outcome.config.timing.peng_timeout_sec == 1
    assert outcome.config.rules.base_score == 100
    assert rules_calls == []  # 从未请求 /rules


@pytest.mark.asyncio
async def test_initialize_discovery_omits_body_when_unlimited(transport, clock, audit) -> None:
    """声明上限为 0（不声明）：match 请求不带 body（缺省=不限，不会 404）。"""

    discovery_handler(transport)
    session = make_auto_session(
        clock=clock, transport=transport, audit=audit
    )
    outcome = await initialize_once(session, _target())
    assert isinstance(outcome, SessionBootstrap)
    recorded = [c for c in transport.calls if c.path == "/api/match"]
    assert recorded and recorded[0].json_body is None


@pytest.mark.asyncio
async def test_initialize_restore_mode_never_calls_match(transport, clock, audit) -> None:
    """非空目标 = 只恢复已知自动房：全程零 match POST，直接核验房间并引导。"""

    call_paths = restore_handler(
        transport, me_active=("g1",), room_status="running", my_games=("g1",)
    )
    session = make_auto_session(clock=clock, transport=transport, audit=audit)
    outcome = await initialize_once(session, _target(room_id="r_auto_1"))
    assert isinstance(outcome, SessionBootstrap)
    assert outcome.tournament_id == "r_auto_1"
    assert outcome.initial_snapshot.status is TournamentStatus.RUNNING
    assert "/api/match" not in call_paths
    assert not any("register" in p or "ready" in p for p in call_paths)


@pytest.mark.asyncio
async def test_initialize_refuses_wrong_mode(transport, clock) -> None:
    """模式守卫：本会话只服务 AUTO_MATCH，其他模式直接拒绝。"""

    session = make_auto_session(clock=clock, transport=transport)
    with pytest.raises(ValueError):
        await session.initialize(
            RuntimeTarget(
                mode=RuntimeMode.OFFICIAL_TOURNAMENT,
                expected_tournament_id="t1",
                known_guide_version=15,
            )
        )


@pytest.mark.asyncio
async def test_initialize_single_call_guard(transport, clock) -> None:
    """同一会话实例只允许一次 initialize（副作用入口防重入）。"""

    discovery_handler(transport)
    session = make_auto_session(clock=clock, transport=transport)
    outcome = await initialize_once(session, _target())
    assert isinstance(outcome, SessionBootstrap)
    with pytest.raises(RuntimeError):
        await session.initialize(_target())


@pytest.mark.asyncio
async def test_register_ready_refused_locally_with_zero_http(transport, clock, audit) -> None:
    """register/ready 本地拒绝（RuntimeError）且 HTTP 调用数为 0。"""

    discovery_handler(transport)
    session = make_auto_session(clock=clock, transport=transport, audit=audit)
    outcome = await initialize_once(session, _target())
    assert isinstance(outcome, SessionBootstrap)
    with pytest.raises(RuntimeError):
        await session.register()
    with pytest.raises(RuntimeError):
        await session.ready(StageIdentity(stage_no=None, observed_revision=1))
    assert not any("register" in c.path or "ready" in c.path for c in transport.calls)


@pytest.mark.asyncio
async def test_initialize_scoped_token_rejected_without_match(transport, clock, audit) -> None:
    """报名（scoped）Token 进入自动匹配入口：TARGET_MISMATCH，零 match 调用。"""

    doc = discovery_handler(transport)
    # handler 里的 /api/me 固定全局形态：需要按场景覆写 me。
    def handler(*, method: str, path: str, json_body=None, params=None, long_poll=False):
        if path == "/portal/api/guide/version":
            return 200, json.dumps(_guide_doc())
        if path == "/api/me":
            return 200, json.dumps(_me_doc(tournament_id="t_scoped"))
        raise AssertionError("unexpected " + method + " " + path)

    transport.handler = handler
    session = make_auto_session(clock=clock, transport=transport, audit=audit)
    outcome = await initialize_once(session, _target())
    assert isinstance(outcome, ParticipantTerminal)
    assert outcome.reason is ParticipantTerminalReason.TARGET_MISMATCH
    assert doc["counts"]["match"] == 0
    assert not any(c.path == "/api/match" for c in transport.calls)


@pytest.mark.asyncio
async def test_initialize_discovery_with_active_games_stops(transport, clock, audit) -> None:
    """空目标但全局 Token 已有活动场次：缺归属证据 → MATCHING_UNAVAILABLE，
    禁止再 match 占第二间房。"""

    doc = discovery_handler(transport, me_active=("g_unknown",))
    session = make_auto_session(clock=clock, transport=transport, audit=audit)
    outcome = await initialize_once(session, _target())
    assert isinstance(outcome, ParticipantTerminal)
    assert outcome.reason is ParticipantTerminalReason.MATCHING_UNAVAILABLE
    assert doc["counts"]["match"] == 0


@pytest.mark.asyncio
async def test_declared_caps_below_server_default_rejected_before_post(
    transport, clock, audit
) -> None:
    """声明上限低于服务默认（M=10/Rounds=8）：永久容量不符，POST 数为 0。"""

    doc = discovery_handler(transport)
    session = make_auto_session(
        clock=clock,
        transport=transport,
        audit=audit,
        declared_max_games=2,
        declared_rounds=8,
    )
    outcome = await initialize_once(session, _target())
    assert isinstance(outcome, ParticipantTerminal)
    assert outcome.reason is ParticipantTerminalReason.CAPACITY_LIMIT
    assert doc["counts"]["match"] == 0


@pytest.mark.asyncio
async def test_match_busy_retries_then_succeeds(transport, clock, audit) -> None:
    """409 MATCH_BUSY：有界等待后重试同一次匹配，成功后正常引导。"""

    busy = ConflictError(409, None, '{"code":"MATCH_BUSY","message":"在途自动房满"}')
    state = {"busy_seen": False}

    def handler(*, method: str, path: str, json_body=None, params=None, long_poll=False):
        if path == "/portal/api/guide/version":
            return 200, json.dumps(_guide_doc())
        if path == "/api/me":
            return 200, json.dumps(_me_doc())
        if path == "/api/match":
            if not state["busy_seen"]:
                state["busy_seen"] = True
                raise busy
            return 200, json.dumps(_match_doc())
        if path == "/api/tournaments/r_auto_1":
            return 200, json.dumps(_room_doc())
        raise AssertionError("unexpected " + method + " " + path)

    transport.handler = handler
    session = make_auto_session(
        clock=clock, transport=transport, audit=audit
    )
    outcome = await initialize_once(session, _target())
    assert isinstance(outcome, SessionBootstrap)
    match_calls = [c for c in transport.calls if c.path == "/api/match"]
    assert len(match_calls) == 2
    recoveries = [
        r
        for r in audit.records
        if r.kind is AuditKind.PROTOCOL_RECOVERED and r.payload.get("official_code") == "MATCH_BUSY"
    ]
    assert recoveries and recoveries[0].payload["attempt_no"] == 1


@pytest.mark.asyncio
async def test_match_busy_exhausts_attempts(transport, clock, audit) -> None:
    """MATCH_BUSY 持续：达到尝试上限后 MATCHING_UNAVAILABLE，不再无限重试。"""

    def handler(*, method: str, path: str, json_body=None, params=None, long_poll=False):
        if path == "/portal/api/guide/version":
            return 200, json.dumps(_guide_doc())
        if path == "/api/me":
            return 200, json.dumps(_me_doc())
        if path == "/api/match":
            raise ConflictError(409, None, '{"code":"MATCH_BUSY","message":"busy"}')
        raise AssertionError("unexpected " + method + " " + path)

    transport.handler = handler
    session = make_auto_session(
        clock=clock,
        transport=transport,
        audit=audit,
        match_max_attempts=3,
    )
    outcome = await initialize_once(session, _target())
    assert isinstance(outcome, ParticipantTerminal)
    assert outcome.reason is ParticipantTerminalReason.MATCHING_UNAVAILABLE
    assert len([c for c in transport.calls if c.path == "/api/match"]) == 3


@pytest.mark.asyncio
async def test_match_limit_reached_capacity_terminal(transport, clock, audit) -> None:
    """409 MATCH_LIMIT_REACHED：停止新增入席（CAPACITY_LIMIT），不重试。"""

    def handler(*, method: str, path: str, json_body=None, params=None, long_poll=False):
        if path == "/portal/api/guide/version":
            return 200, json.dumps(_guide_doc())
        if path == "/api/me":
            return 200, json.dumps(_me_doc())
        if path == "/api/match":
            raise ConflictError(409, "MATCH_LIMIT_REACHED", "达到同时 16 场上限")
        raise AssertionError("unexpected " + method + " " + path)

    transport.handler = handler
    session = make_auto_session(
        clock=clock, transport=transport, audit=audit
    )
    outcome = await initialize_once(session, _target())
    assert isinstance(outcome, ParticipantTerminal)
    assert outcome.reason is ParticipantTerminalReason.CAPACITY_LIMIT
    assert len([c for c in transport.calls if c.path == "/api/match"]) == 1


@pytest.mark.asyncio
async def test_match_no_room_transient_retries_then_stops(transport, clock, audit) -> None:
    """404 NO_ROOM_AVAILABLE（瞬态建房后入席失败）：有界重试后按证据不足停止。"""

    def handler(*, method: str, path: str, json_body=None, params=None, long_poll=False):
        if path == "/portal/api/guide/version":
            return 200, json.dumps(_guide_doc())
        if path == "/api/me":
            return 200, json.dumps(_me_doc())
        if path == "/api/match":
            raise NotFoundError(404, None, '{"code":"NO_ROOM_AVAILABLE","message":"瞬态"}')
        raise AssertionError("unexpected " + method + " " + path)

    transport.handler = handler
    session = make_auto_session(
        clock=clock,
        transport=transport,
        audit=audit,
        match_max_attempts=2,
    )
    outcome = await initialize_once(session, _target())
    assert isinstance(outcome, ParticipantTerminal)
    assert outcome.reason is ParticipantTerminalReason.MATCHING_UNAVAILABLE
    assert len([c for c in transport.calls if c.path == "/api/match"]) == 2


@pytest.mark.asyncio
async def test_match_uncertain_stops_without_blind_republish(transport, clock, audit) -> None:
    """match POST 结果不确定（超时）：核验身份后 MATCHING_UNAVAILABLE，不重发。"""

    state = {"me_calls": 0}

    def handler(*, method: str, path: str, json_body=None, params=None, long_poll=False):
        if path == "/portal/api/guide/version":
            return 200, json.dumps(_guide_doc())
        if path == "/api/me":
            state["me_calls"] += 1
            return 200, json.dumps(_me_doc())
        if path == "/api/match":
            raise UncertainTransportError("timeout:ReadTimeout")
        raise AssertionError("unexpected " + method + " " + path)

    transport.handler = handler
    session = make_auto_session(
        clock=clock, transport=transport, audit=audit
    )
    outcome = await initialize_once(session, _target())
    assert isinstance(outcome, ParticipantTerminal)
    assert outcome.reason is ParticipantTerminalReason.MATCHING_UNAVAILABLE
    assert len([c for c in transport.calls if c.path == "/api/match"]) == 1
    assert state["me_calls"] >= 2  # 初始化身份 + 不确定后核验
    assert any(
        r.payload.get("reason") == "match_uncertain_evidence"
        for r in audit.records
        if r.kind is AuditKind.PROTOCOL_RECOVERED
    )


@pytest.mark.asyncio
async def test_match_401_authentication_terminal(transport, clock, audit) -> None:
    """match 401：AUTHENTICATION_FAILED，零重试（不轮换凭证）。"""

    def handler(*, method: str, path: str, json_body=None, params=None, long_poll=False):
        if path == "/portal/api/guide/version":
            return 200, json.dumps(_guide_doc())
        if path == "/api/me":
            return 200, json.dumps(_me_doc())
        if path == "/api/match":
            raise AuthError(401, "UNAUTHORIZED", "unauthorized")
        raise AssertionError("unexpected " + method + " " + path)

    transport.handler = handler
    session = make_auto_session(
        clock=clock, transport=transport, audit=audit
    )
    outcome = await initialize_once(session, _target())
    assert isinstance(outcome, ParticipantTerminal)
    assert outcome.reason is ParticipantTerminalReason.AUTHENTICATION_FAILED
    assert len([c for c in transport.calls if c.path == "/api/match"]) == 1


@pytest.mark.asyncio
async def test_initialize_guide_breaking_stops_before_match(transport, clock, audit) -> None:
    """未审查 breaking 指南：INCOMPATIBLE_GUIDE，match POST 数为 0。"""

    def handler(*, method: str, path: str, json_body=None, params=None, long_poll=False):
        if path == "/portal/api/guide/version":
            return 200, json.dumps(
                {"version": 16, "updated_at": "2026-09-06", "changes": [
                    {"version": 16, "date": "2026-09-06", "type": "breaking", "summary": "x"}
                ]}
            )
        raise AssertionError("unexpected " + method + " " + path)

    transport.handler = handler
    session = make_auto_session(clock=clock, transport=transport, audit=audit)
    outcome = await initialize_once(session, _target())
    assert isinstance(outcome, ParticipantTerminal)
    assert outcome.reason is ParticipantTerminalReason.INCOMPATIBLE_GUIDE
    assert not any(c.path == "/api/match" for c in transport.calls)


@pytest.mark.asyncio
async def test_initialize_rejects_non_auto_room(transport, clock, audit) -> None:
    """房间 kind 明确不是 auto：TARGET_MISMATCH（不能用自动房生命周期驱动）。"""

    restore_handler(transport, room_status="running", room_kind="tournament")
    session = make_auto_session(clock=clock, transport=transport, audit=audit)
    outcome = await initialize_once(session, _target(room_id="r_auto_1"))
    assert isinstance(outcome, ParticipantTerminal)
    assert outcome.reason is ParticipantTerminalReason.TARGET_MISMATCH


@pytest.mark.asyncio
async def test_initialize_detail_attribution_mismatch(transport, clock, audit) -> None:
    """详情归属与目标房不一致：TARGET_MISMATCH（错误配置会污染时限预算）。

    自动房无 /rules 端点（活场实测 404 bad path），归属核对基于详情内嵌
    tournament_id + config（2026-09-06 修正）。"""

    restore_handler(transport, detail_room="r_other")
    session = make_auto_session(clock=clock, transport=transport, audit=audit)
    outcome = await initialize_once(session, _target(room_id="r_auto_1"))
    assert isinstance(outcome, ParticipantTerminal)
    assert outcome.reason is ParticipantTerminalReason.TARGET_MISMATCH


@pytest.mark.asyncio
async def test_initialize_restore_missing_room_404(transport, clock, audit) -> None:
    """恢复目标 404（房间已关闭/不存在）：恢复证据不足，不调用 match。"""

    def handler(*, method: str, path: str, json_body=None, params=None, long_poll=False):
        if path == "/portal/api/guide/version":
            return 200, json.dumps(_guide_doc())
        if path == "/api/me":
            return 200, json.dumps(_me_doc())
        if path.startswith("/api/tournaments/r_auto_1"):
            raise NotFoundError(404, "TOURNAMENT_NOT_FOUND", "房间不存在")
        raise AssertionError("unexpected " + method + " " + path)

    transport.handler = handler
    session = make_auto_session(clock=clock, transport=transport, audit=audit)
    outcome = await initialize_once(session, _target(room_id="r_auto_1"))
    assert isinstance(outcome, ParticipantTerminal)
    assert outcome.reason is ParticipantTerminalReason.MATCHING_UNAVAILABLE
    assert not any(c.path == "/api/match" for c in transport.calls)


@pytest.mark.asyncio
async def test_next_update_active_intersection_and_finished(transport, clock, audit) -> None:
    """next_update：active_games 只取与房间 my_games 的交集；finished 是普通
    变化快照（终态判定在 application）。"""

    calls: List[str] = []
    my_games = ("g1", "g0_done")
    states = {"me_active": ["g1", "g_foreign_other_room"], "room_status": "running"}

    def handler(*, method: str, path: str, json_body=None, params=None, long_poll=False):
        calls.append(path)
        if path == "/portal/api/guide/version":
            return 200, json.dumps(_guide_doc())
        if path == "/api/me":
            return 200, json.dumps(_me_doc(active_games=states["me_active"]))
        if path == "/api/tournaments/r_auto_1":
            return 200, json.dumps(_room_doc(status=states["room_status"], my_games=my_games))
        raise AssertionError("unexpected " + method + " " + path)

    transport.handler = handler
    session = make_auto_session(clock=clock, transport=transport, audit=audit)
    outcome = await initialize_once(session, _target(room_id="r_auto_1"))
    assert isinstance(outcome, SessionBootstrap)
    assert outcome.initial_snapshot.active_games == ("g1",)  # g_foreign 被隔离
    assert "g_foreign_other_room" not in outcome.initial_snapshot.active_games
    assert any(
        r.payload.get("reason") == "foreign_active_games_ignored"
        for r in audit.records
        if r.kind is AuditKind.PROTOCOL_RECOVERED
    )

    # 房间推进到 finished：普通快照返回，不在此终态化。
    states["room_status"] = "finished"
    snapshot = await asyncio.wait_for(session.next_update(), timeout=3)
    assert not isinstance(snapshot, ParticipantTerminal)
    assert snapshot.status is TournamentStatus.FINISHED
    assert snapshot.my_games == ("g1", "g0_done")


@pytest.mark.asyncio
async def test_next_update_404_after_finished_synthesizes_closed(transport, clock, audit) -> None:
    """finished 后房间 404（官方约 60s 关停）：合成 closed 变化快照按证据收尾。"""

    states = {"room_visible": True, "room_status": "running"}
    calls: List[str] = []

    def handler(*, method: str, path: str, json_body=None, params=None, long_poll=False):
        calls.append(path)
        if path == "/portal/api/guide/version":
            return 200, json.dumps(_guide_doc())
        if path == "/api/me":
            return 200, json.dumps(_me_doc())
        if path == "/api/tournaments/r_auto_1":
            if not states["room_visible"]:
                raise NotFoundError(404, "TOURNAMENT_NOT_FOUND", "房间已关闭")
            return 200, json.dumps(_room_doc(status=states["room_status"], my_games=("g1",)))
        raise AssertionError("unexpected " + method + " " + path)

    transport.handler = handler
    session = make_auto_session(clock=clock, transport=transport, audit=audit)
    outcome = await initialize_once(session, _target(room_id="r_auto_1"))
    assert isinstance(outcome, SessionBootstrap)
    assert outcome.initial_snapshot.status is TournamentStatus.RUNNING
    states["room_status"] = "finished"
    finished = await asyncio.wait_for(session.next_update(), timeout=3)
    assert finished.status is TournamentStatus.FINISHED
    states["room_visible"] = False
    closed = await asyncio.wait_for(session.next_update(), timeout=3)
    assert not isinstance(closed, ParticipantTerminal)
    assert closed.status is TournamentStatus.CLOSED


@pytest.mark.asyncio
async def test_next_update_404_without_finished_evidence_stops(transport, clock, audit) -> None:
    """无 finished 证据的房间 404：不能证明正常完赛，MATCHING_UNAVAILABLE。"""

    states = {"room_visible": True}

    def handler(*, method: str, path: str, json_body=None, params=None, long_poll=False):
        if path == "/portal/api/guide/version":
            return 200, json.dumps(_guide_doc())
        if path == "/api/me":
            return 200, json.dumps(_me_doc())
        if path == "/api/tournaments/r_auto_1":
            if not states["room_visible"]:
                raise NotFoundError(404, "TOURNAMENT_NOT_FOUND", "gone")
            return 200, json.dumps(_room_doc(status="running", my_games=("g1",)))
        raise AssertionError("unexpected " + method + " " + path)

    transport.handler = handler
    session = make_auto_session(clock=clock, transport=transport, audit=audit)
    outcome = await initialize_once(session, _target(room_id="r_auto_1"))
    assert isinstance(outcome, SessionBootstrap)
    states["room_visible"] = False
    item = await asyncio.wait_for(session.next_update(), timeout=3)
    assert isinstance(item, ParticipantTerminal)
    assert item.reason is ParticipantTerminalReason.MATCHING_UNAVAILABLE


@pytest.mark.asyncio
async def test_next_update_token_drift_terminal(transport, clock, audit) -> None:
    """运行中 Token 被改绑为报名 Token：TARGET_MISMATCH，不再轮询本房。"""

    state = {"drift": False}

    def handler(*, method: str, path: str, json_body=None, params=None, long_poll=False):
        if path == "/portal/api/guide/version":
            return 200, json.dumps(_guide_doc())
        if path == "/api/me":
            if state["drift"]:
                return 200, json.dumps(_me_doc(tournament_id="t_other"))
            return 200, json.dumps(_me_doc())
        if path == "/api/tournaments/r_auto_1":
            return 200, json.dumps(_room_doc(status="running", my_games=("g1",)))
        raise AssertionError("unexpected " + method + " " + path)

    transport.handler = handler
    session = make_auto_session(clock=clock, transport=transport, audit=audit)
    outcome = await initialize_once(session, _target(room_id="r_auto_1"))
    assert isinstance(outcome, SessionBootstrap)
    state["drift"] = True
    item = await asyncio.wait_for(session.next_update(), timeout=3)
    assert isinstance(item, ParticipantTerminal)
    assert item.reason is ParticipantTerminalReason.TARGET_MISMATCH


@pytest.mark.asyncio
async def test_match_quota_spacing_min_interval(transport, clock, audit) -> None:
    """每分钟配额：同一会话内两次 match POST 的单调间隔 ≥ 配置最小间隔。"""

    calls: List[float] = []
    state = {"busy_seen": False}

    def handler(*, method: str, path: str, json_body=None, params=None, long_poll=False):
        if path == "/portal/api/guide/version":
            return 200, json.dumps(_guide_doc())
        if path == "/api/me":
            return 200, json.dumps(_me_doc())
        if path == "/api/match":
            calls.append(clock.monotonic())
            if not state["busy_seen"]:
                state["busy_seen"] = True
                raise ConflictError(409, None, '{"code":"MATCH_BUSY","message":"busy"}')
            return 200, json.dumps(_match_doc())
        if path == "/api/tournaments/r_auto_1":
            return 200, json.dumps(_room_doc())
        raise AssertionError("unexpected " + method + " " + path)

    transport.handler = handler
    session = make_auto_session(
        clock=clock,
        transport=transport,
        audit=audit,
        match_min_interval_sec=DEFAULT_MATCH_MIN_INTERVAL_SEC,
        match_busy_wait_cap_sec=DEFAULT_MATCH_BUSY_WAIT_CAP_SEC,
        match_max_attempts=DEFAULT_MATCH_MAX_ATTEMPTS,
    )
    outcome = await initialize_once(session, _target())
    assert isinstance(outcome, SessionBootstrap)
    assert len(calls) == 2
    assert calls[1] - calls[0] >= DEFAULT_MATCH_MIN_INTERVAL_SEC - 1e-9


@pytest.mark.asyncio
async def test_open_game_returns_shared_game_session(transport, clock, audit) -> None:
    """open_game 复用本 Token 传输/调度器创建官方场次会话（路由正确）。"""

    def handler(*, method: str, path: str, json_body=None, params=None, long_poll=False):
        if path == "/portal/api/guide/version":
            return 200, json.dumps(_guide_doc())
        if path == "/api/me":
            return 200, json.dumps(_me_doc())
        if path == "/api/tournaments/r_auto_1":
            return 200, json.dumps(_room_doc(status="running", my_games=("g1",)))
        if path == "/api/games/g1/state":
            return 200, json.dumps({"pending": True})
        raise AssertionError("unexpected " + method + " " + path)

    transport.handler = handler
    session = make_auto_session(clock=clock, transport=transport, audit=audit)
    outcome = await initialize_once(session, _target(room_id="r_auto_1"))
    assert isinstance(outcome, SessionBootstrap)
    game = session.open_game("g1")
    assert isinstance(game, OfficialGameSession)
    assert game.game_id == "g1"
    assert not game.closed
    # 同一场重复 open_game 返回同一会话（缓存）；closed 后重建。
    assert session.open_game("g1") is game
    await game.aclose("test")
    assert session.open_game("g1") is not game
    await session.aclose()


@pytest.mark.asyncio
async def test_match_raw_recorded_when_builder_registered(transport, clock, audit) -> None:
    """match 完整响应原文落 RAW（source=match_response，payload v1）。

    依赖审计线提供的 builder 注册（parallel-v1 §3.3）：注册未合入时跳过
    （适配器弹性跳过发射，不写第二套 raw 代码，见 handoff §5.6）。
    """

    try:
        from hangma_bot.adapters.recording import build_match_response_payload  # noqa: F401
    except Exception:  # noqa: BLE001 - 审计线注册未合入：本用例跳过
        pytest.skip("审计线 match_response raw builder 尚未注册")
    discovery_handler(transport, room_status="registering")
    session = make_auto_session(
        clock=clock, transport=transport, audit=audit
    )
    outcome = await initialize_once(session, _target())
    assert isinstance(outcome, SessionBootstrap)
    match_raw = [
        r
        for r in audit.records
        if r.kind is AuditKind.RAW_PROTOCOL_STATE
        and r.payload.get("source") == "match_response"
    ]
    assert len(match_raw) == 1
    assert match_raw[0].payload["http_status"] == 200
    assert match_raw[0].payload["attempt"] == 1
    assert match_raw[0].payload["payload_schema_version"] == 1
    assert '"room_id"' in match_raw[0].payload["raw"]


@pytest.mark.asyncio
async def test_open_game_session_gap_rebuild_and_finished(transport, clock, audit) -> None:
    """自动房 open_game 复用场次安全路径：seq 缺口→seq=0 权威重建、finished
    返回终局（乱序/缺口与终局收尾在自动房同路径的行为回归锚点）。"""

    def init_handler(*, method: str, path: str, json_body=None, params=None, long_poll=False):
        if path == "/portal/api/guide/version":
            return 200, json.dumps(_guide_doc())
        if path == "/api/me":
            return 200, json.dumps(_me_doc())
        if path == "/api/tournaments/r_auto_1":
            return 200, json.dumps(_room_doc(status="running", my_games=("g1",)))
        raise AssertionError("unexpected " + method + " " + path)

    transport.handler = init_handler
    session = make_auto_session(clock=clock, transport=transport, audit=audit)
    outcome = await initialize_once(session, _target(room_id="r_auto_1"))
    assert isinstance(outcome, SessionBootstrap)

    base = load_fixture("state_response_snapshot_draw.json")
    base["snapshot"]["turn"] = 0  # 首快照无窗口（他人回合）
    game_queue = [
        (200, json.dumps(base)),
        (200, json.dumps(load_fixture("state_response_gap.json"))),
        (200, json.dumps(load_fixture("state_response_snapshot_draw.json"))),
        (200, json.dumps(load_fixture("state_response_finished.json"))),
    ]

    def game_handler(*, method: str, path: str, json_body=None, params=None, long_poll=False):
        if path.startswith("/api/games/g1/state"):
            return game_queue.pop(0)
        raise AssertionError("unexpected game call " + method + " " + path)

    transport.handler = game_handler
    game = session.open_game("g1")
    assert isinstance(game, OfficialGameSession)
    item = await asyncio.wait_for(game.next_item(), timeout=3)
    assert isinstance(item, ObservedActionWindow)
    # 缺口事件后必须经过 seq=0 权威重建（与既有场次回归同路径）。
    rebuild_calls = [c for c in transport.calls if c.params == {"seq": 0}]
    assert rebuild_calls and rebuild_calls[-1].path == "/api/games/g1/state"
    final = await asyncio.wait_for(game.next_item(), timeout=3)
    assert isinstance(final, GameFinished)
    assert final.game_id == "g1"
    assert final.final_scores == (34, 12, -6, -40)  # 座位 0—3
    assert final.authoritative_seq == 210
    await game.aclose("test")
    await session.aclose()


@pytest.mark.asyncio
async def test_vector_auto_resume_known_room(transport, clock, audit) -> None:
    """contract-vectors behaviour_cases auto-resume-known-room：
    POST match=0 且 register/ready HTTP=0（恢复已知房只核验、不重新入席）。"""

    call_paths = restore_handler(transport, room_status="running", my_games=("g1",))
    session = make_auto_session(clock=clock, transport=transport, audit=audit)
    outcome = await initialize_once(session, _target(room_id="r_auto_1"))
    assert isinstance(outcome, SessionBootstrap)
    assert outcome.tournament_id == "r_auto_1"
    with pytest.raises(RuntimeError):
        await session.register()
    with pytest.raises(RuntimeError):
        await session.ready(StageIdentity(stage_no=None, observed_revision=1))
    assert "/api/match" not in call_paths
    assert not any("register" in p or "ready" in p for p in call_paths)
    await session.aclose()


@pytest.mark.asyncio
async def test_vector_auto_404_without_finish_evidence(transport, clock, audit) -> None:
    """contract-vectors behaviour_cases auto-404-without-finish-evidence：
    结果部分/未知——停止并明示缺失；绝不记零分或 complete（无 GAME_FINISHED、
    无 finished 事件）。"""

    states = {"room_visible": True}

    def handler(*, method: str, path: str, json_body=None, params=None, long_poll=False):
        if path == "/portal/api/guide/version":
            return 200, json.dumps(_guide_doc())
        if path == "/api/me":
            return 200, json.dumps(_me_doc())
        if path == "/api/tournaments/r_auto_1":
            if not states["room_visible"]:
                raise NotFoundError(404, "TOURNAMENT_NOT_FOUND", "房间已关闭")
            return 200, json.dumps(_room_doc(status="running", my_games=("g1", "g2")))
        raise AssertionError("unexpected " + method + " " + path)

    transport.handler = handler
    session = make_auto_session(clock=clock, transport=transport, audit=audit)
    outcome = await initialize_once(session, _target(room_id="r_auto_1"))
    assert isinstance(outcome, SessionBootstrap)
    states["room_visible"] = False
    item = await asyncio.wait_for(session.next_update(), timeout=3)
    assert isinstance(item, ParticipantTerminal)
    assert item.reason is ParticipantTerminalReason.MATCHING_UNAVAILABLE
    assert "404" in item.detail
    # 无任何伪造终局/分数：适配器层零 GAME_FINISHED、零 finished 事件。
    assert not [r for r in audit.records if r.kind is AuditKind.GAME_FINISHED]
    assert "finished" not in lifecycle_events(audit.records)
    # 终态事件唯一归应用层（活场双层重复修正 2026-09-06）：适配器返回终态值
    # 但不发射 matching_stopped / PARTICIPANT_FINISHED。
    assert "matching_stopped" not in lifecycle_events(audit.records)
    assert not [r for r in audit.records if r.kind is AuditKind.PARTICIPANT_FINISHED]
    await session.aclose()


async def wait_till(condition, *, limit: int = 3000) -> None:
    """事件循环内轮询条件（本地副本，不改动共享测试文件）。"""

    for _ in range(limit):
        try:
            if condition():
                return
        except (KeyError, IndexError):
            pass
        await asyncio.sleep(0)
    raise AssertionError("等待条件超时")


def test_match_interval_below_official_minimum_rejected() -> None:
    """配额下限钉死：间隔配置低于官方 10 次/分换算值（6s）即构造拒绝，
    配置只能上调不能下调（防击穿；默认 6.5s 留余量）。"""

    with pytest.raises(ValueError, match="官方配额下限"):
        make_auto_session(
            clock=FakeClock(), transport=FakeTransport(), match_min_interval_sec=0.0
        )
    with pytest.raises(ValueError, match="官方配额下限"):
        make_auto_session(
            clock=FakeClock(), transport=FakeTransport(), match_min_interval_sec=5.9
        )
    # 恰好等于下限与默认值都是合法配置。
    make_auto_session(clock=FakeClock(), transport=FakeTransport(), match_min_interval_sec=6.0)
    make_auto_session(clock=FakeClock(), transport=FakeTransport())
    assert MIN_MATCH_INTERVAL_SEC == 6.0
    assert DEFAULT_MATCH_MIN_INTERVAL_SEC >= MIN_MATCH_INTERVAL_SEC


@pytest.mark.asyncio
async def test_match_quota_sliding_window_caps_ten_per_minute(transport, clock, audit) -> None:
    """60 秒滑动窗口配额：连续 12 次失败重试的 POST 时刻分布满足
    任意 60s 窗口 ≤ 10 次——第 11 次最早只能在首 POST 后 60s 发出，
    且相邻间隔不低于配置下限 6.0s。"""

    times: List[float] = []

    def handler(*, method: str, path: str, json_body=None, params=None, long_poll=False):
        if path == "/portal/api/guide/version":
            return 200, json.dumps(_guide_doc())
        if path == "/api/me":
            return 200, json.dumps(_me_doc())
        if path == "/api/match":
            times.append(clock.monotonic())
            raise ConflictError(409, None, '{"code":"MATCH_BUSY","message":"busy"}')
        raise AssertionError("unexpected " + method + " " + path)

    transport.handler = handler
    session = make_auto_session(
        clock=clock,
        transport=transport,
        audit=audit,
        match_min_interval_sec=6.0,  # 合法下限（官方换算值）
        match_max_attempts=12,
    )
    outcome = await initialize_once(session, _target())
    assert isinstance(outcome, ParticipantTerminal)
    assert outcome.reason is ParticipantTerminalReason.MATCHING_UNAVAILABLE
    assert len(times) == 12
    for earlier, later in zip(times, times[1:]):
        assert later - earlier >= 6.0 - 1e-9, "相邻 POST 间隔低于下限"
    # 滑动窗口：第 11 次 POST 距首 POST ≥ 60s（满窗后必须等窗口滑出）。
    assert times[QUOTA_MAX_CALLS] - times[0] >= QUOTA_WINDOW_SEC - 1e-6
    assert times[-1] - times[0] >= QUOTA_WINDOW_SEC - 1e-6


@pytest.mark.asyncio
async def test_open_game_sse_stream_unavailable_degrades_to_long_poll(
    transport, clock, audit
) -> None:
    """SSE 降级贯通：open_game 场次在通知流不可用（传输无 open_sse_stream）
    时自动降级长轮询并记 trigger=sse_degraded，窗口照常交付。"""

    def init_handler(*, method: str, path: str, json_body=None, params=None, long_poll=False):
        if path == "/portal/api/guide/version":
            return 200, json.dumps(_guide_doc())
        if path == "/api/me":
            return 200, json.dumps(_me_doc())
        if path == "/api/tournaments/r_auto_1":
            return 200, json.dumps(_room_doc(status="running", my_games=("g1",)))
        raise AssertionError("unexpected " + method + " " + path)

    transport.handler = init_handler
    session = make_auto_session(
        clock=clock,
        transport=transport,
        audit=audit,
        sse_enabled=True,
        sse_budget=StreamBudget(),
    )
    outcome = await initialize_once(session, _target(room_id="r_auto_1"))
    assert isinstance(outcome, SessionBootstrap)

    def game_handler(*, method: str, path: str, json_body=None, params=None, long_poll=False):
        if path.startswith("/api/games/g1/state"):
            return 200, json.dumps(load_fixture("state_response_snapshot_draw.json"))
        raise AssertionError("unexpected game call " + method + " " + path)

    transport.handler = game_handler
    game = session.open_game("g1")
    item = await asyncio.wait_for(game.next_item(), timeout=3)
    assert isinstance(item, ObservedActionWindow)

    # SSE 客户端首连失败（FakeTransport 无 open_sse_stream）→ 永久降级长轮询。
    def degraded_seen() -> bool:
        return any(
            r.kind is AuditKind.PROTOCOL_RECOVERED and r.payload.get("trigger") == "sse_degraded"
            for r in audit.records
        )

    await wait_till(degraded_seen)
    await game.aclose("test")
    await session.aclose()
