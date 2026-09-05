"""第一阶段接口基线值对象的最小契约测试。"""

import unittest

from hangma_bot.application.contracts import (
    ActionAttempt,
    ParticipantTerminalReason,
    RuntimeMode,
    RuntimeTarget,
    SubmitAmbiguous,
    SubmitRejectedRetryable,
)
from hangma_bot.kernel.actions import Discard, Tile, WindowKey, WindowPhase, action_key
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.policy.interface import DecisionBudget


class ValueContractTests(unittest.TestCase):
    """防止实施过程中无意改变跨模块语义。"""

    def test_response_phases_are_different_windows(self) -> None:
        """同一弃牌的碰与吃必须使用不同窗口键。"""

        common = {"game_id": "g1", "round_no": 1, "trigger_seq": 12, "seat": 2}
        peng = WindowKey(phase=WindowPhase.RESPONSE_PENG, **common)
        chi = WindowKey(phase=WindowPhase.RESPONSE_CHI, **common)
        self.assertNotEqual(peng, chi)

    def test_action_key_is_deterministic(self) -> None:
        """同一规范动作必须产生相同排除键。"""

        self.assertEqual(action_key(Discard(Tile("1w"))), "discard:1w")

    def test_rule_config_rejects_non_positive_base(self) -> None:
        """错误规则配置应在组合阶段失败，而不是进入动作窗口。"""

        with self.assertRaises(ValueError):
            RuleConfig(ruleset_version="test", base_score=0, you_cai_bi_kao=False)

    def test_ambiguous_outcome_has_no_retry_window(self) -> None:
        """模糊提交类型不能携带允许重试的刷新窗口。"""

        outcome = SubmitAmbiguous(recovery_id="r1", reason="timeout")
        self.assertFalse(hasattr(outcome, "refreshed_window"))
        self.assertIn("refreshed_window", SubmitRejectedRetryable.__dataclass_fields__)

    def test_decision_deadlines_must_be_ordered(self) -> None:
        """刷新窗口不能通过构造反向预算变相延长增强计算。"""

        with self.assertRaises(ValueError):
            DecisionBudget(
                enhancement_deadline_monotonic=3.0,
                fallback_deadline_monotonic=2.0,
                latest_send_at_monotonic=4.0,
            )

    def test_action_attempt_rejects_mismatched_key(self) -> None:
        """协议适配器不能收到与动作内容不一致的审计/排除键。"""

        with self.assertRaises(ValueError):
            ActionAttempt(
                decision_id="d1",
                attempt_no=1,
                plan_revision=1,
                window_key=WindowKey(
                    game_id="g1",
                    round_no=1,
                    trigger_seq=12,
                    phase=WindowPhase.DRAW,
                    seat=0,
                ),
                based_on_authoritative_seq=12,
                action=Discard(Tile("1w")),
                action_key="discard:2w",
                latest_send_at_monotonic=3.0,
            )

    def test_auto_match_mode_vocabulary(self) -> None:
        """AUTO_MATCH 及其专用终态原因按 parallel-v1 冻结值存在（§3.3）。"""

        self.assertEqual(RuntimeMode.AUTO_MATCH.value, "auto_match")
        self.assertEqual(
            ParticipantTerminalReason.MATCHING_UNAVAILABLE.value, "matching_unavailable"
        )
        self.assertEqual(ParticipantTerminalReason.CAPACITY_LIMIT.value, "capacity_limit")

    def test_runtime_target_requires_target_outside_auto_match(self) -> None:
        """只有 AUTO_MATCH 允许空 expected_tournament_id 表示尚未发现自动房。"""

        with self.assertRaises(ValueError):
            RuntimeTarget(
                mode=RuntimeMode.OFFICIAL_TOURNAMENT,
                expected_tournament_id="",
                known_guide_version=15,
            )
        target = RuntimeTarget(
            mode=RuntimeMode.AUTO_MATCH, expected_tournament_id="", known_guide_version=15
        )
        self.assertEqual(target.expected_tournament_id, "")


if __name__ == "__main__":
    unittest.main()
