"""N-1 回归：评分上下文 combined_codes 的摸牌双计归一化。

官方快照实测形态（my_hand 含刚摸牌，长度 = 14−3×副露数）与契约形态
（不含，长度 = 13−3×副露数）并存；build_context 必须与 hangma 引擎
_concealed_without_drawn 同口径归一化，否则幻影副本进入评分上下文。
"""
from __future__ import annotations

from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.observation import PublicMeld
from hangma_bot.policy.evaluation import build_context

from .support import make_observation

WEALTH = Tile("白")

NUMBERS = ["1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w"]


def _meld(kind: str, codes) -> PublicMeld:
    return PublicMeld(
        seat=0, kind=kind, tiles=tuple(Tile(c) for c in codes), from_seat=None
    )


def _obs(hand_codes, drawn, melds=(), seat=0):
    row = (melds,) if melds else ()
    return make_observation(
        seat=seat,
        my_hand=tuple(Tile(c) for c in hand_codes),
        drawn_tile=Tile(drawn) if drawn else None,
        melds=((), row, (), ()) if seat == 1 else (row, (), (), ()),
    )


def test_contract_form_counts_drawn_once() -> None:
    """契约形态：my_hand 不含刚摸牌（13−3×副露数）→ combined = 手牌 + 摸牌。"""

    hand = NUMBERS + ["东", "东", "南", "白"]  # 13 张
    ctx = build_context(_obs(hand, drawn="白"))
    assert ctx.combined_codes == tuple(hand) + ("白",)  # 摸牌置尾、只计一次
    assert ctx.combined_codes.count("白") == 2  # 手牌 1 张 + 刚摸 1 张


def test_official_form_does_not_double_count_drawn() -> None:
    """N-1 回归：官方形态（my_hand 已含刚摸牌，长度 = 14−3×副露数）
    与契约形态产生完全相同的 combined_codes（幻影副本不得进入评分上下文）。"""

    hand = NUMBERS + ["东", "东", "南", "白"]  # 13 张
    contract = build_context(_obs(hand, drawn="白"))
    official_hand = hand + ["白"]  # 官方把刚摸的白并入 my_hand 末尾
    official = build_context(_obs(official_hand, drawn="白"))
    assert official.combined_codes == contract.combined_codes
    assert official.combined_codes.count("白") == 2  # 无幻影第三张


def test_official_form_with_meld_normalized() -> None:
    """带副露的官方形态同样归一化（长度判据 14−3×副露数）。"""

    meld = _meld("peng", ("2b", "2b", "2b"))
    hand_contract = NUMBERS + ["东"]  # 13−3×1 = 10 张（不含摸牌）
    contract = build_context(_obs(hand_contract, drawn="东", melds=meld, seat=1))
    official_hand = hand_contract + ["东"]  # 10+1 = 11 = 14−3×1（官方含摸牌形态）
    official = build_context(_obs(official_hand, drawn="东", melds=meld, seat=1))
    assert official.combined_codes == contract.combined_codes
    assert official.combined_codes.count("东") == 2  # 手牌 1 + 刚摸 1，无幻影


def test_no_drawn_leaves_hand_untouched() -> None:
    hand = NUMBERS + ["东", "东", "南", "白"]
    ctx = build_context(_obs(hand, drawn=""))
    assert ctx.combined_codes == tuple(hand)