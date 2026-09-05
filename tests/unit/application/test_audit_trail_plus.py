"""AuditTrail 生产端失败持久化测试（审查 S1 验收）。

验收目标：让 payload 构造（codec）抛异常、记录器正常工作并关闭，
跨目录读取的报告必须包含这次失败、正确关联决策并标记不完整
（producer_failure 记录 + producer_summary + 合并后的 audit_degraded）。
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from hangma_bot.adapters.recording import JsonlAuditSink, validate_run
from hangma_bot.application.audit import AuditTrail
from hangma_bot.application.contracts import AuditKind
from hangma_bot.application.deadline import ManualClock
from hangma_bot.adapters.recording.reader import read_records


def _trail(sink):
    return AuditTrail(
        sink,
        run_id="run-1",
        tournament_id="t1",
        participant_id="p1",
        clock=ManualClock(),
    )


@pytest.mark.asyncio
async def test_construction_failure_persists_as_producer_failure():
    """codec 构造失败：失败事实可迁移、关联决策、汇总诚实降级。"""

    with tempfile.TemporaryDirectory() as temp:
        sink = JsonlAuditSink(temp, "run-1")
        trail = _trail(sink)

        def broken_factory():
            raise ValueError("codec 故障注入：非有限浮点")

        receipt = trail.emit_safe(
            AuditKind.DECISION_INPUT,
            payload_factory=broken_factory,
            stage="decision_input_encode",
            game_id="g1",
            round_no=1,
            trigger_seq=10,
            decision_id="dec-1",
        )
        assert receipt.queued is False and receipt.audit_degraded is True
        assert trail.producer_attempts == 1
        assert trail.construction_failures == 1
        assert trail.audit_degraded is True

        summary = await trail.aclose(timeout_seconds=5.0)
        # 合并口径：构造失败计入缺失，关闭汇总必须反映生产端失败。
        assert summary.missing_high_priority == 1
        assert summary.audit_degraded is True

        # 跨目录读取：producer_failure 带全部关联键与脱敏错误；
        # producer_summary 带计数；验证器报告缺失关闭证据之外的失败事实。
        result = read_records(sink.run_dir)
        lifecycle = [
            record for record in result.records
            if record.kind == "lifecycle_changed"
        ]
        events = [record.payload["event"] for record in lifecycle]
        assert "producer_failure" in events
        assert "producer_summary" in events
        failure = next(
            record for record in lifecycle if record.payload["event"] == "producer_failure"
        )
        assert failure.payload["area"] == "audit"
        assert failure.payload["original_kind"] == "decision_input"
        assert failure.payload["stage"] == "decision_input_encode"
        assert failure.context["decision_id"] == "dec-1"
        assert failure.context["game_id"] == "g1"
        assert failure.context["round_no"] == 1
        assert failure.context["trigger_seq"] == 10
        assert "ValueError" in failure.payload["error"]
        summary_record = next(
            record for record in lifecycle if record.payload["event"] == "producer_summary"
        )
        assert summary_record.payload["attempts"] == 1
        assert summary_record.payload["construction_failures"] == 1
        # profile 由 manifest 声明（生产方 participant_runtime）后，
        # 验证器用 producer_summary 证明尾部完整。这里手工补一份带
        # capture_profile 的 manifest 再验证：报告必须含 producer_failure
        # 事实且不伪造完整。
        manifest_payload = {
            "run_id": "run-1",
            "capture_profile": "audit-plus-v1",
            "audit_producer": "application",
        }
        manifest = json.dumps(
            {
                "schema_version": 1,
                "kind": "run_manifest",
                "context": {"run_id": "run-1", "tournament_id": "t1", "participant_id": "p1"},
                "wall_time_unix_ms": 1,
                "monotonic_ns": 1,
                "payload": manifest_payload,
            }
        )
        (sink.run_dir / "manifest.json").write_text(manifest + chr(10), encoding="utf-8")
        report = validate_run(sink.run_dir)
        assert report["audit_plus"]["profile"] == "audit-plus-v1"
        assert report["audit_plus"]["tail_complete"] is True
        assert report["audit_plus"]["producer_failure_records"] == 1
        # 构造失败事实已持久化，但决策输入本体缺失：完整可审计不成立。
        assert report["audit_complete"] is False


@pytest.mark.asyncio
async def test_success_path_merges_profile_fields():
    """成功路径：payload 自动携带 capture_profile/audit_producer。"""

    sink = JsonlAuditSink.__new__(JsonlAuditSink)  # 不启动线程；用内存替身代替
    from fakes import InMemoryAuditSink

    memory = InMemoryAuditSink()
    trail = _trail(memory)
    receipt = trail.emit_safe(
        AuditKind.DECISION_ENDED,
        payload_factory=lambda: {"plan_revision": 1, "end_reason": "exhausted"},
        stage="decision_ended_encode",
        decision_id="dec-9",
    )
    assert receipt.queued is True
    record = memory.find(AuditKind.DECISION_ENDED)[0]
    assert record.payload["capture_profile"] == "audit-plus-v1"
    assert record.payload["audit_producer"] == "application"
    assert record.payload["end_reason"] == "exhausted"
    assert trail.producer_attempts == 1
    assert trail.construction_failures == 0


@pytest.mark.asyncio
async def test_aclose_repeat_does_not_duplicate_summary():
    memory = __import__("fakes", fromlist=["InMemoryAuditSink"]).InMemoryAuditSink()
    trail = _trail(memory)
    first = await trail.aclose(timeout_seconds=1.0)
    second = await trail.aclose(timeout_seconds=1.0)
    summaries = [
        record for record in memory.records
        if record.payload.get("event") == "producer_summary"
    ]
    assert len(summaries) == 1
    assert first.missing_high_priority == second.missing_high_priority
