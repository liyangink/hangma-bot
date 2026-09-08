"""离线增强计入同一窗口预算；赛后结果来自公开导出，不读取 WorldState。"""

import asyncio
import pytest

from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.offline.evaluate import HandCompletion, MatchDriverConfig, drive_match
from support import FakeChoice, FakeEngine, FakeRules, ScriptedPolicy, draw_frame, final_frame, pick_key
from test_evaluate_matches import make_spec, rules_with_emergency


@pytest.mark.parametrize("duration,status,action", [(2.25, "complete", "discard:1w"), (5.0, "error", None)])
def test_slow_rule_analysis_uses_original_budget_and_never_submits_after_deadline(duration, status, action):
    now = [800.0]
    order = []

    class SlowRules(FakeRules):
        def emergency_action(self, observation):
            order.append("emergency")
            return super().emergency_action(observation)

        def analyze(self, observation):
            order.append("analysis")
            now[0] += duration
            return super().analyze(observation)

    policy = ScriptedPolicy(pick_key("discard:2w"))
    engine = FakeEngine(lambda spec: [draw_frame(1, [0]), final_frame(2, [0, 0, 0, 0], completed_hands=1)])
    outcome = asyncio.run(drive_match(
        engine=engine, spec=make_spec(), policies_by_seat=(policy,) * 4,
        rules=SlowRules(rules_with_emergency()), choice_factory=FakeChoice,
        config=MatchDriverConfig("real", 100, BudgetPolicy(), "budget-test"),
        now_monotonic=lambda: now[0], wall_clock=lambda: now[0],
    ))
    assert order == ["emergency", "analysis"]
    assert outcome.status == status
    assert outcome.runtime_counts.timeouts == 1
    assert outcome.decisions[0].action_key == action
    assert outcome.decisions[0].elapsed_ms == duration * 1000
    assert outcome.decisions[0].fallback_reason == "timeout"
    if status == "error":
        assert not engine.advance_calls


def test_hand_callback_exports_completed_results_once_including_final_hand():
    exported = []
    reported = []

    class ExportingEngine(FakeEngine):
        def export_hand(self, world, round_no):
            exported.append(round_no)
            return {"winner_seat": 0, "fan": 4, "score_delta": [96, -32, -32, -32]}

    engine = ExportingEngine(lambda spec: [
        draw_frame(1, [0]), draw_frame(2, [0], completed_hands=1),
        final_frame(3, [192, -64, -64, -64], completed_hands=2),
    ])
    policy = ScriptedPolicy(pick_key("discard:2w"))
    outcome = asyncio.run(drive_match(
        engine=engine, spec=make_spec(), policies_by_seat=(policy,) * 4,
        rules=FakeRules(rules_with_emergency()), choice_factory=FakeChoice,
        config=MatchDriverConfig("logical", 100, BudgetPolicy(), "result-test"),
        now_monotonic=lambda: 800.0, wall_clock=None, on_hand_completed=reported.append,
    ))
    assert outcome.status == "complete"
    assert exported == [1, 2]
    assert reported == [HandCompletion(i, 0, 4, (96, -32, -32, -32)) for i in (1, 2)]
