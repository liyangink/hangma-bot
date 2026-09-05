"""共用读取器测试：位置化损坏、尾部半行、gzip 分段与 bundle 清单校验。"""

from __future__ import annotations

import gzip
import json

import pytest

from hangma_bot.adapters.recording.reader import (
    ReadRecord,
    read_bundle_manifest,
    read_records,
)


def _envelope(kind="run_manifest", payload=None):
    return {
        "schema_version": 1,
        "kind": kind,
        "context": {"run_id": "r1", "tournament_id": "t1", "participant_id": "p1"},
        "wall_time_unix_ms": 1,
        "monotonic_ns": 1,
        "payload": payload or {},
    }


def test_reads_records_with_positions(tmp_path):
    target = tmp_path / "participants" / "p1"
    target.mkdir(parents=True)
    (target / "decisions.jsonl").write_text(
        json.dumps(_envelope()) + chr(10) + json.dumps(_envelope("lifecycle_changed")) + chr(10),
        encoding="utf-8",
    )
    result = read_records(tmp_path)
    assert len(result.records) == 2
    assert result.records[0].relative_path == "participants/p1/decisions.jsonl"
    assert result.records[0].line_no == 1
    assert result.records[1].line_no == 2
    assert result.issues == ()


def test_corrupt_line_reported_with_position_not_dropped(tmp_path):
    target = tmp_path / "a.jsonl"
    target.write_text('{"schema_version":1,' + chr(10), encoding="utf-8")
    result = read_records(tmp_path)
    assert len(result.records) == 1
    record = result.records[0]
    assert record.error is not None
    assert "json_decode_error" in record.error
    assert record.line_no == 1
    assert len(result.issues) == 1


def test_trailing_partial_line_is_deferred(tmp_path):
    target = tmp_path / "a.jsonl"
    target.write_text(json.dumps(_envelope()), encoding="utf-8")  # 无换行结尾
    result = read_records(tmp_path)
    assert all(record.error is not None for record in result.records)
    assert any("trailing_partial_line" in issue.issue for issue in result.issues)


def test_gzip_segments_are_read(tmp_path):
    target = tmp_path / "raw" / "g1.00001.jsonl.gz"
    target.parent.mkdir(parents=True)
    with gzip.open(target, "wt", encoding="utf-8", newline=chr(10)) as handle:
        handle.write(json.dumps(_envelope("raw_protocol_state", {"source": "state_response"})))
        handle.write(chr(10))
    result = read_records(tmp_path)
    assert len(result.records) == 1
    assert result.records[0].kind == "raw_protocol_state"
    assert result.issues == ()


def test_truncated_gzip_reports_unclosed(tmp_path):
    target = tmp_path / "g.jsonl.gz"
    with gzip.open(target, "wb") as handle:
        handle.write(
            (json.dumps(_envelope()) + chr(10)).encode("utf-8")
        )
    # 手工截断 gzip trailer：读到最后应报未闭合，不悄悄当完整。
    data = target.read_bytes()
    target.write_bytes(data[:-8])
    result = read_records(tmp_path)
    assert any("gzip_tail_unclosed" in issue.issue for issue in result.issues)


def test_bundle_manifest_round_trip(tmp_path):
    document = {
        "bundle_schema_version": 1,
        "bundle_id": "b-1",
        "created_at_unix_ms": 123,
        "run_ids": ["run-1"],
        "parent_bundle_ids": [],
        "closed_cleanly_by_run": True,
        "source_notes": "",
        "files": [
            {"path": "runs/run-1/summary.json", "bytes": 2, "sha256": "ab" * 32},
        ],
    }
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    manifest = read_bundle_manifest(path)
    assert manifest.bundle_id == "b-1"
    assert manifest.files[0].path == "runs/run-1/summary.json"


def test_bundle_manifest_rejects_unknown_major(tmp_path):
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps({"bundle_schema_version": 2, "bundle_id": "b"}), encoding="utf-8")
    with pytest.raises(ValueError):
        read_bundle_manifest(path)


def test_bundle_manifest_rejects_traversal(tmp_path):
    document = {
        "bundle_schema_version": 1,
        "bundle_id": "b-1",
        "created_at_unix_ms": 1,
        "run_ids": ["r"],
        "parent_bundle_ids": [],
        "closed_cleanly_by_run": True,
        "source_notes": "",
        "files": [
            {"path": "../escape.json", "bytes": 0, "sha256": "ab" * 32},
        ],
    }
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError):
        read_bundle_manifest(path)
