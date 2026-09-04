"""同步状态机测试：重复 seq、缺口、gap、未知事件与全量替换。"""
from __future__ import annotations

from hangma_bot.adapters.official.dto import ParsedEvent
from hangma_bot.adapters.official.sync_state import (
    ProtocolSyncState,
    SyncDecision,
)

from _official_testkit import TIMING, load_fixture


def _snapshot(name: str = "state_response_snapshot_draw.json") -> None:
    from hangma_bot.adapters.official.dto import parse_snapshot

    doc = load_fixture(name)
    return parse_snapshot(doc["snapshot"], doc.get("seq"))


def _event(seq: int, type_: str = "tile_discarded") -> ParsedEvent:
    return ParsedEvent(seq=seq, type=type_, seat=0, tiles=("1w",), occurred_at_unix_sec=1756771200)


def test_full_snapshot_replaces_state() -> None:
    state = ProtocolSyncState("g", TIMING)
    state.apply_full_snapshot(_snapshot())
    assert state.has_snapshot and state.last_seq == 101
    assert state.current_observation() is not None

    # 第二次全量替换：序号回退也整体替换（快照是规范真相）
    doc = load_fixture("state_response_snapshot_draw.json")
    doc["seq"] = 90
    from hangma_bot.adapters.official.dto import parse_snapshot

    state.apply_full_snapshot(parse_snapshot(doc["snapshot"], doc["seq"]))
    assert state.last_seq == 90


def test_consecutive_events_accepted() -> None:
    state = ProtocolSyncState("g", TIMING)
    state.apply_full_snapshot(_snapshot())
    result = state.apply_events((_event(102), _event(103)))
    assert result.decision is SyncDecision.ACCEPTED
    assert state.last_seq == 103
    assert len(state.current_observation().public_history) == 2


def test_duplicate_seq_ignored_idempotently() -> None:
    state = ProtocolSyncState("g", TIMING)
    state.apply_full_snapshot(_snapshot())
    result = state.apply_events((_event(101), _event(102), _event(102)))
    assert result.decision is SyncDecision.ACCEPTED
    assert result.ignored_duplicate_seqs == (101, 102)
    assert state.last_seq == 102


def test_seq_gap_triggers_rebuild() -> None:
    state = ProtocolSyncState("g", TIMING)
    state.apply_full_snapshot(_snapshot())
    result = state.apply_events((_event(104),))  # 102/103 缺失
    assert result.decision is SyncDecision.NEEDS_REBUILD
    assert result.reasons[0].startswith("seq_gap:")


def test_explicit_gap_flag_triggers_rebuild() -> None:
    state = ProtocolSyncState("g", TIMING)
    state.apply_full_snapshot(_snapshot())
    result = state.apply_events((_event(102),), gap=True)
    assert result.decision is SyncDecision.NEEDS_REBUILD
    assert result.reasons == ("gap=true",)


def test_events_without_snapshot_rebuild() -> None:
    state = ProtocolSyncState("g", TIMING)
    assert state.apply_events((_event(1),)).decision is SyncDecision.NEEDS_REBUILD


def test_unknown_event_rebuilds_once_then_learned() -> None:
    """未知关键事件重建一次；学习后同类型不再触发重建风暴。"""

    state = ProtocolSyncState("g", TIMING)
    state.apply_full_snapshot(_snapshot())
    first = state.apply_events((_event(102, "future_event"),))
    assert first.decision is SyncDecision.NEEDS_REBUILD
    assert first.reasons[0] == "unknown_event:future_event"

    state.note_rebuild_absorbed("future_event")
    second = state.apply_events((_event(102, "future_event"),))
    assert second.decision is SyncDecision.ACCEPTED
    assert state.last_seq == 102


def test_game_ended_marks_finished() -> None:
    state = ProtocolSyncState("g", TIMING)
    state.apply_full_snapshot(_snapshot())
    state.apply_events((_event(102, "game_ended"),))
    assert state.finished is True
