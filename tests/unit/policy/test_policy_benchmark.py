"""1 秒动作窗口基准：主启发式必须在保底截止时间前完成。

2026-09-04 契约收口后，向听/有效牌数学由 hangma 的候选事实生产承担；
本基准测量「规则引擎分析 + 主策略排序」的完整热路径（真实候选与事实），
断言阈值取 0.5 秒（窗口预算的一半），远大于实际耗时；真实耗时写入
失败消息，便于回归时报告。
"""

from __future__ import annotations

import asyncio
import time
import unittest

from hangma_bot.kernel.actions import Tile
from hangma_bot.policy import WeightedHeuristicPolicy
from hangma_bot.policy.interface import DecisionBudget

from .support import make_observation, make_request, rules_from_engine, run_choose

# 14 张等效、多动作族的重负载窗口手牌：弃牌族全开 + 可杠/可胡分支。
HEAVY_HAND = (
    "1w", "2w", "4w", "5w", "7w", "8w",
    "1b", "2b", "3b", "5b", "6b",
    "3t", "4t", "6t",
)


class BenchmarkTests(unittest.TestCase):
    """主启发式是分层评分，不允许出现复杂搜索。"""

    def test_heavy_window_completes_well_within_budget(self) -> None:
        """重负载窗口（引擎分析 + 主策略）多次运行，最差耗时远低于 0.5 秒。"""

        observation = make_observation(
            my_hand=tuple(Tile(code) for code in HEAVY_HAND[:13]),
            drawn_tile=Tile(HEAVY_HAND[13]),
        )
        analysis = rules_from_engine(observation)
        request = make_request(observation, analysis)
        policy = WeightedHeuristicPolicy()

        durations = []
        for _ in range(5):
            now = time.monotonic()
            budget = DecisionBudget(now + 0.9, now + 1.8, now + 2.7)
            start = time.perf_counter()
            plan = run_choose(policy, request, budget)
            durations.append(time.perf_counter() - start)
            self.assertTrue(plan.candidates)

        worst = max(durations)
        self.assertLess(
            worst,
            0.5,
            "重负载窗口最差耗时 {ms:.1f}ms 超过基准阈值".format(ms=worst * 1000),
        )

    def test_single_window_latency_reported(self) -> None:
        """单次耗时基准：供验收报告引用（不做硬断言，只记下量级）。"""

        observation = make_observation(
            my_hand=tuple(Tile(code) for code in HEAVY_HAND[:13]),
            drawn_tile=Tile(HEAVY_HAND[13]),
        )
        analysis = rules_from_engine(observation)
        request = make_request(observation, analysis)
        policy = WeightedHeuristicPolicy()

        now = time.monotonic()
        budget = DecisionBudget(now + 0.9, now + 1.8, now + 2.7)
        start = time.perf_counter()
        plan = run_choose(policy, request, budget)
        elapsed = time.perf_counter() - start

        self.assertTrue(plan.candidates)
        # 防御性上限：正常应小于 0.2 秒；超过说明引入了复杂搜索。
        self.assertLess(elapsed, 0.2)


if __name__ == "__main__":
    unittest.main()

