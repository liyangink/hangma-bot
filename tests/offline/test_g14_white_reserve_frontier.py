"""G14 白板保留前沿：保留与百搭进度分开，逐牌容量不冒充概率。"""

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

from g14_white_reserve_frontier import _frontier


def test_reserving_white_increases_natural_completion_need():
    # 四个自然顺子、无自然将；白可立即补将，保留白则还须自然成将。
    hand = Counter("1w 2w 3w 4w 5w 6w 7w 8w 9w 1b 2b 3b 白".split())
    result = _frontier(hand, 0, Counter(), Counter(), "东")
    assert result["whites_held"] == 1
    assert result["standard_natural_draws_needed_by_reserved_whites"] == [1, 2]
    assert result["all_whites_reserved_natural_tile_types"] > 0
    assert "白" not in result["all_whites_reserved_useful_by_tile"]
    assert result["all_whites_reserved_public_capacity_upper"] >= (
        result["all_whites_reserved_natural_tile_types"])
