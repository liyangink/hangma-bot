"""E2八包的公开基础接线；真实工厂/全根参考，假身份会话，零联网。"""

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

import hangma_bot.bootstrap as assembly
from fakes import FakePolicy, FakeTournamentSession, make_bootstrap, make_config, make_snapshot
from hangma_bot.application.contracts import ParticipantTerminalReason, RuntimeMode, TournamentStatus
from hangma_bot.bootstrap import TokenKind
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.policy.route_vip_heuristic import RouteVipHeuristicPolicy
from tests.unit.policy.support import make_budget, make_observation, make_request
from scripts.run_participant import load_config as load_participant
from scripts.run_auto_match import load_config as load_free
from scripts.run_test_room import load_room_config, child_config_mapping, TOKEN_ENV_VAR

ROOT = Path(assembly.__file__).resolve().parents[2]
RULES = RuleConfig(assembly.DEFAULT_RULESET_VERSION, 1, False)
ROWS = tuple((algorithm, strategy, mode, manifest, template) for algorithm, values in (
    ("s03", [(assembly.VIP_S03_TESTROOM_STRATEGY, "test_room", "prebuilt/vip-s03-bounded-d1-testroom-v3/manifest.json", "configs/vip-s03-bounded-d1-v3.test-room.example.json"),
             (assembly.VIP_S03_FREE_STRATEGY, "auto_match", "prebuilt/vip-s03-bounded-d1-free-v3/manifest.json", "configs/vip-s03-bounded-d1-v3.free-match.example.json"),
             (assembly.VIP_S03_TEST_TOURNAMENT_STRATEGY, "test_tournament", "prebuilt/vip-s03-bounded-d1-test-tournament-v3/manifest.json", "configs/vip-s03-bounded-d1-v3.test-tournament.example.json"),
             (assembly.VIP_S03_OFFICIAL_TOURNAMENT_STRATEGY, "official_tournament", "prebuilt/vip-s03-bounded-d1-official-tournament-v3/manifest.json", "configs/vip-s03-bounded-d1-v3.official-tournament.example.json")]),
    ("s02", [(assembly.VIP_S02_TESTROOM_SUCCESSOR_STRATEGY, "test_room", assembly.VIP_S02_TESTROOM_SUCCESSOR_MANIFEST, "configs/vip-s02-bounded-d1-v12.test-room.example.json"),
             (assembly.VIP_S02_FREE_SUCCESSOR_STRATEGY, "auto_match", assembly.VIP_S02_FREE_SUCCESSOR_MANIFEST, "configs/vip-s02-bounded-d1-v10.free-match.example.json"),
             (assembly.VIP_S02_TEST_TOURNAMENT_STRATEGY, "test_tournament", assembly.VIP_S02_TEST_TOURNAMENT_MANIFEST, "configs/vip-s02-bounded-d1-v4.test-tournament.example.json"),
             (assembly.VIP_S02_OFFICIAL_TOURNAMENT_STRATEGY, "official_tournament", assembly.VIP_S02_OFFICIAL_TOURNAMENT_MANIFEST, "configs/vip-s02-bounded-d1-v4.official-tournament.example.json")]),
) for strategy, mode, manifest, template in values)


def parsed(row, tmp_path):
    """经真实启动脚本解析；只使用测试显式提供的假环境值。"""
    algorithm, strategy, mode, manifest, template = row
    path = ROOT / template
    data = json.loads(path.read_text())
    settings = None
    if mode == "test_room":
        room = load_room_config(path, environ={item["token_env"]: "public-fake-only" for item in data["identities"]})
        for identity in room.identities:
            child = child_config_mapping(room, identity)
            assert "token" not in child and child["expected_policy_release_id"] == data["expected_policy_release_id"]
            config = assembly.runtime_config_from_mapping(child, environ={TOKEN_ENV_VAR: "public-fake-only"})
            assert config.strategy == strategy and config.sse_enabled
    elif mode == "auto_match":
        config, settings = load_free(path, environ={data["token_env"]: "public-fake-only"})
    else:
        config = load_participant(path, environ={data["token_env"]: "public-fake-only"})
    return replace(config, audit_root=tmp_path), settings


@pytest.mark.parametrize("row", ROWS)
@pytest.mark.parametrize("mature_hu", [False, True])
async def test_eight_public_factories_preserve_complete_functional_reference(row, mature_hu, tmp_path):
    """各自真实工厂载入原编译公式，全合法根的分数/分解/trace与原Python完全相同。"""
    config, settings = parsed(row, tmp_path)
    unit = (assembly.build_runtime(config, session_factory=lambda: object()) if settings is None
        else assembly.build_auto_match_runtime(config, settings, session_factory=lambda: object()))
    try:
        package = json.loads((ROOT / row[3]).read_text())
        assert package["allowed_modes"] == [row[2]] and len(package["source_manifest"]) == 183
        assert unit.compute.factory.expected_id == package["release_package_id"]
        prepared = unit.compute.factory()
        hand = ("1w", "2w", "3w", "1t", "2t", "3t", "1b", "2b", "3b", "东", "东", "南", "南") if mature_hu else (
            "1w", "2w", "3w", "1t", "2t", "3t", "1b", "2b", "3b", "7w", "8w", "东", "东")
        visible = make_observation(my_hand=tuple(Tile(code) for code in hand), drawn_tile=Tile("南"),
            hand_counts=(14, 13, 13, 13), chain_piao=0, gang_draw=False)
        rules = HangmaRules(RULES).analyze(visible, route_limits=assembly.VIP_S02_ROUTE_LIMITS)
        request = make_request(visible, rules)
        source = assembly.VIP_S03_SOURCE if row[0] == "s03" else assembly.VIP_S02_SOURCE
        original = RouteVipHeuristicPolicy(RULES, source=source, max_operations=4_800_000,
            projection_limits=assembly.VIP_S02_PROJECTION_LIMITS)
        actual = await prepared.policy.choose(request, make_budget())
        expected = await original.choose(request, make_budget())
        assert actual == expected
        assert len(actual.candidates) == len(rules.legal_candidates)
        assert package["source_sha256"] == hashlib.sha256(source.encode()).hexdigest()
        if mature_hu:
            assert "hu" in [item.action_key for item in rules.legal_candidates]
        assert unit.compute.snapshot()["process_starts"] == 0
    finally:
        await unit.compute.close()
        await unit.sink.aclose(timeout_seconds=1)


@pytest.mark.parametrize("row", ROWS)
def test_each_scope_rejects_cross_mode(row, tmp_path):
    config, _ = parsed(row, tmp_path)
    mode = RuntimeMode.OFFICIAL_TOURNAMENT if row[2] == "auto_match" else RuntimeMode.AUTO_MATCH
    with pytest.raises(ValueError, match="模式"):
        replace(config, mode=mode, token_kind=TokenKind.OFFICIAL, expected_tournament_id="public-target")


@pytest.mark.parametrize("algorithm", ["s03", "s02"])
@pytest.mark.parametrize("change", [{"expected_policy_release_id": None}, {"expected_policy_release_id": "0" * 64},
    {"known_guide_version": 34}, {"sse_enabled": False}])
def test_required_package_guide_and_sse(algorithm, change, tmp_path):
    row = next(item for item in ROWS if item[0] == algorithm and item[2] == "test_tournament")
    config, _ = parsed(row, tmp_path)
    with pytest.raises(ValueError):
        replace(config, **change)


@pytest.mark.parametrize("algorithm,mode,version", [(alg, mode, version) for alg, versions in (
    ("s03", (2, 2, 2, 2)), ("s02", (11, 9, 3, 3))) for mode, version in zip(
        ("test_room", "auto_match", "test_tournament", "official_tournament"), versions)])
def test_old_eight_keep_source_drift_refusal(algorithm, mode, version, tmp_path):
    suffix = {"test_room": "testroom", "auto_match": "free", "test_tournament": "test_tournament", "official_tournament": "official_tournament"}[mode]
    directory = suffix.replace("_", "-")
    path = ROOT / f"prebuilt/vip-{algorithm}-bounded-d1-{directory}-v{version}/manifest.json"
    package = json.loads(path.read_text())
    with pytest.raises(RuntimeError, match="源码|漂移"):
        assembly.runtime_config_from_mapping(dict(mode=mode, token_kind="official" if mode in ("auto_match", "official_tournament") else "test",
            token="public-fake-only", base_url="https://platform.invalid", expected_tournament_id="public-target",
            known_guide_version=35, audit_root=str(tmp_path), strategy=package["strategy"], sse_enabled=True,
            expected_policy_release_id=package["release_package_id"]))


@pytest.mark.parametrize("actual_rules", [replace(RULES, base_score=2), replace(RULES, you_cai_bi_kao=True),
    replace(RULES, ruleset_version="unsupported")])
async def test_actual_rule_scope_refuses_before_register_with_public_fake_ports(actual_rules, tmp_path):
    row = next(item for item in ROWS if item[0] == "s03" and item[2] == "test_tournament")
    config, _ = parsed(row, tmp_path)
    config = replace(config, expected_tournament_id="t1")
    session = FakeTournamentSession(bootstrap=make_bootstrap(make_snapshot(TournamentStatus.REGISTERING),
        config=replace(make_config(max_games=2), rules=actual_rules), guide_version=35))
    unit = assembly.build_runtime(config, session_factory=lambda: session, policy_factory=FakePolicy)
    terminal = await unit.run()
    assert terminal.reason is ParticipantTerminalReason.FATAL_PROTOCOL_ERROR
    assert session.register_calls == 0 and session.ready_calls == [] and session.game_opens == []
    assert session.closed
