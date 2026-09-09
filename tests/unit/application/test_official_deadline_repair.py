"""官方剩余截止、409 收紧与完整观察交付的离线回归。"""

from dataclasses import replace
import asyncio

import pytest

from fakes import (
    DISCARD_3W, PASS, FakeGameSession, FakePolicy, FakeRules,
    FakeTournamentSession, ManualClock, build_runtime, make_bootstrap,
    make_observation, make_refreshed_window, make_snapshot, make_window,
    wait_for_condition,
)
from hangma_bot.application.contracts import SubmitAccepted, SubmitRejectedRetryable, TournamentStatus
from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.application.audit_codec import decision_request_from_json


def test_official_100ms_cannot_shrink_fixed_network_reserve():
    budget = BudgetPolicy().build(100.0, 3.0, 100.1)
    assert budget.enhancement_deadline_monotonic == 100.0
    assert budget.latest_send_at_monotonic == 100.0


def test_missing_deadline_estimates_but_expired_deadline_has_no_budget():
    assert BudgetPolicy().build(100.0, 3.0).latest_send_at_monotonic == pytest.approx(102.9)
    assert BudgetPolicy().build(100.0, 3.0, 99.9).latest_send_at_monotonic == 100.0


@pytest.mark.parametrize("expiry", [float("nan"), float("inf")])
def test_nonfinite_deadline_rejected(expiry):
    with pytest.raises(ValueError):
        replace(make_window(make_observation()), expires_at_monotonic=expiry)


def test_official_deadline_flag_requires_timestamp():
    with pytest.raises(ValueError):
        replace(make_window(make_observation()), deadline_is_estimated=False)


async def _run(window, *, submit_handler=None, rules=None, clock=None, policy=None):
    game = FakeGameSession(items=[window], submit_handler=submit_handler)
    session = FakeTournamentSession(
        bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=["g1"])),
        updates=[make_snapshot(TournamentStatus.FINISHED)],
        game_factory=lambda gid: game,
    )
    runtime, sink, policy, rules, clock, *_ = build_runtime(
        session=session, rules=rules, clock=clock, policy=policy,
    )
    task = asyncio.create_task(runtime.run())
    await wait_for_condition(lambda: game.drained)
    session.grant_updates(1)
    await task
    return game, sink, policy, rules


@pytest.mark.asyncio
@pytest.mark.parametrize("expiry", [99.9, 100.05, 100.1])
async def test_expired_or_network_only_window_never_reaches_policy_or_submit(expiry):
    window = replace(make_window(make_observation()), expires_at_monotonic=expiry, deadline_is_estimated=False)
    game, _, policy, rules = await _run(window)
    assert not game.submitted
    assert not policy.calls
    assert not rules.analyze_calls


@pytest.mark.asyncio
@pytest.mark.parametrize("new_expiry,expected_latest,expected_attempts", [
    (100.3, 100.2, 2), (110.0, 100.9, 2), (100.2, 100.1, 1), (100.05, 100.1, 1),
])
async def test_409_refresh_only_tightens_original_budget(new_expiry, expected_latest, expected_attempts):
    clock = ManualClock()
    window = replace(make_window(make_observation(), timeout=1.0), expires_at_monotonic=101.0, deadline_is_estimated=False)

    def submit(attempt):
        if attempt.attempt_no == 1:
            clock.advance(0.1)
            refreshed = replace(make_refreshed_window(window, seq=11, received_at=clock.now()),
                                expires_at_monotonic=new_expiry, deadline_is_estimated=False)
            return SubmitRejectedRetryable("INVALID_ACTION", attempt.action_key, refreshed)
        return SubmitAccepted(None, 11)

    game, _, policy, _ = await _run(window, clock=clock, submit_handler=submit)
    assert len(game.submitted) == expected_attempts
    if expected_attempts == 2:
        assert game.submitted[-1].latest_send_at_monotonic == pytest.approx(expected_latest)
        assert all(next_value <= old_value for next_value, old_value in zip(
            (policy.budgets[-1].enhancement_deadline_monotonic, policy.budgets[-1].fallback_deadline_monotonic, policy.budgets[-1].latest_send_at_monotonic),
            (policy.budgets[0].enhancement_deadline_monotonic, policy.budgets[0].fallback_deadline_monotonic, policy.budgets[0].latest_send_at_monotonic),
        ))


@pytest.mark.asyncio
async def test_rules_policy_and_audit_receive_complete_same_observation():
    class RecordingRules(FakeRules):
        def __init__(self):
            super().__init__(candidates=(DISCARD_3W,), emergency=DISCARD_3W)
            self.observations = []

        def analyze(self, observation):
            self.observations.append(observation)
            return super().analyze(observation)

        def emergency_action(self, observation):
            self.observations.append(observation)
            return super().emergency_action(observation)

        def validate(self, observation, action):
            self.observations.append(observation)
            return super().validate(observation, action)

    observation = replace(
        make_observation(), consumed_seq=12, history_complete=False,
        chain_piao=None, gang_draw=True, observation_issues=("history_gap",),
    )
    rules = RecordingRules()
    window = replace(make_window(observation), expires_at_monotonic=100.3, deadline_is_estimated=False)
    game, sink, policy, _ = await _run(window, rules=rules)
    assert game.submitted
    assert policy.calls[0].observation is observation
    assert rules.observations and all(item is observation for item in rules.observations)
    record = next(item for item in sink.records if item.kind.value == "decision_input")
    decoded = decision_request_from_json(record.payload["request"])
    assert decoded.observation == observation
    assert record.payload["window_deadline"] == {"expires_at_monotonic": 100.3, "deadline_is_estimated": False}


@pytest.mark.parametrize("remaining", [.15, .25, 1.0, 3.0])
def test_network_reserve_is_fixed_for_short_and_long_windows(remaining):
    budget = BudgetPolicy().build(100.0, 3.0, 100.0 + remaining)
    assert budget.latest_send_at_monotonic == pytest.approx(100.0 + remaining - .1)
    assert 100.0 < budget.enhancement_deadline_monotonic < budget.fallback_deadline_monotonic < budget.latest_send_at_monotonic


def test_repeated_same_deadline_refresh_does_not_charge_network_again():
    policy = BudgetPolicy()
    budget = policy.build(100.0, 1.0, 101.0)
    for received in (100.1, 100.2, 100.3):
        budget = policy.tighten(budget, received, 1.0, 101.0)
        assert budget.latest_send_at_monotonic == pytest.approx(100.9)


@pytest.mark.parametrize('received', [0.0, 100.1, 1_516_670.1, 1_000_000_000.1])
def test_exact_network_only_boundary_is_not_reopened_by_float_rounding(received):
    budget = BudgetPolicy().build(received, 1, received + .1)
    assert budget.latest_send_at_monotonic == received


@pytest.mark.parametrize("reserve", [0, -.1, float('inf'), float('nan')])
def test_invalid_fixed_reserve_rejected(reserve):
    with pytest.raises(ValueError):
        BudgetPolicy(post_reserve_seconds=reserve)
