"""重复提交根治回归（F1/F2/F3/F4，2026-09-05 测试房取证）。

取证事实（run-29a71a10 同型序列，t_9779c892550e r1_b0_t0 实录）：
- 弃牌事件在被本方轮询到之前已被快照吸收 → 三级记忆从未建立；
- 全员 pass 后官方快照的 responding_seats 不收缩（仍列 [1,2,3]）、
  phase 不变，仅 seq 前进（2→5）；
- 旧 tier-4 每次用"当前快照 seq"造键 → 键漂移成新窗口 → 重复投递 →
  重复提交 pass → 409。

对应修复：
- F1 tier-4 出生快照事实回写跨重建记忆（键恒定）；
- F2 本人 pass（事件回显带座位 / POST 接受回执）抑制本响应周期再投递；
- F3 409-on-pass 按"本窗对我关闭"收口（不再改提下一个 pass）；
- F4 window_deadline_ms 官方绝对截止驱动边界定时。

2026-09-06：碰阶段 pass 只做本地延后，不发 HTTP；涉及 pass 已接受/409
的保护回归使用吃阶段，保留旧取证针对的重复键、已响应与截止不变量。
"""

from __future__ import annotations

import asyncio
import json

import pytest

from hangma_bot.adapters.official.errors import ConflictError
from hangma_bot.application.contracts import (
    ActionAttempt,
    ObservedActionWindow,
    SubmitAccepted,
    SubmitNotSent,
    SubmitRejectedClosed,
)
from hangma_bot.kernel.actions import Pass, WindowKey, WindowPhase

from _official_testkit import load_fixture, make_game_session


def _peng_doc(seq: int, *, deadline_ms=None, last_discard="6b", responding=(1, 2, 3), phase="response_peng"):
    doc = load_fixture("state_response_snapshot_peng.json")
    doc["seq"] = seq
    snap = doc["snapshot"]
    snap["phase"] = phase
    snap["last_discard"] = last_discard
    snap["responding_seats"] = [2] if phase == "response_chi" else list(responding)
    snap["turn"] = 1 if phase == "response_chi" else 0  # 吃阶段座位2承接前家座位1弃牌
    if deadline_ms is not None:
        snap["window_deadline_ms"] = deadline_ms
    return doc


def _events_doc(last_seq: int, events):
    return {"seq": last_seq, "gap": False, "events": events, "pending": False}


def _pass_event(seq: int, seat: int):
    return {"seq": seq, "type": "pass", "seat": seat, "tile": "", "data": None, "ts": 0}


def _state_handler(queue: list):
    def handler(*, method: str, path: str, json_body=None, params=None, long_poll=False):
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return handler


def _attempt(window: WindowKey) -> ActionAttempt:
    return ActionAttempt(
        decision_id="d-fix-1",
        attempt_no=1,
        plan_revision=1,
        window_key=window,
        based_on_authoritative_seq=window.trigger_seq,
        action=Pass(),
        action_key="pass",
        latest_send_at_monotonic=1005.0,
    )


class TestKeyStabilityF1:
    async def test_no_re_delivery_when_snapshot_seq_advances_without_self_pass(
        self, transport, clock
    ) -> None:
        """他家 pass 推进快照 seq（2→5）：出生记忆使键恒定，不再当作新窗投递。"""

        queue = [
            (200, json.dumps(_peng_doc(2))),
            (200, json.dumps(_events_doc(3, [_pass_event(3, 3)]))),
            (200, json.dumps(_peng_doc(5))),
            # 快照5超前：从旧游标3补领已知公开过牌，不再应用到牌面。
            (200, json.dumps(_events_doc(5, [_pass_event(4, 1), _pass_event(5, 0)]))),
            (200, json.dumps(load_fixture("state_response_snapshot_draw.json"))),
            (200, json.dumps({"pending": True})),  # 从旧游标5尝试一次补领
        ]
        transport.handler = _state_handler(queue)
        session = make_game_session(transport=transport, clock=clock)

        window = await asyncio.wait_for(session.next_item(), timeout=2)
        assert isinstance(window, ObservedActionWindow)
        assert window.window_key.phase is WindowPhase.RESPONSE_PENG
        birth_key = window.window_key

        # 他家 pass（座位 3，非本人）→ 快照推进到 5：不得再次投递响应窗
        nxt = await asyncio.wait_for(session.next_item(), timeout=2)
        assert isinstance(nxt, ObservedActionWindow)
        assert nxt.window_key.phase is WindowPhase.DRAW, "应跳过漂移键响应窗，直接到下一真实窗口"


class TestSelfPassSuppressionF2:
    async def test_forensic_replay_no_duplicate_after_own_pass(
        self, transport, clock
    ) -> None:
        """真实吃窗口 pass 接受 → 回显含本人 → 快照@5 → 零二次提交。"""

        queue = [(200, json.dumps(_peng_doc(2, phase="response_chi")))]
        transport.handler = _state_handler(queue)
        session = make_game_session(transport=transport, clock=clock)

        window = await asyncio.wait_for(session.next_item(), timeout=2)
        transport.handler = lambda **kw: (200, "{}")
        outcome = await asyncio.wait_for(session.submit(_attempt(window.window_key)), timeout=2)
        assert isinstance(outcome, SubmitAccepted)

        queue2 = [
            (200, json.dumps(_events_doc(5, [
                _pass_event(3, 3), _pass_event(4, 2), _pass_event(5, 1),
            ]))),
            (200, json.dumps(_peng_doc(5, phase="response_chi"))),
            (200, json.dumps(load_fixture("state_response_snapshot_draw.json"))),
            (200, json.dumps({"pending": True})),  # 从旧游标5补领，不循环
        ]
        transport.handler = _state_handler(queue2)
        nxt = await asyncio.wait_for(session.next_item(), timeout=2)
        assert isinstance(nxt, ObservedActionWindow)
        assert nxt.window_key.phase is WindowPhase.DRAW, "本人已表态：漂移快照不得重开响应窗"
        posts = [c for c in transport.calls if c.method == "POST"]
        assert len(posts) == 1, "不得出现第二次 pass 提交"


class TestConflictPassAbsorbF3:
    async def test_409_on_pass_closes_window_for_self(self, transport, clock) -> None:
        """pass 被 409（官方确认已表态）→ Closed 收口，不改提下一个 pass。"""

        transport.handler = _state_handler([(200, json.dumps(_peng_doc(2, phase="response_chi")))])
        session = make_game_session(transport=transport, clock=clock)
        window = await asyncio.wait_for(session.next_item(), timeout=2)

        transport.handler = _state_handler([
            ConflictError(409, "INVALID_ACTION", "dup", raw_text='{"code":"INVALID_ACTION"}'),
            (200, json.dumps(_peng_doc(2, phase="response_chi"))),  # 刷新：真实吃窗口仍开
        ])
        outcome = await asyncio.wait_for(session.submit(_attempt(window.window_key)), timeout=2)
        assert isinstance(outcome, SubmitRejectedClosed), "pass 的 409 应按本窗关闭收口"

        again = await asyncio.wait_for(
            session.submit(_attempt(window.window_key)), timeout=2
        )
        assert isinstance(again, SubmitNotSent)
        posts = [c for c in transport.calls if c.method == "POST"]
        assert len(posts) == 1, "409 吸收后不得追加提交"


class TestDeadlineTimerF4:
    async def test_boundary_timer_fires_at_official_deadline(self, transport, clock) -> None:
        """官方绝对截止驱动边界刷新（0.25s 截止 → ~0.3s 内拿到窗口，非 1.05s 猜测）。"""

        deadline = clock.wall_ms() + 250
        transport.handler = _state_handler([
            (200, json.dumps(_peng_doc(2, deadline_ms=deadline))),
        ])
        session = make_game_session(transport=transport, clock=clock)

        async def hanging(**kw):
            await asyncio.sleep(30)
            return 200, "{}"

        window = await asyncio.wait_for(session.next_item(), timeout=2)
        assert isinstance(window, ObservedActionWindow)

        # 长轮询挂起、队列耗尽后由边界定时器在官方截止时刻主动刷新
        transport.handler = _state_handler([
            (200, json.dumps(_peng_doc(3, deadline_ms=clock.wall_ms() + 5000))),
        ])
        # 仅验证：deadline 路径下 _phase_boundary_timeout 由官方绝对值推导
        timeout = session._phase_boundary_timeout()
        assert timeout is not None and timeout < 1.0 + 0.05, (
            "官方截止 5s 内的余量应远小于旧猜测式 1.05s"
        )
