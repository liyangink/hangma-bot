"""SafeFallbackPolicy 的行为契约：只保留紧急候选且永不失败。"""

from __future__ import annotations

import unittest

from hangma_bot.hangma.interface import RuleCompleteness, RuleIssue
from hangma_bot.policy import SafeFallbackPolicy

from .support import (
    discards_for,
    make_budget,
    make_observation,
    make_request,
    make_rules,
    rejected,
    run_choose,
)


class SafeFallbackPolicyTests(unittest.TestCase):
    """保底策略只消费规则紧急候选，不做任何增强计算。"""

    def test_emergency_candidate_becomes_single_plan(self) -> None:
        """紧急候选存在且未拒绝时，输出 rank=1 的单候选计划。"""

        candidates = discards_for(("1w", "2w"))
        request = make_request(
            make_observation(),
            make_rules(candidates, emergency=candidates[0]),
        )
        plan = run_choose(SafeFallbackPolicy(), request, make_budget())

        self.assertEqual(plan.decision_id, "d1")
        self.assertEqual(len(plan.candidates), 1)
        only = plan.candidates[0]
        self.assertEqual(only.action_key, "discard:1w")
        self.assertEqual(only.rank, 1)
        self.assertTrue(only.is_emergency)
        self.assertEqual(plan.revision, 1)
        self.assertEqual(plan.based_on_authoritative_seq, 10)
        self.assertTrue(plan.degraded_reasons[0].startswith("保底策略"))

    def test_missing_emergency_returns_empty_plan_without_raising(self) -> None:
        """规则无法提供紧急候选时返回空计划，而不是抛异常。"""

        request = make_request(
            make_observation(),
            make_rules(discards_for(("1w",)), emergency=None),
        )
        plan = run_choose(SafeFallbackPolicy(), request, make_budget())

        self.assertEqual(plan.candidates, ())
        self.assertTrue(any("规则未提供紧急候选" in reason for reason in plan.degraded_reasons))

    def test_rejected_emergency_excluded_with_reason(self) -> None:
        """紧急候选已被官方拒绝时输出空计划并说明原因。"""

        candidates = discards_for(("1w",))
        request = make_request(
            make_observation(),
            make_rules(candidates, emergency=candidates[0]),
            rejected=(rejected("discard:1w"),),
        )
        plan = run_choose(SafeFallbackPolicy(), request, make_budget())

        self.assertEqual(plan.candidates, ())
        self.assertTrue(
            any("紧急候选已被官方拒绝" in reason for reason in plan.degraded_reasons)
        )
        self.assertEqual(plan.revision, 2)

    def test_degraded_rules_still_produce_plan(self) -> None:
        """规则分析 DEGRADED 时保底计划仍可用，降级原因可审计。"""

        candidates = discards_for(("1w",))
        request = make_request(
            make_observation(),
            make_rules(
                candidates,
                emergency=candidates[0],
                completeness=RuleCompleteness.DEGRADED,
                issues=(RuleIssue(area="hu", reason="胡牌分支超时"),),
            ),
        )
        plan = run_choose(SafeFallbackPolicy(), request, make_budget())

        self.assertEqual(len(plan.candidates), 1)
        joined = "；".join(plan.degraded_reasons)
        self.assertIn("规则降级[hu]", joined)

    def test_budget_is_not_consulted(self) -> None:
        """保底策略不读时钟：已过期的预算也不影响输出。"""

        candidates = discards_for(("1w",))
        request = make_request(
            make_observation(),
            make_rules(candidates, emergency=candidates[0]),
        )
        expired = make_budget(enhancement=-1.0, fallback=0.0, latest=1.0)
        plan = run_choose(SafeFallbackPolicy(), request, expired)

        self.assertEqual(len(plan.candidates), 1)


if __name__ == "__main__":
    unittest.main()
