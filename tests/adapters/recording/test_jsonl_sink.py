"""JSONL 记录器测试：非阻塞入队、快照所有权、隔离路由与失败注入。

所有测试只通过公开接口 ``emit`` / ``aclose`` 驱动；队列压力与淘汰路径
通过构造函数声明的 ``before_batch_write`` 观察点确定性阻塞写线程后复现，
不依赖线程时序，也不读取内部私有状态。
"""

import json
import threading

from hangma_bot.adapters.recording import JsonlAuditSink
from hangma_bot.application.contracts import AuditKind

from recording._helpers import make_record


def _intent(index: int):
    """一条高优先级提交意图。"""

    return make_record(
        AuditKind.SUBMISSION_INTENT,
        {"action_key": f"discard:{index}w", "based_on_authoritative_seq": 1},
        game_id="G1",
        round_no=1,
        trigger_seq=1,
        decision_id=f"d{index}",
        attempt_no=1,
    )


def _raw(index: int):
    """一条低优先级冗余原始快照。"""

    return make_record(
        AuditKind.RAW_PROTOCOL_STATE,
        {"raw": f"snapshot-{index}"},
        game_id="G1",
        round_no=1,
        trigger_seq=index,
    )


class TestBasicWriteAndContract:
    async def test_emit_returns_queued_receipt_and_close_writes_envelope(self, tmp_path):
        sink = JsonlAuditSink(tmp_path, "run-1")
        receipt = sink.emit(
            make_record(
                AuditKind.LIFECYCLE_CHANGED,
                {"status": "running"},
                wall_time_unix_ms=1700000000000,
                monotonic_ns=42,
            )
        )
        assert receipt.queued is True
        assert receipt.audit_degraded is False
        assert receipt.reason is None

        summary = await sink.aclose(timeout_seconds=5.0)
        assert summary.written == 1
        assert summary.dropped_low_priority == 0
        assert summary.missing_high_priority == 0
        assert summary.serialization_failures == 0
        assert summary.audit_degraded is False

        lines = (tmp_path / "runs" / "run-1" / "lifecycle.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        envelope = json.loads(lines[0])
        assert envelope["schema_version"] == 1
        assert envelope["kind"] == "lifecycle_changed"
        assert envelope["context"]["participant_id"] == "P1"
        assert envelope["wall_time_unix_ms"] == 1700000000000
        assert envelope["monotonic_ns"] == 42
        assert envelope["payload"] == {"status": "running"}

    async def test_payload_mutation_after_emit_cannot_change_written_line(self, tmp_path):
        # 队列所有权：emit 返回后调用方修改对象不能改写已入队记录。
        sink = JsonlAuditSink(tmp_path, "run-1")
        payload = {"status": "running"}
        assert sink.emit(make_record(AuditKind.LIFECYCLE_CHANGED, payload)).queued
        payload["status"] = "tampered"
        await sink.aclose(timeout_seconds=5.0)

        line = (tmp_path / "runs" / "run-1" / "lifecycle.jsonl").read_text(encoding="utf-8")
        assert "tampered" not in line
        assert json.loads(line)["payload"] == {"status": "running"}


class TestRoutingIsolation:
    async def test_four_participants_share_game_id_without_crosstalk(self, tmp_path):
        sink = JsonlAuditSink(tmp_path, "run-1")
        for pid in ("P1", "P2", "P3", "P4"):
            assert sink.emit(
                make_record(
                    AuditKind.AUTHORITATIVE_STATE,
                    {"authoritative_seq": 5},
                    participant_id=pid,
                    game_id="G-shared",
                    round_no=1,
                    trigger_seq=5,
                )
            ).queued
            assert sink.emit(
                make_record(
                    AuditKind.SUBMISSION_INTENT,
                    {"action_key": "peng:1w", "based_on_authoritative_seq": 5},
                    participant_id=pid,
                    game_id="G-shared",
                    round_no=1,
                    trigger_seq=5,
                    decision_id="d1",
                    attempt_no=1,
                )
            ).queued

        summary = await sink.aclose(timeout_seconds=5.0)
        assert summary.written == 8
        run_summary = json.loads(
            (tmp_path / "runs" / "run-1" / "summary.json").read_text(encoding="utf-8")
        )
        assert run_summary["participants"] == ["P1", "P2", "P3", "P4"]

        for pid in ("P1", "P2", "P3", "P4"):
            game_lines = (
                tmp_path / "runs" / "run-1" / "participants" / pid / "games" / "G-shared.jsonl"
            ).read_text(encoding="utf-8").splitlines()
            assert len(game_lines) == 1
            assert json.loads(game_lines[0])["context"]["participant_id"] == pid

            decision_lines = (
                tmp_path / "runs" / "run-1" / "participants" / pid / "decisions.jsonl"
            ).read_text(encoding="utf-8").splitlines()
            assert len(decision_lines) == 1
            assert json.loads(decision_lines[0])["context"]["participant_id"] == pid


class TestQueuePressure:
    async def test_low_dropped_high_evicts_low_then_high_rejected(self, tmp_path):
        gate = threading.Event()
        sink = JsonlAuditSink(tmp_path, "run-1", max_queue=4, before_batch_write=gate.wait)

        for index in range(4):
            assert sink.emit(_raw(index)).queued is True
        # 队列已满：第 5 条低优先级入队被拒，但不构成审计降级。
        fifth = sink.emit(_raw(4))
        assert fifth.queued is False
        assert fifth.audit_degraded is False
        assert fifth.reason == "queue_full_low_priority_dropped"

        # 4 条高优先级逐条淘汰最旧的低优先级记录后全部入队成功。
        for index in range(1, 5):
            receipt = sink.emit(_intent(index))
            assert receipt.queued is True
            assert receipt.audit_degraded is False

        # 低优先级清空后队列仍满：高优先级只能拒绝并立即标记降级。
        rejected = sink.emit(_intent(5))
        assert rejected.queued is False
        assert rejected.audit_degraded is True
        assert rejected.reason == "queue_full_high_priority_dropped"

        gate.set()  # 放行写线程前队列状态完全确定
        summary = await sink.aclose(timeout_seconds=5.0)
        assert summary.written == 4  # 只剩 4 条高优先级 intent 落盘
        assert summary.dropped_low_priority == 5  # 4 条被高优逐出 + 1 条入队被拒
        assert summary.missing_high_priority == 1
        assert summary.serialization_failures == 0
        assert summary.audit_degraded is True

        # 提交意图属于决策流：落盘在 decisions.jsonl 而不是场次文件。
        decisions_lines = (
            tmp_path / "runs" / "run-1" / "participants" / "P1" / "decisions.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        kinds = {json.loads(line)["kind"] for line in decisions_lines}
        assert kinds == {"submission_intent"}
        assert len(decisions_lines) == 4


class TestFailureInjection:
    async def test_emit_never_raises_on_serialization_or_schema_failures(self, tmp_path):
        sink = JsonlAuditSink(tmp_path, "run-1")

        # 验证器实际消费字段存在时类型必须正确：outcome 为非字符串拒绝入队；
        # 未知词表值（如 "maybe"）按最小校验原则放行，由验证器归并计数。
        type_violation = make_record(AuditKind.SUBMISSION_OUTCOME, {"outcome": 409})
        receipt = sink.emit(type_violation)
        assert receipt.queued is False and receipt.audit_degraded is True

        not_json = make_record(AuditKind.RUN_MANIFEST, {"handle": object()})
        receipt = sink.emit(not_json)
        assert receipt.queued is False and receipt.audit_degraded is True

        nan = make_record(AuditKind.RUN_MANIFEST, {"score": float("nan")})
        receipt = sink.emit(nan)
        assert receipt.queued is False and receipt.audit_degraded is True

        wrong_version = make_record(
            AuditKind.LIFECYCLE_CHANGED, {"status": "running"}, schema_version=99
        )
        receipt = sink.emit(wrong_version)
        assert receipt.queued is False and receipt.audit_degraded is True

        summary = await sink.aclose(timeout_seconds=5.0)
        assert summary.serialization_failures == 4
        # 序列化失败与高优先级缺失是两个独立计数：这些记录从未进入队列。
        assert summary.missing_high_priority == 0
        assert summary.audit_degraded is True

    async def test_unwritable_file_counts_missing_and_does_not_raise(self, tmp_path):
        manifest_path = tmp_path / "runs" / "run-1" / "manifest.json"
        manifest_path.parent.mkdir(parents=True)
        manifest_path.mkdir()  # 同名目录使该文件的每次打开都失败

        sink = JsonlAuditSink(tmp_path, "run-1")
        assert sink.emit(
            make_record(AuditKind.RUN_MANIFEST, {"mode": "test_room"})
        ).queued is True
        assert sink.emit(
            make_record(AuditKind.RUN_MANIFEST, {"mode": "test_room", "retry": True})
        ).queued is True
        assert sink.emit(
            make_record(AuditKind.LIFECYCLE_CHANGED, {"status": "running"})
        ).queued is True

        summary = await sink.aclose(timeout_seconds=5.0)
        # manifest 两条高优先级写失败计缺失；生命周期正常落盘。
        assert summary.written == 1
        assert summary.missing_high_priority == 2
        assert summary.audit_degraded is True
        assert (tmp_path / "runs" / "run-1" / "lifecycle.jsonl").exists()


class TestCloseSemantics:
    async def test_close_timeout_keeps_total_accounting_invariant(self, tmp_path):
        sink = JsonlAuditSink(tmp_path, "run-1")
        total = 1500
        for index in range(total):
            assert sink.emit(_intent(index)).queued is True

        summary = await sink.aclose(timeout_seconds=0.001)
        # 无论写线程排空到什么程度，已写与缺失之和必须对得上总账。
        assert summary.written + summary.missing_high_priority == total
        assert summary.audit_degraded == (summary.missing_high_priority > 0)

        # 重复关闭幂等：返回首次统计。
        again = await sink.aclose(timeout_seconds=0.0)
        assert again == summary

    async def test_close_writes_run_and_participant_summaries(self, tmp_path):
        sink = JsonlAuditSink(tmp_path, "run-1")
        for pid in ("P1", "P2"):
            sink.emit(
                make_record(
                    AuditKind.AUTHORITATIVE_STATE,
                    {"authoritative_seq": 1},
                    participant_id=pid,
                    game_id="G1",
                    round_no=1,
                    trigger_seq=1,
                )
            )
        summary = await sink.aclose(timeout_seconds=5.0)
        assert summary.audit_degraded is False

        run_summary = json.loads(
            (tmp_path / "runs" / "run-1" / "summary.json").read_text(encoding="utf-8")
        )
        assert run_summary["written"] == 2
        assert run_summary["participants"] == ["P1", "P2"]
        assert run_summary["audit_degraded"] is False
        for pid in ("P1", "P2"):
            participant_summary = json.loads(
                (tmp_path / "runs" / "run-1" / "participants" / pid / "summary.json")
                .read_text(encoding="utf-8")
            )
            assert participant_summary["written"] == 1

    async def test_emit_after_close_is_rejected_with_degradation(self, tmp_path):
        sink = JsonlAuditSink(tmp_path, "run-1")
        await sink.aclose(timeout_seconds=1.0)
        receipt = sink.emit(make_record(AuditKind.LIFECYCLE_CHANGED, {"status": "late"}))
        assert receipt.queued is False
        assert receipt.audit_degraded is True
        assert receipt.reason == "sink_closed"
class TestManifestSingleObject:
    async def test_repeated_manifest_records_overwrite_single_object(self, tmp_path):
        # manifest 是运行级单对象文件：后写覆盖，重复发射不产生多行损坏。
        from hangma_bot.adapters.recording import validate_run

        sink = JsonlAuditSink(tmp_path, "run-1")
        assert sink.emit(
            make_record(AuditKind.RUN_MANIFEST, {"mode": "test_room", "guide_version": 8})
        ).queued is True
        assert sink.emit(
            make_record(AuditKind.RUN_MANIFEST, {"mode": "test_room", "guide_version": 9})
        ).queued is True
        summary = await sink.aclose(timeout_seconds=5.0)
        assert summary.serialization_failures == 0

        manifest_path = tmp_path / "runs" / "run-1" / "manifest.json"
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert document["payload"] == {"mode": "test_room", "guide_version": 9}

        # 验证器按单个 JSON 文档解析 manifest：覆盖写后不再误报损坏。
        report = validate_run(tmp_path / "runs" / "run-1")
        assert report["coverage"]["manifest_present"] is True
        assert all(f["code"] != "corrupt_manifest" for f in report["findings"])


class TestClosedReceiptConsistency:
    async def test_closed_sink_receipt_matches_counter_semantics(self, tmp_path):
        # 高优先级关闭后到达 = 缺失 → 降级回执；低优先级按设计丢弃 → 不降级。
        sink = JsonlAuditSink(tmp_path, "run-1")
        await sink.aclose(timeout_seconds=1.0)

        high = sink.emit(make_record(AuditKind.LIFECYCLE_CHANGED, {"status": "late"}))
        assert high.queued is False
        assert high.audit_degraded is True
        assert high.reason == "sink_closed"

        low = sink.emit(
            make_record(AuditKind.RAW_PROTOCOL_STATE, {"raw": "late"}, game_id="G1")
        )
        assert low.queued is False
        assert low.audit_degraded is False
        assert low.reason == "sink_closed_low_priority"

