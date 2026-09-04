"""超时契约、异常语义与模块纯净性（无网络/文件副作用）。"""

from __future__ import annotations

import unittest
from pathlib import Path

from hangma_bot.kernel.actions import Peng, Tile, WindowPhase
from hangma_bot.policy import (
    PolicyError,
    PolicyTimeoutError,
    SafeFallbackPolicy,
    WeightedHeuristicPolicy,
)

from .support import (
    candidates_for,
    discards_for,
    make_budget,
    make_observation,
    make_request,
    make_rules,
    run_choose,
)

POLICY_PACKAGE_DIR = Path(__file__).resolve().parents[3] / "src" / "hangma_bot" / "policy"

# 禁止出现在策略源码中的副作用痕迹；命中即违反模块边界。
FORBIDDEN_TOKENS = (
    "import socket",
    "import urllib",
    "import httpx",
    "import requests",
    "import aiohttp",
    "import subprocess",
    "import shutil",
    "import tempfile",
    "import os",
    "import random",
    "open(",
    "os.remove",
    "Path(",
    ".write_text",
    ".read_text",
)


class SteppingClock:
    """每次读取前进一秒的注入时钟，用于触发评分中段超时。"""

    def __init__(self, step: float = 1.0) -> None:
        self.now = 0.0
        self.step = step

    def __call__(self) -> float:
        self.now += self.step
        return self.now


class TimeoutContractTests(unittest.TestCase):
    """超时必须显式失败，让应用层切换到紧急保底计划。"""

    def test_entry_past_enhancement_deadline_raises(self) -> None:
        """进入策略时已过增强截止时间，立即抛 PolicyTimeoutError。"""

        candidates = discards_for(("1w", "2w"))
        request = make_request(make_observation(my_hand=(Tile("1w"), Tile("2w"))), make_rules(candidates))
        late = WeightedHeuristicPolicy(monotonic=lambda: 999.0)

        with self.assertRaises(PolicyTimeoutError):
            run_choose(late, request, make_budget(enhancement=100.0))

    def test_timeout_error_is_policy_error_subtype(self) -> None:
        """应用层可以用 PolicyError 统一捕获策略失败。"""

        self.assertTrue(issubclass(PolicyTimeoutError, PolicyError))

    def test_mid_scoring_timeout_raises(self) -> None:
        """评分循环中超过截止时间同样抛出，不吞时间预算。"""

        candidates = discards_for(
            ("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "2b", "3b")
        )
        observation = make_observation(
            my_hand=tuple(Tile(code) for code in ("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w", "1b", "2b", "3b", "4t")),
            drawn_tile=Tile("4t"),
        )
        request = make_request(observation, make_rules(candidates))
        stepping = SteppingClock(step=1.0)
        policy = WeightedHeuristicPolicy(monotonic=stepping)

        with self.assertRaises(PolicyTimeoutError):
            run_choose(policy, request, make_budget(enhancement=5.0))

    def test_future_deadline_completes_normally(self) -> None:
        """截止时间充裕时同样的请求正常返回完整计划。"""

        candidates = discards_for(("1w", "2w"))
        request = make_request(make_observation(my_hand=(Tile("1w"), Tile("2w"))), make_rules(candidates))
        policy = WeightedHeuristicPolicy(monotonic=lambda: 0.0)

        plan = run_choose(policy, request, make_budget(enhancement=100.0))
        self.assertEqual(len(plan.candidates), 2)

    def test_fallback_policy_never_times_out(self) -> None:
        """保底策略不读时钟：过期预算下仍立即返回计划。"""

        candidates = discards_for(("1w",))
        request = make_request(
            make_observation(my_hand=(Tile("1w"),)),
            make_rules(candidates, emergency=candidates[0]),
        )
        plan = run_choose(SafeFallbackPolicy(), request, make_budget(enhancement=-1.0, fallback=0.0, latest=1.0))
        self.assertEqual(len(plan.candidates), 1)


class PolicyErrorContractTests(unittest.TestCase):
    """非超时策略异常的契约：可捕获、可定位，应用层据此切换保底。"""

    def test_empty_hand_after_claim_raises_policy_error(self) -> None:
        """鸣牌后手牌为空（极端观察）抛 PolicyError 且文案含动作键。"""

        observation = make_observation(my_hand=(Tile("5w"), Tile("5w")))
        request = make_request(
            observation,
            make_rules(candidates_for([Peng(Tile("5w"))])),
            phase=WindowPhase.RESPONSE_PENG,
        )
        policy = WeightedHeuristicPolicy(monotonic=lambda: 0.0)

        with self.assertRaises(PolicyError) as caught:
            run_choose(policy, request, make_budget())
        self.assertIn("peng:5w", str(caught.exception))


class ModulePurityTests(unittest.TestCase):
    """策略模块自身不得引入网络或文件副作用。"""

    def test_policy_sources_contain_no_side_effect_tokens(self) -> None:
        """源码静态扫描：不出现网络客户端、进程或磁盘写入痕迹。"""

        sources = sorted(POLICY_PACKAGE_DIR.glob("*.py"))
        self.assertGreaterEqual(len(sources), 6)
        for path in sources:
            text = path.read_text(encoding="utf-8")
            for token in FORBIDDEN_TOKENS:
                self.assertNotIn(
                    token,
                    text,
                    "policy 源码 {name} 含禁止痕迹 {token}".format(name=path.name, token=token),
                )


if __name__ == "__main__":
    unittest.main()
