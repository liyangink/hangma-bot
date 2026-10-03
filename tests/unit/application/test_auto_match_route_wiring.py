"""自动房路线事实接线：公开入口、原预算、真实规则审计及旧生命周期。"""
import asyncio
from dataclasses import fields, is_dataclass, replace
import json

import pytest

from fakes import (
    DISCARD_3W, PASS, FakeGameSession, FakePolicy, FakeRules, FakeTournamentSession,
    InMemoryAuditSink, ManualClock, SequencedIds, make_bootstrap, make_config,
    make_observation, make_refreshed_window, make_snapshot, make_window, wait_for_condition,
)
from hangma_bot.application.audit_codec import decision_request_from_json
from hangma_bot.application.auto_match_runtime import AutoMatchRuntime
from hangma_bot.application.contracts import (
    AuditKind, GameFinished, ParticipantTerminal, ParticipantTerminalReason, RuntimeMode,
    RuntimeTarget, SubmitAccepted, SubmitRejectedRetryable, TournamentStatus,
)
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import RuleCompleteness, ValueAnalysisLimits
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.config import RuleConfig
from tests.unit.policy.support import make_observation as rule_observation

pytestmark = pytest.mark.asyncio
LIMITS = ValueAnalysisLimits(8192, 128)
CONFIG = RuleConfig("auto-route-wiring-test", 1, False)


class WorkRules(FakeRules):
    """记录显式额度；注入单调时钟成本，独立紧急动作先于增强。"""
    def __init__(self, clock, *, emergency_cost=0, cost=0, fail=False):
        super().__init__(candidates=(DISCARD_3W, PASS), emergency=PASS)
        self.clock, self.emergency_cost, self.cost, self.fail = clock, emergency_cost, cost, fail
        self.events = []

    def emergency_action(self, observation):
        self.events.append("emergency")
        self.clock.advance(self.emergency_cost)
        return super().emergency_action(observation)

    def analyze(self, observation, **limits):
        self.events.append(limits)
        self.clock.advance(self.cost)
        if self.fail:
            raise RuntimeError("受控自动房路线事实失败")
        return super().analyze(observation)


class RealRules(HangmaRules):
    """记录请求，所有事实和最终复核均委托唯一规则引擎。"""
    def __init__(self):
        super().__init__(CONFIG)
        self.events = []

    def emergency_action(self, observation):
        self.events.append("emergency")
        return super().emergency_action(observation)

    def analyze(self, observation, **limits):
        self.events.append(limits)
        return super().analyze(observation, **limits)


def target():
    return RuntimeTarget(RuntimeMode.AUTO_MATCH, "", 8)


def real_observation():
    codes = ("1w", "2w", "3w", "1t", "2t", "3t", "1b", "2b", "3b", "7w", "8w", "东", "东")
    return rule_observation(my_hand=tuple(Tile(code) for code in codes), drawn_tile=Tile("南"),
        hand_counts=(14, 13, 13, 13), chain_piao=0, gang_draw=False)


def compare_all_fields(first, second):
    """包括 compare=False 的全部字段，不能只靠数据类默认相等。"""
    assert type(first) is type(second)
    if is_dataclass(first):
        for field in fields(first):
            compare_all_fields(getattr(first, field.name), getattr(second, field.name))
    elif type(first) is tuple:
        assert len(first) == len(second)
        for a, b in zip(first, second):
            compare_all_fields(a, b)
    else:
        assert first == second


def inputs(sink):
    return [record.payload for record in sink.records if record.kind is AuditKind.DECISION_INPUT]


async def drive(rules, *, clock, observation=None, handler=None, **configuration):
    """一次脚本房生命周期，不创建 HTTP 或注册/到位动作。"""
    sink, policy = InMemoryAuditSink(), FakePolicy()
    window = make_window(observation if observation is not None else make_observation(),
        received_at=100.0, timeout=1.0)
    game = FakeGameSession(items=[window, GameFinished("g1", (0, 0, 0, 0), 20)], submit_handler=handler)
    bootstrap = make_bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=("g1",), active_games=("g1",)),
        config=make_config(max_games=1, rounds=1))
    if isinstance(rules, RealRules):
        bootstrap = replace(bootstrap, config=replace(bootstrap.config, rules=CONFIG))
    session = FakeTournamentSession(bootstrap=bootstrap,
        updates=[make_snapshot(TournamentStatus.FINISHED, my_games=("g1",), active_games=())],
        game_factory=lambda _id: game)
    runtime = AutoMatchRuntime(session=session, policy=policy, audit_sink=sink, target=target(),
        clock=clock, ids=SequencedIds(), rules_factory=lambda _config: rules, **configuration)
    task = asyncio.create_task(runtime.run())
    try:
        await wait_for_condition(lambda: any(record.kind is AuditKind.GAME_FINISHED for record in sink.records))
        session.grant_updates(1)
        terminal = await asyncio.wait_for(task, 5)
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    assert session.register_calls == 0 and session.ready_calls == []
    assert session.closed
    manifest = next(record.payload for record in sink.records if record.kind is AuditKind.RUN_MANIFEST)
    return game, sink, policy, manifest


@pytest.mark.parametrize("configuration,expected", (
    ({}, {}), ({"route_limits": LIMITS}, {"route_limits": LIMITS}),
    ({"value_limits": LIMITS}, {"value_limits": LIMITS}),
    ({"value_limits": LIMITS, "route_limits": LIMITS}, {"value_limits": LIMITS, "route_limits": LIMITS}),
))
async def test_auto_match_explicit_limits_after_emergency_and_actual_manifest(configuration, expected):
    clock = ManualClock()
    rules = WorkRules(clock)
    game, sink, policy, manifest = await drive(rules, clock=clock, **configuration)
    assert rules.events == ["emergency", expected]
    assert len(game.submitted) == 1
    assert policy.budgets[0].enhancement_deadline_monotonic == pytest.approx(100.45)
    assert policy.budgets[0].latest_send_at_monotonic == pytest.approx(100.9)
    assert manifest["route_analysis_limits"] == (
        {"max_expansions":8192, "max_routes_per_candidate":128} if "route_limits" in configuration else None)
    assert manifest["value_analysis_limits"] == (
        {"max_expansions":8192, "max_routes_per_candidate":128} if "value_limits" in configuration else None)
    assert set(inputs(sink)[0]["request"]["rules"]) == {
        "codec_version", "ruleset_version", "completeness", "legal_candidates", "emergency_candidate", "issues"}


@pytest.mark.parametrize("now,emergency_cost", ((100.45, 0), (100.5, 0), (100, .45)))
async def test_auto_match_late_or_emergency_cost_does_not_regrant_route_enhancement(now, emergency_cost):
    clock = ManualClock(now)
    rules = WorkRules(clock, emergency_cost=emergency_cost)
    game, _, policy, _ = await drive(rules, clock=clock, route_limits=LIMITS, value_limits=LIMITS)
    assert rules.events == ["emergency", {}]
    assert len(game.submitted) == 1
    assert policy.budgets[0].enhancement_deadline_monotonic == pytest.approx(100.45)


async def test_auto_match_409_uses_original_budget_and_disables_late_route_work():
    clock = ManualClock()
    rules = WorkRules(clock)
    original_window = make_window(make_observation(), received_at=100, timeout=1)
    submissions = []
    def handler(attempt):
        submissions.append(attempt)
        if len(submissions) == 1:
            clock.advance(.55)
            return SubmitRejectedRetryable("CONFLICT", attempt.action_key,
                make_refreshed_window(original_window, seq=11, received_at=100.55))
        return SubmitAccepted("200", 12)
    game, sink, policy, _ = await drive(rules, clock=clock, handler=handler, route_limits=LIMITS)
    assert len(game.submitted) == 2
    assert rules.events == ["emergency", {"route_limits": LIMITS}, "emergency", {}]
    assert policy.budgets[0] is policy.budgets[1]
    assert policy.calls[1].rejected_attempts[0].action_key == "discard:3w"
    first, second = inputs(sink)
    assert first["budget"] == second["budget"]
    assert first["budget_origin_monotonic"] == second["budget_origin_monotonic"] == 100


@pytest.mark.parametrize("route_limits", (None, LIMITS))
async def test_auto_match_true_rule_route_facts_lossless_audit(route_limits):
    clock, rules = ManualClock(), RealRules()
    game, sink, policy, _ = await drive(rules, clock=clock, observation=real_observation(), route_limits=route_limits)
    assert len(game.submitted) == 1
    assert rules.events == ["emergency", {} if route_limits is None else {"route_limits": LIMITS}, {}]
    request = policy.calls[0]
    assert (request.rules.route_frontier is not None) == (route_limits is not None)
    assert (request.rules.conditional_roots is not None) == (route_limits is not None)
    if route_limits is not None:
        assert tuple(root.action_key for root in request.rules.conditional_roots) == tuple(c.action_key for c in request.rules.legal_candidates)
    restored = decision_request_from_json(json.loads(json.dumps(inputs(sink)[0]["request"], allow_nan=False)))
    compare_all_fields(request, restored)


async def test_auto_match_rule_failure_preserves_emergency_and_audits_degradation():
    clock = ManualClock()
    rules = WorkRules(clock, fail=True)
    game, sink, _, _ = await drive(rules, clock=clock, route_limits=LIMITS)
    assert rules.events == ["emergency", {"route_limits": LIMITS}]
    assert [attempt.action_key for attempt in game.submitted] == ["pass"]
    request = decision_request_from_json(inputs(sink)[0]["request"])
    assert request.rules.completeness is RuleCompleteness.DEGRADED
    assert request.rules.emergency_candidate.action_key == "pass"
    assert request.rules.conditional_roots is request.rules.route_frontier is None


async def test_auto_match_rule_work_cannot_extend_original_send_deadline():
    clock = ManualClock()
    rules = WorkRules(clock, cost=.9)
    game, sink, _, _ = await drive(rules, clock=clock, route_limits=LIMITS)
    assert not game.submitted
    assert rules.events == ["emergency", {"route_limits": LIMITS}]
    assert inputs(sink)[0]["rule_elapsed_ms"] == pytest.approx(900)


@pytest.mark.parametrize("route_requested", (False, True))
async def test_auto_match_old_value_scope_does_not_silently_replace_route_limits(route_requested):
    clock = ManualClock()
    rules = WorkRules(clock)
    configuration = {"value_limits": LIMITS, "value_rules_scope": CONFIG}
    if route_requested:
        configuration["route_limits"] = LIMITS
    _, _, _, manifest = await drive(rules, clock=clock, **configuration)
    assert rules.events == ["emergency", {"route_limits": LIMITS} if route_requested else {}]
    assert manifest["value_analysis_limits"] is None
    assert manifest["value_analysis_disabled_reason"] == "uncalibrated_rule_config"
    assert (manifest["route_analysis_limits"] is not None) == route_requested


@pytest.mark.parametrize("configuration,error", (
    ({"route_limits":True}, TypeError), ({"route_limits":{}}, TypeError),
    ({"value_limits":True}, TypeError),
    ({"value_limits":ValueAnalysisLimits(1), "route_limits":LIMITS}, ValueError),
))
async def test_auto_match_invalid_limits_rejected_before_any_session_call(configuration, error):
    session = FakeTournamentSession(bootstrap=make_bootstrap(make_snapshot()))
    with pytest.raises(error):
        AutoMatchRuntime(session=session, policy=FakePolicy(), audit_sink=InMemoryAuditSink(),
            target=target(), **configuration)
    assert not session.initialize_calls and session.register_calls == 0 and not session.ready_calls
    assert not session.game_opens


async def test_auto_match_early_terminal_keeps_single_operation_cleanup():
    terminal = ParticipantTerminal(ParticipantTerminalReason.MATCHING_UNAVAILABLE, None, "受控未匹配")
    session, sink = FakeTournamentSession(bootstrap=terminal), InMemoryAuditSink()
    result = await AutoMatchRuntime(session=session, policy=FakePolicy(), audit_sink=sink,
        target=target(), route_limits=LIMITS, clock=ManualClock(), ids=SequencedIds()).run()
    assert result is terminal and len(session.initialize_calls) == 1
    assert session.register_calls == 0 and not session.ready_calls and not session.game_opens
    assert session.closed
    manifest = next(record.payload for record in sink.records if record.kind is AuditKind.RUN_MANIFEST)
    assert manifest["early_exit"] is True
    assert "route_analysis_limits" not in manifest
