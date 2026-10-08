"""G220 缺失抓打资格不能默认为自由续打的定向回归。"""

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

import g220_future_qualification_audit as g220


def test_missing_future_observation_remains_possible_restriction() -> None:
    """完整分母的自由下界、受限上界必须把缺观察保留下来。"""
    rows = [
        ("room-a", "reconstructed/free"),
        ("room-a", "reconstructed/free"),
        ("room-b", "reconstructed/restricted"),
        ("room-b", "unreconstructed/eventual_win"),
        ("room-b", "terminal/other_win"),
    ]
    result = g220.summarize(rows)
    assert result["next_draw"] == 4
    assert result["mode_reconstructed"] == 3
    assert result["free_among_reconstructed"] == 2 / 3
    assert result["free_share_lower_bound_among_all_next_draws"] == 1 / 2
    assert result["restricted_share_upper_bound_among_all_next_draws"] == 1 / 2
    assert result["events"]["unreconstructed/eventual_win"] == 1


def test_terminal_before_next_draw_is_not_a_qualification_observation() -> None:
    """他家先胡是竞争终点，不得混入抓打资格分母。"""
    result = g220.summarize([
        ("room-a", "terminal/other_win"),
        ("room-a", "reconstructed/free"),
    ])
    assert result["windows"] == 2
    assert result["next_draw"] == 1
    assert result["free_share_lower_bound_among_all_next_draws"] == 1.0
