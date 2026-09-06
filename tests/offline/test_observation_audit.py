"""通过公开离线用例检查缺史不误报通过、跨身份隔离与位置追溯。"""
import gzip
import json
from pathlib import Path

from hangma_bot.offline.observation_audit import audit_observations


def test_received_closure_differences_are_located_and_isolated(tmp_path):
    rows = []
    def add(kind, payload, pid="p1"):
        rows.append({"schema_version": 1, "kind": kind, "context": {"participant_id": pid, "game_id": "g"}, "payload": payload})
    add("raw_protocol_state", {"source": "state_response", "raw": json.dumps({"events": [{"seq": 3, "type": "discard", "seat": 1, "data": {"tile": 4}}]})})
    closure = {"history_closure": "round_changed", "round_no": 1, "history_floor_seq": 1, "history_through_seq": 4, "public_history": []}
    add("authoritative_state", closure)
    add("authoritative_state", closure, pid="p2")
    with gzip.open(tmp_path / "evidence.jsonl.gz", "wt") as handle:
        handle.write("".join(json.dumps(r) + "\n" for r in rows))
    report = audit_observations(tmp_path, ruleset_version="test")
    one, two = report["games"]
    assert one["closures"][0]["status"] == "different"
    assert one["closures"][0]["received_missing"] == [3]
    assert one["closures"][0]["file"] == "evidence.jsonl.gz"
    assert one["closures"][0]["line"] == 2
    assert two["closures"][0]["status"] == "not_checked"


def test_malformed_and_partial_raw_leave_visible_issues(tmp_path):
    row = {"schema_version": 1, "kind": "raw_protocol_state", "context": {"participant_id": "p", "game_id": "g"},
        "payload": {"source": "state_response", "raw": "not-json"}}
    (tmp_path / "evidence.jsonl").write_text(json.dumps(row) + "\n" + '{"kind":')
    report = audit_observations(tmp_path, ruleset_version="test")
    assert report["reader_issues"]
    assert report["games"][0]["issues"][0]["issue"] == "raw_unparseable"


def test_official_comparison_masks_other_draw_and_reports_unreceived_events(tmp_path):
    raw = json.loads((Path(__file__).parents[1] / "fixtures/official/v8/state_response_snapshot_draw.json").read_text())
    masked = {"seq": 100, "type": "tile_drawn", "seat": 1, "tile": "", "data": None, "ts": 10}
    raw["events"] = [masked]
    row = {"schema_version": 1, "kind": "raw_protocol_state", "context": {"participant_id": "p", "game_id": "g"},
        "payload": {"source": "state_response", "raw": json.dumps(raw)}}
    (tmp_path / "raw.jsonl").write_text(json.dumps(row) + "\n")
    official = [{"file": "official/hash/events.json", "sha256": "hash", "document": {"game_id": "g", "blocks": [{"events": [
        dict(masked, tile="5w", data={"gang_replenish": True}),
        {"seq": 99, "type": "tile_discarded", "seat": 0, "tile": "1w", "data": None, "ts": 9}]}]}}]
    comparison = audit_observations(tmp_path, ruleset_version="test", official=official)["games"][0]["official_comparisons"][0]
    assert comparison["not_received"] == [99]
    assert comparison["received_field_differences"] == []
    assert comparison["status"] == "different"
    assert comparison["sha256"] == "hash"
