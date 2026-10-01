"""离线实际评分输入录制：有限规范JSON、整图去重、压缩费用及终态验签。

本 Module 不重建规则、筛选节点或添加信息。调用者只传同一实际typed view
的 candidate_view() 结果；来源、母根、单局、换座留在逐调用决策收据中。
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import time
from dataclasses import asdict, dataclass
from typing import Any, BinaryIO, Mapping

CAPTURE_RECORD_SCHEMA = "vip-scoring-input-view/1"


@dataclass(frozen=True)
class ScoringInputCaptureLimits:
    """整个开发批共用上限；字节是UTF-8规范DTO，不含行包装或gzip字节。"""

    max_view_json_bytes: int  # 每个完整公开DTO的原始字节上限，不截断后冒充完整图
    max_total_json_bytes: int  # 本批成功保存的去重DTO原始字节累计上限
    max_unique_views: int  # 本批成功保存的不同完整图SHA数量上限

    def __post_init__(self):
        for key, value in asdict(self).items():
            if type(value) is not int or value <= 0:
                raise ValueError(key + "须为正整数")
        if self.max_view_json_bytes > self.max_total_json_bytes:
            raise ValueError("单图上限不能超过累计去重图上限")

    @classmethod
    def from_json(cls, value):
        """只接受完整三字段配置；不为旧批次默填新预算。"""
        if not isinstance(value, dict) or set(value) != {
            "max_view_json_bytes", "max_total_json_bytes", "max_unique_views"}:
            raise ValueError("评分输入捕获预算须显式完整声明三个字段")
        return cls(**value)


@dataclass(frozen=True)
class ScoringInputCaptureReceipt:
    """一次store小收据；成功是流已flush，终态完整性仍须finish验证。"""

    store_call_no: int  # 本批store调用序号，从1开始；重复图仍有独立调用
    status: str  # stored/deduplicated/rejected/failed；失败不转换为成功缓存
    view_sha256: str | None  # 完整有限DTO的SHA；编码未完成时为None
    json_bytes: int | None  # 完整规范DTO字节；编码未完成时为None
    saved_before_score: bool  # True才允许真实评分；不表示压缩流已终态关闭
    terminal_verification_pending: bool
    error: str | None  # 非有限、预算或I/O原因；不吞失败
    encode_monotonic_seconds: float  # 单调编码持续秒
    store_monotonic_seconds: float  # 单调去重/写入持续秒，不含编码
    gzip_output_bytes_delta: int  # 本调用确认由底层stream接收的压缩字节


class _CountedWriter:
    """隐藏压缩写入计量；短写视为失败，不假定整行已保存。"""

    def __init__(self, stream):
        self.stream, self.write_attempts, self.bytes = stream, 0, 0
        self.uncertain_write_results = 0

    def write(self, raw):
        self.write_attempts += 1
        try:
            count = self.stream.write(raw)
        except BaseException:
            self.uncertain_write_results += 1
            raise
        if type(count) is not int or not 0 <= count <= len(raw):
            self.uncertain_write_results += 1
            raise OSError("二进制stream没有返回精确写入字节数")
        self.bytes += count
        if count != len(raw):
            raise OSError("压缩输入图发生短写")
        return count

    def flush(self):
        self.stream.flush()


def _finite_json(value):
    """只允许原始JSON容器和值；对象键保持字符串，不混入隐藏对象。"""
    if value is None or type(value) in (bool, int, str):
        return
    if type(value) is float and math.isfinite(value):
        return
    if isinstance(value, dict) and all(type(key) is str for key in value):
        for item in value.values():
            _finite_json(item)
        return
    if type(value) in (list, tuple):
        for item in value:
            _finite_json(item)
        return
    raise ValueError("DTO含非有限数或非原始JSON值/键")


def _encode(value, ceiling):
    """按块只编码一次，超过单图上限即拒绝；不截断图作成功记录。"""
    _finite_json(value)
    encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    chunks, count = [], 0
    for chunk in encoder.iterencode(value):
        raw = chunk.encode("utf-8")
        count += len(raw)
        if count > ceiling:
            raise ValueError("max_view_json_bytes额度耗尽")
        chunks.append(raw)
    return b"".join(chunks)


class ScoringInputCapture:
    """小Interface隐藏编码、SHA去重、gzip写入和闭流验签。

    stream须为本批独占的空可读写/可定位二进制流，调用者拥有并最终关闭它。
    store失败返回小收据，调用者必须禁止真实score；I/O失败后不再写新图。
    finish幂等，关闭gzip后流式读回全部唯一记录，核验SHA/字节/分母。
    costs为累计实际费用；任何早先失败使terminal_valid永久为False。
    """

    def __init__(self, stream: BinaryIO, *, limits: ScoringInputCaptureLimits):
        if stream.tell() != 0 or stream.seek(0, 2) != 0:
            raise ValueError("捕获stream须是空流且位于起点")
        stream.seek(0)
        self.stream, self.limits = stream, limits
        self._writer, self._gzip = _CountedWriter(stream), None
        self._seen: dict[str, int] = {}
        self._broken = False
        self._terminal: dict[str, Any] | None = None
        self._last_store_failure: dict[str, Any] | None = None
        self._cost = {"store_calls": 0, "encode_attempts": 0, "encoded_complete_json_bytes": 0,
            "deduplicated_calls": 0, "unique_views_saved": 0, "unique_json_bytes_saved": 0,
            "raw_record_bytes_saved": 0, "raw_record_bytes_attempted": 0,
            "failed_store_calls": 0, "encode_monotonic_seconds": 0.0,
            "store_monotonic_seconds": 0.0, "gzip_attempts": 0, "gzip_monotonic_seconds": 0.0,
            "verification_encode_attempts": 0, "verification_encoded_json_bytes": 0,
            "verification_encode_monotonic_seconds": 0.0}

    @property
    def costs(self):
        """返回累计快照，时间均为单调持续秒；终态前不授完整性。"""
        return {**self._cost, "gzip_write_attempts": self._writer.write_attempts,
            "gzip_output_bytes": self._writer.bytes,
            "gzip_output_bytes_scope": "confirmed_returned_write_bytes",
            "gzip_write_result_uncertain_attempts": self._writer.uncertain_write_results,
            "last_store_failure": self._last_store_failure,
            "terminal": self._terminal or {"closed": False, "verified": False, "terminal_valid": False}}

    def store(self, dto: Mapping[str, Any]) -> ScoringInputCaptureReceipt:
        """保存实际公开DTO，不补字段、不筛图；失败小收据不抛成成功缓存。"""
        self._cost["store_calls"] += 1
        number, before = self._cost["store_calls"], self._writer.bytes
        sha, size, error, status, saved = None, None, None, "failed", False
        encode_seconds, store_seconds = 0.0, 0.0
        try:
            if self._terminal is not None or self._broken:
                raise OSError("捕获流已关闭或已有I/O失败")
            started = time.monotonic()
            self._cost["encode_attempts"] += 1
            try:
                raw = _encode(dto, self.limits.max_view_json_bytes)
                size, sha = len(raw), hashlib.sha256(raw).hexdigest()
                self._cost["encoded_complete_json_bytes"] += size
            finally:
                encode_seconds = time.monotonic() - started
            started = time.monotonic()
            try:
                if sha in self._seen:
                    if size != self._seen[sha]:
                        raise ValueError("同SHA的DTO字节长度不一致")
                    self._cost["deduplicated_calls"] += 1
                    status, saved = "deduplicated", True
                else:
                    if len(self._seen) >= self.limits.max_unique_views:
                        raise ValueError("max_unique_views额度耗尽")
                    if self._cost["unique_json_bytes_saved"] + size > self.limits.max_total_json_bytes:
                        raise ValueError("max_total_json_bytes额度耗尽")
                    prefix = json.dumps({"schema": CAPTURE_RECORD_SCHEMA, "view_sha256": sha,
                        "json_bytes": size}, sort_keys=True, separators=(",", ":")).encode()
                    record = prefix[:-1] + b',"view":' + raw + b"}\n"
                    self._cost["raw_record_bytes_attempted"] += len(record)
                    tick = time.monotonic()
                    self._cost["gzip_attempts"] += 1
                    try:
                        if self._gzip is None:
                            self._gzip = gzip.GzipFile(filename="", mode="wb", fileobj=self._writer, mtime=0)
                        self._gzip.write(record)
                        self._gzip.flush()
                        self.stream.flush()
                    except BaseException:
                        self._broken = True
                        raise
                    finally:
                        self._cost["gzip_monotonic_seconds"] += time.monotonic() - tick
                    self._seen[sha] = size
                    self._cost["unique_views_saved"] += 1
                    self._cost["unique_json_bytes_saved"] += size
                    self._cost["raw_record_bytes_saved"] += len(record)
                    status, saved = "stored", True
            finally:
                store_seconds = time.monotonic() - started
        except BaseException as exc:
            status = "rejected" if isinstance(exc, ValueError) else "failed"
            error = type(exc).__name__ + ": " + str(exc)
            self._cost["failed_store_calls"] += 1
            if not isinstance(exc, Exception):
                self._broken = True
                raise  # 只计费与留失败；KeyboardInterrupt/SystemExit原样传播
        finally:
            self._cost["encode_monotonic_seconds"] += encode_seconds
            self._cost["store_monotonic_seconds"] += store_seconds
            receipt = ScoringInputCaptureReceipt(number, status, sha, size, saved,
                saved and self._terminal is None, error, encode_seconds, store_seconds, self._writer.bytes - before)
            if not saved:
                self._last_store_failure = asdict(receipt)
        return receipt

    def finish(self):
        """正常终态保留stream所有权；通用中断留invalid、尽力闭流后原样抛出。"""
        if self._terminal is not None:
            return self.costs
        try:
            return self._finish()
        except BaseException as primary:
            self._terminal = {"closed": False, "verified": False, "terminal_valid": False,
                "interrupted": True, "compressed_sha256": None, "observed_compressed_bytes": None,
                "errors": [type(primary).__name__ + ": " + str(primary)], "verified_unique_views": 0,
                "store_calls_reconciled": self._cost["store_calls"] == self._cost["unique_views_saved"]
                    + self._cost["deduplicated_calls"] + self._cost["failed_store_calls"]}
            for label, close in (("gzip", None if self._gzip is None else self._gzip.close),
                                 ("binary_stream", self.stream.close)):
                if close is None:
                    continue
                try:
                    close()
                except BaseException as secondary:
                    note = label + "中断清理再次失败:" + type(secondary).__name__ + ": " + str(secondary)
                    self._terminal["errors"].append(note)
                    primary.add_note(note)
            raise

    def _finish(self):
        """终态实现；正常I/O失败返回无效状态，通用中断由公开finish收口。"""
        if self._terminal is not None:
            return self.costs
        errors, closed, verified, records = [], False, False, 0
        tick = time.monotonic()
        try:
            self._cost["gzip_attempts"] += 1
            if self._gzip is None and not self._broken:
                self._gzip = gzip.GzipFile(filename="", mode="wb", fileobj=self._writer, mtime=0)
            if self._gzip is not None:
                self._gzip.close()
            self.stream.flush()
            closed = not self._broken
        except Exception as exc:
            errors.append(type(exc).__name__ + ": " + str(exc))
        finally:
            self._cost["gzip_monotonic_seconds"] += time.monotonic() - tick
        verification_started = time.monotonic()
        try:
            self.stream.seek(0)
            seen = set()
            with gzip.GzipFile(mode="rb", fileobj=self.stream) as reader:
                while line := reader.readline(self.limits.max_view_json_bytes + 513):
                    # 行包装有少量额外字节；不允许篡改流制造无界单行。
                    if len(line) > self.limits.max_view_json_bytes + 512:
                        raise ValueError("终态记录行超额")
                    record = json.loads(line, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("非有限记录")))
                    if set(record) != {"schema", "view_sha256", "json_bytes", "view"} or record["schema"] != CAPTURE_RECORD_SCHEMA:
                        raise ValueError("终态图记录schema或字段集合不符")
                    if (type(record["json_bytes"]) is not int or record["json_bytes"] <= 0
                            or type(record["view_sha256"]) is not str or len(record["view_sha256"]) != 64):
                        raise ValueError("终态图记录字节数或SHA类型不符")
                    encode_started = time.monotonic()
                    self._cost["verification_encode_attempts"] += 1
                    try:
                        raw = _encode(record["view"], self.limits.max_view_json_bytes)
                        self._cost["verification_encoded_json_bytes"] += len(raw)
                    finally:
                        self._cost["verification_encode_monotonic_seconds"] += time.monotonic() - encode_started
                    sha = hashlib.sha256(raw).hexdigest()
                    if (sha != record["view_sha256"] or len(raw) != record["json_bytes"]
                            or self._seen.get(sha) != len(raw) or sha in seen):
                        raise ValueError("终态图记录SHA、长度或唯一性不符")
                    seen.add(sha)
                    records += 1
            if seen != set(self._seen):
                raise ValueError("终态完整图分母不符")
            verified = True
        except Exception as exc:
            errors.append(type(exc).__name__ + ": " + str(exc))
        compressed_sha, observed_compressed_bytes = None, None
        try:
            self.stream.seek(0)
            hasher = hashlib.sha256()
            total_bytes = 0
            while raw := self.stream.read(1024 * 1024):
                hasher.update(raw)
                total_bytes += len(raw)
            compressed_sha = hasher.hexdigest()
            observed_compressed_bytes = total_bytes
        except Exception as exc:
            errors.append(type(exc).__name__ + ": " + str(exc))
        reconciled = self._cost["store_calls"] == self._cost["unique_views_saved"] + self._cost["deduplicated_calls"] + self._cost["failed_store_calls"]
        self._terminal = {"closed": closed, "verified": verified, "verified_unique_views": records,
            "store_calls_reconciled": reconciled,
            "terminal_valid": closed and verified and reconciled and not errors and self._cost["failed_store_calls"] == 0,
            "compressed_sha256": compressed_sha, "observed_compressed_bytes": observed_compressed_bytes,
            "errors": errors,
            "verification_monotonic_seconds": time.monotonic() - verification_started}
        return self.costs
