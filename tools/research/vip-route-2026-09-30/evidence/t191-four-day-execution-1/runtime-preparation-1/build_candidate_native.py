"""唯一确认通过后编译新公式；共享S02助手，独立候选二进制及执行身份。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/runtime-preparation-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import hashlib
import fcntl
import importlib.util
import json
import sys
import sysconfig
from dataclasses import replace
from pathlib import Path

from confirmation_gate import read_accepted_confirmation
from prepare_runtime_inputs import HERE, ROOT, WORK, background_priority, pin, postprocess_lock, require, save

OUT = _project_file(_PROJECT_ROOT, HERE / "native-candidate")
_LOADED = {}  # 启动期验签的本候选模块；不进入受限公式命名空间。


def digest(value):
    """有限JSON摘要作为执行身份；不以候选名称代替实际二进制。"""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def load_checked_runtime():
    """启动期验签并装配新公式，不在动作窗口中编译或读取全确认原件。"""
    from hangma_bot import bootstrap
    plan = json.loads((OUT / "BUILD-PLAN.json").read_text())
    closed = json.loads((OUT / "BUILD-CLOSED.json").read_text())
    require(closed["complete"] is True and closed["build_plan_pin"] == pin(OUT / "BUILD-PLAN.json") and
        closed["candidate_identity"] == plan["candidate_identity"] and
        all(pin(Path(p)) == expected for p, expected in plan["build_input_files"].items()), "本候选编译输入未闭合或漂移")
    name = "_t191_candidate_" + plan["candidate_identity"]["candidate_id"][:12]
    binary = Path(closed["binary_path"])
    require(name == plan["module"] and binary.resolve().is_relative_to(WORK.resolve()) and
        binary.name == name + sysconfig.get_config_var("EXT_SUFFIX") and pin(binary) == closed["binary_pin"],
        "候选二进制、路径或本机ABI不同")
    shared, _ = bootstrap._verify_vip_s02_runtime()
    require(shared == plan["shared_original_helpers"], "共享助手漂移")
    base = bootstrap._load_vip_s02_runtime(shared["manifest_sha256"])
    identity = digest({"build_plan_pin": pin(OUT / "BUILD-PLAN.json"), "binary_pin": closed["binary_pin"]})
    if name in _LOADED:
        expected, module = _LOADED[name]
        require(expected == identity and sys.modules.get(name) is module, "已装模块身份漂移")
    else:
        require(name not in sys.modules, "候选扩展名被未验签模块占用")
        spec = importlib.util.spec_from_file_location(name, binary)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(name, None)
            raise
        _LOADED[name] = identity, module
    return replace(base, source_sha256=plan["candidate_identity"]["source_sha256"], execution_id=identity,
        candidate_factory=module.make_candidate)


def main():
    """确认门通过后只编译隔离目录；失败保留原BUILD，不授等价、时限或上线。"""
    background_priority()
    with postprocess_lock("t191-confirmed-wait-native-build-preparation"):
        confirmation, _, evidence = read_accepted_confirmation(verify_raw_files=True)
        checked_path = _project_file(_PROJECT_ROOT, HERE / "GATE-TOOLS-CHECKED.json")
        checked = json.loads(checked_path.read_text())
        require(checked["complete"] is True and all(pin(Path(p)) == expected for p, expected in checked["files"].items()),
            "确认门工具预检未通过或漂移")
        prepared = json.loads((_project_file(_PROJECT_ROOT, HERE / "CLOSED.json")).read_text())
        candidate = confirmation["candidates"][0]
        require(prepared["candidate"] == candidate and prepared["complete"] is True and
            all(pin(WORK / name) == expected for name, expected in prepared["generated_candidate_input_files"].items()),
            "隔离候选输入漂移")
        from hangma_bot import bootstrap
        shared, _ = bootstrap._verify_vip_s02_runtime()
        require(shared == prepared["preflight"]["native"], "准备以来共享助手漂移")
        name = "_t191_candidate_" + candidate["identity"]["candidate_id"][:12]
        draft = WORK / "draft-candidate"
        source, meter = draft / (name + ".pyx"), draft / "_s02_meter.pxd"
        from common import OLD
        from evaluation_sharding import resource_slot_paths
        slot_path = resource_slot_paths(OLD, 4)[0]
        resource_lock = slot_path.open("r+")
        try:
            fcntl.flock(resource_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            resource_lock.close()
            raise
        OUT.mkdir(exist_ok=False)
        build_plan = {"schema": "t191-confirmed-wait-native-build/1", "module": name,
            "candidate_identity": candidate["identity"], "confirmation_evidence_files": evidence,
            "shared_original_helpers": shared, "new_formula_not_old_s02_candidate": True,
            "build_input_files": {str(p): pin(p) for p in (Path(__file__), _project_file(_PROJECT_ROOT, HERE / "confirmation_gate.py"),
                Path(candidate["source_file"]), source, meter, checked_path)},
            "material": prepared["material"], "ext_suffix": sysconfig.get_config_var("EXT_SUFFIX"),
            "shared_research_slot_lock": str(slot_path),
            "compiled_formula_equivalence_admitted": False, "original_deadline_admitted": False,
            "new_scores_worlds_tables_HTTP_models": 0}
        save(OUT / "BUILD-PLAN.json", build_plan)
    # CPU编译不持赛后IO锁；独立确认须已自然退出，编译不与它争研究槽。
    try:
        from Cython.Build import cythonize
        from setuptools import Extension, setup
        setup(name="t191-confirmed-wait-original-body", ext_modules=cythonize([Extension(name, [str(source)])],
            compiler_directives=prepared["material"]["directives"], include_path=[str(draft)]),
            script_args=["build_ext", "--build-temp", str(draft / "build/temp"), "--build-lib", str(draft / "build/lib")])
        binary, = (draft / "build/lib").glob(name + "*.so")
        require(binary.name == name + build_plan["ext_suffix"] and
            all(pin(Path(p)) == expected for p, expected in build_plan["build_input_files"].items()), "编译期间输入或ABI漂移")
        require(bootstrap._verify_vip_s02_runtime()[0] == shared, "编译期间共享助手漂移")
        save(OUT / "BUILD-CLOSED.json", {"complete": True, "build_plan_pin": pin(OUT / "BUILD-PLAN.json"),
            "binary_path": str(binary), "binary_pin": pin(binary), "candidate_identity": candidate["identity"],
            "compiled_formula_equivalence_admitted": False, "original_deadline_admitted": False,
            "new_scores_worlds_tables_HTTP_models": 0})
    except BaseException as error:
        save(OUT / "BUILD-FAILED.json", {"failure": {"type": type(error).__name__, "message": str(error)},
            "build_plan_pin": pin(OUT / "BUILD-PLAN.json"), "original_files_preserved": True})
        raise
    finally:
        resource_lock.close()


if __name__ == "__main__":
    main()
