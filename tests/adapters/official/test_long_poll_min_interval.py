"""同场普通长轮询底档：只延后重挂，不阻塞快照和高优先级事件发现。"""

import json

import pytest

from _official_testkit import FakeAuditSink, FakeTransport, TIMING, load_fixture, make_audit_context
from _virtual_clock import VirtualClock
from test_sync_repair_regressions import snapshot

from hangma_bot.adapters.official.game import OfficialGameSession
from hangma_bot.adapters.official.scheduler import RequestScheduler
from hangma_bot.application.contracts import GameFinished


async def _run_responses(responses, *, interval_ms=50):
    clock = VirtualClock()
    audit, transport = FakeAuditSink(), FakeTransport()
    calls = []

    def handler(*, method, params, **kwargs):
        assert method == "GET"
        calls.append((params["seq"], clock.monotonic()))
        return 200, json.dumps(responses[len(calls) - 1])

    transport.handler = handler
    session = OfficialGameSession(
        game_id="spacing", transport=transport,
        scheduler=RequestScheduler(clock=clock.monotonic, sleep=clock.sleep).for_game(
            "spacing", max_games=10),
        timing=TIMING, monotonic_clock=clock.monotonic, wall_clock_unix_ms=clock.wall_ms,
        audit=audit, audit_context=make_audit_context, retry_sleep=clock.sleep,
        discard_pacing_enabled=False, ordinary_long_poll_min_interval_ms=interval_ms,
    )
    try:
        assert isinstance(await clock.run(session.next_item()), GameFinished)
        timings = [row.payload["request_timing"] for row in audit.records
                   if row.payload.get("phase") == "started" and row.payload.get("method") == "GET"]
        return calls, timings
    finally:
        await session.aclose("test")


PASS_EVENT = {"seq": 102, "events": [{"seq": 102, "type": "pass", "seat": 0,
                                       "data": None}], "gap": False}


async def test_consecutive_ordinary_incremental_long_polls_have_50ms_start_floor():
    calls, timings = await _run_responses([
        snapshot(101, turn=0),
        PASS_EVENT,
        {"pending": True},
        {"pending": True},
        load_fixture("state_response_finished.json"),
    ])
    assert [seq for seq, _ in calls] == [0, 101, 102, 102, 102]
    assert [at for _, at in calls] == pytest.approx([0, 0, 0, .05, .10])
    assert "ordinary_long_poll_not_before_monotonic" not in timings[2]
    assert timings[3]["ordinary_long_poll_min_interval_ms"] == 50
    assert timings[3]["ordinary_long_poll_not_before_monotonic"] == pytest.approx(.05)


async def test_pass_boundary_exempts_next_poll_then_resumes_60ms_floor():
    calls, timings = await _run_responses([
        snapshot(101, turn=0),
        PASS_EVENT,
        {"seq": 103, "events": [
            {"seq": 103, "type": "pass", "seat": 0, "data": None},
        ], "gap": False},
        {"pending": True},
        {"pending": True},
        load_fixture("state_response_finished.json"),
    ], interval_ms=60)
    assert [seq for seq, _ in calls] == [0, 101, 102, 103, 103, 103]
    assert [at for _, at in calls] == pytest.approx([0, 0, 0, 0, .06, .12])
    assert "ordinary_long_poll_not_before_monotonic" not in timings[3]
    assert timings[4]["ordinary_long_poll_min_interval_ms"] == 60


async def test_opponent_draw_recovery_bypasses_ordinary_floor():
    calls, timings = await _run_responses([
        snapshot(101, turn=0),
        PASS_EVENT,
        {"seq": 103, "events": [{"seq": 103, "type": "tile_drawn", "seat": 0,
                                  "tile": "3w", "data": None}], "gap": False},
        load_fixture("state_response_finished.json"),
    ])
    # 当前同步器将该不连续摸牌链升级为权威快照；快照不得继承普通底档。
    assert [seq for seq, _ in calls] == [0, 101, 102, 0]
    assert [at for _, at in calls] == pytest.approx([0, 0, 0, 0])
    assert timings[1]["scheduler_priority"] == "DRAW_WATCH"
    assert timings[3]["scheduler_priority"] == "RECOVERY"
    assert "ordinary_long_poll_not_before_monotonic" not in timings[3]


async def test_gap_rebuild_snapshot_is_immediate():
    calls, timings = await _run_responses([
        snapshot(101, turn=0),
        PASS_EVENT,
        {"seq": 102, "events": [], "gap": True},
        load_fixture("state_response_finished.json"),
    ])
    assert [seq for seq, _ in calls] == [0, 101, 102, 0]
    assert [at for _, at in calls] == pytest.approx([0, 0, 0, 0])
    assert "ordinary_long_poll_not_before_monotonic" not in timings[3]
