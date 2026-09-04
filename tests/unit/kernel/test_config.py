"""kernel.config 的单元测试：正数配置、有限秒数与不可变性。"""

import math
import unittest
from dataclasses import FrozenInstanceError

from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig


def _rule_config(**overrides: object) -> RuleConfig:
    base = {"ruleset_version": "hangma-v1", "base_score": 8, "you_cai_bi_kao": False}
    base.update(overrides)
    return RuleConfig(**base)  # type: ignore[arg-type]


def _timing_config(**overrides: object) -> TimingConfig:
    base = {
        "peng_timeout_sec": 1.0,
        "chi_timeout_sec": 1.0,
        "discard_timeout_sec": 3.0,
    }
    base.update(overrides)
    return TimingConfig(**base)  # type: ignore[arg-type]


class RuleConfigTests(unittest.TestCase):
    """规则配置必须在组合阶段失败，而不是进入动作窗口后失败。"""

    def test_rejects_non_positive_or_malformed_base_score(self) -> None:
        for bad in (0, -1, True, "8", 8.0, None):
            with self.assertRaises(ValueError):
                _rule_config(base_score=bad)

    def test_rejects_empty_version_and_non_bool_switch(self) -> None:
        with self.assertRaises(ValueError):
            _rule_config(ruleset_version="")
        with self.assertRaises(ValueError):
            _rule_config(you_cai_bi_kao=1)

    def test_immutable_and_deterministic_equality(self) -> None:
        config = _rule_config()
        with self.assertRaises(FrozenInstanceError):
            config.base_score = 9  # type: ignore[misc]
        self.assertEqual(config, _rule_config())
        self.assertEqual(hash(config), hash(_rule_config()))


class TimingConfigTests(unittest.TestCase):
    """动作窗口秒数必须为正且有限。"""

    def test_rejects_non_positive_or_non_finite_seconds(self) -> None:
        """NaN 与 inf 会绕过普通数值比较，必须显式拒绝。"""
        for bad in (0, -1.5, math.nan, math.inf, -math.inf, True, "1.0"):
            with self.assertRaises(ValueError):
                _timing_config(peng_timeout_sec=bad)
            with self.assertRaises(ValueError):
                _timing_config(chi_timeout_sec=bad)
            with self.assertRaises(ValueError):
                _timing_config(discard_timeout_sec=bad)

    def test_accepts_positive_seconds(self) -> None:
        config = _timing_config(peng_timeout_sec=1, chi_timeout_sec=1.5, discard_timeout_sec=3)
        self.assertEqual(config.discard_timeout_sec, 3)


class TournamentConfigTests(unittest.TestCase):
    """并发场次与局数必须为正整数，组件类型必须正确。"""

    def _config(self, **overrides: object) -> TournamentConfig:
        base = {
            "max_games": 2,
            "rounds_per_game": 4,
            "rules": _rule_config(),
            "timing": _timing_config(),
        }
        base.update(overrides)
        return TournamentConfig(**base)  # type: ignore[arg-type]

    def test_rejects_non_positive_counts(self) -> None:
        for bad in (0, -2, True, "2"):
            with self.assertRaises(ValueError):
                self._config(max_games=bad)
            with self.assertRaises(ValueError):
                self._config(rounds_per_game=bad)

    def test_rejects_wrong_component_types(self) -> None:
        with self.assertRaises(ValueError):
            self._config(rules={"ruleset_version": "x"})
        with self.assertRaises(ValueError):
            self._config(timing=None)

    def test_immutable_and_equal(self) -> None:
        config = self._config()
        with self.assertRaises(FrozenInstanceError):
            config.max_games = 3  # type: ignore[misc]
        self.assertEqual(config, self._config())


if __name__ == "__main__":
    unittest.main()
