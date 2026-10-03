"""工程冻结包的漂移隔离、计算生命周期及真实动作链验收，不授算法强度。"""

import asyncio
from dataclasses import replace
import hashlib
import json
from types import SimpleNamespace

import pytest

import hangma_bot.bootstrap as assembly
from fakes import FakeGameSession, InMemoryAuditSink, SequencedIds, make_competition, make_window
from hangma_bot.application.audit import AuditTrail
from hangma_bot.application.audit_codec import decision_request_from_json
from hangma_bot.application.contracts import AuditKind
from hangma_bot.application.deadline import BudgetPolicy, SystemClock
from hangma_bot.application.decision_loop import RuntimeServices, run_action_window
from hangma_bot.kernel.actions import Tile
from hangma_bot.policy.interface import DecisionBudget
from tests.unit.policy.support import make_observation


def configuration(tmp_path, **changes):
    package = assembly._load_vip_testroom_manifest()
    values = dict(mode="test_room", token_kind="test", token="test-secret-not-a-real-token",
        base_url="https://platform.invalid", expected_tournament_id="t-local",
        known_guide_version=package["known_guide_version"], audit_root=str(tmp_path),
        strategy=assembly.VIP_S02_TESTROOM_STRATEGY, sse_enabled=True,
        discard_pacing_enabled=False, expected_policy_release_id=package["release_package_id"])
    values.update(changes)
    return assembly.runtime_config_from_mapping(values)


@pytest.mark.parametrize("mode,kind", (("test_tournament", "test"),
    ("official_tournament", "official"), ("auto_match", "official")))
def test_engineering_package_cannot_expand_to_other_network_modes(tmp_path, mode, kind):
    with pytest.raises(ValueError, match="仅允许测试房"):
        configuration(tmp_path, mode=mode, token_kind=kind)


@pytest.mark.parametrize("changes", ({"expected_policy_release_id": None},
    {"expected_policy_release_id": "0" * 64}, {"sse_enabled": False}))
def test_explicit_identity_and_sse_are_required(tmp_path, changes):
    with pytest.raises(ValueError):
        configuration(tmp_path, **changes)


def test_assembly_rechecks_drift_before_creating_resource_owners(tmp_path, monkeypatch):
    config = configuration(tmp_path)
    monkeypatch.setattr(assembly, "_vip_runtime_sources", lambda: {"changed": "0" * 64})
    created = []
    monkeypatch.setattr(assembly, "JsonlAuditSink", lambda *a, **k: created.append("sink"))
    with pytest.raises(RuntimeError, match="源码摘要漂移"):
        assembly.build_runtime(config, session_factory=lambda: created.append("session"))
    assert created == []


def test_params_do_not_accept_bool_as_integer(tmp_path, monkeypatch):
    original = assembly._load_vip_testroom_manifest()
    original["params"]["rule_config"]["base_score"] = True
    original["release_package_id"] = assembly._vip_package_id(original)
    path = tmp_path / "invalid-manifest.json"
    path.write_text(json.dumps(original))
    monkeypatch.setattr(assembly, "VIP_S02_TESTROOM_MANIFEST", str(path))
    with pytest.raises(RuntimeError, match="范围或参数"):
        assembly._load_vip_testroom_manifest()


def test_evidence_bytes_are_rechecked_even_for_rehashed_package(tmp_path, monkeypatch):
    original = assembly._load_vip_testroom_manifest()
    key = next(iter(original["evidence_sha256"]))
    original["evidence_sha256"][key] = "0" * 64
    original["release_package_id"] = assembly._vip_package_id(original)
    path = tmp_path / "invalid-manifest.json"
    path.write_text(json.dumps(original))
    monkeypatch.setattr(assembly, "VIP_S02_TESTROOM_MANIFEST", str(path))
    with pytest.raises(RuntimeError, match="证据摘要漂移"):
        assembly._load_vip_testroom_manifest()


@pytest.mark.parametrize("failure", ("start", "cancel-start", "runtime", None))
async def test_compute_lifecycle_warms_before_runtime_and_always_closes(failure):
    events = []

    class Compute:
        async def start(self):
            events.append("warm")
            if failure == "start":
                raise RuntimeError("injected startup failure")
            if failure == "cancel-start":
                raise asyncio.CancelledError()

        async def close(self):
            events.append("compute-close")

    class Runtime:
        async def run(self):
            events.append("runtime")
            try:
                if failure == "runtime":
                    raise RuntimeError("injected runtime failure")
                return "finished"
            finally:
                events.extend(("session-close", "audit-close"))

    class Session:
        async def aclose(self):
            events.append("session-close")

    class Sink:
        async def aclose(self, timeout_seconds):
            assert timeout_seconds > 0
            events.append("audit-close")

    unit = assembly.AssembledRuntime(SimpleNamespace(), "test", Sink(), Session(), Compute(), Runtime(), Compute())
    if failure:
        with pytest.raises(asyncio.CancelledError if failure == "cancel-start" else RuntimeError):
            await unit.run()
    else:
        assert await unit.run() == "finished"
    if failure in ("start", "cancel-start"):
        assert events == ["warm", "compute-close", "session-close", "audit-close"]
    else:
        assert events == ["warm", "runtime", "session-close", "audit-close", "compute-close"]


async def test_real_frozen_worker_and_actual_rule_audit_submission_chain(tmp_path):
    """从真实规则分析开始计时，通过真实spawn服务，最后由规则复核合法提交。"""
    config = configuration(tmp_path)
    clock = SystemClock()
    compute = assembly._build_vip_testroom_compute(config, clock)
    await compute.start()
    sink = InMemoryAuditSink()
    try:
        observation = make_observation(
            my_hand=tuple(Tile(c) for c in ("1w", "2w", "3w", "1t", "2t", "3t",
                "1b", "2b", "3b", "7w", "8w", "东", "东")), drawn_tile=Tile("南"),
            hand_counts=(14, 13, 13, 13), chain_piao=0, gang_draw=False)
        rules = assembly._vip_testroom_rules(assembly.RuleConfig(assembly.DEFAULT_RULESET_VERSION, 1, False))
        game = FakeGameSession()
        audit = AuditTrail(sink, run_id="local", tournament_id="t-local", participant_id="p-local", clock=clock)
        services = RuntimeServices(rules, compute, audit, clock, SequencedIds(), BudgetPolicy(),
            route_limits=assembly.VIP_S02_ROUTE_LIMITS)
        window = make_window(observation, received_at=clock.now(), timeout=3.0)
        result = await run_action_window(session=game, window=window, services=services,
            competition=make_competition(), stage_attempt_id="local-attempt")
        assert result.outcome_kind == "accepted" and len(game.submitted) == 1
        input_record = next(r for r in sink.records if r.kind is AuditKind.DECISION_INPUT)
        planned = next(r.payload for r in sink.records if r.kind is AuditKind.DECISION_PLANNED)
        rebuilt = decision_request_from_json(json.loads(json.dumps(input_record.payload["request"], allow_nan=False)))
        assert rebuilt.rules.route_frontier is not None
        assert rebuilt.rules.conditional_roots is not None
        assert planned["returned_plan"] is not None and planned["degraded_reasons"] == []
        actual_keys = {item["action_key"] for item in planned["returned_plan"]["candidates"]}
        assert actual_keys == {c.action_key for c in rebuilt.rules.legal_candidates}
        assert all(c["score_trace"]["max_replacement_depth"] == 1
                   for c in planned["returned_plan"]["candidates"])
        assert compute.snapshot()["completed"] == 1
        assert hashlib.sha256(assembly.VIP_S02_SOURCE.encode()).hexdigest() == assembly.VIP_S02_SOURCE_SHA256
    finally:
        await compute.close()
    assert compute.snapshot()["live_processes"] == 0
    assert compute.snapshot()["transport_threads_alive"] == 0
