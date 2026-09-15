"""官方牌谱时序回放回归：吃窗口可见、窗口身份稳定、零重复提交（R1/R2）。

回放官方响应阶段时序（集成阶段第二轮热修 + 加固轮，诊断依据为官方牌谱
只读核对与测试房实测）：

1. 弃牌（seq 182）触发 response_peng，我方（座位 1）在响应座位；
2. 他家 pass 推进权威 seq（183、184）——响应窗口固定走满期间快照 seq
   前进；测试房实测响应阶段 last_discard 为纯牌码字符串（无 seq），且
   旧实现每次交付前全量重建会清空事件历史。本回放全部用纯牌码形态：旧实现会
   退回快照 seq，为同一物理窗口产出多个 WindowKey（R2：重复提交 pass
   -> 409 级联）；加固后的跨重建触发弃牌记忆（由 tile_discarded 事件
   写入）保证 seq 182->185 期间 WindowKey 恒为 trigger_seq=182；
3. response_peng -> response_chi 的阶段切换不产生任何增量事件（R1：旧实现
   长轮询等不到事件，等看到 chi 的 timeout 事件时窗口已结束）——本回放
   中该段长轮询永久挂起，由阶段边界定时器竞速取胜后主动 seq=0 刷新捕获
   chi 窗口；
4. 碰阶段选择 pass 仅本地延后；我方在真实吃响应座位时捕获吃窗口，
   此时提交 pass；随后权威事件推进到 draw 阶段。

断言：触发窗口唯一 WindowKey(trigger_seq=182)；吃窗口可见；同物理窗口
零重复提交（每窗最多一次 POST、绝无重复交付）；全程无触发序号退化提示
（记忆命中，未退回快照 seq）。
"""
from __future__ import annotations

import asyncio
import json

from hangma_bot.adapters.official.errors import UncertainTransportError
from hangma_bot.application.contracts import (
    ActionAttempt,
    GameFailed,
    ObservedActionWindow,
    SubmitAccepted,
    SubmitNotSent,
)
from hangma_bot.kernel.actions import Pass, Tile, WindowKey, WindowPhase
from hangma_bot.kernel.observation import PublicDiscard

from _official_testkit import FakeAuditSink, FakeTransport, make_game_session

GAME = "g_room1_batch1"

_HAND = ["4w", "5w", "7b", "8b", "9b", "东", "东", "南", "西", "北", "中", "发", "白"]

# 测试房实测形态：响应阶段 last_discard 为纯牌码字符串（无结构化 seq）
_BARE_6W = "6w"


def _snap(
    seq: int,
    *,
    phase: str,
    turn: int,
    responding: tuple,
    last_discard,
    drawn_tile: str = "",
) -> dict:
    """按官方快照形状构造回放快照（我方固定座位 1）。"""

    return {
        "seq": seq,
        "snapshot": {
            "seat": 1,
            "phase": phase,
            "turn": turn,
            "responding_seats": list(responding),
            "dealer": 0,
            "round_no": 1,
            "drawn_tile": drawn_tile,
            "my_hand": list(_HAND),
            "wall_remaining": 30,
            "scores": [0, 0, 0, 0],
            "last_discard": last_discard,
            "discards": [["6w"], ["1b"], [], []],
            "melds": [[], [], [], []],
            "hand_counts": [13, 13, 13, 13],
            "god": {"baotou": False, "chain_count": 0, "catch_play": False},
        },
    }


def _events(*entries: dict) -> dict:
    return {"events": list(entries)}


def _event(seq: int, type_: str, seat: int, tile: str = "") -> dict:
    entry = {"seq": seq, "type": type_, "seat": seat}
    if tile:
        entry["tile"] = tile
    return entry


def _attempt(window: WindowKey, attempt_no: int = 1) -> ActionAttempt:
    return ActionAttempt(
        decision_id="d-1",
        attempt_no=attempt_no,
        plan_revision=1,
        window_key=window,
        based_on_authoritative_seq=window.trigger_seq,
        action=Pass(),
        action_key="pass",
        latest_send_at_monotonic=1_000_000.0,
    )


async def test_official_replay_response_chi_window(transport: FakeTransport, clock, audit: FakeAuditSink) -> None:
    """官方牌谱时序回放（纯牌码 last_discard）：吃窗口可见、身份稳定、零重复提交。"""

    snapshots = [
        _snap(
            180,
            phase="draw",
            turn=0,
            responding=(),
            last_discard={"seat": 3, "tile": "1t", "seq": 179},
        ),
        # 弃牌（182）后的 peng 窗口：纯牌码 last_discard（测试房实测形态）
        _snap(
            182,
            phase="response_peng",
            turn=0,
            responding=(1, 2, 3),
            last_discard=_BARE_6W,
        ),
        # 他家 pass 推进 seq 到 184：同一物理 peng 窗口仍对我方开放
        _snap(
            184,
            phase="response_peng",
            turn=0,
            responding=(1,),
            last_discard=_BARE_6W,
        ),
        # 无事件阶段切换后的 chi 窗口（边界定时刷新捕获），仍为纯牌码
        _snap(
            185,
            phase="response_chi",
            turn=0,
            responding=(1,),
            last_discard=_BARE_6W,
        ),
        _snap(
            187,
            phase="draw",
            turn=2,
            responding=(),
            last_discard={"seat": 1, "tile": "1b", "seq": 186},
            drawn_tile="9t",
        ),
    ]
    posts = []
    seq187_polls = {"n": 0}

    async def handler(*, method: str, path: str, params=None, json_body=None, long_poll=False):
        if method == "POST":
            posts.append(dict(json_body))
            return 200, "{}"
        seq = (params or {}).get("seq")
        if seq == 0:
            return 200, json.dumps(snapshots.pop(0))
        if seq == 180:
            return 200, json.dumps(
                _events(_event(181, "tile_drawn", 0, "1w"), _event(182, "tile_discarded", 0, "6w"))
            )
        if seq == 182:
            return 200, json.dumps(_events(_event(183, "pass", 2), _event(184, "pass", 3)))
        if seq == 184:
            # 快照185已交付吃窗口；普通查询补旧事件，并带回之后的新事件。
            return 200, json.dumps(_events(_event(185, "pass", 3),
                _event(186, "pass", 1), _event(187, "tile_drawn", 2)))
        if seq == 187:
            seq187_polls["n"] += 1
            if seq187_polls["n"] == 1:
                return 200, json.dumps({"pending": True})
            raise UncertainTransportError("timeout:ReadTimeout")
        raise AssertionError("unexpected seq poll: {0}".format(seq))

    transport.handler = handler
    session = make_game_session(transport=transport, clock=clock, audit=audit)

    item1 = await asyncio.wait_for(session.next_item(), timeout=2)
    assert isinstance(item1, ObservedActionWindow)
    peng_key = item1.window_key
    assert peng_key == WindowKey(GAME, 1, 182, WindowPhase.RESPONSE_PENG, 1)
    assert item1.authoritative_seq == 182
    assert item1.timeout_seconds == 1.0
    # 纯牌码 last_discard 按响应阶段语义重建（turn=0 即弃牌者）
    assert item1.observation.last_discard == PublicDiscard(seat=0, tile=Tile("6w"), seq=182)

    deferred = await session.submit(_attempt(peng_key))
    assert isinstance(deferred, SubmitNotSent)
    assert deferred.reason == "pass_deferred_until_chi"
    assert posts == []

    item2 = await asyncio.wait_for(session.next_item(), timeout=2)
    assert isinstance(item2, ObservedActionWindow)
    chi_key = item2.window_key
    # b) 我方在响应座位时吃窗口被捕获；a) 触发窗口的唯一 WindowKey(trigger_seq=182)
    assert chi_key == WindowKey(GAME, 1, 182, WindowPhase.RESPONSE_CHI, 1)
    assert chi_key != peng_key
    assert item2.authoritative_seq == 185
    assert item2.timeout_seconds == 1.0
    assert item2.observation.last_discard == PublicDiscard(seat=0, tile=Tile("6w"), seq=185)
    assert item2.observation.responding_seats == (1,)
    assert item2.observation.drawn_tile is None

    # peng 窗口在 seq=184 快照（我方仍在响应座位）时没有被重复交付
    assert posts == []
    calls = [(c.params or {}).get("seq") for c in transport.calls]
    assert 184 not in calls  # 临近边界直接查快照，不再先占一次会被取消的增量额度。
    assert calls.count(0) == 4

    outcome = await asyncio.wait_for(session.submit(_attempt(chi_key)), timeout=2)
    assert isinstance(outcome, SubmitAccepted)
    assert posts == [{"action": "pass", "tile": ""}]
    again = await asyncio.wait_for(session.submit(_attempt(chi_key, attempt_no=2)), timeout=2)
    assert isinstance(again, SubmitNotSent)
    assert again.reason == "window_already_finalized"
    assert posts == [{"action": "pass", "tile": ""}]

    item3 = await asyncio.wait_for(session.next_item(), timeout=2)
    assert isinstance(item3, GameFailed)
    assert item3.recoverable is True
    assert item3.reason == "get_exhausted"

    # 全程无触发序号退化提示：纯牌码窗口的触发序号全部由跨重建记忆命中
    notes = [
        record for record in audit.records if "trigger_seq_projection_note" in record.payload
    ]
    assert notes == []


async def test_draw_phase_does_not_arm_boundary_timer(transport: FakeTransport, clock) -> None:
    """draw 阶段维持现状：pending 轮询不产生阶段边界 seq=0 刷新。"""

    pending_polls = {"n": 0}

    async def handler(*, method: str, path: str, params=None, json_body=None, long_poll=False):
        seq = (params or {}).get("seq")
        if seq == 0:
            return 200, json.dumps(
                _snap(180, phase="draw", turn=0, responding=(), last_discard=None)
            )
        pending_polls["n"] += 1
        if pending_polls["n"] <= 2:
            return 200, json.dumps({"pending": True})
        raise UncertainTransportError("timeout:ReadTimeout")

    transport.handler = handler
    session = make_game_session(transport=transport, clock=clock)
    item = await asyncio.wait_for(session.next_item(), timeout=2)
    assert isinstance(item, GameFailed)
    assert item.reason == "get_exhausted"
    calls = [(c.params or {}).get("seq") for c in transport.calls]
    assert calls.count(0) == 1
