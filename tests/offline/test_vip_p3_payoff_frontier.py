"""一次未来摸牌的规则支付锚点：不把公开容量冒充成功概率。"""

import gzip
import json
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER, Tile
from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig
from hangma_bot.kernel.observation import PlayerObservation, PublicDiscard, RulePublicState
from hangma_bot.kernel.serialization import observation_from_json
from hangma_bot.simulation import MatchSpec, SimulationEngine
from scripts.vip_p3_afterstate_contract import AfterstateStatus
from scripts.vip_p3_first_event_preflight import _target_root
from scripts.vip_p3_payoff_frontier import (
    extract_payoff_frontier, ordinary_discard_one_draw_component,
)


_SCAN = Path("review/vip-route-2026-09-30/evidence/"
             "p3-competing-terminal-20260930/new-root-scan.json.gz")
_CASES = Path("tests/fixtures/official/v23/fan-calc/cases.jsonl")
_LIMITS = ValueAnalysisLimits(max_expansions=8192)


def _rules():
    return HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))


def test_opened_scan_all_legal_actions_have_nonduplicated_payoff_paths():
    """128 根只核行动前规则真值；已开教师结局不进入提取器。"""

    with gzip.open(_SCAN, "rt", encoding="utf-8") as stream:
        scan = json.load(stream)
    rules = _rules()
    counts = Counter()
    for row in scan["rows"]:
        observation = observation_from_json(row["observation"])
        analysis = rules.analyze(observation, value_limits=_LIMITS, route_limits=_LIMITS)
        assert [item.action_key for item in analysis.legal_candidates] == row["legal_action_keys"]
        for candidate, root in zip(analysis.legal_candidates, analysis.conditional_roots):
            front = extract_payoff_frontier(candidate, root, observation.seat)
            counts["actions"] += 1
            counts["paths"] += len(front.paths)
            for path in front.paths:
                counts["cells"] += len(path.cells)
                assert path.public_capacity_sum == sum(
                    cell.public_unseen_count for cell in path.cells)
                assert path.capacity_weighted_net == sum(
                    cell.public_unseen_count * cell.own_net for cell in path.cells)
                assert len({cell.draw_code for cell in path.cells}) == len(path.cells)
                assert all(sum(cell.score_delta) == 0 and cell.own_net ==
                           cell.score_delta[observation.seat] for cell in path.cells)
                counts["high_cells"] += sum(cell.fan >= 4 for cell in path.cells)
            if candidate.action_key == "hu":
                assert front.afterstate_status is AfterstateStatus.EXACT_TERMINAL
                assert front.immediate_hu_net == root.settlement.score_delta[observation.seat]
                assert not front.paths
            if candidate.action_key.startswith("discard:"):
                component = ordinary_discard_one_draw_component(
                    candidate, root, observation.seat)
                counts["ordinary_discard_components"] += 1
                counts["positive_components"] += (
                    component.conditional_exchangeable_direct_hu_net > 0)
                assert 0 <= component.direct_hu_capacity <= component.total_public_unseen
                assert component.conditional_exchangeable_direct_hu_net == pytest.approx(
                    component.capacity_weighted_own_net / component.total_public_unseen)
    assert counts == {"actions": 1080, "paths": 183, "cells": 857,
                      "high_cells": 0, "ordinary_discard_components": 972,
                      "positive_components": 132}


def test_seed_532_four_fan_routes_match_p1_and_current_hu():
    """自然牌山正控：等四番 90 张公开容量与立即二番 48 分分账。"""

    rules = _rules()
    engine = SimulationEngine(rules)
    spec = MatchSpec(
        match_id="vip-p3-event-532", scenario_id="vip-p3-event-532",
        config=TournamentConfig(1, 1, rules.config, TimingConfig(1.0, 1.0, 3.0)),
        seed=532, initial_dealer=0, initial_scores=(0, 0, 0, 0),
    )
    observation = _target_root(
        engine, rules, engine.start(spec), own_draw_index=9, reference="shape"
    )[2].observation
    analysis = rules.analyze(observation, value_limits=_LIMITS, route_limits=_LIMITS)
    fronts = {candidate.action_key: extract_payoff_frontier(candidate, root, observation.seat)
              for candidate, root in zip(analysis.legal_candidates, analysis.conditional_roots)}
    assert fronts["hu"].immediate_hu_net == 48
    for key in ("discard:7t", "discard:5w"):
        path, = fronts[key].paths
        assert path.public_capacity_sum == 90
        assert path.capacity_weighted_net == 8640
        assert len(path.cells) == 33
        assert {cell.fan for cell in path.cells} == {4}
        assert {cell.own_net for cell in path.cells} == {96}
        assert all(cell.capacity_exact_after_effect for cell in path.cells)
        p1 = next(root for root in analysis.route_frontier.roots if root.action_key == key)
        assert [(edge.draw_code, edge.support_capacity,
                 edge.immediate_win.settlement.score_delta[observation.seat])
                for edge in p1.draw_edges if edge.immediate_win is not None] == [
                    (cell.draw_code, cell.public_unseen_count, cell.own_net)
                    for cell in path.cells]
        candidate = next(item for item in analysis.legal_candidates if item.action_key == key)
        root = next(item for item in analysis.conditional_roots if item.action_key == key)
        component = ordinary_discard_one_draw_component(candidate, root, observation.seat)
        assert (component.total_public_unseen, component.direct_hu_capacity,
                component.capacity_weighted_own_net) == (90, 90, 8640)
        assert component.conditional_exchangeable_direct_hu_net == 96.0
    candidate = next(item for item in analysis.legal_candidates
                     if item.action_key == "discard:4b")
    root = next(item for item in analysis.conditional_roots
                if item.action_key == "discard:4b")
    component = ordinary_discard_one_draw_component(candidate, root, observation.seat)
    assert component.conditional_exchangeable_direct_hu_net == pytest.approx(480 / 90)


def test_official_v23_thirty_two_fan_payoff_is_not_training_mean():
    """官方 v23 算分金例：四白豪华七对爆头净分 768，非 96 均值。"""

    case = next(row for row in (json.loads(line) for line in _CASES.read_text().splitlines())
                if "four-white-natural-quad-and-pairs-draw-1w" in row["tags"])
    hand = case["request"]["hand"]
    draw = case["request"]["draw"]
    claim = next(code for code in CANONICAL_TILE_ORDER
                 if code not in hand and code != draw and code != "白")
    observation = PlayerObservation(
        game_id="vip-official-payoff-v23", seat=0, round_no=1,
        snapshot_seq=10, consumed_seq=10, phase="response_peng",
        dealer_seat=0, turn_seat=3, responding_seats=(0,),
        my_hand=tuple(Tile(code) for code in hand), drawn_tile=None,
        discards=((), (), (), (Tile(claim),)), melds=((), (), (), ()),
        hand_counts=(13, 13, 13, 13),
        last_discard=PublicDiscard(3, Tile(claim), 10),
        remaining_tile_count=60, scores=(0, 0, 0, 0),
        rule_state=RulePublicState(Tile("白"), False, 0, False),
        public_history=(), chain_piao=0,
    )
    analysis = _rules().analyze(observation, value_limits=_LIMITS, route_limits=_LIMITS)
    candidate, = analysis.legal_candidates
    front = extract_payoff_frontier(candidate, analysis.conditional_roots[0], 0)
    assert front.action_key == "pass"
    assert front.afterstate_status is AfterstateStatus.UNRESOLVED_RESPONSE
    cell = next(cell for path in front.paths for cell in path.cells if cell.draw_code == draw)
    assert cell.fan == case["response"]["fan"] == 32
    assert cell.own_net == case["response"]["scores"]["dealer_hu"]["win"] == 768
    assert cell.details == tuple(case["response"]["detail"])
    assert cell.capacity_exact_after_effect is False


def test_duplicate_tile_in_same_payoff_path_is_rejected():
    """同一摸牌码若被重复分组，不能双计可胡路线。"""

    with gzip.open(_SCAN, "rt", encoding="utf-8") as stream:
        rows = json.load(stream)["rows"]
    rules = _rules()
    for row in rows:
        observation = observation_from_json(row["observation"])
        analysis = rules.analyze(observation, value_limits=_LIMITS, route_limits=_LIMITS)
        for candidate, root in zip(analysis.legal_candidates, analysis.conditional_roots):
            facts = candidate.value_facts
            if facts is not None and facts.routes:
                duplicate = replace(candidate, value_facts=replace(
                    facts, routes=facts.routes + (facts.routes[0],)))
                with pytest.raises(ValueError, match="摸牌码重复"):
                    extract_payoff_frontier(duplicate, root, observation.seat)
                return
    pytest.fail("扫描批次缺条件胡支付见证")
