"""专家审查（2 视角交叉评审）修复项的回归测试（规则牌效事实口径）。

2026-09-04 集成阶段契约收口后，向听/有效牌数学已移入 hangma；本文件
回归锚随之更新为事实消费语义，同时保留历史修复的意图：
- 垃圾手牌弃牌排序由规则事实的向听/有效牌驱动（原对子牌眼回归）；
- 七对/豪华七对/财神任意牌听的正反例由规则引擎事实还原；
- 杠后按补牌前余牌口径保守估计，不假设后续弃牌（原专家审查 F7）；
- facts=None / ANALYSIS_FAILED 时策略保守处理，不推断数值；
- 主策略逐候选让出事件循环，应用层 wait_for 才能按保底截止时间抢占。
"""

from __future__ import annotations

import asyncio
import unittest

from hangma_bot.hangma.interface import (
    CandidateFactKind,
    CandidateFacts,
    RuleCandidate,
    RuleCompleteness,
)
from hangma_bot.kernel.actions import (
    Discard,
    Tile,
    WindowPhase,
)
from hangma_bot.policy import WeightedHeuristicPolicy

from .support import (
    keep_keys,
    make_budget,
    make_observation,
    make_request,
    make_rules,
    ranks_by_key,
    rules_from_engine,
    run_choose,
)


def _policy() -> WeightedHeuristicPolicy:
    """注入固定时钟，避免读取真实时间。"""

    return WeightedHeuristicPolicy(monotonic=lambda: 0.0)


def _hand(codes) -> tuple:
    """按牌码元组构造手牌。"""

    return tuple(Tile(code) for code in codes)


class HandMathRegressionTests(unittest.TestCase):
    """规则事实驱动的排序回归（原向听/有效牌估计回归的延续）。"""

    def test_garbage_hand_shanten_facts_order_discards(self) -> None:
        """原对子牌眼反例：打 3b（向听 4）排在打 3t（向听 5）之前。

        旧策略估计器曾把"拆对子 3b3b"误排在"打孤张 3t"之后；现在
        排序由 hangma 单一规则源的向听事实驱动，原因文本写明数值。
        """

        hand = ("1w", "3b", "3b", "3t", "4b", "4t", "5w", "6t", "6w", "7t", "8b", "8t", "9b")
        observation = make_observation(
            my_hand=_hand(hand), drawn_tile=Tile("9t")
        )
        analysis = rules_from_engine(observation)
        plan = run_choose(
            _policy(),
            make_request(
                observation, keep_keys(analysis, ["discard:3t", "discard:3b"])
            ),
            make_budget(),
        )
        ranks = ranks_by_key(plan)

        self.assertLess(ranks["discard:3b"], ranks["discard:3t"])
        by_key = {item.action_key: item for item in plan.candidates}
        self.assertTrue(any("向听数 4" in r for r in by_key["discard:3b"].reasons))
        self.assertTrue(any("向听数 5" in r for r in by_key["discard:3t"].reasons))

    def test_chiitoi_tenpai_discard_preferred_over_breaking_pair(self) -> None:
        """七对听牌：弃单张（保 6 对，向听 0）排在拆对（向听 1）之前。"""

        observation = make_observation(
            my_hand=_hand(("东", "东", "南", "南", "西", "西", "北", "北", "中", "中", "发", "发", "1w"))
        )
        plan = run_choose(
            _policy(),
            make_request(
                observation,
                keep_keys(rules_from_engine(observation), ["discard:1w", "discard:东"]),
            ),
            make_budget(),
        )
        ranks = ranks_by_key(plan)

        self.assertLess(ranks["discard:1w"], ranks["discard:东"])

    def test_luxury_chiitoi_four_of_kind_counts_two_pairs(self) -> None:
        """豪华七对：三个四张 + 单张弃单后听牌，优于拆四张。"""

        observation = make_observation(
            my_hand=_hand(("东", "东", "东", "东", "南", "南", "南", "南", "西", "西", "西", "西", "中"))
        )
        plan = run_choose(
            _policy(),
            make_request(
                observation,
                keep_keys(rules_from_engine(observation), ["discard:中", "discard:东"]),
            ),
            make_budget(),
        )
        ranks = ranks_by_key(plan)

        self.assertLess(ranks["discard:中"], ranks["discard:东"])

    def test_joker_tenpai_counts_all_remaining_tiles_effective(self) -> None:
        """财神听牌态（四面子+财神）：任意可摸牌有效，不得清零。"""

        observation = make_observation(
            my_hand=_hand(("1w", "1w", "1w", "2w", "2w", "2w", "3b", "3b", "3b", "4b", "4b", "4b", "白"))
        )
        plan = run_choose(
            _policy(),
            make_request(
                observation,
                keep_keys(rules_from_engine(observation), ["discard:1w"]),
            ),
            make_budget(),
        )

        joined = "；".join(plan.candidates[0].reasons)
        self.assertIn("有效牌34种", joined)

    def test_gang_evaluated_as_waiting_state_without_followup_discard(self) -> None:
        """杠后按补牌前余牌口径估计：原因不出现最佳弃牌，排序真实。"""

        observation = make_observation(
            my_hand=_hand(("9w", "9w", "9w", "9w", "1t", "2t", "3t", "4t", "5t", "6t", "7t", "8t", "9t")),
            drawn_tile=Tile("西"),
        )
        analysis = rules_from_engine(observation)
        plan = run_choose(
            _policy(),
            make_request(
                observation, keep_keys(analysis, ["gang:concealed:9w", "discard:1t"])
            ),
            make_budget(),
        )

        gang = next(item for item in plan.candidates if item.action_key.startswith("gang:"))
        joined = "；".join(gang.reasons)
        self.assertIn("杠上补牌未知", joined)
        self.assertIn("补牌前口径", joined)
        self.assertNotIn("最佳弃牌", joined)
        self.assertLess(gang.rank, ranks_by_key(plan)["discard:1t"])


class FactsConsumptionContractTests(unittest.TestCase):
    """策略对缺失/失败事实的保守消费契约（§4.1）。"""

    def test_unknown_facts_scored_without_shanten_inference(self) -> None:
        """facts=None（紧急路径或未覆盖族）不得推断向听/有效牌数值。"""

        candidate = RuleCandidate(
            action=Discard(Tile("5w")), action_key="discard:5w", evidence=()
        )
        observation = make_observation(
            my_hand=_hand(("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "2b", "3b", "4t")),
            drawn_tile=Tile("4t"),
        )
        plan = run_choose(
            _policy(),
            make_request(observation, make_rules((candidate,))),
            make_budget(),
        )

        only = plan.candidates[0]
        self.assertNotIn("第三层-向听数", [part.name for part in only.score_parts])
        self.assertTrue(any("未生产" in reason for reason in only.reasons))

    def test_analysis_failed_facts_carry_note_without_numbers(self) -> None:
        """ANALYSIS_FAILED 事实：策略记录失败原因，不携带任何数值分项。"""

        facts = CandidateFacts(
            fact_kind=CandidateFactKind.ANALYSIS_FAILED,
            shanten_after=None,
            completeness=RuleCompleteness.DEGRADED,
            note="向听分支超时",
        )
        candidate = RuleCandidate(
            action=Discard(Tile("5w")),
            action_key="discard:5w",
            evidence=(),
            facts=facts,
        )
        observation = make_observation(
            my_hand=_hand(("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "2b", "3b", "4t")),
            drawn_tile=Tile("4t"),
        )
        plan = run_choose(
            _policy(),
            make_request(observation, make_rules((candidate,))),
            make_budget(),
        )

        only = plan.candidates[0]
        self.assertNotIn("第三层-向听数", [part.name for part in only.score_parts])
        self.assertNotIn("第四层-有效牌", [part.name for part in only.score_parts])
        self.assertTrue(any("牌效分析失败" in reason for reason in only.reasons))
        self.assertTrue(any("向听分支超时" in reason for reason in only.reasons))


class PreemptionContractTests(unittest.TestCase):
    """主策略必须让出事件循环，应用层 wait_for 才能按保底截止时间抢占。"""

    def test_scoring_loop_yields_between_candidates(self) -> None:
        """评分循环逐候选让出事件循环（wait_for 抢占的合作性证明）。

        用事件循环内的计数器任务统计让出次数：候选越多计数越高，
        且让出次数不少于候选数——若评分是同步长循环，计数器不会
        随候选数增长，应用层 wait_for 也无法中途抢占。
        """

        observation = make_observation(
            my_hand=_hand(("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "2b", "3b", "4t")),
            drawn_tile=Tile("4t"),
        )
        candidates = tuple(
            RuleCandidate(action=Discard(Tile(code)), action_key="discard:" + code, evidence=())
            for code in ("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "2b", "3b")
        )
        request = make_request(observation, make_rules(candidates))
        policy = _policy()

        async def scenario():
            yields = 0

            async def counter():
                nonlocal yields
                while True:
                    yields += 1
                    await asyncio.sleep(0)

            task = asyncio.create_task(counter())
            try:
                plan = await policy.choose(request, make_budget())
            finally:
                task.cancel()
            return plan, yields

        plan, yields = asyncio.run(scenario())

        self.assertEqual(len(plan.candidates), len(candidates))
        self.assertGreaterEqual(
            yields,
            len(candidates),
            "评分循环让出次数 {yields} 少于候选数 {n}：疑似同步长循环".format(
                yields=yields, n=len(candidates)
            ),
        )


if __name__ == "__main__":
    unittest.main()

