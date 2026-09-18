"""真实公开计数歧义的对称回归：普通型未知不污染已知七对与综合事实。"""

from dataclasses import replace

from hangma_bot.hangma import HangmaRules
from hangma_bot.hangma.interface import CandidateFactKind, RuleCompleteness
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import PublicMeld

from .test_pattern_progress_facts import _observation, _tiles


def test_standard_only_unknown_count_preserves_seven_pairs_and_combined_facts():
    """六对单南只听南/白；普通型另需万子，缺少吃牌来源只使普通型计数未知。"""
    observation = _observation(
        "1w 1w 3w 3w 5w 5w 7b 7b 9b 9b 东 东 南", drawn_tile=Tile("西")
    )
    # 座位 2 已吃 123w，座位 1 牌河同时有 1w/2w。缺少事件来源证据，
    # 无法辨明吃牌与哪张弃牌重叠；两种牌均非七对或综合听牌进张。
    observation = replace(
        observation,
        discards=((), _tiles("1w 2w"), (), ()),
        melds=((), (), (PublicMeld(2, "chi", _tiles("1w 2w 3w"), 1),), ()),
        hand_counts=(14, 13, 10, 13),
    )
    rules = HangmaRules(RuleConfig("pattern-useful-symmetry", 1, False))
    analysis = rules.analyze(observation)
    facts = next(c.facts for c in analysis.legal_candidates if c.action_key == "discard:西")

    assert facts.fact_kind is CandidateFactKind.HAND_PROGRESS
    assert facts.completeness is RuleCompleteness.COMPLETE
    assert facts.shanten_after == facts.seven_pairs_shanten_after == 0
    assert facts.standard_shanten_after == 3
    # 2026-09-18 口径修订：缺供牌证据的吃副露不再使普通型计数未知，
    # 改为「不扣重叠」的保守数值；七对与该副露无关，事实不变。
    assert facts.standard_useful_tiles is not None
    assert facts.seven_pairs_useful_tiles is not None
    expected = {"南": 3, "白": 4}
    assert {tile.code: tile.remaining_estimate for tile in facts.useful_tiles} == expected
    assert {tile.code: tile.remaining_estimate for tile in facts.seven_pairs_useful_tiles} == expected
    assert facts.pattern_progress_note is None
