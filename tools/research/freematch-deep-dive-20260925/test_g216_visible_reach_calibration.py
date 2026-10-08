"""G216 首后继优先级回归：到达摸牌窗口先于窗口内胡牌选择。"""

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

import g216_visible_reach_calibration as reach


def test_draw_arrival_precedes_hu_chosen_at_same_window() -> None:
    hand = {"is_draw": False, "winner_seat": 0}
    assert reach.first_successor([
        {"phase": "response_peng", "chosen_action": "pass"},
        {"phase": "draw", "chosen_action": "hu"},
    ], hand, 0) == "next_own_draw"


def test_claim_precedes_later_draw_and_terminal_is_unique() -> None:
    hand = {"is_draw": False, "winner_seat": 1}
    assert reach.first_successor([
        {"phase": "response_peng", "chosen_action": "peng:2w"},
        {"phase": "draw", "chosen_action": "discard:5b"},
    ], hand, 0) == "own_claim"
    assert reach.first_successor([
        {"phase": "response_peng", "chosen_action": "pass"},
    ], hand, 0) == "other_win"
    assert reach.first_successor([], {"is_draw": True, "winner_seat": None}, 0) == "draw"
