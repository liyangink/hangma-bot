"""补牌条件前瞻限深只通过公开构图/选择接口验证，不授实际连续杠限制。"""
from dataclasses import asdict, replace

import pytest

from hangma_bot.hangma import route_transition
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER, Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.policy.route_vip_heuristic import (
    RouteHeuristicResearchError, RouteVipHeuristicPolicy, VipRouteProjectionLimits,
    build_vip_route_scoring_view, compute_vip_candidate_identity,
)

from .support import make_budget, make_observation, make_request, run_choose


CONFIG = RuleConfig("vip-bounded-followup-gang-test", 1, False)


def request(hand, drawn="南", *, seq=10, wall=60):
    """由唯一规则源给出当前全部合法根，只提供本座和公开观察。"""
    observation = make_observation(
        my_hand=tuple(Tile(code) for code in hand), drawn_tile=Tile(drawn),
        hand_counts=(len(hand) + 1, 13, 13, 13), chain_piao=0, gang_draw=False,
        snapshot_seq=seq,
        remaining_tile_count=wall,
    )
    rules = HangmaRules(CONFIG).analyze(
        observation, route_limits=ValueAnalysisLimits(max_expansions=8192))
    return make_request(observation, rules, decision_id="bounded-" + str(seq))


@pytest.fixture(scope="module")
def ordinary_request():
    return request(("1w", "2w", "3w", "1t", "2t", "3t", "1b", "2b", "3b",
                    "7w", "8w", "东", "东"))


@pytest.fixture(scope="module")
def multi_gang_request():
    return request(("1w",) * 4 + ("2w",) * 4 + ("3w", "4w", "5w", "东", "南"), "白")


def limits(depth):
    return VipRouteProjectionLimits(8192, 32768, 65536, max_replacement_depth=depth)


@pytest.fixture(scope="module")
def bounded_view(multi_gang_request):
    return build_vip_route_scoring_view(multi_gang_request, CONFIG, limits=limits(1))


@pytest.mark.parametrize("invalid", (True, False, 0, -1, 1.0, "1", (), []))
def test_depth_limits_reject_bool_and_non_positive_or_non_integer_values(ordinary_request, invalid):
    with pytest.raises(ValueError, match="杠补展开深度"):
        VipRouteProjectionLimits(max_replacement_depth=invalid)
    view = build_vip_route_scoring_view(ordinary_request, CONFIG)
    with pytest.raises(ValueError, match="杠补展开深度"):
        replace(view, max_replacement_depth=invalid)


@pytest.mark.parametrize("depth", (None, 1, 2, 100))
def test_depth_setting_is_explicit_in_typed_view_and_input_limits(ordinary_request, depth):
    configured = VipRouteProjectionLimits(max_replacement_depth=depth)
    view = build_vip_route_scoring_view(ordinary_request, CONFIG, limits=configured)
    assert view.max_replacement_depth == depth
    assert view.candidate_view()["limits"] == asdict(configured)


def test_every_current_gang_root_keeps_all_first_replacement_codes(multi_gang_request, bounded_view):
    assert bounded_view.expected_action_keys() == tuple(sorted(
        item.action_key for item in multi_gang_request.rules.legal_candidates))
    by_node = {node.node_key: node for node in bounded_view.nodes}
    roots = {root.action_key: root for root in multi_gang_request.rules.conditional_roots}
    gangs = [action for action in bounded_view.actions if action.action_type == "gang"]
    assert {action.action_key for action in gangs} == {"gang:concealed:1w", "gang:concealed:2w"}
    for action in gangs:
        initial = roots[action.action_key].branches[0].state
        # 这副公开题形中，当前已知四张暗牌与已亮出的四张杠牌各排除一码。
        expected = tuple(code for code in CANONICAL_TILE_ORDER if code not in ("1w", "2w"))
        node = by_node[action.node_key]
        assert node.kind == "replacement"
        assert node.condition_codes == expected
        assert len(node.children) == len(expected) == 32
        assert node.expected_child_count == node.completed_child_count == 32
        landed = route_transition.apply_given_draw(initial, Tile("东"), replacement=True)
        analysis = route_transition.analyze_given_replacement_draw(
            landed, seat=multi_gang_request.observation.seat,
            dealer_seat=multi_gang_request.observation.dealer_seat, config=CONFIG)
        choices = by_node[node.children[node.condition_codes.index("东")]]
        assert choices.kind == "choices"
        # 完全相同的冻结未知事实可共享节点；node_key 不承诺是当前边的动作名。
        actual_keys = {by_node[child].legal_action_key for child in choices.children
                       if by_node[child].legal_action_key is not None}
        gang_keys = {item.action_key for item in analysis.legal_candidates
                     if item.action_key.startswith("gang:")}
        assert actual_keys == {item.action_key for item in analysis.legal_candidates} - gang_keys
        assert len(choices.children) == len(analysis.legal_candidates)
        assert sum(by_node[child].kind == "unknown_draw" for child in choices.children) == len(gang_keys)


def test_followup_gang_is_explicit_unknown_with_real_waiting_structure(bounded_view):
    unknown = [node for node in bounded_view.nodes if node.kind == "unknown_draw"]
    assert unknown
    for node in unknown:
        assert node.pending_condition == "replacement_draw_not_expanded_after_depth:1"
        assert "后继杠已合法" in node.uncertainty_reason
        assert not node.children and node.settlement is None and node.gap_kind is None
        waiting = node.waiting
        assert waiting.qualification_scope == "unanalysed"
        assert waiting.legal_hu_draw_codes is None
        assert waiting.normal_draw_hu_payments is None
        assert "深度上限" in waiting.qualification_missing_reason
        assert waiting.qualification_unknown_codes
        assert waiting.unseen_evidence == ("exact",) * 34
        assert sum(waiting.structure.natural_counts33) + waiting.structure.whites_held == (
            13 - 3 * waiting.structure.meld_set_count)


def test_explicit_two_layers_matches_full_graph_for_two_available_gangs(multi_gang_request):
    observation = multi_gang_request.observation
    # 墙余仍容许两次杠补；第二次补后到保留区，无第三次条件胡资格查询。
    two_draws = request(tuple(tile.code for tile in observation.my_hand), "白", wall=22)
    unbounded = build_vip_route_scoring_view(two_draws, CONFIG, limits=limits(None))
    two_layers = build_vip_route_scoring_view(two_draws, CONFIG, limits=limits(2))
    assert not any(node.kind == "unknown_draw" for node in two_layers.nodes)
    assert two_layers.nodes == unbounded.nodes
    assert two_layers.actions == unbounded.actions
    assert two_layers.waiting_draw_witness_count == unbounded.waiting_draw_witness_count
    assert two_layers.target_distance_evaluation_count == unbounded.target_distance_evaluation_count


def test_default_none_and_bounded_setting_keep_ordinary_scores_and_detail(ordinary_request):
    original = build_vip_route_scoring_view(ordinary_request, CONFIG)
    explicit = build_vip_route_scoring_view(ordinary_request, CONFIG, limits=VipRouteProjectionLimits(
        max_replacement_depth=None))
    bounded = build_vip_route_scoring_view(ordinary_request, CONFIG, limits=VipRouteProjectionLimits(
        max_replacement_depth=1))
    assert original.candidate_view() == explicit.candidate_view()
    assert bounded.nodes == original.nodes and bounded.actions == original.actions
    plain_policy = RouteVipHeuristicPolicy(CONFIG)
    capped_policy = RouteVipHeuristicPolicy(CONFIG, projection_limits=VipRouteProjectionLimits(
        max_replacement_depth=1))
    before = run_choose(plain_policy, ordinary_request, make_budget())
    after = run_choose(capped_policy, ordinary_request, make_budget())
    assert [(entry.action_key, entry.total_score, entry.score_trace["detail"]) for entry in before.candidates] == [
        (entry.action_key, entry.total_score, entry.score_trace["detail"]) for entry in after.candidates]
    assert all(entry.score_trace["max_replacement_depth"] is None for entry in before.candidates)
    assert all(entry.score_trace["max_replacement_depth"] == 1 for entry in after.candidates)


def test_bounded_choose_keeps_all_roots_and_next_authoritative_window_starts_fresh(multi_gang_request):
    policy = RouteVipHeuristicPolicy(CONFIG, max_operations=2_400_000, projection_limits=limits(1))
    first = run_choose(policy, multi_gang_request, make_budget())
    observation = multi_gang_request.observation
    following = request(tuple(tile.code for tile in observation.my_hand),
                        observation.drawn_tile.code, seq=observation.snapshot_seq + 1)
    second = run_choose(policy, following, make_budget())
    expected = {item.action_key for item in multi_gang_request.rules.legal_candidates}
    assert {item.action_key for item in first.candidates} == expected
    assert {item.action_key for item in second.candidates} == expected
    assert [(item.action_key, item.total_score, item.score_trace["detail"]) for item in first.candidates] == [
        (item.action_key, item.total_score, item.score_trace["detail"]) for item in second.candidates]
    assert not first.degraded_reasons and not second.degraded_reasons
    assert all(item.score_trace["max_replacement_depth"] == 1 for item in first.candidates)


def test_failed_draw_projection_cannot_contaminate_next_choose(monkeypatch, multi_gang_request):
    policy = RouteVipHeuristicPolicy(CONFIG, max_operations=2_400_000, projection_limits=limits(1))
    original = route_transition.apply_given_draw

    def fail(*args, **kwargs):
        raise ValueError("给定补牌测试故障")

    monkeypatch.setattr(route_transition, "apply_given_draw", fail)
    with pytest.raises(RouteHeuristicResearchError, match="给定补牌测试故障"):
        run_choose(policy, multi_gang_request, make_budget())
    assert policy.executor.last_operation_count is None
    monkeypatch.setattr(route_transition, "apply_given_draw", original)
    recovered = run_choose(policy, multi_gang_request, make_budget())
    assert {item.action_key for item in recovered.candidates} == {
        item.action_key for item in multi_gang_request.rules.legal_candidates}
    assert not recovered.degraded_reasons


def test_depth_parameter_changes_candidate_identity():
    first = compute_vip_candidate_identity("same-source", "same-contract", "same-dependencies",
        params={"projection_limits": asdict(limits(None))})
    second = compute_vip_candidate_identity("same-source", "same-contract", "same-dependencies",
        params={"projection_limits": asdict(limits(1))})
    assert first != second


@pytest.mark.parametrize("codes", (["1w"], (True,), ("2w", "1w"), ("1w", "1w"), ("bad",)))
def test_waiting_qualification_code_validation_keeps_rejecting_bad_inputs(ordinary_request, codes):
    view = build_vip_route_scoring_view(ordinary_request, CONFIG)
    waiting = next(node.waiting for node in view.nodes if node.waiting is not None)
    with pytest.raises(ValueError, match="规范牌序去重"):
        replace(waiting, qualification_unknown_codes=codes)
