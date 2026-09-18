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
    GameFailed,
    ObservedActionWindow,
    SubmitAccepted,
    SubmitNotSent,
    SubmitRejectedClosed,
    SubmitRejectedRetryable,
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
        # 第 2~6 次调用：物理自洽的"摸→(应用层行动后)弃→再摸"增量链
        # （2026-09-18 修订：本人弃牌回显不再刷新，手牌口径=快照+摸−弃）
        assert seq in (101, 102, 104, 106, 108), "轮询游标必须按已消费 seq 推进"
        if seq == 101:
            return _json(_events(_event(102, "tile_drawn", MY_SEAT, "1w")))
        draw_no = (seq - 100) // 2  # 102→1w, 104→2w, 106→3w, 108→4w, 110→5w
        prev_tile = "{}w".format(draw_no)
        next_tile = "{}w".format(draw_no + 1)
        return _json(_events(
            _event(seq + 1, "tile_discarded", MY_SEAT, prev_tile),
            _event(seq + 2, "tile_drawn", MY_SEAT, next_tile),
        ))

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
        # 增量送达：手牌=快照+本人摸牌−本人弃牌（净额为零，仍是13张暗牌）
        assert sorted(t.code for t in item.observation.my_hand) == sorted(_HAND)

    assert drawn_triggers == [102, 104, 106, 108, 110]
    get_calls = [c.params["seq"] for c in transport.calls if c.method == "GET"]
    assert get_calls == [0, 101, 102, 104, 106, 108]  # 仅首拉 seq=0，零重建请求
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
            return _json(_events(_event(102, "pass", 0)))  # 正常无牌事件：无窗无刷新
        if stage["n"] == 3:
            hanging.set()
            await asyncio.sleep(30)  # 挂起长轮询：被外部取消
            return _json({"pending": True})
        if stage["n"] == 4:
            assert seq == 102, "重连后的轮询必须沿用取消前游标，不得回退"
            return _json(_events(_event(103, "pass", 1)))
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
    assert get_calls == [0, 101, 102, 102, 103]  # 游标只进不退（公开行为口径）


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
    history_polls = {"n": 0}

    def handler(*, method: str, path: str, params=None, json_body=None, long_poll=False):
        if method == "POST":
            return 200, "{}"
        seq = (params or {}).get("seq")
        if seq == 101 and not long_poll and stage["n"] == 8:
            history_polls["n"] += 1
            assert history_polls["n"] == 0
            return _json({"pending": True})  # 水位200后补领102..200，旧事件暂未可得
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
            assert seq == 101  # 正常查询顺带补齐快照跨过的区间
            return _json(_events(*[_event(n, "pass", 1) for n in range(102, 201)], _event(201, "tile_drawn", MY_SEAT, "8w")))
        raise AssertionError("unexpected stage={}".format(stage["n"]))

    transport.handler = handler
    session = make_game_session(transport=transport, clock=clock, audit=audit)

    start = clock.monotonic()
    item = await asyncio.wait_for(session.next_item(), timeout=5)
    assert isinstance(item, ObservedActionWindow)
    assert item.window_key.trigger_seq == 201

    elapsed = clock.monotonic() - start
    # 第 1~2 次无进度快照原速轮询（不延迟边界后响应窗口发现），第 3~6 次
    # 按 (0.5, 1.0, 1.0, 1.0) 退避（封顶 1.0s，P2-N4）：假时钟精确推进 3.5 秒
    assert elapsed == pytest.approx(0.5 + 1.0 + 1.0)  # 首次同seq换单局属于进展
    assert stall_polls["n"] == 6
    assert _recovered_gap_count(audit) == 7  # 6 次无进度 + 1 次前进，总量有界


    assert history_polls["n"] == 0

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
            # 2026-09-18 复盘修订：本人弃牌回显不再触发 seq=0 权威刷新
            # （手牌新鲜化由增量摸牌观察的本人弃牌扣除承担），
            # 游标沿已消费增量水位 103 继续长轮询。
            assert seq == 103
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

    # 消费 POST 产生的增量：本人弃牌回显 + 他家摸牌均走纯增量，不刷新
    task = asyncio.ensure_future(session.next_item())
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    get_calls = [c.params["seq"] for c in transport.calls if c.method == "GET"]
    # 首拉 seq=0 → POST 后增量轮询用 101（不回退 0）→ 本人弃牌回显/他家
    # 摸牌不刷新，游标保持 103 继续（pending 后原游标重拉同样 103）
    assert get_calls[:3] == [0, 101, 103]
    assert all(seq == 103 for seq in get_calls[3:])


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


async def test_own_discard_echo_keeps_cursor_and_next_draw_updates_hand(transport, clock):
    """本人弃牌回显不再触发快照刷新（2026-09-18 复盘修订）。

    下一次增量摸牌送达时 my_hand = 快照手牌 − 本人弃牌回显，新摸牌单列
    drawn_tile；全程游标沿增量水位前进，不出现第二次 seq=0。
    """

    base = _snapshot_doc(101, turn=0, my_hand=_HAND)
    hand_after = [c for c in _HAND if c != "5w"] + ["9t"]  # 摸9t弃5w后仍13张暗牌
    stage = {"n": 0}

    def handler(*, method: str, path: str, params=None, json_body=None, long_poll=False):
        if method == "POST":
            return 200, "{}"
        seq = (params or {}).get("seq")
        stage["n"] += 1
        if stage["n"] == 1:
            return _json(base)
        if stage["n"] == 2:
            # 本人摸牌+弃牌同批到达：均不触发刷新
            return _json(_events(
                _event(102, "tile_drawn", MY_SEAT, "9t"),
                _event(103, "tile_discarded", MY_SEAT, "5w"),
            ))
        if stage["n"] == 3:
            assert seq == 103, "本人弃牌回显不刷新，游标沿增量水位前进"
            return _json(_events(_event(104, "tile_drawn", MY_SEAT, "7w")))
        raise AssertionError("unexpected stage={}".format(stage["n"]))

    transport.handler = handler
    session = make_game_session(transport=transport, clock=clock)

    item = await asyncio.wait_for(session.next_item(), timeout=2)
    assert isinstance(item, ObservedActionWindow)
    assert item.window_key.trigger_seq == 104
    # 快照 + 本人摸牌(9t) − 本人弃牌(5w) = 摸牌前13张；新摸7w单列
    assert [t.code for t in item.observation.my_hand] == hand_after
    assert item.observation.drawn_tile == Tile("7w")
    get_calls = [c.params["seq"] for c in transport.calls if c.method == "GET"]
    assert get_calls[:3] == [0, 101, 103]  # 无第二次 seq=0


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
    def test_discard_and_timeout_refresh_only_with_claim_interest(self):
        """2026-09-18 复盘修订：无关弃牌/标记走增量，有兴趣才刷新。

        fixture 手牌为 1w-9w + 东东 + 南 + 白（摸 5w，即持 5w×2）；
        我方座位 2，上家是座位 1。
        """

        state = _sync_state()
        # 上家弃 3b：无对子、无筒子搭子 → 与我校无关，不刷新
        assert not state.events_need_authoritative_refresh(
            (_parsed_event(102, "tile_discarded", 1, "3b"),)
        )
        # 无关弃牌已入流：同周期 timeout 标记也只推进投影
        assert not state.events_need_authoritative_refresh(
            (_parsed_event(103, "timeout", 1),)
        )
        # 持对（5w×2 含刚摸）→ 任何座位弃 5w 都可能碰 → 刷新
        assert state.events_need_authoritative_refresh(
            (_parsed_event(104, "tile_discarded", 0, "5w"),)
        )
        # 上家弃 2w：同花色距离≤2 搭子超集 → 可能吃 → 刷新
        assert state.events_need_authoritative_refresh(
            (_parsed_event(105, "tile_discarded", 1, "2w"),)
        )
        # 财神白板不能被吃/碰/杠，但弃白是抓打圈唯一激活路径 → 必须刷新
        # （2026-09-18 开圈守卫：合法性空间变化与兴趣无关）
        assert state.events_need_authoritative_refresh(
            (_parsed_event(106, "tile_discarded", 1, "白"),)
        )

    def test_catch_play_discard_requires_refresh(self):
        """携带 catch_play=true 的弃牌（圈内弃牌）无条件刷新。"""

        from hangma_bot.adapters.official.dto import ParsedEvent

        state = _sync_state()
        event = ParsedEvent(
            seq=102, type="tile_discarded", seat=1, tiles=("东",),
            occurred_at_unix_sec=1756771200, catch_play=True,
        )
        assert state.events_need_authoritative_refresh((event,))

    def test_timeout_in_interesting_cycle_requires_refresh(self):
        """有兴趣周期的 timeout 标记仍刷新：我的吃窗可能在切换后开出。"""

        state = _sync_state()
        state.apply_events((_parsed_event(102, "tile_discarded", 0, "5w"),))
        assert state.events_need_authoritative_refresh((_parsed_event(103, "timeout", 0),))

    def test_any_meld_requires_refresh_until_public_board_is_projected(self):
        state = _sync_state()
        assert state.events_need_authoritative_refresh((_parsed_event(102, "peng", MY_SEAT, "3b"),))
        assert state.events_need_authoritative_refresh((_parsed_event(102, "peng", 1, "3b"),))
        assert state.events_need_authoritative_refresh((_parsed_event(102, "chi", 0),))
        assert state.events_need_authoritative_refresh((_parsed_event(102, "gang", 3),))

    def test_draws_and_pass_do_not_require_refresh(self):
        state = _sync_state()
        assert not state.events_need_authoritative_refresh((_parsed_event(102, "tile_drawn", MY_SEAT, "1w"),))
        assert not state.events_need_authoritative_refresh((_parsed_event(102, "tile_drawn", 0),))
        assert state.events_need_authoritative_refresh((_parsed_event(102, "tile_drawn", 0, "9t"),))
        assert not state.events_need_authoritative_refresh((_parsed_event(102, "pass", 1),))
        assert state.events_need_authoritative_refresh((_parsed_event(102, "round_ended", 0),))

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


# ---------- 返工回归：F-02 / P3-01 / F-15 ----------


async def test_conflict_on_incremental_window_refresh_same_seq_retryable(transport, clock):
    """F-02 回归 v1：增量摸牌窗口 409 后，权威刷新快照水位 == 摸牌事件 seq
    （恒等成立）→ 同窗判定为 SubmitRejectedRetryable，可排除 hu 换弃牌。"""

    from hangma_bot.adapters.official.errors import ConflictError

    base = _snapshot_doc(101, turn=0)
    refreshed = _snapshot_doc(102, turn=MY_SEAT, drawn="1w")  # 409 后刷新：同窗仍开
    stage = {"n": 0}

    def handler(*, method: str, path: str, params=None, json_body=None, long_poll=False):
        if method == "POST":
            raise ConflictError(409, "INVALID_ACTION", "hu rejected")
        seq = (params or {}).get("seq")
        stage["n"] += 1
        if stage["n"] == 1:
            return _json(base)
        if stage["n"] == 2:
            return _json(_events(_event(102, "tile_drawn", MY_SEAT, "1w")))
        if stage["n"] == 3:
            assert seq == 0  # 409 后权威刷新
            return _json(refreshed)
        raise AssertionError("unexpected stage={}".format(stage["n"]))

    transport.handler = handler
    session = make_game_session(transport=transport, clock=clock)
    window = await asyncio.wait_for(session.next_item(), timeout=2)
    assert isinstance(window, ObservedActionWindow)
    assert window.window_key.trigger_seq == 102  # 增量投递

    outcome = await asyncio.wait_for(
        session.submit(_attempt(window.window_key, "1w", trigger=102, attempt_no=1)),
        timeout=2,
    )
    assert isinstance(outcome, SubmitRejectedRetryable), outcome
    assert outcome.refreshed_window.window_key == window.window_key  # 同窗可换动作重试
    assert outcome.refreshed_window.observation.drawn_tile == Tile("1w")


async def test_conflict_on_incremental_window_migrated_is_closed(transport, clock):
    """F-02 回归 v2：增量窗口 409 后权威刷新显示窗口已迁移（水位前进、无我方
    窗口）→ SubmitRejectedClosed，绝不在未确认状态上重试。"""

    from hangma_bot.adapters.official.errors import ConflictError

    base = _snapshot_doc(101, turn=0)
    migrated = _snapshot_doc(103, turn=0)  # 窗口已迁移：他人在行动
    stage = {"n": 0}

    def handler(*, method: str, path: str, params=None, json_body=None, long_poll=False):
        if method == "POST":
            raise ConflictError(409, "INVALID_ACTION", "hu rejected")
        seq = (params or {}).get("seq")
        stage["n"] += 1
        if stage["n"] == 1:
            return _json(base)
        if stage["n"] == 2:
            return _json(_events(_event(102, "tile_drawn", MY_SEAT, "1w")))
        if stage["n"] == 3:
            assert seq == 0
            return _json(migrated)
        if stage["n"] == 4:
            assert seq == 102 and not long_poll
            return _json({"pending": True})  # 当前快照超前一条，只补领一次
        raise AssertionError("unexpected stage={}".format(stage["n"]))

    transport.handler = handler
    session = make_game_session(transport=transport, clock=clock)
    window = await asyncio.wait_for(session.next_item(), timeout=2)
    assert isinstance(window, ObservedActionWindow)

    outcome = await asyncio.wait_for(
        session.submit(_attempt(window.window_key, "1w", trigger=102)),
        timeout=2,
    )
    assert isinstance(outcome, SubmitRejectedClosed), outcome
    # 同窗不再接受任何提交
    again = await asyncio.wait_for(
        session.submit(_attempt(window.window_key, "1w", trigger=102, attempt_no=2)),
        timeout=2,
    )
    assert isinstance(again, SubmitNotSent)


async def test_delivered_window_never_delivered_twice_across_paths(transport, clock):
    """P3-01 回归：同一物理窗口经增量路径投递后，权威快照再次携带同窗状态时
    不得二次投递（exactly-once 双路径护栏）。"""

    base = _snapshot_doc(101, turn=0)
    redeliver = _snapshot_doc(102, turn=MY_SEAT, drawn="1w")  # 快照形态重复同窗
    stage = {"n": 0}
    windows = []

    async def handler(*, method: str, path: str, params=None, json_body=None, long_poll=False):
        if method == "POST":
            return 200, "{}"
        seq = (params or {}).get("seq")
        stage["n"] += 1
        if stage["n"] == 1:
            return _json(base)
        if stage["n"] == 2:
            return _json(_events(_event(102, "tile_drawn", MY_SEAT, "1w")))
        if stage["n"] == 3:
            assert seq == 102
            return _json(redeliver)  # 同水位快照重送（含同窗状态）
        if stage["n"] == 4:
            assert seq == 102
            return _json({"pending": True})
        await asyncio.sleep(30)
        return _json({"pending": True})

    transport.handler = handler
    session = make_game_session(transport=transport, clock=clock)
    first = await asyncio.wait_for(session.next_item(), timeout=2)
    assert isinstance(first, ObservedActionWindow)
    windows.append(first.window_key)

    task = asyncio.ensure_future(session.next_item())
    await asyncio.sleep(0.15)  # 让重送快照/pending 被消费（不产生二次投递）
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(windows) == 1  # 快照重送未造成第二次窗口投递
    get_calls = [c.params["seq"] for c in transport.calls if c.method == "GET"]
    assert get_calls[:4] == [0, 101, 102, 102]  # 全程零重建、无回退
    assert get_calls.count(0) == 1


async def test_pending_gap_stall_bounded_by_rebuild_loop_guard(transport, clock):
    """F-15 回归：连续 pending+gap 且重建快照无进度 → 两次无进度重建后按
    rebuild_loop 保护上交可恢复故障（有界快速失败，无退避睡眠依赖、绝不
    无限轮询）；快照+gap 边界路径的退避由 snapshot-gap 分支承担（v10
    真实路径，见 test_v10_boundary_no_progress_backoff_bounded）。"""

    base = _snapshot_doc(101, turn=0)
    stall = _snapshot_doc(101, turn=0, round_no=2, gap=True)  # 重建后仍无进度
    stage = {"n": 0}

    def handler(*, method: str, path: str, params=None, json_body=None, long_poll=False):
        if method == "POST":
            return 200, "{}"
        seq = (params or {}).get("seq")
        stage["n"] += 1
        if stage["n"] == 1:
            return _json(base)
        # 偶数序号 = 长轮询返回 pending+gap；奇数序号 = 对应 seq=0 重建快照
        if stage["n"] % 2 == 0:
            assert seq == 101 or seq == 0, "pending 轮询游标不应回退: seq={}".format(seq)
            return _json({"pending": True, "gap": True})
        assert seq == 0  # 重建请求
        return _json(stall)

    transport.handler = handler
    session = make_game_session(transport=transport, clock=clock)
    start = clock.monotonic()
    item = await asyncio.wait_for(session.next_item(), timeout=5)
    elapsed = clock.monotonic() - start
    assert isinstance(item, GameFailed)
    assert item.recoverable is True
    assert item.reason == "rebuild_loop"  # 第 3 次 pending+gap（streak=3 > 2）保护性上交
    assert elapsed == 0.0  # 无退避睡眠：保护性快速失败，可恢复重入


async def test_pending_gap_progress_restores_incremental(transport, clock):
    """F-15/wv6 回归：pending+gap 重建后水位前进 → 恢复计数清零并恢复增量投递。

    第二轮 pending+gap 用于锁定 wv6 的 rebuild_streak 清零：若进度后不清零，
    第二轮首个 pending+gap 的 streak 累积到 3 会误判 rebuild_loop 提前上交。
    """

    base = _snapshot_doc(101, turn=0)
    boundary_r1 = _snapshot_doc(101, turn=0, round_no=2, gap=True)  # 第一轮无进度
    water_200 = _snapshot_doc(200, turn=0, round_no=2, gap=True)  # 第一轮进展到 200
    boundary_r2 = _snapshot_doc(200, turn=0, round_no=2, gap=True)  # 第二轮无进度
    water_300 = _snapshot_doc(300, turn=0, round_no=2, gap=True)  # 第二轮进展到 300
    stage = {"n": 0}
    history_polls = {"n": 0}

    def handler(*, method: str, path: str, params=None, json_body=None, long_poll=False):
        if method == "POST":
            return 200, "{}"
        seq = (params or {}).get("seq")
        if seq == 101 and not long_poll and stage["n"] == 5:
            history_polls["n"] += 1
            assert history_polls["n"] == 0
            return _json({"pending": True})  # 第一次水位前进后补领；普通poll仍需继续
        stage["n"] += 1
        if stage["n"] == 1:
            return _json(base)
        if stage["n"] in (2, 4, 6, 8):
            # 偶数位（除事件位 10）= 长轮询返回 pending+gap（两轮）
            return _json({"pending": True, "gap": True})
        if stage["n"] == 3:
            return _json(boundary_r1)  # 第一轮重建：无进度（水位 101 不变）
        if stage["n"] == 5:
            return _json(water_200)  # 第一轮进展：水位 200（streak 必须清零）
        if stage["n"] == 7:
            return _json(boundary_r2)  # 第二轮重建：无进度（水位 200 不变）
        if stage["n"] == 9:
            return _json(water_300)  # 第二轮进展：水位 300（streak 再次清零）
        if stage["n"] == 10:
            assert seq == 200
            return _json(_events(*[_event(n, "pass", 1) for n in range(201, 301)], _event(301, "tile_drawn", MY_SEAT, "8w")))
        raise AssertionError("unexpected stage={}".format(stage["n"]))

    transport.handler = handler
    session = make_game_session(transport=transport, clock=clock)
    item = await asyncio.wait_for(session.next_item(), timeout=5)
    get_calls = [c.params["seq"] for c in transport.calls if c.method == "GET"]
    assert isinstance(item, ObservedActionWindow)
    assert item.window_key.round_no == 2
    assert item.window_key.trigger_seq == 301  # 第二轮进展后恢复增量直达
    assert get_calls == [0, 101, 0, 101, 0, 101, 0, 200, 0, 200]
    assert history_polls["n"] == 0

