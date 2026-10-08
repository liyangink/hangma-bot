"""G22 物理不可叫证明的边界；数牌第四张仍可能被下家吃。"""

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

from g22_certified_uncallable_screen import safe
from hangma_bot.hangma.internal_types import TILE_INDEX


def _unknown(**amounts):
    values = [4] * 34
    for code, amount in amounts.items():
        values[TILE_INDEX[code]] = amount
    return tuple(values)


def test_single_unknown_honor_cannot_be_ponged_or_chowed():
    assert safe("东", _unknown(东=1))


def test_fourth_suited_tile_can_still_be_chowed():
    assert not safe("5w", _unknown(**{"5w": 0}))


def test_suited_tile_with_every_chow_path_blocked_is_uncallable():
    assert safe("5w", _unknown(**{"5w": 1, "3w": 0, "4w": 0,
                                     "6w": 0, "7w": 0}))


def test_white_is_excluded_from_d1_preference():
    assert not safe("白", _unknown(白=0))
