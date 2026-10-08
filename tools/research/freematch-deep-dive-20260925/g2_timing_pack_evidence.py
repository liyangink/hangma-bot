#!/usr/bin/env python3
"""封存 G2 开发教师的逐根精确快照和逐墙双臂结果。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = _PROJECT_ROOT
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g2-timing-development-01')
ARCHIVE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g2-timing-development-01/paired-evidence.zip')
CHECKSUMS = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g2-timing-development-01/paired-evidence-checksums.json')


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def expected_names() -> set[str]:
    targets = json.loads((_project_file(_PROJECT_ROOT, OUT / "targets.json")).read_text(encoding="utf-8"))
    if targets.get("replication_labels_opened") is not False:
        raise ValueError("自然复验标签已打开")
    development = [t for t in targets["targets"] if t["split"] == "development"]
    replication = [t for t in targets["targets"] if t["split"] == "replication"]
    if len(development) != 24 or len(replication) != 24:
        raise ValueError("开发或复验根数不符")
    return ({"snapshots/" + t["target_id"] + ".json" for t in development}
            | {"rollouts/" + t["target_id"] + f"-future-{i:02d}.json"
               for t in development for i in range(1, 33)})


def pack() -> None:
    """机械门与数量全绿后创建确定性 ZIP；原始散文件保留供本机复算。"""
    if ARCHIVE.exists() or CHECKSUMS.exists():
        raise SystemExit("G2 归档已存在，拒绝覆盖")
    result = json.loads((_project_file(_PROJECT_ROOT, OUT / "result.json")).read_text(encoding="utf-8"))
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if (result.get("independent_roots") != 24 or result.get("paired_future_walls") != 768
            or result.get("replication_labels_opened") is not False
            or summary.get("actual_tables") != 1536
            or summary.get("mechanical_failures") != 0
            or summary.get("replication_rollouts") != 0):
        raise ValueError("G2 开发完整性门未过")
    expected = expected_names()
    actual = {str(p.relative_to(OUT)) for base in ("snapshots", "rollouts")
              for p in (_project_file(_PROJECT_ROOT, OUT / base)).glob("*.json")}
    if actual != expected:
        raise ValueError("G2 开发文件集合与冻结目标不符")
    checksums = {}
    with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9, strict_timestamps=True) as bundle:
        for name in sorted(expected):
            payload = (_project_file(_PROJECT_ROOT, OUT / name)).read_bytes()
            document = json.loads(payload)
            if name.startswith("rollouts/") and document.get("mechanical_ok") is not True:
                raise ValueError("G2 配对机械失败：" + name)
            checksums[name] = digest(payload)
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            bundle.writestr(entry, payload, compress_type=zipfile.ZIP_DEFLATED,
                            compresslevel=9)
    CHECKSUMS.write_text(json.dumps({
        "schema": "g2-timing-paired-evidence-archive/1",
        "files": len(expected), "snapshots": 24, "paired_future_walls": 768,
        "complete_tables": 1536, "replication_labels_opened": False,
        "archive_sha256": digest(ARCHIVE.read_bytes()),
        "file_sha256": checksums,
    }, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    verify()
    print(json.dumps({"status": "PACKED", "files": len(expected),
                      "archive_bytes": ARCHIVE.stat().st_size}, ensure_ascii=False))


def verify() -> None:
    """逐文件校验归档；散文件缺省时仍可用于移机审查。"""
    manifest = json.loads(CHECKSUMS.read_text(encoding="utf-8"))
    if (manifest.get("files") != 792 or manifest.get("file_sha256") is None
            or manifest.get("replication_labels_opened") is not False
            or set(manifest["file_sha256"]) != expected_names()):
        raise ValueError("G2 归档清单与冻结开发目标不符")
    if digest(ARCHIVE.read_bytes()) != manifest["archive_sha256"]:
        raise ValueError("G2 ZIP 摘要不符")
    with zipfile.ZipFile(ARCHIVE) as bundle:
        if set(bundle.namelist()) != set(manifest["file_sha256"]):
            raise ValueError("G2 ZIP 文件集合不符")
        for name, expected_sha in manifest["file_sha256"].items():
            data = bundle.read(name)
            if digest(data) != expected_sha:
                raise ValueError("G2 ZIP 内文件摘要不符：" + name)
            loose = _project_file(_PROJECT_ROOT, OUT / name)
            if loose.exists() and digest(loose.read_bytes()) != expected_sha:
                raise ValueError("G2 散文件摘要不符：" + name)
    print(json.dumps({"status": "VERIFIED", "files": manifest["files"]},
                     ensure_ascii=False))


def unpack() -> None:
    """恢复散文件，拒绝覆盖不同内容。"""
    verify()
    manifest = json.loads(CHECKSUMS.read_text(encoding="utf-8"))
    restored = 0
    with zipfile.ZipFile(ARCHIVE) as bundle:
        for name, expected_sha in manifest["file_sha256"].items():
            path = _project_file(_PROJECT_ROOT, OUT / name)
            if path.exists():
                continue
            data = bundle.read(name)
            if digest(data) != expected_sha:
                raise ValueError("G2 恢复文件摘要不符：" + name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            restored += 1
    print(json.dumps({"status": "UNPACKED", "restored": restored},
                     ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("pack", "verify", "unpack"))
    args = parser.parse_args()
    {"pack": pack, "verify": verify, "unpack": unpack}[args.command]()


if __name__ == "__main__":
    main()
