"""官方赛事会话测试：初始化发现、报名到位、状态流与资源共享。"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from hangma_bot.adapters.official.errors import AuthError, ConflictError, NotFoundError
from hangma_bot.application.contracts import (
    AuditKind,
    OperationStatus,
    ParticipantTerminal,
    ParticipantTerminalReason,
    RuntimeMode,
    RuntimeTarget,
    StageIdentity,
    TournamentStatus,
)

from _official_testkit import load_fixture, make_tournament_session

REFERENCE_GUIDE_V8 = Path(__file__).parents[3] / "doc" / "references" / "official-guide-version-v8.json"
REFERENCE_GUIDE_V24 = Path(__file__).parents[3] / "doc" / "references" / "official-guide-version-v24.json"

TARGET = RuntimeTarget(
    mode=RuntimeMode.TEST_ROOM,
    expected_tournament_id="t_test_room_1",
    known_guide_version=8,
)


def _guide_doc() -> dict:
    return json.loads(REFERENCE_GUIDE_V8.read_text(encoding="utf-8"))


def _initialize_handler(transport, *, me_doc=None, detail_name="tournament_detail.json", guide_doc=None) -> None:
    me = me_doc or load_fixture("me.json")

    def handler(*, method: str, path: str, json_body=None, params=None, long_poll=False):
        if path == "/portal/api/guide/version":
            return 200, json.dumps(guide_doc if guide_doc is not None else _guide_doc())
        if path == "/api/me":
            return 200, json.dumps(me)
        if path == "/api/tournaments/me/rules":
            return 200, json.dumps(load_fixture("rules.json"))
        if path == "/api/tournaments/t_test_room_1":
            return 200, json.dumps(load_fixture(detail_name))
        raise AssertionError("unexpected " + method + " " + path)

    transport.handler = handler


class TestInitialize:
    async def test_v24_scoped_discovery_success(self, transport, clock) -> None:
        doc = json.loads(REFERENCE_GUIDE_V24.read_text(encoding="utf-8"))
        _initialize_handler(transport, guide_doc=doc)
        session = make_tournament_session(clock=clock, transport=transport)
        outcome = await asyncio.wait_for(session.initialize(TARGET), timeout=2)
        assert not isinstance(outcome, ParticipantTerminal)
        assert outcome.tournament_id == TARGET.expected_tournament_id
        assert outcome.guide.version == 24

    async def test_v24_does_not_allow_global_token_in_scoped_session(self, transport, clock) -> None:
        doc = json.loads(REFERENCE_GUIDE_V24.read_text(encoding="utf-8"))
        me = load_fixture("me.json")
        me["tournament_id"] = ""
        _initialize_handler(transport, guide_doc=doc, me_doc=me)
        session = make_tournament_session(clock=clock, transport=transport)
        outcome = await asyncio.wait_for(session.initialize(TARGET), timeout=2)
        assert isinstance(outcome, ParticipantTerminal)
        assert outcome.reason is ParticipantTerminalReason.TARGET_MISMATCH
        assert all(call.method == "GET" for call in transport.calls)

    async def test_discovery_success(self, transport, clock) -> None:
        _initialize_handler(transport)
        session = make_tournament_session(clock=clock, transport=transport)
        outcome = await asyncio.wait_for(session.initialize(TARGET), timeout=2)
        assert not isinstance(outcome, ParticipantTerminal)
        assert outcome.participant_id == "u_player_a"
        assert outcome.tournament_id == "t_test_room_1"
        assert outcome.config.max_games == 10
        assert outcome.config.timing.discard_timeout_sec == 3.0
        assert outcome.initial_snapshot.status is TournamentStatus.RUNNING
        assert outcome.initial_snapshot.active_games == ("g_room1_batch1",)
        assert outcome.initial_snapshot.stage.observed_revision == 1

    async def test_future_breaking_guide_is_terminal(self, transport, clock) -> None:
        def handler(**kw):
            return 200, json.dumps(load_fixture("guide_breaking_future.json"))

        transport.handler = handler
        session = make_tournament_session(clock=clock, transport=transport)
        outcome = await asyncio.wait_for(session.initialize(TARGET), timeout=2)
        assert isinstance(outcome, ParticipantTerminal)
        assert outcome.reason is ParticipantTerminalReason.INCOMPATIBLE_GUIDE

    async def test_token_bound_to_other_tournament(self, transport, clock) -> None:
        wrong = load_fixture("me.json")
        wrong["tournament_id"] = "t_other"
        _initialize_handler(transport, me_doc=wrong)
        session = make_tournament_session(clock=clock, transport=transport)
        outcome = await asyncio.wait_for(session.initialize(TARGET), timeout=2)
        assert isinstance(outcome, ParticipantTerminal)
        assert outcome.reason is ParticipantTerminalReason.TARGET_MISMATCH

    async def test_auth_failure_is_terminal(self, transport, clock) -> None:
        def handler(*, path, **kw):
            if path == "/portal/api/guide/version":
                return 200, json.dumps(_guide_doc())
            raise AuthError(401, "UNAUTHORIZED", "bad token")

        transport.handler = handler
        session = make_tournament_session(clock=clock, transport=transport)
        outcome = await asyncio.wait_for(session.initialize(TARGET), timeout=2)
        assert isinstance(outcome, ParticipantTerminal)
        assert outcome.reason is ParticipantTerminalReason.AUTHENTICATION_FAILED


class TestRegisterAndReady:
    @pytest.mark.parametrize("unknown_change", [False, True])
    async def test_v24_boundary_checks_reviewed_content(self, transport, clock, unknown_change) -> None:
        _initialize_handler(transport)
        session = make_tournament_session(clock=clock, transport=transport)
        boot = await asyncio.wait_for(session.initialize(TARGET), timeout=2)
        assert not isinstance(boot, ParticipantTerminal)
        guide = json.loads(REFERENCE_GUIDE_V24.read_text(encoding="utf-8"))
        if unknown_change:
            guide["changes"][0]["detail"] += "\n未审查的阶段规则"
        _initialize_handler(transport, detail_name="tournament_stage_open.json", guide_doc=guide)
        update = await asyncio.wait_for(session.next_update(), timeout=2)
        assert not isinstance(update, ParticipantTerminal)
        assert update.stage != boot.initial_snapshot.stage

        def boundary_handler(*, method, path, **kw):
            if path == "/portal/api/guide/version":
                return 200, json.dumps(guide)
            assert method == "POST" and path == "/api/tournaments/me/ready"
            return 200, "{}"

        transport.handler = boundary_handler
        transport.calls.clear()
        result = await asyncio.wait_for(session.ready(update.stage), timeout=2)
        if unknown_change:
            assert isinstance(result, ParticipantTerminal)
            assert result.reason is ParticipantTerminalReason.INCOMPATIBLE_GUIDE
            assert all(call.method == "GET" for call in transport.calls)
        else:
            assert result.status is OperationStatus.ACCEPTED
            assert any(call.method == "POST" for call in transport.calls)

    async def _initialized(self, transport, clock):
        _initialize_handler(transport)
        session = make_tournament_session(clock=clock, transport=transport)
        outcome = await asyncio.wait_for(session.initialize(TARGET), timeout=2)
        assert not isinstance(outcome, ParticipantTerminal)
        return session

    async def test_register_accepted_then_rejected(self, transport, clock) -> None:
        session = await self._initialized(transport, clock)
        transport.handler = lambda **kw: (200, "{}")
        result = await asyncio.wait_for(session.register(), timeout=2)
        assert result.status is OperationStatus.ACCEPTED

        def conflict(**kw):
            raise ConflictError(409, "MATCH_LIMIT_REACHED", "limit")

        transport.handler = conflict
        result = await asyncio.wait_for(session.register(), timeout=2)
        assert result.status is OperationStatus.REJECTED
        assert result.official_code == "MATCH_LIMIT_REACHED"

    async def test_ready_accepted_and_not_qualified(self, transport, clock) -> None:
        session = await self._initialized(transport, clock)
        stage = session._last_snapshot.stage
        transport.handler = lambda **kw: (200, "{}")
        result = await asyncio.wait_for(session.ready(stage), timeout=2)
        assert result.status is OperationStatus.ACCEPTED

        def not_qualified(**kw):
            raise ConflictError(409, "NOT_QUALIFIED", "")

        transport.handler = not_qualified
        result = await asyncio.wait_for(session.ready(stage), timeout=2)
        assert result.status is OperationStatus.REJECTED
        assert result.official_code == "NOT_QUALIFIED"

    async def test_v35_gone_retries_idempotent_register_and_ready(self, transport, clock, audit) -> None:
        """暂时不可达不能让报名或到位静默退出；两端点均为官方幂等操作。"""
        _initialize_handler(transport)
        session = make_tournament_session(clock=clock, transport=transport, audit=audit)
        bootstrap = await session.initialize(TARGET)
        assert not isinstance(bootstrap, ParticipantTerminal)
        calls = {"register": 0, "ready": 0}

        def handler(*, path, **kw):
            operation = "register" if path.endswith("/register") else "ready"
            calls[operation] += 1
            if calls[operation] <= 2:
                raise NotFoundError(404, "TOURNAMENT_GONE", "tournament unavailable")
            return 200, "{}"

        transport.handler = handler
        assert (await session.register()).status is OperationStatus.ACCEPTED
        assert (await session.ready(bootstrap.initial_snapshot.stage)).status is OperationStatus.ACCEPTED
        assert calls == {"register": 3, "ready": 3}
        assert sum(record.payload.get("area") == "tournament_temporarily_unavailable"
                   for record in audit.records) == 4

    async def test_stale_ready_rejected_locally(self, transport, clock) -> None:
        """陈旧到位：观察修订号不匹配时本地拒绝且不发任何 HTTP 请求。"""

        session = await self._initialized(transport, clock)
        stale_stage = StageIdentity(stage_no=1, observed_revision=99)
        transport.calls.clear()
        result = await asyncio.wait_for(session.ready(stale_stage), timeout=2)
        assert result.status is OperationStatus.REJECTED
        assert result.official_code == "STALE_STAGE"
        assert transport.calls == []


class TestNextUpdate:
    async def test_change_then_finished_snapshot_in_test_room(self, transport, clock) -> None:
        """测试房间 finished 非终态：适配器透传快照，由应用层按模式复用。"""

        _initialize_handler(transport)
        session = make_tournament_session(clock=clock, transport=transport)
        bootstrap = await asyncio.wait_for(session.initialize(TARGET), timeout=2)
        assert not isinstance(bootstrap, ParticipantTerminal)

        # 首次 next_update：无变化 → 持续轮询；随后阶段切换 → 返回新快照
        counter = {"n": 0}

        def handler(*, path, **kw):
            if path == "/api/me":
                return 200, json.dumps(load_fixture("me.json"))
            counter["n"] += 1
            if counter["n"] <= 2:
                return 200, json.dumps(load_fixture("tournament_detail.json"))
            return 200, json.dumps(load_fixture("tournament_stage_open.json"))

        transport.handler = handler
        snapshot = await asyncio.wait_for(session.next_update(), timeout=5)
        assert not isinstance(snapshot, ParticipantTerminal)
        assert snapshot.status is TournamentStatus.STAGE_OPEN
        assert snapshot.stage.observed_revision == 2  # 观察修订号单调递增

        # 测试房间 finished：不是适配器终态，快照透传（跨轮复用由应用层决定）。
        def finished_handler(*, path, **kw):
            if path == "/api/me":
                return 200, json.dumps(load_fixture("me.json"))
            return 200, json.dumps(load_fixture("tournament_finished.json"))

        transport.handler = finished_handler
        update = await asyncio.wait_for(session.next_update(), timeout=5)
        assert not isinstance(update, ParticipantTerminal)
        assert update.status is TournamentStatus.FINISHED
        assert update.stage.observed_revision == 3

    async def test_terminal_statuses_are_plain_snapshots(self, transport, clock) -> None:
        """finished/closed 在任何模式下都是普通变化快照：退出判定属于应用层。"""

        _initialize_handler(transport)
        session = make_tournament_session(clock=clock, transport=transport)
        target = RuntimeTarget(
            mode=RuntimeMode.TEST_TOURNAMENT,
            expected_tournament_id="t_test_room_1",
            known_guide_version=8,
        )
        bootstrap = await asyncio.wait_for(session.initialize(target), timeout=2)
        assert not isinstance(bootstrap, ParticipantTerminal)

        def finished_handler(*, path, **kw):
            if path == "/api/me":
                return 200, json.dumps(load_fixture("me.json"))
            return 200, json.dumps(load_fixture("tournament_finished.json"))

        transport.handler = finished_handler
        update = await asyncio.wait_for(session.next_update(), timeout=5)
        assert not isinstance(update, ParticipantTerminal)
        assert update.status is TournamentStatus.FINISHED
        assert update.stage.observed_revision == 2

        # closed 同样透传快照（终态语义由 supervisor 判定，测试见 unit/application）。
        def closed_handler(*, path, **kw):
            if path == "/api/me":
                return 200, json.dumps(load_fixture("me.json"))
            doc = load_fixture("tournament_finished.json")
            doc["status"] = "closed"
            return 200, json.dumps(doc)

        transport.handler = closed_handler
        update = await asyncio.wait_for(session.next_update(), timeout=5)
        assert not isinstance(update, ParticipantTerminal)
        assert update.status is TournamentStatus.CLOSED
        assert update.stage.observed_revision == 3


class TestResourceSharing:
    async def test_open_game_isolates_scheduler_and_shares_transport(self, transport, clock) -> None:
        """同 Token 复用传输；每场独立调度与限频，同场重复打开保留预算。"""

        _initialize_handler(transport)
        session = make_tournament_session(clock=clock, transport=transport)
        bootstrap = await asyncio.wait_for(session.initialize(TARGET), timeout=2)
        assert not isinstance(bootstrap, ParticipantTerminal)
        g1 = session.open_game("g_room1_batch1")
        g2 = session.open_game("g_room1_batch2")
        assert g1 is session.open_game("g_room1_batch1")  # 同场会话复用
        assert g1._scheduler is not g2._scheduler
        assert g1._transport is g2._transport

    async def test_four_tokens_are_isolated(self, clock) -> None:
        """四 Token 隔离：每个会话各自拥有传输与限速器，互不影响冷却。"""

        from _official_testkit import FakeTransport

        sessions = [
            make_tournament_session(clock=clock, transport=FakeTransport())
            for _ in range(4)
        ]
        schedulers = {id(s._scheduler) for s in sessions}
        transports = {id(s._transport) for s in sessions}
        assert len(schedulers) == 4 and len(transports) == 4
        # 一个 Token 的 429 冷却不影响其他 Token
        sessions[0]._scheduler.note_rate_limited(5.0)
        assert sessions[1]._scheduler.cooldown_remaining == 0
        assert sessions[0]._scheduler.cooldown_remaining > 0


class TestTournamentDetailNotFoundTolerance:
    """指南 v35 的两种 404：GONE 暂时不可达，NOT_FOUND 永久不存在。

    证据：测试赛事 t_65d538e905c5 在正常 2 秒轮询中，详情端点连续 200 之后
    单次返回 404 TOURNAMENT_GONE，同时刻 /api/me 为 200，随后同端点又恢复
    200（两次独立运行各命中一次）。因此单次 404 只说明该次读取失败：
    本类固化按官方 code 判型，不把重试次数当成房间是否存在的证据。
    """

    def _flaky_detail(self, transport, *, failures: int,
                      detail_name: str = "tournament_detail.json") -> dict:
        """初始化链路的脚本化传输：详情端点前 failures 次返回 404，之后成功。"""

        state = {"detail_calls": 0}

        def handler(*, method: str, path: str, json_body=None, params=None, long_poll=False):
            if path == "/portal/api/guide/version":
                return 200, json.dumps(_guide_doc())
            if path == "/api/me":
                return 200, json.dumps(load_fixture("me.json"))
            if path == "/api/tournaments/me/rules":
                return 200, json.dumps(load_fixture("rules.json"))
            if path == "/api/tournaments/t_test_room_1":
                state["detail_calls"] += 1
                if state["detail_calls"] <= failures:
                    raise NotFoundError(404, "TOURNAMENT_GONE", "tournament unavailable")
                return 200, json.dumps(load_fixture(detail_name))
            raise AssertionError("unexpected " + method + " " + path)

        transport.handler = handler
        return state

    @staticmethod
    def _not_found_notices(audit) -> list:
        return [record for record in audit.records
                if record.payload.get("area") == "tournament_temporarily_unavailable"]

    async def test_transient_detail_404_is_tolerated(self, transport, clock, audit) -> None:
        """单次 404 后重读成功：初始化正常完成，且容忍事实进审计。"""

        self._flaky_detail(transport, failures=1)
        session = make_tournament_session(clock=clock, transport=transport, audit=audit)
        outcome = await asyncio.wait_for(session.initialize(TARGET), timeout=2)
        assert not isinstance(outcome, ParticipantTerminal)
        assert outcome.tournament_id == TARGET.expected_tournament_id
        notices = self._not_found_notices(audit)
        assert len(notices) == 1
        assert notices[0].kind is AuditKind.PROTOCOL_RECOVERED
        assert notices[0].payload["official_code"] == "TOURNAMENT_GONE"
        assert notices[0].payload["path"] == "/api/tournaments/t_test_room_1"

    async def test_gone_recovers_even_after_old_tolerance(self, transport, clock, audit) -> None:
        """连续六次 GONE 后恢复，仍须留在原房，不得误判永久消失。"""

        state = self._flaky_detail(transport, failures=6)
        session = make_tournament_session(clock=clock, transport=transport, audit=audit)
        outcome = await asyncio.wait_for(session.initialize(TARGET), timeout=2)
        assert not isinstance(outcome, ParticipantTerminal)
        assert state["detail_calls"] == 7
        assert len(self._not_found_notices(audit)) == 6

    async def test_not_found_is_permanent_without_retry(self, transport, clock, audit) -> None:
        """明确不存在的房间不等待；只按 code 而不按 HTTP 404 判型。"""
        _initialize_handler(transport)
        calls = {"detail": 0}
        prior = transport.handler

        def handler(**kw):
            if kw["path"] == "/api/tournaments/t_test_room_1":
                calls["detail"] += 1
                raise NotFoundError(404, "TOURNAMENT_NOT_FOUND", "not found")
            return prior(**kw)

        transport.handler = handler
        session = make_tournament_session(clock=clock, transport=transport, audit=audit)
        outcome = await asyncio.wait_for(session.initialize(TARGET), timeout=2)
        assert isinstance(outcome, ParticipantTerminal)
        assert outcome.reason is ParticipantTerminalReason.TARGET_MISMATCH
        assert calls["detail"] == 1
        assert not self._not_found_notices(audit)

    async def test_transient_detail_404_does_not_end_polling(self, transport, clock, audit) -> None:
        """轮询中的单次 404 不得终结：重读拿到权威快照并正常返回。

        这条是本类的主回归：2026-09-17 首跑正是死在这里（退出码 10）。
        """

        _initialize_handler(transport)
        session = make_tournament_session(clock=clock, transport=transport, audit=audit)
        bootstrap = await asyncio.wait_for(session.initialize(TARGET), timeout=2)
        assert not isinstance(bootstrap, ParticipantTerminal)

        state = {"detail_calls": 0}

        def handler(*, path, **kw):
            if path == "/api/me":
                return 200, json.dumps(load_fixture("me.json"))
            state["detail_calls"] += 1
            if state["detail_calls"] == 1:
                raise NotFoundError(404, "TOURNAMENT_GONE", "tournament unavailable")
            return 200, json.dumps(load_fixture("tournament_stage_open.json"))

        transport.handler = handler
        snapshot = await asyncio.wait_for(session.next_update(), timeout=5)
        assert not isinstance(snapshot, ParticipantTerminal)
        assert snapshot.status is TournamentStatus.STAGE_OPEN
        assert len(self._not_found_notices(audit)) == 1
