"""R17 叶视图与固定公开后继归约合同。"""

from __future__ import annotations

from dataclasses import replace

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import PlayerObservation, RulePublicState
from hangma_bot.policy.public_successor_search import (
    MAX_LEAF_EVALUATIONS,
    RootSearchScore,
    SearchReduction,
    order_discard_keys_by_fronts,
    reduce_public_successors,
)

from .support import make_request


def _observation(**overrides) -> PlayerObservation:
    values = dict(
        game_id="r17-search",
        seat=0,
        round_no=3,
        snapshot_seq=20,
        phase="draw",
        dealer_seat=1,
        turn_seat=0,
        responding_seats=(),
        my_hand=tuple(
            Tile(code)
            for code in (
                "1w", "2w", "3w", "4w", "5w", "6w", "7w",
                "8w", "9w", "1b", "2b", "3b", "东",
            )
        ),
        drawn_tile=Tile("南"),
        discards=((), (), (), ()),
        melds=((), (), (), ()),
        hand_counts=(13, 13, 13, 13),
        last_discard=None,
        remaining_tile_count=60,
        scores=(10, -5, 0, -5),
        rule_state=RulePublicState(Tile("白"), False, 0, False),
        public_history=(),
    )
    values.update(overrides)
    return PlayerObservation(**values)


def _inputs(observation=None):
    observation = observation or _observation()
    rules = HangmaRules(RuleConfig("r17-search-test", 1, False))
    analysis = rules.analyze(
        observation,
        value_limits=ValueAnalysisLimits(
            max_expansions=20_000,
            max_routes_per_candidate=128,
        ),
    )
    request = make_request(observation, analysis)
    successors = rules.analyze_public_self_draw_successors(observation)
    return request, successors


def _score(leaf) -> float:
    """有界确定性测试评分；只消费 LeafView，不重算规则。"""

    return max(
        -1.0,
        min(
            1.0,
            -0.2 * leaf.shanten_after
            + 0.01 * leaf.support_remaining
            + (0.02 if leaf.draw_is_currently_useful else 0.0),
        ),
    )


def test_leaf_limit_is_derived_from_complete_rule_graph_shape() -> None:
    assert MAX_LEAF_EVALUATIONS == 14 * 34 * 2 * 18 == 17_136


def test_real_rule_graph_reduces_with_bounded_leaf_views() -> None:
    request, successors = _inputs()
    seen = []

    def scorer(leaf):
        seen.append(leaf)
        return _score(leaf)

    reduced = reduce_public_successors(request, successors, scorer)
    assert reduced.complete, reduced.reason
    assert {item.action_key for item in reduced.roots} == {
        item.action_key
        for item in request.rules.legal_candidates
        if item.action_key.startswith("discard:")
    }
    assert seen
    assert all(item.schema_version == "r17-public-successor-leaf/1" for item in seen)
    assert all(item.window.table_scores == (10, -5, 0, -5) for item in seen)
    assert all(item.root.action_key.startswith("discard:") for item in seen)
    assert sum(item.leaf_evaluations for item in reduced.roots) == len(seen)
    assert all(-1.0 <= item.lower_support_score <= item.upper_support_score <= 1.0 for item in reduced.roots)


def test_reserved_wall_has_zero_successor_scores_and_keeps_v2_order() -> None:
    """末次摸牌后的弃牌没有未来收益；固定归约必须形成全零同层。"""

    request, successors = _inputs(_observation(remaining_tile_count=20))
    seen = []

    def scorer(leaf):
        seen.append(leaf)
        return _score(leaf)

    reduced = reduce_public_successors(request, successors, scorer)
    assert reduced.complete, reduced.reason
    assert seen == []
    assert all(
        item.dominance_vector == (0.0, 0.0, 0.0)
        and item.capacity_total == 0
        and item.leaf_evaluations == 0
        for item in reduced.roots
    )
    baseline = tuple(
        item.action_key
        for item in request.rules.legal_candidates
        if item.action_key.startswith("discard:")
    )
    assert order_discard_keys_by_fronts(reduced, baseline) == baseline


def test_reordering_graph_does_not_change_root_scores() -> None:
    request, successors = _inputs()
    reversed_roots = []
    for root in reversed(successors.roots):
        edges = []
        for edge in reversed(root.edges):
            edges.append(
                replace(
                    edge,
                    restricted=replace(
                        edge.restricted,
                        gang_leaves=tuple(reversed(edge.restricted.gang_leaves)),
                        discard_frontier=tuple(reversed(edge.restricted.discard_frontier)),
                    ),
                    unrestricted=replace(
                        edge.unrestricted,
                        gang_leaves=tuple(reversed(edge.unrestricted.gang_leaves)),
                        discard_frontier=tuple(reversed(edge.unrestricted.discard_frontier)),
                    ),
                )
            )
        reversed_roots.append(replace(root, edges=tuple(edges)))
    shuffled = replace(successors, roots=tuple(reversed_roots))
    assert reduce_public_successors(request, successors, _score) == (
        reduce_public_successors(request, shuffled, _score)
    )


def test_candidate_error_bound_and_operation_budget_fail_whole_window() -> None:
    request, successors = _inputs()
    too_large = reduce_public_successors(request, successors, lambda leaf: 1.01)
    assert not too_large.complete
    assert "[-1, 1]" in too_large.reason

    too_many = reduce_public_successors(
        request, successors, _score, max_leaf_evaluations=1
    )
    assert not too_many.complete
    assert "超过固定上限" in too_many.reason


def test_future_conditional_gang_only_widens_interval() -> None:
    observation = _observation(
        my_hand=tuple(
            Tile(code)
            for code in (
                "1w", "1w", "1w", "2w", "3w", "4w", "5w",
                "6w", "7w", "8w", "9w", "东", "南",
            )
        ),
        drawn_tile=Tile("西"),
        remaining_tile_count=60,
    )
    request, successors = _inputs(observation)

    def prefer_gang(leaf):
        return 1.0 if leaf.next_action_type == "gang" else -1.0

    reduced = reduce_public_successors(request, successors, prefer_gang)
    assert reduced.complete, reduced.reason
    assert any(
        item.upper_support_score > item.lower_support_score
        for item in reduced.roots
    )


def _root(key, hu, lower, upper):
    return RootSearchScore(key, lower, upper, hu, 0, 100, 1)


def test_pareto_fronts_use_all_dimensions_and_keep_v2_order_inside_front() -> None:
    reduction = SearchReduction(
        complete=True,
        roots=(
            _root("discard:1w", 0, 0.2, 0.5),
            _root("discard:2w", 0, 0.3, 0.6),  # 完整支配 1w
            _root("discard:3w", 10, 0.1, 0.4),  # 胡支撑更高，与 2w 不可比
        ),
        reason=None,
    )
    baseline = ("discard:3w", "discard:1w", "discard:2w")
    assert order_discard_keys_by_fronts(reduction, baseline) == (
        "discard:3w",
        "discard:2w",
        "discard:1w",
    )


def test_incomplete_reduction_or_key_mismatch_returns_exact_v2_order() -> None:
    baseline = ("discard:2w", "discard:1w")
    failed = SearchReduction(False, (), "缺边")
    assert order_discard_keys_by_fronts(failed, baseline) == baseline

    mismatched = SearchReduction(
        True, (_root("discard:1w", 0, 0, 0),), None
    )
    assert order_discard_keys_by_fronts(mismatched, baseline) == baseline
