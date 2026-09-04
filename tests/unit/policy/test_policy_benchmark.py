"""1 秒动作窗口基准：主启发式必须在保底截止时间前完成。

断言阈值取 0.5 秒（窗口预算的一半），远大于实际耗时；
真实耗时写入失败消息，便于回归时报告。
"""

from __future__ import annotations

import asyncio
import time
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
)
from hangma_bot.policy import WeightedHeuristicPolicy
from hangma_bot.policy.interface import DecisionBudget

from .support import candidates_for, make_observation, make_request, make_rules

# 14 张等效、多动作族混出的重负载窗口：弃牌 + 吃 + 碰 + 杠 + 胡 + 过。
HEAVY_HAND = (
    "1w", "2w", "4w", "5w", "7w", "8w",
    "1b", "2b", "3b", "5b", "6b",
    "3t", "4t", "6t",
)


class BenchmarkTests(unittest.TestCase):
    """主启发式是纯分层评分，不允许出现复杂搜索。"""

    def test_heavy_window_completes_well_within_budget(self) -> None:
        """重负载窗口多次运行，最差耗时也远低于 0.5 秒。"""

        observation = make_observation(
            my_hand=tuple(Tile(code) for code in HEAVY_HAND[:13]),
            drawn_tile=Tile(HEAVY_HAND[13]),
        )
        # 候选故意超现实（手牌只有 1 张 1b 仍含碰/暗杠 1b、缺 3w 仍含吃）：
        # 策略不判合法性，全部走最重的后续弃牌评估路径以放大负载；
        # 维护时不要按真实牌形“修正”，否则基准负载形状会悄悄下降。
        actions = [Discard(Tile(code)) for code in sorted(set(HEAVY_HAND))]
        actions.extend(
            [
                Chi((Tile("1w"), Tile("2w"), Tile("3w"))),
                Peng(Tile("1b")),
                Peng(Tile("2b")),
                Gang(Tile("1b"), GangKind.CONCEALED),
                Gang(Tile("2b"), GangKind.EXPOSED),
                Hu(),
                Pass(),
            ]
        )
        request = make_request(observation, make_rules(candidates_for(actions)))
        policy = WeightedHeuristicPolicy()

        durations = []
        for _ in range(5):
            now = time.monotonic()
            budget = DecisionBudget(now + 0.9, now + 1.8, now + 2.7)
            start = time.perf_counter()
            plan = asyncio.run(policy.choose(request, budget))
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
        actions = [Discard(Tile(code)) for code in sorted(set(HEAVY_HAND))]
        request = make_request(observation, make_rules(candidates_for(actions)))
        policy = WeightedHeuristicPolicy()

        now = time.monotonic()
        budget = DecisionBudget(now + 0.9, now + 1.8, now + 2.7)
        start = time.perf_counter()
        plan = asyncio.run(policy.choose(request, budget))
        elapsed = time.perf_counter() - start

        self.assertTrue(plan.candidates)
        # 防御性上限：正常应小于 0.2 秒；超过说明引入了复杂搜索。
        self.assertLess(elapsed, 0.2)


if __name__ == "__main__":
    unittest.main()
