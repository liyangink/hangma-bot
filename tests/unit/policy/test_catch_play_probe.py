"""抓打圈测试策略只提升已有动作，保留预算、拒绝过滤与紧急退路。"""

from dataclasses import replace

import pytest

from hangma_bot.kernel.actions import Chi, Discard, Gang, GangKind, Hu, Pass, Peng, Tile, WindowPhase
from hangma_bot.kernel.observation import PublicDiscard
from hangma_bot.policy import CatchPlayProbePolicy, ComparableHeuristicPolicyV2, PolicyTimeoutError
from tests.unit.policy.support import (
    candidates_for, make_budget, make_observation, make_request, make_rules,
    rejected, run_choose,
)


def policy(now=0.0):
    return CatchPlayProbePolicy(ComparableHeuristicPolicyV2(monotonic=lambda: now))


@pytest.mark.parametrize("drawn", ["白", "3w", None])
def test_white_in_opening_hand_or_draw_is_promoted_even_before_hu(drawn):
    observation = make_observation(
        my_hand=(Tile("白"), Tile("2w")),
        drawn_tile=Tile(drawn) if drawn else None,
    )
    candidates = candidates_for([Hu(), Discard(Tile("2w")), Discard(Tile("白"))])
    request = make_request(observation, make_rules(candidates, emergency=candidates[1]))
    plan = run_choose(policy(), request, make_budget())

    assert plan.candidates[0].action_key == "discard:白"
    assert any(c.action_key == "discard:2w" and c.is_emergency for c in plan.candidates)
    assert {c.action_key for c in plan.candidates} == {c.action_key for c in candidates}
    assert [c.rank for c in plan.candidates] == [1, 2, 3]
    assert any("优先合法弃白" in reason for reason in plan.candidates[0].reasons)


@pytest.mark.parametrize("claim,phase", [
    (Peng(Tile("2w")), WindowPhase.RESPONSE_PENG),
    (Gang(Tile("2w"), GangKind.EXPOSED), WindowPhase.RESPONSE_PENG),
    (Chi((Tile("1w"), Tile("2w"), Tile("3w"))), WindowPhase.RESPONSE_CHI),
])
def test_existing_response_claim_beats_pass_even_without_waiting_facts(claim, phase):
    observation = make_observation(
        phase=phase.value, turn_seat=3, responding_seats=(0,),
        last_discard=PublicDiscard(3, Tile("2w"), 9),
    )
    candidates = candidates_for([Pass(), claim])
    request = make_request(observation, make_rules(candidates, candidates[0]), phase=phase)
    plan = run_choose(policy(), request, make_budget())

    assert plan.candidates[0].action == claim
    assert plan.candidates[-1].action == Pass() and plan.candidates[-1].is_emergency
    assert any("已有响应窗口" in reason for reason in plan.candidates[0].reasons)


@pytest.mark.parametrize("rejected_action", [Discard(Tile("白")), Peng(Tile("2w"))])
def test_rejected_probe_action_is_not_reintroduced(rejected_action):
    is_white = isinstance(rejected_action, Discard)
    phase = WindowPhase.DRAW if is_white else WindowPhase.RESPONSE_PENG
    fallback = Discard(Tile("3w")) if is_white else Pass()
    candidates = candidates_for([rejected_action, fallback])
    observation = make_observation(
        phase=phase.value, my_hand=(Tile("白"), Tile("3w")),
        responding_seats=() if is_white else (0,),
    )
    request = make_request(
        observation, make_rules(candidates, candidates[1]),
        rejected=(rejected(candidates[0].action_key),), phase=phase,
    )
    plan = run_choose(policy(), request, make_budget())

    assert [c.action for c in plan.candidates] == [fallback]
    assert plan.revision == 2


def test_no_legal_white_or_claim_does_not_create_a_probe_action():
    candidates = candidates_for([Discard(Tile("3w"))])
    observation = make_observation(my_hand=(Tile("白"), Tile("3w")), drawn_tile=Tile("3w"))
    request = make_request(observation, make_rules(candidates, candidates[0]))
    plan = run_choose(policy(), request, make_budget())
    assert [c.action_key for c in plan.candidates] == ["discard:3w"]


def test_nonprobe_ranks_and_scores_are_preserved_and_output_is_deterministic():
    candidates = candidates_for([Hu(), Discard(Tile("3w")), Discard(Tile("2w"))])
    request = make_request(make_observation(), make_rules(candidates, candidates[1]))
    base = ComparableHeuristicPolicyV2(monotonic=lambda: 0)
    original = run_choose(base, request, make_budget())
    first = run_choose(CatchPlayProbePolicy(base), request, make_budget())
    assert first.candidates == original.candidates
    assert run_choose(CatchPlayProbePolicy(base), request, make_budget()) == first
    assert request.rules.legal_candidates == candidates


def test_deadline_failure_propagates_to_the_existing_application_fallback():
    candidates = candidates_for([Discard(Tile("白"))])
    request = make_request(make_observation(), make_rules(candidates, candidates[0]))
    with pytest.raises(PolicyTimeoutError):
        run_choose(policy(now=101), request, make_budget(enhancement=100))


def test_empty_or_exhausted_plan_stays_empty():
    request = make_request(make_observation(), make_rules(()))
    assert not run_choose(policy(), request, make_budget()).candidates
    candidates = candidates_for([Discard(Tile("白"))])
    request = replace(request, rules=make_rules(candidates, candidates[0]), rejected_attempts=(rejected("discard:白"),))
    assert not run_choose(policy(), request, make_budget()).candidates
