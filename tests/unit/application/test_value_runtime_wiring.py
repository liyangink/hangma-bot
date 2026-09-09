"""可选分值进入真实决策循环：生产装配、预算与失败隔离均从公开行为验收。"""

import asyncio
import json
import time
from dataclasses import replace
from pathlib import Path

import pytest

from fakes import (
    DISCARD_3W, PASS, FakeGameSession, FakePolicy, FakeRules, FakeTournamentSession,
    InMemoryAuditSink, ManualClock, SequencedIds, make_bootstrap, make_competition,
    make_observation, make_refreshed_window, make_snapshot, make_window, wait_for_condition,
)
from hangma_bot.application.audit import AuditTrail
from hangma_bot.application.audit_codec import decision_request_from_json
from hangma_bot.application.contracts import GameFinished, SubmitAccepted, SubmitRejectedRetryable, TournamentStatus
from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.application.decision_loop import RuntimeServices, run_action_window
from hangma_bot.bootstrap import build_runtime, build_auto_match_runtime, runtime_config_from_mapping
from hangma_bot.application.auto_match_runtime import AutoMatchSettings
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.kernel.config import RuleConfig, TimingConfig, TournamentConfig


RULE_CONFIG = RuleConfig("hangma-mvp-v10-public-counts", 1, False)
LIMITS = ValueAnalysisLimits()


def runtime_config(tmp_path, strategy="v2_hu_upgrade_v1", **overrides):
    """只使用虚构 Token；网络会话在测试中通过公开组合入口替换。"""
    data = dict(mode="test_room", token_kind="test", token="fixture-not-a-real-token",
                base_url="https://platform.invalid", expected_tournament_id="t1",
                known_guide_version=23, audit_root=str(tmp_path), strategy=strategy)
    return runtime_config_from_mapping(dict(data, **overrides))


def bootstrap(snapshot, rules=RULE_CONFIG):
    return make_bootstrap(snapshot, guide_version=23, config=TournamentConfig(
        10, 8, rules, TimingConfig(1, 1, 3),
    ))


def records(assembled):
    return [json.loads(line) for path in assembled.sink.run_dir.rglob("*.jsonl")
            for line in path.read_text().splitlines() if line]


@pytest.mark.parametrize("strategy", ["v2_hu_upgrade_v1", "weighted_heuristic_v2"])
@pytest.mark.parametrize("mode", ["test_room", "auto_match"])
async def test_production_assembly_runs_ten_games_and_records_effective_value_configuration(tmp_path, strategy, mode):
    """真实规则/策略/磁盘审计执行十个共同到达窗口，旧 V2 不生成分值事实。"""
    games = {}
    session = FakeTournamentSession(
        bootstrap=bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=[f"g{i}" for i in range(10)],
                                          active_games=[f"g{i}" for i in range(10)])),
        updates=[make_snapshot(TournamentStatus.FINISHED)], game_factory=games.__getitem__,
    )
    config = runtime_config(tmp_path, strategy, mode=mode, token_kind="official" if mode == "auto_match" else "test")
    assembled = (build_auto_match_runtime(config, AutoMatchSettings(), session_factory=lambda: session)
                 if mode == "auto_match" else build_runtime(config, session_factory=lambda: session))
    fixture_root = Path(__file__).resolve().parents[2] / "fixtures/policy/one-draw-value"
    arrived = time.monotonic()
    for i in range(10):
        name = "A" if i % 2 == 0 else "F"
        request = decision_request_from_json(json.loads((fixture_root / f"{name}.json").read_text())[
            "request_event"]["payload"]["request"])
        obs = replace(request.observation, game_id=f"g{i}")
        games[obs.game_id] = FakeGameSession(items=[
            make_window(obs, received_at=arrived),
            GameFinished(obs.game_id, (0, 0, 0, 0), obs.snapshot_seq + 1),
        ])
    task = asyncio.create_task(assembled.run())
    try:
        await wait_for_condition(lambda: all(len(game.submitted) == 1 for game in games.values()))
        session.grant_updates()
        terminal = await task
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert terminal.reason.value == "tournament_finished"
    assert not assembled.audit_degraded
    for i, game in enumerate(games.values()):
        assert len(game.submitted) == 1
        expected = ("discard:5b" if i % 2 == 0 else "discard:白") if strategy == "v2_hu_upgrade_v1" else "hu"
        assert game.submitted[0].action_key == expected
    audit = records(assembled)
    manifest = json.loads((assembled.sink.run_dir / "manifest.json").read_text())["payload"]
    assert manifest["base_score"] == 1 and manifest["you_cai_bi_kao"] is False
    assert manifest["policy_version"] == strategy
    inputs = [item["payload"] for item in audit if item["kind"] == "decision_input"]
    assert len(inputs) == 10
    has_values = [any(c.get("value_facts") is not None for c in item["request"]["rules"]["legal_candidates"])
                  for item in inputs]
    assert has_values == [strategy == "v2_hu_upgrade_v1"] * 10
    if strategy == "v2_hu_upgrade_v1":
        assert manifest["value_analysis_limits"] == {"max_expansions": 2048, "max_routes_per_candidate": 128}
        assert manifest["policy_weights"]["risk_version"] == "hu-upgrade-risk-v2-v10"
        assert manifest["policy_weights"]["base_policy"] == "weighted_heuristic_v2"
        assert len(manifest["policy_weights"]["risk_cells"]) == 2
    else:
        assert manifest["value_analysis_limits"] is None
        assert "risk_version" not in manifest["policy_weights"]


@pytest.mark.parametrize("rules", [replace(RULE_CONFIG, you_cai_bi_kao=True),
                                  replace(RULE_CONFIG, base_score=2),
                                  replace(RULE_CONFIG, ruleset_version="hangma-mvp-v5-four-white"),
                                  replace(RULE_CONFIG, ruleset_version="unknown-version")])
async def test_candidate_rejects_actual_uncalibrated_rules_before_register_ready_or_open(tmp_path, rules):
    session = FakeTournamentSession(bootstrap=bootstrap(make_snapshot(TournamentStatus.REGISTERING), rules))
    assembled = build_runtime(runtime_config(tmp_path), session_factory=lambda: session)
    terminal = await assembled.run()
    assert terminal.reason.value == "fatal_protocol_error"
    assert "测试范围要求" in terminal.detail
    assert session.register_calls == 0 and session.ready_calls == [] and session.game_opens == []
    assert session.closed


@pytest.mark.parametrize("mode,token_kind", [("official_tournament", "official"),
                                          ("test_tournament", "test")])
def test_candidate_cannot_accidentally_enter_unapproved_competition_modes(tmp_path, mode, token_kind):
    with pytest.raises(ValueError, match="仅允许 mode=test_room/auto_match"):
        runtime_config(tmp_path, mode=mode, token_kind=token_kind)


@pytest.mark.parametrize("rules", [replace(RULE_CONFIG, you_cai_bi_kao=True),
                                  replace(RULE_CONFIG, base_score=2),
                                  replace(RULE_CONFIG, ruleset_version="hangma-mvp-v5-four-white"),
                                  replace(RULE_CONFIG, ruleset_version="unknown-version")])
async def test_auto_match_uncalibrated_rules_finish_with_v2_without_optional_values(tmp_path, rules):
    """已经入席的自由房不因校准范围退出；真实规则照用，所有决策与V2相同。"""
    from hangma_bot.hangma import HangmaRules
    from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
    from hangma_bot.policy.interface import DecisionBudget
    games, expected = {}, {}
    session = FakeTournamentSession(
        bootstrap=bootstrap(make_snapshot(TournamentStatus.RUNNING, my_games=[f"g{i}" for i in range(4)],
                                          active_games=[f"g{i}" for i in range(4)]), rules),
        updates=[make_snapshot(TournamentStatus.FINISHED)], game_factory=games.__getitem__,
    )
    config = runtime_config(tmp_path, mode="auto_match", token_kind="official")
    assembled = build_auto_match_runtime(config, AutoMatchSettings(), session_factory=lambda: session)
    fixture_root = Path(__file__).resolve().parents[2] / "fixtures/policy/one-draw-value"
    arrived = time.monotonic()
    for i, name in enumerate("ABFG"):
        req = decision_request_from_json(json.loads((fixture_root / f"{name}.json").read_text())[
            "request_event"]["payload"]["request"])
        obs = replace(req.observation, game_id=f"g{i}")
        req = replace(req, observation=obs, rules=HangmaRules(rules).analyze(obs))
        expected[obs.game_id] = await ComparableHeuristicPolicyV2(monotonic=lambda: 0).choose(req, DecisionBudget(10, 11, 12))
        games[obs.game_id] = FakeGameSession(items=[make_window(obs, received_at=arrived),
            GameFinished(obs.game_id, (0, 0, 0, 0), obs.snapshot_seq + 1)])
    task = asyncio.create_task(assembled.run())
    try:
        await wait_for_condition(lambda: all(len(game.submitted) == 1 for game in games.values()))
        session.grant_updates()
        terminal = await task
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert terminal.reason.value == "tournament_finished"
    assert session.register_calls == 0 and session.ready_calls == []
    for game_id, game in games.items():
        assert [a.action_key for a in game.submitted] == [expected[game_id].candidates[0].action_key]
    manifest = json.loads((assembled.sink.run_dir / "manifest.json").read_text())["payload"]
    assert manifest["value_analysis_limits"] is None
    assert manifest["value_analysis_disabled_reason"] == "uncalibrated_rule_config"
    assert manifest["base_score"] == rules.base_score
    assert manifest["you_cai_bi_kao"] == rules.you_cai_bi_kao
    for record in records(assembled):
        if record["kind"] == "decision_input":
            assert all(c.get("value_facts") is None for c in record["payload"]["request"]["rules"]["legal_candidates"])
        if record["kind"] == "decision_planned":
            wanted = expected[record["context"]["game_id"]]
            assert [c["action_key"] for c in record["payload"]["candidates"]] == [c.action_key for c in wanted.candidates]


class WorkRules(FakeRules):
    """按确定工作耗时推进时钟，观察紧急路径与增强的调用次序。"""

    def __init__(self, clock, *, cost=0.0, fail=False):
        super().__init__(candidates=(DISCARD_3W, PASS), emergency=PASS)
        self.clock, self.cost, self.fail = clock, cost, fail
        self.events = []

    def emergency_action(self, observation):
        self.events.append("emergency")
        return super().emergency_action(observation)

    def analyze(self, observation, *, value_limits=None):
        self.events.append(value_limits)
        self.clock.advance(self.cost)
        if self.fail:
            raise RuntimeError("受控分析失败")
        return super().analyze(observation)


async def run_window(clock, rules, *, arrived=100.0, handler=None):
    sink, policy = InMemoryAuditSink(), FakePolicy()
    window = make_window(make_observation(), received_at=arrived, timeout=1.0)
    game = FakeGameSession(submit_handler=handler)
    services = RuntimeServices(rules, policy, AuditTrail(
        sink, run_id="run-test", tournament_id="t1", participant_id="p1", clock=clock,
    ), clock, SequencedIds(), BudgetPolicy(), value_limits=LIMITS)
    result = await run_action_window(session=game, window=window, services=services,
                                     competition=make_competition(), stage_attempt_id="attempt-1")
    return result, game, sink, policy


async def test_value_analysis_is_after_emergency_and_inside_original_budget():
    clock = ManualClock()
    rules = WorkRules(clock, cost=.2)
    result, game, sink, policy = await run_window(clock, rules)
    assert result.outcome_kind == "accepted" and len(game.submitted) == 1
    assert rules.events == ["emergency", LIMITS]
    assert policy.budgets[0].latest_send_at_monotonic == pytest.approx(100.90)
    entry = next(r.payload for r in sink.records if r.kind.value == "decision_input")
    assert entry["rule_elapsed_ms"] == pytest.approx(200)


async def test_retry_does_not_renew_value_budget_and_reject_history_survives():
    clock = ManualClock()
    rules = WorkRules(clock)
    window = make_window(make_observation(), timeout=1.0)
    calls = []
    def handler(attempt):
        calls.append(attempt)
        if len(calls) == 1:
            clock.advance(.55)
            return SubmitRejectedRetryable("CONFLICT", attempt.action_key, make_refreshed_window(window, seq=11))
        return SubmitAccepted("200", 12)
    result, game, sink, policy = await run_window(clock, rules, handler=handler)
    assert result.outcome_kind == "accepted" and len(game.submitted) == 2
    assert rules.events == ["emergency", LIMITS, "emergency", None]
    assert policy.budgets[0] is policy.budgets[1]
    assert policy.calls[1].rejected_attempts[0].action_key == "discard:3w"


async def test_value_failure_keeps_independent_emergency_action():
    clock = ManualClock()
    rules = WorkRules(clock, fail=True)
    result, game, *_ = await run_window(clock, rules)
    assert result.outcome_kind == "accepted"
    assert rules.events == ["emergency", LIMITS]
    assert [attempt.action_key for attempt in game.submitted] == ["pass"]


async def test_value_work_cannot_submit_after_the_original_send_deadline():
    clock = ManualClock()
    result, game, *_ = await run_window(clock, WorkRules(clock, cost=.9))
    assert not game.submitted
    assert result.outcome_kind == "deadline"
