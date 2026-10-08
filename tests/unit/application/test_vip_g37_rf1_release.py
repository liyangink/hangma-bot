"""RF1独立包作用域/拒绝/组合根接线；全为本地合成收据，不连接平台。"""
import hashlib
import json
import platform
import sys
import sysconfig
from pathlib import Path
from types import SimpleNamespace

import pytest

import hangma_bot.bootstrap as assembly
from hangma_bot.application.auto_match_runtime import AutoMatchSettings
from hangma_bot.policy import vip_g37_rf1_release as release


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


def pin(path):
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


@pytest.fixture
def compiled_root(tmp_path):
    """只用于验签边界的合成二进制；不加载、不冒称实际原生等价。"""
    real = Path(assembly.__file__).resolve().parents[2]; root = tmp_path / "root"
    root.mkdir(); (root / "src").symlink_to(real / "src", target_is_directory=True)
    directory = root / release.COMPILED_DIRECTORY; directory.mkdir(parents=True)
    name = release.MODULE_NAME; suffix = sysconfig.get_config_var("EXT_SUFFIX")
    (directory / "source.py").write_bytes((real / "review/vip-route-2026-09-30/evidence/t226-minimal-scoring-repair-1/candidate.py").read_bytes())
    for filename in [name + ".pyx", name + ".c", name + suffix, "_s02_meter.pxd"]:
        (directory / filename).write_bytes(b"synthetic-test-only-not-executable")
    shared = {"directory": "test-shared", "manifest_sha256": "a" * 64}
    build = {"candidate_identity": release.VIP_G37_RF1_IDENTITY, "module": name, "shared_original_helpers": shared}
    write(directory / "BUILD-PLAN.json", build)
    build_pin = pin(directory / "BUILD-PLAN.json"); binary_pin = pin(directory / (name + suffix))
    write(directory / "BUILD-CLOSED.json", {"complete": True, "candidate_identity": release.VIP_G37_RF1_IDENTITY,
        "build_plan_pin": build_pin, "binary_pin": binary_pin})
    execution = hashlib.sha256(release._canonical({"build_plan_pin": build_pin, "binary_pin": binary_pin})).hexdigest()
    manifest = {"schema": "vip-s03-compiled-formula/1", "identity": release.VIP_G37_RF1_IDENTITY, "module": name,
        "files": {p.name: pin(p) for p in directory.iterdir()}, "shared_original_helpers": shared,
        "original_execution_id": execution, "python_implementation": sys.implementation.name,
        "python_cache_tag": sys.implementation.cache_tag, "platform": sys.platform, "machine": platform.machine(), "ext_suffix": suffix}
    write(directory / "manifest.json", manifest)
    compiled, _ = release.verify_compiled_runtime(root, shared)
    return root, shared, compiled


def approve(root, compiled):
    """合成测试批准，绝不写真实prebuilt收据。"""
    directory = root / release.EVIDENCE_DIRECTORY; rules = "b" * 64; receipts = {}
    for key, name in release.REQUIRED_RECEIPTS.items():
        proof = {"complete": True, "candidate_identity": release.VIP_G37_RF1_IDENTITY, "rules_source_hash": rules, key: True}
        if key == "native_equivalence_passed":
            proof["compiled_runtime"] = compiled
        if key == "runtime_passed":
            proof.update(runtime_passed_for_covered_legal_deadline_and_fault_recovery=True,
                corrected_fallback_passed_for_covered_faults=True, native={"execution_id": compiled["manifest"]["original_execution_id"]})
        write(directory / name, proof)
        receipts[key] = {"path": release.EVIDENCE_ORIGIN + "/" + name, "pin": pin(directory / name)}
    write(directory / "PUBLISH-APPROVAL.json", {"schema": "vip-g37-rf1-publish-approval/1", "complete": True,
        "release_kind": "scoring_defect_repair", "candidate_identity": release.VIP_G37_RF1_IDENTITY, "compiled_runtime": compiled,
        "rules_source_hash": rules, "strength_admission": False, "approved_modes": ["test_room", "auto_match", "test_tournament", "official_tournament"],
        "receipts": receipts, "reviewer": "synthetic-test-only"})
    return rules


def build(root, shared, rules, strategy):
    """用生产builder核合成包，没有实际native装载或策略评分。"""
    identity = release.VIP_G37_RF1_IDENTITY; backend = identity["math_backend"]
    math = {k: backend[k] for k in ["implementation", "semantics_version", "fallback_reason"]}
    math["native_sha256"] = backend["native_binary"]["sha256"]
    return release.build_manifest(root, strategy, runtime_sources={"synthetic": "c" * 64}, params=assembly._vip_params(),
        hand_math=math, shared_runtime_identity=shared, rules_source_hash=rules, known_guide_version=35)


@pytest.mark.parametrize("strategy", release.PACKAGE_SCOPES)
def test_missing_own_receipts_remains_draft_and_refuses_startup(compiled_root, strategy):
    root, shared, _ = compiled_root; payload = build(root, shared, "b" * 64, strategy)
    assert payload["startup_admitted"] is False and payload["strength_admission"] is False
    assert payload["inherits_P0_approval"] is False and payload["production_default"] is False
    write(root / release.PACKAGE_SCOPES[strategy][2], payload)
    with pytest.raises(RuntimeError, match="draft"):
        release.load_manifest(root, strategy, payload["release_package_id"], build=lambda s: build(root, shared, "b" * 64, s))


@pytest.mark.parametrize("fault", ["P0_identity", "binary", "ABI", "parameter", "strength_claim"])
def test_rf1_cannot_relabel_p0_or_bypass_native_and_approval(compiled_root, fault):
    root, shared, compiled = compiled_root; rules = approve(root, compiled)
    strategy = "vip_g37_rf1_free_v1"
    if fault == "P0_identity":
        path = root / release.EVIDENCE_DIRECTORY / "REPAIR-CLOSED.json"; value = json.loads(path.read_text())
        value["candidate_identity"] = assembly.VIP_S03_RULEFIX_P0_IDENTITY; write(path, value)
    elif fault == "binary":
        path = root / release.COMPILED_DIRECTORY / (release.MODULE_NAME + sysconfig.get_config_var("EXT_SUFFIX"))
        path.write_bytes(path.read_bytes() + b"drift")
    elif fault == "ABI":
        path = root / release.COMPILED_DIRECTORY / "manifest.json"; value = json.loads(path.read_text()); value["python_cache_tag"] = "wrong"; write(path, value)
    elif fault == "strength_claim":
        path = root / release.EVIDENCE_DIRECTORY / "PUBLISH-APPROVAL.json"; value = json.loads(path.read_text()); value["strength_admission"] = True; write(path, value)
    else:
        params = assembly._vip_params(); params["compute_settings"]["max_pending"] = 1
        with pytest.raises(RuntimeError, match="参数"):
            release.build_manifest(root, strategy, runtime_sources={}, params=params, hand_math={}, shared_runtime_identity=shared, rules_source_hash=rules, known_guide_version=35)
        return
    with pytest.raises(RuntimeError):
        build(root, shared, rules, strategy)


@pytest.fixture
def approved_config_package(compiled_root, monkeypatch):
    root, shared, compiled = compiled_root; rules = approve(root, compiled)
    monkeypatch.setattr(assembly, "_REPO_ROOT", root)
    monkeypatch.setattr(assembly, "build_vip_g37_rf1_manifest", lambda s: build(root, shared, rules, s))
    payloads = {}
    for strategy, (_, _, path) in release.PACKAGE_SCOPES.items():
        value = build(root, shared, rules, strategy); write(root / path, value); payloads[strategy] = value
    return root, payloads


def configuration(root, strategy, payload, **changes):
    mode = release.PACKAGE_SCOPES[strategy][0]
    values = {"mode": mode, "token_kind": "test" if mode in ["test_room", "test_tournament"] else "official",
        "token": "synthetic-test-only", "base_url": "https://platform.invalid", "expected_tournament_id": "t1",
        "known_guide_version": 35, "audit_root": str(root / "audit"), "strategy": strategy, "sse_enabled": True,
        "expected_policy_release_id": payload["release_package_id"]}
    values.update(changes); return assembly.runtime_config_from_mapping(values)


@pytest.mark.parametrize("strategy", release.PACKAGE_SCOPES)
def test_four_explicit_modes_bind_own_id_and_sse(approved_config_package, strategy):
    root, payloads = approved_config_package; payload = payloads[strategy]
    config = configuration(root, strategy, payload)
    assert config.strategy == strategy
    assert len({p["release_package_id"] for p in payloads.values()}) == 4
    for changes in [{"expected_policy_release_id": None}, {"expected_policy_release_id": "0" * 64}, {"sse_enabled": False}]:
        with pytest.raises((ValueError, RuntimeError)):
            configuration(root, strategy, payload, **changes)


def test_wrong_mode_rejects_before_session_or_audit_creation(approved_config_package, monkeypatch):
    root, payloads = approved_config_package; strategy = "vip_g37_rf1_free_v1"; called = []
    monkeypatch.setattr(assembly, "JsonlAuditSink", lambda *a, **k: called.append("audit"))
    with pytest.raises(ValueError, match="各自绑定"):
        configuration(root, strategy, payloads[strategy], mode="test_tournament", token_kind="test")
    assert called == []


def test_factory_injects_rf1_source_and_runtime_without_s03_identity(approved_config_package, monkeypatch):
    root, payloads = approved_config_package; strategy = "vip_g37_rf1_free_v1"; payload = payloads[strategy]; calls = {}
    monkeypatch.setattr(assembly, "_verify_vip_s02_runtime", lambda: (payload["compiled_runtime"]["manifest"]["shared_original_helpers"], {}))
    monkeypatch.setattr(assembly, "_load_vip_s02_runtime", lambda sha: SimpleNamespace(marker="base"))
    monkeypatch.setattr(release, "load_compiled_runtime", lambda r, c, base: SimpleNamespace(marker="RF1"))
    monkeypatch.setattr(assembly, "RouteVipHeuristicPolicy", lambda config, **kwargs: calls.update(kwargs) or SimpleNamespace())
    unit = assembly._VipWorkerFactory(payload["release_package_id"], strategy)()
    assert calls["compiled_runtime"].marker == "RF1"
    assert hashlib.sha256(calls["source"].encode()).hexdigest() == release.VIP_G37_RF1_IDENTITY["source_sha256"]
    assert unit.execution_id == payload["release_package_id"]
    assert assembly.VIP_S02_COMPUTE_SETTINGS.workers == 10 and assembly.VIP_S02_COMPUTE_SETTINGS.max_pending == 0
    assert assembly.DEFAULT_STRATEGY == "weighted_heuristic"
