"""规则、只读视图、受限评分与严格研究包装的跨模块契约。"""

import asyncio

import pytest

from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.policy.action_value import SCORING_VIEW_SCHEMA_VERSION
from hangma_bot.policy.action_value_executor import ActionValueExecutor
from hangma_bot.policy.action_value_policy import build_scoring_view
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy.route_heuristic_view import VIP_ROUTE_SCORING_VIEW_SCHEMA_VERSION
from hangma_bot.policy.route_vip_heuristic import (
    RouteHeuristicResearchError, RouteVipHeuristicPolicy, build_vip_route_scoring_view,
)
from hangma_bot.simulation import MatchSpec, SimulationEngine


COMPLETE_SOURCE = '''
def score_actions(view):
    entries = []
    for action in view["actions"]:
        entries.append({"action_key": action["action_key"], "score": 0.0, "trace": {}})
    return {"status": "SCORED", "entries": entries}
'''


@pytest.fixture(scope="module")
def contract_request():
    """从公开模拟帧取本座观察，再通过生产规则接口取得同次全合法根。"""

    rules = HangmaRules(RuleConfig("vip-route-scoring-contract", 1, False))
    engine = SimulationEngine(rules)
    config = TournamentConfig(1, 1, rules.config, TimingConfig(1, 1, 3))
    spec = MatchSpec("vip-contract", "vip-contract", config, 13, 0, (0, 0, 0, 0))
    decision = engine.frame(engine.start(spec)).decisions[0]
    observation = decision.observation
    analysis = rules.analyze(observation, route_limits=ValueAnalysisLimits(max_expansions=8192))
    request = DecisionRequest(
        observation, CompetitionContext("vip-contract", None, None, None, None, (), 0),
        analysis, "vip-contract-decision", decision.window_key.trigger_seq,
        decision.window_key, (),
    )
    return rules.config, request


def test_new_precise_view_entry_and_legacy_entry_are_separate(contract_request):
    config, request = contract_request
    vip = build_vip_route_scoring_view(request, config)
    legacy = build_scoring_view(request, value_limits=ValueAnalysisLimits(max_expansions=8192))
    assert vip.schema_version == VIP_ROUTE_SCORING_VIEW_SCHEMA_VERSION
    assert legacy.schema_version == SCORING_VIEW_SCHEMA_VERSION == "sitin-scoring-view/4"
    executor = ActionValueExecutor(COMPLETE_SOURCE)
    current = executor.score_vip_route(vip)
    previous = executor.score(legacy)
    expected = {item.action_key for item in request.rules.legal_candidates}
    assert {item.action_key for item in current.entries} == expected
    assert {item.action_key for item in previous.entries} == expected
    with pytest.raises(ValueError, match="ScoringView"):
        executor.score(vip)
    with pytest.raises(ValueError, match="VipRouteScoringView"):
        executor.score_vip_route(legacy)


def test_incomplete_or_duplicate_batch_cannot_pass_new_scoring_seam(contract_request):
    config, request = contract_request
    view = build_vip_route_scoring_view(request, config)
    omitted = COMPLETE_SOURCE.replace('"entries": entries}', '"entries": entries[:1]}')
    duplicated = COMPLETE_SOURCE.replace('"entries": entries}', '"entries": entries + [entries[0]]}')
    for source in (omitted, duplicated):
        with pytest.raises(ValueError):
            ActionValueExecutor(source).score_vip_route(view)


@pytest.mark.parametrize("source,operations,category", (
    ('def score_actions(view):\n return {"status":"ABSTAIN","reason":"契约故障注入"}', 100_000, "ABSTAIN"),
    ('def score_actions(view):\n return {"status":"SCORED","entries":[]}', 100_000, "SCORING_FAILED"),
    (COMPLETE_SOURCE, 8, "WORKLOAD_EXCEEDED"),
))
def test_scoring_failure_is_unfinished_despite_available_legal_backup(
    contract_request, source, operations, category,
):
    config, request = contract_request
    policy = RouteVipHeuristicPolicy(config, source=source, max_operations=operations)
    budget = BudgetPolicy().build(800, 3)
    assert asyncio.run(policy.emergency_policy.choose(request, budget)).candidates
    with pytest.raises(RouteHeuristicResearchError) as failure:
        asyncio.run(policy.choose(request, budget))
    assert failure.value.category == category
