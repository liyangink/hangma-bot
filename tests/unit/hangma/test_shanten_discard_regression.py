"""自由对战真实手牌的普通型向听回归；数学见证不依赖搜索内部状态。

样本来源：review/policy-replay-2026-09-06/README.md §3/§4。
续打见证只证明手牌数学上界，不声称官方牌墙或公开剩余张数允许兑现。
"""

from collections import Counter
from itertools import permutations

import pytest

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.hand_analysis import analyse_hand, win_split
from hangma_bot.hangma.interface import CandidateFactKind, RuleCompleteness
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import PlayerObservation, RulePublicState


PAIR_CASE = "8w 3b 5t 4b 2b 7b 4t 南 南 发 7t 6w 9w 白"
SEVEN_PAIRS_CASE = "5w 6w 1b 1b 5b 7b 8b 8b 9b 5t 6t 7t 7t 东"


def _tiles(text):
    return tuple(Tile(code) for code in text.split())


def _discard(hand, code):
    remaining = list(hand)
    remaining.remove(Tile(code))
    return tuple(remaining)


def _permute_suits(hand, suit_order):
    mapping = dict(zip("wbt", suit_order))
    return tuple(
        Tile(tile.code[:-1] + mapping[tile.code[-1]])
        if tile.code[-1] in mapping else tile
        for tile in hand
    )


@pytest.mark.parametrize("suit_order", tuple(permutations("wbt")))
def test_real_pair_case_keeps_three_draw_completion_bound(suit_order):
    """三次进张即能组成四面子一对，不能把保留南对算成三向听。"""
    hand = _permute_suits(_tiles(PAIR_CASE), suit_order)
    keep_pair = analyse_hand(_discard(hand, "发"), 0)
    break_pair = analyse_hand(_discard(hand, "南"), 0)
    assert keep_pair.standard_shanten <= 2
    assert break_pair.standard_shanten == 3
    assert keep_pair.standard_shanten < break_pair.standard_shanten


def test_pair_case_has_explicit_legal_completion_witness():
    """逐次摸舍保持张数和四张上限，终手由公开胡牌接口确认。"""
    waiting = _discard(_tiles(PAIR_CASE), "发")
    for draw, discard in (("7w", "7b"), ("7t", "6w")):
        drawn = waiting + (Tile(draw),)
        assert len(drawn) == 14
        assert max(Counter(tile.code for tile in drawn).values()) <= 4
        waiting = _discard(drawn, discard)
    final_hand = waiting + (Tile("7t"),)
    # 789w + 234b + 45白t（白作6t）+ 777t + 南南。
    expected = _tiles("7w 8w 9w 2b 3b 4b 4t 5t 白 7t 7t 7t 南 南")
    assert Counter(final_hand) == Counter(expected)
    assert max(Counter(final_hand).values()) <= 4
    split = win_split(final_hand, 0)
    assert split is not None and split.branch == "平胡"
    assert analyse_hand(_discard(_tiles(PAIR_CASE), "发"), 0).standard_shanten <= 2


@pytest.mark.parametrize("suit_order", tuple(permutations("wbt")))
def test_real_sequence_case_does_not_falsely_favor_seven_pairs(suit_order):
    """普通型至多两向听，不能因遗漏弃牌路径而让三向听七对显得更近。"""
    hand = _permute_suits(_discard(_tiles(SEVEN_PAIRS_CASE), "东"), suit_order)
    summary = analyse_hand(hand, 0)
    assert summary.standard_shanten <= 2
    assert summary.chiitoi_shanten == 3
    assert summary.standard_shanten < summary.chiitoi_shanten


def test_sequence_case_has_explicit_completion_witness():
    """摸 4w、7t、7t，舍多余 5b、8b 后组成四面子一对。"""
    waiting = _discard(_tiles(SEVEN_PAIRS_CASE), "东")
    for draw, discard in (("4w", "5b"), ("7t", "8b")):
        waiting = _discard(waiting + (Tile(draw),), discard)
    final_hand = waiting + (Tile("7t"),)
    # 456w + 11b + 789b + 567t + 777t，四张 7t 分属于顺子和刻子。
    expected = _tiles("4w 5w 6w 1b 1b 7b 8b 9b 5t 6t 7t 7t 7t 7t")
    assert Counter(final_hand) == Counter(expected)
    assert len(final_hand) == 14
    assert max(Counter(final_hand).values()) <= 4
    assert win_split(final_hand, 0) is not None


@pytest.mark.parametrize("text,discard", ((PAIR_CASE, "发"), (SEVEN_PAIRS_CASE, "东")))
def test_extra_available_tile_cannot_worsen_subset_distance(text, discard):
    """原手最多两张同种牌；移除一张不会改变紧缺四张的边界条件。

    子集的可用成牌路线也是母集可选路线，母集普通型向听不能更差。
    不对触及四张物理额度的任意手牌宣称无条件单调性。
    """
    hand = _discard(_tiles(text), discard)
    assert max(Counter(hand).values()) <= 2
    parent_distance = analyse_hand(hand, 0).standard_shanten
    for code in sorted({tile.code for tile in hand}):
        subset_distance = analyse_hand(_discard(hand, code), 0).standard_shanten
        assert parent_distance <= subset_distance, code


def test_rule_candidates_preserve_real_pair_progress_difference():
    """公开规则入口必须把保留南对的牌效优势交付策略，不能靠降级通过。"""
    full_hand = _tiles(PAIR_CASE)
    observation = PlayerObservation(
        game_id="shanten-discard-regression", seat=1, round_no=6,
        snapshot_seq=1542, phase="draw", dealer_seat=0, turn_seat=1,
        responding_seats=(), my_hand=_discard(full_hand, "白"),
        drawn_tile=Tile("白"), discards=((), (), (), ()), melds=((), (), (), ()),
        hand_counts=(13, 14, 13, 13), last_discard=None,
        remaining_tile_count=40, scores=(0, 0, 0, 0),
        rule_state=RulePublicState(wealth_god=Tile("白"), baotou=False,
                                   chain_count=0, catch_play=False),
        public_history=(),
    )
    rules = HangmaRules(RuleConfig(ruleset_version="shanten-discard-test", base_score=1,
                                  you_cai_bi_kao=False))
    analysis = rules.analyze(observation)
    assert analysis.completeness is RuleCompleteness.COMPLETE
    facts = {candidate.action_key: candidate.facts for candidate in analysis.legal_candidates}
    keep_pair, break_pair = facts["discard:发"], facts["discard:南"]
    for candidate in (keep_pair, break_pair):
        assert candidate is not None
        assert candidate.fact_kind is CandidateFactKind.HAND_PROGRESS
    assert keep_pair.shanten_after <= 2
    assert break_pair.shanten_after == 3
    assert keep_pair.shanten_after < break_pair.shanten_after
    # 此形中摸7t或南能推进普通型；原剪枝把这两种真实进张漏掉。
    assert {"7t", "南"} <= {entry.code for entry in keep_pair.useful_tiles}
