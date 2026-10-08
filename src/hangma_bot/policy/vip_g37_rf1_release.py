"""独立G37-RF1发布包的启动验签；不读取对手隐手，不在choose内读盘。"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import platform
import sys
import sysconfig
from dataclasses import replace
from pathlib import Path
from typing import Mapping

from .vip_g37_rf1_identity import VIP_G37_RF1_IDENTITY

COMPILED_DIRECTORY = "prebuilt/vip-g37-rf1-compiled-v1"
EVIDENCE_DIRECTORY = "prebuilt/vip-g37-rf1-release-evidence-v1"
EVIDENCE_ORIGIN = "review/vip-route-2026-09-30/evidence/t226-minimal-scoring-repair-1"
MODULE_NAME = "_t226_rf1_candidate_" + VIP_G37_RF1_IDENTITY["candidate_id"][:12]
COMPUTE_SETTINGS = {"workers": 10, "max_pending": 0, "max_message_bytes": 16777216,
    "startup_seconds": 5.0, "max_job_seconds": 3.0, "abandon_grace_seconds": 0.1,
    "resource_reap_seconds": 1.0, "max_restarts": 2, "per_game_workers": True}
PACKAGE_SCOPES = {
    "vip_g37_rf1_testroom_v1": ("test_room", "scoring_repair_testroom_only", "prebuilt/vip-g37-rf1-testroom-v2/manifest.json"),
    "vip_g37_rf1_free_v1": ("auto_match", "scoring_repair_free_only", "prebuilt/vip-g37-rf1-free-v2/manifest.json"),
    "vip_g37_rf1_test_tournament_v1": ("test_tournament", "scoring_repair_test_tournament_only", "prebuilt/vip-g37-rf1-test-tournament-v2/manifest.json"),
    "vip_g37_rf1_official_tournament_v1": ("official_tournament", "scoring_repair_official_tournament_only", "prebuilt/vip-g37-rf1-official-tournament-v2/manifest.json"),
}
REQUIRED_RECEIPTS = {
    "repair_passed": "REPAIR-CLOSED.json",
    "native_equivalence_passed": "NATIVE-EQUIVALENCE-CLOSED.json",
    "runtime_passed": "ENGINEERING-CLOSED.json",
    "representative_regression_passed": "SHORT-REGRESSION-CLOSED.json",
}
_NATIVE_CACHE = None


def _canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def package_id(payload: Mapping) -> str:
    """完整规范JSON摘要；包ID字段自身不参与摘要。"""
    return hashlib.sha256(_canonical({k: v for k, v in payload.items() if k != "release_package_id"})).hexdigest()


def _pin(path: Path) -> dict:
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def verify_compiled_runtime(root: Path, shared_runtime_identity: Mapping,
                            expected_manifest_sha256: str | None = None) -> tuple[dict, Path]:
    """只在启动验签RF1原体、ABI和共享助手；不编译或装入扩展。"""
    directory = root / COMPILED_DIRECTORY
    raw = (directory / "manifest.json").read_bytes(); digest = hashlib.sha256(raw).hexdigest()
    if expected_manifest_sha256 is not None and digest != expected_manifest_sha256:
        raise RuntimeError("RF1编译清单身份不匹配")
    manifest = json.loads(raw); suffix = sysconfig.get_config_var("EXT_SUFFIX")
    required = {"schema", "identity", "module", "files", "shared_original_helpers", "original_execution_id",
                "python_implementation", "python_cache_tag", "platform", "machine", "ext_suffix"}
    filenames = {"source.py", MODULE_NAME + ".pyx", "_s02_meter.pxd", MODULE_NAME + ".c", MODULE_NAME + suffix,
                 "BUILD-PLAN.json", "BUILD-CLOSED.json"}
    if (type(manifest) is not dict or set(manifest) != required
            or manifest["schema"] != "vip-s03-compiled-formula/1" or manifest["identity"] != VIP_G37_RF1_IDENTITY
            or manifest["module"] != MODULE_NAME or manifest["python_implementation"] != sys.implementation.name
            or manifest["python_cache_tag"] != sys.implementation.cache_tag or manifest["platform"] != sys.platform
            or manifest["machine"] != platform.machine() or manifest["ext_suffix"] != suffix
            or type(manifest["files"]) is not dict or set(manifest["files"]) != filenames
            or manifest["shared_original_helpers"] != shared_runtime_identity):
        raise RuntimeError("RF1源码身份、编译范围、助手或ABI不匹配")
    for relative, expected in VIP_G37_RF1_IDENTITY["source_manifest"].items():
        if _pin(root / relative) != expected:
            raise RuntimeError("RF1核心源码漂移: " + relative)
    for filename, expected in manifest["files"].items():
        if (type(expected) is not dict or set(expected) != {"bytes", "sha256"}
                or type(expected["bytes"]) is not int or expected["bytes"] < 1
                or type(expected["sha256"]) is not str or len(expected["sha256"]) != 64
                or any(c not in "0123456789abcdef" for c in expected["sha256"])):
            raise RuntimeError("RF1编译文件摘要格式错误")
        if _pin(directory / filename) != expected:
            raise RuntimeError("RF1编译文件漂移: " + filename)
    if manifest["files"]["source.py"]["sha256"] != VIP_G37_RF1_IDENTITY["source_sha256"]:
        raise RuntimeError("RF1修复源原文不匹配")
    build_path = directory / "BUILD-PLAN.json"; build_pin = _pin(build_path)
    build = json.loads(build_path.read_bytes()); closed = json.loads((directory / "BUILD-CLOSED.json").read_bytes())
    binary = directory / (MODULE_NAME + suffix); binary_pin = manifest["files"][binary.name]
    execution = hashlib.sha256(_canonical({"build_plan_pin": build_pin, "binary_pin": binary_pin})).hexdigest()
    if (build.get("candidate_identity") != VIP_G37_RF1_IDENTITY or build.get("module") != MODULE_NAME
            or build.get("shared_original_helpers") != shared_runtime_identity or closed.get("complete") is not True
            or closed.get("candidate_identity") != VIP_G37_RF1_IDENTITY or closed.get("build_plan_pin") != build_pin
            or closed.get("binary_pin") != binary_pin or manifest["original_execution_id"] != execution):
        raise RuntimeError("RF1实际编译原件未闭合绑定")
    return {"directory": COMPILED_DIRECTORY, "manifest_sha256": digest, "manifest": manifest}, binary


def source_body(root: Path) -> str:
    """启动期读取已验签原文，动作窗口不访问文件。"""
    body = (root / COMPILED_DIRECTORY / "source.py").read_bytes()
    if hashlib.sha256(body).hexdigest() != VIP_G37_RF1_IDENTITY["source_sha256"]:
        raise RuntimeError("RF1原文漂移")
    return body.decode("utf-8")


def load_compiled_runtime(root: Path, compiled: Mapping, base_runtime):
    """组合根验签后装入RF1独立模块，透传S02原meter/facts/runtime。"""
    global _NATIVE_CACHE
    name = compiled["manifest"]["module"]; digest = compiled["manifest_sha256"]
    if name != MODULE_NAME:
        raise RuntimeError("RF1模块作用域不匹配")
    if _NATIVE_CACHE is not None:
        old_digest, module = _NATIVE_CACHE
        if old_digest != digest or sys.modules.get(name) is not module:
            raise RuntimeError("RF1已装载扩展身份或绑定漂移")
    else:
        if name in sys.modules:
            raise RuntimeError("RF1模块名被未经验签的模块占用")
        path = root / COMPILED_DIRECTORY / (name + compiled["manifest"]["ext_suffix"])
        if _pin(path) != compiled["manifest"]["files"][path.name]:
            raise RuntimeError("RF1装载前二进制漂移")
        spec = importlib.util.spec_from_file_location(name, path); module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(name, None)
            raise
        _NATIVE_CACHE = digest, module
    return replace(base_runtime, source_sha256=VIP_G37_RF1_IDENTITY["source_sha256"],
                   execution_id=compiled["manifest"]["original_execution_id"], candidate_factory=module.make_candidate)


def _qualification(root: Path, compiled: Mapping, rules_source_hash: str) -> tuple[bool, dict]:
    """RF1独立修复审批；缺件保持draft，错身份拒绝，绝不继承P0批准。"""
    directory = root / EVIDENCE_DIRECTORY
    names = [*REQUIRED_RECEIPTS.values(), "PUBLISH-APPROVAL.json"]
    missing = [name for name in names if not (directory / name).is_file()]
    if missing:
        return False, {"release_kind": "scoring_defect_repair", "final_approval_passed": False,
                       "pending": missing, "inherits_P0_approval": False, "strength_confirmation_required": False}
    receipts = {}; flags = {}
    for key, name in REQUIRED_RECEIPTS.items():
        path = directory / name; proof = json.loads(path.read_bytes())
        if (proof.get("candidate_identity") != VIP_G37_RF1_IDENTITY
                or proof.get("rules_source_hash") != rules_source_hash):
            raise RuntimeError("RF1独立修复收据身份不符: " + name)
        flag = proof.get(key) if key != "runtime_passed" else proof.get("runtime_passed_for_covered_legal_deadline_and_fault_recovery")
        flags[key] = proof.get("complete") is True and flag is True
        if key == "native_equivalence_passed" and proof.get("compiled_runtime") != compiled:
            raise RuntimeError("RF1原生等价收据不属于当前二进制")
        if key == "runtime_passed":
            flags[key] = flags[key] and proof.get("corrected_fallback_passed_for_covered_faults") is True
            if proof.get("native", {}).get("execution_id") != compiled["manifest"]["original_execution_id"]:
                raise RuntimeError("RF1及时合法收据原生身份不符")
        receipts[key] = {"path": EVIDENCE_ORIGIN + "/" + name, "pin": _pin(path)}
    approval = json.loads((directory / "PUBLISH-APPROVAL.json").read_bytes())
    if (approval.get("schema") != "vip-g37-rf1-publish-approval/1"
            or type(approval.get("complete")) is not bool or approval.get("release_kind") != "scoring_defect_repair"
            or approval.get("candidate_identity") != VIP_G37_RF1_IDENTITY or approval.get("compiled_runtime") != compiled
            or approval.get("rules_source_hash") != rules_source_hash or approval.get("strength_admission") is not False
            or approval.get("approved_modes") != ["test_room", "auto_match", "test_tournament", "official_tournament"]
            or approval.get("receipts") != receipts):
        raise RuntimeError("RF1最终批准范围或实际原件绑定不符")
    approved = approval["complete"] and all(flags.values())
    if approval["complete"] and (not approved or type(approval.get("reviewer")) is not str or not approval["reviewer"].strip()):
        raise RuntimeError("RF1批准声称通过但修复/等价/及时合法/代表回归未闭")
    return approved, {"release_kind": "scoring_defect_repair", **flags, "receipts": receipts,
                      "final_approval_passed": approved, "inherits_P0_approval": False, "strength_confirmation_required": False}


def build_manifest(root: Path, strategy: str, *, runtime_sources: Mapping, params: Mapping, hand_math: Mapping,
                   shared_runtime_identity: Mapping, rules_source_hash: str, known_guide_version: int) -> dict:
    """冻结RF1唯一模式包；只核实际工程修复，不设置收益或现场赛事门。"""
    if strategy not in PACKAGE_SCOPES:
        raise ValueError("未知RF1发布作用域")
    accepted = VIP_G37_RF1_IDENTITY["params"]
    if (any(params[k] != accepted[k] for k in ["rule_config", "route_limits", "projection_limits", "max_operations"])
            or params["compute_settings"] != COMPUTE_SETTINGS
            or accepted["max_local_collection_size"] != 8192):
        raise RuntimeError("RF1参数或每桌独立计算范围漂移")
    expected_math = VIP_G37_RF1_IDENTITY["math_backend"]
    if hand_math != {"implementation": expected_math["implementation"], "semantics_version": expected_math["semantics_version"],
                     "fallback_reason": expected_math["fallback_reason"], "native_sha256": expected_math["native_binary"]["sha256"]}:
        raise RuntimeError("RF1规则数学原生身份漂移")
    compiled, _ = verify_compiled_runtime(root, shared_runtime_identity)
    approved, qualification = _qualification(root, compiled, rules_source_hash)
    mode, admission, _ = PACKAGE_SCOPES[strategy]
    payload = {"schema": "vip-g37-rf1-scoring-defect-repair-release/1", "display": "G37-RF1", "strategy": strategy,
        "allowed_modes": [mode], "known_guide_version": known_guide_version, "params": dict(params),
        "candidate_identity": VIP_G37_RF1_IDENTITY, "source_sha256": VIP_G37_RF1_IDENTITY["source_sha256"],
        "rules_source_hash": rules_source_hash, "source_manifest": dict(runtime_sources), "hand_math": dict(hand_math),
        "compiled_runtime": compiled, "admission": admission, "release_kind": "scoring_defect_repair",
        "release_status": "approved" if approved else "draft", "startup_admitted": approved, "qualification": qualification,
        "strength_admission": False, "strength_scope": "repair-only-no-enhancement-claim", "correctness_fix": False,
        "full_ten_scoring_admitted": False, "real_HTTP_submissions_verified": False,
        "production_default": False, "llm_online": False, "inherits_P0_approval": False}
    payload["release_package_id"] = package_id(payload)
    return payload


def load_manifest(root: Path, strategy: str, expected_id: str | None, *, build, offline_validation_only: bool = False) -> dict:
    """配置/工作进程同一路径验签，未批准在会话与资源装配前拒绝。"""
    if strategy not in PACKAGE_SCOPES:
        raise ValueError("未知RF1发布作用域")
    payload = json.loads((root / PACKAGE_SCOPES[strategy][2]).read_bytes()); actual = package_id(payload)
    if payload.get("release_package_id") != actual or expected_id is not None and expected_id != actual:
        raise ValueError("RF1配置绑定的发布包摘要不匹配")
    if _canonical(payload) != _canonical(build(strategy)):
        raise RuntimeError("RF1完整源码、参数、修复批准或编译绑定漂移")
    if not offline_validation_only and payload["startup_admitted"] is not True:
        raise RuntimeError("RF1仍是draft；独立修复发布批准未闭，禁止启动")
    return payload
