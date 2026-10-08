"""G219 两摸互斥结算及两摸墙余边界的定向回归。"""

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

import json

import g196_three_draw_competing_route_pilot as g196
import g219_two_draw_settlement_route as g219


def test_optional_hu_is_mutually_exclusive_and_weighted() -> None:
    """先摸可胡时只能取立即胡或继续之一，不能把两次胡分相加。"""
    search = object.__new__(g219.ModeSearch)
    branches = [
        (1, g196.Value(plain=16, depth1=16), g196.Value(special=24, depth2=24)),
        (1, None, g196.Value(special=8, depth2=8)),
    ]
    full, continued = search.value(branches, 1.0)
    assert full.plain == 0
    assert full.special == 16
    assert full.total == 16
    assert continued == 1
    half, continued = search.value(branches, 0.5)
    assert half.plain == 8
    assert half.special == 2
    assert half.total == 10
    assert continued == 0


def test_two_draw_wall_boundary_recovers_27_tile_official_window() -> None:
    """三摸工具的 32 张边界不能误排墙余 27 张的合法两摸窗口。"""
    row = next(item for item in g219.selected_rows()
               if item["room"] == "a_7fae66b4d5cd" and item["round_no"] == 2)
    batch = json.loads((g219.g217.G61 / "result.json").read_text(encoding="utf-8"))
    result = g219.one(row, batch, {})
    assert result["wall_remaining"] == 27
    assert result["status"] == "complete"
    assert all(result["arms"][key]["modes"][mode]["values"][str(weight)]["value"]["total"] >= 0
               for key in result["arms"] for mode in g219.MODES for weight in g219.WEIGHTS)
