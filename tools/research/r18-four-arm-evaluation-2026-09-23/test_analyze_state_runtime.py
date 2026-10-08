"""赛后时限统计必须按真实弃牌周期去掉旧快照重复窗。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/r18-four-arm-evaluation-2026-09-23'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import importlib.util
import json
from pathlib import Path


SOURCE = Path(__file__).with_name("analyze_state_runtime.py")
SPEC = importlib.util.spec_from_file_location("state_runtime_report", SOURCE)
REPORT = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(REPORT)


def test_no_input_window_after_handled_chi_is_not_counted_as_new_miss(tmp_path):
    """吃窗已进策略后，超时事件推进 seq 却未换弃牌，不产生第二次机会。"""
    raw = tmp_path / "participants" / "u" / "raw" / "g.jsonl"
    raw.parent.mkdir(parents=True)
    raw.write_text(json.dumps({
        "payload": {"endpoint": "GET /api/games/g/state", "raw": json.dumps({
            "events": [
                {"seq": 10, "type": "tile_discarded"},
                {"seq": 11, "type": "timeout"},
                {"seq": 12, "type": "timeout"},
            ]})}
    }) + "\n")
    handled = {"input": True, "input_window": {
        "game_id": "g", "round_no": 1, "trigger_seq": 10,
        "phase": "response_chi", "seat": 2}}
    repeated = {"ended": {"end_reason": "deadline", "window": {
        "game_id": "g", "round_no": 1, "trigger_seq": 12,
        "phase": "response_chi", "seat": 2}}}
    result = REPORT.reconstruct_no_input_windows(tmp_path, {}, {"a": handled, "b": repeated})
    assert result["previously_handled"] == 1
    assert result["candidate_windows"] == []
    assert result["unknown"] == 0


def test_new_discard_is_not_removed_by_prior_chi(tmp_path):
    """新弃牌虽同一单局同一阶段，仍须单独重建，不能按时段粗略去重。"""
    raw = tmp_path / "participants" / "u" / "raw" / "g.jsonl"
    raw.parent.mkdir(parents=True)
    raw.write_text(json.dumps({
        "payload": {"endpoint": "GET /api/games/g/state", "raw": json.dumps({
            "events": [
                {"seq": 10, "type": "tile_discarded"},
                {"seq": 13, "type": "tile_discarded"},
            ]})}
    }) + "\n")
    handled = {"input": True, "input_window": {
        "game_id": "g", "round_no": 1, "trigger_seq": 10,
        "phase": "response_chi", "seat": 2}}
    missed = {"ended": {"end_reason": "deadline", "window": {
        "game_id": "g", "round_no": 1, "trigger_seq": 13,
        "phase": "response_chi", "seat": 2}}}
    result = REPORT.reconstruct_no_input_windows(tmp_path, {}, {"a": handled, "b": missed})
    assert result["previously_handled"] == 0
    assert result["unknown_windows"] == [{
        "game_id": "g", "round_no": 1, "trigger_seq": 13,
        "phase": "response_chi"}]


def test_watchdog_get_uses_origin_after_request_purpose_changes(tmp_path):
    """过期看门狗改查当前状态仍计入看门狗；旧日志不能伪装成精确总数。"""
    (tmp_path / "manifest.json").write_text(json.dumps({"payload": {"run_id": "test"}}))
    raw = tmp_path / "participants" / "u" / "raw" / "g.jsonl"
    raw.parent.mkdir(parents=True)

    def record(purpose, origin=None):
        timing = {"query_purpose": purpose}
        if origin is not None:
            timing["query_origin"] = origin
        return json.dumps({"payload": {
            "endpoint": "GET /api/games/g/state", "request_timing": timing,
        }})

    raw.write_text("\n".join((
        record("current_state_sync", "phase_boundary"),
        record("state_sync", "state_sync"),
    )) + "\n")
    result = REPORT.analyze_run(tmp_path)
    assert result["state_get"] == 2
    assert result["purpose_counts"].get("phase_boundary", 0) == 0
    assert result["watchdog_state_get"] == 1
    assert result["watchdog_state_get_pct"] == 50.0
    assert result["watchdog_state_get_by_origin"] == {"phase_boundary": 1}

    with raw.open("a") as handle:
        handle.write(record("phase_boundary") + "\n")
    old_mixed = REPORT.analyze_run(tmp_path)
    assert old_mixed["query_origin_coverage"] == 2
    assert old_mixed["watchdog_state_get"] is None
    assert old_mixed["watchdog_state_get_pct"] is None
    assert old_mixed["watchdog_state_get_by_origin"] is None


def test_sse_watchdogs_count_by_original_trigger(tmp_path):
    """静默、权威年龄、局间和动作链探针均计入看门狗，并保留细分。"""
    (tmp_path / "manifest.json").write_text(json.dumps({"payload": {"run_id": "sse-test"}}))
    raw = tmp_path / "participants" / "u" / "raw" / "g.jsonl"
    raw.parent.mkdir(parents=True)
    origins = [
        "state_sync", "phase_boundary", "sse_boundary", "sse_own_discard_probe",
        "sse_phase_probe", "sse_silence_probe", "sse_state_age_probe", "sse_settled_probe",
    ]
    raw.write_text("\n".join(json.dumps({"payload": {
        "endpoint": "GET /api/games/g/state", "request_timing": {
            "query_purpose": "current_state_sync" if origin == "sse_state_age_probe" else origin,
            "query_origin": origin,
        },
    }}) for origin in origins) + "\n")

    result = REPORT.analyze_run(tmp_path)
    assert result["state_get"] == 8
    assert result["watchdog_state_get"] == 7
    assert result["watchdog_state_get_pct"] == 87.5
    assert result["watchdog_state_get_by_origin"] == {
        origin: 1 for origin in origins if origin != "state_sync"
    }
