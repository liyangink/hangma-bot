#!/usr/bin/env python3
"""将 G1 结果盲自然来源压缩封存，并逐文件校验内容摘要。"""

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
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g1-timing-natural-01')
ARCHIVE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g1-timing-natural-01/sources.zip')
CHECKSUMS = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g1-timing-natural-01/source-checksums.json')


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pack() -> None:
    """冻结 256 个完整来源；归档不含阶段分或终局标签。"""

    if ARCHIVE.exists() or CHECKSUMS.exists():
        raise SystemExit("来源归档已存在；拒绝覆盖")
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    frozen = json.loads((_project_file(_PROJECT_ROOT, OUT / "sources.json")).read_text(encoding="utf-8"))["sources"]
    if summary.get("failure") or summary.get("actual_tables") != 512 or len(frozen) != 256:
        raise ValueError("512 桌来源未完整，不可封存")
    expected = {str(row["source_id"]).replace(":", "-") + ".json" for row in frozen}
    actual = {path.name for path in (_project_file(_PROJECT_ROOT, OUT / "sources")).glob("*.json")}
    if actual != expected:
        raise ValueError("来源文件集合与冻结清单不符")
    digests = {}
    with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9, strict_timestamps=True) as bundle:
        for name in sorted(expected):
            data = (_project_file(_PROJECT_ROOT, OUT / "sources" / name)).read_bytes()
            document = json.loads(data)
            if document.get("status") != "complete" or document.get("tables") != 2:
                raise ValueError("来源未完成：" + name)
            digests[name] = _digest(data)
            entry = zipfile.ZipInfo("sources/" + name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            bundle.writestr(entry, data, compress_type=zipfile.ZIP_DEFLATED,
                            compresslevel=9)
    manifest = {
        "schema": "g1-timing-source-archive/1",
        "source_count": len(digests), "tables": 512,
        "archive_sha256": _digest(ARCHIVE.read_bytes()),
        "source_sha256": digests,
        "contains_outcome_labels": False,
    }
    CHECKSUMS.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                                    indent=2) + "\n", encoding="utf-8")
    verify()
    print(json.dumps({"status": "PACKED", "sources": len(digests),
                      "archive_bytes": ARCHIVE.stat().st_size,
                      "sha256": manifest["archive_sha256"]}, ensure_ascii=False))


def verify() -> None:
    """逐条核对 ZIP 与散文件；移机后散文件可缺省。"""

    manifest = json.loads(CHECKSUMS.read_text(encoding="utf-8"))
    if manifest.get("source_count") != 256 or manifest.get("tables") != 512:
        raise ValueError("归档清单数量不符")
    if _digest(ARCHIVE.read_bytes()) != manifest["archive_sha256"]:
        raise ValueError("ZIP 摘要不符")
    with zipfile.ZipFile(ARCHIVE) as bundle:
        entries = {info.filename: info for info in bundle.infolist()}
        expected = {"sources/" + name for name in manifest["source_sha256"]}
        if set(entries) != expected:
            raise ValueError("ZIP 内文件集合不符")
        for name, sha in manifest["source_sha256"].items():
            data = bundle.read("sources/" + name)
            if _digest(data) != sha:
                raise ValueError("ZIP 内来源摘要不符：" + name)
            loose = _project_file(_PROJECT_ROOT, OUT / "sources" / name)
            if loose.exists() and _digest(loose.read_bytes()) != sha:
                raise ValueError("本地散文件摘要不符：" + name)
    print(json.dumps({"status": "VERIFIED", "sources": len(expected)},
                     ensure_ascii=False))


def unpack() -> None:
    """移机后恢复来源散文件，拒绝覆盖内容不同的现有文件。"""

    verify()
    manifest = json.loads(CHECKSUMS.read_text(encoding="utf-8"))
    (_project_file(_PROJECT_ROOT, OUT / "sources")).mkdir(parents=True, exist_ok=True)
    restored = 0
    with zipfile.ZipFile(ARCHIVE) as bundle:
        for name, sha in manifest["source_sha256"].items():
            path = _project_file(_PROJECT_ROOT, OUT / "sources" / name)
            if path.exists():
                if _digest(path.read_bytes()) != sha:
                    raise ValueError("现有来源内容不同，拒绝覆盖：" + name)
                continue
            data = bundle.read("sources/" + name)
            if _digest(data) != sha:
                raise ValueError("归档来源摘要不符：" + name)
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
