"""自然面子分段缺口必须真实消费牌，且不能把白板当自然牌。"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[2] /
                       "review/freematch-deep-dive-20260925"))

from g14_disjoint_natural_meld_profile import _profile


def test_two_disjoint_natural_melds_need_no_future_tile():
    hand = Counter({"1w": 2, "2w": 2, "3w": 2})
    assert _profile(hand, 2) == (0, 0)


def test_one_missing_natural_tile_cannot_be_replaced_by_white():
    hand = Counter({"1w": 2, "2w": 2, "3w": 1, "白": 1})
    assert _profile(hand, 2) == (0, 1)
