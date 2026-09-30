"""新版只读事实、全合法动作、严格未完成与统一排名尺度的接口测试。"""

import gzip
import json
from dataclasses import FrozenInstanceError, replace

import pytest

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import RuleIssue, ValueAnalysisLimits
from hangma_bot.hangma.route_frontier import RouteGapKind
from hangma_bot.hangma.route_transition import analyze_waiting_draw_witness
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER, Hu, Tile, WindowPhase
from hangma_bot.kernel.observation import PublicDiscard
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.serialization import observation_from_json
from hangma_bot.policy.action_value import SCORING_VIEW_SCHEMA_VERSION
from hangma_bot.policy.action_value_executor import ActionValueExecutor, WorkloadExceeded
from hangma_bot.policy.route_heuristic_view import (
    VIP_ROUTE_SCORING_VIEW_SCHEMA_VERSION, run_vip_route_scoring_skeleton,
)
from hangma_bot.policy.route_vip_heuristic import (
    VIP_ROUTE_HEURISTIC_SEED_SOURCE, RouteHeuristicResearchError,
    RouteVipHeuristicPolicy, VipRouteProjectionLimits,
    build_vip_route_scoring_view, compute_vip_candidate_identity,
)

from .support import make_budget, make_observation, make_request, rejected, run_choose


CONFIG = RuleConfig("vip-route-policy-test", 1, False)


def _request(observation):
    """用实际规则产生同次全合法根，不伪造数学或动作合法性。"""

    rules = HangmaRules(CONFIG).analyze(
        observation, route_limits=ValueAnalysisLimits(max_expansions=8192))
    return make_request(observation, rules, phase=WindowPhase(observation.phase))


def _draw_observation(hand, drawn="东", *, wall=60, catch=False):
    return make_observation(
        my_hand=tuple(Tile(code) for code in hand), drawn_tile=Tile(drawn),
        hand_counts=(len(hand) + 1, 13, 13, 13),
        remaining_tile_count=wall, chain_piao=0, gang_draw=False,
        rule_state=replace(make_observation().rule_state, catch_play=catch,
                           catch_play_owner_seat=1 if catch else None),
    )


@pytest.fixture(scope="module")
def ready_request():
    return _request(_draw_observation((
        "1w", "2w", "3w", "1t", "2t", "3t", "1b", "2b", "3b",
        "7w", "8w", "白", "白",
    )))


@pytest.fixture(scope="module")
def representative_requests():
    """旧机械题账只取行动前公开观察，不消费教师价值或牌局结局。"""

    path = ("review/vip-route-2026-09-30/evidence/"
            "p3-all-action-teacher-20260930/report.json.gz")
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        rows = json.load(handle)["rows"]
    selected = {}
    for row in rows:
        for key in row["legal_action_keys"]:
            selected.setdefault(key.split(":")[0], row["observation"])
    assert set(selected) == {"discard", "hu", "pass", "chi", "peng", "gang"}
    return {family: _request(observation_from_json(data))
            for family, data in selected.items()}


@pytest.mark.parametrize("family", ("discard", "hu", "pass", "chi", "peng", "gang"))
def test_seed_scores_every_legal_root_without_internal_fallback(representative_requests, family):
    request = representative_requests[family]
    policy = RouteVipHeuristicPolicy(CONFIG)
    plan = run_choose(policy, request, make_budget())
    assert {item.action_key for item in plan.candidates} == {
        item.action_key for item in request.rules.legal_candidates}
    assert [item.rank for item in plan.candidates] == list(range(1, len(plan.candidates) + 1))
    assert not plan.degraded_reasons
    assert policy.executor.last_operation_count <= 100_000
    assert all(item.score_trace["detail"]["unit"] == "heuristic_rank_points"
               for item in plan.candidates)


def test_new_view_keeps_old_schema_and_excludes_all_score_and_pressure_fields(ready_request):
    view = build_vip_route_scoring_view(ready_request, CONFIG)
    mapping = view.candidate_view()
    assert SCORING_VIEW_SCHEMA_VERSION == "sitin-scoring-view/4"
    assert view.schema_version == VIP_ROUTE_SCORING_VIEW_SCHEMA_VERSION
    assert "competition" not in mapping
    serialized = json.dumps(mapping, ensure_ascii=False)
    for name in ("table_scores", "stage_scores", "participant_rank", "stage_no", "tournament_id"):
        assert name not in serialized
    assert mapping["tile_order"] == CANONICAL_TILE_ORDER
    assert mapping["tile_order"][33] == "白"
    waiting = next(node.waiting for node in view.nodes if node.kind == "wait")
    assert waiting.structure.whites_held == 2 or waiting.structure.whites_held == 1
    assert len(waiting.unseen_capacities) == len(mapping["tile_order"]) == 34
    assert mapping["limits"]["max_waiting_draw_witnesses"] == 16384
    assert mapping["workload"]["waiting_draw_witness_count"] > 0


def test_score_pressure_changes_do_not_change_candidate_mapping_or_plan(ready_request):
    pressured = replace(
        ready_request,
        observation=replace(ready_request.observation, scores=(1000, -1, 99, -1098)),
        competition=replace(ready_request.competition, stage_no=3,
                            stage_role="final", participant_rank=4),
    )
    before = build_vip_route_scoring_view(ready_request, CONFIG).candidate_view()
    after = build_vip_route_scoring_view(pressured, CONFIG).candidate_view()
    assert before == after
    policy = RouteVipHeuristicPolicy(CONFIG)
    a = run_choose(policy, ready_request, make_budget())
    b = run_choose(policy, pressured, make_budget())
    assert [(item.action_key, item.total_score) for item in a.candidates] == [
        (item.action_key, item.total_score) for item in b.candidates]


def test_frozen_view_and_fresh_primitive_maps_cannot_share_candidate_mutation(ready_request):
    view = build_vip_route_scoring_view(ready_request, CONFIG)
    with pytest.raises(FrozenInstanceError):
        view.base_score = 2
    first = view.candidate_view()
    first["visible_state"]["my_hand"] = ()
    first["nodes"][0]["kind"] = "hu"
    assert view.candidate_view()["visible_state"]["my_hand"]
    assert view.candidate_view()["nodes"][0]["kind"] == view.nodes[0].kind
    executor = ActionValueExecutor(VIP_ROUTE_HEURISTIC_SEED_SOURCE)
    with pytest.raises(ValueError, match="ScoringView"):
        executor.score(view)
    with pytest.raises(ValueError, match="VipRouteScoringView"):
        executor.score_vip_route(first)


@pytest.mark.parametrize("source,category", (
    ('def score_actions(view):\n return {"status":"ABSTAIN","reason":"故障注入"}', "ABSTAIN"),
    ('def score_actions(view):\n return {"status":"SCORED","entries":[]}', "SCORING_FAILED"),
    ('def score_actions(view):\n value=1/0\n return value', "SCORING_FAILED"),
))
def test_candidate_failure_is_strictly_unfinished_with_independent_rule_backup(ready_request, source, category):
    policy = RouteVipHeuristicPolicy(CONFIG, source=source)
    emergency = run_choose(policy.emergency_policy, ready_request, make_budget())
    assert emergency.candidates[0].is_emergency
    with pytest.raises(RouteHeuristicResearchError) as error:
        run_choose(policy, ready_request, make_budget())
    assert error.value.category == category


def test_workload_exhaustion_is_not_a_successful_emergency_plan(ready_request):
    policy = RouteVipHeuristicPolicy(CONFIG, max_operations=8)
    with pytest.raises(RouteHeuristicResearchError) as error:
        run_choose(policy, ready_request, make_budget())
    assert error.value.category == "WORKLOAD_EXCEEDED"
    assert policy.executor.last_operation_count > 8


def test_successful_first_choice_equal_to_emergency_is_not_fallback(ready_request):
    emergency_key = ready_request.rules.emergency_candidate.action_key
    source = (
        'def score_actions(view):\n'
        ' entries = []\n'
        ' for action in view["actions"]:\n'
        f'  value = 1.0 if action["action_key"] == {emergency_key!r} else 0.0\n'
        '  entries.append({"action_key":action["action_key"],"score":value,"trace":{}})\n'
        ' return {"status":"SCORED","entries":entries}\n'
    )
    plan = run_choose(RouteVipHeuristicPolicy(CONFIG, source=source), ready_request, make_budget())
    assert plan.candidates[0].is_emergency
    assert not plan.degraded_reasons
    assert len(plan.candidates) == len(ready_request.rules.legal_candidates)


def test_any_normal_root_gap_stops_even_when_that_root_is_rejected(ready_request):
    emergency_key = ready_request.rules.emergency_candidate.action_key
    root = next(root for root in ready_request.rules.conditional_roots if root.action_key != emergency_key)
    broken = replace(root, gap_kind=RouteGapKind.MECHANICAL_GAP,
                     issues=(RuleIssue("test", "注入未实现正常机械"),))
    rules = replace(ready_request.rules, conditional_roots=tuple(
        broken if candidate.action_key == root.action_key else candidate
        for candidate in ready_request.rules.conditional_roots))
    request = replace(ready_request, rules=rules, rejected_attempts=(rejected(root.action_key),))
    with pytest.raises(RouteHeuristicResearchError) as error:
        run_choose(RouteVipHeuristicPolicy(CONFIG), request, make_budget())
    assert error.value.category == "MECHANICAL_GAP"
    assert error.value.action_key == root.action_key


def test_input_rule_binding_and_projection_truncation_are_explicit_failures(ready_request):
    with pytest.raises(RouteHeuristicResearchError, match="INPUT_EVIDENCE_GAP"):
        build_vip_route_scoring_view(ready_request, RuleConfig("wrong", 1, False))
    with pytest.raises(RouteHeuristicResearchError, match="SEARCH_TRUNCATED"):
        build_vip_route_scoring_view(ready_request, CONFIG,
                                    limits=VipRouteProjectionLimits(max_nodes=1))


def test_hu_payment_scale_is_a_normalized_feature_in_the_same_rank_unit(ready_request):
    view = build_vip_route_scoring_view(ready_request, CONFIG)
    scaled = replace(view, base_score=10, nodes=tuple(
        replace(node, settlement=replace(node.settlement, score_delta=tuple(
            amount * 10 for amount in node.settlement.score_delta)))
        if node.kind == "hu" else node for node in view.nodes))
    executor = ActionValueExecutor(VIP_ROUTE_HEURISTIC_SEED_SOURCE)
    a = executor.score_vip_route(view)
    b = executor.score_vip_route(scaled)
    assert [(entry.action_key, entry.score) for entry in a.entries] == [
        (entry.action_key, entry.score) for entry in b.entries]
    hu_node = next(node for node in view.nodes if node.kind == "hu")
    hu_score = next(entry.score for entry in a.entries if entry.action_key == "hu")
    assert hu_score != float(hu_node.settlement.score_delta[view.visible_state.seat])


def test_claim_keeps_all_followup_actions_with_unresolved_root_label(representative_requests):
    request = representative_requests["peng"]
    view = build_vip_route_scoring_view(request, CONFIG)
    by_node = {node.node_key: node for node in view.nodes}
    for action in view.actions:
        if action.action_type not in ("chi", "peng"):
            continue
        assert action.pending_condition == "claim_awarded_if_own_claim_others_pass_and_removed_from_river"
        root = by_node[action.node_key]
        expected = next(candidate.facts.followup_branches for candidate in request.rules.legal_candidates
                        if candidate.action_key == action.action_key)
        assert {by_node[child].followup_key for child in root.children
                if by_node[child].kind == "wait"} == {branch.followup_key for branch in expected}


def test_unknown_replacement_code_is_kept_without_fabricating_exact_capacity(representative_requests):
    request = _request(_draw_observation((
        "1w", "1w", "1w", "1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "东", "南",
    ), drawn="白"))
    root = next(root for root in request.rules.conditional_roots
                if root.action_key.startswith("gang:") and root.proposal_state is None)
    state = root.branches[0].state
    index = next(index for index, capacity in enumerate(state.unseen_capacities)
                 if capacity is not None and capacity > 0 and state.unseen_evidence[index] == "exact")
    code = CANONICAL_TILE_ORDER[index]
    changed_state = replace(
        state,
        unseen_capacities=state.unseen_capacities[:index] + (None,) + state.unseen_capacities[index + 1:],
        unseen_evidence=state.unseen_evidence[:index] + ("unknown",) + state.unseen_evidence[index + 1:],
    )
    changed_root = replace(root, branches=(replace(root.branches[0], state=changed_state),))
    changed_rules = replace(request.rules, conditional_roots=tuple(
        changed_root if item.action_key == root.action_key else item for item in request.rules.conditional_roots))
    view = build_vip_route_scoring_view(replace(request, rules=changed_rules), CONFIG)
    by_key = {node.node_key: node for node in view.nodes}
    gang = by_key[root.action_key]
    assert code in gang.condition_codes
    unknown = by_key[gang.children[gang.condition_codes.index(code)]]
    assert unknown.kind == "unknown_draw"
    assert unknown.uncertainty_reason
    assert unknown.waiting.unseen_capacities[index] is None
    assert unknown.waiting.legal_hu_draw_codes is None
    assert sum(unknown.waiting.structure.natural_counts33) + unknown.waiting.structure.whites_held == 13 - 3 * state.meld_count
    ActionValueExecutor(VIP_ROUTE_HEURISTIC_SEED_SOURCE).score_vip_route(view)


def test_zero_need_predecessor_has_empty_structure_push_and_real_terminal_hu_width(ready_request):
    view = build_vip_route_scoring_view(ready_request, CONFIG)
    waiting = next(node.waiting for node in view.nodes if node.node_key == "discard:东")
    target = next(target for target in waiting.structure.targets
                  if target.family == "standard" and target.retained_whites == 1)
    assert target.natural_need == 0
    assert target.requires_terminal_draw
    assert target.conditional_need_improvement_codes == ()
    assert waiting.legal_hu_draw_codes
    assert waiting.legal_hu_code_width > 0


def test_pattern_width_preserves_both_labels_and_counts_shared_codes_once():
    request = _request(_draw_observation((
        "1w", "1w", "2w", "2w", "3w", "3w", "4w", "4w", "5w", "6w", "7w", "白", "白",
    )))
    view = build_vip_route_scoring_view(request, CONFIG)
    waiting = next(node.waiting for node in view.nodes if node.node_key == "discard:东")
    standard = set(waiting.standard_useful_codes)
    seven = set(waiting.seven_pairs_useful_codes)
    assert standard & seven
    assert set(waiting.useful_codes) == standard | seven | set(waiting.combined_useful_codes)
    assert waiting.useful_code_width <= len(standard | seven | set(waiting.combined_useful_codes))
    assert waiting.useful_code_width < len(standard) + len(seven)
    assert waiting.structure.natural_pair_count == 4
    assert waiting.structure.seven_pairs_shanten == 0


def test_chi_without_draw_keeps_legal_concealed_gang_in_followup_choices():
    hand = ("1w", "2w", "1b", "1b", "1b", "1b", "5w", "6w", "7w", "8w", "9w", "东", "南")
    observation = make_observation(
        phase="response_chi", turn_seat=3, responding_seats=(0,),
        my_hand=tuple(Tile(code) for code in hand),
        discards=((), (), (), (Tile("3w"),)),
        last_discard=PublicDiscard(3, Tile("3w"), 10),
        hand_counts=(13, 13, 13, 13), chain_piao=0, gang_draw=False,
    )
    request = _request(observation)
    view = build_vip_route_scoring_view(request, CONFIG)
    action = next(action for action in view.actions if action.action_key == "chi:1w,2w,3w")
    node = next(node for node in view.nodes if node.node_key == action.node_key)
    by_key = {node.node_key: node for node in view.nodes}
    assert any(child.endswith("/gang:concealed:1b") and by_key[child].kind == "replacement"
               for child in node.children)
    assert any(by_key[child].kind == "wait" for child in node.children)


def test_failed_projection_does_not_reuse_last_scoring_count(ready_request):
    policy = RouteVipHeuristicPolicy(CONFIG)
    run_choose(policy, ready_request, make_budget())
    assert policy.executor.last_operation_count > 0
    missing = replace(ready_request, rules=replace(ready_request.rules, conditional_roots=None))
    with pytest.raises(RouteHeuristicResearchError):
        run_choose(policy, missing, make_budget())
    assert policy.executor.last_operation_count is None


@pytest.mark.parametrize("hand,wall,catch", (
    (("1w", "2w", "3w", "1t", "2t", "3t", "1b", "2b", "3b", "7w", "8w", "白", "白"), 60, False),
    (("1w", "1w", "2w", "2w", "3w", "3w", "4w", "4w", "5w", "6w", "7w", "白", "白"), 60, False),
    (("1w", "2w", "3w", "1t", "2t", "3t", "1b", "2b", "3b", "7w", "8w", "白", "白"), 20, False),
    (("1w", "2w", "3w", "1t", "2t", "3t", "1b", "2b", "3b", "7w", "8w", "白", "白"), 60, True),
))
def test_qualification_query_optimization_matches_all_34_code_rule_queries(hand, wall, catch):
    """多白零缺口、两型交集、末墙、摸切包络逐码对照无减枝规则入口。"""

    request = _request(_draw_observation(hand, drawn="东", wall=wall, catch=catch))
    root = next(root for root in request.rules.conditional_roots if root.action_key == "discard:东")
    state = root.branches[0].state
    view = build_vip_route_scoring_view(request, CONFIG)
    waiting = next(node.waiting for node in view.nodes if node.node_key == "discard:东")
    expected = set()
    if wall > 20:
        for index, code in enumerate(CANONICAL_TILE_ORDER):
            if state.unseen_evidence[index] != "exact" or not state.unseen_capacities[index]:
                continue
            for restricted in (True, False):
                analysis = analyze_waiting_draw_witness(
                    state, Tile(code), wall_remaining_before_draw=wall,
                    catch_restricted=restricted, config=CONFIG)
                if any(isinstance(candidate.action, Hu) for candidate in analysis.legal_candidates):
                    expected.add(code)
    assert set(waiting.legal_hu_draw_codes) == expected
    assert not (expected & set(waiting.qualification_math_closed_codes))


def test_skeleton_rejects_duplicate_missing_foreign_and_nonfinite_entries(ready_request):
    view = build_vip_route_scoring_view(ready_request, CONFIG)
    entries = [{"action_key": key, "score": 0.0, "trace": {}}
               for key in view.expected_action_keys()]
    for bad in (entries[:-1], entries + [entries[0]],
                entries[:-1] + [{"action_key": "foreign", "score": 0.0, "trace": {}}],
                entries[:-1] + [{**entries[-1], "score": float("nan")}]):
        with pytest.raises(ValueError):
            run_vip_route_scoring_skeleton(view, lambda mapping: {"status": "SCORED", "entries": bad})


def test_new_candidate_identity_binds_source_contract_dependencies_and_params():
    source = VIP_ROUTE_HEURISTIC_SEED_SOURCE
    base = compute_vip_candidate_identity(source, "contract", "deps")
    assert len(base) == 64
    assert base == compute_vip_candidate_identity(source, "contract", "deps")
    assert len({base, compute_vip_candidate_identity(source + "\n", "contract", "deps"),
                compute_vip_candidate_identity(source, "contract2", "deps"),
                compute_vip_candidate_identity(source, "contract", "deps2"),
                compute_vip_candidate_identity(source, "contract", "deps", {"seed": 2})}) == 5
