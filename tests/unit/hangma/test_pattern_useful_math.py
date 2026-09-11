"""分牌型有效牌的数学契约：保留已有计算，不改变综合牌效或扩张搜索。"""

from collections import Counter
from unittest import mock

import pytest

from hangma_bot.hangma import hand_analysis
from hangma_bot.hangma.internal_types import TILE_ORDER
from hangma_bot.kernel.actions import Tile


def _tiles(text):
    return tuple(Tile(code) for code in text.split())


def _values(entries):
    return {entry.code: entry.shanten_after for entry in entries}


def test_seven_pairs_progress_survives_unchanged_best_shanten():
    """普通型已听时，配成一个对子仍应记录七对进度，即使综合向听不变。"""
    result = hand_analysis.analyse_hand(_tiles("1w 2w 3w 4w 5w 6w 7w 8w 9w 1b 2b 3b 4t"), 0)
    assert (result.standard_shanten, result.chiitoi_shanten, result.shanten) == (0, 6, 0)
    assert "1w" not in _values(result.useful_tiles)
    assert "1w" not in _values(result.standard_useful_tiles)
    assert _values(result.seven_pairs_useful_tiles)["1w"] == 5
    assert _values(result.standard_useful_tiles) == {"4t": -1, "白": -1}
    assert _values(result.seven_pairs_useful_tiles)["白"] == 5


@pytest.mark.parametrize("text,melds", [
    ("1w 2w 3w 4w 5w 6w 7w 8w 9w 1b 2b 3b 4t", 0),
    ("1w 1w 3w 3w 5w 5w 7b 7b 9b 9b 东 东 白", 0),
    ("1w 2w 3w 4w 5w 6w 7b 8b 9b 白 白 白 白", 0),
    ("1w 1w 1w 1w 3w 3w 5b 5b 7b 7b 9t 9t 东", 0),
    ("1t 2t 3t 4t 5t 6t 7t 8t 9t 西", 1),
])
def test_each_reported_progress_matches_actual_draw_analysis(text, melds):
    """由公开入口实际摸入每张牌，检查集合完整性、对应牌型向听和规范顺序。"""
    hand = _tiles(text)
    summary = hand_analysis.analyse_hand(hand, melds)
    counts = Counter(tile.code for tile in hand)
    expected_standard, expected_seven_pairs = {}, {}
    for code in TILE_ORDER:
        if counts[code] == 4:
            continue
        actual = hand_analysis.analyse_hand(hand + (Tile(code),), melds)
        if actual.standard_shanten < summary.standard_shanten:
            expected_standard[code] = actual.standard_shanten
        if melds == 0 and actual.chiitoi_shanten < summary.chiitoi_shanten:
            expected_seven_pairs[code] = actual.chiitoi_shanten
    assert _values(summary.standard_useful_tiles) == expected_standard
    assert tuple(entry.code for entry in summary.standard_useful_tiles) == tuple(expected_standard)
    if melds:
        assert summary.seven_pairs_useful_tiles is None
    else:
        assert _values(summary.seven_pairs_useful_tiles) == expected_seven_pairs
        assert tuple(entry.code for entry in summary.seven_pairs_useful_tiles) == tuple(expected_seven_pairs)


@pytest.mark.parametrize("text,exhausted", [
    ("1w 2w 3w 4w 5w 6w 7b 8b 9b 白 白 白 白", "白"),
    ("1w 1w 1w 1w 3w 3w 5b 5b 7b 7b 9t 9t 东", "1w"),
])
def test_fifth_tile_excluded_from_all_useful_sets(text, exhausted):
    summary = hand_analysis.analyse_hand(_tiles(text), 0)
    for entries in (summary.useful_tiles, summary.standard_useful_tiles, summary.seven_pairs_useful_tiles):
        assert exhausted not in _values(entries)


def test_computed_empty_set_is_not_unavailable_or_copied_white_insurance():
    """空暗牌是数学输入边界而非合法牌局：单摸一张不能形成对子。

    原综合有效牌的白板保险仍保留；新七对结果必须采用真实数学，返回已算空集。
    """
    summary = hand_analysis.analyse_hand((), 0)
    assert _values(summary.useful_tiles) == {"白": 5}
    assert summary.seven_pairs_useful_tiles == ()
    assert _values(summary.standard_useful_tiles)["白"] == 12


def test_winning_hand_does_not_start_another_draw_search():
    hand = _tiles("1w 2w 3w 4w 5w 6w 7w 8w 9w 1b 2b 3b 4t 4t")
    with mock.patch.object(hand_analysis, "_need_std", wraps=hand_analysis._need_std) as calls:
        summary = hand_analysis.analyse_hand(hand, 0)
    assert summary.is_win
    assert summary.useful_tiles == ()
    assert summary.standard_useful_tiles is None
    assert summary.seven_pairs_useful_tiles is None
    assert calls.call_count == 1


@pytest.mark.parametrize("text,melds,expected_calls", [
    ("1w 2w 3w 4w 5w 6w 7w 8w 9w 1b 2b 3b 4t", 0, 35),
    ("1w 2w 3w 4w 5w 6w 7b 8b 9b 白 白 白 白", 0, 34),
    ("1t 2t 3t 4t 5t 6t 7t 8t 9t 西", 1, 35),
])
def test_no_additional_standard_math_calls(text, melds, expected_calls):
    """维持原调用上界：当前手牌一次，加每种物理可摸牌各一次。"""
    with mock.patch.object(hand_analysis, "_need_std", wraps=hand_analysis._need_std) as calls:
        hand_analysis.analyse_hand(_tiles(text), melds)
    assert calls.call_count == expected_calls


@pytest.mark.parametrize("text,melds,expected", [
    ("1w 2w 3w 4w 5w 6w 7w 8w 9w 1b 2b 3b 4t", 0,
     (False, 0, 6, 0, (("4t", -1), ("白", -1)), 0,
      ("标准型向听 0", "七对向听 6", "最优向听 0", "手留白板 0 张"))),
    ("1t 2t 3t 4t 5t 6t 7t 8t 9t 西", 1,
     (False, 0, None, 0, (("西", -1), ("白", -1)), 0,
      ("标准型向听 0", "七对向听 N/A(有副露)", "最优向听 0", "手留白板 0 张"))),
])
def test_legacy_summary_fields_remain_identical(text, melds, expected):
    """固定修改前捕获的原字段与人读证据，避免新事实改变旧消费方输入。"""
    summary = hand_analysis.analyse_hand(_tiles(text), melds)
    assert (
        summary.is_win, summary.standard_shanten, summary.chiitoi_shanten, summary.shanten,
        tuple((entry.code, entry.shanten_after) for entry in summary.useful_tiles),
        summary.whites_held, summary.evidence,
    ) == expected
