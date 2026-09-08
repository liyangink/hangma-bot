"""分组数学回归：按具体成牌见证验证公共输出，不绑定求解器实现。"""

import pytest

from hangma_bot.hangma.hand_analysis import analyse_hand, any_tile_win, win_split
from hangma_bot.kernel.actions import Tile


@pytest.mark.parametrize(
    "codes,meld_set_count",
    (
        (
            "1w 2w 4b 5b 6b 7t 8t 9t 东 东 东 东 白",
            0,
        ),
        (
            "1w 2w 9w 9w 9w 9w 白",
            2,
        ),
    ),
    ids=("reserve_white_across_groups", "reserve_white_within_one_suit"),
)
def test_reserving_white_for_quad_recognizes_natural_tile_wait(
    codes: str, meld_set_count: int
) -> None:
    """白应留给同种四张的刻加将；12w等3w，不能被高估为一向听。

    摸3w的见证：123w，加其余完整面子，再以同种四张和白组成刻与将。
    单次自然进张已经能成牌，因此摸前必须是0向听；只听3w或白。
    """
    hand = tuple(Tile(code) for code in codes.split())

    summary = analyse_hand(hand, meld_set_count)

    assert not summary.is_win
    assert summary.standard_shanten == 0
    assert summary.shanten == 0
    assert [(tile.code, tile.shanten_after) for tile in summary.useful_tiles] == [
        ("3w", -1),
        ("白", -1),
    ]
    assert not any_tile_win(hand, meld_set_count)

    completed = hand + (Tile("3w"),)
    assert analyse_hand(completed, meld_set_count).is_win
    split = win_split(completed, meld_set_count)
    assert split is not None
    assert split.branch == "平胡"
    assert sum(label.startswith("将:") for label in split.evidence) == 1
    assert sum(
        label.startswith(("刻子:", "顺子:")) for label in split.evidence
    ) == 4 - meld_set_count


def test_four_white_seven_pairs_keep_summary_and_split_consistent() -> None:
    """五个自然对加四白同时成标准型与七对，分支优先级和豪华数不变。"""
    hand = tuple(
        Tile(code)
        for code in "1w 1w 3w 3w 5w 5w 7w 7w 9w 9w 白 白 白 白".split()
    )

    summary = analyse_hand(hand, 0)
    split = win_split(hand, 0)

    assert summary.is_win
    assert summary.standard_shanten == -1
    assert summary.chiitoi_shanten == -1
    assert summary.shanten == -1
    assert summary.whites_held == 4
    assert summary.useful_tiles == ()
    assert split is not None
    assert split.branch == "七对"
    assert split.luxury_pairs == 1
    assert split.whites_held == 4
    assert sum(label.startswith("对:") for label in split.evidence) == 7
    # 摸第四白前，五个自然对加三白可接任意牌；v23 四白同样可以爆头。
    assert any_tile_win(hand[:-1], 0)
