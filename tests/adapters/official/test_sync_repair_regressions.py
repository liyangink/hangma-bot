"""通过正式会话入口核验观察历史、序号恢复和响应身份；不依赖私有状态。"""
from __future__ import annotations

import asyncio
import json

from hangma_bot.application.contracts import ActionAttempt, ObservedActionWindow, SubmitAccepted
from hangma_bot.kernel.actions import Pass, WindowPhase

from _official_testkit import load_fixture, TIMING, instant_sleep, make_audit_context
from hangma_bot.adapters.official.game import OfficialGameSession
from hangma_bot.adapters.official.scheduler import RequestScheduler


MY_SEAT = 2


def make_game_session(*, transport, clock, audit=None):
    """网络脚本立即返回，边界时钟保持未到期；不引入真实 sleep。"""
    async def not_elapsed(seconds):
        await asyncio.Future()  # 网络先完成后会话负责取消此计时等待

    return OfficialGameSession(
        game_id="g_room1_batch1", transport=transport,
        scheduler=RequestScheduler(clock=clock.monotonic, sleep=instant_sleep(clock), poll_interval=0),
        timing=TIMING, monotonic_clock=clock.monotonic, wall_clock_unix_ms=clock.wall_ms,
        audit=audit, audit_context=make_audit_context, retry_sleep=not_elapsed,
    )


def snapshot(seq, *, turn=0, phase="draw", round_no=1, drawn="", river=None, discard=None, responders=(), gap=False):
    """构造玩家座位 2 的规范快照，所有牌面均为测试数据。"""
    doc = load_fixture("state_response_snapshot_draw.json")
    doc.update(seq=seq, gap=gap)
    body = doc["snapshot"]
    body.update(turn=turn, phase=phase, round_no=round_no, drawn_tile=drawn,
                responding_seats=list(responders), last_discard=discard)
    body["discards"] = [list(river or ()), [], [], []]
    return doc


def event(seq, kind, *, seat=0, tile="", data=None):
    return {"seq": seq, "type": kind, "seat": seat, "tile": tile, "data": data}


def script(transport, steps):
    """每一步断言 GET 消费游标；意外额外请求立即失败，避免真实等待。"""
    queue = list(steps)

    def handler(*, method, params=None, **kwargs):
        if method == "POST":
            return 200, "{}"
        assert queue, "会话发出了计划外的 GET"
        expected_seq, response = queue.pop(0)
        assert params["seq"] == expected_seq
        return 200, json.dumps(response)

    transport.handler = handler
    return queue


def attempt(window, clock):
    return ActionAttempt(
        decision_id="repair-pass", attempt_no=1, plan_revision=1,
        window_key=window.window_key,
        based_on_authoritative_seq=window.observation.snapshot_seq,
        action=Pass(), action_key="pass", latest_send_at_monotonic=clock.monotonic() + 0.5,
    )


async def test_refresh_preserves_history_without_duplicating_river(transport, clock):
    queue = script(transport, [
        (0, snapshot(100)),
        (100, {"events": [event(101, "tile_discarded", tile="6t")]}),
        (0, snapshot(101, phase="response_peng", river=("6t",), discard=(None))),
        (101, {"events": [event(102, "tile_drawn", seat=MY_SEAT, tile="7w")]}),
    ])
    session = make_game_session(transport=transport, clock=clock)
    try:
        window = await session.next_item()
        assert isinstance(window, ObservedActionWindow)
        assert tuple(t.code for t in window.observation.discards[0]) == ("6t",)
        assert [(e.seq, e.kind) for e in window.observation.public_history] == [(101, "tile_discarded"), (102, "tile_drawn")]
        assert not queue
    finally:
        await session.aclose("test_completed")


async def test_retained_draw_is_not_redelivered_after_snapshot_absorbs_it(transport, clock):
    queue = script(transport, [
        (0, snapshot(100)),
        (100, {"events": [event(101, "tile_drawn", seat=MY_SEAT, tile="7w")]}),
        (101, snapshot(102, turn=0)),
        (101, {"pending": True}),  # 有界补领未能提供历史，窗口测试保留显式缺口
        (101, {"pending": True}),  # 空闲机会按欠账旧游标补领一次
        (102, snapshot(103, turn=MY_SEAT, drawn="8w")),
        (102, {"pending": True}),
    ])
    session = make_game_session(transport=transport, clock=clock)
    try:
        first = await session.next_item()
        second = await session.next_item()
        assert first.window_key.trigger_seq == 101
        assert second.window_key.trigger_seq == 103
        assert second.observation.drawn_tile.code == "8w"
        assert any(e.seq == 101 for e in second.observation.public_history)
        assert not queue
    finally:
        await session.aclose("test_completed")


async def test_same_seat_same_tile_new_river_clears_previous_pass(transport, clock):
    queue = script(transport, [
        (0, snapshot(100, phase="response_chi", river=("6t",), discard="6t", responders=(1, 2, 3))),
        (100, snapshot(110, phase="response_peng", river=("6t", "6t"), discard="6t", responders=(1, 2, 3))),
        (100, {"pending": True}),
    ])
    session = make_game_session(transport=transport, clock=clock)
    try:
        first = await session.next_item()
        assert isinstance(first, ObservedActionWindow)
        assert isinstance(await session.submit(attempt(first, clock)), SubmitAccepted)
        second = await session.next_item()
        assert isinstance(second, ObservedActionWindow)
        assert second.window_key.trigger_seq == 110
        assert second.window_key != first.window_key
        assert not queue
    finally:
        await session.aclose("test_completed")


async def test_new_structured_discard_clears_previous_pass(transport, clock):
    queue = script(transport, [
        (0, snapshot(100, phase="response_chi", river=("6t",), discard={"seq":100,"seat":0,"tile":"6t"}, responders=(1, 2, 3))),
        (100, snapshot(110, phase="response_peng", river=("6t", "7t"), discard={"seq":109,"seat":0,"tile":"7t"}, responders=(1, 2, 3))),
        (100, {"pending": True}),
    ])
    session = make_game_session(transport=transport, clock=clock)
    try:
        first = await session.next_item()
        assert isinstance(await session.submit(attempt(first, clock)), SubmitAccepted)
        second = await session.next_item()
        assert second.window_key.trigger_seq == 109
        assert second.window_key != first.window_key
        assert not queue
    finally:
        await session.aclose("test_completed")


async def test_duplicate_sequence_with_conflicting_payload_recovers_whole_batch(transport, clock, audit):
    queue = script(transport, [
        (0, snapshot(100)),
        (100, {"events": [event(101, "tile_discarded", tile="6t"), event(101, "tile_discarded", tile="7t")]}),
        (0, snapshot(101, turn=MY_SEAT, drawn="8w")),
    ])
    session = make_game_session(transport=transport, clock=clock, audit=audit)
    try:
        window = await session.next_item()
        assert isinstance(window, ObservedActionWindow)
        assert window.observation.public_history == ()
        reasons = [str(r.payload) for r in audit.records]
        assert any("conflicting_duplicate" in reason for reason in reasons)
        assert not window.observation.history_complete
        assert not queue
    finally:
        await session.aclose("test_completed")


async def test_same_sequence_new_round_is_progress_and_gap_snapshot_needs_no_extra_get(transport, clock):
    queue = script(transport, [
        (0, snapshot(100, phase="settled")),
        (100, snapshot(100, turn=MY_SEAT, round_no=2, drawn="白", gap=True)),
    ])
    start = clock.monotonic()
    session = make_game_session(transport=transport, clock=clock)
    try:
        window = await session.next_item()
        assert isinstance(window, ObservedActionWindow)
        assert window.window_key.round_no == 2
        assert window.window_key.phase is WindowPhase.DRAW
        assert window.observation.public_history == ()
        assert clock.monotonic() == start
        assert not queue
    finally:
        await session.aclose("test_completed")


async def test_second_unknown_event_still_requires_authoritative_recovery(transport, clock):
    queue = script(transport, [
        (0, snapshot(100)),
        (100, {"events": [event(101, "future_critical")]}),
        (0, snapshot(101)),
        (100, {"pending": True}),  # 已吸收未知事件仍缺原文；有界补领未取得
        (101, {"events": [event(102, "future_critical")]}),
        (0, snapshot(102, turn=MY_SEAT, drawn="8w")),
    ])
    session = make_game_session(transport=transport, clock=clock)
    try:
        window = await session.next_item()
        assert isinstance(window, ObservedActionWindow)
        assert not window.observation.history_complete
        assert all(e.kind != "future_critical" for e in window.observation.public_history)
        assert [call.params["seq"] for call in transport.calls].count(0) == 3
        assert not queue
    finally:
        await session.aclose("test_completed")


async def test_other_players_private_draw_never_enters_observation(transport, clock):
    queue = script(transport, [
        (0, snapshot(100)),
        (100, {"events": [event(101, "tile_drawn", seat=0, tile="9t"), event(102, "tile_drawn", seat=MY_SEAT, tile="7w")]}),
        (0, snapshot(102, turn=MY_SEAT, drawn="7w")),
    ])
    session = make_game_session(transport=transport, clock=clock)
    try:
        window = await session.next_item()
        assert isinstance(window, ObservedActionWindow)
        assert window.observation.consumed_seq == 102
        assert all(e.seat != 0 or not e.tiles for e in window.observation.public_history)
        assert window.observation.drawn_tile.code == "7w"
        assert "unexpected_other_draw" in window.observation.observation_issues
        assert not queue
    finally:
        await session.aclose("test_completed")


async def test_same_sequence_phase_change_delivers_chi_without_new_event(transport, clock):
    queue = script(transport, [
        (0, snapshot(100, phase="response_peng", river=("6t",), discard="6t", responders=(1, 2, 3))),
        (100, snapshot(100, phase="response_chi", river=("6t",), discard="6t", responders=(2,))),
    ])
    session = make_game_session(transport=transport, clock=clock)
    try:
        peng = await session.next_item()
        chi = await session.next_item()
        assert peng.window_key.phase is WindowPhase.RESPONSE_PENG
        assert chi.window_key.phase is WindowPhase.RESPONSE_CHI
        assert chi.window_key.trigger_seq == peng.window_key.trigger_seq == 100
        assert not queue
    finally:
        await session.aclose("test_completed")


async def test_conflicting_old_event_after_snapshot_is_not_silently_ignored(transport, clock, audit):
    queue = script(transport, [
        (0, snapshot(100)),
        (100, {"events": [event(101, "tile_drawn", seat=MY_SEAT, tile="7w")]}),
        (101, {"events": [event(101, "tile_drawn", seat=MY_SEAT, tile="8w")]}),
        (0, snapshot(102, turn=MY_SEAT, drawn="9w")),
    ])
    session = make_game_session(transport=transport, clock=clock, audit=audit)
    try:
        await session.next_item()
        window = await session.next_item()
        assert window.window_key.trigger_seq == 102
        assert any("conflicting_duplicate" in str(r.payload) for r in audit.records)
        assert [e.tiles[0].code for e in window.observation.public_history if e.seq == 101] == ["7w"]
        assert not queue
    finally:
        await session.aclose("test_completed")
