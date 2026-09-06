"""新版过牌事实下，冻结策略保持旧评分，原输入及序列化事实不被改写。"""

import asyncio
from dataclasses import replace

import pytest

from hangma_bot.application.audit_codec import decision_request_to_json, decision_request_from_json
from hangma_bot.hangma.interface import CandidateFacts, CandidateFactKind, RuleCompleteness
from hangma_bot.policy.legacy_pass import LegacyWeightedHeuristicPolicy, LegacyClaimIfLegalPolicy
from hangma_bot.policy import WeightedHeuristicPolicy, ClaimIfLegalPolicy, ReliableHeuristicPolicyV1
from tests.unit.policy.support import make_budget, make_request
from tests.unit.hangma.test_pass_progress import response
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.config import RuleConfig


@pytest.mark.parametrize("old, adapted", [(WeightedHeuristicPolicy, LegacyWeightedHeuristicPolicy), (ClaimIfLegalPolicy, LegacyClaimIfLegalPolicy)])
def test_legacy_view_keeps_original_scores_without_mutating_request(old, adapted):
    obs = response()
    rules = HangmaRules(RuleConfig("pass-contract", 1, False)).analyze(obs)
    request = make_request(obs, rules)
    original = decision_request_to_json(request)
    old_rules = replace(rules, legal_candidates=tuple(
        replace(c, facts=CandidateFacts(CandidateFactKind.NOT_APPLICABLE, None)) if c.action_key == "pass" else c
        for c in rules.legal_candidates
    ))
    expected = asyncio.run(old(monotonic=lambda: 0).choose(replace(request, rules=old_rules), make_budget()))
    actual = asyncio.run(adapted(monotonic=lambda: 0).choose(request, make_budget()))
    assert actual.candidates == expected.candidates
    assert "legacy-pass-neutral-v1" in " ".join(actual.degraded_reasons)
    assert decision_request_to_json(request) == original
    assert decision_request_from_json(original) == request


def test_v1_keeps_neutral_pass_and_failed_fact_is_not_laundered():
    obs = response()
    rules = HangmaRules(RuleConfig("pass-contract", 1, False)).analyze(obs)
    request = make_request(obs, rules)
    v1 = asyncio.run(ReliableHeuristicPolicyV1(monotonic=lambda: 0).choose(request, make_budget()))
    assert next(c for c in v1.candidates if c.action_key == "pass").total_score == 0
    failed = CandidateFacts(CandidateFactKind.ANALYSIS_FAILED, None,
                            completeness=RuleCompleteness.DEGRADED, note="测试失败")
    request = replace(request, rules=replace(rules, legal_candidates=tuple(
        replace(c, facts=failed) if c.action_key == "pass" else c for c in rules.legal_candidates
    )))
    plan = asyncio.run(LegacyWeightedHeuristicPolicy(monotonic=lambda: 0).choose(request, make_budget()))
    assert "legacy-pass-neutral-v1" not in " ".join(plan.degraded_reasons)
    assert "测试失败" in " ".join(next(c for c in plan.candidates if c.action_key == "pass").reasons)
