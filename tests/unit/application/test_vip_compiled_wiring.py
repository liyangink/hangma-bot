"""编译策略接线的启动拒绝与全评分对账；不连接官方平台或修改真实冻结包。"""

import hashlib
import json
import shutil
from pathlib import Path

import pytest

import hangma_bot.bootstrap as assembly
from hangma_bot.application.auto_match_runtime import AutoMatchSettings
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.actions import Tile, WindowPhase
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.policy import action_value_executor
from hangma_bot.policy.route_vip_heuristic import RouteVipHeuristicPolicy
from tests.unit.policy.support import make_budget, make_observation, make_request


@pytest.fixture
def release_root(tmp_path, monkeypatch):
    """用真实源码和编译原件生成临时包，不覆盖任何线上或待发布包。"""
    root = tmp_path / "package"
    root.mkdir()
    real_root = Path(assembly.__file__).resolve().parents[2]
    (root / "src").symlink_to(real_root / "src", target_is_directory=True)
    (root / "scripts").symlink_to(real_root / "scripts", target_is_directory=True)
    shutil.copytree(real_root / assembly.VIP_S02_COMPILED_DIRECTORY,
                    root / assembly.VIP_S02_COMPILED_DIRECTORY)
    evidence = root / "review" / "compiled-wiring-test.txt"
    evidence.parent.mkdir()
    evidence.write_text("临时测试证据；不授正式赛事或强度。\n")
    monkeypatch.setattr(assembly, "_REPO_ROOT", root)
    digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
    payload = assembly.build_vip_free_manifest({evidence.relative_to(root).as_posix(): digest})
    manifest = root / assembly.VIP_S02_FREE_MANIFEST
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return root, payload


def configuration(root, payload):
    """仅构造无真实凭证的实验自由赛配置；失败必须早于资源装配。"""
    return assembly.runtime_config_from_mapping(dict(
        mode="auto_match", token_kind="official", token="public-test-only",
        base_url="https://platform.invalid", expected_tournament_id="",
        known_guide_version=payload["known_guide_version"], audit_root=str(root / "audit"),
        strategy=assembly.VIP_S02_FREE_STRATEGY, sse_enabled=True,
        expected_policy_release_id=payload["release_package_id"],
    ))


def test_new_package_binds_every_native_original_and_exclusive_compute_mode(release_root):
    root, payload = release_root
    identity = payload["compiled_runtime"]
    directory = root / identity["directory"]
    raw = (directory / "manifest.json").read_bytes()
    assert identity["manifest_sha256"] == hashlib.sha256(raw).hexdigest()
    assert identity["manifest"] == json.loads(raw)
    assert set(identity["manifest"]["binaries"]) == {
        "_s02_meter", "_s02_candidate", "_s02_facts", "_s02_runtime"}
    for row in identity["manifest"]["binaries"].values():
        actual = (directory / row["filename"]).read_bytes()
        assert len(actual) == row["bytes"]
        assert hashlib.sha256(actual).hexdigest() == row["sha256"]
    assert payload["params"]["compute_settings"]["workers"] == 10
    assert payload["params"]["compute_settings"]["max_pending"] == 0
    assert payload["params"]["compute_settings"]["per_game_workers"] is True
    assert payload["allowed_modes"] == ["auto_match"]
    assert payload["strength_admission"] is payload["production_default"] is False
    assert assembly.VIP_S02_FREE_STRATEGY.endswith("free_v6")
    assert assembly.VIP_S02_TESTROOM_STRATEGY.endswith("testroom_v8")
    configuration(root, payload)


@pytest.mark.parametrize("kind", ("binary", "generated", "manifest"))
def test_actual_native_drift_is_rejected_before_http_or_audit(release_root, monkeypatch, kind):
    root, payload = release_root
    config = configuration(root, payload)
    directory = root / payload["compiled_runtime"]["directory"]
    if kind == "binary":
        target = directory / payload["compiled_runtime"]["manifest"]["binaries"]["_s02_meter"]["filename"]
    elif kind == "generated":
        target = directory / "_s02_meter.pyx"
    else:
        target = directory / "manifest.json"
    target.write_bytes(target.read_bytes() + b" ")
    created = []
    monkeypatch.setattr(assembly, "JsonlAuditSink", lambda *args, **kwargs: created.append("audit"))
    with pytest.raises(RuntimeError, match="S02"):
        assembly.build_auto_match_runtime(config, AutoMatchSettings("test-only"),
            session_factory=lambda: created.append("http"))
    assert created == []


def test_native_abi_drift_rejects_freeze_instead_of_creating_relabelled_package(release_root):
    root, payload = release_root
    path = root / payload["compiled_runtime"]["directory"] / "manifest.json"
    value = json.loads(path.read_bytes())
    value["python_cache_tag"] = "cpython-unverified"
    path.write_text(json.dumps(value))
    with pytest.raises(RuntimeError, match="ABI"):
        assembly.build_vip_free_manifest(payload["evidence_sha256"])


def test_package_cannot_relabel_a_different_native_original_even_with_fresh_package_id(release_root):
    """重新计算包摘要仍须逐项核实际原件，不能只相信包自述或清单SHA。"""
    root, payload = release_root
    payload["compiled_runtime"]["manifest"]["binaries"]["_s02_meter"]["bytes"] += 1
    body = {key: value for key, value in payload.items() if key != "release_package_id"}
    payload["release_package_id"] = hashlib.sha256(json.dumps(body, ensure_ascii=False,
        sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    (root / assembly.VIP_S02_FREE_MANIFEST).write_text(json.dumps(payload, ensure_ascii=False))
    with pytest.raises(RuntimeError, match="编译运行时清单与冻结包不匹配"):
        configuration(root, payload)


@pytest.mark.asyncio
async def test_real_worker_factory_injects_native_runtime_and_preserves_all_scores(release_root, monkeypatch):
    """由公开组装得到真实工厂；阻断旧Python助手证明编译接线已经使用。"""
    root, payload = release_root
    config = configuration(root, payload)
    unit = assembly.build_auto_match_runtime(config, AutoMatchSettings("test-only"),
                                            session_factory=lambda: object())
    rule_config = RuleConfig(assembly.DEFAULT_RULESET_VERSION, 1, False)
    observation = make_observation(
        my_hand=tuple(Tile(code) for code in ("1w", "2w", "3w", "1t", "2t", "3t",
            "1b", "2b", "3b", "7w", "8w", "东", "东")),
        drawn_tile=Tile("南"), hand_counts=(14, 13, 13, 13), chain_piao=0, gang_draw=False)
    rules = HangmaRules(rule_config).analyze(observation, route_limits=assembly.VIP_S02_ROUTE_LIMITS)
    request = make_request(observation, rules, phase=WindowPhase.DRAW)
    baseline = RouteVipHeuristicPolicy(rule_config, source=assembly.VIP_S02_SOURCE,
        max_operations=4_800_000, projection_limits=assembly.VIP_S02_PROJECTION_LIMITS)
    expected = await baseline.choose(request, make_budget())

    def reject_old_python_runtime(*args, **kwargs):
        raise AssertionError("不得重新使用未接线的Python受限助手")

    monkeypatch.setattr(action_value_executor, "_make_runtime", reject_old_python_runtime)
    prepared = unit.compute.factory()
    actual = await prepared.policy.choose(request, make_budget())
    assert prepared.execution_id == payload["release_package_id"]
    assert actual == expected
    assert prepared.policy.executor.last_operation_count == baseline.executor.last_operation_count
    assert len(actual.candidates) == len(request.rules.legal_candidates)
    assert not actual.degraded_reasons
    assert unit.compute.snapshot()["live_processes"] == 0
    await unit.compute.close()
    await unit.sink.aclose(timeout_seconds=1)
