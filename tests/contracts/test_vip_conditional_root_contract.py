"""VIP 同窗全部条件根的公开规则分析接缝契约。"""

import pytest

from hangma_bot.application.audit_codec import rule_analysis_to_json, rule_analysis_from_json
from hangma_bot.hangma import route_transition
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.hangma.route_frontier import RouteGapKind
from hangma_bot.simulation import SimulationChoice, SimulationEngine

from tests.simulation._helpers import make_rules, make_spec


def test_explicit_route_analysis_preserves_every_legal_root_across_window_families():
    """规则合法集保持不变；P1 前沿未覆盖的响应仍有 P2 条件根。"""

    rules = make_rules()
    engine = SimulationEngine(rules)
    world = engine.start(make_spec(rules, rounds=1, seed=13))
    frame = engine.frame(world)
    own = frame.decisions[0]
    ordinary = rules.analyze(own.observation)
    assert ordinary.conditional_roots is None
    limits = ValueAnalysisLimits(max_expansions=8192)
    research = rules.analyze(own.observation, route_limits=limits)
    assert tuple(root.action_key for root in research.conditional_roots) == tuple(
        item.action_key for item in ordinary.legal_candidates)
    assert all(root.gap_kind is None for root in research.conditional_roots)

    discard = next(item for item in research.legal_candidates
                   if item.action_key == "discard:1w")
    world = engine.advance(world, frame.revision, (
        SimulationChoice(own.window_key, discard.action),
    ))
    for decision in engine.frame(world).decisions:
        ordinary = rules.analyze(decision.observation)
        research = rules.analyze(decision.observation, route_limits=limits)
        assert tuple(item.action_key for item in research.legal_candidates) == tuple(
            item.action_key for item in ordinary.legal_candidates)
        assert tuple(root.action_key for root in research.conditional_roots) == tuple(
            item.action_key for item in ordinary.legal_candidates)
        assert all(root.gap_kind is None for root in research.conditional_roots)
        assert all(root.gap_kind is not None
                   for root in research.route_frontier.roots)


def test_conditional_projection_failure_keeps_legal_and_emergency_actions(monkeypatch):
    """研发量具故障只标根，不使生产规则合法集或紧急路径消失。"""

    rules = make_rules()
    engine = SimulationEngine(rules)
    world = engine.start(make_spec(rules, rounds=1, seed=13))
    observation = engine.frame(world).decisions[0].observation
    ordinary = rules.analyze(observation)

    def fail(*args, **kwargs):
        raise RuntimeError("injected root failure")

    monkeypatch.setattr(route_transition, "project_legal_roots", fail)
    research = rules.analyze(
        observation, route_limits=ValueAnalysisLimits(max_expansions=8192))
    assert tuple((item.action_key, item.action) for item in research.legal_candidates) == tuple(
        (item.action_key, item.action) for item in ordinary.legal_candidates)
    assert research.emergency_candidate.action_key == ordinary.emergency_candidate.action_key
    assert tuple(root.action_key for root in research.conditional_roots) == tuple(
        item.action_key for item in ordinary.legal_candidates)
    assert all(root.gap_kind is RouteGapKind.MECHANICAL_GAP
               for root in research.conditional_roots)


def test_research_roots_are_losslessly_preserved_by_production_audit_codec():
    """当前路线审计已支持完整根；严格JSON往返不得遗漏条件事实。"""

    rules = make_rules()
    engine = SimulationEngine(rules)
    world = engine.start(make_spec(rules, rounds=1, seed=13))
    observation = engine.frame(world).decisions[0].observation
    ordinary = rules.analyze(observation)
    assert rule_analysis_to_json(ordinary)["legal_candidates"]
    research = rules.analyze(
        observation, route_limits=ValueAnalysisLimits(max_expansions=8192))
    import json
    encoded = rule_analysis_to_json(research)
    restored = rule_analysis_from_json(json.loads(json.dumps(encoded, allow_nan=False)))
    assert restored.conditional_roots == research.conditional_roots
    assert rule_analysis_to_json(restored) == encoded
