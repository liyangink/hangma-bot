"""候选牌效事实（CandidateFacts）生产的契约与故障隔离测试。

只通过 HangmaRules.analyze 公开接口验证：事实种类、向听、有效牌、
最佳后续弃牌、杠补牌口径、剩余张数口径、紧急路径无事实与降级行为。
事实与 action_key 一一对应；契约依据 doc/implementation/interface-contracts.md
§4.1（2026-09-04 集成阶段契约收口）。
"""

from __future__ import annotations

import unittest
from unittest import mock

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import CandidateFactKind, RuleCompleteness
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import PlayerObservation, PublicDiscard, RulePublicState

WEALTH = Tile("白")


def _rule_state(**kw) -> RulePublicState:
    base = dict(wealth_god=WEALTH, baotou=False, chain_count=0, catch_play=False)
    base.update(kw)
    return RulePublicState(**base)


def make_observation(**kw) -> PlayerObservation:
    """构造合法 PlayerObservation；默认为座位 0 的摸牌出牌窗口。"""

    hand_codes = kw.pop(
        "hand_codes",
        ("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "2b", "3b", "4t"),
    )
    base = dict(
        game_id="g-facts",
        seat=0,
        round_no=1,
        snapshot_seq=10,
        phase="draw",
        dealer_seat=0,
        turn_seat=0,
        responding_seats=(),
        my_hand=tuple(Tile(c) for c in hand_codes),
        drawn_tile=None,
        discards=((), (), (), ()),
        melds=((), (), (), ()),
        hand_counts=(13, 13, 13, 13),
        last_discard=None,
        remaining_tile_count=60,
        scores=(0, 0, 0, 0),
        rule_state=_rule_state(),
        public_history=(),
    )
    base.update(kw)
    return PlayerObservation(**base)


def _rules() -> HangmaRules:
    return HangmaRules(RuleConfig(ruleset_version="facts-test", base_score=1, you_cai_bi_kao=False))


def _facts_by_key(analysis):
    return {candidate.action_key: candidate.facts for candidate in analysis.legal_candidates}


class FactsProductionContractTests(unittest.TestCase):
    """各动作族的事实种类与关键数值。"""

    def test_discard_candidates_carry_hand_progress_facts(self) -> None:
        """弃牌候选全部携带 HAND_PROGRESS：向听与有效牌来自规则引擎。"""

        observation = make_observation(drawn_tile=Tile("4t"))
        analysis = _rules().analyze(observation)
        by_key = _facts_by_key(analysis)

        self.assertEqual(analysis.completeness, RuleCompleteness.COMPLETE)
        for key, facts in by_key.items():
            if key.startswith("discard:"):
                self.assertIsNotNone(facts)
                self.assertIs(facts.fact_kind, CandidateFactKind.HAND_PROGRESS)
                self.assertIsInstance(facts.shanten_after, int)
                self.assertIsNone(facts.best_followup_discard)
                self.assertFalse(facts.replacement_draw_unknown)

    def test_discard_facts_match_hand_analysis_math(self) -> None:
        """具体数值锚点：打 1w 后向听 0，有效牌按剩余张数口径折算。"""

        observation = make_observation(drawn_tile=Tile("4t"))
        analysis = _rules().analyze(observation)
        facts = _facts_by_key(analysis)["discard:1w"]

        self.assertEqual(facts.shanten_after, 0)
        useful = {item.code: item.remaining_estimate for item in facts.useful_tiles}
        # 手牌 1w 被打出、无公开 1w：剩余估计 = 4 - 0 - 1(新公开) = 3。
        self.assertEqual(useful["1w"], 3)
        self.assertEqual(useful["白"], 4)

    def test_hu_candidate_facts_are_win_sentinel(self) -> None:
        """胡候选事实为 WIN：shanten_after=-1，不携带有效牌数值。"""

        observation = make_observation(drawn_tile=Tile("4t"))
        analysis = _rules().analyze(observation)
        hu = _facts_by_key(analysis)["hu"]

        self.assertIs(hu.fact_kind, CandidateFactKind.WIN)
        self.assertEqual(hu.shanten_after, -1)
        self.assertEqual(hu.useful_tiles, ())

    def test_pass_candidate_facts_describe_current_waiting_hand(self) -> None:
        """过候选给出当前等待牌效，不领取触发弃牌或模拟后续弃牌。"""

        observation = make_observation(
            phase="response_peng",
            responding_seats=(0,),
            turn_seat=2,
            drawn_tile=None,
            my_hand=tuple(Tile(c) for c in ("5w", "5w", "1t", "2t", "3t", "4t", "5t", "6t", "7t", "8t", "9t", "2b", "3b")),
            last_discard=PublicDiscard(seat=2, tile=Tile("5w"), seq=9),
        )
        analysis = _rules().analyze(observation)
        facts = _facts_by_key(analysis)["pass"]

        self.assertIs(facts.fact_kind, CandidateFactKind.HAND_PROGRESS)
        self.assertIsInstance(facts.shanten_after, int)
        self.assertIsNone(facts.best_followup_discard)

    def test_peng_facts_carry_best_followup_discard(self) -> None:
        """碰事实给出最佳合法后续弃牌与动作后向听。"""

        observation = make_observation(
            phase="response_peng",
            responding_seats=(0,),
            turn_seat=2,
            drawn_tile=None,
            my_hand=tuple(Tile(c) for c in ("5w", "5w", "1t", "2t", "3t", "4t", "5t", "6t", "7t", "8t", "9t", "2b", "3b")),
            last_discard=PublicDiscard(seat=2, tile=Tile("5w"), seq=9),
        )
        analysis = _rules().analyze(observation)
        facts = _facts_by_key(analysis)["peng:5w"]

        self.assertIs(facts.fact_kind, CandidateFactKind.HAND_PROGRESS)
        self.assertEqual(facts.shanten_after, 0)
        self.assertEqual(facts.best_followup_discard, "2b")
        self.assertFalse(facts.replacement_draw_unknown)

    def test_chi_facts_carry_best_followup_discard(self) -> None:
        """吃事实给出最佳合法后续弃牌与动作后向听。"""

        observation = make_observation(
            phase="response_chi",
            responding_seats=(0,),
            turn_seat=3,
            drawn_tile=None,
            my_hand=tuple(Tile(c) for c in ("1w", "2w", "1t", "2t", "3t", "4t", "5t", "6t", "7t", "8t", "9t", "2b", "2b")),
            last_discard=PublicDiscard(seat=3, tile=Tile("3w"), seq=9),
        )
        analysis = _rules().analyze(observation)
        facts = _facts_by_key(analysis)["chi:1w,2w,3w"]

        self.assertIs(facts.fact_kind, CandidateFactKind.HAND_PROGRESS)
        self.assertEqual(facts.shanten_after, 0)
        self.assertEqual(facts.best_followup_discard, "1t")

    def test_gang_facts_mark_replacement_unknown(self) -> None:
        """杠事实：补牌未知，向听与有效牌为补牌前余牌口径，无后续弃牌。"""

        observation = make_observation(
            my_hand=tuple(Tile(c) for c in ("9w", "9w", "9w", "9w", "1t", "2t", "3t", "4t", "5t", "6t", "7t", "8t", "9t")),
            drawn_tile=Tile("西"),
        )
        analysis = _rules().analyze(observation)
        facts = _facts_by_key(analysis)["gang:concealed:9w"]

        self.assertIs(facts.fact_kind, CandidateFactKind.HAND_PROGRESS)
        self.assertTrue(facts.replacement_draw_unknown)
        self.assertIsNone(facts.best_followup_discard)
        self.assertIn("补牌前", facts.note)
        # 补牌前 10 张余牌 = 123456789t + 西，向听 0。
        self.assertEqual(facts.shanten_after, 0)

    def test_remaining_estimate_deducts_public_tiles(self) -> None:
        """剩余张数口径：他家牌河已见 1w 时，1w 的剩余估计随之扣减。"""

        observation = make_observation(
            drawn_tile=Tile("4t"),
            discards=((), (Tile("1w"),), (), ()),
        )
        analysis = _rules().analyze(observation)
        facts = _facts_by_key(analysis)["discard:1w"]
        useful = {item.code: item.remaining_estimate for item in facts.useful_tiles}

        # 4 - 本人手牌 0 - 他家牌河 1 - 本动作新公开 1 = 2。
        self.assertEqual(useful["1w"], 2)

    def test_malformed_discard_candidate_analysis_failed(self) -> None:
        """畸形弃牌候选的正反例：弃牌不在手牌 → ANALYSIS_FAILED，不伪造事实。

        正例：弃牌牌值在手牌中 → 正常 HAND_PROGRESS 事实；
        反例：弃牌牌值不在手牌 → FactsAnalysisError 收敛为 ANALYSIS_FAILED
        + note + candidate_facts RuleIssue，数值字段全空（与吃/碰/杠的
        形状校验同款口径，避免 _remove_codes 静默空转产出"未弃牌"事实）。
        """

        from hangma_bot.hangma import candidate_facts
        from hangma_bot.hangma.interface import RuleCandidate
        from hangma_bot.hangma.internal_types import WindowContext
        from hangma_bot.kernel.actions import Discard

        context = WindowContext(
            seat=0,
            phase="draw",
            turn_seat=0,
            responding_seats=(),
            hand_tiles=(Tile("1w"), Tile("2w"), Tile("3w"), Tile("4w")),
            drawn_tile=None,
            my_chi_count=0,
            my_peng_codes=(),
            last_discard=None,
            catch_play=False,
            remaining_tile_count=60,
        )
        public_counts = (0,) * 34

        good = RuleCandidate(action=Discard(Tile("1w")), action_key="discard:1w", evidence=())
        attached, issues = candidate_facts.attach_facts(context, public_counts, 0, (good,))
        self.assertEqual(issues, ())
        self.assertIs(attached[0].facts.fact_kind, CandidateFactKind.HAND_PROGRESS)
        self.assertIsInstance(attached[0].facts.shanten_after, int)

        bad = RuleCandidate(action=Discard(Tile("9w")), action_key="discard:9w", evidence=())
        attached, issues = candidate_facts.attach_facts(context, public_counts, 0, (bad,))
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].area, "candidate_facts")
        self.assertIs(attached[0].facts.fact_kind, CandidateFactKind.ANALYSIS_FAILED)
        self.assertIsNone(attached[0].facts.shanten_after)
        self.assertEqual(attached[0].facts.useful_tiles, ())
        self.assertIsNone(attached[0].facts.best_followup_discard)
        self.assertIn("不在手牌", attached[0].facts.note)

    def test_emergency_candidate_has_no_facts(self) -> None:
        """紧急路径按设计不运行复杂分析：紧急候选事实为 None。"""

        observation = make_observation(drawn_tile=Tile("4t"))
        analysis = _rules().analyze(observation)

        self.assertIsNotNone(analysis.emergency_candidate)
        self.assertIsNone(analysis.emergency_candidate.facts)
        # 同键的合法候选（动作族生产）仍携带事实。
        emergency_key = analysis.emergency_candidate.action_key
        family_version = _facts_by_key(analysis)[emergency_key]
        self.assertIsNotNone(family_version)

    def test_analysis_failed_degrades_only_that_candidate(self) -> None:
        """畸形短手牌使吃碰和等待事实都失败，但过仍是合法紧急动作。"""

        observation = make_observation(
            phase="response_peng",
            responding_seats=(0,),
            turn_seat=2,
            drawn_tile=None,
            my_hand=(Tile("5w"), Tile("5w")),
            last_discard=PublicDiscard(seat=2, tile=Tile("5w"), seq=9),
        )
        analysis = _rules().analyze(observation)
        by_key = _facts_by_key(analysis)

        self.assertEqual(analysis.completeness, RuleCompleteness.DEGRADED)
        self.assertIs(by_key["peng:5w"].fact_kind, CandidateFactKind.ANALYSIS_FAILED)
        self.assertIsNone(by_key["peng:5w"].shanten_after)
        self.assertTrue(by_key["peng:5w"].note)
        self.assertIs(by_key["pass"].fact_kind, CandidateFactKind.ANALYSIS_FAILED)
        self.assertEqual(analysis.emergency_candidate.action_key, "pass")
        self.assertTrue(any(issue.area == "candidate_facts" for issue in analysis.issues))

    def test_facts_module_failure_degrades_to_unproduced(self) -> None:
        """事实模块整体异常：候选保留（facts=None）并记 RuleIssue，不崩溃。"""

        import hangma_bot.hangma.candidate_facts as candidate_facts

        def broken(context, public_counts, meld_blocks, candidates):
            raise RuntimeError("事实生产故障注入")

        observation = make_observation(drawn_tile=Tile("4t"))
        with mock.patch.object(candidate_facts, "attach_facts", broken):
            analysis = _rules().analyze(observation)

        self.assertEqual(analysis.completeness, RuleCompleteness.DEGRADED)
        self.assertTrue(all(candidate.facts is None for candidate in analysis.legal_candidates))
        self.assertTrue(
            any(
                issue.area == "candidate_facts" and "事实生产故障注入" in issue.reason
                for issue in analysis.issues
            )
        )
        self.assertIsNotNone(analysis.emergency_candidate)

    def test_hand_analysis_failure_isolated_per_candidate(self) -> None:
        """手牌数学异常：全部 HAND_PROGRESS 候选降级为 ANALYSIS_FAILED。

        胡族独立降级，紧急路径保持可用——不伪造任何向听/有效牌数值。
        """

        import hangma_bot.hangma.hand_analysis as hand_analysis

        def broken(hand_tiles, meld_set_count):
            raise ValueError("手牌数学故障注入")

        observation = make_observation(drawn_tile=Tile("4t"))
        with mock.patch.object(hand_analysis, "analyse_hand", broken):
            analysis = _rules().analyze(observation)

        self.assertEqual(analysis.completeness, RuleCompleteness.DEGRADED)
        self.assertIsNotNone(analysis.emergency_candidate)
        for candidate in analysis.legal_candidates:
            if candidate.action_key.startswith("discard:"):
                self.assertIs(candidate.facts.fact_kind, CandidateFactKind.ANALYSIS_FAILED)
                self.assertIsNone(candidate.facts.shanten_after)
                self.assertEqual(candidate.facts.useful_tiles, ())


class FactsLatencyTests(unittest.TestCase):
    """事实生产不拖慢动作窗口：重候选窗口的最差与 P95 延迟受控。"""

    def test_heavy_candidate_windows_latency_under_budget(self) -> None:
        """重候选窗口反复分析：最差 < 0.5 秒（1 秒窗口预算的一半）。

        覆盖两个最重形状：(a) 全弃牌族——15 种分散垃圾牌的摸牌窗口，
        每种弃牌各跑一次完整向听/有效牌分析；(b) 响应窗口——吃/碰/明杠
        候选各枚举最佳后续弃牌。失败消息写入最差与 P95，便于验收报告引用。
        """

        import time

        garbage = tuple(
            Tile(c)
            for c in ("1w", "4w", "7w", "2b", "5b", "8b", "3t", "6t", "9t", "东", "南", "西", "北", "中")
        )
        draw_observation = make_observation(
            my_hand=garbage, drawn_tile=Tile("发")
        )
        # 吃窗口：被吃 5b，手牌含 3b4b / 4b6b / 6b7b 三组组合 + 9 种杂牌，
        # 每个吃候选都要枚举全部后续弃牌。
        chi_hand = tuple(
            Tile(c)
            for c in ("3b", "4b", "6b", "7b", "1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w")
        )
        response_observation = make_observation(
            phase="response_chi",
            responding_seats=(0,),
            turn_seat=3,
            drawn_tile=None,
            my_hand=chi_hand,
            last_discard=PublicDiscard(seat=3, tile=Tile("5b"), seq=9),
        )

        rules = _rules()
        durations = []
        for _ in range(20):
            start = time.perf_counter()
            rules.analyze(draw_observation)
            rules.analyze(response_observation)
            durations.append(time.perf_counter() - start)

        ordered = sorted(durations)
        worst = ordered[-1]
        p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
        self.assertLess(
            worst,
            0.5,
            "重候选窗口最差 {worst_ms:.1f}ms、P95 {p95_ms:.1f}ms 超过 0.5 秒预算上限".format(
                worst_ms=worst * 1000, p95_ms=p95 * 1000
            ),
        )


if __name__ == "__main__":
    unittest.main()
