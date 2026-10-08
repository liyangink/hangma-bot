"""独立确认通过后编译唯一候选原体；共享助手必须精确绑定当前已验签S02制品。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import ast
import hashlib
import json
import os
import sys
import sysconfig
from dataclasses import replace
from pathlib import Path

from common import HERE, ROOT, pin, save
import t185_close_development as dev
from t185_prepare_confirmation import background_priority, postprocess_lock, read_confirmation_plan

ORIGINAL_GENERATOR = _project_file(_PROJECT_ROOT, HERE.parent / "t173-joint-exact-equivalence-1/build_native.py")
ORIGINAL_PLAN = ORIGINAL_GENERATOR.with_name("BUILD-PLAN.json")
_LOADED = {}  # 仅工作进程启动期缓存本工具验签的扩展；不进入候选的可变命名空间


def sha(raw):
    """实际字节摘要；输入源码与编译器转换分别绑定，不用候选名称替代身份。"""
    return hashlib.sha256(raw).hexdigest()


def material(source):
    """仅在内存生成受限原体Cython；不编译、不评分、不修改生产制品。"""
    from hangma_bot.policy import action_value_executor as executor
    golden = json.loads(ORIGINAL_PLAN.read_text())
    raw = ORIGINAL_GENERATOR.read_bytes()
    dev.require(sha(raw) == golden["generator_sha256"], "原始编译转换器漂移")
    tree = ast.parse(raw)
    transform_class = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "DirectCalls")
    constants = {}
    for n in tree.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            if n.targets[0].id in ("HELPERS", "METER_PXD"):
                constants[n.targets[0].id] = ast.literal_eval(n.value)
    context = {"ast": ast}
    exec(compile(ast.Module(body=[transform_class], type_ignores=[]), "<frozen-direct-calls>", "exec"), context)
    candidate = executor.static_check(source)
    instrumented = executor._Instrumentor().visit(ast.parse(ast.unparse(candidate)))
    ast.fix_missing_locations(instrumented)
    instrumented_sha = sha(ast.dump(instrumented, include_attributes=False).encode())
    transform = context["DirectCalls"]()
    direct = transform.visit(instrumented)
    ast.fix_missing_locations(direct)
    names = sorted(executor._make_runtime(executor._Meter(4_800_000), 8192))
    top = []
    for n in candidate.body:
        if isinstance(n, ast.FunctionDef):
            top.append(n.name)
        elif isinstance(n, ast.Assign):
            top.extend(target.id for target in n.targets)
        elif isinstance(n, ast.AnnAssign):
            top.append(n.target.id)
        else:
            dev.require(isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant), "非受限模块节点")
    text = constants["HELPERS"].replace("from _t173_meter cimport Meter", "from _s02_meter cimport Meter")
    text += "def make_candidate(runtime, Meter bound_meter, bound_cap):\n"
    text += "".join("    " + n + " = runtime[" + repr(n) + "]\n" for n in names)
    text += "".join("    " + line + "\n" for line in ast.unparse(direct).splitlines())
    text += '    return {"__builtins__": {},\n'
    text += "".join("        " + repr(n) + ": " + n + ",\n" for n in names + top) + "    }\n"
    directives = dict(language_level=3, annotation_typing=False, infer_types=False,
        boundscheck=True, wraparound=True, nonecheck=True, cdivision=False, overflowcheck=True, binding=True)
    dev.require(directives == golden["directives"], "原编译语义约束不同")
    return {"candidate_source_sha256": sha(source.encode()), "instrumented_ast_sha256": instrumented_sha,
        "direct_ast_sha256": sha(ast.dump(direct, include_attributes=False).encode()),
        "direct_sites": transform.counts, "candidate_pyx": text, "meter_pxd": constants["METER_PXD"],
        "directives": directives}


def load_checked_runtime():
    """离线原预算验证的启动期装配：实际源码、共享助手及候选二进制逐项验签。

    返回与生产执行器同型的编译接缝，不创建HTTP客户端、不读取隐藏世界。
    编译成功仍不授评分等价或时限；动作窗口内不得调用此装载方法。
    """
    import importlib.util
    from hangma_bot import bootstrap
    directory = _project_file(_PROJECT_ROOT, HERE / "native-candidate")
    closed, _ = dev.read(directory / "BUILD-CLOSED.json")
    plan, plan_pin = dev.read(directory / "BUILD-PLAN.json")
    dev.require(closed["complete"] is True and closed["build_plan_pin"] == plan_pin and
        closed["candidate_identity"] == plan["candidate_identity"], "候选编译未闭合或身份不同")
    dev.require(all(pin(Path(p)) == h for p,h in plan["files"].items()), "候选编译输入漂移")
    binary = Path(closed["binary_path"])
    module_name = "_t185_candidate_" + plan["candidate_identity"]["candidate_id"][:12]
    dev.require(binary.resolve().is_relative_to(directory.resolve()) and plan["module"] == module_name and
        binary.name == module_name + sysconfig.get_config_var("EXT_SUFFIX") and pin(binary) == closed["binary_pin"],
        "候选二进制路径、ABI或字节不同")
    shared, _ = bootstrap._verify_vip_s02_runtime()
    dev.require(shared == plan["shared_s02_runtime"], "共享助手不是原编译绑定")
    base = bootstrap._load_vip_s02_runtime(shared["manifest_sha256"])
    identity = sha(json.dumps({"build_plan_pin": plan_pin, "binary_pin": closed["binary_pin"]},
        sort_keys=True, separators=(",", ":")).encode())
    if module_name in _LOADED:
        expected_identity, module = _LOADED[module_name]
        dev.require(expected_identity == identity and sys.modules.get(module_name) is module, "已装入模块身份漂移")
    else:
        dev.require(module_name not in sys.modules, "候选扩展名被未经本工具验签的模块占用")
        spec = importlib.util.spec_from_file_location(module_name, binary)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(module_name, None)
            raise
        _LOADED[module_name] = (identity, module)
    return replace(base, source_sha256=plan["candidate_source_sha256"], execution_id=identity,
        candidate_factory=module.make_candidate)


def main():
    """只编译通过事前独立增强门的唯一公式；失败保留原文件，不继承S02时限成绩。"""
    background_priority()
    with postprocess_lock("confirmed_candidate_build_preparation"):
        plan, plan_pin = read_confirmation_plan(verify_development_evidence=True)
        closed, closed_pin = dev.read(_project_file(_PROJECT_ROOT, HERE / "CONFIRMATION-CLOSED.json"))
        dispatch, dispatch_pin = dev.read(_project_file(_PROJECT_ROOT, HERE / "confirmation-dispatch/CLOSED.json"))
        comparison = closed["comparison"]
        dev.require(closed["complete"] is True and closed["source_stable"] is True and
            closed["actual_table_instances"] == 1024 and closed["independent_strength_evidence_passed"] is True and
            comparison["mean_delta"]["net"] >= 0.5 and comparison["net_source_bootstrap95"][0] > 0 and
            dispatch["complete"] is True and dispatch["resources_released"] is True and
            dispatch["confirmation_closed_pin"] == closed_pin and closed["files"][str(_project_file(_PROJECT_ROOT, HERE / "CONFIRMATION-PLAN.json"))] == plan_pin,
            "确认强度或完整资源门未通过，禁止编译候选接线产物")
        arm = plan["candidates"][0]
        from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents
        batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
        dev.require(load_vip_parents([Path(arm["package"])], batch)[0]["identity"] == arm["identity"], "公式身份不同")
        from hangma_bot import bootstrap
        shared, paths = bootstrap._verify_vip_s02_runtime()
        source = Path(arm["source_file"]).read_text()
        body = material(source)
        dev.require(body["candidate_source_sha256"] == arm["identity"]["source_sha256"], "候选原体摘要不同")
        directory = _project_file(_PROJECT_ROOT, HERE / "native-candidate")
        directory.mkdir(exist_ok=False)
        module = "_t185_candidate_" + arm["identity"]["candidate_id"][:12]
        candidate_file = directory / (module + ".pyx")
        candidate_file.write_text(body.pop("candidate_pyx"))
        meter_file = directory / "_s02_meter.pxd"
        meter_file.write_text(body.pop("meter_pxd"))
        native = _project_file(_PROJECT_ROOT, ROOT / shared["directory"])
        dev.require(pin(meter_file) == pin(native / "_s02_meter.pxd"), "共享Meter ABI声明不同")
        build_plan = {"schema": "t185-confirmed-candidate-native-build/1", **body,
            "module": module, "candidate_identity": arm["identity"], "confirmation_plan_pin": plan_pin,
            "confirmation_closed_pin": closed_pin, "confirmation_dispatch_pin": dispatch_pin,
            "shared_s02_runtime": shared, "shared_runtime_not_candidate_formula_reused": True,
            "files": {str(p): pin(p) for p in (Path(__file__), ORIGINAL_GENERATOR, ORIGINAL_PLAN, Path(bootstrap.__file__),
                Path(arm["source_file"]), candidate_file, meter_file)},
            "compiled_formula_equivalence_admitted": False, "original_deadline_admitted": False,
            "new_scores_worlds_tables": 0, "ext_suffix": sysconfig.get_config_var("EXT_SUFFIX")}
        save(directory / "BUILD-PLAN.json", build_plan)
    # 编译只在本批独占目录；不持共同赛后IO锁，不写主线prebuilt。
    from Cython.Build import cythonize
    from setuptools import Extension, setup
    try:
        setup(name="t185-confirmed-candidate-original-body", ext_modules=cythonize(
            [Extension(module, [str(candidate_file)])], compiler_directives=body["directives"],
            include_path=[str(directory)]), script_args=["build_ext", "--build-temp", str(directory / "build/temp"),
                "--build-lib", str(directory / "build/lib")])
        binary, = (directory / "build/lib").glob(module + "*.so")
        dev.require(binary.name == module + build_plan["ext_suffix"], "实际候选ABI后缀不同")
        dev.require(all(pin(Path(p)) == h for p,h in build_plan["files"].items()), "编译期间输入漂移")
        actual_shared, _ = bootstrap._verify_vip_s02_runtime()
        dev.require(actual_shared == shared, "编译期间共享编译助手漂移")
        save(directory / "BUILD-CLOSED.json", {"complete": True, "build_plan_pin": pin(directory / "BUILD-PLAN.json"),
            "binary_path": str(binary), "binary_pin": pin(binary), "candidate_identity": arm["identity"],
            "compiled_formula_equivalence_admitted": False, "original_deadline_admitted": False,
            "new_scores_worlds_tables": 0})
    except BaseException as error:
        save(directory / "BUILD-FAILED.json", {"failure": {"type": type(error).__name__, "message": str(error)},
            "build_plan_pin": pin(directory / "BUILD-PLAN.json"), "original_files_preserved": True})
        raise


if __name__ == "__main__":
    main()
