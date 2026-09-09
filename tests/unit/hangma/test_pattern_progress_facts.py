"""公开规则入口的分牌型进度事实：同一等待手牌，不引入第二套向听数学。"""

from dataclasses import replace
import unittest
from unittest import mock

from hangma_bot.hangma import hand_analysis
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import CandidateFactKind, CandidateFacts
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import PlayerObservation, PublicDiscard, PublicMeld, RulePublicState


def _tiles(codes):
    return tuple(Tile(code) for code in codes.split())


def _observation(hand="1w 2w 3w 4w 5w 6w 7w 8w 9w 1b 2b 3b 4t", **updates):
    observation = PlayerObservation(
        game_id="pattern-progress", seat=0, round_no=1, snapshot_seq=10,
        phase="draw", dealer_seat=0, turn_seat=0, responding_seats=(),
        my_hand=_tiles(hand), drawn_tile=Tile("4t"),
        discards=((), (), (), ()), melds=((), (), (), ()),
        hand_counts=(13, 13, 13, 13), last_discard=None,
        remaining_tile_count=60, scores=(0, 0, 0, 0),
        rule_state=RulePublicState(Tile("白"), False, 0, False), public_history=(),
    )
    return replace(observation, **updates)


def _response(hand, code, phase="response_peng", **updates):
    return _observation(
        hand, phase=phase, drawn_tile=None, turn_seat=3,
        responding_seats=(0,), last_discard=PublicDiscard(3, Tile(code), 9),
        **updates,
    )


class PatternProgressFactsTests(unittest.TestCase):
    """只通过 HangmaRules.analyze 验证生产事实及故障边界。"""

    def setUp(self):
        self.rules = HangmaRules(RuleConfig("pattern-progress-test", 1, False))

    def facts(self, observation, action_key):
        return next(
            candidate.facts for candidate in self.rules.analyze(observation).legal_candidates
            if candidate.action_key == action_key
        )

    def assert_waiting_facts(self, facts, waiting_hand, melds):
        summary = hand_analysis.analyse_hand(tuple(waiting_hand), melds)
        self.assertIs(facts.fact_kind, CandidateFactKind.HAND_PROGRESS)
        self.assertEqual(facts.standard_shanten_after, summary.standard_shanten)
        self.assertEqual(facts.seven_pairs_shanten_after, summary.chiitoi_shanten)
        self.assertEqual(facts.shanten_after, summary.shanten)

    def test_discard_retains_distinct_seven_pairs_progress(self):
        """七对已听而普通型尚未听，不能把综合向听复制到两个牌型。"""
        observation = _observation(
            "1w 1w 3w 3w 5w 5w 7b 7b 9b 9b 东 东 南", drawn_tile=Tile("西")
        )
        facts = self.facts(observation, "discard:西")
        self.assert_waiting_facts(facts, observation.my_hand, 0)
        self.assertEqual(facts.seven_pairs_shanten_after, 0)
        self.assertGreater(facts.standard_shanten_after, 0)

    def test_response_pass_uses_current_hand_without_claimed_tile(self):
        observation = _response("1w 1w 3w 3w 5w 5w 7b 7b 9b 9b 东 东 南", "南")
        facts = self.facts(observation, "pass")
        self.assert_waiting_facts(facts, observation.my_hand, 0)
        self.assertEqual(facts.seven_pairs_shanten_after, 0)
        self.assertIsNone(facts.best_followup_discard)

    def test_claims_use_existing_best_followup_and_exclude_seven_pairs(self):
        """吃碰后只标注既有最佳后续弃牌的普通型，不改变原弃牌选择。"""
        cases = (
            ("5w 5w 1t 2t 3t 4t 5t 6t 7t 8t 9t 2b 3b", "5w", "response_peng", "peng:5w", ("5w", "5w"), "2b"),
            ("1w 2w 1t 2t 3t 4t 5t 6t 7t 8t 9t 2b 2b", "3w", "response_chi", "chi:1w,2w,3w", ("1w", "2w"), "1t"),
        )
        for hand, claimed, phase, key, removed, expected_discard in cases:
            with self.subTest(action=key):
                observation = _response(hand, claimed, phase)
                facts = self.facts(observation, key)
                self.assertEqual(facts.best_followup_discard, expected_discard)
                waiting = list(observation.my_hand)
                for code in (*removed, expected_discard):
                    waiting.remove(Tile(code))
                self.assert_waiting_facts(facts, waiting, 1)
                self.assertEqual(facts.standard_shanten_after, 0)
                self.assertIsNone(facts.seven_pairs_shanten_after)

    def test_all_gang_kinds_use_pre_replacement_hand(self):
        """暗杠、明杠、补杠均不臆造补牌；补杠不额外增加副露数。"""
        existing_peng = PublicMeld(0, "peng", _tiles("9w 9w 9w"), 2)
        cases = (
            (_observation("9w 9w 9w 9w 1t 2t 3t 4t 5t 6t 7t 8t 9t", drawn_tile=Tile("西")), "gang:concealed:9w"),
            (_response("9w 9w 9w 1t 2t 3t 4t 5t 6t 7t 8t 9t 西", "9w"), "gang:exposed:9w"),
            (_observation("9w 1t 2t 3t 4t 5t 6t 7t 8t 9t", drawn_tile=Tile("西"), melds=((existing_peng,), (), (), ()), hand_counts=(10, 13, 13, 13)), "gang:added:9w"),
        )
        for observation, key in cases:
            with self.subTest(action=key):
                facts = self.facts(observation, key)
                self.assert_waiting_facts(facts, _tiles("1t 2t 3t 4t 5t 6t 7t 8t 9t 西"), 1)
                self.assertEqual(facts.standard_shanten_after, 0)
                self.assertIsNone(facts.seven_pairs_shanten_after)
                self.assertTrue(facts.replacement_draw_unknown)

    def test_open_hand_discard_and_pass_keep_seven_pairs_inapplicable(self):
        meld = PublicMeld(0, "peng", _tiles("9w 9w 9w"), 2)
        observation = _observation(
            "1t 2t 3t 4t 5t 6t 7t 8t 9t 西", drawn_tile=Tile("南"),
            melds=((meld,), (), (), ()), hand_counts=(10, 13, 13, 13),
        )
        self.assert_waiting_facts(self.facts(observation, "discard:南"), observation.my_hand, 1)
        response = replace(observation, drawn_tile=None, phase="response_peng", turn_seat=3,
                           responding_seats=(0,), last_discard=PublicDiscard(3, Tile("东"), 9))
        self.assert_waiting_facts(self.facts(response, "pass"), observation.my_hand, 1)

    def test_hu_and_legacy_unknown_do_not_fabricate_pattern_progress(self):
        facts = self.facts(_observation(), "hu")
        legacy = CandidateFacts(CandidateFactKind.HAND_PROGRESS, 0)
        for item in (facts, legacy):
            self.assertIsNone(item.standard_shanten_after)
            self.assertIsNone(item.seven_pairs_shanten_after)

    def test_failed_analysis_and_emergency_do_not_fabricate_pattern_progress(self):
        with mock.patch.object(hand_analysis, "analyse_hand", side_effect=ValueError("牌型分析故障注入")):
            analysis = self.rules.analyze(_observation())
        failed = [candidate.facts for candidate in analysis.legal_candidates
                  if candidate.facts and candidate.facts.fact_kind is CandidateFactKind.ANALYSIS_FAILED]
        self.assertTrue(failed)
        for facts in failed:
            self.assertIsNone(facts.standard_shanten_after)
            self.assertIsNone(facts.seven_pairs_shanten_after)
        self.assertIsNotNone(analysis.emergency_candidate)
        self.assertIsNone(analysis.emergency_candidate.facts)


if __name__ == "__main__":
    unittest.main()
