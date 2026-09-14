"""通过正式会话验证快照跨过的事件由下一次正常查询补齐。"""

import json

import pytest

from hangma_bot.application.contracts import ObservedActionWindow
from hangma_bot.kernel.actions import Tile

from test_sync_repair_regressions import event, make_game_session, snapshot


@pytest.mark.asyncio
async def test_next_regular_poll_recovers_snapshot_covered_chi_without_replaying_board(transport, clock):
    before = snapshot(100)
    after = snapshot(103, river=("7t", "9t"))
    after["snapshot"]["melds"][1] = [{"kind": "chi", "tiles": ["7t", "8t", "9t"]}]
    lost = event(102, "chi", seat=1, tile="9t", data={"tiles": ["7t", "8t", "9t"]})
    scripted = [
        (0, before),
        (100, {"events": [event(101, "timeout", data={"kind": "response"})]}),
        (0, after),
        (101, {"events": [lost, event(103, "pass", seat=3),
                           event(104, "tile_drawn", seat=2, tile="7w")]}),
    ]

    def handler(*, params, **kwargs):
        assert scripted, "补史不应触发额外的串行快照或网络查询"
        expected, response = scripted.pop(0)
        assert params["seq"] == expected, "完整快照不能吞掉尚未领取的吃事件"
        return 200, json.dumps(response)

    transport.handler = handler
    session = make_game_session(transport=transport, clock=clock)
    try:
        window = await session.next_item()
        assert isinstance(window, ObservedActionWindow)
        obs = window.observation
        assert (obs.snapshot_seq, obs.consumed_seq) == (103, 104)
        chi = [e for e in obs.public_history if e.kind == "chi"]
        assert len(chi) == 1 and chi[0].claimed_tile == Tile("9t")
        assert obs.discards[0] == (Tile("7t"), Tile("9t"))
        assert len(obs.melds[1]) == 1
        assert not scripted
    finally:
        await session.aclose("test_done")


@pytest.mark.parametrize("unavailable,needs_full", [
    ({"pending": True}, False),
    ({"events": []}, False),
    (snapshot(102), False),
    ({"pending": True, "gap": True}, True),
    ({"events": [event(102, "pass", seat=1)]}, True),  # 缺101
    ({"events": [event(101, "future_critical"), event(102, "pass")]}, True),
    ({"events": [event(101, "tile_drawn", seat=0, tile="9t"), event(102, "pass")]}, True),
    ({"events": [event(101, "pass", seat=0), event(101, "pass", seat=1)]}, True),
    ({"events": [event(101, "chi", tile="1w", data={"tiles": ["7t", "8t", "9t"]})]}, True),
])
async def test_unavailable_or_invalid_history_is_bounded_and_does_not_delay_current_action(
    transport, clock, audit, unavailable, needs_full,
):
    from test_sync_repair_regressions import script
    entries = [(0, snapshot(100)), (100, snapshot(102, turn=2, drawn="7w")),
               (100, unavailable)]
    if needs_full:
        entries.append((0, snapshot(102)))
    entries.append((102, {"events": [event(103, "tile_drawn", seat=2, tile="8w")]}))
    queue = script(transport, entries)
    session = make_game_session(transport=transport, clock=clock, audit=audit)
    try:
        first = await session.next_item()
        assert first.observation.drawn_tile == Tile("7w")
        assert len(transport.calls) == 2  # 未发任何旧游标请求，当前窗口已交付
        second = await session.next_item()
        assert second.window_key.trigger_seq == 103
        assert [e.seq for e in second.observation.public_history] == [103]
        assert not second.observation.history_complete
        assert not queue
        assert any(r.payload.get("history_recovery") in ("unavailable", "rejected")
                   for r in audit.records)
    finally:
        await session.aclose("test_done")


def test_recovery_filters_consumed_incrementals_and_detects_conflicting_duplicates():
    from hangma_bot.adapters.official.errors import DtoError
    from test_history_debt_state import start, parsed_snapshot, events
    state = start()
    state.apply_full_snapshot(parsed_snapshot(102))
    received = event(103, "pass", seat=1)
    state.apply_events(events(received))
    old = event(101, "pass", seat=0), event(102, "pass", seat=3)
    before = state.current_observation()
    with pytest.raises(DtoError, match="冲突"):
        state.recover_snapshot_history(events(*old, event(103, "pass", seat=2)), after_seq=100, round_no=1)
    assert state.current_observation() == before  # 冲突时旧历史也不部分提交
    new = events(event(104, "tile_drawn", seat=2, tile="8w"))
    assert state.recover_snapshot_history(events(*old, received, received) + new,
                                         after_seq=100, round_no=1) == new
    assert [e.seq for e in state.current_observation().public_history] == [101, 102, 103]
    assert state.last_seq == 103
    assert state.history_query_seq() == 103


def test_partial_recovery_advances_only_received_history_and_never_guesses_seq_one():
    from test_history_debt_state import start, parsed_snapshot, events
    state = start(0)
    state.apply_full_snapshot(parsed_snapshot(4))
    assert state.history_query_seq() == 1  # seq=0有特殊含义，不能声称补到了事件1
    state.recover_snapshot_history(events(event(2, "pass", seat=1)), after_seq=1, round_no=1)
    assert state.history_query_seq() == 2
    state.recover_snapshot_history(events(event(3, "pass", seat=1), event(4, "pass", seat=3)),
                                   after_seq=2, round_no=1)
    assert state.history_missing_ranges() == ((1, 1),)
    assert not state.current_observation().history_complete
    assert state.history_query_seq() == 4


def test_retention_and_abandoned_ranges_do_not_loop_or_claim_completeness():
    from test_history_debt_state import start, parsed_snapshot, events
    state = start()
    state.apply_full_snapshot(parsed_snapshot(356))
    assert state.history_query_seq() == 100
    state.apply_full_snapshot(parsed_snapshot(357))
    assert state.history_query_seq() == 357  # 已超过官方256条范围
    state.abandon_history_query(357)
    state.apply_full_snapshot(parsed_snapshot(359))
    assert state.history_query_seq() == 357  # 新缺口仍可补，旧缺口如实保留
    state.recover_snapshot_history(events(event(358, "pass", seat=1), event(359, "pass", seat=3)),
                                   after_seq=357, round_no=1)
    assert state.history_missing_ranges() == ((101, 357),)
    assert state.history_query_seq() == 359
    assert not state.current_observation().history_complete


def test_cross_round_recovery_requires_new_snapshot_and_resets_cursor_scope():
    from hangma_bot.adapters.official.errors import DtoError
    from test_history_debt_state import start, parsed_snapshot, events
    state = start()
    state.apply_full_snapshot(parsed_snapshot(103))
    with pytest.raises(DtoError, match="终局"):
        state.recover_snapshot_history(events(event(101, "round_ended", data={"draw": True}),
                                             event(102, "pass"), event(103, "pass")),
                                       after_seq=100, round_no=1)
    assert state.current_observation().public_history == ()
    state.abandon_history_query(103)
    state.apply_full_snapshot(parsed_snapshot(104, round_no=2, phase="deal"))
    state.apply_full_snapshot(parsed_snapshot(106, round_no=2))
    assert state.history_query_seq() == 104
    with pytest.raises(DtoError, match="单局"):
        state.recover_snapshot_history(events(event(105, "pass")), after_seq=104, round_no=1)
    state.recover_snapshot_history(events(event(105, "pass"), event(106, "pass")),
                                   after_seq=104, round_no=2)
    assert state.current_observation().history_complete


def test_v34_live_snapshot_does_not_consume_server_event_history():
    from pathlib import Path
    from hangma_bot.adapters.official.dto import parse_state_response
    from hangma_bot.adapters.official.sync_state import ProtocolSyncState
    from _official_testkit import TIMING
    path = Path(__file__).resolve().parents[2] / "fixtures/official/v34/history-cursor-recovery.json"
    raw = json.loads(path.read_text())
    before, refreshed, recovered = raw["captures"]
    state = ProtocolSyncState(raw["game_id"], TIMING)
    state.apply_full_snapshot(parse_state_response(before["body"]).snapshot)
    state.apply_full_snapshot(parse_state_response(refreshed["body"]).snapshot)
    assert refreshed["requested_seq"] == 0 and not refreshed["body"].get("events")
    assert state.last_seq == 376 and state.history_query_seq() == recovered["requested_seq"] == 372
    board = state.current_observation()
    parsed = parse_state_response(recovered["body"])
    assert not state.recover_snapshot_history(parsed.events, after_seq=372, round_no=board.round_no)
    after = state.current_observation()
    assert [e.seq for e in after.public_history] == [373, 374, 375, 376]
    assert after.my_hand == board.my_hand and after.discards == board.discards
    assert after.melds == board.melds and after.hand_counts == board.hand_counts
    assert state.last_seq == state.history_query_seq() == 376
