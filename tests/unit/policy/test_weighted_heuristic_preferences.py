"""WeightedHeuristicPolicy 分层偏好的正反例（规则牌效事实口径）。

2026-09-04 集成阶段契约收口：策略只消费 hangma 生产的 CandidateFacts，
不再自行推演向听/有效牌。本文件的排序场景全部经真实规则引擎
（support.rules_from_engine）生成候选与事实，断言只依赖向听层
（每步 100 分）与固定惩罚/收益分项的数量级差异，不依赖小权重精确值。
"""

from __future__ import annotations

import unittest

from hangma_bot.kernel.actions import Tile, WindowPhase
from hangma_bot.kernel.observation import PublicDiscard, RulePublicState
from hangma_bot.policy.legacy_pass import LegacyWeightedHeuristicPolicy

from .support import (
    keep_keys,
    make_budget,
    make_observation,
    make_request,
    ranks_by_key,
    rules_from_engine,
    run_choose,
)


def _policy() -> LegacyWeightedHeuristicPolicy:
    """新规则输入走正式 V0 兼容入口；冻结原类另由历史请求回归验证。"""

    return LegacyWeightedHeuristicPolicy(monotonic=lambda: 0.0)


def _hand(codes) -> tuple:
    """按牌码元组构造手牌。"""

    return tuple(Tile(code) for code in codes)


def _plan(observation, keys, phase=WindowPhase.DRAW):
    """真实引擎分析 + 选键子集 + 主策略排序，返回计划。"""

    analysis = rules_from_engine(observation)
    request = make_request(observation, keep_keys(analysis, keys), phase=phase)
    return run_choose(_policy(), request, make_budget())


class FamilyPreferenceTests(unittest.TestCase):
    """各动作族的分层排序正反例。"""

    def test_legal_hu_always_ranks_first(self) -> None:
        """正例：规则确认可胡（WIN 事实）时立即胡牌排在第一位。"""

        observation = make_observation(
            my_hand=_hand(("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "2b", "3b", "4t")),
            drawn_tile=Tile("4t"),
        )
        plan = _plan(observation, ["hu", "discard:4t", "discard:1b"])

        self.assertEqual(plan.candidates[0].action_key, "hu")
        self.assertIn(
            "第一层-立即胡牌", [part.name for part in plan.candidates[0].score_parts]
        )

    def test_discard_keeping_structure_beats_breaking_run(self) -> None:
        """弃牌正反例：打孤张中（向听 4）优于拆对子 5t（向听 5）。"""

        observation = make_observation(
            my_hand=_hand(("1w", "4w", "7w", "1b", "2b", "4b", "7b", "5t", "5t", "9t", "东", "西", "中")),
            drawn_tile=Tile("9t"),
        )
        plan = _plan(observation, ["discard:中", "discard:5t"])
        ranks = ranks_by_key(plan)

        self.assertLess(ranks["discard:中"], ranks["discard:5t"])

    def test_peng_to_tenpai_beats_pass(self) -> None:
        """碰正例：碰后按最佳后续弃牌到听牌（有效牌收益压过 6 分风险）。"""

        observation = make_observation(
            phase="response_peng",
            responding_seats=(0,),
            turn_seat=2,
            my_hand=_hand(("5w", "5w", "1t", "2t", "3t", "4t", "5t", "6t", "7t", "8t", "9t", "2b", "3b")),
            last_discard=PublicDiscard(seat=2, tile=Tile("5w"), seq=9),
        )
        plan = _plan(observation, ["peng:5w", "pass"], WindowPhase.RESPONSE_PENG)

        self.assertEqual(plan.candidates[0].action_key, "peng:5w")
        peng = next(item for item in plan.candidates if item.action_key == "peng:5w")
        self.assertTrue(any("最佳后续弃牌2b" in reason for reason in peng.reasons))

    def test_peng_not_reaching_tenpai_loses_to_pass(self) -> None:
        """碰反例：碰后仍离听牌一步（向听 1）时，过排在前且风险分被钉住。"""

        observation = make_observation(
            phase="response_peng",
            responding_seats=(0,),
            turn_seat=1,
            my_hand=_hand(("5w", "5w", "1t", "2t", "3t", "4t", "5t", "6t", "1b", "2b", "8t", "9t", "东")),
            last_discard=PublicDiscard(seat=1, tile=Tile("5w"), seq=9),
        )
        plan = _plan(observation, ["peng:5w", "pass"], WindowPhase.RESPONSE_PENG)

        self.assertEqual(plan.candidates[0].action_key, "pass")
        peng = next(item for item in plan.candidates if item.action_key == "peng:5w")
        risk_parts = [part for part in peng.score_parts if part.name == "第六层-鸣牌风险"]
        self.assertEqual(len(risk_parts), 1)
        self.assertEqual(risk_parts[0].value, -6.0)

    def test_chi_to_rich_tenpai_beats_pass(self) -> None:
        """吃正例：吃后到听牌且有效牌充裕（收益压过 10 分鸣牌风险）。"""

        observation = make_observation(
            phase="response_chi",
            responding_seats=(0,),
            turn_seat=3,
            my_hand=_hand(("1w", "2w", "1t", "2t", "3t", "4t", "5t", "6t", "7t", "8t", "9t", "2b", "2b")),
            last_discard=PublicDiscard(seat=3, tile=Tile("3w"), seq=9),
        )
        plan = _plan(observation, ["chi:1w,2w,3w", "pass"], WindowPhase.RESPONSE_CHI)

        self.assertEqual(plan.candidates[0].action_key, "chi:1w,2w,3w")
        chi = next(item for item in plan.candidates if item.action_key == "chi:1w,2w,3w")
        self.assertIn("第六层-鸣牌风险", [part.name for part in chi.score_parts])
        self.assertTrue(any("最佳后续弃牌1t" in reason for reason in chi.reasons))

    def test_chi_not_reaching_tenpai_loses_to_pass(self) -> None:
        """吃反例：吃后仍离听牌一步（向听 1）时，过排在前。"""

        observation = make_observation(
            phase="response_chi",
            responding_seats=(0,),
            turn_seat=3,
            my_hand=_hand(("1w", "2w", "1t", "2t", "3t", "4t", "5t", "6t", "7t", "8t", "东", "2b", "9b")),
            last_discard=PublicDiscard(seat=3, tile=Tile("3w"), seq=9),
        )
        plan = _plan(observation, ["chi:1w,2w,3w", "pass"], WindowPhase.RESPONSE_CHI)

        self.assertEqual(plan.candidates[0].action_key, "pass")

    def test_gang_has_bonus_and_unknown_replacement_reason(self) -> None:
        """杠正反例：杠后有杠收益分项；补牌未知时按补牌前余牌口径保守估计。"""

        observation = make_observation(
            my_hand=_hand(("9w", "9w", "9w", "9w", "1t", "2t", "3t", "4t", "5t", "6t", "7t", "8t", "9t")),
            drawn_tile=Tile("西"),
        )
        plan = _plan(observation, ["gang:concealed:9w", "discard:1t"])

        self.assertEqual(plan.candidates[0].action_key, "gang:concealed:9w")
        gang = next(item for item in plan.candidates if item.action_key.startswith("gang:"))
        part_names = [part.name for part in gang.score_parts]
        self.assertIn("第二层-杠收益", part_names)
        self.assertTrue(any("暗杠" in reason for reason in gang.reasons))
        self.assertTrue(any("杠上补牌未知" in reason for reason in gang.reasons))
        self.assertFalse(any("最佳弃牌" in reason for reason in gang.reasons))

    def test_wealth_god_discard_penalized_below_equal_structure(self) -> None:
        """财神反例：结构等价时打财神受大惩罚，排在使用普通牌之后。"""

        observation = make_observation(
            my_hand=_hand(("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "2b", "3b", "4t")),
            drawn_tile=Tile("白"),
        )
        plan = _plan(observation, ["discard:4t", "discard:白", "discard:3b"])
        ranks = ranks_by_key(plan)

        self.assertLess(ranks["discard:4t"], ranks["discard:白"])
        wealth = next(item for item in plan.candidates if item.action_key == "discard:白")
        self.assertTrue(any("财神" in reason for reason in wealth.reasons))

    def test_safe_tile_preferred_over_fresh_tile(self) -> None:
        """弃牌防守正例：结构等价时熟张（已见于他家牌河）优于生张。"""

        observation = make_observation(
            my_hand=_hand(("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "1b", "1b", "东")),
            drawn_tile=Tile("西"),
            discards=((), (Tile("东"),), (), ()),
        )
        plan = _plan(observation, ["discard:东", "discard:西"])
        ranks = ranks_by_key(plan)

        self.assertLess(ranks["discard:东"], ranks["discard:西"])

    def test_catch_play_note_recorded(self) -> None:
        """抓打圈：计划记录硬约束上下文，弃牌原因说明抓打圈。"""

        observation = make_observation(
            my_hand=_hand(("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "2b", "3b", "4t")),
            drawn_tile=Tile("4t"),
            rule_state=RulePublicState(
                wealth_god=Tile("白"), baotou=False, chain_count=0, catch_play=True
            ),
        )
        plan = _plan(observation, ["discard:4t"])

        self.assertTrue(any("抓打圈" in reason for reason in plan.degraded_reasons))
        self.assertTrue(any("抓打圈" in r for item in plan.candidates for r in item.reasons))

    def test_leading_rank_style_prefers_safe_tile(self) -> None:
        """第七层正例：桌内领先时熟张弃牌获得名次风格分项。"""

        observation = make_observation(
            my_hand=_hand(("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "1b", "1b", "东")),
            drawn_tile=Tile("西"),
            discards=((), (Tile("东"),), (), ()),
            scores=(100, 0, 0, 0),
        )
        plan = _plan(observation, ["discard:东", "discard:西"])

        east = next(item for item in plan.candidates if item.action_key == "discard:东")
        self.assertIn("第七层-名次风格", [part.name for part in east.score_parts])

    def test_trailing_rank_style_rewards_fastest_route(self) -> None:
        """第七层反例角：桌内垫底时向听最优弃牌获得进取风格分项。"""

        observation = make_observation(
            my_hand=_hand(("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "2b", "3b", "4t")),
            drawn_tile=Tile("4t"),
            scores=(0, 100, 100, 100),
        )
        plan = _plan(observation, ["discard:4t", "discard:3b"])

        best = next(item for item in plan.candidates if item.action_key == "discard:4t")
        self.assertIn("第七层-名次风格", [part.name for part in best.score_parts])

    def test_effective_tile_layer_decides_order_when_shanten_ties(self) -> None:
        """第四层回归锚：向听持平时，有效牌权重高的弃牌排前且分项值可比较。"""

        observation = make_observation(
            my_hand=_hand(("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "2b", "3b", "4t")),
            drawn_tile=Tile("4t"),
        )
        plan = _plan(observation, ["discard:1w", "discard:4t"])
        ranks = ranks_by_key(plan)

        self.assertLess(ranks["discard:1w"], ranks["discard:4t"])
        by_key = {item.action_key: item for item in plan.candidates}
        parts = {key: {part.name: part for part in item.score_parts} for key, item in by_key.items()}
        self.assertIn("第四层-有效牌", parts["discard:1w"])
        # 两个候选向听层完全持平，排序差异只能来自第四层分项值。
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
