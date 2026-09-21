"""R18 机会能力评测接缝：完整 oracle、缺值退出和正式策略配对。"""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from hangma_bot.kernel.actions import Discard, Tile
from hangma_bot.offline.opportunity_capability import (
    OpportunityCapabilityCase,
    OracleActionValue,
    evaluate_case,
    evaluate_pair,
    summarize_family,
)
from hangma_bot.policy.interface import DecisionPlan, RankedCandidate
from tests.unit.policy.support import (
    candidates_for,
    make_budget,
    make_observation,
    make_request,
    make_rules,
)


class FixedPolicy:
    """只用于验证离线接缝；返回题面已有动作，不实现规则。"""

    def __init__(self, action_key):
        self.action_key = action_key

    async def choose(self, request, budget):
        del budget
        candidate = next(
            item for item in request.rules.legal_candidates
            if item.action_key == self.action_key
        )
        ranked = RankedCandidate(
            action=candidate.action,
            action_key=candidate.action_key,
            rank=1,
            total_score=0.0,
            score_parts=(),
            reasons=("固定测试策略",),
        )
        return DecisionPlan(
            decision_id=request.decision_id,
            window_key=request.window_key,
            based_on_authoritative_seq=request.trigger_seq,
            revision=1,
            candidates=(ranked,),
            degraded_reasons=(),
        )


def _case(values):
    actions = candidates_for((Discard(Tile("1w")), Discard(Tile("2w"))))
    request = make_request(make_observation(), make_rules(actions))
    return OpportunityCapabilityCase(
        case_id="case-1",
        base_scenario_id="base-1",
        family="multi_wealth_baotou",
        split="development",
        generator_seed=2026092201,
        rules_hash="rules-hash",
        generator_sha256="generator-hash",
        oracle_version="test-oracle/1",
        oracle_level="declared_conditional_proxy",
        request_sha256="request-hash",
        reachability_witness_sha256="witness-hash",
        request=request,
        action_values=tuple(
            OracleActionValue(
                action_key=item[0],
                value=item[1],
                error_bound=item[2] if len(item) > 2 else 0.0,
                oracle_level="declared_conditional_proxy",
                evidence="测试条件代理",
            )
            for item in values
        ),
    )


def test_pair_reports_candidate_regret_improvement_over_v2():
    case = _case((("discard:1w", 1.0), ("discard:2w", 3.0)))

    result = asyncio.run(
        evaluate_pair(
            FixedPolicy("discard:2w"),
            FixedPolicy("discard:1w"),
            case,
            make_budget,
        )
    )

    assert result.candidate.status == "SCORED"
    assert result.candidate.regret == 0.0
    assert result.baseline.regret == 2.0
    assert result.capability_gain == 2.0
    assert result.capability_gain_lower == 2.0
    assert result.capability_gain_upper == 2.0


def test_missing_legal_action_value_exits_scoring_instead_of_false_hit():
    case = _case((("discard:1w", 1.0),))

    result = asyncio.run(evaluate_case(FixedPolicy("discard:1w"), case, make_budget()))

    assert result.status == "ORACLE_INCOMPLETE"
    assert result.regret is None
    assert result.optimal_action_keys == ()


def test_oracle_rejects_action_not_in_rule_legal_set():
    case = _case((("discard:1w", 1.0), ("discard:2w", 3.0)))

    with pytest.raises(ValueError, match="非法动作"):
        replace(
            case,
            action_values=case.action_values + (
                OracleActionValue(
                    "discard:3w", 4.0, 0.0,
                    "declared_conditional_proxy", "测试非法动作",
                ),
            ),
        )


def test_error_bounds_produce_conservative_paired_gain_interval():
    case = _case((("discard:1w", 1.0, 0.25), ("discard:2w", 3.0, 0.5)))

    result = asyncio.run(
        evaluate_pair(
            FixedPolicy("discard:2w"),
            FixedPolicy("discard:1w"),
            case,
            make_budget,
        )
    )

    assert result.candidate.regret == 0.0
    assert result.candidate.regret_lower == 0.0
    assert result.candidate.regret_upper == 1.0
    assert result.baseline.regret == 2.0
    assert result.baseline.regret_lower == 1.25
    assert result.baseline.regret_upper == 2.75
    assert result.capability_gain == 2.0
    assert result.capability_gain_lower == 0.25
    assert result.capability_gain_upper == 2.75


def test_family_summary_weights_base_scenarios_instead_of_expanded_cases():
    first = _case((("discard:1w", 0.0), ("discard:2w", 10.0)))
    second = replace(first, case_id="case-2")
    third = replace(first, case_id="case-3", base_scenario_id="base-2")
    rows = [
        asyncio.run(evaluate_pair(FixedPolicy("discard:2w"), FixedPolicy("discard:1w"), case, make_budget))
        for case in (first, second)
    ]
    rows.append(
        asyncio.run(evaluate_pair(FixedPolicy("discard:1w"), FixedPolicy("discard:2w"), third, make_budget))
    )

    summary = summarize_family(
        rows,
        family="multi_wealth_baotou",
        split="development",
    )

    assert summary.case_count == 3
    assert summary.base_scenario_count == 2
    # base-1 = +10，base-2 = -10；两个基础场景等权后为 0。
    assert summary.mean_capability_gain == 0.0
    assert summary.candidate_optimal_hit_rate == 0.5
