"""原始事件全量保留的落盘路径测试：raw/ 路由、gzip 轮转与非阻塞规模模拟。

验收锚点（任务 4/4）：
1. 原始事件按 kind/按场分文件（raw/ 子目录），与关键事实流隔离；
2. gzip 轮转只分段不丢弃，验证器透明解压扫描；
3. 百万级记录模拟下 emit 走非阻塞路径——写线程独立，emit 只做
   入队前快照，逐条延迟有界，全部记录最终落盘、零丢弃。
"""

import gzip
import json
import os
import threading
import time

from hangma_bot.adapters.recording import JsonlAuditSink, validate_run
from hangma_bot.adapters.recording.raw_events import build_state_response_payload
from hangma_bot.application.contracts import AuditKind

from recording._helpers import make_record


def _raw_state(index: int, game_id: str = "G1"):
    """一条带 request_no 簿记的 state 响应原文（约 600B，模拟真实快照体积）。"""

    snapshot = {
        "seq": 10 + index,
        "snapshot": {
            "phase": "draw",
            "seat": 0,
            "turn": 0,
            "responding_seats": [],
            "dealer": 0,
            "round_no": 1,
            "drawn_tile": "5w",
            "my_hand": ["1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "东", "东", "南", "白"],
            "wall_remaining": 40,
            "scores": [10, 4, -2, -12],
            "discards": [[], ["3b", "2w"], [], ["东"]],
            "melds": [[], [], [], []],
            "hand_counts": [10, 10, 13, 10],
            "last_discard": {"seat": 1, "tile": "2w", "seq": 10 + index},
            "god": {"baotou": False, "chain_count": 0, "catch_play": False},
        },
    }
    return make_record(
        AuditKind.RAW_PROTOCOL_STATE,
        build_state_response_payload(
            endpoint=f"GET /api/games/{game_id}/state",
            http_status=200,
            seq_requested=0,
            seq_observed=10 + index,
            request_no=index,
            raw=json.dumps(snapshot),
        ),
        game_id=game_id,
        round_no=1,
        trigger_seq=10 + index,
    )


async def test_raw_events_route_to_raw_directory(tmp_path):
    """raw 记录落在 participants/{pid}/raw/{game}.jsonl，不进关键事实流。"""

    sink = JsonlAuditSink(tmp_path, "run-raw-route")
    sink.emit(make_record(AuditKind.RUN_MANIFEST, {"mode": "test_room"}))
    sink.emit(make_record(AuditKind.LIFECYCLE_CHANGED, {"status": "running"}))
    for index in (1, 2, 3):
        assert sink.emit(_raw_state(index)).queued
    sink.emit(
        make_record(
            AuditKind.RAW_PROTOCOL_STATE,
            build_state_response_payload(
                endpoint="GET /api/games/{none}/state",
                http_status=200,
                seq_requested=0,
                seq_observed=None,
                request_no=1,
                raw='{"pending": true}',
            ),
            game_id=None,
        )
    )
    summary = await sink.aclose(timeout_seconds=5.0)
    assert summary.written == 6  # manifest + lifecycle + 3 场次 raw + 1 global raw
    assert summary.dropped_low_priority == 0

    run_dir = tmp_path / "runs" / "run-raw-route"
    raw_lines = (run_dir / "participants" / "P1" / "raw" / "G1.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    assert len(raw_lines) == 3
    envelope = json.loads(raw_lines[0])
    assert envelope["kind"] == "raw_protocol_state"
    assert envelope["payload"]["request_no"] == 1
    # 无场次回退 raw/global.jsonl。
    global_lines = (run_dir / "participants" / "P1" / "raw" / "global.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    assert len(global_lines) == 1
    # 关键事实流不混入原始事件。
    assert not (run_dir / "participants" / "P1" / "games" / "G1.jsonl").exists()

    report = validate_run(run_dir)
    assert report["counts_by_kind"]["raw_protocol_state"] == 4
    assert report["raw_events"]["by_source"] == {"state_response": 4}
    assert report["raw_events"]["raw_bytes_total"] > 0


async def test_raw_gzip_rotation_segments_without_loss(tmp_path):
    """gzip 轮转：段满只开新段不丢行；验证器透明解压读到全部记录。"""

    sink = JsonlAuditSink(tmp_path, "run-gz", raw_gzip=True, raw_rotate_bytes=3000)
    total = 60
    for index in range(1, total + 1):
        assert sink.emit(_raw_state(index)).queued
    summary = await sink.aclose(timeout_seconds=5.0)
    assert summary.written == total
    assert summary.dropped_low_priority == 0
    assert summary.audit_degraded is False

    run_dir = tmp_path / "runs" / "run-gz"
    raw_dir = run_dir / "participants" / "P1" / "raw"
    segments = sorted(raw_dir.glob("*.jsonl.gz"))
    assert len(segments) >= 2  # 3KB 段上限必然轮转出多个段
    lines = []
    for segment in segments:
        with gzip.open(segment, "rt", encoding="utf-8") as handle:
            lines.extend(handle.read().splitlines())
    assert len(lines) == total
    request_nos = {json.loads(line)["payload"]["request_no"] for line in lines}
    assert request_nos == set(range(1, total + 1))  # 轮转零丢失

    # 运行级汇总声明 gzip 模式；验证器透明解压扫描全部段。
    run_summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert run_summary["raw_retention"]["mode"] == "per_game_files_gzip"
    assert run_summary["raw_retention"]["gzip"] is True
    report = validate_run(run_dir)
    assert report["raw_events"]["retention_mode"] == "per_game_files_gzip"
    assert report["counts_by_kind"]["raw_protocol_state"] == total
    assert report["corrupt_lines"] == []


async def test_corrupt_gzip_segment_reported_not_crash(tmp_path):
    """损坏的 gzip 段：验证器报 violation 而不是崩溃。"""

    sink = JsonlAuditSink(tmp_path, "run-gz-bad", raw_gzip=True, raw_rotate_bytes=10 ** 9)
    sink.emit(_raw_state(1))
    await sink.aclose(timeout_seconds=5.0)
    run_dir = tmp_path / "runs" / "run-gz-bad"
    segments = list((run_dir / "participants" / "P1" / "raw").glob("*.jsonl.gz"))
    assert len(segments) == 1
    segments[0].write_bytes(b"not a gzip stream")
    report = validate_run(run_dir)
    codes = {f["code"] for f in report["findings"] if f["severity"] == "violation"}
    assert "unreadable_audit_file" in codes


async def test_truncated_gzip_tail_reported_not_crash(tmp_path):
    """F-10 回归：截断的 gzip 段（进程被杀、无 trailer）读取抛 EOFError
    （非 OSError），验证器必须报 unreadable_audit_file 而不是裸抛崩溃。"""

    import gzip as _gzip

    sink = JsonlAuditSink(tmp_path, "run-gz-trunc", raw_gzip=True, raw_rotate_bytes=10 ** 9)
    sink.emit(_raw_state(1))
    sink.emit(_raw_state(2))
    await sink.aclose(timeout_seconds=5.0)
    run_dir = tmp_path / "runs" / "run-gz-trunc"
    segments = list((run_dir / "participants" / "P1" / "raw").glob("*.jsonl.gz"))
    assert len(segments) == 1
    data = segments[0].read_bytes()
    # 截掉尾部 40%：gzip trailer 缺失，读取到截断点抛 EOFError。
    segments[0].write_bytes(data[: int(len(data) * 0.6)])
    report = validate_run(run_dir)
    codes = {f["code"] for f in report["findings"] if f["severity"] == "violation"}
    assert "unreadable_audit_file" in codes


async def test_raw_stream_is_nonblocking_at_scale(tmp_path):
    """规模模拟：大量原始事件不阻塞动作路径，计数诚实无静默丢失。

    默认 6 万条（约 40MB 原文）；环境变量 RECORDING_RAW_SCALE_ITEMS 可放大
    到百万级做真实压测。紧循环生产者远快于磁盘是人为压力：断言 emit
    单条延迟有界（写线程独立，磁盘从不进入动作路径），且审计恒等式
    written + dropped == 发射数成立（低优先级背压计数可见，绝不静默）。
    """

    scale = int(os.environ.get("RECORDING_RAW_SCALE_ITEMS", "60000"))
    sink = JsonlAuditSink(tmp_path, "run-scale")
    worst_emit_s = 0.0
    t0 = time.perf_counter()
    for index in range(1, scale + 1):
        t1 = time.perf_counter()
        receipt = sink.emit(_raw_state(index))
        worst_emit_s = max(worst_emit_s, time.perf_counter() - t1)
        # 原始事件低优先级：压力下要么入队、要么计数丢弃；绝不抛异常、
        # 绝不阻塞、绝不把丢弃伪装成审计降级。
        assert receipt.audit_degraded is False
    emit_elapsed = time.perf_counter() - t0
    summary = await sink.aclose(timeout_seconds=30.0)
    # 审计恒等式：任何记录都落在 written 或 dropped 桶里，无静默丢失。
    assert summary.written + summary.dropped_low_priority == scale
    assert summary.missing_high_priority == 0
    # emit 只做入队前快照：单条最坏延迟远小于任何动作窗口（1s/3s 预算）。
    assert worst_emit_s < 0.05
    assert emit_elapsed < 60.0


async def test_raw_retention_zero_drop_when_queue_provisioned(tmp_path):
    """体量不构成丢弃理由：队列按突发规模配置时全量保留、零丢弃。

    记录器不做任何抽样或体积裁剪——本测试证明 2 万条原始事件（约 12MB
    原文）在队列按规模配置后全部落盘：唯一可能的丢失路径是队列压力
    背压（默认 16384 条），由上一测试的计数恒等式兜底可见。
    """

    total = 20000
    sink = JsonlAuditSink(tmp_path, "run-provisioned", max_queue=total + 1024)
    for index in range(1, total + 1):
        assert sink.emit(_raw_state(index)).queued
    summary = await sink.aclose(timeout_seconds=30.0)
    assert summary.written == total
    assert summary.dropped_low_priority == 0
    assert summary.audit_degraded is False


async def test_raw_stream_does_not_block_emit_while_writer_stuck(tmp_path):
    """写线程被阻塞时 emit 依旧立即返回：非阻塞由架构保证而非运气。"""

    gate = threading.Event()
    sink = JsonlAuditSink(tmp_path, "run-stuck", max_queue=65536, before_batch_write=gate.wait)
    t0 = time.perf_counter()
    for index in range(1, 20001):
        assert sink.emit(_raw_state(index)).queued
    elapsed = time.perf_counter() - t0
    gate.set()  # 放行写线程
    summary = await sink.aclose(timeout_seconds=30.0)
    assert summary.written == 20000
    assert summary.dropped_low_priority == 0
    # 写线程全程阻塞在观察点：2 万条 emit（含每次 ~600B 的序列化与脱敏）
    # 仍在秒级内完成，证明写盘等待从不进入动作路径。
    assert elapsed < 20.0
