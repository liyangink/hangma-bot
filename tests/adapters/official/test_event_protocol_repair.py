"""官方 v15 事件边界与观察触发身份修复，均通过公开解析/投影入口验证。"""
from dataclasses import replace

import pytest

from hangma_bot.adapters.official.dto import parse_snapshot, parse_state_response
from hangma_bot.adapters.official.errors import DtoError
from hangma_bot.adapters.official import projector
from hangma_bot.kernel.config import TimingConfig

from _official_testkit import load_fixture


def event_doc(kind, *, tile="", seat=1, data=None):
    return {"events": [{"seq": 103, "type": kind, "seat": seat, "tile": tile, "data": data}]}


@pytest.mark.parametrize("kind", ["pass", "timeout", "round_ended", "game_ended"])
def test_official_empty_tile_events_are_preserved(kind):
    parsed = parse_state_response(event_doc(kind, seat=-1 if kind.endswith("ended") else 1))
    event = projector.public_event(parsed.events[0])
    assert event.kind == kind
    assert event.tiles == ()
    assert event.seat == (None if kind.endswith("ended") else 1)


def test_chi_preserves_complete_ordered_combination_without_duplicate_claimed_tile():
    parsed = parse_state_response(event_doc("chi", tile="6t", data={"tiles": ["7t", "8t", "6t"]}))
    public = projector.public_event(parsed.events[0])
    assert tuple(tile.code for tile in public.tiles) == ("7t", "8t", "6t")


@pytest.mark.parametrize("kind,tile,detail", [("gang", "6t", "added"), ("timeout", "", "peng")])
def test_action_detail_reaches_public_event(kind, tile, detail):
    parsed = parse_state_response(event_doc(kind, tile=tile, data={"kind": detail, "private_hand": ["白"]}))
    public = projector.public_event(parsed.events[0])
    assert public.detail_kind == detail
    assert not hasattr(public, "data")


@pytest.mark.parametrize("kind", ["tile_drawn", "tile_discarded", "chi", "peng", "gang"])
@pytest.mark.parametrize("tile", ["", "10w", False])
def test_tile_actions_do_not_accept_missing_or_bad_tiles(kind, tile):
    if kind == "tile_drawn" and tile == "":
        assert parse_state_response(event_doc(kind, tile=tile)).events[0].tiles == ()
        return  # 是否为本人缺牌，由拥有座位上下文的同步层判断
    with pytest.raises(DtoError):
        parse_state_response(event_doc(kind, tile=tile))


@pytest.mark.parametrize("kind", ["tile_drawn", "tile_discarded", "chi", "peng", "gang", "pass", "timeout"])
def test_player_action_seat_sentinel_is_not_a_real_player(kind):
    with pytest.raises(DtoError):
        parse_state_response(event_doc(kind, tile="1w", seat=-1))


@pytest.mark.parametrize("data", [{"tiles": ["7t", "8t"]}, {"tiles": ["1w", "2w", "3w"]}, {"tiles": "6t"}])
def test_malformed_chi_combination_requires_recovery(data):
    with pytest.raises(DtoError):
        parse_state_response(event_doc("chi", tile="6t", data=data))


@pytest.mark.parametrize("field,value", [
    ("baotou", ""), ("baotou", []), ("baotou", 0), ("baotou", None),
    ("catch_play", ""), ("catch_play", {}), ("catch_play", 0),
    ("chain_count", False), ("chain_count", ""), ("chain_count", []), ("chain_count", -1),
])
def test_invalid_god_values_do_not_silently_turn_off(field, value):
    doc = load_fixture("state_response_snapshot_peng.json")
    doc["snapshot"]["god"][field] = value
    with pytest.raises(DtoError):
        parse_state_response(doc)


def test_active_snapshot_requires_all_god_fields():
    doc = load_fixture("state_response_snapshot_peng.json")
    del doc["snapshot"]["god"]["baotou"]
    with pytest.raises(DtoError):
        parse_state_response(doc)


def test_terminal_snapshot_may_omit_nonactionable_god_object():
    doc = load_fixture("state_response_snapshot_peng.json")
    doc["snapshot"]["phase"] = "finished"
    del doc["snapshot"]["god"]
    assert parse_state_response(doc).snapshot.god_chain_count == 0


def test_new_structured_discard_outweighs_retained_old_history():
    doc = load_fixture("state_response_snapshot_peng.json")
    snapshot = parse_snapshot(doc["snapshot"], doc.get("seq"))
    snapshot = replace(snapshot, seq=500, last_discard=(1, "6t", 499))
    window = projector.detect_window(snapshot, TimingConfig(1.0, 1.0, 3.0), "g", event_stream_discard=(119, "2w", 1))
    assert window.window_key.trigger_seq == 499


def test_retained_history_must_match_bare_current_discard():
    doc = load_fixture("state_response_snapshot_peng.json")
    snapshot = parse_snapshot(doc["snapshot"], doc.get("seq"))
    snapshot = replace(snapshot, seq=500, last_discard="6t")
    window = projector.detect_window(snapshot, TimingConfig(1.0, 1.0, 3.0), "g", event_stream_discard=(119, "2w", 1))
    assert window.window_key.trigger_seq == 500


def test_new_incremental_discard_outweighs_older_structured_snapshot():
    doc = load_fixture("state_response_snapshot_peng.json")
    snapshot = parse_snapshot(doc["snapshot"], doc.get("seq"))
    window = projector.detect_window(snapshot, TimingConfig(1.0, 1.0, 3.0), "g", event_stream_discard=(501, "6t", 1))
    assert window.window_key.trigger_seq == 501
