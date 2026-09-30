"""公开模拟帧、唯一规则、v2支付映射与受限执行器的跨模块契约。"""

from dataclasses import replace

import pytest

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.policy.action_value_executor import ActionValueExecutor
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy.route_heuristic_view import (
    VIP_NORMAL_DRAW_HU_PAYMENT_SEMANTICS_VERSION, VIP_ROUTE_CANDIDATE_KIND,
)
from hangma_bot.policy.route_vip_heuristic import build_vip_route_scoring_view, compute_vip_candidate_identity
from hangma_bot.simulation import MatchSpec, SimulationEngine


READ_PAYMENT_SOURCE = '''
def score_actions(view):
    entries = []
    node_indexes = {node["node_key"]: index for index, node in enumerate(view["nodes"])}
    for action in view["actions"]:
        node = view["nodes"][node_indexes[action["node_key"]]]
        payments = None if node["waiting"] is None else node["waiting"]["normal_draw_hu_payments"]
        known_rows = 0 if payments is None else len(payments)
        entries.append({"action_key":action["action_key"], "score":float(known_rows), "trace":{
            "payment_semantics":view["binding"]["normal_draw_hu_payment_semantics_version"],
            "known_local_rows":known_rows,
        }})
    return {"status":"SCORED", "entries":entries}
'''


@pytest.fixture(scope="module")
def simulation_view():
    """只将公开模拟首帧的本座观察送入生产规则与视图，不读取世界私有字段。"""
    config = RuleConfig("vip-payment-contract", 1, False)
    rules = HangmaRules(config)
    engine = SimulationEngine(rules)
    spec = MatchSpec("vip-payment-contract", "vip-payment-contract",
        TournamentConfig(1, 1, config, TimingConfig(1, 1, 3)), 13, 0, (0, 0, 0, 0))
    decision = engine.frame(engine.start(spec)).decisions[0]
    analysis = rules.analyze(decision.observation, route_limits=ValueAnalysisLimits(max_expansions=8192))
    request = DecisionRequest(decision.observation, CompetitionContext(
        "vip-payment-contract", None, None, None, None, (), 0), analysis,
        "vip-payment-contract", decision.window_key.trigger_seq, decision.window_key, ())
    return build_vip_route_scoring_view(request, config)


def test_public_v2_payment_mapping_is_consumable_by_exact_executor_type(simulation_view):
    result = ActionValueExecutor(READ_PAYMENT_SOURCE).score_vip_route(simulation_view)
    assert {entry.action_key for entry in result.entries} == set(simulation_view.expected_action_keys())
    assert all(entry.trace["payment_semantics"] == VIP_NORMAL_DRAW_HU_PAYMENT_SEMANTICS_VERSION
               for entry in result.entries)
    mapping = simulation_view.candidate_view()
    assert mapping["schema_version"] == "vip-route-scoring-view/2"
    assert mapping["graph_schema_version"] == "vip-route-action-graph/2"
    assert mapping["candidate_kind"] == VIP_ROUTE_CANDIDATE_KIND == "vip_route_heuristic_v1"
    assert all("normal_draw_hu_payments" in node["waiting"]
               for node in mapping["nodes"] if node["waiting"] is not None)
    with pytest.raises(ValueError, match="VipRouteScoringView"):
        ActionValueExecutor(READ_PAYMENT_SOURCE).score_vip_route(mapping)


def test_v1_schema_cannot_be_relabelled_as_current_type_or_completion(simulation_view):
    with pytest.raises(ValueError, match="版本"):
        replace(simulation_view, schema_version="vip-route-scoring-view/1")
    mapping = simulation_view.candidate_view()
    assert "admitted" not in mapping and "complete_table" not in mapping


def test_new_identity_explicitly_binds_conditional_payment_semantics(monkeypatch):
    from hangma_bot.policy import route_vip_heuristic

    original = compute_vip_candidate_identity(READ_PAYMENT_SOURCE, "new-contract", "dependencies")
    monkeypatch.setattr(route_vip_heuristic, "VIP_NORMAL_DRAW_HU_PAYMENT_SEMANTICS_VERSION", "different-semantics")
    changed = compute_vip_candidate_identity(READ_PAYMENT_SOURCE, "new-contract", "dependencies")
    assert original != changed
