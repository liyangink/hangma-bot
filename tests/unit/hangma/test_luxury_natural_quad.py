"""用户确认的豪七对边界：白板能补对子，不能补出豪华四张（2026-09-09）。"""

import pytest

from hangma_bot.hangma.hand_analysis import win_split
from hangma_bot.kernel.actions import Tile


@pytest.mark.parametrize("group,luxury", [
    (("1w", "1w", "1w", "白"), 0),
    (("1w", "1w", "白", "白"), 0),
    (("1w", "白", "白", "白"), 0),
    (("1w", "1w", "1w", "1w"), 1),
    (("白", "白", "白", "白"), 1),
])
def test_white_can_complete_pairs_but_cannot_complete_a_luxury_group(group, luxury):
    """五个自然对子加四张，分别区分可胡、自然四张和四白自配。"""
    pairs = tuple(code for code in ("2w", "3w", "4w", "5w", "6w") for _ in range(2))
    split = win_split(tuple(Tile(code) for code in group + pairs), 0)
    assert split is not None and split.branch == "七对"
    assert split.luxury_pairs == luxury
