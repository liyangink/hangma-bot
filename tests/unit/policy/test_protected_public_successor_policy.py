"""累计专项保护的 R17 组合策略契约。"""

from __future__ import annotations

from dataclasses import replace

from hangma_bot.kernel.actions import Discard, Tile
from hangma_bot.policy.interface import DecisionPlan, RankedCandidate
from hangma_bot.policy.protected_public_successor_policy import (
    ProtectedPublicSuccessorSearchPolicy,
    protected_trace_state,
)
from hangma_bot.policy.public_successor_leaf_executor import LeafProgramExecutor
from hangma_bot.policy.public_successor_search import RootSearchScore, SearchReduction

from .support import candidates_for, make_budget, make_observation, make_request, make_rules, run_choose


SOURCE = "def score_actions(view):\n    return 0.0\n"
PROTECTED = ("r18_seven_pairs_value_overlay", "two_wealth_piao_keeps_baotou_cf")


class _Baseline:
    def __init__(self, plan: DecisionPlan) -> None:
        self.plan = plan

    async def choose(self, request, budget) -> DecisionPlan:
        return self.plan


def _request():
    observation = make_observation(phase="draw")
    actions = (Discard(Tile("1w")), Discard(Tile("2w")), Discard(Tile("3w")))
    return make_request(observation, make_rules(candidates_for(actions)))


def _plan(request, *, trace) -> DecisionPlan:
    candidates = tuple(
        RankedCandidate(
            action=Discard(Tile(code)),
            action_key="discard:" + code,
            rank=index,
            total_score=float(4 - index),
            score_parts=(),
            reasons=("baseline",),
            is_emergency=index == 3,
            score_trace=trace,
        )
        for index, code in enumerate(("1w", "2w", "3w"), 1)
    )
    return DecisionPlan(
        decision_id=request.decision_id,
        window_key=request.window_key,
        based_on_authoritative_seq=request.observation.snapshot_seq,
        revision=1,
        candidates=candidates,
        degraded_reasons=("baseline",),
    )


def _policy(plan, provider):
    return ProtectedPublicSuccessorSearchPolicy(
        provider,
        LeafProgramExecutor(SOURCE),
        candidate_identity="candidate-identity-0123456789",
        baseline=_Baseline(plan),
        protected_trace_keys=PROTECTED,
        monotonic=lambda: 0.0,
    )


def _reduction() -> SearchReduction:
    return SearchReduction(
        complete=True,
        roots=tuple(
            RootSearchScore(key, 0.0, 0.0, 0.0, 0, 1, 1)
            for key in ("discard:1w", "discard:2w", "discard:3w")
        ),
        reason=None,
    )


def test_triggered_special_returns_exact_baseline_without_search() -> None:
    request = _request()
    trace = {
        "trace_schema": "sitin-action-score-trace/1",
        "detail": {PROTECTED[0]: {"triggered": True}},
    }
    original = _plan(request, trace=trace)
    calls = []
    policy = _policy(original, lambda observation: calls.append(observation))

    actual = run_choose(policy, request, make_budget())

    assert actual is original
    assert calls == []
    assert protected_trace_state(original, PROTECTED) == (True, (PROTECTED[0],))


def test_missing_or_malformed_trace_fails_closed() -> None:
    request = _request()
    for trace, reason in ((None, "trace_unavailable"), ({}, "trace_detail_unavailable")):
        original = _plan(request, trace=trace)
        calls = []
        policy = _policy(original, lambda observation: calls.append(observation))
        assert run_choose(policy, request, make_budget()) is original
        assert calls == []
        assert protected_trace_state(original, PROTECTED) == (True, (reason,))


def test_ordinary_plan_uses_existing_r17_reduction(monkeypatch) -> None:
    request = _request()
    trace = {"trace_schema": "sitin-action-score-trace/1", "detail": {}}
    original = _plan(request, trace=trace)
    calls = []
    policy = _policy(original, lambda observation: calls.append(observation) or object())
    monkeypatch.setattr(
        "hangma_bot.policy.protected_public_successor_policy.reduce_public_successors",
        lambda request, successors, scorer: _reduction(),
    )
    monkeypatch.setattr(
        "hangma_bot.policy.protected_public_successor_policy.order_discard_keys_by_fronts",
        lambda reduction, baseline_keys: tuple(reversed(baseline_keys)),
    )

    actual = run_choose(policy, request, make_budget())

    assert calls == [request.observation]
    assert tuple(item.action_key for item in actual.candidates) == (
        "discard:3w",
        "discard:2w",
        "discard:1w",
    )
    assert {item.action_key for item in actual.candidates} == {
        item.action_key for item in original.candidates
    }
    assert tuple(item.rank for item in actual.candidates) == (1, 2, 3)
    assert all("候选=candidate-id" in item.reasons[-1] for item in actual.candidates)


def test_duplicate_or_empty_protection_keys_are_rejected() -> None:
    request = _request()
    plan = _plan(
        request,
        trace={"trace_schema": "sitin-action-score-trace/1", "detail": {}},
    )
    base = {
        "successor_provider": lambda observation: object(),
        "leaf_executor": LeafProgramExecutor(SOURCE),
        "candidate_identity": "candidate",
        "baseline": _Baseline(plan),
    }
    import pytest

    with pytest.raises(ValueError):
        ProtectedPublicSuccessorSearchPolicy(**base, protected_trace_keys=())
    with pytest.raises(ValueError):
        ProtectedPublicSuccessorSearchPolicy(
            **base, protected_trace_keys=("same", "same")
        )
