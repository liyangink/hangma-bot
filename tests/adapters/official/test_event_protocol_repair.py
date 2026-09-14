"""官方 v15 事件边界与观察触发身份修复，均通过公开解析/投影入口验证。"""
from dataclasses import replace
import json
from pathlib import Path

import pytest

from hangma_bot.adapters.official.dto import parse_snapshot, parse_state_response
from hangma_bot.adapters.official.errors import DtoError
from hangma_bot.adapters.official import projector
from hangma_bot.kernel.actions import Tile
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
    assert parsed.events[0].claimed_tile == "6t"
    assert public.claimed_tile == Tile("6t")


def test_v18_chi_fixture_preserves_official_claimed_tile():
    """官方指南 v18，2026-09-06 采集；来源随 action-chain/source.json 保存。"""
    fixture = Path(__file__).parents[2] / "fixtures/official/v18/action-chain/chi-gang-draw.json"
    trace = json.loads(fixture.read_text(encoding="utf-8"))
    events = parse_state_response({"events": trace["events"]}).events
    chi = next(event for event in events if event.type == "chi")
    assert chi.seq == 2267
    assert chi.claimed_tile == "9t"
    assert projector.public_event(chi).claimed_tile == Tile("9t")


@pytest.mark.parametrize("payload,expected_tiles", [
    ({"tiles": ["7t", "8t"]}, ("7t", "8t", "9t")),
    ({"tiles": ["9t", "7t", "8t"]}, ("9t", "7t", "8t")),
    ({"data": {"tiles": ["7t", "9t", "8t"]}}, ("7t", "9t", "8t")),
])
def test_chi_top_level_tile_is_preserved_separately_from_combination(payload, expected_tiles):
    """旧两张自有牌、新三张完整组合均只用顶层 tile 确认供牌。"""
    doc = event_doc("chi", tile="9t")
    doc["events"][0].update(payload)
    parsed = parse_state_response(doc).events[0]
    public = projector.public_event(parsed)
    assert parsed.claimed_tile == "9t"
    assert public.claimed_tile == Tile("9t")
    assert tuple(tile.code for tile in public.tiles) == expected_tiles


@pytest.mark.parametrize("tile_fields", [{}, {"tile": None}, {"tile": ""}])
@pytest.mark.parametrize("combination_fields", [
    {"data": {"tiles": ["7t", "9t", "8t"], "tile": "9t", "claimed_tile": "9t"}},
    {"tiles": ["7t", "9t", "8t"]},
])
def test_chi_missing_top_level_tile_does_not_guess_claimed_tile(tile_fields, combination_fields):
    """兼容缺字段旧事件，不按三张位置或未声明的 data 字段猜供牌。"""
    event = {"seq": 103, "type": "chi", "seat": 1, **combination_fields, **tile_fields}
    parsed = parse_state_response({"events": [event]}).events[0]
    assert parsed.claimed_tile is None
    public = projector.public_event(parsed)
    assert public.claimed_tile is None
    assert tuple(tile.code for tile in public.tiles) == ("7t", "9t", "8t")


@pytest.mark.parametrize("kind,tile", [
    ("tile_drawn", "9t"), ("tile_drawn", ""), ("tile_discarded", "9t"),
    ("peng", "9t"), ("gang", "9t"), ("pass", ""),
])
def test_claimed_tile_is_only_a_chi_fact(kind, tile):
    parsed = parse_state_response(event_doc(kind, tile=tile)).events[0]
    assert parsed.claimed_tile is None
    assert projector.public_event(parsed).claimed_tile is None


@pytest.mark.parametrize("tile", ["10t", "6t", False, 9, ["9t"]])
def test_bad_claimed_tile_keeps_dto_recovery_path(tile):
    with pytest.raises(DtoError):
        parse_state_response(event_doc("chi", tile=tile, data={"tiles": ["7t", "8t", "9t"]}))


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
