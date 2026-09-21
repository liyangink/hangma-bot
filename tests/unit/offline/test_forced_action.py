"""离线反事实首动作干预器的契约测试。"""

from __future__ import annotations

import pytest

from hangma_bot.kernel.actions import Pass, Peng, Tile, WindowPhase
from hangma_bot.offline.forced_action import ForceFirstActionPolicy
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2

from ..policy.support import (
    candidates_for,
    make_budget,
    make_observation,
    make_request,
    make_rules,
    run_choose,
)


def response_request():
    """构造同时允许过与碰的公开响应窗口。"""

    observation = make_observation(
        phase="response_peng",
        turn_seat=1,
        responding_seats=(0,),
    )
    candidates = candidates_for((Pass(), Peng(Tile("5w"))))
    return make_request(
        observation,
        make_rules(candidates, emergency=candidates[0]),
        phase=WindowPhase.RESPONSE_PENG,
    )


def test_forces_only_the_exact_window_once_and_preserves_the_plan() -> None:
    request = response_request()
    inner = ComparableHeuristicPolicyV2(monotonic=lambda: 0.0)
    policy = ForceFirstActionPolicy(
        inner,
        target_window=request.window_key,
        forced_action_key="peng:5w",
        policy_id="test-force-peng",
    )

    first = run_choose(policy, request, make_budget())
    second = run_choose(policy, request, make_budget())

    assert first.candidates[0].action_key == "peng:5w"
    assert [item.rank for item in first.candidates] == [1, 2]
    assert first.outcome_trace is None
    assert first.degraded_reasons[-1] == "offline_counterfactual_force_first:peng:5w"
    assert second.candidates[0].action_key == "pass"
    assert policy.force_count == 1


def test_rejects_a_forced_action_missing_from_the_delegate_plan() -> None:
    request = response_request()
    policy = ForceFirstActionPolicy(
        ComparableHeuristicPolicyV2(monotonic=lambda: 0.0),
        target_window=request.window_key,
        forced_action_key="chi:1w,2w,3w",
        policy_id="test-force-missing",
    )

    with pytest.raises(ValueError, match="不在目标窗口合法候选"):
        run_choose(policy, request, make_budget())


def test_does_not_intervene_in_another_window() -> None:
    request = response_request()
    other = make_request(
        request.observation,
        request.rules,
        decision_id="other",
        phase=WindowPhase.RESPONSE_PENG,
    )
    other = type(other)(
        observation=other.observation,
        competition=other.competition,
        rules=other.rules,
        decision_id=other.decision_id,
        trigger_seq=other.trigger_seq,
        window_key=type(other.window_key)(
            game_id=other.window_key.game_id,
            round_no=other.window_key.round_no,
            trigger_seq=other.window_key.trigger_seq + 1,
            phase=other.window_key.phase,
            seat=other.window_key.seat,
        ),
        rejected_attempts=other.rejected_attempts,
    )
    policy = ForceFirstActionPolicy(
        ComparableHeuristicPolicyV2(monotonic=lambda: 0.0),
        target_window=request.window_key,
        forced_action_key="peng:5w",
        policy_id="test-force-window",
    )

    plan = run_choose(policy, other, make_budget())

    assert plan.candidates[0].action_key == "pass"
    assert policy.force_count == 0
