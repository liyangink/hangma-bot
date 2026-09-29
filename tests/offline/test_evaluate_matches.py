"""完整桌赛驱动（E2）测试：最小 Fake 引擎验证循环编排。

source_kind=simulation 的结果行由驱动生成；这里验证的是编排行为，
不产生强度结论（mock/Fake 引擎的结果不进统计门禁）。
"""

from __future__ import annotations

import asyncio

import pytest

from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.actions import Discard, Tile, WindowKey, WindowPhase
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.offline.evaluate import (
    MatchDriverConfig,
    MatchExperiment,
    MatchSeedSpec,
    PolicyDeclaration,
    build_match_result,
    drive_match,
    policy_ids_by_seat_from,
    run_match_experiment,
    seat_policies_from,
)
from hangma_bot.offline.evaluation_statistics import pair_matches, summarize_results
from hangma_bot.policy.safe_fallback import SafeFallbackPolicy

from support import (
    FakeChoice,
    FakeDecision,
    FakeEngine,
    FakeFrame,
    FakeMatchSpec,
    FakeRules,
    ScriptedPolicy,
    blocked_frame,
    candidates_for,
    draw_frame,
    final_frame,
    make_observation,
    make_rules,
    make_tournament_config,
    pick_illegal,
    pick_key,
)


def driver_config(step_limit: int = 100) -> MatchDriverConfig:
    return MatchDriverConfig(
        clock_mode="logical",
        step_limit=step_limit,
        budget_policy=BudgetPolicy(),
        competition_tournament_id="sc-1",
    )


def rules_with_emergency():
    candidates = candidates_for([Discard(Tile("1w")), Discard(Tile("2w"))])
    return make_rules(candidates, emergency=candidates[0])


def make_policies():
    policies = tuple(ScriptedPolicy(pick_key("discard:2w")) for _ in range(4))
    for index, policy in enumerate(policies):
        policy.policy_id = "policy-{0}".format(index)
    return policies


def make_spec(match_id: str = "m-1") -> FakeMatchSpec:
    return FakeMatchSpec(
        match_id=match_id,
        scenario_id="sc-1",
        config=make_tournament_config(rounds_per_game=1),
        seed=1,
        initial_dealer=0,
        initial_scores=(0, 0, 0, 0),
    )


def run_drive(engine, policies, rules, spec=None, config=None):
    return asyncio.run(
        drive_match(
            engine=engine,
            spec=spec or make_spec(),
            policies_by_seat=policies,
            rules=rules,
            choice_factory=FakeChoice,
            config=config or driver_config(),
            now_monotonic=lambda: 800.0,
            wall_clock=None,
        )
    )


def test_complete_run_collects_all_windows_and_advances_once():
    engine = FakeEngine(
        lambda spec: [draw_frame(1, [0, 1]), final_frame(2, [5, 0, 0, 0], completed_hands=1)]
    )
    outcome = run_drive(engine, make_policies(), FakeRules(rules_with_emergency()))
    assert outcome.status == "complete"
    assert outcome.final_scores == (5, 0, 0, 0)
    assert outcome.steps == 2
    assert len(engine.advance_calls) == 1
    revision, choices = engine.advance_calls[0][1], engine.advance_calls[0][2]
    assert revision == 1
    assert [choice.window_key.seat for choice in choices] == [0, 1]
    records = outcome.decisions
    assert [record.policy_id for record in records] == ["policy-0", "policy-1"]
    assert all(record.action_key == "discard:2w" for record in records)
    assert all(record.legal is True for record in records)
    assert all(record.fallback_reason is None for record in records)
    assert all(record.elapsed_ms is None for record in records)  # 逻辑时钟不产耗时
    assert outcome.runtime_counts.timeouts == 0
    assert outcome.runtime_counts.fallbacks == 0


def test_blocked_run_is_not_complete():
    engine = FakeEngine(
        lambda spec: [draw_frame(1, [0]), blocked_frame(2, "规则不支持 X", completed_hands=1)]
    )
    outcome = run_drive(engine, make_policies(), FakeRules(rules_with_emergency()))
    assert outcome.status == "blocked"
    assert outcome.blocked_reason == "规则不支持 X"
    assert outcome.final_scores is None
    result = build_match_result(
        match_id="m-1",
        scenario_id="sc-1",
        pair_id="p-1",
        config=make_tournament_config(rounds_per_game=1),
        policy_ids_by_seat=("policy-0", "policy-1", "policy-2", "policy-3"),
        seat_permutation=(0, 1, 2, 3),
        initial_scores_physical=(0, 0, 0, 0),
        outcome=outcome,
        versions=(("contract_id", "parallel-v1"),),
        result_id="r-1",
        source_kind="mock",
    )
    assert result.status == "partial"
    assert result.source_kind == "mock"
    assert result.invalid_reasons[0].startswith("blocked:")


def test_blocked_without_hands_is_error_result():
    engine = FakeEngine(lambda spec: [blocked_frame(1, "起点不可初始化")])
    outcome = run_drive(engine, make_policies(), FakeRules(rules_with_emergency()))
    assert outcome.status == "blocked"
    result = build_match_result(
        match_id="m-1",
        scenario_id="sc-1",
        pair_id="p-1",
        config=make_tournament_config(rounds_per_game=1),
        policy_ids_by_seat=("policy-0", "policy-1", "policy-2", "policy-3"),
        seat_permutation=(0, 1, 2, 3),
        initial_scores_physical=(0, 0, 0, 0),
        outcome=outcome,
        versions=(("contract_id", "parallel-v1"),),
        result_id="r-1",
        source_kind="mock",
    )
    assert result.status == "error"
    assert result.source_kind == "mock"


def test_empty_decisions_non_terminal_frame_errors():
    engine = FakeEngine(
        lambda spec: [FakeFrame(revision=1, decisions=(), completed_hands=0)]
    )
    outcome = run_drive(engine, make_policies(), FakeRules(rules_with_emergency()))
    assert outcome.status == "error"
    assert "空决策" in outcome.error_reason


def test_step_limit_errors_not_synthetic_draw():
    frames = lambda spec: [draw_frame(index + 1, [0]) for index in range(20)]
    engine = FakeEngine(frames)
    outcome = run_drive(engine, make_policies(), FakeRules(rules_with_emergency()), config=driver_config(step_limit=3))
    assert outcome.status == "error"
    assert "步数上限" in outcome.error_reason


def test_policy_exception_falls_back_to_emergency_and_counts():
    policies = make_policies()
    policies[0]._raise_error = RuntimeError("boom")
    engine = FakeEngine(
        lambda spec: [draw_frame(1, [0]), final_frame(2, [5, 0, 0, 0], completed_hands=1)]
    )
    outcome = run_drive(engine, policies, FakeRules(rules_with_emergency()))
    assert outcome.status == "complete"
    record = outcome.decisions[0]
    assert record.fallback_reason == "policy_error"
    assert record.is_emergency is True
    assert record.action_key == "discard:1w"
    assert outcome.runtime_counts.fallbacks == 1


def test_timeout_falls_back_and_counts():
    policies = make_policies()
    policies[0]._never_return = True
    engine = FakeEngine(
        lambda spec: [
            draw_frame(1, [0], timeout_seconds=0.01),
            final_frame(2, [5, 0, 0, 0], completed_hands=1),
        ]
    )
    outcome = run_drive(engine, policies, FakeRules(rules_with_emergency()))
    assert outcome.status == "complete"
    record = outcome.decisions[0]
    assert record.fallback_reason == "timeout"
    assert record.action_key == "discard:1w"
    assert outcome.runtime_counts.timeouts == 1


def test_illegal_choice_falls_back_to_emergency_and_counts():
    policies = make_policies()
    policies[0]._picker = pick_illegal("9w")
    engine = FakeEngine(
        lambda spec: [draw_frame(1, [0]), final_frame(2, [5, 0, 0, 0], completed_hands=1)]
    )
    outcome = run_drive(engine, policies, FakeRules(rules_with_emergency()))
    assert outcome.status == "complete"
    record = outcome.decisions[0]
    assert record.fallback_reason == "illegal_choice"
    assert record.action_key == "discard:1w"
    assert record.legal is True
    assert outcome.runtime_counts.illegal_choices == 1


def test_illegal_choice_without_emergency_errors():
    candidates = candidates_for([Discard(Tile("1w")), Discard(Tile("2w"))])
    rules = FakeRules(make_rules(candidates, emergency=None))
    policies = make_policies()
    policies[0]._picker = pick_illegal("9w")
    engine = FakeEngine(
        lambda spec: [draw_frame(1, [0]), final_frame(2, [5, 0, 0, 0], completed_hands=1)]
    )
    outcome = run_drive(engine, policies, rules)
    assert outcome.status == "error"
    assert "无可用动作" in outcome.error_reason


def test_advance_value_error_ends_with_error():
    engine = FakeEngine(
        lambda spec: [draw_frame(1, [0]), final_frame(2, [5, 0, 0, 0], completed_hands=1)],
        reject_advance=True,
    )
    outcome = run_drive(engine, make_policies(), FakeRules(rules_with_emergency()))
    assert outcome.status == "error"
    assert "advance" in outcome.error_reason


def test_seat_permutation_mapping_direction():
    policies_by_id = {"t": "policy-t", "o1": "policy-o1", "o2": "policy-o2", "o3": "policy-o3"}
    permutation = (2, 0, 1, 3)
    by_seat = seat_policies_from(policies_by_id, permutation, ["t", "o1", "o2", "o3"])
    assert by_seat == ("policy-o1", "policy-o2", "policy-t", "policy-o3")
    ids_by_seat = policy_ids_by_seat_from(permutation, ["t", "o1", "o2", "o3"])
    assert ids_by_seat == ("o1", "o2", "t", "o3")


def _run_two_rotation_experiment(source_kind, *, strict_challenger=False, challenger_error=None):
    def frames_factory(spec):
        challenger = ":candidate" in spec.match_id
        scores = [7, 0, 0, 0] if challenger else [3, 0, 0, 0]
        return [draw_frame(1, [spec.initial_dealer]), final_frame(2, scores, completed_hands=1)]

    engine = FakeEngine(frames_factory)
    policies = [ScriptedPolicy(pick_key("discard:2w")) for _ in range(5)]
    if challenger_error is not None:
        policies[1] = ScriptedPolicy(
            pick_key("discard:2w"), raise_error=challenger_error
        )
    for index, policy in enumerate(policies):
        policy.policy_id = ["stable", "candidate", "opp-1", "opp-2", "opp-3"][index]
    policies_by_id = {policy.policy_id: policy for policy in policies}
    experiment = MatchExperiment(
        kind="matches",
        clock_mode="logical",
        baseline=PolicyDeclaration("stable", "scripted"),
        challenger=PolicyDeclaration("candidate", "scripted"),
        opponents=tuple(PolicyDeclaration("opp-{0}".format(index), "scripted") for index in (1, 2, 3)),
        tournament_config=make_tournament_config(rounds_per_game=1),
        seeds=(MatchSeedSpec(seed=1, scenario_id="sc-1"),),
        seat_permutations=((0, 1, 2, 3), (2, 0, 1, 3)),
        initial_dealer=0,
        initial_scores=(0, 0, 0, 0),
        step_limit=100,
    )
    outcome = asyncio.run(
        run_match_experiment(
            experiment,
            engine=engine,
            spec_factory=lambda **kwargs: FakeMatchSpec(**kwargs),
            choice_factory=FakeChoice,
            policies_by_id=policies_by_id,
            rules=FakeRules(rules_with_emergency()),
            rules_hash="a" * 64,
            now_monotonic=lambda: 800.0,
            wall_clock=None,
            budget_policy=BudgetPolicy(),
            source_kind=source_kind,
            strict_challenger=strict_challenger,
        )
    )
    return outcome


def test_vip_strict_challenger_failure_does_not_inherit_emergency_results():
    """A 照常完整续打；C 的机械缺口在全部换座都保留为未完成。"""

    outcome = _run_two_rotation_experiment(
        "mock", strict_challenger=True,
        challenger_error=RuntimeError("MECHANICAL_GAP: chi followup"),
    )
    assert len(outcome.results) == 4
    baseline = [row for row in outcome.results if "stable" in row.policy_ids_by_seat]
    challenger = [row for row in outcome.results if "candidate" in row.policy_ids_by_seat]
    assert len(baseline) == len(challenger) == 2
    assert all(row.status == "complete" for row in baseline)
    assert all(row.status == "error" for row in challenger)
    assert all("MECHANICAL_GAP" in row.invalid_reasons[0] for row in challenger)
    assert all(row.scores_after is None for row in challenger)


def test_run_match_experiment_mock_labeled_and_excluded_from_strength():
    """E2 编排验证（Fake 引擎）必须报 mock，不冒充强度证据。"""

    outcome = _run_two_rotation_experiment(source_kind="mock")
    assert len(outcome.results) == 4
    assert outcome.excluded == ()
    by_pair = {}
    for result in outcome.results:
        assert result.status == "complete"
        assert result.source_kind == "mock"
        by_pair.setdefault(result.pair_id, []).append(result)
    assert len(by_pair) == 2  # 换座/配对结构照常生成
    pairing = pair_matches(
        outcome.results, baseline_policy_id="stable", challenger_policy_id="candidate"
    )
    assert pairing.pairs == ()
    assert any("不进入强度结论" in reason for reason in pairing.unpaired_reasons)
    report = summarize_results(
        outcome.results, baseline_policy_id="stable", challenger_policy_id="candidate"
    )
    conclusion = "；".join(report["sections"][-1]["paragraphs"])
    assert "数据不足" in conclusion


def test_run_match_experiment_simulation_labeled_pairs():
    """显式 source_kind=simulation 是真实驱动路径；配对统计照常工作。"""

    outcome = _run_two_rotation_experiment(source_kind="simulation")
    assert len(outcome.results) == 4
    for result in outcome.results:
        assert result.status == "complete"
        assert result.source_kind == "simulation"
        assert result.game_key.source_namespace == "hangma-simulation"
    pairing = pair_matches(
        outcome.results, baseline_policy_id="stable", challenger_policy_id="candidate"
    )
    assert len(pairing.pairs) == 2
    assert pairing.unpaired_reasons == ()
    rotated = [item for item in outcome.results if item.seat_permutation == (2, 0, 1, 3)]
    assert len(rotated) == 2
    for item in rotated:
        assert item.policy_ids_by_seat[2] in ("stable", "candidate")


def test_same_frame_windows_have_unique_decision_ids():
    """同帧多窗口（如三家碰响应）的 decision_id 必须唯一（AGENTS.md §8 关联链路）。"""

    captured = []

    def picker(request):
        captured.append(request.decision_id)
        return Discard(Tile("2w"))

    policies = tuple(ScriptedPolicy(picker) for _ in range(4))
    engine = FakeEngine(
        lambda spec: [
            draw_frame(1, [0, 1, 2, 3]),
            final_frame(2, [1, 0, 0, 0], completed_hands=1),
        ]
    )
    outcome = run_drive(engine, policies, FakeRules(rules_with_emergency()))
    assert outcome.status == "complete"
    assert len(captured) == 4
    assert len(set(captured)) == 4  # 修复前同帧同阶段同 seq 会碰撞
    record_ids = [record.decision_id for record in outcome.decisions]
    assert len(set(record_ids)) == 4
    for record in outcome.decisions:
        assert record.decision_id.endswith(":seat{0}".format(record.seat))


def test_real_hangma_rules_and_safe_fallback_integration():
    hand = tuple(
        Tile(code)
        for code in ("1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "1b", "2b", "3b", "4b", "5b", "9w")
    )
    observation = make_observation(
        seat=0, turn_seat=0, my_hand=hand, hand_counts=(14, 13, 13, 13)
    )
    decision = FakeDecision(
        window_key=WindowKey(game_id="g1", round_no=1, trigger_seq=1, phase=WindowPhase.DRAW, seat=0),
        observation=observation,
        timeout_seconds=3.0,
    )
    engine = FakeEngine(
        lambda spec: [
            FakeFrame(revision=1, decisions=(decision,), completed_hands=0),
            final_frame(2, [1, 0, 0, 0], completed_hands=1),
        ]
    )
    policies = tuple(SafeFallbackPolicy() for _ in range(4))
    for index, policy in enumerate(policies):
        policy.policy_id = "safe-{0}".format(index)
    rules = HangmaRules(RuleConfig(ruleset_version="test", base_score=1, you_cai_bi_kao=False))
    outcome = run_drive(engine, policies, rules)
    assert outcome.status == "complete"
    record = outcome.decisions[0]
    assert record.is_emergency is True
    assert record.action_key.startswith("discard:")
    assert record.legal is True


def test_policy_deadline_error_is_counted_as_timeout():
    """策略主动发现预算超限也属于 timeout，不能掩盖在普通异常保底里。"""
    from hangma_bot.policy.errors import PolicyTimeoutError
    policies = (ScriptedPolicy(pick_key('discard:2w'),raise_error=PolicyTimeoutError('deadline')),)+make_policies()[1:]
    engine = FakeEngine(lambda spec:[draw_frame(1,[0]),final_frame(2,[5,0,0,0],completed_hands=1)])
    outcome = run_drive(engine,policies,FakeRules(rules_with_emergency()))
    assert outcome.decisions[0].fallback_reason == 'timeout'
    assert outcome.runtime_counts.timeouts == 1
    assert outcome.runtime_counts.fallbacks == 0  # 现有计数定义为互斥类别
