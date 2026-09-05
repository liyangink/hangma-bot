"""验证器 audit-plus-v1 增强校验测试（方案 §7.2：以 profile 开启）。

- 旧目录（无 capture_profile）结论与升级前一致（legacy）；
- profile 运行缺 producer_summary → 尾部完整性未知（violation）；
- 存在 producer_failure → 运行不完整（violation）；
- DECISION_INPUT 无 DECISION_ENDED → violation；终结无输入 → warning；
- 完整 profile 运行（含 producer_summary）通过且 tail_complete=true。
"""

from __future__ import annotations

import asyncio
import json

import pytest

from hangma_bot.adapters.recording import JsonlAuditSink, validate_run
from hangma_bot.application.audit import AuditTrail
from hangma_bot.application.contracts import AuditKind
from hangma_bot.application.deadline import ManualClock

from ._helpers import make_record


def _write_manifest(run_dir, with_profile: bool):
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_dir.name,
    }
    if with_profile:
        payload["capture_profile"] = "audit-plus-v1"
        payload["audit_producer"] = "application"
    envelope = {
        "schema_version": 1,
        "kind": "run_manifest",
        "context": {"run_id": run_dir.name, "tournament_id": "t1", "participant_id": "p1"},
        "wall_time_unix_ms": 1,
        "monotonic_ns": 1,
        "payload": payload,
    }
    (run_dir / "manifest.json").write_text(json.dumps(envelope) + chr(10), encoding="utf-8")


@pytest.mark.asyncio
async def test_legacy_run_without_profile_unchanged(tmp_path):
    """旧目录无 capture_profile：不触发任何 audit-plus violation。"""

    sink = JsonlAuditSink(tmp_path, "run-legacy")
    trail = AuditTrail(
        sink, run_id="run-legacy", tournament_id="t1", participant_id="p1",
        clock=ManualClock(),
    )
    trail.emit(
        AuditKind.LIFECYCLE_CHANGED,
        {"event": "status_changed", "from": "registering", "to": "running"},
    )
    trail.emit(
        AuditKind.PARTICIPANT_FINISHED,
        {"reason": "cancelled", "detail": "x"},
    )
    await trail.aclose(timeout_seconds=5.0)
    _write_manifest(sink.run_dir, with_profile=False)
    report = validate_run(sink.run_dir)
    assert report["audit_plus"]["profile"] == "legacy"
    assert report["audit_complete"] is True
    assert not any(f["code"].startswith("producer") for f in report["findings"])
    assert not any(f["code"].startswith("decision_input") for f in report["findings"])


@pytest.mark.asyncio
async def test_profile_run_missing_producer_summary_is_tail_unknown(tmp_path):
    """profile 开启但被强杀（无 producer_summary）：尾部完整性未知。"""

    sink = JsonlAuditSink(tmp_path, "run-killed")
    trail = AuditTrail(
        sink, run_id="run-killed", tournament_id="t1", participant_id="p1",
        clock=ManualClock(),
    )
    trail.emit_safe(
        AuditKind.DECISION_INPUT,
        payload_factory=lambda: {"plan_revision": 1, "request": {}},
        stage="decision_input_encode",
        decision_id="dec-1",
    )
    # 模拟强杀：不 aclose，直接把已写出的文件留下；补 summary.json 模拟
    # 部分关闭（记录器关闭写出 summary 是独立失败面）。
    # 此处不写 summary：missing_summary 与 missing_producer_summary 都应报告。
    _write_manifest(sink.run_dir, with_profile=True)
    report = validate_run(sink.run_dir)
    codes = [f["code"] for f in report["findings"]]
    assert "missing_producer_summary" in codes
    assert report["audit_plus"]["tail_complete"] is False
    assert report["audit_complete"] is False


@pytest.mark.asyncio
async def test_profile_run_with_decision_input_without_end_is_violation(tmp_path):
    sink = JsonlAuditSink(tmp_path, "run-half")
    trail = AuditTrail(
        sink, run_id="run-half", tournament_id="t1", participant_id="p1",
        clock=ManualClock(),
    )
    trail.emit_safe(
        AuditKind.DECISION_INPUT,
        payload_factory=lambda: {"plan_revision": 1, "request": {}},
        stage="decision_input_encode",
        decision_id="dec-1",
    )
    await trail.aclose(timeout_seconds=5.0)
    _write_manifest(sink.run_dir, with_profile=True)
    report = validate_run(sink.run_dir)
    codes = [f["code"] for f in report["findings"]]
    assert "decision_input_without_end" in codes
    assert report["audit_complete"] is False


@pytest.mark.asyncio
async def test_full_profile_run_passes_with_tail_complete(tmp_path):
    sink = JsonlAuditSink(tmp_path, "run-ok")
    trail = AuditTrail(
        sink, run_id="run-ok", tournament_id="t1", participant_id="p1",
        clock=ManualClock(),
    )
    trail.emit(
        AuditKind.LIFECYCLE_CHANGED,
        {"event": "status_changed", "from": "registering", "to": "running"},
    )
    trail.emit_safe(
        AuditKind.DECISION_INPUT,
        payload_factory=lambda: {"plan_revision": 1, "request": {}},
        stage="decision_input_encode",
        decision_id="dec-1",
    )
    trail.emit_safe(
        AuditKind.DECISION_ENDED,
        payload_factory=lambda: {
            "plan_revision": 1, "end_reason": "exhausted",
            "attempt_count": 0, "sent_attempts": 0,
        },
        stage="decision_ended_encode",
        decision_id="dec-1",
    )
    trail.emit(
        AuditKind.PARTICIPANT_FINISHED,
        {"reason": "cancelled", "detail": "x"},
    )
    await trail.aclose(timeout_seconds=5.0)
    _write_manifest(sink.run_dir, with_profile=True)
    report = validate_run(sink.run_dir)
    assert report["audit_plus"]["profile"] == "audit-plus-v1"
    assert report["audit_plus"]["tail_complete"] is True
    assert report["audit_plus"]["producer_failure_records"] == 0
    assert report["audit_plus"]["decisions_with_input"] == 1
    assert report["audit_plus"]["decisions_ended"] == 1
    assert report["audit_complete"] is True
