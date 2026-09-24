"""SSE 帧驱动"自唤醒"回归（2026-09-05 r5 取证：暗杠后出牌窗被代打）。

机制（取证时间线 t_9779c892550e r5_b1_t0）：
  t0      暗杠提交接受（事件 gang@341 + 杠上补牌@342 由我方动作产生）
  0~3s    服务端对本人动作事件不推 SSE 帧 → 帧等待挂 5s 静默 > 3s 出牌窗
  +3013ms 超时代打（timeout@344）才有帧唤醒——窗口已丢
修复：自己的动作被 SubmitAccepted 后立即 set 帧事件（自唤醒 → 短拉增量
拿到 341/342 → 刷新 → 投递补牌后的出牌窗）。
"""

from __future__ import annotations

import asyncio
import json

from hangma_bot.adapters.official import game as game_module
from hangma_bot.application.contracts import (
    ActionAttempt,
    ObservedActionWindow,
    SubmitAccepted,
)
from hangma_bot.kernel.actions import Discard, Tile, WindowPhase

from _official_testkit import FakeClock, FakeTransport, TIMING, load_fixture, make_audit_context
from hangma_bot.adapters.official.game import OfficialGameSession
from hangma_bot.adapters.official.scheduler import RequestScheduler


class InitialFrameOnlyClient:
    """SSE 替身：连接时推一条初始帧（官方真实行为），此后永不推帧
    （模拟"服务端不推本人动作事件"的取证场景）。"""

    def __init__(self, game_id, transport, *, budget=None, on_frame=None, on_event=None, config=None, **kw):
        self.on_frame = on_frame

    async def run(self):
        # 初始帧（包含式水位，仅作唤醒信号）
        if self.on_frame is not None:
            await self.on_frame(_Frame(seq=1))
        await asyncio.Event().wait()  # 挂起直到取消

    async def aclose(self):
        return None


class _Frame:
    def __init__(self, seq, closed=False):
        self.seq = seq
        self.closed = closed


def _instant_sleep(clock):
    async def _sleep(seconds):
        clock.advance(seconds)
    return _sleep


def _make(transport, clock, *, sse):
    return OfficialGameSession(
        game_id="g_room1_batch1", transport=transport,
        scheduler=RequestScheduler(clock=clock.monotonic, sleep=_instant_sleep(clock)),
        timing=TIMING, monotonic_clock=clock.monotonic, wall_clock_unix_ms=clock.wall_ms,
        audit=None, audit_context=make_audit_context, retry_sleep=_instant_sleep(clock),
        sse_enabled=sse,
    )


def _attempt(window, action_key="discard:5w"):
    return ActionAttempt(
        decision_id="d-wake-1", attempt_no=1, plan_revision=1,
        window_key=window.window_key, based_on_authoritative_seq=window.window_key.trigger_seq,
        action=Discard(Tile("5w")), action_key=action_key, latest_send_at_monotonic=1005.0,
    )


class TestSelfWakeAfterOwnAction:
    async def test_accepted_submission_sets_sse_event(self, monkeypatch) -> None:
        """单元：SubmitAccepted 后帧事件必须被置位（自唤醒）。"""

        monkeypatch.setattr(game_module, "SSENotifyClient", InitialFrameOnlyClient)
        draw_doc = load_fixture("state_response_snapshot_draw.json")
        transport = FakeTransport()
        transport.handler = lambda **kw: (200, json.dumps(draw_doc))
        clock = FakeClock()
        session = _make(transport, clock, sse=True)

        window = await asyncio.wait_for(session.next_item(), timeout=2)
        assert isinstance(window, ObservedActionWindow)
        session._sse_event.clear()  # 消费初始帧唤醒

        transport.handler = lambda **kw: (200, "{}")
        outcome = await asyncio.wait_for(session.submit(_attempt(window)), timeout=2)
        assert isinstance(outcome, SubmitAccepted)
        assert session._sse_event.is_set(), "动作被接受后必须自唤醒（不等帧）"
        await session.aclose("t")

    async def test_own_action_window_delivered_without_any_frame(self, monkeypatch) -> None:
        """行为：无任何后续帧时，接受弃牌 → 自唤醒短拉 → 下一窗口照常投递。"""

        monkeypatch.setattr(game_module, "SSENotifyClient", InitialFrameOnlyClient)
        draw_doc = load_fixture("state_response_snapshot_draw.json")
        monkeypatch.setattr(game_module, "_SSE_OWN_DISCARD_PROBE_SEC", 0.01)
        # 完全无后续通知时，本人动作探针直接取权威快照，不挂长轮询。
        refreshed = load_fixture("state_response_snapshot_draw.json")
        refreshed["seq"] = 103  # 刷新快照水位推进到新事件之后
        queue = [(200, json.dumps(draw_doc)), (200, "{}"), (200, json.dumps(refreshed))]

        def handler(*, method, path, json_body=None, params=None, long_poll=False):
            return queue.pop(0)

        transport = FakeTransport()
        transport.handler = handler
        clock = FakeClock()
        session = _make(transport, clock, sse=True)

        window = await asyncio.wait_for(session.next_item(), timeout=2)
        assert window.window_key.phase is WindowPhase.DRAW
        # 初始帧唤醒已被消费；此后替身不再推任何帧
        outcome = await asyncio.wait_for(session.submit(_attempt(window)), timeout=2)
        assert isinstance(outcome, SubmitAccepted)

        nxt = await asyncio.wait_for(session.next_item(), timeout=2)
        assert isinstance(nxt, ObservedActionWindow), (
            "无帧场景：自唤醒必须让下一窗口在远小于 5s 静默周期内投递"
        )
        await session.aclose("t")
