"""按原字节恢复T185完整开发与确认计划元数据，不覆盖不同原件。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import gzip
import hashlib
import json
from pathlib import Path


def main():
    """先核齐三份压缩与原摘要，再排他新建缺件；不恢复大体积逐桌审计。"""
    folder = Path(__file__).resolve().parent
    archive = json.loads((folder / "DEVELOPMENT-RAW-ARCHIVE.json").read_text())
    names = {"DEVELOPMENT-CLOSED.json", "DEVELOPMENT-JOKER-STRATA.json", "CONFIRMATION-PLAN.json"}
    if archive["schema"] != "t185-development-metadata-archive/1" or set(archive["files"]) != names:
        raise ValueError("不是本批固定三份闭合／冻结元数据")
    pending = []
    for name, expected in archive["files"].items():
        compressed = (folder / (name + ".gz")).read_bytes()
        if len(compressed) != expected["compressed"]["bytes"] or hashlib.sha256(compressed).hexdigest() != expected["compressed"]["sha256"]:
            raise ValueError("压缩原件身份漂移:" + name)
        ceiling = expected["original"]["bytes"]
        if type(ceiling) is not int or not 0 < ceiling <= 33554432:
            raise ValueError("原件字节预算无效")
        with gzip.open(folder / (name + ".gz"), "rb") as stream:
            raw = stream.read(ceiling + 1)
        if len(raw) != ceiling or hashlib.sha256(raw).hexdigest() != expected["original"]["sha256"]:
            raise ValueError("解压不能匹配原字节:" + name)
        target = folder / name
        if target.exists() and target.read_bytes() != raw:
            raise ValueError("已有原件不同，不覆盖:" + name)
        pending.append((name, target, raw, expected["original"]))
    for name, target, raw, original in pending:
        if target.exists():
            status = "existing_original_verified"
        else:
            with target.open("xb") as output:
                if output.write(raw) != len(raw):
                    raise OSError("写入不足，不声称恢复成功:" + name)
            if target.read_bytes() != raw:
                raise OSError("恢复后字节不同:" + name)
            status = "original_restored"
        print(json.dumps({"file": name, "status": status, **original}))


if __name__ == "__main__":
    main()
