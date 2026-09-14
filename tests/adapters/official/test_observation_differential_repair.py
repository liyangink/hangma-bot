"""正式会话输出与手写独立参考值对拍；脚本化协议回归，不冒充官方金例。"""

import asyncio
from dataclasses import replace
import json

import pytest

from _official_testkit import FakeClock, FakeTransport, TIMING
from hangma_bot.adapters.official.game import OfficialGameSession
from hangma_bot.adapters.official.scheduler import RequestScheduler
from hangma_bot.application.contracts import ActionAttempt, ObservedActionWindow, SubmitAccepted
from hangma_bot.kernel.actions import Discard, Tile
from hangma_bot.kernel.observation import PlayerObservation, PublicDiscard, PublicEvent, PublicMeld, RulePublicState
from hangma_bot.offline.observation_check import compare_observations

HAND = ("1w", "2w", "3w", "4w", "5w", "6w", "7b", "8b", "9b", "东", "南", "西", "北")


def _snapshot(seq=100, *, phase="draw", turn=1):
    return {"seq": seq, "snapshot": {
        "seat": 2, "phase": phase, "turn": turn,
        "responding_seats": [2] if phase.startswith("response_") else [],
        "dealer": 0, "round_no": 1, "drawn_tile": None,
        "my_hand": list(HAND), "wall_remaining": 40, "scores": [0, 0, 0, 0],
        "last_discard": {"seat": 1, "tile": "9t", "seq": 100},
        "discards": [[], ["9t"], [], []], "melds": [[], [], [], []],
        "hand_counts": [13, 13, 13, 13],
        "god": {"baotou": False, "chain_count": 0, "catch_play": False},
    }}


def _reference(*, seq=101, history=(), melds=((), (), (), ()), last_discard_seq=100, river=(Tile("9t"),)):
    # 有意独立于 DTO/projector：本行字段是测试场景定义的预期事实。
    return PlayerObservation(
        game_id="g_room1_batch1", seat=2, round_no=1, snapshot_seq=seq,
        phase="draw", dealer_seat=0, turn_seat=2, responding_seats=(),
        my_hand=tuple(Tile(code) for code in HAND), drawn_tile=Tile("中"),
        discards=((), river, (), ()), melds=melds, hand_counts=(13, 13, 14, 13),
        last_discard=PublicDiscard(1, Tile("9t"), last_discard_seq),
        remaining_tile_count=39, scores=(0, 0, 0, 0),
        rule_state=RulePublicState(Tile("白"), False, 0, False),
        public_history=history, consumed_seq=seq, history_complete=False,
        chain_piao=0, gang_draw=None,
    )


def _session(documents):
    transport, clock = FakeTransport(), FakeClock()
    pending = list(documents)

    def response(**kwargs):
        if kwargs["method"] == "POST":
            return 200, "{}"
        assert pending, "会话发出了场景之外的恢复请求"
        return 200, json.dumps(pending.pop(0))

    async def timer(_seconds):
        await asyncio.Future()  # 响应脚本立即返回，阶段计时器必须可取消

    transport.handler = response
    return OfficialGameSession(
        game_id="g_room1_batch1", transport=transport,
        scheduler=RequestScheduler(clock=clock.monotonic, poll_interval=0), timing=TIMING,
        monotonic_clock=clock.monotonic, wall_clock_unix_ms=clock.wall_ms,
        retry_sleep=timer,
    ), transport, clock


@pytest.mark.asyncio
async def test_incremental_observation_matches_independent_reference_and_submits():
    event = {"seq": 101, "type": "tile_drawn", "seat": 2, "tile": "中"}
    session, transport, clock = _session([_snapshot(), {"events": [event]}])
    try:
        window = await asyncio.wait_for(session.next_item(), 1)
        assert isinstance(window, ObservedActionWindow)
        expected = _reference(history=(PublicEvent(101, "tile_drawn", 2, (Tile("中"),)),))
        report = compare_observations(window.observation, expected, boundary_verified=True)
        assert not report.differences, report
        assert window.observation.snapshot_seq == 100
        assert window.observation.consumed_seq == 101
        assert report.status == "not_checked"  # 中途起点缺史不能变成完整验收通过
        result = await session.submit(ActionAttempt(
            decision_id="diff-draw", attempt_no=1, plan_revision=1,
            window_key=window.window_key, based_on_authoritative_seq=window.authoritative_seq,
            action=Discard(Tile("中")), action_key="discard:中",
            latest_send_at_monotonic=clock.monotonic() + 1,
        ))
        assert isinstance(result, SubmitAccepted)
        assert sum(call.method == "POST" for call in transport.calls) == 1
    finally:
        await session.aclose("test_done")


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("baotou", True), ("chain_count", 2), ("catch_play", True)])
async def test_wrong_god_in_actual_observation_is_detected(field, value):
    final = _snapshot(101, turn=2)
    final["snapshot"].update(drawn_tile="中", wall_remaining=39, hand_counts=[13, 13, 14, 13])
    final["snapshot"]["god"][field] = value  # 在传输响应注入错值，经过正式解析与观察交付
    session, _, _ = _session([final])
    try:
        window = await asyncio.wait_for(session.next_item(), 1)
        report = compare_observations(window.observation, _reference(), boundary_verified=True)
        assert report.state_status == "failed"
        assert "rule_state." + field in [item.path for item in report.differences]
    finally:
        await session.aclose("test_done")


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,tiles,detail", [
    ("chi", ("7t", "8t", "9t"), None),
    ("gang", ("9t", "9t", "9t", "9t"), "an"),
])
async def test_event_details_survive_full_refresh_and_faults_are_located(kind, tiles, detail):
    data = {"tiles": list(tiles)} if kind == "chi" else {"kind": detail}
    events = {"events": [
        {"seq": 101, "type": kind, "seat": 1, "tile": "9t", "data": data},
        {"seq": 102, "type": "tile_discarded", "seat": 1, "tile": "9t"},
        {"seq": 103, "type": "tile_drawn", "seat": 2, "tile": "中"},
    ]}
    final = _snapshot(103, turn=2)
    final["snapshot"].update(drawn_tile="中", wall_remaining=39, hand_counts=[13, 13, 14, 13],
                             last_discard={"seat": 1, "tile": "9t", "seq": 102})
    final["snapshot"]["discards"][1].append("9t")
    final["snapshot"]["melds"][1] = [{"kind": kind, "tiles": list(tiles), "from_seat": 0 if kind == "chi" else None}]
    session, _, _ = _session([_snapshot(), events, final])
    try:
        window = await asyncio.wait_for(session.next_item(), 1)
        assert isinstance(window, ObservedActionWindow)
        # gang 事件规范 tiles 保存顶层单牌；四张牌副露由快照提供。
        event_tiles = tuple(Tile(code) for code in tiles) if kind == "chi" else (Tile("9t"),)
        history = (PublicEvent(101, kind, 1, event_tiles, detail_kind=detail,
                               claimed_tile=Tile("9t") if kind == "chi" else None),
                   PublicEvent(102, "tile_discarded", 1, (Tile("9t"),)),
                   PublicEvent(103, "tile_drawn", 2, (Tile("中"),)))
        meld = PublicMeld(1, kind, tuple(Tile(code) for code in tiles), 0 if kind == "chi" else None)
        expected = _reference(seq=103, history=history, melds=((), (meld,), (), ()),
                              last_discard_seq=102, river=(Tile("9t"), Tile("9t")))
        report = compare_observations(window.observation, expected, boundary_verified=True)
        assert not report.differences, report
        missing = replace(window.observation, public_history=window.observation.public_history[1:])
        assert compare_observations(missing, expected, boundary_verified=True).history_status == "failed"
        broken = replace(history[0], tiles=(Tile("9t"),)) if kind == "chi" else replace(history[0], detail_kind=None)
        corrupted = replace(window.observation, public_history=(broken,) + history[1:])
        detected = compare_observations(corrupted, expected, boundary_verified=True)
        assert detected.history_status == "failed"
        assert any(item.path.startswith("public_history[seq=101]") for item in detected.differences)
    finally:
        await session.aclose("test_done")


@pytest.mark.asyncio
async def test_same_seq_phase_migration_is_a_different_comparison_boundary():
    session, _, _ = _session([
        _snapshot(100, phase="response_peng"),
        _snapshot(100, phase="response_chi"),
    ])
    try:
        peng = await asyncio.wait_for(session.next_item(), 1)
        chi = await asyncio.wait_for(session.next_item(), 1)
        assert isinstance(peng, ObservedActionWindow) and isinstance(chi, ObservedActionWindow)
        assert peng.observation.consumed_seq == chi.observation.consumed_seq == 100
        assert peng.window_key != chi.window_key
        report = compare_observations(peng.observation, chi.observation, boundary_verified=True)
        assert report.status == "not_checked"
        assert "boundary.phase" in [item.path for item in report.boundary_differences]
    finally:
        await session.aclose("test_done")


def test_equal_values_need_verified_boundary_and_known_information():
    partial = _reference()
    assert compare_observations(partial, partial).status == "not_checked"
    assert compare_observations(partial, partial, boundary_verified=True).status == "not_checked"
    complete = replace(partial, history_complete=True, gang_draw=False)
    assert compare_observations(complete, complete, boundary_verified=True).status == "passed"
    stale = replace(complete, consumed_seq=102)
    assert compare_observations(stale, complete, boundary_verified=True).status == "not_checked"


@pytest.mark.asyncio
async def test_snapshot_and_incremental_sessions_match_same_independent_state_reference():
    final = _snapshot(101, turn=2)
    final["snapshot"].update(drawn_tile="中", wall_remaining=39, hand_counts=[13, 13, 14, 13])
    snapshot_session, _, _ = _session([final])
    incremental_session, _, _ = _session([
        _snapshot(), {"events": [{"seq": 101, "type": "tile_drawn", "seat": 2, "tile": "中"}]},
    ])
    try:
        snapshot_window = await asyncio.wait_for(snapshot_session.next_item(), 1)
        incremental_window = await asyncio.wait_for(incremental_session.next_item(), 1)
        reference = _reference()
        # 独立人工参考约束两条路径，而不是只比较两次同一 projector 的结果。
        for observed in (snapshot_window.observation, incremental_window.observation):
            report = compare_observations(observed, reference, boundary_verified=True)
            assert not report.differences
        cross = compare_observations(incremental_window.observation, snapshot_window.observation, boundary_verified=True)
        assert not cross.differences  # snapshot_seq 100/101 是不同基线，消费水位都是101
        assert cross.history_status == "not_checked"
    finally:
        await snapshot_session.aclose("test_done")
        await incremental_session.aclose("test_done")


def test_different_discard_or_draw_marker_is_not_the_same_boundary():
    base = _reference()
    for changed in (
        replace(base, last_discard=PublicDiscard(1, Tile("8t"), 100)),
        replace(base, drawn_tile=Tile("东")),
    ):
        report = compare_observations(changed, base, boundary_verified=True)
        assert report.status == "not_checked"
        assert report.boundary_differences


def test_incomplete_reference_does_not_reject_extra_locally_preserved_history():
    expected = _reference()
    actual = replace(expected, public_history=(PublicEvent(101, "tile_drawn", 2, (Tile("中"),)),))
    report = compare_observations(actual, expected, boundary_verified=True)
    assert not report.differences
    assert report.history_status == "not_checked"


def test_hand_comparison_accepts_both_draw_encodings_without_mutating_observation():
    separate = _reference()
    included = replace(separate, my_hand=separate.my_hand + (separate.drawn_tile,))
    report = compare_observations(included, separate, boundary_verified=True)
    assert not report.differences
    assert len(included.my_hand) == 14
    assert len(separate.my_hand) == 13


def test_hand_normalization_removes_only_one_duplicate_and_preserves_other_order():
    separate = replace(_reference(), drawn_tile=Tile("1w"))
    included = replace(separate, my_hand=separate.my_hand + (Tile("1w"),))
    assert not compare_observations(included, separate, boundary_verified=True).differences
    # 第一张1w是原有副本，不能连同新增摸牌一并去重，也不能排序掉2w/3w倒置。
    reordered = replace(included, my_hand=(included.my_hand[0], included.my_hand[2], included.my_hand[1]) + included.my_hand[3:])
    report = compare_observations(reordered, separate, boundary_verified=True)
    assert report.state_status == "failed"
    assert any(item.path.startswith("my_hand") for item in report.differences)


def test_hand_normalization_does_not_guess_when_counts_disagree():
    separate = _reference()
    inconsistent = replace(separate, my_hand=separate.my_hand + (Tile("东"),))
    report = compare_observations(inconsistent, separate, boundary_verified=True)
    assert report.state_status == "failed"


def test_same_hand_encoding_still_checks_position_of_drawn_tile():
    separate = _reference()
    appended = replace(separate, my_hand=separate.my_hand + (Tile("中"),))
    prepended = replace(separate, my_hand=(Tile("中"),) + separate.my_hand)
    assert compare_observations(appended, prepended, boundary_verified=True).state_status == "failed"
