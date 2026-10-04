"""自由赛组合根的单次真实评分闭环；官方端口均为脚本，不发 HTTP。"""

import asyncio
from dataclasses import asdict, replace
import hashlib
import json
import time

import pytest

import hangma_bot.bootstrap as assembly
from fakes import FakeGameSession, FakeTournamentSession, make_bootstrap, make_config, make_snapshot, make_window
from hangma_bot.application.audit_codec import decision_request_from_json
from hangma_bot.application.auto_match_runtime import AutoMatchSettings
from hangma_bot.application.contracts import GameFinished, ParticipantTerminalReason, TournamentStatus
from hangma_bot.application.deadline import SystemClock
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.config import RuleConfig
from tests.unit.policy.support import make_observation


@pytest.mark.asyncio
async def test_free_bootstrap_real_worker_rule_audit_submission_and_normal_close(tmp_path):
    """仅一个动作窗口真实评分；预热先于模拟匹配，审计读回和资源归零后收据。"""
    package = assembly._load_vip_free_manifest()
    config = assembly.runtime_config_from_mapping(dict(
        mode="auto_match", token_kind="official", token="public-fake-only",
        base_url="https://platform.invalid", expected_tournament_id="",
        known_guide_version=package["known_guide_version"], audit_root=str(tmp_path / "audit"),
        strategy=assembly.VIP_S02_FREE_STRATEGY, sse_enabled=True,
        expected_policy_release_id=package["release_package_id"],
    ))
    finished = asyncio.Event()
    lifecycle = []
    received = []
    config_rules = RuleConfig(assembly.DEFAULT_RULESET_VERSION, 1, False)
    observation = make_observation(
        my_hand=tuple(Tile(code) for code in ("1w", "2w", "3w", "1t", "2t", "3t",
            "1b", "2b", "3b", "7w", "8w", "东", "东")),
        drawn_tile=Tile("南"), hand_counts=(14, 13, 13, 13), chain_piao=0, gang_draw=False,
    )

    class PublicGame(FakeGameSession):
        """预热完成后才产生新窗口，以真实到达时刻建立原预算。"""
        def __init__(self):
            super().__init__()
            self.items_delivered = 0

        async def next_item(self):
            self.items_delivered += 1
            if self.items_delivered == 1:
                now = SystemClock().now()
                received.append(now)
                lifecycle.append("window")
                return make_window(observation, received_at=now, timeout=3.0)
            if self.items_delivered == 2:
                lifecycle.append("game-finished")
                finished.set()
                return GameFinished("g1", (0, 0, 0, 0), 20)
            raise AssertionError("脚本仅有一个动作窗口和一个终局")

    game = PublicGame()
    snapshot = make_snapshot(TournamentStatus.RUNNING, my_games=("g1",), active_games=("g1",))
    bootstrap = make_bootstrap(snapshot, config=replace(make_config(max_games=1, rounds=1),
        rules=config_rules), guide_version=package["known_guide_version"])

    class PublicSession(FakeTournamentSession):
        """模拟 match 的公开会话，复现真实总会话的场次资源关闭职责。"""
        async def initialize(self, target):
            assert unit.compute.snapshot()["ready"] == package["params"]["compute_settings"]["workers"]
            lifecycle.append("match")
            return await super().initialize(target)

        async def next_update(self):
            if "room-finished" in lifecycle:
                await asyncio.Event().wait()  # 终态后无新通知，等待监督器关闭会话
            await finished.wait()
            lifecycle.append("room-finished")
            return make_snapshot(TournamentStatus.FINISHED, my_games=("g1",), active_games=())

        async def aclose(self):
            lifecycle.append("http-close")
            for opened in self.opened_games.values():
                await opened.aclose("public_session_closed")
            await super().aclose()

    session = PublicSession(bootstrap=bootstrap, game_factory=lambda game_id: game)
    unit = assembly.build_auto_match_runtime(config, AutoMatchSettings("test-only"),
        session_factory=lambda: session)
    assert asdict(unit.compute.factory) == {"expected_id": package["release_package_id"],
        "strategy": assembly.VIP_S02_FREE_STRATEGY}
    assert hashlib.sha256(assembly.VIP_S02_SOURCE.encode()).hexdigest() == assembly.VIP_S02_SOURCE_SHA256
    started = time.monotonic()
    terminal = await asyncio.wait_for(unit.run(), timeout=15)
    elapsed = time.monotonic() - started
    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    assert session.closed and game.closed
    assert session.register_calls == 0 and session.ready_calls == []
    assert lifecycle == ["match", "window", "game-finished", "room-finished", "http-close"]
    assert len(game.submitted) == 1
    resources = unit.compute.snapshot()
    assert resources["completed"] == resources["submitted"] == resources["dispatched"] == 1
    assert resources["process_starts"] == package["params"]["compute_settings"]["workers"]
    assert resources["restarts"] == resources["faults"] == 0
    for field in ("owned", "pending", "active", "current", "ready", "live_processes",
                  "transport_inflight", "transport_threads_alive", "late_reap_inflight", "late_reap_threads_alive",
                  "bound_games", "releasing_games"):
        assert resources[field] == 0, field
    assert resources["closed"] is True
    assert not unit.audit_degraded

    records = [json.loads(line) for path in sorted(unit.sink.run_dir.rglob("*.jsonl"))
        for line in path.read_text().splitlines()]
    records.append(json.loads((unit.sink.run_dir / "manifest.json").read_text()))
    payloads = lambda kind: [record["payload"] for record in records if record["kind"] == kind]
    manifest, = payloads("run_manifest")
    decision, = payloads("decision_input")
    planned, = payloads("decision_planned")
    assert manifest["route_analysis_limits"] == package["params"]["route_limits"]
    assert manifest["value_analysis_limits"] is None
    assert manifest["policy_release"]["release_package_id"] == package["release_package_id"]
    request = decision_request_from_json(decision["request"])
    assert request.rules.ruleset_version == assembly.DEFAULT_RULESET_VERSION
    assert request.rules.route_frontier is not None and request.rules.conditional_roots is not None
    assert planned["returned_plan"] is not None and planned["degraded_reasons"] == []
    actual_candidates = planned["returned_plan"]["candidates"]
    assert {candidate["action_key"] for candidate in actual_candidates} == {
        candidate.action_key for candidate in request.rules.legal_candidates}
    assert all(candidate["score_trace"]["max_replacement_depth"] == 1 for candidate in actual_candidates)
    assert decision["budget_origin_monotonic"] == received[0]
    assert planned["policy_elapsed_ms"] < 3000
    assert payloads("game_finished") and payloads("participant_finished")
    assert all("public-fake-only" not in json.dumps(record, ensure_ascii=False) for record in records)
    receipt = dict(
        schema_version=1, release_package_id=package["release_package_id"],
        factory_public_fields=asdict(unit.compute.factory), actual_s02_choose_count=1,
        http_calls=0, terminal=terminal.reason.value, elapsed_seconds=elapsed,
        decision_input=decision, decision_planned=planned, run_manifest=manifest,
        submissions=[dict(action_key=attempt.action_key) for attempt in game.submitted],
        compute=resources, lifecycle=lifecycle,
        audit_summary=asdict(unit.last_audit_summary), audit_dir=str(unit.sink.run_dir),
    )
    (tmp_path / "PUBLIC-E2E-RECEIPT.json").write_text(json.dumps(receipt, ensure_ascii=False,
        indent=2, allow_nan=False) + "\n")
