"""分牌型活进张的公开事实与局部缺证据隔离。"""
from dataclasses import replace

from hangma_bot.hangma import HangmaRules
from hangma_bot.hangma.interface import RuleCompleteness
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import PublicMeld
from .test_pattern_progress_facts import _observation, _tiles


def candidate(obs,key='discard:西'):
    rules=HangmaRules(RuleConfig('pattern-useful-test',1,False))
    return next(c for c in rules.analyze(obs).legal_candidates if c.action_key==key)


def test_progress_of_a_slower_pattern_is_visible_without_changing_best_wait():
    obs=_observation('1w 2w 3w 4w 5w 6w 7w 8w 9w 1b 2b 3b 4t',drawn_tile=Tile('西'))
    facts=candidate(obs).facts
    assert facts.shanten_after==facts.standard_shanten_after==0
    assert facts.seven_pairs_shanten_after==6
    assert {t.code for t in facts.useful_tiles}=={'4t','白'}
    assert {t.code for t in facts.standard_useful_tiles}=={'4t','白'}
    assert '1w' in {t.code for t in facts.seven_pairs_useful_tiles}
    assert next(t.remaining_estimate for t in facts.seven_pairs_useful_tiles if t.code=='1w')==3


def test_new_pattern_unknown_count_does_not_poison_complete_old_facts():
    obs=_observation('1w 2w 3w 4w 5w 6w 7w 8w 9w 1b 2b 3b 4t',drawn_tile=Tile('西'))
    ambiguous=replace(obs,discards=((),_tiles('1w 2w'),(),()),
        melds=((),(),(PublicMeld(2,'chi',_tiles('1w 2w 3w'),1),),()),hand_counts=(14,13,10,13))
    facts=candidate(ambiguous).facts
    assert facts.completeness is RuleCompleteness.COMPLETE
    assert facts.shanten_after==0
    assert {t.code for t in facts.useful_tiles}=={'4t','白'}
    assert facts.standard_useful_tiles is not None
    assert facts.seven_pairs_shanten_after==6
    # 2026-09-18 口径修订：缺供牌证据的吃副露不再把任何牌种标为未知（改为不扣重叠），
    # 因此七对推进牌也照常给出保守数值，且不再有「计数未知」备注。
    assert facts.seven_pairs_useful_tiles is not None
    assert facts.pattern_progress_note is None


def test_exhausted_pattern_tiles_are_zero_not_unknown_or_a_fifth_copy():
    obs=_observation('1w 1w 3w 3w 5w 5w 2b 2b 4b 4b 6b 6b 8t',drawn_tile=Tile('9t'))
    obs=replace(obs,discards=(_tiles('白 8t'),_tiles('白 8t'),_tiles('白 8t'),_tiles('白 东')),
                remaining_tile_count=75)
    facts=candidate(obs,'discard:9t').facts
    assert facts.seven_pairs_useful_tiles is not None
    assert {t.code:t.remaining_estimate for t in facts.seven_pairs_useful_tiles}=={'8t':0,'白':0}
    assert facts.pattern_progress_note is None
