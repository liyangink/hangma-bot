"""G14 两窗口压力测试只允许静态保白弃牌，不把条件未来牌当线上事实。"""

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

from g14_novel_next_draw_stress import _best_second


def test_second_discard_keeps_white_and_returns_natural_metrics():
    full = Counter("1w 2w 3w 4w 5w 6w 7w 8w 9w 1b 2b 3b 白 东".split())
    best = _best_second(full, 0, 1)
    assert best is not None
    assert best["action"].startswith("discard:")
    assert best["action"] != "discard:白"
    assert isinstance(best["natural_draws_needed"], int)
    assert isinstance(best["natural_physical_tile_types"], int)
