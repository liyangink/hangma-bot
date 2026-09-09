"""保财是策略偏好：规则仍允许普通弃白，强制白和独立退路可用。"""

import pytest

from hangma_bot.hangma import HangmaRules
from hangma_bot.kernel.actions import Discard, Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import RulePublicState
from hangma_bot.policy import (
    ComparableHeuristicPolicyV2,
    SafeFallbackPolicy,
    WhiteDiscardGuardPolicy,
)
from tests.unit.policy.support import make_budget, make_observation, make_request, run_choose


@pytest.mark.parametrize("forced", [False, True])
def test_rule_legality_policy_preference_and_emergency_remain_distinct(forced):
    """同一真实规则结果同时供主策略和保底消费，策略过滤不改合法集。"""

    observation = make_observation(
        my_hand=tuple(Tile(code) for code in "1w 2w 3w 4w 5w 6w 7w 8w 9w 东 南 西 白 白".split()),
        drawn_tile=Tile("白"),
        rule_state=RulePublicState(Tile("白"), False, 0, forced),
    )
    rules = HangmaRules(RuleConfig("white-guard-contract", 1, True))
    analysis = rules.analyze(observation)
    request = make_request(observation, analysis)
    original_keys = tuple(candidate.action_key for candidate in analysis.legal_candidates)
    policy = WhiteDiscardGuardPolicy(ComparableHeuristicPolicyV2(monotonic=lambda: 0))

    plan = run_choose(policy, request, make_budget())
    fallback = run_choose(SafeFallbackPolicy(), request, make_budget())

    assert "discard:白" in original_keys
    assert rules.validate(observation, Discard(Tile("白"))).legal
    assert tuple(candidate.action_key for candidate in analysis.legal_candidates) == original_keys
    assert [candidate.rank for candidate in plan.candidates] == list(range(1, len(plan.candidates) + 1))
    assert all(candidate.action_key in original_keys for candidate in plan.candidates)
    assert any(candidate.is_emergency for candidate in plan.candidates)
    assert fallback.candidates[0].action_key == ("discard:白" if forced else "discard:西")
    assert ("discard:白" in {candidate.action_key for candidate in plan.candidates}) is forced
