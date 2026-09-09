"""官方场次会话测试：窗口交付、终局、提交结果封闭与审计。"""
from __future__ import annotations

import asyncio
import json

import pytest

from hangma_bot.adapters.official.errors import (
    AuthError,
    ConflictError,
    UncertainTransportError,
)
from hangma_bot.application.contracts import (
    ActionAttempt,
    AuditKind,
    GameFailed,
    GameFinished,
    ObservedActionWindow,
    SubmitAccepted,
    SubmitAmbiguous,
    SubmitFatal,
    SubmitNotSent,
    SubmitRejectedClosed,
    SubmitRejectedRetryable,
)
from hangma_bot.kernel.actions import Discard, Pass, Peng, Tile, WindowKey, WindowPhase

from _official_testkit import TIMING, load_fixture, make_game_session


def _draw_window_key(trigger: int = 101, seat: int = 2) -> WindowKey:
    return WindowKey(game_id="g_room1_batch1", round_no=1, trigger_seq=trigger, phase=WindowPhase.DRAW, seat=seat)


def _peng_window_key(trigger: int = 120, seat: int = 2) -> WindowKey:
    return WindowKey(game_id="g_room1_batch1", round_no=1, trigger_seq=trigger, phase=WindowPhase.RESPONSE_PENG, seat=seat)


def _attempt(window: WindowKey, action, action_key: str, *, attempt_no: int = 1) -> ActionAttempt:
    return ActionAttempt(
        decision_id="d-1",
        attempt_no=attempt_no,
        plan_revision=1,
        window_key=window,
        based_on_authoritative_seq=window.trigger_seq,
        action=action,
        action_key=action_key,
        latest_send_at_monotonic=1005.0,
    )


def _state_handler(queue: list):
    """按调用顺序弹出响应脚本；元素为 (status, text) 或异常实例。

    动作 POST 与 state GET 共用一个队列：409 场景中 POST 弹出冲突异常，
    随后的权威刷新 GET 弹出刷新快照。
    """

    def handler(*, method: str, path: str, json_body=None, params=None, long_poll=False):
        assert method in ("GET", "POST") and path.startswith("/api/games/"), path
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return handler


def _json(doc: dict):
    return 200, json.dumps(doc)


class TestNextItem:
    async def test_snapshot_opens_draw_window(self, transport, clock) -> None:
        """首拉 seq=0 返回全量快照并交付 draw 窗口。"""

        transport.handler = _state_handler([_json(load_fixture("state_response_snapshot_draw.json"))])
        session = make_game_session(transport=transport, clock=clock)
        item = await asyncio.wait_for(session.next_item(), timeout=2)
        assert isinstance(item, ObservedActionWindow)
        assert item.window_key == _draw_window_key()
        assert item.authoritative_seq == 101
        assert item.timeout_seconds == 3.0
        assert item.observation.my_hand[-1] == Tile("白")

    async def test_last_discard_string_reconstructed_and_audited(self, transport, clock, audit) -> None:
        """官方纯牌码 last_discard + 牌河交叉验证不一致：仍以 turn 重建并记审计。

        回归背景：真实快照 last_discard 为纯牌码字符串时旧投影返回 None，
        响应窗口只剩过。修复后观察携带重建的 PublicDiscard，提示进审计。
        """

        from hangma_bot.kernel.observation import PublicDiscard

        doc = load_fixture("state_response_snapshot_peng.json")
        doc["snapshot"]["last_discard"] = "2w"  # 纯牌码形态（官方实测形状）
        doc["snapshot"]["turn"] = 0  # 座位 0 牌河末张 "1t" != "2w"：触发提示
        transport.handler = _state_handler([_json(doc)])
        session = make_game_session(transport=transport, clock=clock, audit=audit)
        item = await asyncio.wait_for(session.next_item(), timeout=2)
        assert isinstance(item, ObservedActionWindow)
        assert item.window_key.phase is WindowPhase.RESPONSE_PENG
        assert item.observation.last_discard == PublicDiscard(
            seat=0, tile=Tile("2w"), seq=120
        )
        notes = [
            record
            for record in audit.records
            if "last_discard_projection_note" in record.payload
        ]
        assert len(notes) == 1
        assert "turn" in notes[0].payload["last_discard_projection_note"]

    async def test_pending_then_snapshot(self, transport, clock) -> None:
        transport.handler = _state_handler([
            _json(load_fixture("state_response_pending.json")),
            _json(load_fixture("state_response_snapshot_draw.json")),
        ])
        session = make_game_session(transport=transport, clock=clock)
        item = await asyncio.wait_for(session.next_item(), timeout=2)
        assert isinstance(item, ObservedActionWindow)
        # 尚无权威快照时，pending 后的下一轮仍以 seq=0 请求全量
        assert transport.calls[0].params == {"seq": 0}
        assert transport.calls[1].params == {"seq": 0}

    async def test_events_trigger_full_refresh_and_window(self, transport, clock) -> None:
        """增量事件后必须刷新全量快照：私有字段只在快照中出现。"""

        base = load_fixture("state_response_snapshot_draw.json")
        base["snapshot"]["turn"] = 0  # 首快照无窗口（他人回合）
        refreshed = load_fixture("state_response_snapshot_draw.json")
        refreshed["seq"] = 103  # 权威快照必须吸收本批事件
        transport.handler = _state_handler([
            _json(base),
            _json(load_fixture("state_response_events.json")),
            _json(refreshed),
        ])
        session = make_game_session(transport=transport, clock=clock)
        item = await asyncio.wait_for(session.next_item(), timeout=2)
        assert isinstance(item, ObservedActionWindow)
        # 调用顺序：增量轮询 → 全量刷新(seq=0)
        assert transport.calls[1].params == {"seq": 101}
        assert transport.calls[2].params == {"seq": 0}

    async def test_gap_triggers_rebuild(self, transport, clock) -> None:
        base = load_fixture("state_response_snapshot_draw.json")
        base["snapshot"]["turn"] = 0
        transport.handler = _state_handler([
            _json(base),
            _json(load_fixture("state_response_gap.json")),
            _json(load_fixture("state_response_snapshot_draw.json")),
        ])
        session = make_game_session(transport=transport, clock=clock)
        item = await asyncio.wait_for(session.next_item(), timeout=2)
        assert isinstance(item, ObservedActionWindow)
        assert transport.calls[2].params == {"seq": 0}

    async def test_finished_returns_final_scores(self, transport, clock) -> None:
        transport.handler = _state_handler([_json(load_fixture("state_response_finished.json"))])
        session = make_game_session(transport=transport, clock=clock)
        item = await asyncio.wait_for(session.next_item(), timeout=2)
        assert isinstance(item, GameFinished)
        assert item.final_scores == (34, 12, -6, -40)
        assert item.authoritative_seq == 210
        # 终局幂等：再次调用返回同一结果
        again = await asyncio.wait_for(session.next_item(), timeout=2)
        assert again == item

    async def test_auth_failure_is_classified(self, transport, clock) -> None:
        transport.handler = _state_handler([AuthError(401, "UNAUTHORIZED", "token invalid")])
        session = make_game_session(transport=transport, clock=clock)
        item = await asyncio.wait_for(session.next_item(), timeout=2)
        assert isinstance(item, GameFailed)
        assert item.recoverable is False and item.reason == "authentication_failed"

    async def test_rate_limited_then_success(self, transport, clock) -> None:
        from hangma_bot.adapters.official.errors import RateLimitedError

        transport.handler = _state_handler([
            RateLimitedError(429, "RATE_LIMITED", "too many", 0.1),
            _json(load_fixture("state_response_snapshot_draw.json")),
        ])
        session = make_game_session(transport=transport, clock=clock)
        item = await asyncio.wait_for(session.next_item(), timeout=3)
        assert isinstance(item, ObservedActionWindow)

    async def test_game_not_found_is_recoverable(self, transport, clock) -> None:
        from hangma_bot.adapters.official.errors import NotFoundError

        transport.handler = _state_handler([NotFoundError(404, "GAME_NOT_FOUND", "")])
        session = make_game_session(transport=transport, clock=clock)
        item = await asyncio.wait_for(session.next_item(), timeout=2)
        assert isinstance(item, GameFailed) and item.recoverable is True

    async def test_aclose_cancels_pending_poll(self, transport, clock) -> None:
        """aclose 取消挂起长轮询并返回分类故障，不影响共享传输。"""

        async def hanging_handler(**kw):
            await asyncio.sleep(30)
            return 200, "{}"

        transport.handler = hanging_handler
        session = make_game_session(transport=transport, clock=clock)
        task = asyncio.create_task(session.next_item())
        await asyncio.sleep(0.05)
        await session.aclose("stage_switched")
        item = await asyncio.wait_for(task, timeout=2)
        assert isinstance(item, GameFailed)
        assert item.reason.startswith("session_closed:")


class TestSubmit:
    @pytest.mark.parametrize("relay,gap,accepted", [(False, False, True), (True, False, False), (False, True, False)])
    async def test_catch_owner_hand_discard_uses_current_circle_at_protocol_exit(
        self, transport, clock, relay, gap, accepted,
    ):
        """协议出口允许可证明圈主手切；接力换主或缺史后仍拦截旧手牌。

        这是受控报文的提交路径回归，Fake 接受响应不作为官方规则证据。
        """
        doc = load_fixture("state_response_snapshot_draw.json")
        doc["seq"] = 8
        doc["snapshot"]["dealer"] = 2
        doc["snapshot"]["last_discard"]["seq"] = 7
        doc["snapshot"]["god"]["catch_play"] = True
        doc["snapshot"]["discards"] = [["1t"], ["9t"], ["白"], ["白" if relay else "东"]]
        sequence = [
            (94, "tile_discarded", 2, "白"),
            (95, "tile_drawn", 3, None),
            (96, "tile_discarded", 3, "白" if relay else "东"),
            (97, "tile_drawn", 0, None),
            (98, "tile_discarded", 0, "1t"),
            (99, "tile_drawn", 1, None),
            (100, "tile_discarded", 1, "9t"),
            (101, "tile_drawn", 2, "5w"),
        ]
        doc["events"] = [
            {"seq": seq - 93, "type": kind, "seat": seat, "tile": tile,
             "data": {"catch_play": True} if kind == "tile_discarded" else {}}
            for seq, kind, seat, tile in sequence if not (gap and seq == 97)
        ]
        transport.handler = _state_handler([_json(doc)])
        session = make_game_session(transport=transport, clock=clock)
        window = await asyncio.wait_for(session.next_item(), timeout=2)
        assert isinstance(window, ObservedActionWindow)
        if accepted:
            from hangma_bot.hangma.catch_play import analyze_catch_play
            assert analyze_catch_play(window.observation).owner_seat == 2, (
                analyze_catch_play(window.observation), window.observation.public_history,
            )
        transport.handler = lambda **kw: (200, "{}")

        outcome = await session.submit(_attempt(window.window_key, Discard(Tile("1w")), "discard:1w"))

        if accepted:
            assert isinstance(outcome, SubmitAccepted)
            posts = [call for call in transport.calls if call.method == "POST"]
            assert len(posts) == 1 and posts[0].json_body == {"action": "discard", "tile": "1w"}
        else:
            assert isinstance(outcome, SubmitNotSent)
            assert not [call for call in transport.calls if call.method == "POST"]

    def _open_window(self, transport, clock, fixture: str = "state_response_snapshot_draw.json", audit=None):
        transport.handler = _state_handler([_json(load_fixture(fixture))])
        session = make_game_session(transport=transport, clock=clock, audit=audit)
        return session

    async def test_accepted_flow_with_audit(self, transport, clock, audit) -> None:
        """成功提交：intent 先于 POST，outcome 后于返回；同窗封锁。"""

        session = self._open_window(transport, clock, audit=audit)
        window = await asyncio.wait_for(session.next_item(), timeout=2)
        transport.handler = lambda **kw: (200, "{}")
        outcome = await asyncio.wait_for(
            session.submit(_attempt(window.window_key, Discard(Tile("5w")), "discard:5w")),
            timeout=2,
        )
        assert isinstance(outcome, SubmitAccepted)
        kinds = [r.kind for r in audit.records]
        # 原始事件全量保留接线（E1/E3）后：state 响应原文先于权威状态审计、
        # POST 响应原文在 intent 与 outcome 之间——两者都是 RAW_PROTOCOL_STATE
        assert kinds == [
            AuditKind.HTTP_REQUEST, AuditKind.HTTP_REQUEST,
            AuditKind.RAW_PROTOCOL_STATE,       # E1：开桌 /state 响应原文
            AuditKind.AUTHORITATIVE_STATE,
            AuditKind.AUTHORITATIVE_STATE,     # 普通弃牌快照恢复：记录跳过缓发
            AuditKind.SUBMISSION_INTENT,
            AuditKind.HTTP_REQUEST, AuditKind.HTTP_REQUEST,
            AuditKind.RAW_PROTOCOL_STATE,       # E3：动作 POST 响应原文
            AuditKind.SUBMISSION_OUTCOME,
        ]
        post = [c for c in transport.calls if c.method == "POST"]
        assert len(post) == 1 and post[0].json_body == {"action": "discard", "tile": "5w"}
        # 同窗再提交：已被终结
        again = await asyncio.wait_for(
            session.submit(_attempt(window.window_key, Discard(Tile("5w")), "discard:5w", attempt_no=2)),
            timeout=2,
        )
        assert isinstance(again, SubmitNotSent) and again.reason == "window_already_finalized"
        assert len([c for c in transport.calls if c.method == "POST"]) == 1

    async def test_conflict_same_window_retryable(self, transport, clock) -> None:
        """409 后权威刷新确认同窗仍需行动 → Retryable 携带刷新窗口。"""

        session = self._open_window(transport, clock, "state_response_snapshot_peng.json")
        window = await asyncio.wait_for(session.next_item(), timeout=2)
        assert window.window_key.phase is WindowPhase.RESPONSE_PENG
        transport.handler = _state_handler([
            ConflictError(409, "INVALID_ACTION", "no"),
            _json(load_fixture("state_response_snapshot_peng.json")),  # 同窗仍开放
        ])
        outcome = await asyncio.wait_for(
            session.submit(_attempt(window.window_key, Peng(Tile("2w")), "peng:2w")),
            timeout=2,
        )
        assert isinstance(outcome, SubmitRejectedRetryable)
        assert outcome.official_code == "INVALID_ACTION"
        assert outcome.rejected_action_key == "peng:2w"
        assert outcome.refreshed_window.window_key == window.window_key
        assert outcome.refreshed_window.observation.snapshot_seq == 120
        # 刷新请求必须是 seq=0 权威快照
        refresh = transport.calls[-1]
        assert refresh.params == {"seq": 0}

    async def test_conflict_window_closed(self, transport, clock) -> None:
        session = self._open_window(transport, clock, "state_response_snapshot_peng.json")
        window = await asyncio.wait_for(session.next_item(), timeout=2)
        migrated = load_fixture("state_response_snapshot_draw.json")
        migrated["seq"] = 121
        transport.handler = _state_handler([
            ConflictError(409, "INVALID_ACTION", "no"),
            _json(migrated),  # 窗口已迁移且水位向前
            _json({"pending": True}),  # 从旧游标120最多一次补领
        ])
        outcome = await asyncio.wait_for(
            session.submit(_attempt(window.window_key, Peng(Tile("2w")), "peng:2w")),
            timeout=2,
        )
        assert isinstance(outcome, SubmitRejectedClosed)
        assert outcome.latest_authoritative_seq == 121
        # 原窗口已终结：同窗再提交被拒
        again = await asyncio.wait_for(
            session.submit(_attempt(window.window_key, Peng(Tile("2w")), "peng:2w", attempt_no=2)),
            timeout=2,
        )
        assert isinstance(again, SubmitNotSent)

    async def test_timeout_is_ambiguous_and_blocks_window(self, transport, clock) -> None:
        """POST 结果不确定 → Ambiguous；同窗零次追加提交。"""

        session = self._open_window(transport, clock)
        window = await asyncio.wait_for(session.next_item(), timeout=2)
        transport.handler = _state_handler([UncertainTransportError("timeout:ReadTimeout")])
        outcome = await asyncio.wait_for(
            session.submit(_attempt(window.window_key, Discard(Tile("5w")), "discard:5w")),
            timeout=2,
        )
        assert isinstance(outcome, SubmitAmbiguous)
        assert outcome.recovery_id
        again = await asyncio.wait_for(
            session.submit(_attempt(window.window_key, Discard(Tile("5w")), "discard:5w", attempt_no=2)),
            timeout=2,
        )
        assert isinstance(again, SubmitNotSent)
        assert again.reason == "ambiguous_window_blocked"
        assert len([c for c in transport.calls if c.method == "POST"]) == 1

    async def test_deadline_passed_never_sends(self, transport, clock) -> None:
        """超过 latest_send_at_monotonic：POST 发送次数为 0。"""

        session = self._open_window(transport, clock)
        window = await asyncio.wait_for(session.next_item(), timeout=2)
        clock.advance(10.0)  # 越过 latest_send_at=1005
        transport.handler = lambda **kw: (200, "{}")
        attempt = _attempt(window.window_key, Discard(Tile("5w")), "discard:5w")
        outcome = await asyncio.wait_for(session.submit(attempt), timeout=2)
        assert isinstance(outcome, SubmitNotSent) and outcome.reason == "deadline_passed"
        assert len([c for c in transport.calls if c.method == "POST"]) == 0

    async def test_deadline_checked_again_after_scheduling(self, transport, clock) -> None:
        """调度等待越过截止时间：POST 发送次数为 0（排队不豁免截止）。"""

        from hangma_bot.adapters.official.scheduler import Priority, RequestKind, RequestScheduler

        from _official_testkit import instant_sleep

        # state额度不再阻塞POST；用占满共享并发槽验证排队仍服从截止。
        slow_scheduler = RequestScheduler(
            max_concurrent=1,
            clock=clock.monotonic,
            sleep=instant_sleep(clock),
            poll_interval=0.01,
        )
        session = self._open_window(transport, clock)
        session._scheduler = slow_scheduler
        window = await asyncio.wait_for(session.next_item(), timeout=2)
        lease = await slow_scheduler.acquire(Priority.BACKGROUND, request_kind=RequestKind.OTHER)
        transport.handler = lambda **kw: (200, "{}")
        outcome = await asyncio.wait_for(
            session.submit(_attempt(window.window_key, Discard(Tile("5w")), "discard:5w")),
            timeout=3,
        )
        lease.release()
        assert isinstance(outcome, SubmitNotSent)
        # 排队期间预算耗尽：deadline-aware acquire 更早终止（POST 从未发出）
        assert outcome.reason == "deadline_passed_in_schedule"
        assert len([c for c in transport.calls if c.method == "POST"]) == 0

    async def test_stale_window_rejected(self, transport, clock) -> None:
        """基于过期窗口的提交被本地拒绝，不产生 POST。"""

        session = self._open_window(transport, clock)
        await asyncio.wait_for(session.next_item(), timeout=2)
        stale = _draw_window_key(trigger=99)
        outcome = await asyncio.wait_for(
            session.submit(_attempt(stale, Discard(Tile("5w")), "discard:5w")),
            timeout=2,
        )
        assert isinstance(outcome, SubmitNotSent) and outcome.reason == "stale_window"

    async def test_auth_error_is_fatal(self, transport, clock) -> None:
        session = self._open_window(transport, clock)
        window = await asyncio.wait_for(session.next_item(), timeout=2)
        transport.handler = _state_handler([AuthError(401, "UNAUTHORIZED", "x")])
        outcome = await asyncio.wait_for(
            session.submit(_attempt(window.window_key, Discard(Tile("5w")), "discard:5w")),
            timeout=2,
        )
        assert isinstance(outcome, SubmitFatal)
        assert outcome.reason == "authentication_failed"

    async def test_audit_failure_never_blocks_submission(self, transport, clock) -> None:
        """审计 emit 抛异常不得影响动作路径（防御性保障）。"""

        class BrokenAudit:
            def emit(self, record):
                raise RuntimeError("disk full")

        session = self._open_window(transport, clock)
        session._audit = BrokenAudit()
        window = await asyncio.wait_for(session.next_item(), timeout=2)
        transport.handler = lambda **kw: (200, "{}")
        outcome = await asyncio.wait_for(
            session.submit(_attempt(window.window_key, Discard(Tile("5w")), "discard:5w")),
            timeout=2,
        )
        assert isinstance(outcome, SubmitAccepted)
