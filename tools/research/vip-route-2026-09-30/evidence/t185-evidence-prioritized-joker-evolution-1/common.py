"""T185独立证据工具；只新建文件，不改旧冻结批或线上配置。"""

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
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
OLD = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t182-step12-diagnosis-and-joint-evolution-1')


def canonical(value):
    """稳定JSON字节；拒绝非有限数，用于输入与完整输出复核。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def pin(path):
    """返回文件字节数与SHA；不从名称继承旧验收。"""
    raw = Path(path).read_bytes()
    return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def save(path, value):
    """排他新建JSON证据；失败不覆盖已经发生的尝试。"""
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
