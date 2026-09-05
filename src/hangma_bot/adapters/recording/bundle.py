"""审计证据包：封存运行目录、清单校验、打包与安全展开。

职责（审计增强方案 §4）：把关闭后的运行目录复制进不可变 bundle，
为每个文件生成 SHA-256 清单；打包为 tar.gz + .sha256 后可以跨节点
转移；展开前先核验归档哈希、再核对内部清单，拒绝绝对路径、路径穿越、
链接及同名覆盖。所有注释写在文档，JSON 文件保持严格 JSON。

- create_bundle：关闭运行目录后检查、复制并写 bundle.json；
- verify_bundle：核对清单内所有文件的存在、字节数与哈希，并写
  validation.json（发现额外文件只提示，不影响清单自身成立）；
- pack_bundle：封存前重算全量文件清单（含 official/ 下载目录），
  重写 bundle.json 后产出 tar.gz 与 .sha256；
- extract_bundle：校验归档哈希后安全展开到目标目录并核对内部清单。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import time
import uuid
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from hangma_bot.adapters.recording.reader import (
    BUNDLE_SCHEMA_VERSION,
    BundleManifest,
    read_bundle_manifest,
)

BUNDLE_JSON_NAME = "bundle.json"
VALIDATION_JSON_NAME = "validation.json"


def sha256_hex(data: bytes) -> str:
    """返回数据的 SHA-256 全长小写十六进制；与 bundle 清单口径一致。"""

    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    """流式计算文件 SHA-256；大文件不整体载入内存。"""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _scan_regular_files(root: Path) -> dict[str, Path]:
    """扫描目录下全部普通文件；符号链接一律拒绝（安全边界）。

    返回包内相对路径（POSIX 风格）到绝对路径的映射。目录符号链接不
    遍历（pathlib 默认），文件符号链接显式拒绝，避免把链接目标内容
    当成包内容封存。
    """

    result: dict[str, Path] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("包内不允许符号链接: {!r}".format(path))
        if path.is_file():
            result[path.relative_to(root).as_posix()] = path
    return result


def _build_manifest_document(
    *,
    bundle_id: str,
    created_at_unix_ms: int,
    run_ids: Sequence[str],
    parent_bundle_ids: Sequence[str],
    closed_cleanly_by_run: bool,
    source_notes: str,
    file_entries: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """组装 bundle.json 文档；固定字段见方案 §4，files 按路径排序。"""

    return {
        "bundle_schema_version": BUNDLE_SCHEMA_VERSION,
        "bundle_id": bundle_id,
        "created_at_unix_ms": created_at_unix_ms,
        "run_ids": list(run_ids),
        "parent_bundle_ids": list(parent_bundle_ids),
        "closed_cleanly_by_run": closed_cleanly_by_run,
        "source_notes": source_notes,
        "files": sorted(file_entries, key=lambda item: item["path"]),
    }


def _write_bundle_json(bundle_dir: Path, document: Mapping[str, Any]) -> None:
    bundle_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / BUNDLE_JSON_NAME).write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def create_bundle(
    audit_root: str | Path,
    *,
    run_ids: Sequence[str],
    out_dir: str | Path,
    source_notes: str = "",
    parent_bundle_ids: Sequence[str] = (),
    bundle_id: str | None = None,
    created_at_unix_ms: int | None = None,
) -> BundleManifest:
    """把已关闭的 run 目录复制进新 bundle 并写清单；返回可校验清单。

    - 复制前检查每个 run 目录是否已关闭（存在 summary.json）：
      未关闭的运行如实标记 closed_cleanly_by_run=false 并写入
      source_notes，绝不把活动目录声称已完整封存；
    - bundle 目录在 out_dir/bundles/{bundle_id}/ 下创建，已存在同名
      目录时拒绝（封存后不可原地修改）；
    - 文件逐字节复制并同步计算 SHA-256，清单不含 bundle.json 自身。
    """

    root = Path(audit_root)
    out = Path(out_dir)
    if not root.is_dir():
        raise FileNotFoundError("审计根目录不存在: {}".format(root))
    if not run_ids:
        raise ValueError("run_ids 不能为空")
    chosen_id = bundle_id if bundle_id is not None else uuid.uuid4().hex
    created_ms = (
        int(created_at_unix_ms)
        if created_at_unix_ms is not None
        else int(time.time() * 1000)
    )
    bundle_dir = out / "bundles" / chosen_id
    if bundle_dir.exists():
        raise FileExistsError("bundle 目录已存在，封存后不可覆盖: {}".format(bundle_dir))

    copied_runs: list[str] = []
    all_closed = True
    for run_id in run_ids:
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id 必须是非空字符串")
        source = root / "runs" / run_id
        if not source.is_dir():
            raise FileNotFoundError("run 目录不存在: {}".format(source))
        destination = bundle_dir / "runs" / run_id
        shutil.copytree(source, destination, symlinks=True)
        # copytree(symlinks=True) 保留符号链接——复制后再显式拒绝，
        # 避免把链接封进包（安全边界）。
        for path in destination.rglob("*"):
            if path.is_symlink():
                raise ValueError("run 目录含符号链接，拒绝封存: {}".format(path))
        copied_runs.append(run_id)
        if not (source / "summary.json").is_file():
            all_closed = False
    if not all_closed:
        source_notes = (
            (source_notes + "；" if source_notes else "")
            + "存在未关闭运行目录（缺 summary.json），closed_cleanly_by_run=false"
        )
    bundle_dir.mkdir(parents=True, exist_ok=True)
    files = _scan_regular_files(bundle_dir)
    entries = [
        {
            "path": relative,
            "bytes": absolute.stat().st_size,
            "sha256": sha256_file(absolute),
        }
        for relative, absolute in sorted(files.items())
    ]
    document = _build_manifest_document(
        bundle_id=chosen_id,
        created_at_unix_ms=created_ms,
        run_ids=copied_runs,
        parent_bundle_ids=list(parent_bundle_ids),
        closed_cleanly_by_run=all_closed,
        source_notes=source_notes,
        file_entries=entries,
    )
    _write_bundle_json(bundle_dir, document)
    return read_bundle_manifest(bundle_dir / BUNDLE_JSON_NAME)


def verify_bundle(bundle_dir: str | Path, *, write_report: bool = True) -> dict[str, Any]:
    """核对清单内所有文件的存在、字节数与 SHA-256；返回机器可读报告。

    报告字段：bundle_id/files_total/files_ok/mismatched/missing/extra/
    ok。ok 仅当清单内所有文件都匹配；extra 为包根下未列入清单的
    文件（bundle.json/validation.json 除外），只提示不改变 ok——
    清单自身是否成立只由清单内文件决定。write_report 时把报告写入
    validation.json。
    """

    directory = Path(bundle_dir)
    manifest_path = directory / BUNDLE_JSON_NAME
    if not manifest_path.is_file():
        raise FileNotFoundError("缺少 bundle.json: {}".format(manifest_path))
    manifest = read_bundle_manifest(manifest_path)
    listed = {entry.path for entry in manifest.files}
    mismatched: list[dict[str, Any]] = []
    missing: list[str] = []
    files_ok = 0
    for entry in manifest.files:
        absolute = directory / Path(*entry.path.split("/"))
        if not absolute.is_file():
            missing.append(entry.path)
            continue
        size = absolute.stat().st_size
        if size != entry.bytes:
            mismatched.append(
                {"path": entry.path, "kind": "size", "expected": entry.bytes, "actual": size}
            )
            continue
        digest = sha256_file(absolute)
        if digest != entry.sha256:
            mismatched.append(
                {"path": entry.path, "kind": "sha256", "expected": entry.sha256, "actual": digest}
            )
            continue
        files_ok += 1
    extra: list[str] = []
    for relative, _ in _scan_regular_files(directory).items():
        if relative in listed or relative in (BUNDLE_JSON_NAME, VALIDATION_JSON_NAME):
            continue
        extra.append(relative)
    report: dict[str, Any] = {
        "bundle_id": manifest.bundle_id,
        "files_total": len(manifest.files),
        "files_ok": files_ok,
        "mismatched": mismatched,
        "missing": missing,
        "extra": extra,
        "ok": not mismatched and not missing,
    }
    if write_report:
        (directory / VALIDATION_JSON_NAME).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return report


def pack_bundle(
    bundle_dir: str | Path,
    archive_path: str | Path,
    *,
    source_notes: str = "",
) -> dict[str, Any]:
    """封存 bundle：重算全量清单、重写 bundle.json、产出 tar.gz + .sha256。

    为什么在 pack 时重算清单：collect-test-room 在 create_bundle 之后
    把 official/ 下载目录写入 bundle 根，封存点必须把全部内容（含
    下载目录）纳入清单——封存后不可追加。pack 只增加/更新清单文件，
    不修改任何数据文件；若清单已有条目与实际文件不符，先报错拒绝
    封存而不是用新哈希覆盖证据。
    """

    directory = Path(bundle_dir)
    manifest_path = directory / BUNDLE_JSON_NAME
    if not manifest_path.is_file():
        raise FileNotFoundError("缺少 bundle.json: {}".format(manifest_path))
    previous = read_bundle_manifest(manifest_path)
    # 已有清单条目必须仍然成立：打包不得吞掉"文件被篡改/丢失"的事实。
    existing = verify_bundle(directory, write_report=False)
    if not existing["ok"]:
        raise ValueError("已有清单校验失败，拒绝封存: {}".format(existing))
    files = _scan_regular_files(directory)
    entries = [
        {
            "path": relative,
            "bytes": absolute.stat().st_size,
            "sha256": sha256_file(absolute),
        }
        for relative, absolute in sorted(files.items())
        if relative not in (BUNDLE_JSON_NAME, VALIDATION_JSON_NAME)
    ]
    merged_notes = previous.source_notes
    if source_notes:
        merged_notes = merged_notes + ("；" if merged_notes else "") + source_notes
    document = _build_manifest_document(
        bundle_id=previous.bundle_id,
        created_at_unix_ms=previous.created_at_unix_ms,
        run_ids=previous.run_ids,
        parent_bundle_ids=previous.parent_bundle_ids,
        closed_cleanly_by_run=previous.closed_cleanly_by_run,
        source_notes=merged_notes,
        file_entries=entries,
    )
    _write_bundle_json(directory, document)
    archive = Path(archive_path)
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists():
        raise FileExistsError("归档已存在，拒绝覆盖: {}".format(archive))
    base = directory.name
    with tarfile.open(archive, "w:gz") as tar:
        for relative in sorted(files):
            if relative in (BUNDLE_JSON_NAME, VALIDATION_JSON_NAME):
                continue
            tar.add(directory / Path(*relative.split("/")), arcname=base + "/" + relative)
        tar.add(directory / BUNDLE_JSON_NAME, arcname=base + "/" + BUNDLE_JSON_NAME)
    digest = sha256_file(archive)
    sha_path = Path(str(archive) + ".sha256")
    sha_path.write_text(digest + "  " + archive.name + "\n", encoding="utf-8")
    return {
        "bundle_id": previous.bundle_id,
        "archive": str(archive),
        "sha256": digest,
        "sha256_file": str(sha_path),
        "files_total": len(entries),
    }


def _safe_member_name(name: str) -> str:
    """校验归档成员名并归一化；拒绝绝对路径、穿越与反斜杠。"""

    if not name or name.startswith("/") or "\\" in name or "\x00" in name:
        raise ValueError("归档成员名非法（绝对路径或非法字符）: {!r}".format(name))
    parts = name.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError("归档成员名含路径穿越: {!r}".format(name))
    return name


def extract_bundle(archive_path: str | Path, dest_dir: str | Path) -> dict[str, Any]:
    """核验归档哈希后安全展开并核对内部清单；返回核验报告。

    安全约束（方案 §4）：先核验 .sha256（存在时），再安全展开到目标
    目录——拒绝绝对路径、路径穿越、链接与设备文件、以及目标内同名
    覆盖；展开完成后读取包内 bundle.json 并核对全部哈希。
    """

    archive = Path(archive_path)
    if not archive.is_file():
        raise FileNotFoundError("归档不存在: {}".format(archive))
    sha_path = Path(str(archive) + ".sha256")
    expected_digest: str | None = None
    if sha_path.is_file():
        first = sha_path.read_text(encoding="utf-8").split()[0]
        if len(first) == 64 and all(ch in "0123456789abcdef" for ch in first):
            expected_digest = first
    actual_digest = sha256_file(archive)
    if expected_digest is not None and expected_digest != actual_digest:
        raise ValueError(
            "归档哈希核验失败: 期望 {} 实际 {}".format(expected_digest, actual_digest)
        )
    destination = Path(dest_dir)
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        top_dirs: set[str] = set()
        for member in members:
            name = _safe_member_name(member.name)
            if member.issym() or member.islnk() or member.isdev():
                raise ValueError("归档含链接或设备文件，拒绝展开: {!r}".format(member.name))
            top = name.split("/", 1)[0]
            top_dirs.add(top)
        if not top_dirs:
            raise ValueError("归档为空")
        for member in members:
            name = _safe_member_name(member.name)
            target = destination / Path(*name.split("/"))
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if target.exists():
                raise FileExistsError("目标已存在同名路径，拒绝覆盖: {}".format(target))
            source = tar.extractfile(member)
            if source is None:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with source, target.open("wb") as handle:
                shutil.copyfileobj(source, handle)
    # 定位包根（唯一顶层目录）并核对内部清单。
    extracted_root = destination / sorted(top_dirs)[0]
    manifest_path = extracted_root / BUNDLE_JSON_NAME
    if not manifest_path.is_file():
        raise ValueError("展开结果缺少 bundle.json: {}".format(manifest_path))
    report = verify_bundle(extracted_root, write_report=False)
    return {
        "archive": str(archive),
        "archive_sha256": actual_digest,
        "extracted_to": str(extracted_root),
        "bundle_id": report["bundle_id"],
        "verification": report,
    }


__all__ = [
    "BUNDLE_JSON_NAME",
    "VALIDATION_JSON_NAME",
    "create_bundle",
    "extract_bundle",
    "pack_bundle",
    "sha256_file",
    "sha256_hex",
    "verify_bundle",
]
