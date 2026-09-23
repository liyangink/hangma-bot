"""通过正式会话入口核验观察历史、序号恢复和响应身份；不依赖私有状态。"""
from __future__ import annotations

import asyncio
import json

from hangma_bot.application.contracts import ActionAttempt, ObservedActionWindow, SubmitAccepted
from hangma_bot.kernel.actions import Discard, Pass, Peng, Tile, WindowPhase, action_key
from hangma_bot.hangma import HangmaRules
from hangma_bot.kernel.config import RuleConfig

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
        discard_pacing_enabled=False,  # 同步夹具不推进等待时钟；缓发另行覆盖
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
        # 弃东：本方手牌持东×2（碰兴趣超集）——2026-09-18 起有兴趣才刷新
        (100, {"events": [event(101, "tile_discarded", tile="东")]}),
        (0, snapshot(101, phase="response_peng", river=("东",), discard=(None))),
        (101, {"events": [event(102, "tile_drawn", seat=MY_SEAT, tile="7w")]}),
    ])
    session = make_game_session(transport=transport, clock=clock)
    try:
        window = await session.next_item()
        assert isinstance(window, ObservedActionWindow)
        assert tuple(t.code for t in window.observation.discards[0]) == ("东",)
        assert [(e.seq, e.kind) for e in window.observation.public_history] == [(101, "tile_discarded"), (102, "tile_drawn")]
        assert not queue
    finally:
        await session.aclose("test_completed")


async def test_opponent_draw_makes_next_state_query_a_discard_watch(transport, clock, audit):
    """他家摸牌之后的首个状态查询负责发现未知弃牌，必须区别于普通轮询。"""
    queue = script(transport, [
        (0, snapshot(100, turn=0)),
        (100, {"events": [event(101, "tile_drawn", seat=0)]}),
        (101, {"events": [event(102, "tile_discarded", seat=0, tile="东")]}),
        (0, snapshot(102, turn=0, phase="response_peng", river=("东",),
                     discard={"seq": 102, "seat": 0, "tile": "东"}, responders=(2,))),
    ])
    session = make_game_session(transport=transport, clock=clock, audit=audit)
    try:
        window = await session.next_item()
        assert isinstance(window, ObservedActionWindow)
        assert window.window_key.trigger_seq == 102
        requests = [r.payload for r in audit.records if r.kind.value == "http_request"
                    and r.payload.get("phase") == "started"
                    and r.payload.get("endpoint") == "GET /api/games/g_room1_batch1/state"]
        assert [r["request_timing"]["query_purpose"] for r in requests] == [
            "state_sync", "discard_watch", "discard_watch", "state_sync"]
        assert [r["request_timing"]["scheduler_priority"] for r in requests] == [
            "POLL", "DRAW_WATCH", "DRAW_WATCH", "RECOVERY"]
        assert not queue
    finally:
        await session.aclose("test_completed")


async def test_interesting_incremental_discard_fetches_official_deadline_before_delivery(
    transport, clock,
):
    """排队后整秒估算已过期，仍须先查官方截止再决定能否碰。"""
    requested = []
    posts = []

    def handler(*, method, params=None, **kwargs):
        if method == "POST":
            posts.append(kwargs.get("json_body"))
            return 200, '{"ok":true}'
        assert method == "GET"
        seq = params["seq"]
        requested.append(seq)
        if len(requested) == 1:
            assert seq == 0
            return 200, json.dumps(snapshot(100, turn=0))
        if len(requested) == 2:
            assert seq == 100
            clock.advance(1.2)  # 他家摸牌长轮询先消耗时间，旧水位时间已陈旧。
            return 200, json.dumps({"events": [event(101, "tile_drawn", seat=0)]})
        if len(requested) == 3:
            assert seq == 101
            occurred_at = clock.wall_ms() // 1000
            clock.advance(.9)  # 排队/传输后才发现弃牌，整数 ts 的早界已过。
            discarded = event(102, "tile_discarded", seat=0, tile="东",
                              data={"catch_play": False})
            discarded["ts"] = occurred_at
            return 200, json.dumps({"events": [discarded]})
        assert len(requested) == 4 and seq == 0
        response = snapshot(102, turn=0, phase="response_peng", river=("东",),
                            discard={"seq": 102, "seat": 0, "tile": "东"}, responders=(2,))
        response["snapshot"]["window_deadline_ms"] = clock.wall_ms() + 500
        return 200, json.dumps(response)

    transport.handler = handler
    session = make_game_session(transport=transport, clock=clock)
    try:
        window = await session.next_item()
        assert isinstance(window, ObservedActionWindow)
        assert window.window_key.trigger_seq == 102
        assert window.observation.snapshot_seq == 102
        assert window.deadline_is_estimated is False
        assert requested == [0, 100, 101, 0]
        action = Peng(Tile("东"))
        assert HangmaRules(RuleConfig("estimated-deadline-rescue", 1, False)).validate(
            window.observation, action).legal
        attempt = ActionAttempt(
            decision_id="deadline-rescue-peng", attempt_no=1, plan_revision=1,
            window_key=window.window_key,
            based_on_authoritative_seq=window.observation.snapshot_seq,
            action=action, action_key=action_key(action),
            latest_send_at_monotonic=window.expires_at_monotonic - .1)
        assert isinstance(await session.submit(attempt), SubmitAccepted)
        assert len(posts) == 1
    finally:
        await session.aclose("test_completed")


async def test_response_handoff_watches_next_opponent_discard_before_draw_is_seen(
    transport, clock, audit,
):
    """无鸣牌兴趣的响应标记结束后，下一次查询也须及时发现对手摸打。"""
    queue = script(transport, [
        (0, snapshot(100, turn=0)),
        (100, {"events": [event(101, "tile_discarded", seat=0, tile="9w")]}),
        (101, {"events": [
            event(102, "timeout", seat=1, data={"kind": "response", "window": "peng"}),
            event(103, "timeout", seat=2, data={"kind": "response", "window": "peng"}),
            event(104, "timeout", seat=3, data={"kind": "response", "window": "peng"}),
            event(105, "pass", seat=1),
        ]}),
        (105, {"events": [event(106, "tile_drawn", seat=0),
                           event(107, "tile_discarded", seat=0, tile="东")]}),
        (0, snapshot(107, turn=0, phase="response_peng", river=("9w", "东"),
                     discard={"seq": 107, "seat": 0, "tile": "东"}, responders=(2,))),
    ])
    session = make_game_session(transport=transport, clock=clock, audit=audit)
    try:
        window = await session.next_item()
        assert isinstance(window, ObservedActionWindow)
        assert window.window_key.trigger_seq == 107
        requests = [r.payload for r in audit.records if r.kind.value == "http_request"
                    and r.payload.get("phase") == "started"
                    and r.payload.get("endpoint") == "GET /api/games/g_room1_batch1/state"]
        assert [r["request_timing"]["query_purpose"] for r in requests] == [
            "state_sync", "discard_watch", "discard_watch", "discard_watch", "state_sync"]
        assert not queue
    finally:
        await session.aclose("test_completed")


async def test_uninteresting_discard_still_watches_opponent_peng_then_new_discard(
    transport, clock, audit,
):
    """我方不能鸣当前弃牌时，仍要及时观察他家碰后打出的新牌。"""
    claimed = snapshot(103, turn=1, phase="response_peng", river=("9w",),
                       discard={"seq": 103, "seat": 1, "tile": "东"}, responders=(2,))
    claimed["snapshot"]["discards"][1] = ["东"]
    queue = script(transport, [
        (0, snapshot(100, turn=0)),
        (100, {"events": [event(101, "tile_discarded", seat=0, tile="9w")]}),
        (101, {"events": [event(102, "peng", seat=1, tile="9w"),
                           event(103, "tile_discarded", seat=1, tile="东")]}),
        (0, claimed),
    ])
    session = make_game_session(transport=transport, clock=clock, audit=audit)
    try:
        window = await session.next_item()
        assert isinstance(window, ObservedActionWindow)
        assert window.window_key.trigger_seq == 103
        requests = [r.payload for r in audit.records if r.kind.value == "http_request"
                    and r.payload.get("phase") == "started"
                    and r.payload.get("endpoint") == "GET /api/games/g_room1_batch1/state"]
        assert [r["request_timing"]["query_purpose"] for r in requests] == [
            "state_sync", "discard_watch", "discard_watch", "state_sync"]
        assert not queue
    finally:
        await session.aclose("test_completed")


async def test_first_query_after_own_discard_keeps_discard_watch(transport, clock, audit):
    """交付并提交本人弃牌后，新轮询周期首个请求仍保护他家快速鸣打。"""
    second_get = asyncio.Event()
    blocker = asyncio.Event()
    gets = 0

    async def handler(*, method, **kwargs):
        nonlocal gets
        if method == "POST":
            return 200, '{"ok":true}'
        gets += 1
        if gets == 1:
            return 200, json.dumps(snapshot(100, turn=MY_SEAT, drawn="7w"))
        second_get.set()
        await blocker.wait()
        return 200, '{"pending":true}'

    transport.handler = handler
    session = make_game_session(transport=transport, clock=clock, audit=audit)
    task = None
    try:
        window = await session.next_item()
        assert isinstance(window, ObservedActionWindow)
        action = Discard(Tile("7w"))
        submitted = ActionAttempt(
            decision_id="own-discard-watch", attempt_no=1, plan_revision=1,
            window_key=window.window_key, based_on_authoritative_seq=window.authoritative_seq,
            action=action, action_key="discard:7w",
            latest_send_at_monotonic=clock.monotonic() + 1.0)
        assert isinstance(await session.submit(submitted), SubmitAccepted)
        task = asyncio.create_task(session.next_item())
        await second_get.wait()
        requests = [r.payload for r in audit.records if r.kind.value == "http_request"
                    and r.payload.get("phase") == "started"
                    and r.payload.get("endpoint") == "GET /api/games/g_room1_batch1/state"]
        assert [r["request_timing"]["query_purpose"] for r in requests] == [
            "state_sync", "discard_watch"]
    finally:
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await session.aclose("test_completed")


async def test_new_draw_does_not_reuse_previous_response_boundary(transport, clock, audit):
    """旧响应快照之后已看到本人摸牌时，提交弃牌不再等待旧吃窗边界。"""
    old = snapshot(100, turn=1, phase="response_chi", river=(),
                   discard={"seq": 100, "seat": 1, "tile": "东"}, responders=(2,))
    old["snapshot"]["discards"][1] = ["东"]
    old["snapshot"]["window_deadline_ms"] = clock.wall_ms() + 5000
    next_get = asyncio.Event()
    blocker = asyncio.Event()
    gets = 0

    async def handler(*, method, **kwargs):
        nonlocal gets
        if method == "POST":
            return 200, '{"ok":true}'
        gets += 1
        if gets == 1:
            return 200, json.dumps(old)
        if gets == 2:
            return 200, json.dumps({"events": [event(101, "pass", seat=2),
                                              event(102, "tile_drawn", seat=2, tile="7w")]})
        next_get.set()
        await blocker.wait()
        return 200, '{"pending":true}'

    transport.handler = handler
    session = make_game_session(transport=transport, clock=clock, audit=audit)
    task = None
    try:
        old_window = await session.next_item()
        assert old_window.window_key.phase is WindowPhase.RESPONSE_CHI
        assert isinstance(await session.submit(attempt(old_window, clock)), SubmitAccepted)
        draw = await session.next_item()
        assert isinstance(draw, ObservedActionWindow)
        assert draw.window_key.phase is WindowPhase.DRAW
        discard = Discard(Tile("7w"))
        sent = ActionAttempt(
            decision_id="post-old-response", attempt_no=1, plan_revision=1,
            window_key=draw.window_key, based_on_authoritative_seq=draw.authoritative_seq,
            action=discard, action_key="discard:7w",
            latest_send_at_monotonic=clock.monotonic() + 1.0)
        assert isinstance(await session.submit(sent), SubmitAccepted)
        task = asyncio.create_task(session.next_item())
        await next_get.wait()
        requests = [r.payload for r in audit.records if r.kind.value == "http_request"
                    and r.payload.get("phase") == "started"
                    and r.payload.get("endpoint") == "GET /api/games/g_room1_batch1/state"]
        assert [r["request_timing"]["query_purpose"] for r in requests] == [
            "state_sync", "response_progress", "discard_watch"]
    finally:
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await session.aclose("test_completed")


async def test_retained_draw_is_not_redelivered_after_snapshot_absorbs_it(transport, clock):
    queue = script(transport, [
        (0, snapshot(100)),
        (100, {"events": [event(101, "tile_drawn", seat=MY_SEAT, tile="7w")]}),
        (101, snapshot(102, turn=0)),
        (101, snapshot(103, turn=MY_SEAT, drawn="8w")),
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
        (100, {"events": [event(101, "future_critical"), event(102, "future_critical")]}),
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
