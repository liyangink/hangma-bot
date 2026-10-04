"""路线事实从公开运行入口接线；只用脚本策略，不运行真实 choose 或官方房。"""

import asyncio
from dataclasses import fields, is_dataclass, replace
import json

import pytest

from fakes import (
    DISCARD_3W, PASS, FakeGameSession, FakePolicy, FakeRules, FakeTournamentSession,
    InMemoryAuditSink, ManualClock, SequencedIds, make_bootstrap, make_competition,
    make_observation, make_refreshed_window, make_snapshot, make_target, make_window,
    wait_for_condition,
)
from hangma_bot.application.audit import AuditTrail
from hangma_bot.application.audit_codec import decision_request_from_json, rule_analysis_to_json
from hangma_bot.application.contracts import AuditKind, SubmitAccepted, SubmitRejectedRetryable, TournamentStatus
from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.application.decision_loop import RuntimeServices, run_action_window
from hangma_bot.application.participant_runtime import ParticipantRuntime
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import RuleCompleteness, ValueAnalysisLimits
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.config import RuleConfig
from tests.unit.policy.support import make_observation as make_rule_observation


LIMITS = ValueAnalysisLimits(max_expansions=8192, max_routes_per_candidate=128)
CONFIG = RuleConfig("application-route-wiring-test", 1, False)
ORDINARY = ("1w", "2w", "3w", "1t", "2t", "3t", "1b", "2b", "3b", "7w", "8w", "东", "东")


def real_observation():
    return make_rule_observation(
        my_hand=tuple(Tile(code) for code in ORDINARY), drawn_tile=Tile("南"),
        hand_counts=(14, 13, 13, 13), chain_piao=0, gang_draw=False,
    )


def assert_all_fields_equal(before, after):
    """完整比较审计输入，包括数据类 compare=False 字段。"""
    assert type(before) is type(after)
    if is_dataclass(before):
        for field in fields(before):
            assert_all_fields_equal(getattr(before, field.name), getattr(after, field.name))
    elif type(before) is tuple:
        assert len(before) == len(after)
        for first, second in zip(before, after):
            assert_all_fields_equal(first, second)
    else:
        assert before == after


class WorkRules(FakeRules):
    """记录实传关键字，并以注入时钟模拟规则或紧急路径耗时。"""

    def __init__(self, clock, *, cost=0.0, emergency_cost=0.0, fail=False):
        super().__init__(candidates=(DISCARD_3W, PASS), emergency=PASS)
        self.clock, self.cost, self.emergency_cost, self.fail = clock, cost, emergency_cost, fail
        self.events = []

    def emergency_action(self, observation):
        self.events.append("emergency")
        self.clock.advance(self.emergency_cost)
        return super().emergency_action(observation)

    def analyze(self, observation, **limits):
        self.events.append(limits)
        self.clock.advance(self.cost)
        if self.fail:
            raise RuntimeError("受控路线分析失败")
        return super().analyze(observation)


class RealRules(HangmaRules):
    """委托唯一规则引擎，记录应用请求的增强额度与真实分析。"""

    def __init__(self, config=CONFIG, *, recovery=None):
        super().__init__(config)
        self.events, self.analyses = [], []
        self.recovery = recovery

    def emergency_action(self, observation):
        self.events.append("emergency")
        return super().emergency_action(observation)

    def analyze(self, observation, **limits):
        self.events.append(limits)
        analysis = super().analyze(observation, **limits)
        if self.recovery:
            emergency = analysis.emergency_candidate
            assert emergency is not None
            candidates = tuple(c for c in analysis.legal_candidates if c.action_key != emergency.action_key)
            analysis = replace(analysis, legal_candidates=candidates,
                               emergency_candidate=emergency if self.recovery == "analysis" else None)
        self.analyses.append(analysis)
        return analysis


def services_for(rules, *, clock=None, policy=None, sink=None, **limits):
    clock = clock if clock is not None else ManualClock()
    sink = sink if sink is not None else InMemoryAuditSink()
    policy = policy if policy is not None else FakePolicy()
    return RuntimeServices(rules, policy, AuditTrail(
        sink, run_id="run-route-test", tournament_id="t1", participant_id="p1", clock=clock,
    ), clock, SequencedIds(), BudgetPolicy(), **limits)


async def run_window(rules, *, clock=None, observation=None, arrived=100.0, handler=None, **limits):
    sink = InMemoryAuditSink()
    services = services_for(rules, clock=clock, sink=sink, **limits)
    window = make_window(observation if observation is not None else make_observation(),
                         received_at=arrived, timeout=1.0)
    game = FakeGameSession(submit_handler=handler)
    result = await run_action_window(session=game, window=window, services=services,
                                     competition=make_competition(), stage_attempt_id="attempt-route-1")
    return result, game, sink, services.policy


def inputs(sink):
    return [record.payload for record in sink.records if record.kind is AuditKind.DECISION_INPUT]


@pytest.mark.parametrize("configuration,expected", (
    ({}, {}), ({"value_limits": LIMITS}, {"value_limits": LIMITS}),
    ({"route_limits": LIMITS}, {"route_limits": LIMITS}),
    ({"value_limits": LIMITS, "route_limits": LIMITS}, {"value_limits": LIMITS, "route_limits": LIMITS}),
))
async def test_explicit_limits_only_are_requested_after_emergency(configuration, expected):
    clock = ManualClock()
    rules = WorkRules(clock)
    result, game, sink, policy = await run_window(rules, clock=clock, **configuration)
    assert result.outcome_kind == "accepted" and len(game.submitted) == 1
    assert rules.events == ["emergency", expected]
    assert policy.budgets[0].latest_send_at_monotonic == pytest.approx(100.9)
    assert set(inputs(sink)[0]["request"]["rules"]) == {
        "codec_version", "ruleset_version", "completeness", "legal_candidates", "emergency_candidate", "issues",
    }


@pytest.mark.parametrize("now,emergency_cost", ((100.45, 0), (100.5, 0), (100.0, .45)))
async def test_late_window_or_emergency_work_does_not_request_route_enhancement(now, emergency_cost):
    clock = ManualClock(now)
    rules = WorkRules(clock, emergency_cost=emergency_cost)
    result, game, *_ = await run_window(rules, clock=clock, route_limits=LIMITS, value_limits=LIMITS)
    assert result.outcome_kind == "accepted" and len(game.submitted) == 1
    assert rules.events == ["emergency", {}]


async def test_retry_keeps_original_budget_and_loses_route_enhancement_after_deadline():
    clock = ManualClock()
    rules = WorkRules(clock)
    window = make_window(make_observation(), timeout=1.0)
    calls = []

    def handler(attempt):
        calls.append(attempt)
        if len(calls) == 1:
            clock.advance(.55)
            return SubmitRejectedRetryable("CONFLICT", attempt.action_key,
                                          make_refreshed_window(window, seq=11, received_at=100.55))
        return SubmitAccepted("200", 12)

    result, game, sink, policy = await run_window(rules, clock=clock, handler=handler, route_limits=LIMITS)
    assert result.outcome_kind == "accepted" and len(game.submitted) == 2
    assert rules.events == ["emergency", {"route_limits": LIMITS}, "emergency", {}]
    assert policy.budgets[0] is policy.budgets[1]
    assert policy.calls[1].rejected_attempts[0].action_key == "discard:3w"
    first, second = inputs(sink)
    assert first["budget"] == second["budget"]
    assert first["budget_origin_monotonic"] == second["budget_origin_monotonic"] == 100
    assert second["request"]["observation"]["snapshot_seq"] == 11


async def test_route_analysis_exception_keeps_independent_emergency_and_audits_degradation():
    clock = ManualClock()
    rules = WorkRules(clock, fail=True)
    result, game, sink, _ = await run_window(rules, clock=clock, route_limits=LIMITS)
    assert result.outcome_kind == "accepted"
    assert rules.events == ["emergency", {"route_limits": LIMITS}]
    assert [attempt.action_key for attempt in game.submitted] == ["pass"]
    request = decision_request_from_json(inputs(sink)[0]["request"])
    assert request.rules.completeness is RuleCompleteness.DEGRADED
    assert request.rules.emergency_candidate.action_key == "pass"
    assert request.rules.route_frontier is request.rules.conditional_roots is None
    assert any("analyze 抛出异常" in issue.reason for issue in request.rules.issues)


async def test_route_work_cannot_extend_original_send_deadline():
    clock = ManualClock()
    rules = WorkRules(clock, cost=.9)
    result, game, sink, _ = await run_window(rules, clock=clock, route_limits=LIMITS)
    assert rules.events == ["emergency", {"route_limits": LIMITS}]
    assert result.outcome_kind == "deadline" and not game.submitted
    assert inputs(sink)[0]["rule_elapsed_ms"] == pytest.approx(900)


@pytest.mark.parametrize("recovery", (None, "analysis", "independent"))
async def test_real_route_facts_and_emergency_recovery_are_losslessly_audited(recovery):
    rules = RealRules(recovery=recovery)
    result, game, sink, policy = await run_window(rules, observation=real_observation(), route_limits=LIMITS)
    assert result.outcome_kind == "accepted" and len(game.submitted) == 1
    # 提交复核由真实规则引擎再次调用普通 analyze，不重新请求增强。
    assert rules.events == ["emergency", {"route_limits": LIMITS}, {}]
    original = rules.analyses[0]
    actual = policy.calls[0].rules
    assert actual.route_frontier is original.route_frontier
    assert actual.conditional_roots is original.conditional_roots
    assert actual.route_frontier is not None and actual.conditional_roots
    assert actual.emergency_candidate is not None
    assert actual.emergency_candidate.action_key in {c.action_key for c in actual.legal_candidates}
    entry = inputs(sink)[0]
    restored = decision_request_from_json(json.loads(json.dumps(entry["request"], allow_nan=False)))
    assert_all_fields_equal(policy.calls[0], restored)
    assert rule_analysis_to_json(restored.rules) == entry["request"]["rules"]
    if recovery is None:
        assert [root.action_key for root in actual.conditional_roots] == [c.action_key for c in actual.legal_candidates]


@pytest.mark.parametrize("limits,error", (
    ({"route_limits": True}, TypeError), ({"route_limits": {}}, TypeError),
    ({"value_limits": True}, TypeError),
    ({"value_limits": ValueAnalysisLimits(1), "route_limits": LIMITS}, ValueError),
))
def test_invalid_or_conflicting_limits_are_rejected_at_both_assembly_boundaries(limits, error):
    rules = FakeRules()
    with pytest.raises(error):
        services_for(rules, **limits)
    session = FakeTournamentSession(bootstrap=make_bootstrap(make_snapshot()))
    with pytest.raises(error):
        ParticipantRuntime(session=session, policy=FakePolicy(), audit_sink=InMemoryAuditSink(),
                           target=make_target(), **limits)
    assert session.initialize_calls == [] and session.register_calls == 0 and session.game_opens == []


@pytest.mark.parametrize("route_limits", (None, LIMITS))
async def test_participant_runtime_passes_actual_route_limits_and_records_manifest(route_limits):
    clock, sink, policy = ManualClock(), InMemoryAuditSink(), FakePolicy()
    rules = RealRules()
    game = FakeGameSession(items=[make_window(real_observation())])
    bootstrap = make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=["g1"]))
    bootstrap = replace(bootstrap, config=replace(bootstrap.config, rules=CONFIG))
    session = FakeTournamentSession(bootstrap=bootstrap,
                                   updates=[make_snapshot(TournamentStatus.FINISHED)],
                                   game_factory=lambda _game_id: game)
    runtime = ParticipantRuntime(session=session, policy=policy, audit_sink=sink,
                                 target=make_target(), clock=clock, ids=SequencedIds(),
                                 rules_factory=lambda config: rules, route_limits=route_limits)
    task = asyncio.create_task(runtime.run())
    try:
        await wait_for_condition(lambda: game.drained)
        session.grant_updates()
        terminal = await task
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert terminal.reason.value == "tournament_finished" and not runtime.audit_degraded
    assert len(game.submitted) == 1 and session.closed
    assert rules.events == ["emergency", {} if route_limits is None else {"route_limits": LIMITS}, {}]
    manifest = next(r.payload for r in sink.records if r.kind is AuditKind.RUN_MANIFEST)
    assert manifest["route_analysis_limits"] == (None if route_limits is None else {
        "max_expansions": LIMITS.max_expansions, "max_routes_per_candidate": LIMITS.max_routes_per_candidate,
    })
    assert manifest["value_analysis_limits"] is None
    restored = decision_request_from_json(inputs(sink)[0]["request"])
    assert_all_fields_equal(policy.calls[0], restored)
    assert (restored.rules.conditional_roots is not None) == (route_limits is not None)


@pytest.mark.parametrize("requires,called", ((False, True), (True, False)))
async def test_missing_expired_conditional_facts_skip_only_declared_vip(requires, called):
    """条件事实预算耗尽时仅VIP跳过，普通路线策略仍按原预算调用。"""
    clock = ManualClock(100.5)
    rules = WorkRules(clock)
    result, game, sink, policy = await run_window(
        rules, clock=clock, route_limits=LIMITS, requires_conditional_roots=requires)
    assert result.outcome_kind == "accepted" and len(game.submitted) == 1
    assert bool(policy.budgets) is called
    assert rules.events == ["emergency", {}]
    if requires:
        planned = [r.payload for r in sink.records if r.kind is AuditKind.DECISION_PLANNED]
        assert planned and planned[0]["returned_plan"] is None
        recovered = [r.payload for r in sink.records if r.kind is AuditKind.PROTOCOL_RECOVERED]
        assert any("跳过策略" in note for row in recovered for note in row.get("reasons", []))
