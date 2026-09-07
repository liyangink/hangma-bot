"""官方赛事会话测试：初始化发现、报名到位、状态流与资源共享。"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from hangma_bot.adapters.official.errors import AuthError, ConflictError
from hangma_bot.application.contracts import (
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

TARGET = RuntimeTarget(
    mode=RuntimeMode.TEST_ROOM,
    expected_tournament_id="t_test_room_1",
    known_guide_version=8,
)


def _guide_doc() -> dict:
    return json.loads(REFERENCE_GUIDE_V8.read_text(encoding="utf-8"))


def _initialize_handler(transport, *, me_doc=None, detail_name="tournament_detail.json") -> None:
    me = me_doc or load_fixture("me.json")

    def handler(*, method: str, path: str, json_body=None, params=None, long_poll=False):
        if path == "/portal/api/guide/version":
            return 200, json.dumps(_guide_doc())
        if path == "/api/me":
            return 200, json.dumps(me)
        if path == "/api/tournaments/me/rules":
            return 200, json.dumps(load_fixture("rules.json"))
        if path == "/api/tournaments/t_test_room_1":
            return 200, json.dumps(load_fixture(detail_name))
        raise AssertionError("unexpected " + method + " " + path)

    transport.handler = handler


class TestInitialize:
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
