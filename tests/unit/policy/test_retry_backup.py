"""备用选择只读取同次规则合法集；不改紧急身份、不改变原全根评分。"""

from dataclasses import replace
import pytest
from hangma_bot.bootstrap import DEFAULT_RULESET_VERSION, VIP_S02_SOURCE, VIP_S02_ROUTE_LIMITS, VIP_S02_PROJECTION_LIMITS
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.policy.retry_backup import rejected_emergency_backup
from hangma_bot.policy.route_vip_heuristic import RouteVipHeuristicPolicy, RouteHeuristicResearchError
from .support import make_budget, make_observation, make_request, rejected


@pytest.fixture
def decision_request():
    config = RuleConfig(DEFAULT_RULESET_VERSION, 1, False)
    visible = make_observation(my_hand=tuple(Tile(code) for code in ("1w", "2w", "3w", "1t", "2t", "3t",
        "1b", "2b", "3b", "7w", "8w", "东", "东")), drawn_tile=Tile("南"), hand_counts=(14, 13, 13, 13),
        chain_piao=0, gang_draw=False)
    rules = HangmaRules(config).analyze(visible, route_limits=VIP_S02_ROUTE_LIMITS)
    return make_request(visible, rules)


def test_backup_requires_a_real_rejected_rule_emergency_and_does_not_mutate(decision_request):
    assert rejected_emergency_backup(decision_request) is None
    emergency = decision_request.rules.emergency_candidate
    available = [candidate for candidate in decision_request.rules.legal_candidates if candidate.action_key != emergency.action_key]
    retry = replace(decision_request, rejected_attempts=(rejected(emergency.action_key),))
    backup = rejected_emergency_backup(retry)
    assert backup is min(available, key=lambda candidate: candidate.action_key)
    assert retry.rules is decision_request.rules
    assert retry.rules.emergency_candidate is emergency
    assert backup is not emergency
    assert rejected_emergency_backup(replace(decision_request, rules=replace(decision_request.rules, emergency_candidate=None))) is None
    assert rejected_emergency_backup(replace(decision_request, rejected_attempts=tuple(rejected(candidate.action_key)
        for candidate in decision_request.rules.legal_candidates))) is None
    assert rejected_emergency_backup(replace(decision_request, rejected_attempts=(rejected(available[0].action_key),))) is None


async def test_rejection_of_emergency_preserves_all_other_original_scores(decision_request):
    policy = RouteVipHeuristicPolicy(RuleConfig(DEFAULT_RULESET_VERSION, 1, False), source=VIP_S02_SOURCE,
        max_operations=4_800_000, projection_limits=VIP_S02_PROJECTION_LIMITS)
    before = await policy.choose(decision_request, make_budget())
    rejected_key = decision_request.rules.emergency_candidate.action_key
    after = await policy.choose(replace(decision_request, rejected_attempts=(rejected(rejected_key),)), make_budget())
    assert [(candidate.action_key, candidate.total_score, candidate.score_parts, candidate.score_trace)
        for candidate in after.candidates] == [(candidate.action_key, candidate.total_score, candidate.score_parts, candidate.score_trace)
        for candidate in before.candidates if candidate.action_key != rejected_key]
    assert not any(candidate.is_emergency for candidate in after.candidates)
    assert not after.degraded_reasons


async def test_missing_emergency_and_all_rejected_remain_explicit_failure(decision_request):
    policy = RouteVipHeuristicPolicy(RuleConfig(DEFAULT_RULESET_VERSION, 1, False), source=VIP_S02_SOURCE,
        max_operations=4_800_000, projection_limits=VIP_S02_PROJECTION_LIMITS)
    for changed in [replace(decision_request, rules=replace(decision_request.rules, emergency_candidate=None)),
        replace(decision_request, rejected_attempts=tuple(rejected(candidate.action_key) for candidate in decision_request.rules.legal_candidates))]:
        with pytest.raises(RouteHeuristicResearchError, match="NO_EMERGENCY"):
            await policy.choose(changed, make_budget())
