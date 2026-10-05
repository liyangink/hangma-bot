"""S02赛事候选的公开组合根验收；真实计算、脚本会话，不连接官方平台。"""

import asyncio
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path

import pytest

import hangma_bot.bootstrap as assembly
from fakes import FakeGameSession, FakeTournamentSession, make_bootstrap, make_config, make_snapshot, make_window
from hangma_bot.application.audit_codec import decision_request_from_json
from hangma_bot.application.contracts import (GameFinished, ParticipantTerminalReason, TournamentStatus,
    SubmitAccepted, SubmitAmbiguous, SubmitRejectedRetryable)
from hangma_bot.application.deadline import SystemClock
from hangma_bot.application.auto_match_runtime import AutoMatchSettings
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.actions import Tile, WindowPhase
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import PublicDiscard
from hangma_bot.policy.route_vip_heuristic import RouteVipHeuristicPolicy
from tests.unit.policy.support import make_budget, make_observation, make_request

ROOT = Path(assembly.__file__).resolve().parents[2]
SCOPES = (
    (assembly.VIP_S02_TESTROOM_SUCCESSOR_STRATEGY, assembly.VIP_S02_TESTROOM_SUCCESSOR_MANIFEST, "test_room", "test"),
    (assembly.VIP_S02_FREE_SUCCESSOR_STRATEGY, assembly.VIP_S02_FREE_SUCCESSOR_MANIFEST, "auto_match", "official"),
    (assembly.VIP_S02_TEST_TOURNAMENT_STRATEGY, assembly.VIP_S02_TEST_TOURNAMENT_MANIFEST, "test_tournament", "test"),
    (assembly.VIP_S02_OFFICIAL_TOURNAMENT_STRATEGY, assembly.VIP_S02_OFFICIAL_TOURNAMENT_MANIFEST, "official_tournament", "official"),
)
TOURNAMENTS = SCOPES[2:]
RULES = RuleConfig(assembly.DEFAULT_RULESET_VERSION, 1, False)


def package(scope):
    """读取公开冻结清单；任何接线校验都经 RuntimeConfig 及 build_runtime。"""
    return json.loads((ROOT / scope[1]).read_text())


def configuration(tmp_path, scope, **changes):
    """构造无真实凭证的配置；mode/Token类别/包ID三者独立绑定。"""
    frozen = package(scope)
    values = dict(mode=scope[2], token_kind=scope[3], token="public-fake-only",
        base_url="https://platform.invalid", expected_tournament_id="t1",
        known_guide_version=frozen["known_guide_version"], audit_root=str(tmp_path),
        strategy=scope[0], sse_enabled=True, discard_pacing_enabled=False,
        expected_policy_release_id=frozen["release_package_id"])
    values.update(changes)
    return assembly.runtime_config_from_mapping(values)


def observation(game_id="g1"):
    """合法的公开摸牌观察；四座手牌张数与积分均按座位0—3。"""
    return make_observation(game_id=game_id,
        my_hand=tuple(Tile(code) for code in ("1w", "2w", "3w", "1t", "2t", "3t",
            "1b", "2b", "3b", "7w", "8w", "东", "东")),
        drawn_tile=Tile("南"), hand_counts=(14, 13, 13, 13), chain_piao=0, gang_draw=False)


def records(unit):
    """关闭后读回公开审计文件，不依赖监督器或计算服务的私有状态。"""
    rows = [json.loads(line) for path in sorted(unit.sink.run_dir.rglob("*.jsonl"))
        for line in path.read_text().splitlines()]
    rows.append(json.loads((unit.sink.run_dir / "manifest.json").read_text()))
    return rows


async def until(condition):
    """只为真实spawn/I/O让出短时间；总等待有限，不模拟动作期限。"""
    async with asyncio.timeout(15):
        while not condition():
            await asyncio.sleep(0.001)


def assert_closed(unit):
    """公开资源诊断必须归零，真实收据不能把关闭等待等同于回收成功。"""
    state = unit.compute.snapshot()
    assert state["closed"] is True
    for key in ("owned", "pending", "active", "current", "ready", "live_processes",
        "transport_inflight", "transport_threads_alive", "late_reap_inflight",
        "late_reap_threads_alive", "bound_games", "releasing_games"):
        assert state[key] == 0, key


@pytest.mark.parametrize("scope", SCOPES)
def test_four_scopes_bind_same_original_and_exact_config(tmp_path, scope):
    frozen = package(scope)
    configuration(tmp_path, scope)
    all_packages = [package(item) for item in SCOPES]
    assert len({value["release_package_id"] for value in all_packages}) == 4
    for field in ("source_manifest", "source_sha256", "params", "compiled_runtime", "hand_math"):
        assert all(value[field] == frozen[field] for value in all_packages)
    assert frozen["source_sha256"] == hashlib.sha256(assembly.VIP_S02_SOURCE.encode()).hexdigest()
    assert frozen["allowed_modes"] == [scope[2]]
    assert frozen["strength_admission"] is frozen["production_default"] is frozen["llm_online"] is False
    assert frozen["params"]["compute_settings"] == asdict(assembly.VIP_S02_COMPUTE_SETTINGS)


@pytest.mark.parametrize("scope", SCOPES)
@pytest.mark.parametrize("mode,kind", [("test_room", "test"), ("auto_match", "official"),
    ("test_tournament", "test"), ("official_tournament", "official")])
def test_scope_cannot_be_expanded_by_configuration(tmp_path, scope, mode, kind):
    if mode == scope[2]:
        configuration(tmp_path, scope, mode=mode, token_kind=kind)
    else:
        with pytest.raises(ValueError, match="各自绑定的模式"):
            configuration(tmp_path, scope, mode=mode, token_kind=kind)


@pytest.mark.parametrize("scope", TOURNAMENTS)
@pytest.mark.parametrize("changes", [{"expected_policy_release_id": None},
    {"expected_policy_release_id": "0" * 64}, {"sse_enabled": False},
    {"known_guide_version": 34}, {"expected_tournament_id": ""}])
def test_required_identity_guide_and_sse_rejected(tmp_path, scope, changes):
    with pytest.raises(ValueError):
        configuration(tmp_path, scope, **changes)


@pytest.mark.parametrize("strategy,manifest,mode,kind", [
    (assembly.VIP_S02_TESTROOM_STRATEGY, assembly.VIP_S02_TESTROOM_MANIFEST, "test_room", "test"),
    (assembly.VIP_S02_FREE_STRATEGY, assembly.VIP_S02_FREE_MANIFEST, "auto_match", "official")])
def test_old_packages_keep_source_drift_rejection(tmp_path, strategy, manifest, mode, kind):
    with pytest.raises(RuntimeError, match="完整运行源码摘要漂移"):
        configuration(tmp_path, (strategy, manifest, mode, kind))


def test_old_r18_still_rejects_current_rule_source_before_session_creation(tmp_path):
    """新增S02模式不能绕过旧R18的规则/依赖摘要拒绝。"""
    config = configuration(tmp_path, TOURNAMENTS[0],
        strategy=assembly.R18_INTEGRATED_POSITIVE_V2_RELEASE_STRATEGY,
        expected_policy_release_id=assembly.R18_V2_RULES_20260929_RELEASE_PACKAGE_ID)
    calls = []
    with pytest.raises(RuntimeError, match="摘要漂移"):
        assembly.build_runtime(config, session_factory=lambda: calls.append("session"))
    assert calls == []


def test_public_room_launcher_transmits_each_successor_identity(tmp_path):
    """四身份公开解析/派生接口传递后继包；不读取真实凭证、不启动子进程。"""
    from scripts.run_test_room import load_room_config, child_config_mapping, TOKEN_ENV_VAR
    path = ROOT / "configs/vip-s02-bounded-d1-v9.test-room.example.json"
    names = ("qinglong", "baihu", "zhuque", "xuanwu")
    room = load_room_config(path, environ={"HM_ROOM_TOKEN_" + name.upper(): "public-fake-only" for name in names})
    for identity in room.identities:
        child = child_config_mapping(room, identity)
        assert "token" not in child
        child["audit_root"] = str(tmp_path / identity.slot)
        config = assembly.runtime_config_from_mapping(child, environ={TOKEN_ENV_VAR: "public-fake-only"})
        assert config.strategy == SCOPES[0][0]
        assert config.expected_policy_release_id == package(SCOPES[0])["release_package_id"]


@pytest.mark.parametrize("fault", ["missing_id", "wrong_identity_id", "free_scope"])
def test_room_successor_launcher_rejects_wrong_binding_before_spawn(tmp_path, fault):
    from scripts.run_test_room import load_room_config
    payload = json.loads((ROOT / "configs/vip-s02-bounded-d1-v9.test-room.example.json").read_text())
    if fault == "missing_id":
        payload.pop("expected_policy_release_id")
        for identity in payload["identities"]:
            identity.pop("expected_policy_release_id")
    elif fault == "wrong_identity_id":
        payload["identities"][0]["expected_policy_release_id"] = "0" * 64
    else:
        payload["identities"][0]["strategy"] = SCOPES[1][0]
    path = tmp_path / "public-room.json"
    path.write_text(json.dumps(payload))
    environ = {identity["token_env"]: "public-fake-only" for identity in payload["identities"]}
    with pytest.raises(ValueError):
        load_room_config(path, environ=environ)


@pytest.mark.parametrize("scope", SCOPES)
async def test_public_factory_scores_equal_original_without_token(tmp_path, scope):
    config = configuration(tmp_path, scope)
    unit = (assembly.build_auto_match_runtime(config, AutoMatchSettings(), session_factory=lambda: object())
        if scope[2] == "auto_match" else assembly.build_runtime(config, session_factory=lambda: object()))
    frozen = package(scope)
    assert asdict(unit.compute.factory) == {"expected_id": frozen["release_package_id"], "strategy": scope[0]}
    actual_policy = unit.compute.factory()
    visible = observation()
    rules = HangmaRules(RULES).analyze(visible, route_limits=assembly.VIP_S02_ROUTE_LIMITS)
    request = make_request(visible, rules)
    original = RouteVipHeuristicPolicy(RULES, source=assembly.VIP_S02_SOURCE,
        max_operations=4_800_000, projection_limits=assembly.VIP_S02_PROJECTION_LIMITS)
    actual = await actual_policy.policy.choose(request, make_budget())
    expected = await original.choose(request, make_budget())
    assert actual == expected
    assert len(actual.candidates) == len(rules.legal_candidates)
    assert rules.emergency_candidate.action in [item.action for item in actual.candidates]
    await unit.compute.close()
    await unit.sink.aclose(timeout_seconds=1)
    assert_closed(unit)


@pytest.mark.parametrize("scope", TOURNAMENTS)
async def test_real_tournament_lifecycle_rematch_backup_final_extra_game(tmp_path, scope):
    """真实预热和评分穿过三阶段、空档、候补确认、作废重赛及决赛新场次。"""
    started = asyncio.Event()

    class Game(FakeGameSession):
        def __init__(self, game_id):
            super().__init__()
            self.game_id, self.delivered = game_id, 0
            self.done = asyncio.Event()

        async def next_item(self):
            self.delivered += 1
            if self.game_id == "g2":
                await asyncio.Future()  # 在行动前被权威中断，旧窗口不能续用
            if self.delivered == 1:
                return make_window(observation(self.game_id), received_at=SystemClock().now(), timeout=3.0)
            if self.delivered == 2:
                self.done.set()
                return GameFinished(self.game_id, (0, 0, 0, 0), 20)
            await asyncio.Future()

    class Session(FakeTournamentSession):
        async def initialize(self, target):
            assert unit.compute.snapshot()["ready"] == 10
            started.set()
            return await super().initialize(target)

        async def aclose(self):
            for game in self.opened_games.values():
                await game.aclose("public_session_closed")
            await super().aclose()

    def snap(status, stage, revision, *, games=(), role="qualify", total=3, qualified=None, qualify_role=None, crashed=False):
        return replace(make_snapshot(status, stage_no=stage, revision=revision,
            qualified=qualified, crashed=crashed, active_games=games, my_games=games),
            stage_role=role, stage_total=total, qualify_role=qualify_role)

    updates = [
        snap(TournamentStatus.RUNNING, 1, 2, games=("g1",)),
        snap(TournamentStatus.STAGE_DONE, 1, 3),
        snap(TournamentStatus.STAGE_OPEN, 2, 4, total=3, qualified=True, qualify_role="backup"),
        snap(TournamentStatus.RUNNING, 2, 5, games=("g2",)),
        snap(TournamentStatus.RUNNING, 2, 6, crashed=True),
        snap(TournamentStatus.STAGE_OPEN, 2, 7, total=2, qualified=True, qualify_role="backup"),
        snap(TournamentStatus.RUNNING, 2, 8, games=("g3",), total=2),
        snap(TournamentStatus.STAGE_DONE, 2, 9, total=2),
        snap(TournamentStatus.STAGE_OPEN, 3, 10, role="final", total=3, qualified=True, qualify_role="finalist"),
        snap(TournamentStatus.RUNNING, 3, 11, games=("g4",), role="final"),
        snap(TournamentStatus.RUNNING, 3, 12, role="final"),
        snap(TournamentStatus.RUNNING, 3, 13, games=("g5",), role="final"),
        snap(TournamentStatus.FINISHED, 3, 14, role="final"),
    ]
    session = Session(bootstrap=make_bootstrap(make_snapshot(TournamentStatus.REGISTERING),
        config=replace(make_config(max_games=2), rules=RULES), guide_version=35),
        updates=updates, game_factory=Game)
    unit = assembly.build_runtime(configuration(tmp_path, scope), session_factory=lambda: session)
    task = asyncio.create_task(unit.run())
    try:
        await asyncio.wait_for(started.wait(), 15)
        await until(lambda: len(session.ready_calls) == 1)
        session.grant_updates(1)
        await until(lambda: "g1" in session.opened_games and session.opened_games["g1"].done.is_set())
        session.grant_updates(1)  # stage_done 空档必须持续等待
        await until(lambda: session.next_update_calls >= 3)
        assert not task.done()
        session.grant_updates(1)
        await until(lambda: len(session.ready_calls) == 2)
        session.grant_updates(1)
        await until(lambda: "g2" in session.opened_games)
        session.grant_updates(1)
        await until(lambda: session.opened_games["g2"].closed)
        session.grant_updates(1)
        await until(lambda: len(session.ready_calls) == 3)
        session.grant_updates(1)
        await until(lambda: "g3" in session.opened_games and session.opened_games["g3"].done.is_set())
        session.grant_updates(2)
        await until(lambda: len(session.ready_calls) == 4)
        session.grant_updates(1)
        await until(lambda: "g4" in session.opened_games and session.opened_games["g4"].done.is_set())
        session.grant_updates(1)  # 决赛 active_games 为空，仍不能退出
        await until(lambda: session.next_update_calls >= 12)
        assert not task.done()
        session.grant_updates(1)
        await until(lambda: "g5" in session.opened_games and session.opened_games["g5"].done.is_set())
        session.grant_updates(1)
        terminal = await asyncio.wait_for(task, 15)
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    assert session.register_calls == 1
    assert [(item.stage_no, item.observed_revision) for item in session.ready_calls] == [(None, 1), (2, 4), (2, 7), (3, 10)]
    assert session.game_opens == ["g1", "g2", "g3", "g4", "g5"]
    assert session.opened_games["g2"].close_reasons[0] == "stage_crashed"
    rows = records(unit)
    events = [row["payload"] for row in rows if row["kind"] == "lifecycle_changed"]
    attempts = [row["stage_attempt_id"] for row in events if row["event"] == "stage_attempt_started"]
    # 首次stage_no=None确认与随后出现的官方stage1分别记尝试；不把无场次
    # 的初次确认误算成执行桌赛。其后stage2中断前/重赛及stage3各有独立ID。
    assert len(attempts) == len(set(attempts)) == 5
    assert sum(row["event"] == "stage_attempt_voided" for row in events) == 1
    assert sum(row["kind"] == "decision_planned" for row in rows) == 4
    for row in rows:
        if row["kind"] == "decision_input":
            request = decision_request_from_json(row["payload"]["request"])
            assert request.rules.emergency_candidate is not None
    state = unit.compute.snapshot()
    assert state["completed"] == state["dispatched"] == 4
    assert state["faults"] == state["restarts"] == 0
    assert_closed(unit)
    assert not unit.audit_degraded


@pytest.mark.parametrize("rule_config,max_games,reason", [
    (replace(RULES, base_score=2), 10, "BaseScore=1"),
    (replace(RULES, you_cai_bi_kao=True), 10, "YouCaiBiKao=false"),
    (replace(RULES, ruleset_version="unsupported"), 10, "冻结规则版本"),
    (RULES, 11, "config.M")])
async def test_actual_rules_and_capacity_reject_before_register_ready(tmp_path, rule_config, max_games, reason):
    scope = TOURNAMENTS[0]
    session = FakeTournamentSession(bootstrap=make_bootstrap(make_snapshot(TournamentStatus.REGISTERING),
        config=replace(make_config(max_games=max_games), rules=rule_config), guide_version=35))
    unit = assembly.build_runtime(configuration(tmp_path, scope), session_factory=lambda: session)
    terminal = await asyncio.wait_for(unit.run(), 15)
    assert terminal.reason is ParticipantTerminalReason.FATAL_PROTOCOL_ERROR
    assert reason in terminal.detail
    assert session.register_calls == 0 and session.ready_calls == [] and session.game_opens == []
    assert session.closed
    assert_closed(unit)


@pytest.mark.parametrize("phase,timeout,target_tile", [(WindowPhase.DRAW, 3.0, None),
    (WindowPhase.RESPONSE_PENG, 1.0, "南"), (WindowPhase.RESPONSE_PENG, 1.0, "东")])
async def test_ten_simultaneous_games_use_exclusive_preheated_workers(tmp_path, phase, timeout, target_tile):
    """十个原3秒弃牌或1秒响应窗同刻就绪；允许显式预算跳过，合法提交必须及时。"""
    arrived, received, barrier, done = [], [], asyncio.Event(), set()

    class Game(FakeGameSession):
        def __init__(self, game_id):
            super().__init__()
            self.game_id, self.delivered = game_id, 0

        async def next_item(self):
            self.delivered += 1
            if self.delivered == 1:
                arrived.append(self.game_id)
                if len(arrived) == 10:
                    assert unit.compute.snapshot()["bound_games"] == 10
                    received.append(SystemClock().now())
                    barrier.set()
                await barrier.wait()
                visible = observation(self.game_id)
                if phase is WindowPhase.RESPONSE_PENG:
                    discard = PublicDiscard(1, Tile(target_tile), 10)
                    visible = replace(visible, phase="response_peng", drawn_tile=None,
                        responding_seats=(2, 3, 0), turn_seat=1, hand_counts=(13, 13, 13, 13),
                        discards=((), (discard.tile,), (), ()), last_discard=discard)
                return replace(make_window(visible, phase=phase, received_at=received[0], timeout=timeout),
                    expires_at_monotonic=received[0] + timeout, deadline_is_estimated=False)
            if self.delivered == 2:
                done.add(self.game_id)
                return GameFinished(self.game_id, (0, 0, 0, 0), 20)
            await asyncio.Future()

    games = tuple("g" + str(number) for number in range(10))
    session = FakeTournamentSession(bootstrap=make_bootstrap(
        make_snapshot(TournamentStatus.RUNNING, active_games=games, my_games=games),
        config=replace(make_config(max_games=10), rules=RULES), guide_version=35),
        updates=[make_snapshot(TournamentStatus.FINISHED)], game_factory=Game)
    unit = assembly.build_runtime(configuration(tmp_path, TOURNAMENTS[1]), session_factory=lambda: session)
    task = asyncio.create_task(unit.run())
    try:
        await until(lambda: len(done) == 10)
        session.grant_updates(1)
        terminal = await asyncio.wait_for(task, 15)
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    assert len(session.game_opens) == 10
    assert all(len(game.submitted) == 1 for game in session.opened_games.values())
    state = unit.compute.snapshot()
    rows = records(unit)
    plans = [row for row in rows if row["kind"] == "decision_planned"]
    complete = [row for row in plans if row["payload"]["returned_plan"] is not None]
    assert state["completed"] == state["dispatched"] == len(complete)
    assert 0 < len(complete) <= 10
    assert state["process_starts"] == 10
    assert state["faults"] == state["restarts"] == state["discarded"] == 0
    assert len(plans) == 10
    for row in rows:
        if row["kind"] == "submission_intent":
            assert row["monotonic_ns"] / 1_000_000_000 < received[0] + timeout - 0.1
    for row in plans:
        if row not in complete:
            assert row["payload"]["degraded_reasons"]
            assert any(candidate["is_emergency"] for candidate in row["payload"]["effective_candidates"])
    if phase is WindowPhase.RESPONSE_PENG and target_tile == "南":
        assert len(complete) == 10  # 这里只过的快速响应控制应全部按原1秒窗口评分
    assert_closed(unit)


@pytest.mark.parametrize("result_kind", ["retryable", "ambiguous"])
async def test_real_s02_rejection_keeps_original_budget_and_ambiguity_stops(tmp_path, result_kind):
    """真实S02对明确拒绝排除动作并重评；刷新报未来时间仍不延原截止，模糊零追加。"""
    finished = asyncio.Event()
    received = []

    class Game(FakeGameSession):
        def __init__(self):
            super().__init__(submit_handler=self.handle_submit)
            self.window = None
            self.delivered = 0

        def handle_submit(self, attempt):
            if len(self.submitted) == 1:
                if result_kind == "ambiguous":
                    return SubmitAmbiguous("public-recovery", "simulated-timeout")
                refreshed = replace(self.window, observation=replace(self.window.observation, snapshot_seq=11),
                    authoritative_seq=11, received_at_monotonic=self.window.received_at_monotonic + 1000,
                    timeout_seconds=1000)
                return SubmitRejectedRetryable("CONFLICT", attempt.action_key, refreshed)
            return SubmitAccepted("200", 12)

        async def next_item(self):
            self.delivered += 1
            if self.delivered == 1:
                received.append(SystemClock().now())
                self.window = replace(make_window(observation(), received_at=received[0], timeout=3.0),
                    expires_at_monotonic=received[0] + 3.0, deadline_is_estimated=False)
                return self.window
            finished.set()
            return GameFinished("g1", (0, 0, 0, 0), 20)

    game = Game()

    class Session(FakeTournamentSession):
        async def next_update(self):
            await finished.wait()
            return make_snapshot(TournamentStatus.FINISHED)

    session = Session(bootstrap=make_bootstrap(make_snapshot(TournamentStatus.RUNNING, active_games=("g1",), my_games=("g1",)),
        config=replace(make_config(max_games=1), rules=RULES), guide_version=35), game_factory=lambda game_id: game)
    unit = assembly.build_runtime(configuration(tmp_path, TOURNAMENTS[0]), session_factory=lambda: session)
    terminal = await asyncio.wait_for(unit.run(), 15)
    assert terminal.reason is ParticipantTerminalReason.TOURNAMENT_FINISHED
    rows = records(unit)
    inputs = [row["payload"] for row in rows if row["kind"] == "decision_input"]
    if result_kind == "retryable":
        assert len(game.submitted) == len(inputs) == 2
        assert game.submitted[0].action_key != game.submitted[1].action_key
        assert game.submitted[0].decision_id == game.submitted[1].decision_id
        assert inputs[0]["budget"] == inputs[1]["budget"]
        refreshed = decision_request_from_json(inputs[1]["request"])
        assert refreshed.rejected_attempts[0].action_key == game.submitted[0].action_key
        assert refreshed.observation.snapshot_seq == 11
    else:
        assert len(game.submitted) == len(inputs) == 1
    assert all(row["monotonic_ns"] / 1_000_000_000 < received[0] + 2.9
        for row in rows if row["kind"] == "submission_intent")
    assert_closed(unit)
