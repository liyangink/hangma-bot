"""在专用隔离副本接线T110-S03；不改生产、玩家、凭据或已冻结公式。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/successor-wiring-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import hashlib
import json
import platform
import pprint
import shutil
import sys
import sysconfig
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
WORK = _project_file(_PROJECT_ROOT, '.private/t191-successor-wiring/workspace')
EVIDENCE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1')
PREP = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/runtime-preparation-1')


def pin(path):
    """返回实际字节数和SHA；只读取指定公开文件。"""
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def save(path, value):
    """只写新证据；失败或已有产物不能自动覆盖。"""
    with path.open("x") as output:
        json.dump(value, output, ensure_ascii=False, indent=2, allow_nan=False)
        output.write("\n")


def edit(path, before, after):
    """只替换唯一且已确认的旧片段；隔离副本没有其他作者改动。"""
    raw = path.read_text()
    assert raw.count(before) == 1, str(path) + ":预期片段不是唯一"
    path.write_text(raw.replace(before, after))


SUPPORT = r'''
def _verify_vip_s03_runtime(expected_manifest_sha256: str | None = None) -> tuple[dict, Path]:
    """启动期验签新公式及原共享助手；不编译，不扫描确认牌桌原流。"""
    import platform
    import sys
    import sysconfig
    directory = _REPO_ROOT / VIP_S03_COMPILED_DIRECTORY
    raw = (directory / "manifest.json").read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if expected_manifest_sha256 is not None and actual != expected_manifest_sha256:
        raise RuntimeError("S03编译清单身份不匹配")
    manifest = json.loads(raw)
    required = {"schema", "identity", "module", "files", "shared_original_helpers",
        "original_execution_id", "python_implementation", "python_cache_tag", "platform", "machine", "ext_suffix"}
    name = "_t191_candidate_" + VIP_S03_IDENTITY["candidate_id"][:12]
    names = {"source.py", name + ".pyx", "_s02_meter.pxd", name + ".c",
        name + sysconfig.get_config_var("EXT_SUFFIX"), "BUILD-PLAN.json", "BUILD-CLOSED.json"}
    if (type(manifest) is not dict or set(manifest) != required
            or manifest.get("schema") != "vip-s03-compiled-formula/1"
            or manifest.get("identity") != VIP_S03_IDENTITY or manifest.get("module") != name
            or manifest.get("python_implementation") != sys.implementation.name
            or manifest.get("python_cache_tag") != sys.implementation.cache_tag
            or manifest.get("platform") != sys.platform or manifest.get("machine") != platform.machine()
            or manifest.get("ext_suffix") != sysconfig.get_config_var("EXT_SUFFIX")
            or type(manifest.get("files")) is not dict or set(manifest["files"]) != names):
        raise RuntimeError("S03公式、编译范围或ABI不匹配")
    for relative, expected in VIP_S03_IDENTITY["source_manifest"].items():
        body = (_REPO_ROOT / relative).read_bytes()
        if len(body) != expected["bytes"] or hashlib.sha256(body).hexdigest() != expected["sha256"]:
            raise RuntimeError("S03已确认核心源码漂移: " + relative)
    for filename, expected in manifest["files"].items():
        if (type(expected) is not dict or set(expected) != {"bytes", "sha256"}
                or type(expected["bytes"]) is not int or expected["bytes"] < 1
                or type(expected["sha256"]) is not str or len(expected["sha256"]) != 64
                or any(c not in "0123456789abcdef" for c in expected["sha256"])):
            raise RuntimeError("S03编译文件摘要格式错误")
        body = (directory / filename).read_bytes()
        if len(body) != expected["bytes"] or hashlib.sha256(body).hexdigest() != expected["sha256"]:
            raise RuntimeError("S03编译文件漂移: " + filename)
    if (hashlib.sha256(VIP_S03_SOURCE.encode()).hexdigest() != VIP_S03_IDENTITY["source_sha256"]
            or manifest["files"]["source.py"]["sha256"] != VIP_S03_IDENTITY["source_sha256"]):
        raise RuntimeError("S03已确认公式原文漂移")
    shared, _ = _verify_vip_s02_runtime()
    if manifest["shared_original_helpers"] != shared:
        raise RuntimeError("S03共享编译助手漂移")
    build_raw = (directory / "BUILD-PLAN.json").read_bytes()
    build = json.loads(build_raw)
    closed = json.loads((directory / "BUILD-CLOSED.json").read_text())
    binary = directory / (name + manifest["ext_suffix"])
    build_pin = {"bytes": len(build_raw), "sha256": hashlib.sha256(build_raw).hexdigest()}
    binary_pin = manifest["files"][binary.name]
    execution = hashlib.sha256(json.dumps({"build_plan_pin": build_pin, "binary_pin": binary_pin},
        sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    if (closed.get("complete") is not True or closed.get("candidate_identity") != VIP_S03_IDENTITY
            or build.get("candidate_identity") != VIP_S03_IDENTITY or build.get("module") != name
            or build.get("shared_original_helpers") != shared or closed.get("build_plan_pin") != build_pin
            or closed.get("binary_pin") != binary_pin or manifest["original_execution_id"] != execution):
        raise RuntimeError("S03未绑定实际已验证编译原件")
    return {"directory": VIP_S03_COMPILED_DIRECTORY, "manifest_sha256": actual, "manifest": manifest}, binary


def _load_vip_s03_runtime(expected_manifest_sha256: str):
    """每个工作进程启动时装载新公式，复用原助手；动作窗口没有文件访问。"""
    import importlib.util
    import sys
    from dataclasses import replace
    global _VIP_S03_NATIVE_CACHE
    identity, binary = _verify_vip_s03_runtime(expected_manifest_sha256)
    name = identity["manifest"]["module"]
    base = _load_vip_s02_runtime(identity["manifest"]["shared_original_helpers"]["manifest_sha256"])
    if _VIP_S03_NATIVE_CACHE is not None:
        digest, module = _VIP_S03_NATIVE_CACHE
        if digest != identity["manifest_sha256"] or sys.modules.get(name) is not module:
            raise RuntimeError("S03已装模块身份漂移")
    else:
        if name in sys.modules:
            raise RuntimeError("S03扩展名已被未验签模块占用")
        spec = importlib.util.spec_from_file_location(name, binary)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(name, None)
            raise
        _VIP_S03_NATIVE_CACHE = identity["manifest_sha256"], module
    return replace(base, source_sha256=VIP_S03_IDENTITY["source_sha256"],
        execution_id=identity["manifest"]["original_execution_id"], candidate_factory=module.make_candidate)


def build_vip_s03_manifest(strategy: str, evidence_sha256: Mapping[str, str]) -> dict:
    """冻结已确认候选的单一模式包；不写文件、不发HTTP，不授榜前对手优势。"""
    if strategy not in VIP_S03_PACKAGE_SCOPES:
        raise ValueError("未知S03冻结作用域")
    if (not evidence_sha256 or any(type(k) is not str or type(v) is not str or len(v) != 64
            or any(c not in "0123456789abcdef" for c in v) for k, v in evidence_sha256.items())
            or any(evidence_sha256.get(k) != v for k, v in VIP_S03_REQUIRED_EVIDENCE_SHA256.items())):
        raise ValueError("S03缺本次实际确认、等价、原截止、重型或原件封存证据")
    _verify_vip_evidence(evidence_sha256)
    from hangma_bot.adapters.official.dto import KNOWN_GUIDE_VERSION
    math = hand_math_runtime_metadata()
    # 离线身份另存原生二进制大小；线上元数据使用native_sha256，不能直接比较两种结构。
    expected_math = VIP_S03_IDENTITY["math_backend"]
    expected_runtime_math = {k: expected_math[k] for k in ("implementation", "semantics_version", "fallback_reason")}
    expected_runtime_math["native_sha256"] = expected_math["native_binary"]["sha256"]
    if math != expected_runtime_math:
        raise RuntimeError("S03实际数学后端与独立确认不同")
    from hangma_bot.hangma import _grouped_native
    actual_native = Path(_grouped_native.__file__).read_bytes()
    if (len(actual_native) != expected_math["native_binary"]["bytes"]
            or hashlib.sha256(actual_native).hexdigest() != expected_math["native_binary"]["sha256"]):
        raise RuntimeError("S03实际数学二进制与独立确认不同")
    params = _vip_params()
    accepted_params = VIP_S03_IDENTITY["params"]
    if (any(params[k] != accepted_params[k] for k in
            ("rule_config", "route_limits", "projection_limits", "max_operations"))
            or accepted_params["max_local_collection_size"] != 8192):
        raise RuntimeError("S03运行参数与独立确认不同")
    mode, admission, _ = VIP_S03_PACKAGE_SCOPES[strategy]
    payload = {"schema": "vip-route-bounded-release/3", "strategy": strategy, "allowed_modes": [mode],
        "known_guide_version": KNOWN_GUIDE_VERSION, "params": params,
        "base_candidate_id": VIP_S02_BASE_CANDIDATE_ID, "candidate_identity": VIP_S03_IDENTITY,
        "source_sha256": VIP_S03_IDENTITY["source_sha256"], "source_manifest": _vip_runtime_sources(),
        "hand_math": math, "compiled_runtime": _verify_vip_s03_runtime()[0],
        "evidence_sha256": dict(evidence_sha256), "admission": admission,
        "strength_admission": True, "strength_scope": "t191-frozen-local-mixed-pool-net-vs-s02",
        "production_default": False, "llm_online": False}
    payload["release_package_id"] = _vip_package_id(payload)
    return payload


def _load_vip_s03_manifest(strategy: str, expected_id: str | None = None) -> dict:
    """配置、当前来源、实际二进制及确认证据全部绑定；错配在联网前拒绝。"""
    payload = json.loads((_REPO_ROOT / VIP_S03_PACKAGE_SCOPES[strategy][2]).read_text())
    if type(payload) is not dict or type(payload.get("evidence_sha256")) is not dict:
        raise ValueError("S03冻结包结构错误")
    actual = _vip_package_id(payload)
    if payload.get("release_package_id") != actual or expected_id is not None and expected_id != actual:
        raise ValueError("S03配置绑定的冻结包摘要不匹配")
    expected = build_vip_s03_manifest(strategy, payload["evidence_sha256"])
    if json.dumps(payload, sort_keys=True, allow_nan=False) != json.dumps(expected, sort_keys=True, allow_nan=False):
        raise RuntimeError("S03冻结范围、完整源码、参数或编译绑定漂移")
    return payload


'''


def main():
    """只对事前逐字节副本准备三处接线；保留全部旧作用域身份。"""
    prepared = json.loads((_project_file(_PROJECT_ROOT, HERE / "INPUTS-PREPARED.json")).read_text())
    assert prepared["complete"] and prepared["workspace"] == str(WORK)
    for relative, expected in prepared["copied_baseline_files"].items():
        assert pin(_project_file(_PROJECT_ROOT, WORK / relative)) == expected, relative
    assert not (_project_file(_PROJECT_ROOT, HERE / "ASSEMBLY-PREPARED.json")).exists()
    plan = json.loads((_project_file(_PROJECT_ROOT, EVIDENCE / "wait-confirmation-1/wait-confirmation-001-PLAN.json")).read_text())
    identity = plan["candidates"][0]["identity"]
    required = [_project_file(_PROJECT_ROOT, PREP / "CONFIRMATION-GATE-ACTUAL.json"), _project_file(_PROJECT_ROOT, PREP / "native-verification/CLOSED.json"),
        _project_file(_PROJECT_ROOT, PREP / "original-deadline-probe/CLOSED.json"), _project_file(_PROJECT_ROOT, PREP / "heavy-nominal-deadline-probe/CLOSED.json"),
        _project_file(_PROJECT_ROOT, EVIDENCE / "wait-confirmation-1/wait-confirmation-001-dispatch/SUMMARY.json"),
        _project_file(_PROJECT_ROOT, EVIDENCE / "wait-confirmation-1/sealed-originals-1/CLOSED.json")]
    evidence = {}
    for path in required:
        data = json.loads(path.read_text())
        assert data.get("complete", data.get("complete_independent_confirmation_accepted")) is True, path
        relative = path.relative_to(ROOT)
        destination = _project_file(_PROJECT_ROOT, WORK / relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            assert pin(destination) == pin(path)
        else:
            shutil.copyfile(path, destination)
        evidence[relative.as_posix()] = pin(path)["sha256"]
    source = (_project_file(_PROJECT_ROOT, EVIDENCE / "wait-reassessment-1/candidate/source.py")).read_text()
    assert hashlib.sha256(source.encode()).hexdigest() == identity["source_sha256"] and "'''" not in source
    frozen = _project_file(_PROJECT_ROOT, WORK / "src/hangma_bot/policy/vip_s03_frozen_source.py")
    assert not frozen.exists()
    frozen.write_text('"""T110-S03确认公式、核心依赖和强度证据的逐字冻结；无IO或模型调用。"""\n\n'
        + "VIP_S03_IDENTITY = " + pprint.pformat(identity, width=100, sort_dicts=True) + "\n\n"
        + "VIP_S03_REQUIRED_EVIDENCE_SHA256 = " + pprint.pformat(evidence, width=100, sort_dicts=True) + "\n\n"
        + "VIP_S03_SOURCE = r'''" + source + "'''\n")
    directory = _project_file(_PROJECT_ROOT, WORK / "prebuilt/vip-s03-compiled-formula-v1")
    directory.mkdir()
    name = "_t191_candidate_" + identity["candidate_id"][:12]
    originals = _project_file(_PROJECT_ROOT, PREP / "native-candidate/saved-build-artifacts")
    files = {}
    inputs = [originals / (name + suffix) for suffix in (".pyx", ".c", sysconfig.get_config_var("EXT_SUFFIX"))]
    inputs += [originals / "_s02_meter.pxd", _project_file(_PROJECT_ROOT, PREP / "native-candidate/BUILD-PLAN.json"), _project_file(_PROJECT_ROOT, PREP / "native-candidate/BUILD-CLOSED.json")]
    for path in inputs:
        shutil.copyfile(path, directory / path.name)
        files[path.name] = pin(path)
    (directory / "source.py").write_bytes(source.encode())
    files["source.py"] = pin(directory / "source.py")
    build = json.loads((directory / "BUILD-PLAN.json").read_text())
    closed = json.loads((directory / "BUILD-CLOSED.json").read_text())
    assert closed["complete"] and closed["candidate_identity"] == build["candidate_identity"] == identity
    execution = hashlib.sha256(json.dumps({"build_plan_pin": pin(directory / "BUILD-PLAN.json"),
        "binary_pin": closed["binary_pin"]}, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    save(directory / "manifest.json", {"schema": "vip-s03-compiled-formula/1", "identity": identity,
        "module": name, "files": files, "shared_original_helpers": build["shared_original_helpers"],
        "original_execution_id": execution, "python_implementation": sys.implementation.name,
        "python_cache_tag": sys.implementation.cache_tag, "platform": sys.platform,
        "machine": platform.machine(), "ext_suffix": sysconfig.get_config_var("EXT_SUFFIX")})
    bootstrap, launcher = _project_file(_PROJECT_ROOT, WORK / "src/hangma_bot/bootstrap.py"), _project_file(_PROJECT_ROOT, WORK / "scripts/run_test_room.py")
    before = {p.relative_to(WORK).as_posix(): pin(p) for p in (bootstrap, launcher)}
    edit(bootstrap, "from hangma_bot.policy.vip_s02_frozen_source import VIP_S02_SOURCE, VIP_S02_SOURCE_SHA256",
        "from hangma_bot.policy.vip_s02_frozen_source import VIP_S02_SOURCE, VIP_S02_SOURCE_SHA256\n"
        "from hangma_bot.policy.vip_s03_frozen_source import (VIP_S03_SOURCE, VIP_S03_IDENTITY,\n    VIP_S03_REQUIRED_EVIDENCE_SHA256)")
    constants = "\n# S03四个固定模式；S02备用另冻结，不覆盖旧包或公式。\n"
    for suffix, mode, admission in (("TESTROOM", "test_room", "engineering_test_room_only"),
            ("FREE", "auto_match", "experimental_free_match_only"),
            ("TEST_TOURNAMENT", "test_tournament", "test_tournament_runtime_candidate_only"),
            ("OFFICIAL_TOURNAMENT", "official_tournament", "official_tournament_runtime_candidate_only")):
        token = suffix.lower()
        constants += f'VIP_S03_{suffix}_STRATEGY = "vip_s03_bounded_d1_{token}_v1"\n'
    constants += "VIP_S03_PACKAGE_SCOPES = {\n"
    for suffix, mode, admission in (("TESTROOM", "test_room", "engineering_test_room_only"),
            ("FREE", "auto_match", "experimental_free_match_only"),
            ("TEST_TOURNAMENT", "test_tournament", "test_tournament_runtime_candidate_only"),
            ("OFFICIAL_TOURNAMENT", "official_tournament", "official_tournament_runtime_candidate_only")):
        path = "prebuilt/vip-s03-bounded-d1-" + suffix.lower().replace("_", "-") + "-v1/manifest.json"
        constants += f'    VIP_S03_{suffix}_STRATEGY: ("{mode}", "{admission}", "{path}"),\n'
    constants += "}\nVIP_S03_COMPILED_DIRECTORY = \"prebuilt/vip-s03-compiled-formula-v1\"\n_VIP_S03_NATIVE_CACHE = None\n"
    constants += "VIP_S02_BACKUP_PACKAGE_SCOPES = {\n"
    for token, version, mode, admission in (("testroom", 10, "test_room", "engineering_test_room_only"),
            ("free", 8, "auto_match", "experimental_free_match_only"),
            ("test_tournament", 2, "test_tournament", "test_tournament_runtime_candidate_only"),
            ("official_tournament", 2, "official_tournament", "official_tournament_runtime_candidate_only")):
        constants += f'    "vip_s02_bounded_d1_{token}_v{version}": ("{mode}", "{admission}", "prebuilt/vip-s02-bounded-d1-{token.replace("_", "-")}-v{version}/manifest.json"),\n'
    constants += "}\nVIP_S02_PARTICIPANT_STRATEGIES += tuple(k for k,v in VIP_S02_BACKUP_PACKAGE_SCOPES.items() if v[0] != 'auto_match')\n"
    constants += "VIP_S02_AUTO_MATCH_STRATEGIES += tuple(k for k,v in VIP_S02_BACKUP_PACKAGE_SCOPES.items() if v[0] == 'auto_match')\n"
    constants += "VIP_PARTICIPANT_STRATEGIES = (*VIP_S02_PARTICIPANT_STRATEGIES, *(k for k,v in VIP_S03_PACKAGE_SCOPES.items() if v[0] != 'auto_match'))\n"
    constants += "VIP_AUTO_MATCH_STRATEGIES = (*VIP_S02_AUTO_MATCH_STRATEGIES, VIP_S03_FREE_STRATEGY)\n"
    constants += "VIP_NETWORK_STRATEGIES = (*VIP_PARTICIPANT_STRATEGIES, *VIP_AUTO_MATCH_STRATEGIES)\n"
    constants += "VIP_TESTROOM_STRATEGIES = tuple(k for k in VIP_NETWORK_STRATEGIES if 'testroom' in k)\n\n"
    edit(bootstrap, "def _verify_vip_s02_runtime(", constants + "def _verify_vip_s02_runtime(")
    edit(bootstrap, "def _vip_runtime_sources() -> dict[str, str]:", SUPPORT + "def _vip_runtime_sources() -> dict[str, str]:")
    edit(bootstrap, '    if strategy == VIP_S02_TESTROOM_STRATEGY:\n',
        '    if strategy in VIP_S03_PACKAGE_SCOPES:\n        return VIP_S03_PACKAGE_SCOPES[strategy]\n'
        '    if strategy in VIP_S02_BACKUP_PACKAGE_SCOPES:\n        return VIP_S02_BACKUP_PACKAGE_SCOPES[strategy]\n'
        '    if strategy == VIP_S02_TESTROOM_STRATEGY:\n')
    edit(bootstrap, '    mode, admission, manifest_path = _vip_package_scope(strategy)\n',
        '    if strategy in VIP_S03_PACKAGE_SCOPES:\n        return _load_vip_s03_manifest(strategy, expected_id)\n'
        '    mode, admission, manifest_path = _vip_package_scope(strategy)\n')
    edit(bootstrap, '        policy = RouteVipHeuristicPolicy(\n            RuleConfig(**package["params"]["rule_config"]), source=VIP_S02_SOURCE,',
        '        is_s03 = self.strategy in VIP_S03_PACKAGE_SCOPES\n'
        '        runtime = (_load_vip_s03_runtime if is_s03 else _load_vip_s02_runtime)(package["compiled_runtime"]["manifest_sha256"])\n'
        '        policy = RouteVipHeuristicPolicy(\n            RuleConfig(**package["params"]["rule_config"]), source=VIP_S03_SOURCE if is_s03 else VIP_S02_SOURCE,')
    edit(bootstrap, '            compiled_runtime=_load_vip_s02_runtime(package["compiled_runtime"]["manifest_sha256"]))',
        '            compiled_runtime=runtime)')
    raw = bootstrap.read_text()
    for old, new in (("in VIP_S02_NETWORK_STRATEGIES", "in VIP_NETWORK_STRATEGIES"),
            ("in VIP_S02_PARTICIPANT_STRATEGIES", "in VIP_PARTICIPANT_STRATEGIES"),
            ("in VIP_S02_AUTO_MATCH_STRATEGIES", "in VIP_AUTO_MATCH_STRATEGIES"),
            ("+ VIP_S02_NETWORK_STRATEGIES)", "+ VIP_NETWORK_STRATEGIES)")):
        assert old in raw
        raw = raw.replace(old, new)
    raw = raw.replace("实际配置与官方测试赛事通过仍须另行验收", "实际正式配置与现场流程另核；已取消的测试锦标赛不作为前置")
    bootstrap.write_text(raw)
    edit(launcher, "    VIP_S02_AUTO_MATCH_STRATEGIES,", "    VIP_AUTO_MATCH_STRATEGIES,\n    VIP_TESTROOM_STRATEGIES,\n    VIP_NETWORK_STRATEGIES,")
    edit(launcher, "if value in VIP_S02_AUTO_MATCH_STRATEGIES:", "if value in VIP_AUTO_MATCH_STRATEGIES:")
    edit(launcher, '        raise ValueError("VIP自由赛冻结包只允许auto_match，不能用于测试房")\n    return value',
        '        raise ValueError("VIP自由赛冻结包只允许auto_match，不能用于测试房")\n'
        '    if value in VIP_NETWORK_STRATEGIES and value not in VIP_TESTROOM_STRATEGIES:\n'
        '        raise ValueError("VIP赛事冻结包不能用于测试房；须使用对应模式的单身份入口")\n    return value')
    edit(launcher, "for vip_strategy in (VIP_S02_TESTROOM_STRATEGY, VIP_S02_TESTROOM_SUCCESSOR_STRATEGY):", "for vip_strategy in VIP_TESTROOM_STRATEGIES:")
    edit(launcher, "        VIP_S02_TESTROOM_STRATEGY,\n        VIP_S02_TESTROOM_SUCCESSOR_STRATEGY,", "        *VIP_TESTROOM_STRATEGIES,")
    for path in (bootstrap, launcher, frozen):
        compile(path.read_text(), str(path), "exec")
    changed = {p.relative_to(WORK).as_posix(): {"before": before.get(p.relative_to(WORK).as_posix()), "after": pin(p)}
        for p in (bootstrap, launcher, frozen)}
    for relative, expected in prepared["copied_baseline_files"].items():
        if relative not in changed:
            assert pin(_project_file(_PROJECT_ROOT, WORK / relative)) == expected, relative
    save(_project_file(_PROJECT_ROOT, HERE / "ASSEMBLY-PREPARED.json"), {"complete": True, "workspace": str(WORK),
        "changed_source_files": changed, "native_files": files, "native_manifest_pin": pin(directory / "manifest.json"),
        "candidate_identity": identity, "required_actual_evidence_sha256": evidence,
        "new_score_world_table_HTTP_model_calls": 0, "production_or_watchdog_modified": False,
        "assembly_functional_or_deadline_admission": False})
    print(json.dumps({"complete": True, "changed_source_files": len(changed), "new_scores_HTTP": 0}))


if __name__ == "__main__":
    main()
