"""T200 微型共同P0余桌适配；原T199 driver、恢复、采样和规则不改。

默认prepare仅检查现接口及真实全座来源，0评分/World/桌/API。候选机械
两次完整评分闭合后才绑定最多两改点加一同选负控，每点两相容世界、
父/子首动作两臂，随后本家共同P0至R8桌末；根精确收据才能execute。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t200-eoh-fast-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import ast
import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import types

ROOT = _PROJECT_ROOT
STAGE = _project_file(_PROJECT_ROOT, '.private/t200-eoh-fast-evolution')
OUT = _project_file(_PROJECT_ROOT, '.private/t200-eoh-fast-evolution/tiny-followup')
OLD = _project_file(_PROJECT_ROOT, '.private/t199-four-step-execution/joint-continuation')
DEFAULT_BINDINGS = _project_file(_PROJECT_ROOT, '.private/t200-eoh-fast-evolution/frontier-feedback-001/ORIGIN-BINDINGS.json')
TEMPLATE = _project_file(_PROJECT_ROOT, '.private/t199-four-step-execution/joint-continuation/G2-connection-diagnostic-prepared-1/PLAN.json')
P0_PARENT = _project_file(_PROJECT_ROOT, '.private/t200-eoh-fast-evolution/parents/p0-reference')
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))


def module_file(path, name):
    """装载已有stdlib薄helper；不替换其全局或修改原件。"""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def legacy():
    """只取原common定义；其恢复和采样入口不会在prepare被调用。"""
    return module_file(_project_file(_PROJECT_ROOT, OLD / "common.py"), "_t200_original_joint_helpers")


def driver_tree():
    """唯一AST差异是移除common导入，由隔离namespace注入原同函数。"""
    tree = ast.parse((_project_file(_PROJECT_ROOT, OLD / "run_point.py")).read_text())
    imports = [node for node in tree.body if isinstance(node, ast.ImportFrom) and node.module == "common"]
    if len(imports) != 1:
        raise ValueError("原driver导入接缝不唯一")
    names = [alias.name for alias in imports[0].names]
    tree.body.remove(imports[0])
    # 原同动作负控、恢复/采样、首动作强制、完整余桌终点和所有计费/结算门均保留。
    return tree, names


def source_material(bindings_path):
    """只核真实P032来源与当前P0父身份；不读取确认池或恢复世界。"""
    old = legacy()
    bindings = old.read(bindings_path)
    if bindings["schema"] != "t200-frontier-teacher-prefix-binding/1":
        raise ValueError("不是T200已封全座前缀来源")
    source, origins, files, _ = old.composite_origins(bindings["source_plan_path"], bindings["source_composite_path"])
    parent = old.read(_project_file(_PROJECT_ROOT, P0_PARENT / "generation.json"))
    if source["candidate_identity"] != parent["identity"]:
        raise ValueError("来源不是当前已发布P0精确父")
    files.update({str(path.resolve()): old.pin(path) for path in
        (Path(bindings_path), Path(__file__), _project_file(_PROJECT_ROOT, OLD / "common.py"), _project_file(_PROJECT_ROOT, OLD / "run_point.py"), TEMPLATE,
         _project_file(_PROJECT_ROOT, P0_PARENT / "candidate.py"), _project_file(_PROJECT_ROOT, P0_PARENT / "generation.json"), _project_file(_PROJECT_ROOT, STAGE / "AUTHOR-BATCH-001.json"))})
    for point in bindings["points"]:
        origin = origins[point["table_no"]]
        if point["source_origin"] != origin or point["task"] != origin["task"]:
            raise ValueError("点的真实任务/来源映射不同")
        case_path = Path(point["case_path"])
        if old.pin(case_path) != point["case_pin"]:
            raise ValueError("完整公开case漂移")
        files[str(case_path)] = point["case_pin"]
    old.verify_files(files)
    return old, bindings, source, files


def new_output(path):
    """新原件只在T200独立续打目录；原T199账和源不可覆盖。"""
    path = Path(path).resolve()
    if not path.is_relative_to(OUT.resolve()) or path == OUT.resolve():
        raise ValueError("续打输出须为T200 tiny-followup下的新目录")
    path.mkdir(parents=True, exist_ok=False)
    return path


def prepare(args):
    """默认只准备接口；给候选与真实机械闭件时冻结至多12轨迹计划。"""
    old, bindings, source, files = source_material(args.bindings)
    tree, names = driver_tree()
    if any(not hasattr(old, name) for name in names if name != "checked_plan"):
        raise ValueError("旧common依赖缺失")
    derived = ast.unparse(tree) + "\n"
    if args.candidate is None or args.probe is None:
        out = new_output(args.out or _project_file(_PROJECT_ROOT, OUT / "interface-prepared-001"))
        old.save(out / "PREPARED.json", {"schema": "t200-tiny-followup-interface-preparation/1", "complete": True,
            "files": files, "bindings_pin": old.pin(args.bindings), "available_real_points": len(bindings["points"]),
            "derived_driver_AST_sha256": hashlib.sha256(derived.encode()).hexdigest(),
            "only_driver_AST_change": "remove one common import; inject same original functions plus T200 plan validator",
            "same_action_negative_control_required_unchanged": True,
            "compatible_sampler": "original engine.resample_public_consistent_hidden_world",
            "endpoint": "current_complete_R8_table_end", "maximum_points_with_control": 3,
            "maximum_trajectories": 12, "candidate_mechanical_binding_pending": True,
            "scores_World_tables_API": 0, "original_T199_files_or_ledgers_modified": False})
        return {"complete": True, "status": "interface_prepared_not_executable", "scores_World_tables_API": 0,
                "receipt": str(out / "PREPARED.json")}
    from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, STAGE / "AUTHOR-BATCH-001.json"))
    candidate = load_vip_parents([args.candidate], batch)[0]
    probe = Path(args.probe).resolve()
    closed = old.read(probe / "CLOSED.json")
    if closed.get("complete") is not True or closed.get("failures"):
        raise ValueError("候选机械没有真实完整闭合")
    rows = {}
    with (probe / "RESULTS.jsonl").open() as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("candidate_id") == candidate["identity"]["candidate_id"]:
                label = row.get("label", row.get("case_id"))
                rows.setdefault(label, []).append(row)
    compared = []
    for point in bindings["points"]:
        repeated = rows.get(point["case_id"], [])
        if len(repeated) != 2 or {row.get("repeat") for row in repeated} != {0, 1}:
            continue
        if any(row.get("status") != "scored" or row.get("score_calls") != 1 for row in repeated):
            raise ValueError("候选点没有两次真实完整评分")
        if repeated[0]["entries"] != repeated[1]["entries"]:
            raise ValueError("候选点两次评分不确定")
        for row in repeated:
            sha = row.get("view_sha256", row.get("view_sha256_before"))
            if sha != point["view_sha256"]:
                raise ValueError("候选真实输入不是同源P0完整图")
        entries = repeated[0]["entries"]
        if sorted(entry["action_key"] for entry in entries) != sorted(point["legal_action_keys"]):
            raise ValueError("候选评分没有覆盖全部合法根")
        chosen = sorted(entries, key=lambda entry: (-entry["score"], entry["action_key"]))[0]["action_key"]
        compared.append({**point, "candidate_first": chosen, "changed": chosen != point["parent_first"],
            "same_action_negative_control": chosen == point["parent_first"],
            "candidate_mechanical_entries_sha256": hashlib.sha256(old.canonical(entries)).hexdigest()})
    changed = [point for point in compared if point["changed"]][:2]
    controls = [point for point in compared if point["same_action_negative_control"]][:1]
    if not changed or not controls:
        raise ValueError("必须有实际机械改选与同源实际同选负控，0World不购买轨迹")
    points = changed + controls
    template = old.read(TEMPLATE)
    measurement_path = _project_file(_PROJECT_ROOT, ROOT / ".private/t199-four-step-execution/p0-impact-32-attempt-004/PLAN.json")
    gate = old.measurement_gate(source, measurement_path)
    files.update({str(measurement_path): old.pin(measurement_path), str(Path(gate["helper_path"])): gate["helper_pin"]})
    for path in (probe / "CLOSED.json", probe / "RESULTS.jsonl", args.candidate / "generation.json", args.candidate / "candidate.py"):
        files[str(path.resolve())] = old.pin(path)
    out = new_output(args.out or _project_file(_PROJECT_ROOT, OUT / "binding-001"))
    (out / "REUSED-DRIVER.py").write_text(derived)
    files[str(out / "REUSED-DRIVER.py")] = old.pin(out / "REUSED-DRIVER.py")
    plan = {"schema": "t200-common-P0-tiny-continuation-plan/1", "candidate_identity": candidate["identity"],
        "candidate_package_path": str(args.candidate.resolve()), "candidate_mechanical_probe_path": str(probe),
        "source_impact_plan": bindings["source_plan_path"], "source_impact_plan_pin": old.pin(bindings["source_plan_path"]),
        "source_origin_manifest": bindings["source_composite_path"], "parent_identity": source["candidate_identity"],
        "points": points, "max_continuations": len(points) * 4, "compatible_samples_per_point": 2,
        "slot_paths": source["slot_paths"], "measurement_gate": gate, "files": files,
        "driver_snapshot_path": str(out / "REUSED-DRIVER.py"), "zero_changed_stop": False,
        "same_action_negative_control_present": True, "selection_failures": [],
        "selection_order": "已封frontier case顺序；首两个实际改选与首一个实际同选，未读效果挑点",
        "maximum_authorized_trajectories": 12, "World_tables_API": 0, "effects_auto_dispatch": False}
    for key in ("capture_limits", "logical_now", "max_all_seat_choose_windows_per_point", "max_focal_scores_per_point",
                "step_limit_per_continuation", "wall_seconds_per_point"):
        plan[key] = template[key]
    plan["binding_id"] = hashlib.sha256(old.canonical(plan)).hexdigest()
    old.verify_files(files)
    old.save(out / "RUN-PLAN.json", plan)
    old.save(out / "PREPARED.json", {"complete": True, "plan_pin": old.pin(out / "RUN-PLAN.json"),
        "binding_id": plan["binding_id"], "changed_points": len(changed), "same_action_negative_controls": 1,
        "planned_remaining_table_continuations": plan["max_continuations"], "scores_World_tables_API": 0,
        "original_driver_logic_AST_preserved_except_dependency_import": True,
        "candidate_formula_is_only_first_action_evidence": True, "common_continuation_formula": "published_P0_original_S03"})
    return {"complete": True, "status": "bound_not_executed", "plan": str(out / "RUN-PLAN.json"),
            "plan_pin": old.pin(out / "RUN-PLAN.json"), "binding_id": plan["binding_id"],
            "planned_trajectories": plan["max_continuations"], "scores_World_tables_API": 0}


def checked_plan(path):
    """替换的仅是新计划schema/预算绑定，生产恢复与driver规则保持原函数。"""
    old = legacy()
    plan = old.read(path)
    if (plan["schema"] != "t200-common-P0-tiny-continuation-plan/1" or not 2 <= len(plan["points"]) <= 3 or
        plan["max_continuations"] != len(plan["points"]) * 4 or plan["max_continuations"] > 12 or
        sum(point["same_action_negative_control"] for point in plan["points"]) != 1 or
        not any(point["changed"] for point in plan["points"])):
        raise ValueError("不是保留同选负控的至多12轨迹冻结计划")
    old.verify_files(plan["files"])
    body = {key: value for key, value in plan.items() if key != "binding_id"}
    if hashlib.sha256(old.canonical(body)).hexdigest() != plan["binding_id"]:
        raise ValueError("续打完整绑定不同")
    source, _ = old.verify_impact(plan["source_impact_plan"])
    old.composite_origins(plan["source_impact_plan"], plan["source_origin_manifest"])
    if source["candidate_identity"] != plan["parent_identity"] or old.pin(plan["source_impact_plan"]) != plan["source_impact_plan_pin"]:
        raise ValueError("共同P0父或来源计划不同")
    return plan, source


def execute(args):
    """干净解释器通过根收据后注入原函数，实际运行原run_point.run。"""
    if any(name == "hangma_bot" or name.startswith("hangma_bot.") for name in sys.modules):
        raise ValueError("需干净进程绑定原冻结P0，不能混载main")
    plan, _ = checked_plan(args.plan)
    if not Path(args.output).resolve().is_relative_to(OUT.resolve()):
        raise ValueError("实际输出只允许T200独立tiny-followup目录")
    old = legacy()
    tree, names = driver_tree()
    if Path(plan["driver_snapshot_path"]).read_text() != ast.unparse(tree) + "\n":
        raise ValueError("driver快照不是唯一导入接缝差异")
    module = types.ModuleType("_t200_original_joint_driver")
    module.__file__ = plan["driver_snapshot_path"]
    module.__dict__.update({name: checked_plan if name == "checked_plan" else getattr(old, name) for name in names})
    sys.modules[module.__name__] = module
    exec(compile(tree, plan["driver_snapshot_path"], "exec"), module.__dict__)
    # 原run会验证approved_for_common_continuation、plan_pin、binding_id、allowed_points、max轨迹。
    asyncio.run(module.run(args))
    return {"complete": True, "point": args.point, "driver": "original_T199_run_point"}


def main():
    """默认prepare，源接口检查和候选绑定均0World；execute必须根精确批准。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=("prepare", "execute"), default="prepare")
    parser.add_argument("--bindings", type=Path, default=DEFAULT_BINDINGS)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--probe", type=Path, help="已闭真实机械目录，CLOSED.json与RESULTS.jsonl")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--point", type=int)
    parser.add_argument("--slot", type=int, default=0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = prepare(args) if args.command == "prepare" else execute(args)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
