"""普通下一摸支付只来自公开规则见证；未知、当前胡和不同包络严格分离。"""

import hashlib
import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.hangma.route_transition import analyze_waiting_draw_witness
from hangma_bot.hangma.route_structure import ROUTE_STRUCTURE_SCHEMA_VERSION
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER, Tile, WindowKey, WindowPhase
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import CompetitionContext, PublicDiscard
from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
from hangma_bot.policy.action_value_executor import ActionValueExecutor
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy.route_heuristic_view import (
    VIP_NORMAL_DRAW_HU_PAYMENT_SEMANTICS_VERSION,
    VIP_ROUTE_GRAPH_SCHEMA_VERSION, VIP_ROUTE_SCORING_VIEW_SCHEMA_VERSION,
)
from hangma_bot.policy.route_vip_heuristic import (
    VIP_ROUTE_HEURISTIC_SEED_SOURCE, RouteVipHeuristicPolicy, build_vip_route_scoring_view,
)

from .support import make_observation, make_budget, run_choose


CONFIG = RuleConfig("vip-normal-payment-test", 1, False)
READY = ("1w", "2w", "3w", "1t", "2t", "3t", "1b", "2b", "3b", "7w", "8w", "白", "白")


def request_from_observation(observation, config=CONFIG):
    """只由真实HangmaRules分析玩家可见观察，窗口键不携未来信息。"""
    analysis = HangmaRules(config).analyze(observation, route_limits=ValueAnalysisLimits(max_expansions=8192))
    trigger_seq = observation.snapshot_seq if observation.consumed_seq is None else observation.consumed_seq
    window = WindowKey(observation.game_id, observation.round_no, trigger_seq,
                       WindowPhase(observation.phase), observation.seat)
    return DecisionRequest(observation, CompetitionContext(
        "vip-payment-test", None, None, None, None, (), 0), analysis,
        "vip-payment-test", window.trigger_seq, window, ())


def ready_request(wall=60):
    """构造合法多白等待前驱的摸牌窗，不伪造胡资格或向听。"""
    return request_from_observation(make_observation(
        my_hand=tuple(Tile(code) for code in READY), drawn_tile=Tile("东"),
        hand_counts=(14, 13, 13, 13), remaining_tile_count=wall, chain_piao=0, gang_draw=False))


@pytest.fixture(scope="module")
def ready_view():
    return build_vip_route_scoring_view(ready_request(), CONFIG)


@pytest.fixture(scope="module")
def p3_requests_and_views():
    """只读取封存的原行动前观察；不消费旧评分、赢家或教师结局。"""
    base = Path("review/vip-route-2026-09-30/evidence/t3-highfan-diagnostic-2/run-1")
    seal_raw = (base / "seal.json").read_bytes()
    assert hashlib.sha256(seal_raw).hexdigest() == "852360582ed7e077ee89f101e9298644a2d98e25e2053b69ec4dde1a9a907ca1"
    raw = (base / "inputs.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == json.loads(seal_raw)["files"]["inputs.json"]["sha256"]
    config = RuleConfig("hangma-mvp-v10-public-counts", 1, False)
    result = {}
    for case in json.loads(raw)["roots"]:
        if case["seed"] not in (3704, 2298):
            continue
        observation = observation_from_json(case["observation"])
        request = request_from_observation(observation, config)
        assert request.window_key == window_key_from_json(case["window_key"])
        assert sorted(candidate.action_key for candidate in request.rules.legal_candidates) == case["legal_action_keys"]
        result[case["seed"]] = (request, build_vip_route_scoring_view(request, config), config)
    return result


def test_3704_current96_and_conditional192_384_stay_separate_without_extra_queries(p3_requests_and_views):
    request, view, config = p3_requests_and_views[3704]
    current = next(node for node in view.nodes if node.node_key == "hu")
    wait = next(node for node in view.nodes if node.node_key == "discard:6w")
    assert current.settlement.fan == 4
    assert current.settlement.score_delta == (96, -32, -32, -32)
    assert wait.settlement is None
    payments = wait.waiting.normal_draw_hu_payments
    assert len(payments) == 64
    assert view.waiting_draw_witness_count == 6542  # v1同根已封存计数；支付表不增加规则调用
    assert view.target_distance_evaluation_count == 30554
    assert len(view.nodes) == 259
    assert sum(len(node.children) for node in view.nodes) == 250
    for restricted in (False, True):
        rows = [row for row in payments if row.catch_restricted is restricted]
        assert len(rows) == 32
        natural = [row for row in rows if row.draw_code != "白"]
        white = next(row for row in rows if row.draw_code == "白")
        assert sum(row.draw_capacity_before for row in natural) == 71
        assert all(row.settlement.fan == 8 and row.settlement.score_delta == (192, -64, -64, -64)
                   for row in natural)
        assert white.draw_capacity_before == 1
        assert white.settlement.fan == 16 and white.settlement.score_delta == (384, -128, -128, -128)
    assert {row.draw_code for row in payments} == set(wait.waiting.legal_hu_draw_codes)
    assert all(row.ruleset_version == config.ruleset_version and row.winner_seat == row.dealer_seat == 0
               and row.wall_remaining_before_draw == 42 and row.wall_remaining_after_draw == 41
               and row.chain_count == row.chain_piao == 0 and row.baotou_after_draw
               and row.draw_kind == "normal" and row.local_witness_only for row in payments)
    # 独立完整动作入口仍保留；两个不同支付各抽一个码核同源结算。
    state = next(root.branches[0].state for root in request.rules.conditional_roots
                 if root.action_key == "discard:6w")
    for code in ("5w", "白"):
        full = analyze_waiting_draw_witness(state, Tile(code), wall_remaining_before_draw=42,
                                           catch_restricted=True, config=config)
        row = next(row for row in payments if row.draw_code == code and row.catch_restricted)
        assert row.settlement == full.immediate_settlement


def test_2298_wall23_is_only_local_given_draw_scope(p3_requests_and_views):
    _, view, _ = p3_requests_and_views[2298]
    assert next(node.settlement.score_delta[0] for node in view.nodes if node.node_key == "hu") == 24
    payments = next(node.waiting.normal_draw_hu_payments for node in view.nodes if node.node_key == "discard:6w")
    assert payments
    assert all(row.wall_remaining_before_draw == 23 and row.wall_remaining_after_draw == 22
               and row.scope == "local_given_normal_draw_hu_only" and row.local_witness_only
               and row.settlement.fan == 1 for row in payments)
    # 表没有下一本人回合必达、概率或期望积分；23张不构造第四次普通摸牌的承诺。
    mapping = view.candidate_view()
    row = next(node["waiting"]["normal_draw_hu_payments"][0] for node in mapping["nodes"]
               if node["node_key"] == "discard:6w")
    assert "probability" not in row and "expected_value" not in row


@pytest.mark.parametrize("wall", (20, 21))
def test_wall_reserve_and_last_legal_draw_keep_empty_versus_payment(wall):
    view = build_vip_route_scoring_view(ready_request(wall), CONFIG)
    waiting = next(node.waiting for node in view.nodes if node.node_key == "discard:东")
    if wall == 20:
        assert waiting.legal_hu_draw_codes == waiting.normal_draw_hu_payments == ()
    else:
        assert waiting.normal_draw_hu_payments
        assert all(row.wall_remaining_before_draw == 21 and row.wall_remaining_after_draw == 20
                   for row in waiting.normal_draw_hu_payments)


@pytest.mark.parametrize("evidence,capacity", (("exact", 0), ("unknown", None), ("conservative", 0)))
def test_zero_capacity_excludes_and_partial_unknown_keeps_known_rows(evidence, capacity):
    request = ready_request()
    root = next(root for root in request.rules.conditional_roots if root.action_key == "discard:东")
    index = CANONICAL_TILE_ORDER.index("9w")
    state = replace(root.branches[0].state,
        unseen_capacities=root.branches[0].state.unseen_capacities[:index] + (capacity,) + root.branches[0].state.unseen_capacities[index + 1:],
        unseen_evidence=root.branches[0].state.unseen_evidence[:index] + (evidence,) + root.branches[0].state.unseen_evidence[index + 1:])
    altered = replace(root, branches=(replace(root.branches[0], state=state),))
    changed = replace(request, rules=replace(request.rules, conditional_roots=tuple(
        altered if item.action_key == root.action_key else item for item in request.rules.conditional_roots)))
    view = build_vip_route_scoring_view(changed, CONFIG)
    waiting = next(node.waiting for node in view.nodes if node.node_key == "discard:东")
    assert waiting.normal_draw_hu_payments  # 其他精确码的已知事实不被删除
    assert "9w" not in {row.draw_code for row in waiting.normal_draw_hu_payments}
    assert ("9w" in waiting.qualification_unknown_codes) == (evidence != "exact")


@pytest.mark.parametrize("changes", (
    {"catch_restricted": 1}, {"baotou_after_draw": 1}, {"winner_seat": True},
    {"dealer_seat": -1}, {"dealer_seat": True}, {"wall_remaining_before_draw": True},
    {"wall_remaining_before_draw": 20}, {"wall_remaining_after_draw": True},
    {"draw_capacity_before": True}, {"draw_capacity_before": 0}, {"draw_capacity_after": True},
    {"chain_count": True}, {"chain_piao": None}, {"chain_piao": True}, {"chain_piao": -1},
    {"draw_code": "5z"}, {"ruleset_version": ""}, {"settlement": None},
))
def test_public_payment_type_rejects_invalid_facts_without_bool_integer_coercion(ready_view, changes):
    payment = next(node.waiting.normal_draw_hu_payments[0] for node in ready_view.nodes
                   if node.waiting and node.waiting.normal_draw_hu_payments)
    with pytest.raises(ValueError):
        replace(payment, **changes)


@pytest.mark.parametrize("bad_delta", ((True, -1, 0, 0), (3, -1, -1), (3, -1, -1, 0), [3, -1, -1, -1]))
def test_payment_rejects_noninteger_or_nonconserved_four_seat_vector(ready_view, bad_delta):
    payment = next(node.waiting.normal_draw_hu_payments[0] for node in ready_view.nodes
                   if node.waiting and node.waiting.normal_draw_hu_payments)
    with pytest.raises(ValueError):
        replace(payment, settlement=replace(payment.settlement, score_delta=bad_delta))


@pytest.mark.parametrize("changes", ({"fan": True}, {"fan": 0}, {"details": ["结算"]}, {"details": (1,)}))
def test_payment_rejects_invalid_settlement_fan_and_detail_types(ready_view, changes):
    payment = next(node.waiting.normal_draw_hu_payments[0] for node in ready_view.nodes
                   if node.waiting and node.waiting.normal_draw_hu_payments)
    with pytest.raises(ValueError):
        replace(payment, settlement=replace(payment.settlement, **changes))


def test_public_waiting_rejects_duplicate_scope_mismatch_and_capacity_drift(ready_view):
    waiting = next(node.waiting for node in ready_view.nodes if node.node_key == "discard:东")
    rows = waiting.normal_draw_hu_payments
    for bad in (rows + (rows[0],), rows[1:], tuple(reversed(rows)), None):
        with pytest.raises(ValueError):
            replace(waiting, normal_draw_hu_payments=bad)
    changed = replace(rows[0], draw_capacity_before=1, draw_capacity_after=0)
    if rows[0].draw_capacity_before == 1:
        changed = replace(rows[0], draw_capacity_before=2, draw_capacity_after=1)
    with pytest.raises(ValueError):
        replace(waiting, normal_draw_hu_payments=(changed,) + rows[1:])
    with pytest.raises(ValueError):
        replace(waiting, qualification_unknown_codes=(rows[0].draw_code,))
    with pytest.raises(ValueError):
        replace(waiting, qualification_scope="unanalysed", qualification_missing_reason="未知补牌",
                legal_hu_draw_codes=None, normal_draw_hu_payments=None)


def test_projection_retains_existing_witness_results_without_additional_calls(monkeypatch):
    from hangma_bot.policy import route_vip_heuristic

    original = route_vip_heuristic.analyze_waiting_hu_witness
    calls = []

    def counted(*args, **kwargs):
        calls.append((args[1].code, kwargs["catch_restricted"]))
        return original(*args, **kwargs)

    monkeypatch.setattr(route_vip_heuristic, "analyze_waiting_hu_witness", counted)
    view = build_vip_route_scoring_view(ready_request(), CONFIG)
    assert len(calls) == view.waiting_draw_witness_count
    assert any(node.waiting.normal_draw_hu_payments for node in view.nodes if node.waiting)


@pytest.mark.parametrize("changes", ({"winner_seat": 1}, {"dealer_seat": 1}, {"ruleset_version": "other"}))
def test_outer_view_rejects_payment_rule_and_seat_binding_drift(ready_view, changes):
    node = next(node for node in ready_view.nodes if node.node_key == "discard:东")
    waiting = replace(node.waiting, normal_draw_hu_payments=tuple(
        replace(row, **changes) for row in node.waiting.normal_draw_hu_payments))
    altered = replace(node, waiting=waiting)
    with pytest.raises(ValueError):
        replace(ready_view, nodes=tuple(altered if n.node_key == node.node_key else n for n in ready_view.nodes))


def test_v2_binding_frozen_payment_and_fresh_mapping_do_not_rewrite_structure_semantics(ready_view):
    assert ready_view.schema_version == VIP_ROUTE_SCORING_VIEW_SCHEMA_VERSION == "vip-route-scoring-view/2"
    mapping = ready_view.candidate_view()
    assert mapping["candidate_kind"] == "vip_route_heuristic_v1"
    assert mapping["graph_schema_version"] == VIP_ROUTE_GRAPH_SCHEMA_VERSION == "vip-route-action-graph/2"
    assert mapping["binding"]["structure_semantics_version"] == ROUTE_STRUCTURE_SCHEMA_VERSION == "vip-route-structure/1"
    assert mapping["binding"]["normal_draw_hu_payment_semantics_version"] == VIP_NORMAL_DRAW_HU_PAYMENT_SEMANTICS_VERSION
    row = next(node.waiting.normal_draw_hu_payments[0] for node in ready_view.nodes
               if node.waiting and node.waiting.normal_draw_hu_payments)
    with pytest.raises(FrozenInstanceError):
        row.chain_piao = 2
    primitive = next(node["waiting"]["normal_draw_hu_payments"][0] for node in mapping["nodes"]
                     if node["node_key"] == "discard:东")
    primitive["settlement"]["score_delta"] = ()
    assert ready_view.candidate_view() != mapping
    with pytest.raises(ValueError):
        replace(ready_view, normal_draw_hu_payment_semantics_version="stale")


def test_compatible_v1_source_runs_v2_without_any_admission_or_completion_claim(ready_view):
    scored = ActionValueExecutor(VIP_ROUTE_HEURISTIC_SEED_SOURCE).score_vip_route(ready_view)
    assert {entry.action_key for entry in scored.entries} == set(ready_view.expected_action_keys())
    serialized = json.dumps(ready_view.candidate_view())
    assert "admitted" not in serialized and "complete_table" not in serialized


def test_policy_trace_binds_view_and_payment_semantics():
    plan = run_choose(RouteVipHeuristicPolicy(CONFIG), ready_request(), make_budget())
    assert all(candidate.score_trace["view_schema_version"] == "vip-route-scoring-view/2"
               and candidate.score_trace["normal_draw_hu_payment_semantics_version"]
               == VIP_NORMAL_DRAW_HU_PAYMENT_SEMANTICS_VERSION for candidate in plan.candidates)


def test_claim_followup_payments_are_normal_draw_after_explicit_award_and_discard():
    observation = make_observation(
        phase="response_chi", turn_seat=3, responding_seats=(0,),
        my_hand=tuple(Tile(code) for code in ("1w", "2w", "1b", "2b", "3b", "4b", "5b", "6b", "7t", "8t", "9t", "白", "白")),
        discards=((), (), (), (Tile("3w"),)), last_discard=PublicDiscard(3, Tile("3w"), 10),
        hand_counts=(13, 13, 13, 13), chain_piao=0, gang_draw=False)
    request = request_from_observation(observation)
    view = build_vip_route_scoring_view(request, CONFIG)
    action = next(action for action in view.actions if action.action_key == "chi:1w,2w,3w")
    assert action.pending_condition == "claim_awarded_if_own_claim_others_pass_and_removed_from_river"
    nodes = {node.node_key: node for node in view.nodes}
    waiting_nodes = [nodes[key] for key in nodes[action.node_key].children if nodes[key].kind == "wait"]
    assert waiting_nodes
    payments = [row for node in waiting_nodes for row in node.waiting.normal_draw_hu_payments]
    assert payments and all(row.draw_kind == "normal" and row.local_witness_only for row in payments)
    assert all(node.settlement is None and node.followup_key for node in waiting_nodes)


def test_unknown_replacement_has_no_payment_table_and_known_replacement_hu_stays_in_hu_leaf():
    hand = ("1w", "1w", "1w", "1w", "2b", "3b", "4b", "5b", "6b", "7b", "7t", "8t", "白")
    request = request_from_observation(make_observation(
        my_hand=tuple(Tile(code) for code in hand), drawn_tile=Tile("白"), hand_counts=(14, 13, 13, 13),
        remaining_tile_count=60, chain_piao=0, gang_draw=False))
    root = next(root for root in request.rules.conditional_roots if root.action_key == "gang:concealed:1w")
    state = root.branches[0].state
    index = CANONICAL_TILE_ORDER.index("9t")
    state = replace(state, unseen_capacities=state.unseen_capacities[:index] + (None,) + state.unseen_capacities[index + 1:],
                    unseen_evidence=state.unseen_evidence[:index] + ("unknown",) + state.unseen_evidence[index + 1:])
    altered = replace(root, branches=(replace(root.branches[0], state=state),))
    request = replace(request, rules=replace(request.rules, conditional_roots=tuple(
        altered if item.action_key == root.action_key else item for item in request.rules.conditional_roots)))
    view = build_vip_route_scoring_view(request, CONFIG)
    unknown = next(node for node in view.nodes if node.kind == "unknown_draw")
    assert unknown.waiting.normal_draw_hu_payments is None
    assert unknown.waiting.legal_hu_draw_codes is None and unknown.waiting.qualification_missing_reason
    conditional_hu = [node for node in view.nodes if node.kind == "hu" and node.node_key.startswith("gang:")]
    assert conditional_hu and all(node.waiting is None and node.settlement for node in conditional_hu)
    waits = [node for node in view.nodes if node.kind == "wait" and node.node_key.startswith("gang:")]
    assert any(node.waiting.normal_draw_hu_payments for node in waits)
    assert all(row.draw_kind == "normal" and row.wall_remaining_before_draw == 59
               for node in waits for row in node.waiting.normal_draw_hu_payments)
