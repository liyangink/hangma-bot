"""自然面子分段缺口必须真实消费牌，且不能把白板当自然牌。"""

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

from collections import Counter
from pathlib import Path
import sys


sys.path.insert(0, str(_project_file(_PROJECT_ROOT, Path(__file__).resolve().parents[2] /
                       "review/freematch-deep-dive-20260925")))

from g14_disjoint_natural_meld_profile import _profile


def test_two_disjoint_natural_melds_need_no_future_tile():
    hand = Counter({"1w": 2, "2w": 2, "3w": 2})
    assert _profile(hand, 2) == (0, 0)


def test_one_missing_natural_tile_cannot_be_replaced_by_white():
    hand = Counter({"1w": 2, "2w": 2, "3w": 1, "白": 1})
    assert _profile(hand, 2) == (0, 1)
