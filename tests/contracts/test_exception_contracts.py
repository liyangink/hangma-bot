"""跨模块异常契约：未知动作类型的故障隔离必须保持。

kernel-mvp-review 终裁（第 3 轮）确认：`action_key` 对未知类型抛
`TypeError` 是承重契约——`hangma` 验证与 `policy` 候选过滤依赖捕获
`TypeError` 隔离坏候选；曾把它统一为 `ValueError`（RS-3 提案）导致
故障隔离被击穿。本文件把该链路钉进契约层，防止"全绿带病"重演。
"""

import asyncio
import time
import unittest

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import RuleCandidate
from hangma_bot.kernel.actions import Pass, Tile, action_key
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.policy.interface import DecisionBudget, DecisionRequest


def _rule_config() -> RuleConfig:
    return RuleConfig(ruleset_version="contract-test", base_score=8, you_cai_bi_kao=False)


def _observation():
    """最小合法观察；构造细节属于 kernel 公开接口，不依赖内部状态。"""
    from hangma_bot.kernel.observation import (
        PlayerObservation,
        RulePublicState,
    )

    return PlayerObservation(
        game_id="g-contract",
        seat=0,
        round_no=1,
        snapshot_seq=1,
        phase="draw",
        dealer_seat=0,
        turn_seat=0,
        responding_seats=(),
        my_hand=(Tile("1w"), Tile("2w"), Tile("3w")),
        drawn_tile=None,
        discards=((), (), (), ()),
        melds=((), (), (), ()),
        hand_counts=(13, 13, 13, 13),
        last_discard=None,
        remaining_tile_count=None,
        scores=(0, 0, 0, 0),
        rule_state=RulePublicState(
            wealth_god=Tile("白"), baotou=False, chain_count=0, catch_play=False
        ),
        public_history=(),
    )


class UnknownActionIsolationContracts(unittest.TestCase):
    """未知动作类型必须被隔离为结构化结果，而不是泄漏异常。"""

    def test_action_key_unknown_type_raises_type_error(self) -> None:
        """kernel 契约：`action_key` 未知类型抛 `TypeError`。"""
        with self.assertRaises(TypeError):
            action_key(object())

    def test_hangma_validate_isolates_unknown_action(self) -> None:
        """hangma 契约：验证路径把未知动作转为结构化非法结果，不泄漏异常。"""
        rules = HangmaRules(_rule_config())
        verdict = rules.validate(_observation(), object())
        self.assertFalse(verdict.legal)
        self.assertTrue(verdict.reason)

    def test_policy_filtering_isolates_unknown_candidate(self) -> None:
        """policy 契约：候选过滤吞掉未知动作类型的候选，choose 不抛异常。"""
        from hangma_bot.policy.weighted_heuristic import WeightedHeuristicPolicy
        from hangma_bot.kernel.observation import CompetitionContext

        observation = _observation()
        bad_candidate = RuleCandidate(action=object(), action_key="unknown:object", evidence=())
        good_candidate = RuleCandidate(action=Pass(), action_key="pass", evidence=())
        from hangma_bot.hangma.interface import RuleAnalysis, RuleCompleteness

        analysis = RuleAnalysis(
            legal_candidates=(bad_candidate, good_candidate),
            emergency_candidate=None,
            completeness=RuleCompleteness.DEGRADED,
            ruleset_version="contract-test",
            issues=(),
        )
        request = DecisionRequest(
            observation=observation,
            competition=CompetitionContext(
                tournament_id="t-contract",
                stage_no=None,
                stage_role=None,
                stage_total=None,
                participant_rank=None,
                ranking=(),
                observed_at_unix_ms=0,
            ),
            rules=analysis,
            decision_id="d-contract",
            trigger_seq=1,
            window_key=None,  # type: ignore[arg-type]
            rejected_attempts=(),
        )
        # 截止时间是绝对单调时钟秒；给足余量，本用例只测异常隔离不测超时。
        now = time.monotonic()
        budget = DecisionBudget(
            enhancement_deadline_monotonic=now + 10.0,
            fallback_deadline_monotonic=now + 20.0,
            latest_send_at_monotonic=now + 30.0,
        )
        plan = asyncio.run(WeightedHeuristicPolicy().choose(request, budget))
        # 坏候选被隔离；计划仍可产生（允许空候选计划，但不允许异常泄漏）。
        keys = [candidate.action_key for candidate in plan.candidates]
        self.assertNotIn("unknown:object", keys)


if __name__ == "__main__":
    unittest.main()
