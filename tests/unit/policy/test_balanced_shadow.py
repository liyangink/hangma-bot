import asyncio
from types import SimpleNamespace

from hangma_bot.hangma import HangmaRules
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.hangma.interface import CandidateFactKind, RuleCompleteness, UsefulTileFact
from hangma_bot.hangma.interface import CandidateFacts, RuleAnalysis, RuleCandidate
from hangma_bot.kernel.actions import Discard, WindowKey
from hangma_bot.policy.balanced_shadow import V2BalancedShadowPolicy, _pareto, _route_signature
from hangma_bot.policy.interface import DecisionPlan, RankedCandidate
from .support import make_budget, make_observation, make_request, make_rules


def test_pareto_keeps_distinct_speed_and_seven_pair_routes():
    def candidate(key, standard, pairs, outs):
        facts = SimpleNamespace(
            fact_kind=CandidateFactKind.HAND_PROGRESS,
            completeness=RuleCompleteness.COMPLETE,
            shanten_after=min(standard, pairs),
            standard_shanten_after=standard,
            seven_pairs_shanten_after=pairs,
            replacement_draw_unknown=False,
            useful_tiles=tuple(UsefulTileFact(code=code, remaining_estimate=4) for code in ("1w", "2w", "3w", "4w")[:outs]),
        )
        return SimpleNamespace(action_key=key, facts=facts)

    frontier = _pareto((candidate("a", 1, 3, 4), candidate("b", 2, 1, 3), candidate("c", 2, 2, 1)))
    assert {candidate.action_key for candidate in frontier} == {"a", "b"}

    # 七对更近必须能被签名表达：综合向听是最小值，会把该情形写成同距离。
    nearer = candidate("d", 3, 0, 2)
    standard, pairs, _ = _route_signature(nearer)
    assert (standard, pairs) == (3, 0), "七对更近（0 < 3）必须出现在签名里"
    assert standard != nearer.facts.shanten_after, "签名不得使用综合向听，否则该情形会伪装成同距离"
    assert nearer in _pareto((nearer, candidate("e", 4, 2, 2)))


def test_shadow_preserves_baseline_action_without_complete_facts():
    tiles = tuple(Tile(code) for code in "2t 2w 发 5t 白 发 2w 2t 3w 4t 4b 3t 1t 8b".split())
    observation = make_observation(my_hand=tiles[:-1], drawn_tile=tiles[-1], remaining_tile_count=83)
    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    request = make_request(observation, rules.analyze(observation))
    shadow = V2BalancedShadowPolicy(monotonic=lambda: 0)
    baseline = asyncio.run(shadow._baseline.choose(request, make_budget()))
    result = asyncio.run(shadow.choose(request, make_budget()))
    assert result.candidates[0].action_key == baseline.candidates[0].action_key
    assert result.candidates[0].action_key == baseline.candidates[0].action_key


def test_shadow_does_not_invent_route_for_incomplete_facts():
    tiles = tuple(Tile(code) for code in "2t 2w 发 5t 白 发 2w 2t 3w 4t 4b 3t 1t 8b".split())
    observation = make_observation(my_hand=tiles[:-1], drawn_tile=tiles[-1], remaining_tile_count=83)
    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    request = make_request(observation, rules.analyze(observation))
    request = request.__class__(**{**request.__dict__, "rules": request.rules.__class__(
        legal_candidates=tuple(c.__class__(**{**c.__dict__, "facts": None}) for c in request.rules.legal_candidates),
        emergency_candidate=request.rules.emergency_candidate,
        completeness=request.rules.completeness,
        ruleset_version=request.rules.ruleset_version,
        issues=request.rules.issues,
    )})
    result = asyncio.run(V2BalancedShadowPolicy(monotonic=lambda: 0).choose(request, make_budget()))
    assert not any("Pareto候选" in reason for candidate in result.candidates for reason in candidate.reasons)


def test_shadow_audits_real_candidate_fact_frontier_without_reordering():
    def fact(standard, pairs, outs):
        return CandidateFacts(
            fact_kind=CandidateFactKind.HAND_PROGRESS,
            shanten_after=standard,
            standard_shanten_after=standard,
            seven_pairs_shanten_after=pairs,
            useful_tiles=tuple(UsefulTileFact(code, 4) for code in ("1w", "2w", "3w", "4w")[:outs]),
        )

    candidates = tuple(
        RuleCandidate(Discard(Tile(tile)), f"discard:{tile}", (), facts=facts)
        for tile, facts in (("1w", fact(1, 3, 4)), ("2w", fact(2, 1, 3)), ("3w", fact(2, 2, 1)))
    )
    observation = make_observation(my_hand=(Tile("1w"),), drawn_tile=Tile("2w"))
    request = make_request(observation, make_rules(candidates))
    baseline_candidate = RankedCandidate(Discard(Tile("1w")), "discard:1w", 1, 0.0, (), ())
    baseline = DecisionPlan("d1", request.window_key, 10, 1, (baseline_candidate,), ())

    class Baseline:
        async def choose(self, request, budget):
            return baseline

    result = asyncio.run(V2BalancedShadowPolicy(Baseline()).choose(request, make_budget()))
    assert result.candidates[0].action_key == "discard:1w"
    assert "Pareto候选 2 个" in result.candidates[0].reasons[-1]
    assert "路线签名=" in result.candidates[0].reasons[-1]
