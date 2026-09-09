"""普通弃财保护的公开输入、退路顺序与异常传播验收。"""

import asyncio
from copy import deepcopy
from dataclasses import replace

import pytest

from hangma_bot.hangma.interface import CandidateFactKind, CandidateFacts, RuleIssue
from hangma_bot.kernel.actions import Discard, Hu, Tile, WindowPhase, action_key
from hangma_bot.policy.errors import PolicyTimeoutError
from hangma_bot.policy.interface import DecisionPlan, RankedCandidate, ScorePart
from hangma_bot.policy.white_discard_guard import (
    WHITE_DISCARD_GUARD_VERSION,
    WhiteDiscardGuardPolicy,
)

from .support import (
    candidates_for,
    discards_for,
    make_budget,
    make_observation,
    make_request,
    make_rules,
    rejected,
    run_choose,
)


class WhiteFirstPolicy:
    """测试策略：胡最先、随后故意偏爱弃财，仅消费传入候选。"""

    def __init__(self):
        self.requests = []
        self.budgets = []
        self.last_plan = None

    async def choose(self, request, budget):
        self.requests.append(request)
        self.budgets.append(budget)
        rejected_keys = {attempt.action_key for attempt in request.rejected_attempts}
        candidates = [
            candidate
            for candidate in request.rules.legal_candidates
            if candidate.action_key not in rejected_keys
            and candidate.action_key == action_key(candidate.action)
        ]
        candidates.sort(
            key=lambda candidate: (
                0 if isinstance(candidate.action, Hu) else
                1 if candidate.action == Discard(request.observation.rule_state.wealth_god) else 2,
                candidate.action_key,
            )
        )
        emergency = request.rules.emergency_candidate
        self.last_plan = DecisionPlan(
            decision_id=request.decision_id,
            window_key=request.window_key,
            based_on_authoritative_seq=request.observation.snapshot_seq,
            revision=len(request.rejected_attempts) + 1,
            candidates=tuple(
                RankedCandidate(
                    action=candidate.action,
                    action_key=candidate.action_key,
                    rank=index * 2,
                    total_score=10.0 - index,
                    score_parts=(ScorePart("桩评分", 10.0 - index),),
                    reasons=("桩策略排序",),
                    is_emergency=emergency is not None and emergency.action_key == candidate.action_key,
                )
                for index, candidate in enumerate(candidates, 1)
            ),
            degraded_reasons=("底层审计标记",),
        )
        return self.last_plan


def request_with_discards(*codes, emergency_code=None, rejected_keys=(), **observation_overrides):
    """用公开测试夹具构造候选；不自行推演合法性。"""
    candidates = discards_for(codes)
    emergency = next(
        (candidate for candidate in candidates if candidate.action.tile.code == emergency_code),
        None,
    )
    return make_request(
        make_observation(**observation_overrides),
        make_rules(candidates, emergency),
        rejected=tuple(rejected(key) for key in rejected_keys),
    )


def test_non_baotou_white_preference_is_blocked_without_mutating_request_or_facts():
    original = request_with_discards("白", "2b", "3t", emergency_code="2b")
    fact = CandidateFacts(CandidateFactKind.HAND_PROGRESS, 1)
    non_white = replace(original.rules.legal_candidates[1], facts=fact)
    original = replace(original, rules=replace(
        original.rules,
        legal_candidates=(original.rules.legal_candidates[0], non_white, original.rules.legal_candidates[2]),
        issues=(RuleIssue("guard-test", "既有规则问题"),),
    ))
    snapshot = deepcopy(original)
    base = WhiteFirstPolicy()
    assert run_choose(base, original, make_budget()).candidates[0].action_key == "discard:白"
    policy = WhiteDiscardGuardPolicy(base)
    budget = make_budget()

    plan = run_choose(policy, original, budget)

    assert policy.base_policy is base
    assert [candidate.action_key for candidate in plan.candidates] == ["discard:2b", "discard:3t"]
    assert [candidate.rank for candidate in plan.candidates] == [1, 2]
    assert plan.candidates[0].is_emergency
    assert original == snapshot
    view = base.requests[-1]
    assert view is not original
    assert view.observation is original.observation
    assert view.competition is original.competition
    assert view.rejected_attempts is original.rejected_attempts
    assert view.rules.legal_candidates[0] is non_white
    assert view.rules.legal_candidates[0].facts is fact
    assert view.rules.emergency_candidate is original.rules.emergency_candidate
    assert view.rules.issues is original.rules.issues
    assert base.budgets[-1] is budget
    assert plan.decision_id == original.decision_id
    assert plan.window_key == original.window_key
    assert plan.degraded_reasons[0] == "底层审计标记"
    assert WHITE_DISCARD_GUARD_VERSION in " ".join(plan.degraded_reasons)


def test_baotou_leaves_white_and_hu_unchanged():
    observation = make_observation()
    observation = replace(observation, rule_state=replace(observation.rule_state, baotou=True))
    request = make_request(observation, make_rules(candidates_for((Hu(), Discard(Tile("白")), Discard(Tile("2b"))))))
    base = WhiteFirstPolicy()

    plan = run_choose(WhiteDiscardGuardPolicy(base), request, make_budget())

    assert base.requests[-1] is request
    assert plan is base.last_plan
    assert [candidate.action_key for candidate in plan.candidates] == ["hu", "discard:白", "discard:2b"]


def test_guard_keeps_hu_and_its_score_when_filtering_ordinary_white():
    request = request_with_discards("白", "2b", emergency_code="2b")
    request = replace(request, rules=replace(request.rules, legal_candidates=candidates_for((Hu(),)) + request.rules.legal_candidates))
    base = WhiteFirstPolicy()

    plan = run_choose(WhiteDiscardGuardPolicy(base), request, make_budget())

    assert [candidate.action_key for candidate in plan.candidates] == ["hu", "discard:2b"]
    assert plan.candidates[0].total_score == base.last_plan.candidates[0].total_score
    assert plan.candidates[0].score_parts == base.last_plan.candidates[0].score_parts


@pytest.mark.parametrize("rejected_keys", [(), ("discard:2b",)])
def test_no_available_non_white_delegates_original_request(rejected_keys):
    codes = ("白", "2b") if rejected_keys else ("白",)
    request = request_with_discards(*codes, emergency_code="白", rejected_keys=rejected_keys)
    request = replace(request, observation=replace(request.observation, rule_state=replace(request.observation.rule_state, catch_play=True)))
    base = WhiteFirstPolicy()

    plan = run_choose(WhiteDiscardGuardPolicy(base), request, make_budget())

    assert base.requests[-1] is request
    assert plan is base.last_plan
    assert [candidate.action_key for candidate in plan.candidates] == ["discard:白"]


def test_malformed_non_white_action_key_does_not_enable_guard():
    request = request_with_discards("白", "2b", emergency_code="白")
    bad = replace(request.rules.legal_candidates[1], action_key="discard:3t")
    request = replace(request, rules=replace(request.rules, legal_candidates=(request.rules.legal_candidates[0], bad)))
    base = WhiteFirstPolicy()

    plan = run_choose(WhiteDiscardGuardPolicy(base), request, make_budget())

    assert base.requests[-1] is request
    assert [candidate.action_key for candidate in plan.candidates] == ["discard:白"]


def test_legacy_white_emergency_is_excluded_from_scoring_and_retained_only_last():
    request = request_with_discards("白", "2b", "3t", emergency_code="白")
    base = WhiteFirstPolicy()

    plan = run_choose(WhiteDiscardGuardPolicy(base), request, make_budget())

    assert base.requests[-1].rules.emergency_candidate is None
    assert [candidate.action_key for candidate in base.requests[-1].rules.legal_candidates] == ["discard:2b", "discard:3t"]
    assert [candidate.action_key for candidate in plan.candidates] == ["discard:2b", "discard:3t", "discard:白"]
    assert [candidate.rank for candidate in plan.candidates] == [1, 2, 3]
    assert plan.candidates[-1].is_emergency
    assert "最后退路" in " ".join(plan.candidates[-1].reasons)
    assert plan.candidates[-1].total_score == sum(part.value for part in plan.candidates[-1].score_parts)
    assert request.rules.emergency_candidate.action_key == "discard:白"


@pytest.mark.parametrize("emergency_mode", ["rejected", "missing_from_legal", "malformed_key"])
def test_ineligible_legacy_white_emergency_is_never_restored(emergency_mode):
    request = request_with_discards("白", "2b", emergency_code="白")
    if emergency_mode == "rejected":
        request = replace(request, rejected_attempts=(rejected("discard:白"),))
    elif emergency_mode == "missing_from_legal":
        request = replace(request, rules=replace(request.rules, legal_candidates=request.rules.legal_candidates[1:]))
    else:
        request = replace(request, rules=replace(request.rules, emergency_candidate=replace(request.rules.emergency_candidate, action_key="bad-key")))
    base = WhiteFirstPolicy()

    plan = run_choose(WhiteDiscardGuardPolicy(base), request, make_budget())

    assert base.requests[-1].rules.emergency_candidate is None
    assert [candidate.action_key for candidate in plan.candidates] == ["discard:2b"]


@pytest.mark.parametrize("phase,turn", [("response_peng", 0), ("draw", 1)])
def test_other_windows_delegate_unchanged(phase, turn):
    request = request_with_discards("白", "2b", phase=phase, turn_seat=turn)
    request = replace(request, window_key=replace(request.window_key, phase=WindowPhase(phase)))
    base = WhiteFirstPolicy()

    plan = run_choose(WhiteDiscardGuardPolicy(base), request, make_budget())

    assert base.requests[-1] is request
    assert plan is base.last_plan


def test_window_without_white_delegates_unchanged():
    request = request_with_discards("2b", "3t", emergency_code="2b")
    base = WhiteFirstPolicy()

    plan = run_choose(WhiteDiscardGuardPolicy(base), request, make_budget())

    assert base.requests[-1] is request
    assert plan is base.last_plan


@pytest.mark.parametrize("error", [ValueError("底层错误"), PolicyTimeoutError("超时"), asyncio.TimeoutError("外层超时")])
def test_exceptions_and_timeouts_propagate_as_the_same_instance(error):
    class FailingPolicy:
        async def choose(self, request, budget):
            raise error

    request = request_with_discards("白", "2b", emergency_code="白")
    with pytest.raises(type(error)) as raised:
        run_choose(WhiteDiscardGuardPolicy(FailingPolicy()), request, make_budget())
    assert raised.value is error


def test_cancellation_reaches_the_base_policy():
    async def check():
        started = asyncio.Event()
        cancelled = asyncio.Event()

        class WaitingPolicy:
            async def choose(self, request, budget):
                started.set()
                try:
                    await asyncio.Future()
                finally:
                    cancelled.set()

        request = request_with_discards("白", "2b", emergency_code="白")
        task = asyncio.create_task(WhiteDiscardGuardPolicy(WaitingPolicy()).choose(request, make_budget()))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cancelled.is_set()

    asyncio.run(check())


def test_empty_base_plan_is_not_masked_by_restoring_only_white():
    class EmptyPolicy(WhiteFirstPolicy):
        async def choose(self, request, budget):
            return replace(await super().choose(request, budget), candidates=())

    request = request_with_discards("白", "2b", emergency_code="白")
    plan = run_choose(WhiteDiscardGuardPolicy(EmptyPolicy()), request, make_budget())
    assert plan.candidates == ()
