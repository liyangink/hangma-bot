"""自然两张牌连接的边界金例：只作结构探针，不替代生产胡牌判断。"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[2] /
                       "review/freematch-deep-dive-20260925"))

from g14_latent_natural_links_probe import _latent, _natural_pair_completions


def test_natural_pair_completions_cover_open_gap_pair_and_honor():
    after = Counter("4w 5w 4b 6b 西 西 白".split())
    # 4w/5w 可补 3w、6w；4b/6b 可补 5b；西西可补刻子。
    assert _natural_pair_completions(after) == {"3w", "6w", "5b", "西"}


def test_latent_support_excludes_immediate_useful_and_publicly_gone_tiles():
    after = Counter("4w 5w 4b 6b 西 西 白".split())
    facts = {"standard_useful_tiles": [
        {"code": "3w", "remaining_estimate": 4},
    ]}
    result = _latent(after, "discard:东", facts, Counter(), Counter({"5b": 2}))
    assert result == {"types": 3, "capacity_upper": 8,
                      "tile_upper": {"5b": 2, "6w": 4, "西": 2}}
    assert _latent(after, "discard:东", {"standard_useful_tiles": [
        {"code": "3w", "remaining_estimate": True}]}, Counter(), Counter()) is None
