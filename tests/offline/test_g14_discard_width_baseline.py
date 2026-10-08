"""G14 窄面量具：同向听、多路线保护与公开容量边界。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'tests/offline'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from pathlib import Path
import sys


sys.path.insert(0, str(_project_file(_PROJECT_ROOT, Path(__file__).resolve().parents[2] /
                       "review/freematch-deep-dive-20260925")))

from g14_discard_width_baseline import _safe_wider, _shape


def test_wider_requires_progress_and_capacity_protection():
    parent = _shape({"standard_shanten_after": 1, "shanten_after": 1,
                     "seven_pairs_shanten_after": 2,
                     "standard_useful_tiles": [
                         {"code": "1w", "remaining_estimate": 2},
                         {"code": "2w", "remaining_estimate": 2}],
                     "useful_tiles": [{"code": "1w", "remaining_estimate": 4}]})
    wider = _shape({"standard_shanten_after": 1, "shanten_after": 1,
                    "seven_pairs_shanten_after": 2,
                    "standard_useful_tiles": [
                        {"code": "3w", "remaining_estimate": 1},
                        {"code": "4w", "remaining_estimate": 1},
                        {"code": "5w", "remaining_estimate": 2}],
                    "useful_tiles": [{"code": "3w", "remaining_estimate": 4}]})
    assert _safe_wider(parent, wider, allowed_capacity_loss=0)
    assert not _safe_wider(parent, {**wider, "seven_shanten": 3},
                           allowed_capacity_loss=0)
    assert not _safe_wider(parent, {**wider, "standard_shanten": 2},
                           allowed_capacity_loss=0)
    lower = {**wider, "standard": (2, 3), "combined": (2, 3)}
    assert not _safe_wider(parent, lower, allowed_capacity_loss=0)
    assert _safe_wider(parent, lower, allowed_capacity_loss=2)
