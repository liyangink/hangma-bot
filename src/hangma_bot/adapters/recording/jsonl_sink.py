"""JSONL 审计接收器：有界后台队列与单写线程，不阻塞动作路径。

设计模式与意图
==============

- **生产者-消费者模式**：``emit()`` 是同步生产者，后台守护写线程是唯一消费者；
  两者只通过一把 ``threading.Condition`` 和高/低两个有界 ``deque`` 交互。
- **固定优先级双队列**：优先级由 ``schema.is_high_priority`` 按 ``AuditKind`` 固定，
  调用方不能降级。队列满时高优先级记录先淘汰最旧的低优先级记录腾位；
  仍无空间才拒绝该高优先级记录，立即返回 ``audit_degraded=true`` 并计入缺失。
  这是刻意取舍：不为“100% 不丢”阻塞 1 秒动作窗口（模块说明 §优先级）。
- **队列所有权（入队即快照）**：``emit()`` 返回前完成结构校验、防御性脱敏和
  JSON 编码，队列中只有不可变字符串；调用方随后修改原对象不影响已入队记录。
- **单写线程串行化磁盘访问**：天然避免多协程并发写同一文件的交错；
  ``aclose()`` 停止接收、限时排空、统计残余、写汇总文件并关闭句柄。

失败语义（对应接口协议 §8 “磁盘或审计异常 → 不阻塞动作，标记审计降级”）
======================================================================

- ``emit()`` 永不向调用方抛异常；一切失败折叠为
  ``AuditReceipt(queued=False, audit_degraded=True, reason=...)``。
- 某个文件写盘失败后不再重试同一文件（避免磁盘满/慢时的错误风暴），
  该文件后续记录直接计数放弃：高优先级计入 ``missing_high_priority``，
  低优先级计入 ``dropped_low_priority``，两者同时计入 ``write_failures`` 明细。
- 关闭时限内未排空的队列残余按同样规则计入缺失/丢弃。
- 校验或 JSON 编码失败的记录从未进入队列，单独计入
  ``serialization_failures`` 并标记降级，不与丢失计数混同。

因此 ``written + dropped_low_priority + missing_high_priority + serialization_failures``
等于 ``emit()`` 收到的记录总数（线程正常退出时），验证器与运维都可用该恒等式对账。
"""

from __future__ import annotations

import asyncio
import dataclasses
import gzip
import json
import os
import threading
from collections import Counter, deque
from pathlib import Path
from typing import IO, Callable, NamedTuple

from hangma_bot.adapters.recording.chain_piao import normalize_decision_input_payload
from hangma_bot.adapters.recording.raw_events import is_new_shape_raw_payload
from hangma_bot.adapters.recording.redact import redact_json_line, redact_value
from hangma_bot.adapters.recording.schema import (
    AUDIT_SCHEMA_VERSION,
    RUN_MANIFEST_PATH,
    is_high_priority,
    relative_path_for,
    sanitize_component,
    validate_payload,
)
from hangma_bot.adapters.recording.summary import (
    build_participant_summary,
    build_run_summary,
    participant_ids_from_paths,
    paths_for_participant,
)
from hangma_bot.application.contracts import AuditKind, AuditReceipt, AuditRecord, AuditSummary

# 单个批次的写盘上限：限制锁外持有时间，让 close 排空时的进度可观察。
_BATCH_LIMIT = 512
# aclose 事件等待的执行器线程内部上限；写线程总会退出，这里只防异常悬挂。
_DRAINED_WAIT_CAP_SECONDS = 60.0


class _PendingRecord(NamedTuple):
    """入队后的不可变写盘任务；``line`` 已脱敏并编码完毕。"""

    path: str  # 相对 ``runs/{run_id}/`` 的 POSIX 风格相对路径
    line: str  # 单行 JSON，不含换行符
    kind: str
    high: bool
    participant_id: str


class JsonlAuditSink:
    """``AuditSink`` 的第一阶段真实实现：按身份隔离目录的 JSONL 记录器。

    文件布局（``audit_root`` 是 ``runs/`` 目录的父目录）：

    ``{audit_root}/runs/{run_id}/`` 下按 ``schema.relative_path_for`` 路由；
    每个参赛身份独立子目录，四身份写同一 ``game_id`` 时互不冲突。
    """

    def __init__(
        self,
        audit_root: str | os.PathLike[str],
        run_id: str,
        *,
        max_queue: int = 16384,
        before_batch_write: Callable[[], None] | None = None,
        raw_gzip: bool = False,
        raw_rotate_bytes: int = 32 * 1024 * 1024,
    ) -> None:
        """``before_batch_write`` 是写线程在每次取出批次前调用的观察点。

        默认为 None（生产行为不受影响）；故障注入测试用它确定性阻塞写线程，
        从而复现队列满、淘汰与拒绝路径。观察点内部不允许抛异常。

        ``raw_gzip`` 开启后，``RAW_PROTOCOL_STATE`` 原始事件改按 gzip 压缩
        分段落盘，每段上限 ``raw_rotate_bytes`` 字节（轮转只是分段，绝不丢弃）。
        为什么默认关闭：普通盘位无需压缩，保持验证器与运维工具可读；
        官方快照原文约 1KB/条、每场万级记录，长期运行建议开启（体量测算见
        doc/implementation/notes/audit-raw-retention.md）。
        """

        if max_queue <= 0:
            raise ValueError("max_queue 必须为正数")
        if raw_gzip and raw_rotate_bytes <= 0:
            raise ValueError("raw_rotate_bytes 必须为正数")
        self._raw_gzip = raw_gzip
        self._raw_rotate_bytes = raw_rotate_bytes
        self._before_batch_write = before_batch_write
        self._run_id = run_id
        self._run_dir = Path(audit_root) / "runs" / sanitize_component(run_id)
        self._max_queue = max_queue

        self._cond = threading.Condition()
        self._high_queue: deque[_PendingRecord] = deque()
        self._low_queue: deque[_PendingRecord] = deque()

        # 全部计数器由 ``self._cond`` 的锁保护；写线程与 emit/aclose 共用。
        self._written = 0
        self._written_by_kind: Counter[str] = Counter()
        self._written_by_path: Counter[str] = Counter()
        self._written_by_participant_kind: dict[str, Counter[str]] = {}
        self._dropped_low = 0
        self._missing_high = 0
        self._serialization_failures = 0
        self._write_failures = 0
        self._raw_attempts = 0  # 收到的原始事件尝试总数（含被淘汰/拒绝的）
        # 是否见到过新形态原始事件：见 _emit_inner 的 auto-evidence 说明。
        self._raw_new_shape_seen = False
        self._degraded = False
        self._participants: set[str] = set()
        self._failed_paths: set[str] = set()
        self._handles: dict[str, IO[str]] = {}
        # gzip 轮转状态：base 相对路径 → [当前段号, gzip 句柄, 本段已写字节]。
        # 只被唯一写线程访问，无需加锁。
        self._raw_gz: dict[str, list[object]] = {}
        self._write_error_notes: list[str] = []

        self._stopping = False
        self._closed = False
        self._summary_cache: AuditSummary | None = None
        self._drained = threading.Event()
        self._writer = threading.Thread(
            target=self._writer_loop,
            name=f"audit-writer-{sanitize_component(run_id)}",
            daemon=True,  # 审计线程绝不阻止进程退出；动作路径关闭流程负责显式排空
        )
        self._writer.start()

    @property
    def run_dir(self) -> Path:
        """本次运行的审计根目录（含 ``runs/{run_id}``）。"""

        return self._run_dir

    # ------------------------------------------------------------------ emit

    def emit(self, record: AuditRecord) -> AuditReceipt:
        """同步快照后立即入队；任何失败都不抛异常（``AuditSink`` 契约）。"""

        try:
            return self._emit_inner(record)
        except Exception as exc:  # noqa: BLE001 - 契约要求吞掉一切异常
            with self._cond:
                self._serialization_failures += 1
                self._degraded = True
            return AuditReceipt(
                queued=False,
                audit_degraded=True,
                reason=f"emit_error:{type(exc).__name__}",
            )

    def _emit_inner(self, record: AuditRecord) -> AuditReceipt:
        with self._cond:
            if self._closed:
                # 关闭后到达的高优先级记录视为缺失；低优先级按设计丢弃、不构成降级，
                # 回执与计数语义保持一致。
                high = is_high_priority(record.kind)
                degraded = self._reject_locked(high=high)
                reason = "sink_closed" if degraded else "sink_closed_low_priority"
                return AuditReceipt(queued=False, audit_degraded=degraded, reason=reason)

        kind = record.kind
        if not isinstance(kind, AuditKind):
            raise TypeError("record.kind 必须是 AuditKind")
        if kind is AuditKind.RAW_PROTOCOL_STATE:
            with self._cond:
                self._raw_attempts += 1
                if is_new_shape_raw_payload(record.payload):
                    # 自动门控（auto-evidence）：只有真正收到过新形态原始事件
                    # 才在汇总中声明 raw_retention，验证器才启用严格完整性
                    # 检查。旧目录与"适配器尚未接线"的运行不声明 → legacy
                    # 检查整体跳过，验证结论与升级前一致、不产生误报。
                    self._raw_new_shape_seen = True
        if record.schema_version != AUDIT_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version {record.schema_version!r} 与当前版本 {AUDIT_SCHEMA_VERSION} 不符"
            )
        errors = validate_payload(kind, record.payload)
        if errors:
            raise ValueError("payload 校验失败: " + "; ".join(errors))
        # 3.6d 记录补全：决策输入落盘前把「链内飘出白板数」归一到**可归因**推导值
        # （官方 god 不提供 chain.piao，只能由本人动作史推导；不可归因记 unknown）。
        # 只改这一种记录的落盘内容，不影响任何决策输入本身；补全失败原样落盘。
        payload = (
            normalize_decision_input_payload(record.payload)
            if kind is AuditKind.DECISION_INPUT
            else record.payload
        )

        participant_id = record.context.participant_id
        path = relative_path_for(kind, participant_id, record.context.game_id)
        # 入队即取得内容所有权：结构脱敏 + 序列化行兜底扫描 + JSON 编码都在本线程完成。
        envelope = {
            "schema_version": record.schema_version,
            "kind": kind.value,
            "context": dataclasses.asdict(record.context),
            "wall_time_unix_ms": record.wall_time_unix_ms,
            "monotonic_ns": record.monotonic_ns,
            "payload": redact_value(dict(payload)),
        }
        line = redact_json_line(json.dumps(envelope, ensure_ascii=False, allow_nan=False))
        pending = _PendingRecord(
            path=path,
            line=line,
            kind=kind.value,
            high=is_high_priority(kind),
            participant_id=participant_id,
        )

        with self._cond:
            if self._closed:
                degraded = self._reject_locked(high=pending.high)
                reason = "sink_closed" if degraded else "sink_closed_low_priority"
                return AuditReceipt(queued=False, audit_degraded=degraded, reason=reason)
            if pending.high:
                backlog = len(self._high_queue) + len(self._low_queue)
                if backlog >= self._max_queue and self._low_queue:
                    # 淘汰最旧的低优先级记录腾位：冗余原始快照让位于关键事实。
                    self._low_queue.popleft()
                    self._dropped_low += 1
                if len(self._high_queue) + len(self._low_queue) >= self._max_queue:
                    self._missing_high += 1
                    self._degraded = True
                    return AuditReceipt(
                        queued=False,
                        audit_degraded=True,
                        reason="queue_full_high_priority_dropped",
                    )
                self._high_queue.append(pending)
            else:
                if len(self._high_queue) + len(self._low_queue) >= self._max_queue:
                    self._dropped_low += 1
                    return AuditReceipt(
                        queued=False,
                        audit_degraded=False,
                        reason="queue_full_low_priority_dropped",
                    )
                self._low_queue.append(pending)
            if participant_id:
                self._participants.add(participant_id)
            self._cond.notify()
        return AuditReceipt(queued=True, audit_degraded=False, reason=None)

    def _reject_locked(self, *, high: bool) -> bool:
        """关闭后到达记录的统一计数；返回该记录是否构成审计降级。"""

        if high:
            self._missing_high += 1
            self._degraded = True
            return True
        self._dropped_low += 1
        return False

    # ---------------------------------------------------------------- writer

    def _writer_loop(self) -> None:
        """唯一写线程：高优先级先写，批次间让出锁；退出时通知排空事件。"""

        try:
            while True:
                with self._cond:
                    while not self._high_queue and not self._low_queue and not self._stopping:
                        self._cond.wait()
                    if self._stopping and not self._high_queue and not self._low_queue:
                        break
                if self._before_batch_write is not None:
                    # 故障注入观察点：阻塞必须发生在取出批次之前，队列状态才可复现。
                    self._before_batch_write()
                with self._cond:
                    batch: list[_PendingRecord] = []
                    while self._high_queue and len(batch) < _BATCH_LIMIT:
                        batch.append(self._high_queue.popleft())
                    while self._low_queue and len(batch) < _BATCH_LIMIT:
                        batch.append(self._low_queue.popleft())
                self._write_batch(batch)
        finally:
            self._drained.set()

    def _write_batch(self, batch: list[_PendingRecord]) -> None:
        for pending in batch:
            if pending.path in self._failed_paths:
                self._abandon_write(pending)
                continue
            try:
                if pending.path == RUN_MANIFEST_PATH:
                    # manifest 是运行级单对象文件：后写覆盖（last-wins），
                    # 保持"一个 JSON 文档"语义，重复发射不会产生多行损坏。
                    self._overwrite_manifest(pending.line)
                elif self._raw_gzip and pending.kind == AuditKind.RAW_PROTOCOL_STATE.value:
                    # 原始事件全量保留：压缩分段落盘，段满只轮转不丢弃。
                    self._write_raw_gzip(pending)
                else:
                    handle = self._handle_for(pending.path)
                    handle.write(pending.line)
                    handle.write("\n")
                    handle.flush()  # 每条落盘即 flush：进程被杀时审计尽量不缺行
            except OSError as exc:
                with self._cond:
                    self._failed_paths.add(pending.path)
                    self._write_error_notes.append(f"{pending.path}: {exc}")
                self._abandon_write(pending)
                continue
            with self._cond:
                self._written += 1
                self._written_by_kind[pending.kind] += 1
                self._written_by_path[pending.path] += 1
                if pending.participant_id:
                    self._written_by_participant_kind.setdefault(
                        pending.participant_id, Counter()
                    )[pending.kind] += 1

    def _abandon_write(self, pending: _PendingRecord) -> None:
        """写盘失败的计数：高优先级计缺失，低优先级计丢弃。"""

        with self._cond:
            self._write_failures += 1
            if pending.high:
                self._missing_high += 1
                self._degraded = True
            else:
                self._dropped_low += 1

    def _overwrite_manifest(self, line: str) -> None:
        """以覆盖模式重写 manifest.json；调用方需捕获 OSError。"""

        absolute = self._run_dir / RUN_MANIFEST_PATH
        os.makedirs(absolute.parent, exist_ok=True)
        with absolute.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(line)
            handle.write("\n")
            handle.flush()

    def _handle_for(self, path: str) -> IO[str]:
        """惰性打开追加句柄；目录按需创建。调用方需捕获 OSError。"""

        handle = self._handles.get(path)
        if handle is not None and not handle.closed:
            return handle
        absolute = self._run_dir / Path(*path.split("/"))
        os.makedirs(absolute.parent, exist_ok=True)
        handle = absolute.open("a", encoding="utf-8", newline="\n")
        self._handles[path] = handle
        return handle

    # ------------------------------------------------------ raw gzip rotation

    @staticmethod
    def _raw_gz_segment_path(base: str, segment_no: int) -> str:
        """把 raw 基础路径映射到第 N 段的压缩文件名。

        约定：基础路径形如 participants/P1/raw/G1.jsonl，第 N 段为
        participants/P1/raw/G1.NNNNN.jsonl.gz（五位数补零保证字典序）。
        验证器按 .jsonl.gz 后缀透明解压扫描，段文件名不需再登记。
        """

        stem = base[: -len(".jsonl")]
        return f"{stem}.{segment_no:05d}.jsonl.gz"

    def _write_raw_gzip(self, pending: _PendingRecord) -> None:
        """把一条原始事件写入 gzip 段；超过段上限先关旧段再开新段。

        轮转是分段而非丢弃：所有段都追加保留，aclose 关闭最后一个段
        写出 gzip 尾部。段号与字节计数只被唯一写线程访问（见 __init__）。
        """

        entry = self._raw_gz.get(pending.path)
        if entry is None or entry[1].closed:
            segment_no = 1
            entry = [segment_no, self._open_raw_gz_segment(pending.path, segment_no), 0]
            self._raw_gz[pending.path] = entry
        line_bytes = (pending.line + "\n").encode("utf-8")
        segment_no, handle, written = entry
        if written > 0 and written + len(line_bytes) > self._raw_rotate_bytes:
            handle.close()
            segment_no += 1
            handle = self._open_raw_gz_segment(pending.path, segment_no)
            written = 0
            entry[0], entry[1], entry[2] = segment_no, handle, written
        handle.write(pending.line)
        handle.write("\n")
        handle.flush()
        entry[2] = written + len(line_bytes)

    def _open_raw_gz_segment(self, base: str, segment_no: int):
        """打开一个 gzip 文本追加段；目录按需创建。调用方需捕获 OSError。"""

        relative = self._raw_gz_segment_path(base, segment_no)
        absolute = self._run_dir / Path(*relative.split("/"))
        os.makedirs(absolute.parent, exist_ok=True)
        return gzip.open(absolute, "at", encoding="utf-8", newline="\n")

    # ---------------------------------------------------------------- aclose

    async def aclose(self, timeout_seconds: float) -> AuditSummary:
        """限时排空队列，返回诚实统计；重复调用返回首次结果。"""

        if timeout_seconds < 0:
            raise ValueError("timeout_seconds 不能为负数")
        with self._cond:
            if self._closed and self._summary_cache is not None:
                return self._summary_cache
            self._stopping = True
            self._cond.notify_all()

        loop = asyncio.get_running_loop()
        try:
            await asyncio.wait_for(
                asyncio.to_thread(self._drained.wait, _DRAINED_WAIT_CAP_SECONDS),
                timeout=timeout_seconds,
            )
        except (asyncio.TimeoutError, TimeoutError):
            pass  # 超时属于预期路径：残余队列按缺失/丢弃统计

        grace_seconds = max(1.0, min(5.0, timeout_seconds))
        self._writer.join(timeout=grace_seconds)
        writer_alive = self._writer.is_alive()

        with self._cond:
            # 排空超时的残余队列：高优先级计缺失，低优先级计丢弃。
            self._missing_high += len(self._high_queue)
            self._dropped_low += len(self._low_queue)
            self._high_queue.clear()
            self._low_queue.clear()
            if self._missing_high or self._serialization_failures:
                self._degraded = True
            self._closed = True
            state = self._snapshot_state_locked()

        summary_file_failed = False
        if writer_alive:
            # 写线程卡死（如磁盘悬挂）：不能安全写汇总，诚实标记降级。
            summary_file_failed = True
            state["detail"]["writer_stuck"] = True
        else:
            summary_file_failed = not self._write_summary_files(state)
            self._close_handles()
        if summary_file_failed:
            self._degraded = True

        summary = AuditSummary(
            written=state["written"],
            dropped_low_priority=state["dropped_low_priority"],
            missing_high_priority=state["missing_high_priority"],
            serialization_failures=state["serialization_failures"],
            audit_degraded=self._degraded,
        )
        self._summary_cache = summary
        return summary

    def _snapshot_state_locked(self) -> dict[str, object]:
        """在锁内取计数快照，交给 summary 模块组装汇总内容。"""

        detail: dict[str, object] = {}
        if self._write_error_notes:
            detail["write_errors"] = list(self._write_error_notes)
        # 原始事件保留模式声明：验证器据此启用严格完整性检查
        # （缺口/流缺失/动作响应缺失）。声明条件 = auto-evidence：
        # 收到过新形态原始事件（适配器已接线）或显式开启 raw_gzip。
        # 旧目录与未接线运行没有该键，检查整体跳过，保证向后兼容的
        # 验证结论不变（audit-raw-retention 设计）。
        if self._raw_new_shape_seen or self._raw_gzip:
            raw_retention: dict[str, object] = {
                "mode": "per_game_files_gzip" if self._raw_gzip else "per_game_files",
                "gzip": self._raw_gzip,
                "emitted_attempts": self._raw_attempts,
                "dropped": self._dropped_low,
            }
            if self._raw_gzip:
                raw_retention["rotate_bytes"] = self._raw_rotate_bytes
        else:
            raw_retention = None
        state: dict[str, object] = {
            "run_id": self._run_id,
            "written": self._written,
            "written_by_kind": dict(self._written_by_kind),
            "written_by_path": dict(self._written_by_path),
            "dropped_low_priority": self._dropped_low,
            "missing_high_priority": self._missing_high,
            "serialization_failures": self._serialization_failures,
            "write_failures": self._write_failures,
            "audit_degraded": self._degraded,
            "participants": sorted(self._participants),
            "written_by_participant_kind": {
                pid: dict(counter) for pid, counter in sorted(self._written_by_participant_kind.items())
            },
            "detail": detail,
        }
        if raw_retention is not None:
            state["raw_retention"] = raw_retention
        return state

    def _write_summary_files(self, state: dict[str, object]) -> bool:
        """尽力写入运行级与身份级 ``summary.json``；失败返回 False 由上层降级。"""

        try:
            documents: list[tuple[Path, dict[str, object]]] = [
                (
                    self._run_dir / "summary.json",
                    build_run_summary(
                        run_id=state["run_id"],
                        written=state["written"],
                        written_by_kind=state["written_by_kind"],
                        written_by_path=state["written_by_path"],
                        dropped_low_priority=state["dropped_low_priority"],
                        missing_high_priority=state["missing_high_priority"],
                        serialization_failures=state["serialization_failures"],
                        write_failures=state["write_failures"],
                        audit_degraded=state["audit_degraded"],
                        participants=state["participants"],
                        raw_retention=state.get("raw_retention"),
                        extra_detail=state["detail"],
                    ),
                )
            ]
            by_participant_kind = state["written_by_participant_kind"]
            written_by_path: dict[str, int] = state["written_by_path"]
            global_losses = {
                "dropped_low_priority": state["dropped_low_priority"],
                "missing_high_priority": state["missing_high_priority"],
                "serialization_failures": state["serialization_failures"],
                "write_failures": state["write_failures"],
                "audit_degraded": state["audit_degraded"],
            }
            for pid in participant_ids_from_paths(written_by_path.keys()):
                documents.append(
                    (
                        self._run_dir / "participants" / pid / "summary.json",
                        build_participant_summary(
                            run_id=state["run_id"],
                            participant_id=pid,
                            written=sum(by_participant_kind.get(pid, {}).values()),
                            written_by_kind=by_participant_kind.get(pid, {}),
                            written_by_path={
                                rel: written_by_path[rel]
                                for rel in paths_for_participant(written_by_path.keys(), pid)
                            },
                            **global_losses,
                        ),
                    )
                )
            for path, document in documents:
                os.makedirs(path.parent, exist_ok=True)
                path.write_text(
                    json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            return True
        except OSError:
            return False

    def _close_handles(self) -> None:
        """关闭全部文件句柄；flush 已在写入时完成，这里只释放资源。"""

        for handle in self._handles.values():
            try:
                handle.close()
            except OSError:
                pass
        self._handles.clear()
        # gzip 段关闭写出 gzip 尾部，保证验证器/运维工具可独立解压。
        for entry in self._raw_gz.values():
            handle = entry[1]
            if not handle.closed:
                try:
                    handle.close()
                except OSError:
                    pass
        self._raw_gz.clear()
