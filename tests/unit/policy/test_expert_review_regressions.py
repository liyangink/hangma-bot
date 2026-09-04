"""专家审查（2 视角交叉评审）修复项的回归测试。

每条测试对应一个已修复的 risk 级发现，防止数学与抢占语义回退：
- 分解贪心两变体 + 牌眼约束公式（原发现：对子牌眼与搭子混淆反转排序）；
- 七对原始向听可达成牌值、豪华七对（四张同牌计两对）；
- 财神 13 张等待态的“任意牌听”按全牌种有效处理；
- 杠后按 13 张等效等待态直接评估（不预先弃牌）；
- 主策略协程可在应用层 wait_for 下被抢占。
"""

from __future__ import annotations

import asyncio
import time
import unittest
from itertools import combinations
from typing import Tuple

from hangma_bot.kernel.actions import Chi, Discard, Gang, GangKind, Tile
from hangma_bot.policy import WeightedHeuristicPolicy
from hangma_bot.policy.hand_estimate import ALL_CODES
from hangma_bot.policy.interface import DecisionBudget

from .support import (
    candidates_for,
    discards_for,
    make_budget,
    make_observation,
    make_request,
    make_rules,
    ranks_by_key,
    run_choose,
)


def _policy() -> WeightedHeuristicPolicy:
    """注入固定时钟，避免读取真实时间。"""

    return WeightedHeuristicPolicy(monotonic=lambda: 0.0)


class HandMathRegressionTests(unittest.TestCase):
    """向听/有效牌估计的数学修复回归。"""

    def test_pair_eye_not_faked_by_proto_run(self) -> None:
        """专家反例：打 3t（向听 2）必须排在打 3b（向听 3）之前。"""

        hand = ("1w", "3b", "3b", "3t", "4b", "4t", "5w", "6t", "6w", "7t", "8b", "8t", "9b")
        observation = make_observation(
            my_hand=tuple(Tile(code) for code in hand), drawn_tile=Tile("9t")
        )
        plan = run_choose(
            _policy(),
            make_request(observation, make_rules(discards_for(("3t", "3b")))),
            make_budget(),
        )
        ranks = ranks_by_key(plan)

        self.assertLess(ranks["discard:3t"], ranks["discard:3b"])
        by_key = {item.action_key: item.reasons[0] for item in plan.candidates}
        self.assertIn("向听估计2", by_key["discard:3t"])
        self.assertIn("向听估计3", by_key["discard:3b"])

    def test_chiitoi_tenpai_discard_preferred_over_breaking_pair(self) -> None:
        """七对听牌：弃单张（保 6 对）排在拆对之前。"""

        hand = ("东", "东", "南", "南", "西", "西", "北", "北", "中", "中", "发", "发", "1w")
        observation = make_observation(my_hand=tuple(Tile(code) for code in hand))
        plan = run_choose(
            _policy(),
            make_request(observation, make_rules(discards_for(("1w", "东")))),
            make_budget(),
        )
        ranks = ranks_by_key(plan)

        self.assertLess(ranks["discard:1w"], ranks["discard:东"])

    def test_luxury_chiitoi_four_of_kind_counts_two_pairs(self) -> None:
        """豪华七对（工程假设）：三个四张 + 单张弃单后听牌，优于拆四张。"""

        hand = ("东", "东", "东", "东", "南", "南", "南", "南", "西", "西", "西", "西", "中")
        observation = make_observation(my_hand=tuple(Tile(code) for code in hand))
        plan = run_choose(
            _policy(),
            make_request(observation, make_rules(discards_for(("中", "东")))),
            make_budget(),
        )
        ranks = ranks_by_key(plan)

        self.assertLess(ranks["discard:中"], ranks["discard:东"])

    def test_joker_tenpai_counts_all_remaining_tiles_effective(self) -> None:
        """财神听牌态（四面子+财神）：任意可摸牌有效，不得清零。"""

        hand = ("1w", "1w", "1w", "2w", "2w", "2w", "3b", "3b", "3b", "4b", "4b", "4b", "白")
        observation = make_observation(my_hand=tuple(Tile(code) for code in hand))
        plan = run_choose(
            _policy(),
            make_request(observation, make_rules(discards_for(("1w",)))),
            make_budget(),
        )

        joined = "；".join(plan.candidates[0].reasons)
        self.assertIn("有效牌34种", joined)

    def test_gang_evaluated_as_waiting_state_without_followup_discard(self) -> None:
        """杠后按 13 张等效等待态直接评估：原因不出现最佳弃牌，排序真实。"""

        hand = ("1w", "2b", "5t", "5w", "6b", "7t", "8t", "9w", "9w", "9w", "9w", "南", "南")
        observation = make_observation(
            my_hand=tuple(Tile(code) for code in hand), drawn_tile=Tile("西")
        )
        candidates = candidates_for(
            [Gang(Tile("9w"), GangKind.CONCEALED), Discard(Tile("1w"))]
        )
        plan = run_choose(_policy(), make_request(observation, make_rules(candidates)), make_budget())

        gang = next(item for item in plan.candidates if item.action_key.startswith("gang:"))
        self.assertIn("按杠后余牌保守估计", "；".join(gang.reasons))
        self.assertNotIn("最佳弃牌", "；".join(gang.reasons))
        self.assertLess(gang.rank, ranks_by_key(plan)["discard:1w"])


class PreemptionContractTests(unittest.TestCase):
    """主策略必须让出事件循环，应用层 wait_for 才能按保底截止时间抢占。"""

    def test_wait_for_can_preempt_long_scoring_loop(self) -> None:
        """长评分循环在 wait_for 超时后立即被取消，而不是同步跑完。"""

        combos: Tuple[Tuple[str, str, str], ...] = tuple(combinations(sorted(ALL_CODES), 3))[:150]
        chi_actions = [Chi((Tile(a), Tile(b), Tile(c))) for a, b, c in combos]
        observation = make_observation(
            my_hand=tuple(
                Tile(code)
                for code in ("1w", "2w", "4w", "5w", "7w", "8w", "1b", "2b", "3b", "5b", "6b", "3t", "4t")
            ),
            drawn_tile=Tile("6t"),
        )
        request = make_request(observation, make_rules(candidates_for(chi_actions)))
        policy = WeightedHeuristicPolicy()

        async def scenario() -> Tuple[str, float]:
            now = time.monotonic()
            budget = DecisionBudget(now + 5.0, now + 8.0, now + 10.0)
            start = time.perf_counter()
            try:
                await asyncio.wait_for(policy.choose(request, budget), timeout=0.05)
                return "completed", time.perf_counter() - start
            except asyncio.TimeoutError:
                return "timeout", time.perf_counter() - start

        outcome, elapsed = asyncio.run(scenario())

        self.assertEqual(outcome, "timeout")
        self.assertLess(
            elapsed,
            0.5,
            "wait_for 未能在超时后抢占评分循环（耗时 {ms:.0f}ms）".format(ms=elapsed * 1000),
        )


if __name__ == "__main__":
    unittest.main()
