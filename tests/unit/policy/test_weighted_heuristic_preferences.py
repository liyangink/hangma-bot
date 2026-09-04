"""WeightedHeuristicPolicy 分层偏好的正反例。

胡/过/吃/碰/杠/弃牌各动作族至少一正一反：
排序断言只依赖向听层（每步 100 分）与固定惩罚（60/10/6 分）的
数量级差异，不依赖小权重的精确数值。
"""

from __future__ import annotations

import unittest

from hangma_bot.kernel.actions import (
    Chi,
    Discard,
    Gang,
    GangKind,
    Hu,
    Pass,
    Peng,
    Tile,
    WindowPhase,
)
from hangma_bot.kernel.observation import PublicDiscard
from hangma_bot.policy import WeightedHeuristicPolicy

from .support import (
    candidates_for,
    make_budget,
    make_observation,
    make_request,
    make_rules,
    ranks_by_key,
    run_choose,
)


def _policy() -> WeightedHeuristicPolicy:
    """使用注入时钟，避免读取真实时间。"""

    return WeightedHeuristicPolicy(monotonic=lambda: 0.0)


def _hand(codes) -> tuple:
    """按牌码元组构造手牌。"""

    return tuple(Tile(code) for code in codes)


class FamilyPreferenceTests(unittest.TestCase):
    """各动作族的分层排序正反例。"""

    def test_legal_hu_always_ranks_first(self) -> None:
        """正例：规则确认可胡时立即胡牌排在第一位。"""

        observation = make_observation(
            my_hand=_hand(("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "1b", "2t", "3t")),
            drawn_tile=Tile("2t"),
        )
        candidates = candidates_for(
            [Hu(), Discard(Tile("2t")), Discard(Tile("1b")), Pass()]
        )
        plan = run_choose(
            _policy(), make_request(observation, make_rules(candidates)), make_budget()
        )

        self.assertEqual(plan.candidates[0].action_key, "hu")
        self.assertIn("第一层-立即胡牌", [part.name for part in plan.candidates[0].score_parts])

    def test_discard_keeping_structure_beats_breaking_run(self) -> None:
        """弃牌正反例：保留对子结构的弃牌（向听估计 4）优于拆对（向听估计 5）。"""

        observation = make_observation(
            my_hand=_hand(("1w", "4w", "7w", "1b", "2b", "4b", "7b", "5t", "5t", "9t", "东", "西", "中")),
            drawn_tile=Tile("9t"),
        )
        from .support import discards_for

        plan = run_choose(
            _policy(), make_request(observation, make_rules(discards_for(("中", "5t")))), make_budget()
        )
        ranks = ranks_by_key(plan)

        self.assertLess(ranks["discard:中"], ranks["discard:5t"])

    def test_peng_reducing_shanten_beats_pass(self) -> None:
        """碰正例：碰后向听改善（1 步 = 100 分）压过 6 分鸣牌风险。"""

        observation = make_observation(
            phase="response_peng",
            responding_seats=(0,),
            turn_seat=2,
            my_hand=_hand(("5w", "5w", "1t", "2t", "3t", "4t", "5t", "6t", "1b", "2b", "8t", "9t", "东")),
            last_discard=PublicDiscard(seat=2, tile=Tile("5w"), seq=9),
        )
        candidates = candidates_for([Peng(Tile("5w")), Pass()])
        plan = run_choose(
            _policy(),
            make_request(observation, make_rules(candidates), phase=WindowPhase.RESPONSE_PENG),
            make_budget(),
        )

        self.assertEqual(plan.candidates[0].action_key, "peng:5w")
        ranks = ranks_by_key(plan)
        self.assertLess(ranks["peng:5w"], ranks["pass"])

    def test_peng_not_reducing_shanten_loses_to_pass(self) -> None:
        """碰反例：碰后向听不改善时，过（保灵活度）排在前。"""

        observation = make_observation(
            phase="response_peng",
            responding_seats=(0,),
            turn_seat=1,
            my_hand=_hand(("5w", "5w", "1t", "2t", "3t", "4t", "5t", "6t", "7t", "8t", "9t", "2b", "3b")),
            last_discard=PublicDiscard(seat=1, tile=Tile("5w"), seq=9),
        )
        candidates = candidates_for([Peng(Tile("5w")), Pass()])
        plan = run_choose(
            _policy(),
            make_request(observation, make_rules(candidates), phase=WindowPhase.RESPONSE_PENG),
            make_budget(),
        )

        self.assertEqual(plan.candidates[0].action_key, "pass")

    def test_chi_reducing_shanten_beats_pass(self) -> None:
        """吃正例：吃后向听改善压过 10 分鸣牌风险。"""

        observation = make_observation(
            phase="response_chi",
            responding_seats=(0,),
            turn_seat=3,
            my_hand=_hand(("1w", "2w", "2b", "2b", "2b", "5t", "5t", "5t", "9t", "东", "西", "南", "北")),
            last_discard=PublicDiscard(seat=3, tile=Tile("3w"), seq=9),
        )
        candidates = candidates_for(
            [Chi((Tile("1w"), Tile("2w"), Tile("3w"))), Pass()]
        )
        plan = run_choose(
            _policy(),
            make_request(observation, make_rules(candidates), phase=WindowPhase.RESPONSE_CHI),
            make_budget(),
        )

        self.assertEqual(plan.candidates[0].action_key, "chi:1w,2w,3w")
        chi = next(item for item in plan.candidates if item.action_key.startswith("chi:"))
        self.assertIn("第六层-鸣牌风险", [part.name for part in chi.score_parts])

    def test_chi_not_reducing_shanten_loses_to_pass(self) -> None:
        """吃反例：吃后向听不改善（听牌对听牌）时，过排在前且风险分被钉住。"""

        observation = make_observation(
            phase="response_chi",
            responding_seats=(0,),
            turn_seat=3,
            my_hand=_hand(("1w", "2w", "1t", "2t", "3t", "4t", "5t", "6t", "7t", "8t", "9t", "2b", "2b")),
            last_discard=PublicDiscard(seat=3, tile=Tile("3w"), seq=9),
        )
        candidates = candidates_for(
            [Chi((Tile("1w"), Tile("2w"), Tile("3w"))), Pass()]
        )
        plan = run_choose(
            _policy(),
            make_request(observation, make_rules(candidates), phase=WindowPhase.RESPONSE_CHI),
            make_budget(),
        )

        self.assertEqual(plan.candidates[0].action_key, "pass")
        chi = next(item for item in plan.candidates if item.action_key.startswith("chi:"))
        risk_parts = [part for part in chi.score_parts if part.name == "第六层-鸣牌风险"]
        self.assertEqual(len(risk_parts), 1)
        self.assertEqual(risk_parts[0].value, -10.0)

    def test_gang_scored_with_bonus_but_below_hu(self) -> None:
        """杠正反例：有杠收益分项；存在可胡时胡仍第一。"""

        observation = make_observation(
            my_hand=_hand(("2b", "2b", "2b", "2b", "1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w")),
            drawn_tile=Tile("东"),
        )
        candidates = candidates_for(
            [Hu(), Gang(Tile("2b"), GangKind.CONCEALED), Discard(Tile("2b"))]
        )
        plan = run_choose(
            _policy(), make_request(observation, make_rules(candidates)), make_budget()
        )

        self.assertEqual(plan.candidates[0].action_key, "hu")
        gang = next(item for item in plan.candidates if item.action_key.startswith("gang:"))
        part_names = [part.name for part in gang.score_parts]
        self.assertIn("第二层-杠收益", part_names)
        self.assertTrue(any("暗杠" in reason for reason in gang.reasons))

    def test_wealth_god_discard_penalized_below_equal_structure(self) -> None:
        """财神反例：结构等价时打财神受大惩罚，排在使用普通牌之后。"""

        observation = make_observation(
            my_hand=_hand(("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "2b", "3b", "4t")),
            drawn_tile=Tile("白"),
        )
        from .support import discards_for

        codes = sorted(set(code.code for code in observation.my_hand) | {"白"})
        plan = run_choose(
            _policy(), make_request(observation, make_rules(discards_for(codes))), make_budget()
        )
        ranks = ranks_by_key(plan)

        self.assertLess(ranks["discard:4t"], ranks["discard:白"])
        wealth = next(item for item in plan.candidates if item.action_key == "discard:白")
        self.assertTrue(any("财神" in reason for reason in wealth.reasons))

    def test_safe_tile_preferred_over_fresh_tile(self) -> None:
        """弃牌防守正例：结构等价时熟张（已见于他家牌河）优于生张。"""

        observation = make_observation(
            my_hand=_hand(("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "1b", "1b", "东")),
            drawn_tile=Tile("西"),
            # 东已见于下家（座位 1）牌河，是熟张；西是生张。
            discards=((), (Tile("东"),), (), ()),
        )
        from .support import discards_for

        codes = ("东", "西")
        plan = run_choose(
            _policy(), make_request(observation, make_rules(discards_for(codes))), make_budget()
        )
        ranks = ranks_by_key(plan)

        self.assertLess(ranks["discard:东"], ranks["discard:西"])

    def test_catch_play_note_recorded(self) -> None:
        """抓打圈：计划记录硬约束上下文，弃牌原因说明抓打圈。"""

        from .support import discards_for
        from hangma_bot.kernel.observation import RulePublicState

        observation = make_observation(
            my_hand=_hand(("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "2b", "3b", "4t")),
            drawn_tile=Tile("4t"),
            rule_state=RulePublicState(
                wealth_god=Tile("白"), baotou=False, chain_count=0, catch_play=True
            ),
        )
        plan = run_choose(
            _policy(),
            make_request(observation, make_rules(discards_for(("4t",)))),
            make_budget(),
        )

        self.assertTrue(any("抓打圈" in reason for reason in plan.degraded_reasons))
        self.assertTrue(any("抓打圈" in r for item in plan.candidates for r in item.reasons))

    def test_leading_rank_style_prefers_safe_tile(self) -> None:
        """第七层正例：桌内领先时熟张弃牌获得名次风格分项。"""

        from .support import discards_for

        observation = make_observation(
            my_hand=_hand(("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "1b", "1b", "东")),
            drawn_tile=Tile("西"),
            discards=((), (Tile("东"),), (), ()),
            scores=(100, 0, 0, 0),
        )
        plan = run_choose(
            _policy(), make_request(observation, make_rules(discards_for(("东", "西")))), make_budget()
        )

        east = next(item for item in plan.candidates if item.action_key == "discard:东")
        self.assertIn("第七层-名次风格", [part.name for part in east.score_parts])

    def test_trailing_rank_style_rewards_fastest_route(self) -> None:
        """第七层反例角：桌内垫底时向听最优弃牌获得进取风格分项。"""

        from .support import discards_for

        observation = make_observation(
            my_hand=_hand(("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "2b", "3b", "4t")),
            drawn_tile=Tile("4t"),
            scores=(0, 100, 100, 100),
        )
        codes = ("4t", "3b")
        plan = run_choose(
            _policy(), make_request(observation, make_rules(discards_for(codes))), make_budget()
        )

        best = next(item for item in plan.candidates if item.action_key == "discard:4t")
        self.assertIn("第七层-名次风格", [part.name for part in best.score_parts])

    def test_effective_tile_layer_decides_order_when_shanten_ties(self) -> None:
        """第四层回归锚：向听持平时，有效牌权重高的弃牌排前且分项值可比较。"""

        from .support import discards_for

        observation = make_observation(
            my_hand=_hand(("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "2b", "3b", "4t")),
            drawn_tile=Tile("4t"),
        )
        plan = run_choose(
            _policy(),
            make_request(observation, make_rules(discards_for(("4t", "1w")))),
            make_budget(),
        )
        ranks = ranks_by_key(plan)

        self.assertLess(ranks["discard:1w"], ranks["discard:4t"])
        by_key = {item.action_key: item for item in plan.candidates}
        parts = {key: {part.name: part for part in item.score_parts} for key, item in by_key.items()}
        self.assertIn("第四层-有效牌", parts["discard:1w"])
        self.assertIn("第五层-灵活度", parts["discard:1w"])
        # 两个候选向听层完全持平，排序差异只能来自第四/五层分项值。
        self.assertEqual(
            parts["discard:1w"]["第三层-向听数"].value,
            parts["discard:4t"]["第三层-向听数"].value,
        )
        self.assertGreater(
            parts["discard:1w"]["第四层-有效牌"].value,
            parts["discard:4t"]["第四层-有效牌"].value,
        )


if __name__ == "__main__":
    unittest.main()
