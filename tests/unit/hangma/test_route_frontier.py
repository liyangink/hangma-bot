"""P1 路线事实对账：全部合法根登记、非胡边和故障可见。"""

from dataclasses import replace

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import (
    PublicSuccessorCoverage,
    RuleIssue,
    ValueAnalysisLimits,
)
from hangma_bot.hangma.route_frontier import RouteGapKind, join_one_draw_frontier
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import PlayerObservation, RulePublicState


def _observation() -> PlayerObservation:
    return PlayerObservation(
        game_id="route-frontier-test", seat=0, round_no=1,
        snapshot_seq=10, phase="draw", dealer_seat=0, turn_seat=0,
        responding_seats=(),
        my_hand=tuple(Tile(code) for code in (
            "1w", "2w", "3w", "4w", "5w", "6w", "7w",
            "8w", "9w", "1b", "2b", "3b", "东",
        )),
        drawn_tile=Tile("南"),
        discards=((), (), (), ()), melds=((), (), (), ()),
        hand_counts=(14, 13, 13, 13), last_discard=None,
        remaining_tile_count=60, scores=(0, 0, 0, 0),
        rule_state=RulePublicState(Tile("白"), False, 0, False),
        public_history=(), chain_piao=0, gang_draw=False,
    )


def _inputs():
    rules = HangmaRules(RuleConfig("route-frontier-test", 1, False))
    observation = _observation()
    legal = rules.analyze(observation, value_limits=ValueAnalysisLimits(max_expansions=8192))
    successors = rules.analyze_public_self_draw_successors(observation)
    return legal.legal_candidates, successors


_RULESET = "route-frontier-test"


def test_join_preserves_every_legal_root_and_nonwinning_positive_capacity_edge():
    candidates, successors = _inputs()
    result = join_one_draw_frontier(
        candidates, successors, expected_ruleset_version=_RULESET,
        ordinary_draw_source_proven=True, white_capacity_evidence_complete=True,
        you_cai_bi_kao=False,
    )
    assert tuple(root.action_key for root in result.roots) == tuple(
        candidate.action_key for candidate in candidates
    )
    assert result.complete
    root = next(root for root in result.roots if root.action_key == "discard:东")
    assert len(root.draw_edges) == 34
    assert any(edge.immediate_win is None for edge in root.draw_edges)
    assert sum(edge.support_capacity for edge in root.draw_edges) == next(
        item.edge_capacity_total for item in successors.roots if item.action_key == "discard:东"
    )


def test_unproven_current_draw_source_keeps_roots_but_fails_visible():
    candidates, successors = _inputs()
    result = join_one_draw_frontier(
        candidates, successors, expected_ruleset_version=_RULESET,
        ordinary_draw_source_proven=False, white_capacity_evidence_complete=True,
        you_cai_bi_kao=False,
    )
    assert tuple(root.action_key for root in result.roots) == tuple(
        candidate.action_key for candidate in candidates
    )
    assert not result.complete
    assert all(root.gap_kind is RouteGapKind.INPUT_EVIDENCE_GAP for root in result.roots)


def test_missing_positive_capacity_edge_is_not_silent_zero():
    candidates, successors = _inputs()
    first = successors.roots[0]
    # 在原本不能立即胡的条件边上捏造胡资格，必须被双源对账识别。
    winning = next(
        edge for edge in first.edges if not edge.unrestricted.hu_available
    )
    broken = replace(
        winning,
        unrestricted=replace(winning.unrestricted, hu_available=True),
    )
    changed = replace(first, edges=tuple(
        broken if edge is winning else edge for edge in first.edges
    ))
    changed_successors = replace(successors, roots=(changed,) + successors.roots[1:])
    result = join_one_draw_frontier(
        candidates, changed_successors, expected_ruleset_version=_RULESET,
        ordinary_draw_source_proven=True, white_capacity_evidence_complete=True,
        you_cai_bi_kao=False,
    )
    assert result.roots[0].gap_kind is RouteGapKind.MECHANICAL_GAP
    assert "冲突" in result.roots[0].issues[0].reason


def test_empty_candidate_set_is_not_vacuously_complete():
    _, successors = _inputs()
    result = join_one_draw_frontier(
        (), replace(successors, roots=()),
        expected_ruleset_version=_RULESET,
        ordinary_draw_source_proven=True, white_capacity_evidence_complete=True, you_cai_bi_kao=False,
    )
    assert result.roots == ()
    assert not result.complete
    assert result.top_level_gap is RouteGapKind.INPUT_EVIDENCE_GAP


def test_partial_successor_analysis_fails_all_roots_closed():
    candidates, successors = _inputs()
    partial = replace(
        successors,
        coverage=PublicSuccessorCoverage.PARTIAL,
        issues=(RuleIssue("public_successor.root", "有一根被截断"),),
    )
    result = join_one_draw_frontier(
        candidates, partial, expected_ruleset_version=_RULESET,
        ordinary_draw_source_proven=True, white_capacity_evidence_complete=True, you_cai_bi_kao=False,
    )
    assert not result.complete
    assert result.top_level_gap is RouteGapKind.MECHANICAL_GAP
    assert all(root.gap_kind is not None for root in result.roots)


def test_ruleset_mismatch_fails_closed():
    candidates, successors = _inputs()
    result = join_one_draw_frontier(
        candidates, replace(successors, ruleset_version="old-rules"),
        expected_ruleset_version=_RULESET,
        ordinary_draw_source_proven=True, white_capacity_evidence_complete=True, you_cai_bi_kao=False,
    )
    assert not result.complete
    assert result.top_level_gap is RouteGapKind.INPUT_EVIDENCE_GAP
    assert all(root.gap_kind is not None for root in result.roots)


def test_missing_legal_discard_root_is_visible():
    candidates, successors = _inputs()
    missing = successors.roots[0].action_key
    incomplete = replace(
        successors,
        roots=successors.roots[1:],
    )
    result = join_one_draw_frontier(
        candidates, incomplete, expected_ruleset_version=_RULESET,
        ordinary_draw_source_proven=True, white_capacity_evidence_complete=True, you_cai_bi_kao=False,
    )
    root = next(root for root in result.roots if root.action_key == missing)
    assert root.gap_kind is RouteGapKind.MECHANICAL_GAP
    assert not result.complete


def test_unproven_white_capacity_is_input_gap_not_mechanical_conflict():
    candidates, successors = _inputs()
    result = join_one_draw_frontier(
        candidates, successors, expected_ruleset_version=_RULESET,
        ordinary_draw_source_proven=True,
        white_capacity_evidence_complete=False,
        you_cai_bi_kao=False,
    )
    assert not result.complete
    assert all(root.gap_kind is RouteGapKind.INPUT_EVIDENCE_GAP for root in result.roots)


def test_current_hu_and_conditional_hu_keep_true_settlement_witnesses():
    observation = replace(
        _observation(),
        my_hand=tuple(Tile(code) for code in (
            "1w", "2w", "3w", "4w", "5w", "6w", "7w",
            "8w", "9w", "1b", "2b", "3b", "4t",
        )),
        drawn_tile=Tile("4t"),
    )
    rules = HangmaRules(RuleConfig(_RULESET, 1, False))
    candidates = rules.analyze(
        observation, value_limits=ValueAnalysisLimits(max_expansions=8192)
    ).legal_candidates
    successors = rules.analyze_public_self_draw_successors(observation)
    result = join_one_draw_frontier(
        candidates, successors, expected_ruleset_version=_RULESET,
        ordinary_draw_source_proven=True,
        white_capacity_evidence_complete=True,
        you_cai_bi_kao=False,
    )
    assert result.complete
    hu = next(root for root in result.roots if root.action_key == "hu")
    assert hu.immediate_settlement is not None
    assert hu.immediate_settlement.fan > 0
    assert any(
        edge.immediate_win is not None and edge.immediate_win.settlement.fan > 0
        for root in result.roots for edge in root.draw_edges
    )
