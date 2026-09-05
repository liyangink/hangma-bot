"""共用审计读取器：按实际文件返回记录及相对路径/行号。

定位（审计增强方案 §6）：验证器、离线转换与 audit_tool 的 inspect/watch
共用同一读取实现，避免各自发明损坏行处理。约束：

- 支持普通 .jsonl 与 gzip 分段 .jsonl.gz（含 raw 轮转段）；
- 格式损坏提供位置（相对路径 + 行号），不悄悄丢掉行；
- 运行中 JSONL 的最后半行（无换行结尾）暂缓读取并报告问题——
  封存后仍存在半行才是损坏（离线消费方据此区分运行中与已封存）；
- 压缩尾段正在写入（无 gzip trailer）标记为未闭合，不反复从头扫描；
- 读取器只做逐行 JSON 解码，不重做验证器的关联检查。
"""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping


@dataclass(frozen=True)
class ReadRecord:
    """一条按位置读出的审计记录；解析失败时 envelope 字段为空并带 error。"""

    relative_path: str  # 相对读取根的 POSIX 风格路径
    line_no: int  # 1 起；整文件记录（manifest/summary）为 0
    kind: str | None
    context: Mapping[str, Any] | None
    payload: Mapping[str, Any] | None
    error: str | None  # 非空表示该行无法 JSON 解码或信封不完整


@dataclass(frozen=True)
class ReadIssue:
    """文件级读取问题（尾部半行/截断 gzip/不可读等），带位置。"""

    relative_path: str
    line_no: int  # 问题行号；文件级问题为 0
    issue: str


@dataclass(frozen=True)
class ReadResult:
    """一次读取的完整结果：记录、文件清单与位置化问题。"""

    records: tuple[ReadRecord, ...]
    files: tuple[str, ...]
    issues: tuple[ReadIssue, ...]


class _UnreadableFile(Exception):
    """文件无法打开/读取；由 iter_records 转成 ReadIssue。"""


def _iter_lines(path: Path):
    """逐行产出 (line_no, text, complete)；complete=False 表示最后半行。

    对 gzip 段：读取途中 EOFError（无 trailer）表示压缩尾段未闭合；
    以 _GzipTailUnclosed 异常把未闭合事实与已读行数交给调用方，
    调用方丢弃未闭合尾巴，不再从头扫描。
    """

    if path.name.endswith(".jsonl.gz"):
        handle = gzip.open(path, "rt", encoding="utf-8", errors="replace", newline="\n")
    else:
        handle = path.open("r", encoding="utf-8", errors="replace", newline="\n")
    line_no = 0
    last_raw = None
    truncated = False
    try:
        with handle:
            while True:
                raw = handle.readline()
                if raw == "":
                    break
                line_no += 1
                last_raw = raw
                if not raw.endswith("\n"):
                    yield line_no, raw.rstrip("\n"), False
                    return
                yield line_no, raw.rstrip("\n"), True
    except EOFError:
        truncated = True
    except OSError as exc:
        raise _UnreadableFile(str(exc)) from None
    if truncated:
        partial = None
        if last_raw is not None and not last_raw.endswith("\n"):
            partial = last_raw.rstrip("\n")
        raise _GzipTailUnclosed(line_no, partial)


class _GzipTailUnclosed(Exception):
    """gzip 段未闭合；携带未闭合位置供调用方丢弃。"""

    def __init__(self, line_no: int, partial: str | None) -> None:
        super().__init__("gzip 段未闭合")
        self.line_no = line_no
        self.partial = partial


def iter_records(root: str | Path) -> Iterator[ReadRecord]:
    """按字典序遍历读取根下的全部 JSONL 记录；损坏行以 error 形式产出。

    本函数是生成器：边读边产出，适合大数据集流式消费。不产出
    manifest/summary 等单对象文件——它们由各自解析函数读取。
    """

    directory = Path(root)
    paths = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        if path.name.endswith(".jsonl") or path.name.endswith(".jsonl.gz"):
            paths.append(path)
    for path in paths:
        relative = path.relative_to(directory).as_posix()
        try:
            lines = _iter_lines(path)
        except _UnreadableFile as exc:
            yield ReadRecord(
                relative_path=relative,
                line_no=0,
                kind=None,
                context=None,
                payload=None,
                error="unreadable_file: " + str(exc),
            )
            continue
        while True:
            try:
                item = next(lines)
            except StopIteration:
                break
            except _GzipTailUnclosed as exc:
                # 未闭合 gzip 段：该段尾部整体不可信，产出错误记录说明。
                yield ReadRecord(
                    relative_path=relative,
                    line_no=exc.line_no,
                    kind=None,
                    context=None,
                    payload=None,
                    error="gzip_tail_unclosed",
                )
                break
            line_no, text, complete = item
            if not text.strip():
                continue  # 空行按可忽略空白处理
            if not complete:
                # 运行中文件的最后半行：暂缓读取（方案 §6）。该半行可能
                # 恰好是完整记录，但无法证明——不产出记录，由文件级问题说明。
                yield ReadRecord(
                    relative_path=relative,
                    line_no=line_no,
                    kind=None,
                    context=None,
                    payload=None,
                    error="trailing_partial_line",
                )
                break
            try:
                envelope = json.loads(text)
            except json.JSONDecodeError as exc:
                yield ReadRecord(
                    relative_path=relative,
                    line_no=line_no,
                    kind=None,
                    context=None,
                    payload=None,
                    error="json_decode_error: " + str(exc.msg),
                )
                continue
            if not isinstance(envelope, dict) or envelope.get("schema_version") != 1:
                yield ReadRecord(
                    relative_path=relative,
                    line_no=line_no,
                    kind=None,
                    context=None,
                    payload=None,
                    error="envelope_shape_invalid",
                )
                continue
            context = envelope.get("context")
            payload = envelope.get("payload")
            yield ReadRecord(
                relative_path=relative,
                line_no=line_no,
                kind=envelope.get("kind"),
                context=context if isinstance(context, dict) else None,
                payload=payload if isinstance(payload, dict) else None,
                error=None,
            )


def read_records(root: str | Path) -> ReadResult:
    """读取根下全部记录并收集文件清单与位置化问题；损坏行不丢。"""

    directory = Path(root)
    files = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        if path.name.endswith(".jsonl") or path.name.endswith(".jsonl.gz"):
            files.append(path.relative_to(directory).as_posix())
    issues = []
    records = []
    for record in iter_records(directory):
        records.append(record)
        if record.error is not None and record.kind is None:
            issues.append(
                ReadIssue(
                    relative_path=record.relative_path,
                    line_no=record.line_no,
                    issue=record.error,
                )
            )
    return ReadResult(records=tuple(records), files=tuple(files), issues=tuple(issues))


# ---------------------------------------------------------------------------
# bundle 清单读取与校验（供打包/核验/转换共用）
# ---------------------------------------------------------------------------

BUNDLE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class BundleFileEntry:
    """bundle 清单中的一个文件条目；path 为包内相对路径。"""

    path: str
    bytes: int
    sha256: str


@dataclass(frozen=True)
class BundleManifest:
    """已校验的 bundle.json 内容；raw 保留完整原对象供逐字段追溯。"""

    bundle_id: str
    created_at_unix_ms: int
    run_ids: tuple[str, ...]
    parent_bundle_ids: tuple[str, ...]
    closed_cleanly_by_run: bool
    source_notes: str
    files: tuple[BundleFileEntry, ...]
    raw: Mapping[str, Any]


def _require_safe_relative_path(value: object) -> str:
    """拒绝绝对路径、路径穿越、空组件与反斜杠；只接受 POSIX 相对路径。"""

    if not isinstance(value, str) or not value:
        raise ValueError("文件路径必须是非空字符串")
    if value.startswith("/") or "\\" in value or "\x00" in value:
        raise ValueError("文件路径必须是包内相对路径: {!r}".format(value))
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError("文件路径包含非法组件: {!r}".format(value))
    return value


def read_bundle_manifest(path: str | Path) -> BundleManifest:
    """读取并校验 bundle.json；未知主版本或非法结构抛 ValueError。

    校验内容（方案 §4）：固定字段类型、files 条目的 {path,bytes,sha256}
    三键、SHA-256 全长小写十六进制、包内相对路径安全性与路径唯一性。
    """

    document: object
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(
            "bundle.json 无法读取: {}: {}".format(type(exc).__name__, exc)
        ) from None
    if not isinstance(document, dict):
        raise ValueError("bundle.json 必须是 JSON 对象")
    version = document.get("bundle_schema_version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise ValueError("bundle_schema_version 缺失或不是整数")
    if version != BUNDLE_SCHEMA_VERSION:
        raise ValueError(
            "bundle_schema_version={!r} 与当前版本 {} 不匹配，拒绝读取未知主版本".format(
                version, BUNDLE_SCHEMA_VERSION
            )
        )
    bundle_id = document.get("bundle_id")
    if not isinstance(bundle_id, str) or not bundle_id.strip():
        raise ValueError("bundle_id 缺失")
    created = document.get("created_at_unix_ms")
    if isinstance(created, bool) or not isinstance(created, int) or created < 0:
        raise ValueError("created_at_unix_ms 必须是非负整数 Unix 毫秒")
    run_ids = document.get("run_ids")
    if not isinstance(run_ids, list) or not all(isinstance(item, str) and item for item in run_ids):
        raise ValueError("run_ids 必须是非空字符串数组")
    parent_ids = document.get("parent_bundle_ids", [])
    if not isinstance(parent_ids, list) or not all(isinstance(item, str) and item for item in parent_ids):
        raise ValueError("parent_bundle_ids 必须是非空字符串数组")
    closed = document.get("closed_cleanly_by_run")
    if not isinstance(closed, bool):
        raise ValueError("closed_cleanly_by_run 必须是布尔值")
    notes = document.get("source_notes", "")
    if not isinstance(notes, str):
        raise ValueError("source_notes 必须是字符串")
    files_raw = document.get("files")
    if not isinstance(files_raw, list):
        raise ValueError("files 缺失或不是数组")
    entries = []
    seen = set()
    for item in files_raw:
        if not isinstance(item, dict):
            raise ValueError("files 元素必须是对象")
        entry_path = _require_safe_relative_path(item.get("path"))
        if entry_path in seen:
            raise ValueError("files 存在重复路径: {!r}".format(entry_path))
        seen.add(entry_path)
        size = item.get("bytes")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise ValueError("files[].bytes 必须是非负整数: {!r}".format(entry_path))
        digest = item.get("sha256")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(ch not in "0123456789abcdef" for ch in digest)
        ):
            raise ValueError(
                "files[].sha256 必须是 64 位小写十六进制: {!r}".format(entry_path)
            )
        entries.append(BundleFileEntry(path=entry_path, bytes=size, sha256=digest))
    return BundleManifest(
        bundle_id=bundle_id,
        created_at_unix_ms=created,
        run_ids=tuple(run_ids),
        parent_bundle_ids=tuple(parent_ids),
        closed_cleanly_by_run=closed,
        source_notes=notes,
        files=tuple(entries),
        raw=document,
    )


__all__ = [
    "BUNDLE_SCHEMA_VERSION",
    "BundleFileEntry",
    "BundleManifest",
    "ReadIssue",
    "ReadRecord",
    "ReadResult",
    "iter_records",
    "read_bundle_manifest",
    "read_records",
]
