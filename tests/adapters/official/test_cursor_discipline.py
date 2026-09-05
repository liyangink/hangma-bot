"""游标纪律回归测试：增量摸牌送达零重建、取消/重连不回退、v10 边界恰好一次快照、POST 后游标语义。

背景（2026-09-04 官方测试赛 t_dee58824c308 实测）：protocol_recovered 3063 次，
其中 rebuild_snapshot_gap（v10 跨局 gap 快照）531 次且同一边界重复 5~47 次；
全部 120 次胡牌决策都发生在重建后的快照路径上——摸牌事件的送达常态性依赖
全量快照而非增量事件。本文件证明修复后的游标纪律：

- 官方依据（指南 v14 §2.1）：「客户端局面 = 快照 + 后续增量事件」「事件流
  只含自己的摸牌」「游标永远是本地已消费 seq」；v10 跨局规则「seq 落后当前局
  （round_ended 后新局已发牌、不产生事件）→ 立即返回全量快照（gap:true）」。
- 断言口径：重建次数 = 审计 PROTOCOL_RECOVERED 计数 + 传输层 seq=0 请求计数，
  不新增任何公共接口（tests/AGENTS：只通过公开接口验证行为）。
"""
from __future__ import annotations

import asyncio
import json

import pytest

from hangma_bot.application.contracts import (
    ActionAttempt,
    AuditKind,
    ObservedActionWindow,
    SubmitAccepted,
    SubmitNotSent,
)
from hangma_bot.kernel.actions import Discard, Tile, WindowKey, WindowPhase
from hangma_bot.kernel.observation import PublicDiscard

from _official_testkit import make_game_session, load_fixture

GAME = "g_room1_batch1"
MY_SEAT = 2  # state_response_snapshot_draw.json 的官方座位
_HAND = ["1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "东", "东", "南", "白"]


def _json(doc: dict):
    return 200, json.dumps(doc)


def _event(seq: int, type_: str, seat: int, tile: str = "") -> dict:
    entry = {"seq": seq, "type": type_, "seat": seat, "data": {}}
    if tile:
        entry["tile"] = tile
    return entry


def _events(*entries: dict) -> dict:
    return {"events": list(entries)}


def _snapshot_doc(seq: int, *, turn: int, round_no: int = 1, my_hand=None, drawn: str = "", gap: bool = False) -> dict:
    """基于官方 v8 快照 fixture 构造回放快照（我方固定座位 2）。"""

    doc = load_fixture("state_response_snapshot_draw.json")
    doc["seq"] = seq
    doc["gap"] = gap
    doc["snapshot"]["turn"] = turn
    doc["snapshot"]["round_no"] = round_no
    doc["snapshot"]["drawn_tile"] = drawn
    if my_hand is not None:
        doc["snapshot"]["my_hand"] = list(my_hand)
    return doc


def _attempt(window: WindowKey, tile: str, *, trigger: int = 101, attempt_no: int = 1) -> ActionAttempt:
    return ActionAttempt(
        decision_id="d-1",
        attempt_no=attempt_no,
        plan_revision=1,
        window_key=window,
        based_on_authoritative_seq=trigger,
        action=Discard(Tile(tile)),
        action_key="discard:" + tile,
        latest_send_at_monotonic=1_005.0,
    )


def _recovered_gap_count(audit) -> int:
    """审计口径的 v10 跨局 gap 快照重建计数。"""

    return len(
        [
            r
            for r in audit.records
            if r.kind is AuditKind.PROTOCOL_RECOVERED
            and r.payload.get("trigger") == "rebuild_snapshot_gap"
        ]
    )


async def test_consecutive_draws_delivered_incrementally_zero_rebuilds(transport, clock, audit):
    """N 次连续本人摸牌增量事件全部由增量路径送达，重建数为 0。

    官方语义：摸牌事件是事件流最后一条时，本人处于摸牌窗口；交付不需要
    任何 seq=0 全量快照（修复前每个增量批后强制一次 seq=0，摸牌送达常态性
    依赖快照）。
    """

    base = _snapshot_doc(101, turn=0)  # 首快照无窗（他人回合）
    stage = {"n": 0}

    def handler(*, method: str, path: str, params=None, json_body=None, long_poll=False):
        if method == "POST":
            return 200, "{}"
        seq = (params or {}).get("seq")
        stage["n"] += 1
        if stage["n"] == 1:
            return _json(base)
        # 第 2~6 次调用：连续的本人摸牌增量（游标 101→105，事件 102~106）
        assert 101 <= seq <= 105, "轮询游标必须按已消费 seq 推进"
        return _json(_events(_event(seq + 1, "tile_drawn", MY_SEAT, "{}w".format(seq - 98))))

    transport.handler = handler
    session = make_game_session(transport=transport, clock=clock, audit=audit)

    drawn_triggers = []
    for _ in range(5):
        item = await asyncio.wait_for(session.next_item(), timeout=2)
        assert isinstance(item, ObservedActionWindow)
        assert item.window_key.phase is WindowPhase.DRAW
        assert item.window_key.seat == MY_SEAT
        drawn_triggers.append(item.window_key.trigger_seq)
        assert item.observation.drawn_tile is not None
        # 增量送达：手牌与最后快照一致（本人改牌动作全部落在刷新触发集）
        assert [t.code for t in item.observation.my_hand] == _HAND

    assert drawn_triggers == [102, 103, 104, 105, 106]
    get_calls = [c.params["seq"] for c in transport.calls if c.method == "GET"]
    assert get_calls == [0, 101, 102, 103, 104, 105]  # 仅首拉 seq=0，零重建请求
    assert get_calls.count(0) == 1
    assert _recovered_gap_count(audit) == 0
    assert all(r.kind is not AuditKind.PROTOCOL_RECOVERED for r in audit.records)


async def test_poll_cancel_reconnect_cursor_never_regresses(transport, clock):
    """轮内模拟轮询取消后重连：游标保持本地已消费 seq，不回退到 0。"""

    base = _snapshot_doc(101, turn=0)
    stage = {"n": 0}
    hanging = asyncio.Event()

    async def handler(*, method: str, path: str, params=None, json_body=None, long_poll=False):
        if method == "POST":
            return 200, "{}"
        seq = (params or {}).get("seq")
        stage["n"] += 1
        if stage["n"] == 1:
            return _json(base)
        if stage["n"] == 2:
            assert seq == 101
            return _json(_events(_event(102, "tile_drawn", 0)))  # 他家摸牌：无窗无刷新
        if stage["n"] == 3:
            hanging.set()
            await asyncio.sleep(30)  # 挂起长轮询：被外部取消
            return _json({"pending": True})
        if stage["n"] == 4:
            assert seq == 102, "重连后的轮询必须沿用取消前游标，不得回退"
            return _json(_events(_event(103, "tile_drawn", 1)))
        await asyncio.sleep(30)
        return _json({"pending": True})

    transport.handler = handler
    session = make_game_session(transport=transport, clock=clock)

    task = asyncio.ensure_future(session.next_item())
    await asyncio.wait_for(hanging.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # 重连：同一会话再次轮询；游标必须仍是取消前的 102
    task2 = asyncio.ensure_future(session.next_item())
    await asyncio.sleep(0.1)
    task2.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task2

    get_calls = [c.params["seq"] for c in transport.calls if c.method == "GET"]
    # 取消前挂起于 seq=102；重连后首次轮询仍用 102（不回退 0），再按新游标 103
    assert get_calls == [0, 101, 102, 102, 103]
    assert session._sync.last_seq == 103  # 内部游标同样只进不退


async def test_v10_boundary_exactly_one_snapshot_then_incremental(transport, clock, audit):
    """v10 跨局边界：恰好一次 gap 快照吸收后立即恢复增量，无重建风暴。"""

    base = _snapshot_doc(101, turn=0)
    boundary = _snapshot_doc(130, turn=0, round_no=2, gap=True)  # 新局已发牌、无事件
    stage = {"n": 0}

    def handler(*, method: str, path: str, params=None, json_body=None, long_poll=False):
        if method == "POST":
            return 200, "{}"
        seq = (params or {}).get("seq")
        stage["n"] += 1
        if stage["n"] == 1:
            return _json(base)
        if stage["n"] == 2:
            assert seq == 101  # 局终后仍以旧 seq 轮询：官方直接回 gap 快照（v10）
            return _json(boundary)
        if stage["n"] == 3:
            assert seq == 130  # 快照为包含式水位：消费后游标设为 130，恢复增量
            return _json(_events(_event(131, "tile_drawn", MY_SEAT, "7w")))
        raise AssertionError("边界吸收后不应再有任何全量请求: stage={}".format(stage["n"]))

    transport.handler = handler
    session = make_game_session(transport=transport, clock=clock, audit=audit)

    item = await asyncio.wait_for(session.next_item(), timeout=2)
    assert isinstance(item, ObservedActionWindow)
    assert item.window_key.round_no == 2
    assert item.window_key.trigger_seq == 131  # 增量摸牌事件的真实触发序号
    assert item.window_key.phase is WindowPhase.DRAW
    assert item.observation.drawn_tile == Tile("7w")

    get_calls = [c.params["seq"] for c in transport.calls if c.method == "GET"]
    assert get_calls == [0, 101, 130]
    assert get_calls.count(0) == 1
    assert _recovered_gap_count(audit) == 1  # 恰好一次边界快照，且这是唯一重建


async def test_v10_boundary_no_progress_backoff_bounded(transport, clock, audit):
    """v10 边界无进度快照：前 2 次原速后指数退避，不再同 seq 重复刷爆（实测 5~47 次）。"""

    base = _snapshot_doc(101, turn=0)
    stall = _snapshot_doc(101, turn=0, round_no=2, gap=True)  # 新局首事件未产生：水位不变
    progress = _snapshot_doc(200, turn=0, round_no=2, gap=True)  # 首事件已产生：水位前进
    stage = {"n": 0}
    stall_polls = {"n": 0}

    def handler(*, method: str, path: str, params=None, json_body=None, long_poll=False):
        if method == "POST":
            return 200, "{}"
        seq = (params or {}).get("seq")
        stage["n"] += 1
        if stage["n"] == 1:
            return _json(base)
        if stage["n"] <= 7:
            assert seq == 101
            stall_polls["n"] += 1
            return _json(stall)  # 连续 6 次无进度 gap 快照
        if stage["n"] == 8:
            assert seq == 101
            return _json(progress)  # 新局首事件已发生：快照水位前进，退避立即清零
        if stage["n"] == 9:
            assert seq == 200
            return _json(_events(_event(201, "tile_drawn", MY_SEAT, "8w")))
        raise AssertionError("unexpected stage={}".format(stage["n"]))

    transport.handler = handler
    session = make_game_session(transport=transport, clock=clock, audit=audit)

    start = clock.monotonic()
    item = await asyncio.wait_for(session.next_item(), timeout=5)
    assert isinstance(item, ObservedActionWindow)
    assert item.window_key.trigger_seq == 201

    elapsed = clock.monotonic() - start
    # 第 1~2 次无进度快照原速轮询（不延迟边界后响应窗口发现），第 3~6 次
    # 按 (0.5, 1.0, 2.0, 2.0) 退避：假时钟精确推进 5.5 秒
    assert elapsed == pytest.approx(0.5 + 1.0 + 2.0 + 2.0)
    assert stall_polls["n"] == 6
    assert _recovered_gap_count(audit) == 7  # 6 次无进度 + 1 次前进，总量有界


async def test_post_keeps_cursor_at_last_consumed_seq(transport, clock):
    """动作 POST 完成后游标语义：不重置为 0，动作效果由后续增量事件送达。"""

    base = _snapshot_doc(101, turn=MY_SEAT)  # 本人 draw 窗口（turn=seat）
    refreshed = _snapshot_doc(103, turn=0)  # 出牌后：无窗
    stage = {"n": 0}

    async def handler(*, method: str, path: str, params=None, json_body=None, long_poll=False):
        if method == "POST":
            return 200, "{}"
        seq = (params or {}).get("seq")
        stage["n"] += 1
        if stage["n"] == 1:
            return _json(base)
        if stage["n"] == 2:
            assert seq == 101, "POST 后游标必须是本地已消费的最后 seq（101），不是 0"
            return _json(
                _events(
                    _event(102, "tile_discarded", MY_SEAT, "5w"),
                    _event(103, "tile_drawn", 0),
                )
            )
        if stage["n"] == 3:
            assert seq == 0  # 本人弃牌触发权威刷新（手牌/神位状态新鲜化）
            return _json(refreshed)
        if stage["n"] == 4:
            assert seq == 103  # 刷新后按快照包含式水位继续增量
            return _json({"pending": True})
        await asyncio.sleep(30)  # 后续轮询挂起：测试取消
        return _json({"pending": True})

    transport.handler = handler
    session = make_game_session(transport=transport, clock=clock)

    window = await asyncio.wait_for(session.next_item(), timeout=2)
    assert isinstance(window, ObservedActionWindow)
    assert window.window_key.phase is WindowPhase.DRAW
    outcome = await asyncio.wait_for(
        session.submit(_attempt(window.window_key, "5w", trigger=window.window_key.trigger_seq)),
        timeout=2,
    )
    assert isinstance(outcome, SubmitAccepted)

    # 消费 POST 产生的增量：本人弃牌触发刷新、按新水位继续轮询
    task = asyncio.ensure_future(session.next_item())
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    get_calls = [c.params["seq"] for c in transport.calls if c.method == "GET"]
    # 首拉 seq=0 → POST 后增量轮询用 101（不回退 0）→ 本人弃牌触发刷新(0) →
    # 按快照水位 103 继续增量（pending 后原游标重拉同样 103）
    assert get_calls[:4] == [0, 101, 0, 103]
    assert all(seq == 103 for seq in get_calls[4:])


async def test_submit_on_incremental_draw_window_accepted(transport, clock):
    """增量摸牌窗口的提交复核能识别窗口身份（否则全部被 stale_window 本地拒绝）。"""

    base = _snapshot_doc(101, turn=0)
    stage = {"n": 0}

    def handler(*, method: str, path: str, params=None, json_body=None, long_poll=False):
        if method == "POST":
            return 200, "{}"
        seq = (params or {}).get("seq")
        stage["n"] += 1
        if stage["n"] == 1:
            return _json(base)
        if stage["n"] == 2:
            return _json(_events(_event(102, "tile_drawn", MY_SEAT, "1w")))
        raise AssertionError("unexpected stage={}".format(stage["n"]))

    transport.handler = handler
    session = make_game_session(transport=transport, clock=clock)

    window = await asyncio.wait_for(session.next_item(), timeout=2)
    assert isinstance(window, ObservedActionWindow)
    assert window.window_key.trigger_seq == 102
    assert window.observation.drawn_tile == Tile("1w")

    outcome = await asyncio.wait_for(
        session.submit(_attempt(window.window_key, "1w", trigger=window.window_key.trigger_seq)),
        timeout=2,
    )
    assert isinstance(outcome, SubmitAccepted)
    post = [c for c in transport.calls if c.method == "POST"]
    assert len(post) == 1 and post[0].json_body == {"action": "discard", "tile": "1w"}

    # 过期窗口（错误 trigger）仍被本地拒绝：增量路径与快照路径同口径
    stale = WindowKey(game_id=GAME, round_no=1, trigger_seq=99, phase=WindowPhase.DRAW, seat=MY_SEAT)
    again = await asyncio.wait_for(
        session.submit(_attempt(stale, "1w", trigger=99, attempt_no=2)),
        timeout=2,
    )
    assert isinstance(again, SubmitNotSent)
    assert again.reason == "stale_window"


async def test_own_discard_refreshes_hand_before_next_incremental_draw(transport, clock):
    """本人弃牌触发权威刷新：下一次增量摸牌送达时 my_hand 与官方快照一致。"""

    base = _snapshot_doc(101, turn=0, my_hand=_HAND)
    hand_after = [c for c in _HAND if c != "5w"]  # 出掉 "5w" 后剩 12 张
    refreshed = _snapshot_doc(103, turn=0, my_hand=hand_after)
    stage = {"n": 0}

    def handler(*, method: str, path: str, params=None, json_body=None, long_poll=False):
        if method == "POST":
            return 200, "{}"
        seq = (params or {}).get("seq")
        stage["n"] += 1
        if stage["n"] == 1:
            return _json(base)
        if stage["n"] == 2:
            return _json(_events(_event(102, "tile_discarded", MY_SEAT, "5w")))
        if stage["n"] == 3:
            assert seq == 0  # 本人弃牌 → 刷新
            return _json(refreshed)
        if stage["n"] == 4:
            return _json(_events(_event(104, "tile_drawn", MY_SEAT, "7w")))
        raise AssertionError("unexpected stage={}".format(stage["n"]))

    transport.handler = handler
    session = make_game_session(transport=transport, clock=clock)

    item = await asyncio.wait_for(session.next_item(), timeout=2)
    assert isinstance(item, ObservedActionWindow)
    assert item.window_key.trigger_seq == 104
    assert [t.code for t in item.observation.my_hand] == hand_after  # 刷新后的官方手牌
    assert item.observation.drawn_tile == Tile("7w")


# ---------- sync_state 状态机单元回归 ----------


def _parsed_event(seq: int, type_: str, seat: int, tile: str = ""):
    from hangma_bot.adapters.official.dto import ParsedEvent

    return ParsedEvent(
        seq=seq, type=type_, seat=seat, tiles=(tile,) if tile else (),
        occurred_at_unix_sec=1756771200,
    )


def _sync_state():
    from hangma_bot.adapters.official.dto import parse_snapshot
    from hangma_bot.adapters.official.sync_state import ProtocolSyncState

    from _official_testkit import TIMING

    doc = load_fixture("state_response_snapshot_draw.json")
    state = ProtocolSyncState(GAME, TIMING)
    state.apply_full_snapshot(parse_snapshot(doc["snapshot"], doc.get("seq")))
    return state


class TestRefreshPredicate:
    def test_discard_and_timeout_require_refresh(self):
        state = _sync_state()
        assert state.events_need_authoritative_refresh((_parsed_event(102, "tile_discarded", 1, "3b"),))
        assert state.events_need_authoritative_refresh((_parsed_event(102, "timeout", 1),))

    def test_own_meld_requires_refresh_others_not(self):
        state = _sync_state()
        assert state.events_need_authoritative_refresh((_parsed_event(102, "peng", MY_SEAT, "3b"),))
        assert not state.events_need_authoritative_refresh((_parsed_event(102, "peng", 1, "3b"),))
        assert not state.events_need_authoritative_refresh((_parsed_event(102, "chi", 0),))
        assert not state.events_need_authoritative_refresh((_parsed_event(102, "gang", 3),))

    def test_draws_and_pass_do_not_require_refresh(self):
        state = _sync_state()
        assert not state.events_need_authoritative_refresh((_parsed_event(102, "tile_drawn", MY_SEAT, "1w"),))
        assert not state.events_need_authoritative_refresh((_parsed_event(102, "tile_drawn", 0),))
        assert not state.events_need_authoritative_refresh((_parsed_event(102, "pass", 1),))
        assert not state.events_need_authoritative_refresh((_parsed_event(102, "round_ended", 0),))

    def test_own_draw_without_tile_requires_refresh(self):
        state = _sync_state()
        assert state.events_need_authoritative_refresh((_parsed_event(102, "tile_drawn", MY_SEAT),))


class TestIncrementalDrawWindow:
    def test_draw_window_detected_from_last_event_only(self):
        state = _sync_state()
        assert state.incremental_draw_window() is None  # 尚无增量事件
        state.apply_events((_parsed_event(102, "tile_drawn", MY_SEAT, "1w"),))
        window = state.incremental_draw_window()
        assert window is not None
        assert window.window_key == WindowKey(GAME, 1, 102, WindowPhase.DRAW, MY_SEAT)
        assert window.timeout_seconds == 3.0
        # 后续任何事件都使摸牌窗口失效（本人摸牌不再是事件流末条）
        state.apply_events((_parsed_event(103, "pass", 1),))
        assert state.incremental_draw_window() is None

    def test_other_seat_draw_is_not_a_window(self):
        state = _sync_state()
        state.apply_events((_parsed_event(102, "tile_drawn", 0, "1w"),))
        assert state.incremental_draw_window() is None

    def test_incremental_observation_derives_private_facts(self):
        state = _sync_state()
        state.apply_events(
            (
                _parsed_event(102, "tile_discarded", 1, "3b"),
                _parsed_event(103, "tile_drawn", MY_SEAT, "7w"),
            )
        )
        observation = state.incremental_draw_observation()
        assert observation is not None
        assert observation.phase == "draw"
        assert observation.turn_seat == MY_SEAT
        assert observation.responding_seats == ()
        assert observation.drawn_tile == Tile("7w")
        assert [t.code for t in observation.my_hand] == _HAND  # 快照手牌原样（本人未改牌）
        assert observation.last_discard == PublicDiscard(seat=1, tile=Tile("3b"), seq=102)
        # 牌河按事件流追加公开弃牌（估算口径与真实牌河一致）
        assert observation.discards[1][-1] == Tile("3b")
        assert observation.snapshot_seq == 101  # 权威水位仍为最后快照 seq（契约口径）
