"""R17 公开后继研究策略只能重排弃牌，并可逐字节回退 V2。"""

from __future__ import annotations

from hangma_bot.kernel.actions import Discard, Hu, Tile, WindowPhase
from hangma_bot.policy.interface import DecisionPlan, RankedCandidate
from hangma_bot.policy.public_successor_leaf_executor import LeafProgramExecutor
from hangma_bot.policy.public_successor_policy import PublicSuccessorSearchPolicy
from hangma_bot.policy.public_successor_search import RootSearchScore, SearchReduction

from .support import (
    candidates_for,
    make_budget,
    make_observation,
    make_request,
    make_rules,
    run_choose,
)


SOURCE = "def score_actions(view):\n    return 0.0\n"


class _Baseline:
    def __init__(self, plan: DecisionPlan) -> None:
        self.plan = plan
        self.calls = 0

    async def choose(self, request, budget) -> DecisionPlan:
        self.calls += 1
        return self.plan


def _plan(request) -> DecisionPlan:
    actions = (
        Hu(),
        Discard(Tile("1w")),
        Discard(Tile("2w")),
        Discard(Tile("3w")),
    )
    candidates = tuple(
        RankedCandidate(
            action=action,
            action_key=("hu" if isinstance(action, Hu) else "discard:" + action.tile.code),
            rank=index + 1,
            total_score=10.0 - index,
            score_parts=(),
            reasons=("v2",),
            is_emergency=(index == 3),
        )
        for index, action in enumerate(actions)
    )
    return DecisionPlan(
        decision_id=request.decision_id,
        window_key=request.window_key,
        based_on_authoritative_seq=request.observation.snapshot_seq,
        revision=1,
        candidates=candidates,
        degraded_reasons=("baseline",),
    )


def _request(*, observation_phase="draw", window_phase=WindowPhase.DRAW):
    observation = make_observation(phase=observation_phase)
    rules = make_rules(
        candidates_for(
            (Hu(), Discard(Tile("1w")), Discard(Tile("2w")), Discard(Tile("3w")))
        )
    )
    return make_request(observation, rules, phase=window_phase)


def _policy(request, monkeypatch, *, now=0.0, enabled=True, provider=None):
    baseline_plan = _plan(request)
    baseline = _Baseline(baseline_plan)
    calls = []

    def default_provider(observation):
        calls.append(observation)
        return object()

    policy = PublicSuccessorSearchPolicy(
        provider or default_provider,
        LeafProgramExecutor(SOURCE),
        candidate_identity="candidate-identity-0123456789",
        baseline=baseline,
        monotonic=lambda: now,
        enabled=enabled,
    )
    assert policy.policy_id == "r17-public-successor:candidate-id"
    assert policy.max_operations == 500_000
    return policy, baseline, baseline_plan, calls


def _complete_reduction() -> SearchReduction:
    return SearchReduction(
        complete=True,
        roots=tuple(
            RootSearchScore(key, 0.0, 0.0, 0.0, 0, 1, 1)
            for key in ("discard:1w", "discard:2w", "discard:3w")
        ),
        reason=None,
    )


def test_success_path_only_reorders_existing_discard_slots(monkeypatch) -> None:
    request = _request()
    policy, baseline, original, provider_calls = _policy(request, monkeypatch)
    monkeypatch.setattr(
        "hangma_bot.policy.public_successor_policy.reduce_public_successors",
        lambda request, successors, scorer: _complete_reduction(),
    )
    monkeypatch.setattr(
        "hangma_bot.policy.public_successor_policy.order_discard_keys_by_fronts",
        lambda reduction, baseline_keys: tuple(reversed(baseline_keys)),
    )

    result = run_choose(policy, request, make_budget())

    assert baseline.calls == 1
    assert provider_calls == [request.observation]
    assert tuple(item.action_key for item in result.candidates) == (
        "hu",
        "discard:3w",
        "discard:2w",
        "discard:1w",
    )
    assert result.candidates[0] == original.candidates[0]
    assert tuple(item.total_score for item in result.candidates) == (10.0, 7.0, 8.0, 9.0)
    assert tuple(item.is_emergency for item in result.candidates) == (False, True, False, False)
    assert tuple(item.rank for item in result.candidates) == (1, 2, 3, 4)
    assert result.degraded_reasons == original.degraded_reasons
    assert all(
        "候选=candidate-id" in item.reasons[-1]
        for item in result.candidates[1:]
    )


def test_disabled_response_or_expired_enhancement_returns_exact_baseline(monkeypatch) -> None:
    cases = (
        (_request(), False, 0.0, make_budget()),
        (_request(observation_phase="response_peng", window_phase=WindowPhase.RESPONSE_PENG), True, 0.0, make_budget()),
        (_request(observation_phase="draw", window_phase=WindowPhase.RESPONSE_PENG), True, 0.0, make_budget()),
        (_request(), True, 101.0, make_budget(enhancement=100.0)),
    )
    for request, enabled, now, budget in cases:
        policy, baseline, original, provider_calls = _policy(
            request, monkeypatch, enabled=enabled, now=now
        )
        result = run_choose(policy, request, budget)
        assert result is original
        assert baseline.calls == 1
        assert provider_calls == []


def test_provider_or_reduction_failure_returns_exact_baseline(monkeypatch) -> None:
    request = _request()

    def fail_provider(observation):
        raise RuntimeError("provider failed")

    policy, _, original, _ = _policy(request, monkeypatch, provider=fail_provider)
    assert run_choose(policy, request, make_budget()) is original

    policy, _, original, _ = _policy(request, monkeypatch)
    monkeypatch.setattr(
        "hangma_bot.policy.public_successor_policy.reduce_public_successors",
        lambda request, successors, scorer: SearchReduction(False, (), "candidate failed"),
    )
    assert run_choose(policy, request, make_budget()) is original


def test_key_mismatch_and_post_search_deadline_return_exact_baseline(monkeypatch) -> None:
    request = _request()
    policy, _, original, _ = _policy(request, monkeypatch)
    monkeypatch.setattr(
        "hangma_bot.policy.public_successor_policy.reduce_public_successors",
        lambda request, successors, scorer: _complete_reduction(),
    )
    monkeypatch.setattr(
        "hangma_bot.policy.public_successor_policy.order_discard_keys_by_fronts",
        lambda reduction, baseline_keys: ("discard:1w", "discard:2w", "discard:9w"),
    )
    assert run_choose(policy, request, make_budget()) is original

    ticks = iter((0.0, 101.0))
    baseline = _Baseline(_plan(request))
    policy = PublicSuccessorSearchPolicy(
        lambda observation: object(),
        LeafProgramExecutor(SOURCE),
        candidate_identity="candidate",
        baseline=baseline,
        monotonic=lambda: next(ticks),
    )
    assert run_choose(policy, request, make_budget(enhancement=100.0)) is baseline.plan
