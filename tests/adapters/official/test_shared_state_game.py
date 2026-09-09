"""共享额度接入正式场次会话后的预算、边界取消与过期目的回归。

只通过GameSessionPort的next_item/submit/aclose、公开调度接口、传输调用和
审计验证。时间为虚拟单调秒，窗口协议片段为合成测试，不连接官方平台。
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace

import pytest

from _official_testkit import (
    FakeAuditSink,
    FakeTransport,
    TIMING,
    load_fixture,
    make_audit_context,
)
from _virtual_clock import VirtualClock
from test_sync_repair_regressions import event, snapshot

from hangma_bot.adapters.official.errors import ConflictError
from hangma_bot.adapters.official.game import OfficialGameSession
from hangma_bot.adapters.official.scheduler import RequestKind, RequestScheduler
from hangma_bot.application.contracts import (
    ActionAttempt,
    GameFinished,
    ObservedActionWindow,
    SubmitNotSent,
    SubmitRejectedRetryable,
)
from hangma_bot.kernel.actions import Pass, Peng, Tile, WindowPhase


class NoJitter:
    """只检验指定冷却时间，不引入随机附加等待。"""

    def uniform(self, lower, upper):
        return 0.0


class BudgetTransport(FakeTransport):
    """记录公开request参数，使读取预算可以和实际发起时刻独立核对。"""

    def __init__(self, clock):
        super().__init__()
        self.clock = clock
        self.started_at = []
        self.request_budgets = []

    async def request(self, *args, **kwargs):
        self.started_at.append(self.clock.monotonic())
        self.request_budgets.append(kwargs.get("request_budget_sec"))
        return await super().request(*args, **kwargs)


def make_session(clock, transport, root, audit, game_id="active"):
    return OfficialGameSession(
        game_id=game_id, transport=transport,
        scheduler=root.for_game(game_id, max_games=10), timing=TIMING,
        monotonic_clock=clock.monotonic, wall_clock_unix_ms=clock.wall_ms,
        audit=audit, audit_context=make_audit_context, retry_sleep=clock.sleep,
        max_get_retries=0,
    )


def new_scheduler(clock):
    return RequestScheduler(clock=clock.monotonic, sleep=clock.sleep, jitter_rng=NoJitter())


def response_snapshot(wall_origin_ms, *, phase="response_peng", seq=179):
    """座位1弃牌、本人座位2可响应的固定阶段，截止使用官方Unix毫秒字段。"""
    doc = snapshot(seq, turn=1, phase=phase, river=("4t",),
                   discard={"seat": 1, "tile": "4t", "seq": 179}, responders=(2,))
    doc["snapshot"]["discards"] = [[], ["4t"], [], []]
    doc["snapshot"]["window_deadline_ms"] = wall_origin_ms + (1000 if phase == "response_peng" else 2000)
    if seq > 179:
        doc["events"] = [event(number, "timeout", seat=seat,
                               data={"kind": "response", "window": "peng"})
                         for number, seat in ((180, 0), (181, 2), (182, 3)) if number <= seq]
    return doc


async def defer_peng(session, window, latest):
    outcome = await session.submit(ActionAttempt(
        decision_id="boundary-test", attempt_no=1, plan_revision=1,
        window_key=window.window_key, based_on_authoritative_seq=window.authoritative_seq,
        action=Pass(), action_key="pass", latest_send_at_monotonic=latest,
    ))
    assert isinstance(outcome, SubmitNotSent)
    assert outcome.reason == "pass_deferred_until_chi"


async def test_409_near_query_start_deadline_keeps_the_original_response_budget():
    """扣100ms网络后，0.79秒获额度仍有0.11秒读预算，不截成发起截止的0.01秒。"""
    clock, audit = VirtualClock(), FakeAuditSink()
    root = new_scheduler(clock)
    peer = root.for_game("peer", max_games=10)
    transport = BudgetTransport(clock)
    original_doc = load_fixture("state_response_snapshot_peng.json")
    original_doc["snapshot"]["window_deadline_ms"] = clock.wall_ms() + 1000
    gets = 0

    async def handler(*, method, params, **kwargs):
        nonlocal gets
        if method == "POST":
            # 另一场已确认的state限频冷却只约束查询，当前POST仍独立发出。
            peer.note_rate_limited(.79, request_kind=RequestKind.STATE)
            raise ConflictError(409, "INVALID_ACTION", "injected_rejection")
        gets += 1
        assert params["seq"] == 0
        if gets == 1:
            return 200, json.dumps(original_doc)
        assert gets == 2, "409只允许一次必要权威刷新，不追查旧历史"
        assert clock.monotonic() == pytest.approx(.79)
        assert transport.request_budgets[-1] == pytest.approx(.11)
        await clock.sleep(.05)
        return 200, json.dumps(original_doc)

    transport.handler = handler
    session = make_session(clock, transport, root, audit)
    try:
        original = await clock.run(session.next_item())
        assert isinstance(original, ObservedActionWindow)
        attempted = ActionAttempt(
            decision_id="refresh-budget", attempt_no=1, plan_revision=1,
            window_key=original.window_key, based_on_authoritative_seq=original.authoritative_seq,
            action=Peng(Tile("2w")), action_key="peng:2w", latest_send_at_monotonic=1.0,
        )
        outcome = await clock.run(session.submit(attempted))
        assert isinstance(outcome, SubmitRejectedRetryable), outcome
        assert clock.monotonic() == pytest.approx(.84)
        assert outcome.refreshed_window.window_key == original.window_key
        assert outcome.refreshed_window.expires_at_monotonic <= original.expires_at_monotonic
        timings = [record.payload["request_timing"] for record in audit.records
                   if record.payload.get("phase") == "started"
                   and record.payload.get("method") == "GET"]
        assert timings[-1]["latest_start_monotonic"] == pytest.approx(.8)
        assert timings[-1]["response_deadline_monotonic"] == pytest.approx(.9)
        clock.advance(1.0 - clock.monotonic())
        after_deadline = await session.submit(replace(attempted, attempt_no=2))
        assert isinstance(after_deadline, SubmitNotSent)
        assert "deadline" in after_deadline.reason
        assert sum(call.method == "POST" for call in transport.calls) == 1
    finally:
        await session.aclose("test_complete")


async def test_boundary_waits_for_cancelled_poll_cleanup_before_reusing_the_state_slot():
    """长轮询取消后还有异步清理；边界GET必须等清理结束，已发次数仍保留。"""
    clock, audit = VirtualClock(), FakeAuditSink()
    wall_origin = clock.wall_ms()
    clock.advance(.75)  # 仍有250ms，先在网络安全边界前本地延后碰阶段Pass
    root = new_scheduler(clock)
    transport = BudgetTransport(clock)
    sequence = []
    gets = 0

    async def handler(*, method, params, long_poll, **kwargs):
        nonlocal gets
        assert method == "GET"
        gets += 1
        if gets == 1:
            assert params["seq"] == 0
            return 200, json.dumps(response_snapshot(wall_origin))
        if gets == 2:
            assert long_poll and params["seq"] == 179
            sequence.append("poll_started")
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                sequence.append("poll_cancelled")
                raise
            finally:
                await clock.sleep(.04)
                sequence.append("poll_cleanup_done")
        assert gets == 3 and not long_poll and params["seq"] == 0
        assert sequence[-1] == "poll_cleanup_done"
        sequence.append("boundary_get_started")
        return 200, json.dumps(response_snapshot(wall_origin, phase="response_chi", seq=182))

    transport.handler = handler
    session = make_session(clock, transport, root, audit)
    try:
        first = await clock.run(session.next_item())
        await defer_peng(session, first, .99)
        second = await clock.run(session.next_item())
        assert isinstance(second, ObservedActionWindow)
        assert second.window_key.phase is WindowPhase.RESPONSE_CHI
        assert sequence == ["poll_started", "poll_cancelled", "poll_cleanup_done", "boundary_get_started"]
        assert transport.started_at[-1] == pytest.approx(1.09)
        assert root.state_used_count == 3, "取消已发长轮询不能退state次数"
        assert root.for_game("active", max_games=10).active_count == 0
        assert [call.params["seq"] for call in transport.calls] == [0, 179, 0]
        assert any(record.payload.get("outcome") == "cancelled" for record in audit.records)
    finally:
        await session.aclose("test_complete")


async def test_authoritative_response_returned_during_cancel_is_consumed_without_another_get():
    """取消与读取完成交错时，传输返回的真实响应仍必须推进事件水位。"""
    clock, audit = VirtualClock(), FakeAuditSink()
    wall_origin = clock.wall_ms()
    clock.advance(.75)
    root = new_scheduler(clock)
    transport = BudgetTransport(clock)
    returned_on_cancel = []
    gets = 0

    async def handler(*, method, params, long_poll, **kwargs):
        nonlocal gets
        assert method == "GET"
        gets += 1
        if gets == 1:
            return 200, json.dumps(response_snapshot(wall_origin))
        assert gets == 2 and long_poll and params["seq"] == 179, "已有响应后不应补发seq=0吞掉它"
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            returned_on_cancel.append(clock.monotonic())
            return 200, json.dumps(response_snapshot(wall_origin, phase="response_chi", seq=180))

    transport.handler = handler
    session = make_session(clock, transport, root, audit)
    try:
        first = await clock.run(session.next_item())
        await defer_peng(session, first, .99)
        second = await clock.run(session.next_item())
        assert isinstance(second, ObservedActionWindow)
        assert returned_on_cancel == [pytest.approx(1.05)]
        assert second.window_key.phase is WindowPhase.RESPONSE_CHI
        assert second.observation.consumed_seq == 180
        assert any(item.seq == 180 and item.kind == "timeout" for item in second.observation.public_history)
        assert len(transport.calls) == 2
        assert root.state_used_count == 2
    finally:
        await session.aclose("test_complete")


@pytest.mark.parametrize("terminal", [False, True])
async def test_expired_queued_chi_query_is_replaced_by_one_current_state_sync(terminal):
    """冷却越过吃窗时，旧查询零发送，之后仅获取当前出牌窗口或最终成绩。"""
    clock, audit = VirtualClock(), FakeAuditSink()
    wall_origin = clock.wall_ms()
    root = new_scheduler(clock)
    peer = root.for_game("peer", max_games=10)
    transport = BudgetTransport(clock)
    gets = 0

    async def handler(*, method, params, long_poll, **kwargs):
        nonlocal gets
        assert method == "GET"
        gets += 1
        if gets == 1:
            assert params["seq"] == 0
            return 200, json.dumps(response_snapshot(wall_origin))
        assert gets == 2, "过期目的不能堆成恢复查询积压"
        assert params["seq"] == 0 and not long_poll
        assert clock.monotonic() == pytest.approx(2.2), "旧chi目的不能抢在冷却/阶段结束前发送"
        if terminal:
            return 200, json.dumps(load_fixture("state_response_finished.json"))
        doc = snapshot(184, turn=2, drawn="7w", river=("4t",),
                       discard={"seat": 1, "tile": "4t", "seq": 179})
        doc["snapshot"]["discards"] = [[], ["4t"], [], []]
        doc["snapshot"]["window_deadline_ms"] = wall_origin + 5000
        return 200, json.dumps(doc)

    transport.handler = handler
    session = make_session(clock, transport, root, audit)
    try:
        first = await clock.run(session.next_item())
        await defer_peng(session, first, .5)
        peer.note_rate_limited(2.2, request_kind=RequestKind.STATE)
        current = await clock.run(session.next_item())
        if terminal:
            assert isinstance(current, GameFinished)
            assert current.final_scores == (34, 12, -6, -40)
        else:
            assert isinstance(current, ObservedActionWindow)
            assert current.window_key.phase is WindowPhase.DRAW
            assert current.window_key.trigger_seq == 184
        assert [call.params["seq"] for call in transport.calls] == [0, 0]
        expired = [record.payload for record in audit.records
                   if record.payload.get("state_query_cancel_reason") == "expired_window_purpose"]
        assert len(expired) == 1
        assert expired[0]["query_purpose"] == "phase_boundary"
        assert expired[0]["window"] == {
            "schema_version": 1, "game_id": "active", "round_no": first.window_key.round_no,
            "trigger_seq": 179, "phase": "response_chi", "seat": 2,
        }
        assert expired[0]["window_is_expected"] is True
        assert expired[0]["purpose_wait_sec"] == pytest.approx(.70)
        assert expired[0]["replacement_purpose"] == "current_state_sync"
        assert expired[0]["latest_start_monotonic"] == pytest.approx(1.75)
        assert expired[0]["obsolete_window_end_monotonic"] == pytest.approx(2.0)
        starts = [record.payload for record in audit.records
                  if record.payload.get("phase") == "started" and record.payload.get("method") == "GET"]
        assert len(starts) == 2
        assert starts[-1]["request_timing"]["query_purpose"] == "current_state_sync"
        assert root.state_used_count == 1, "只有新的现状同步在当前滚动秒内实际发送"
    finally:
        await session.aclose("test_complete")
