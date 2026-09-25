"""汇总脚本的行为回归：用合成审计验证计数、分层与"未观测不写 0"。

脚本与判据见 review/wiring-queue-rootcause-2026-09-25/ROOT-CAUSE-2026-09-25.md。
本测试只构造最小审计目录，不联网、不读真实审计。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT = (Path(__file__).resolve().parents[2]
           / "review/wiring-queue-rootcause-2026-09-25/summarize_wait_observability.py")


def _load():
    spec = importlib.util.spec_from_file_location("summarize_wait_observability", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sw = _load()


def _write(audit_root: Path, slot: str, records: list) -> None:
    directory = audit_root / slot / "runs" / "run-x" / "participants" / "u_1"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "decisions.jsonl").open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def _state_started(request_id, purpose, queued, granted, queue=None):
    timing = {"queued_at_monotonic": queued, "granted_at_monotonic": granted,
              "query_purpose": purpose}
    if queue is not None:
        timing["state_queue_at_grant"] = queue
    return {"kind": "http_request", "payload": {
        "request_id": request_id, "endpoint": "GET /api/games/g/state",
        "method": "GET", "phase": "started", "request_timing": timing}}


def _finished_429(request_id):
    return {"kind": "http_request", "payload": {
        "request_id": request_id, "endpoint": "GET /api/games/g/state",
        "method": "GET", "phase": "finished", "http_status": 429,
        "request_timing": {}}}


def _cancelled(purpose, waited, reservation=False):
    return {"kind": "authoritative_state", "payload": {
        "state_wait_outcome": "cancelled_before_send", "query_purpose": purpose,
        "scheduler_priority": "POLL", "waited_sec": waited,
        "had_reservation": reservation, "consumed_seq": 7}}


def _decision(game_id, round_no):
    return {"kind": "decision_input", "context": {"game_id": game_id, "round_no": round_no},
            "payload": {}}


def test_counts_purposes_queue_delays_and_429(tmp_path):
    audit = tmp_path / "audit"
    _write(audit, "slot-a", [
        _state_started("r1", "sse_frame", 10.0, 10.2),
        _state_started("r2", "sse_settled_long_poll", 20.0, 21.0),
        _finished_429("r3"),
        _decision("g1", 1),
        _decision("g1", 2),
    ])
    summary = sw.summarize(audit)
    slot = summary["slots"]["slot-a"]
    assert slot["state_requests"] == 2
    assert slot["by_purpose"] == {"sse_frame": 1, "sse_settled_long_poll": 1}
    assert slot["http_429"] == 1
    # 两样本取整后 p50 落在低位（[200, 1000] 的中位索引为 0）；大样本下无影响。
    assert slot["queue_wait_ms"]["p50"] == pytest.approx(200.0, abs=1.0)
    assert slot["queue_wait_ms"]["p90"] == pytest.approx(1000.0, abs=1.0)
    assert slot["queue_wait_ms"]["max"] == pytest.approx(1000.0, abs=1.0)
    assert slot["decisions"] == 2
    assert slot["game_rounds"] == 2
    assert summary["totals"]["state_per_decision"] == pytest.approx(1.0)


def test_cancelled_before_send_is_layered_by_purpose(tmp_path):
    audit = tmp_path / "audit"
    _write(audit, "slot-a", [
        _cancelled("sse_settled_long_poll", 7.58, reservation=True),
        _cancelled("sse_settled_long_poll", 2.4),
        _cancelled("sse_frame", 0.3),
    ])
    row = sw.summarize(audit)["slots"]["slot-a"]
    assert row["cancelled_before_send"] == {"sse_settled_long_poll": 2, "sse_frame": 1}
    assert row["cancelled_with_reservation"] == 1
    layered = row["cancelled_wait_sec_by_purpose"]["sse_settled_long_poll"]
    assert layered["n"] == 2
    assert layered["max"] == pytest.approx(7.58)


def test_missing_observability_is_reported_as_unobserved_not_zero(tmp_path):
    """旧审计没有新增字段时必须给出 None，不能把"没观测"写成 0。"""

    audit = tmp_path / "audit"
    _write(audit, "slot-a", [_state_started("r1", "sse_frame", 1.0, 1.05)])
    row = sw.summarize(audit)["slots"]["slot-a"]
    assert row["queue_at_grant_waiters"] == {"p50": None, "p90": None, "p99": None, "max": None, "n": 0}
    assert row["cancelled_before_send"] == {}
    assert row["queue_wait_ms"]["n"] == 1


def test_queue_snapshot_at_grant_is_summarized(tmp_path):
    audit = tmp_path / "audit"
    _write(audit, "slot-a", [
        _state_started("r1", "sse_frame", 1.0, 1.1, queue={"waiters_total": 4, "state_used_in_window": 14,
                                                           "ready_state": 3}),
        _state_started("r2", "sse_frame", 2.0, 2.1, queue={"waiters_total": 8, "state_used_in_window": 16,
                                                           "ready_state": 6}),
    ])
    row = sw.summarize(audit)["slots"]["slot-a"]
    assert row["queue_at_grant_waiters"]["max"] == pytest.approx(8.0)
    assert row["queue_at_grant_state_used"]["max"] == pytest.approx(16.0)
    assert row["queue_at_grant_ready_state"]["n"] == 2


def test_multiple_slots_are_aggregated_separately(tmp_path):
    audit = tmp_path / "audit"
    _write(audit, "slot-a", [_state_started("r1", "sse_frame", 1.0, 1.1), _decision("g1", 1)])
    _write(audit, "slot-b", [_state_started("r2", "sse_frame", 1.0, 1.1)])
    summary = sw.summarize(audit)
    assert summary["totals"]["slots"] == 2
    assert summary["totals"]["state_requests"] == 2
    assert summary["slots"]["slot-a"]["decisions"] == 1
    assert summary["slots"]["slot-b"]["decisions"] == 0
    assert summary["slots"]["slot-b"]["state_per_decision"] is None
