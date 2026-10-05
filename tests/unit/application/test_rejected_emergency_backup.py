"""明确拒绝后备用动作的公开动作循环契约；假单调时钟，不重授预算。"""

from dataclasses import replace
import pytest
from fakes import (FakeGameSession, FakePolicy, FakeRules, InMemoryAuditSink,
    ManualClock, SequencedIds, make_competition, make_observation, make_refreshed_window, make_window)
from hangma_bot.application.audit import AuditTrail
from hangma_bot.application.contracts import SubmitAccepted, SubmitAmbiguous, SubmitRejectedRetryable
from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.application.decision_loop import RuntimeServices, run_action_window
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.actions import Discard, Tile


@pytest.mark.parametrize("scenario", ["scoring_failure", "enhancement_expired", "all_rejected", "window_changed", "ambiguous"])
async def test_backup_is_prepared_before_scoring_and_never_becomes_rule_emergency(scenario):
    """未拒合法备用可在失败/预算跳过后提交；全拒、换窗、模糊都停止旧窗追加。"""
    first, second, third = (Discard(Tile(code)) for code in ("3w", "1w", "2w"))
    sink, clock = InMemoryAuditSink(), ManualClock()
    window = make_window(make_observation(), timeout=1.0)

    class Rules(FakeRules):
        def analyze(self, observation, **kwargs):
            return super().analyze(observation)

    class Policy(FakePolicy):
        async def choose(self, request, budget):
            if request.rejected_attempts:
                assert request.rules.emergency_candidate.action == first
                if scenario != "all_rejected" or len(request.rejected_attempts) < 3:
                    assert any(record.payload.get("area") == "rejected_emergency_backup" for record in sink.records)
                if scenario == "scoring_failure":
                    self.calls.append(request)
                    self.budgets.append(budget)
                    raise RuntimeError("forced-scoring-failure")
            return await super().choose(request, budget)

    rules = Rules(candidates=(first, second, third), emergency=first)
    policy = Policy()

    def handle(attempt):
        if len(game.submitted) == 1 or scenario == "all_rejected":
            if scenario == "ambiguous":
                return SubmitAmbiguous("public-recovery", "simulated-timeout")
            if scenario == "enhancement_expired":
                clock.advance(0.55)
            fresh = make_refreshed_window(window, seq=10 + len(game.submitted))
            if scenario == "window_changed":
                fresh = replace(fresh, window_key=replace(fresh.window_key, trigger_seq=99))
            return SubmitRejectedRetryable("CONFLICT", attempt.action_key, fresh)
        return SubmitAccepted("200", 12)

    game = FakeGameSession(submit_handler=handle)
    services = RuntimeServices(rules=rules, policy=policy,
        audit=AuditTrail(sink, run_id="public-run", tournament_id="t1", participant_id="p1", clock=clock),
        clock=clock, ids=SequencedIds(), budget_policy=BudgetPolicy(),
        route_limits=ValueAnalysisLimits(1, 1), requires_conditional_roots=True)
    result = await run_action_window(session=game, window=window, services=services,
        competition=make_competition(), stage_attempt_id="public-attempt")
    backup_rows = [record for record in sink.records if record.payload.get("area") == "rejected_emergency_backup"]
    if scenario in ("scoring_failure", "enhancement_expired"):
        assert result.outcome_kind == "accepted"
        assert [attempt.action for attempt in game.submitted] == [first, second]
        assert rules.validate_calls == ["discard:3w", "discard:1w"]
        assert backup_rows[0].payload["is_rule_emergency"] is False
        planned = [record.payload for record in sink.records if record.kind.value == "decision_planned"][-1]
        backup, = planned["effective_candidates"]
        assert backup["is_emergency"] is False
        assert backup["score_parts"] == [{"name": "legal_retry_backup", "value": 0.0}]
        if scenario == "scoring_failure":
            assert policy.budgets[0] is policy.budgets[1]
        else:
            assert len(policy.calls) == 1
    elif scenario == "all_rejected":
        assert result.outcome_kind == "exhausted"
        assert [attempt.action for attempt in game.submitted] == [first, second, third]
        assert all(budget is policy.budgets[0] for budget in policy.budgets)
    else:
        assert result.outcome_kind == ("window_changed" if scenario == "window_changed" else "ambiguous")
        assert len(game.submitted) == len(policy.calls) == 1
        assert not backup_rows
    inputs = [record.payload for record in sink.records if record.kind.value == "decision_input"]
    assert all(item["budget"] == inputs[0]["budget"] for item in inputs)
