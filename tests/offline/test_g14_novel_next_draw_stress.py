"""G14 两窗口压力测试只允许静态保白弃牌，不把条件未来牌当线上事实。"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[2] /
                       "review/freematch-deep-dive-20260925"))

from g14_novel_next_draw_stress import _best_second


def test_second_discard_keeps_white_and_returns_natural_metrics():
    full = Counter("1w 2w 3w 4w 5w 6w 7w 8w 9w 1b 2b 3b 白 东".split())
    best = _best_second(full, 0, 1)
    assert best is not None
    assert best["action"].startswith("discard:")
    assert best["action"] != "discard:白"
    assert isinstance(best["natural_draws_needed"], int)
    assert isinstance(best["natural_physical_tile_types"], int)
