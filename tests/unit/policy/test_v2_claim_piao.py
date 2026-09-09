"""通过公开 choose 与实际模拟前缀验证独立续飘增量及完整降级。"""

import asyncio
from dataclasses import replace

import pytest

from hangma_bot.hangma.interface import RuleIssue, ValueAnalysisLimits, ValueCoverage, WinDescription
from hangma_bot.kernel.actions import Discard, Pass, Tile
from hangma_bot.policy.v2_claim_piao import V2ClaimPiaoPolicy
from hangma_bot.simulation import SimulationChoice
from tests.simulation.test_catch_owner_v26 import _after_piao_and_claim, _discard
from .test_hu_upgrade import BUDGET, historical, replace_candidates
from .test_v2_hu_upgrade import v2
from .support import rejected


def claimed(claim="peng"):
    """由守恒牌墙经合法动作得到真实吃碰后窗口，不伪造规则候选。"""
    rules, engine, world = _after_piao_and_claim(claim)
    decision = engine.frame(world).decisions[0]
    obs = decision.observation
    request = replace(historical("F"), observation=obs, window_key=decision.window_key,
                      trigger_seq=obs.consumed_seq, rules=rules.analyze(obs, value_limits=ValueAnalysisLimits()))
    return request, rules, engine, world


def choose(request, **kwargs):
    return asyncio.run(V2ClaimPiaoPolicy(monotonic=lambda: 0, **kwargs).choose(request, BUDGET))


@pytest.mark.parametrize("claim", ["peng", "chi"])
def test_continuation_improves_conditional_value_and_matches_actual_next_draw(claim):
    request, rules, engine, world = claimed(claim)
    old, plan = v2(request), choose(request)
    assert old.candidates[0].action_key != "discard:白"
    assert plan.candidates[0].action_key == "discard:白"
    assert plan == choose(request)
    assert {c.action_key for c in plan.candidates} == {c.action_key for c in old.candidates}
    assert [c.rank for c in plan.candidates] == list(range(1, len(plan.candidates) + 1))
    assert all(c.total_score == sum(p.value for p in c.score_parts) for c in plan.candidates)
    assert {c.action_key for c in plan.candidates if c.is_emergency} == {c.action_key for c in old.candidates if c.is_emergency}
    values = next(c.value_facts for c in request.rules.legal_candidates if c.action_key == "discard:白")
    world = _discard(engine, world, 0, "白")
    for _ in range(16):
        frame = engine.frame(world)
        current = frame.decisions[0].observation
        if current.phase == "draw" and current.seat == 0:
            break
        choices = tuple(SimulationChoice(d.window_key, Discard(d.observation.drawn_tile)
                        if d.observation.phase == "draw" else Pass()) for d in frame.decisions)
        world = engine.advance(world, frame.revision, choices)
    else:
        pytest.fail("未到达下一次本人摸牌")
    route = next(r for r in values.routes if current.drawn_tile.code in {t.code for t in r.useful_tiles})
    assert rules.score(WinDescription(current, 0)) == route.conditional_settlement
    assert (current.rule_state.chain_count, current.chain_piao) == (2, 2)


@pytest.mark.parametrize("name", list("ABCDEFGH"))
def test_all_historical_actions_remain_exactly_v2(name):
    request = historical(name)
    assert choose(request) == v2(request)


def test_disabled_rejected_and_missing_proofs_keep_v2():
    request, *_ = claimed()
    assert choose(request, continuation_weight=0) == v2(request)
    denied = replace(request, rejected_attempts=(rejected("discard:白"),))
    assert choose(denied) == v2(denied)
    for coverage in (ValueCoverage.PARTIAL, ValueCoverage.UNAVAILABLE):
        changed = replace_candidates(request, lambda c: replace(c, value_facts=replace(c.value_facts, coverage=coverage, issues=(RuleIssue("value", "测试截断"),))))
        assert choose(changed) == v2(changed)
    changed = replace_candidates(request, lambda c: replace(c, value_facts=None))
    assert choose(changed) == v2(changed)


@pytest.mark.parametrize("changes", [{"chain_piao": None}, {"chain_piao": 0}, {"drawn_tile": Tile("1w")}, {"gang_draw": True}])
def test_unknown_chain_or_other_window_keeps_v2(changes):
    request, *_ = claimed()
    request = replace(request, observation=replace(request.observation, **changes))
    assert choose(request) == v2(request)


@pytest.mark.parametrize("damage", ["support", "replacement", "not_baotou", "no_advantage"])
def test_incomparable_or_unimproved_values_keep_v2(damage):
    request, *_ = claimed()
    def transform(candidate):
        if candidate.action_key != "discard:白":
            return candidate
        routes = list(candidate.value_facts.routes)
        if damage == "support":
            routes[0] = replace(routes[0], useful_tiles=routes[0].useful_tiles[1:])
        elif damage == "no_advantage":
            routes = [replace(r, conditional_settlement=replace(r.conditional_settlement, score_delta=(1, -1, 0, 0))) for r in routes]
        else:
            changes = {"draw_kind": "replacement"} if damage == "replacement" else {"baotou": False}
            routes = [replace(r, conditions=replace(r.conditions, **changes)) for r in routes]
        return replace(candidate, value_facts=replace(candidate.value_facts, routes=tuple(routes)))
    request = replace_candidates(request, transform)
    assert choose(request) == v2(request)


def test_deadline_after_baseline_keeps_full_plan_and_cancellation_propagates(monkeypatch):
    request, *_ = claimed()
    old = v2(request)
    policy = V2ClaimPiaoPolicy(monotonic=lambda: 101)
    async def completed(*args):
        return old
    monkeypatch.setattr(policy._baseline, "choose", completed)
    plan = asyncio.run(policy.choose(request, BUDGET))
    assert plan.candidates == old.candidates
    assert "PolicyTimeoutError" in plan.degraded_reasons[-1]
    async def cancelled(*args):
        raise asyncio.CancelledError
    monkeypatch.setattr(policy, "_check_deadline", cancelled)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(policy.choose(request, BUDGET))
