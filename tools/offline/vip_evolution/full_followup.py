"""T200 两独立起点的完整策略余桌诊断；默认prepare为0评分/World/API。

原T199 driver仅作明确的AST装配差异：移除首动作强制，按臂装配P0与
完整候选，核每次本家完整评分及首窗机械证据。恢复、相容采样、资源锁、
对手、resume_match、R8终点和费用函数沿原实现。至多8条轨迹，无自动扩量。
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
from pathlib import Path
import sys
import textwrap
import types

import tiny_followup as tiny

ROOT, STAGE = tiny.ROOT, tiny.STAGE
OUT = STAGE / "full-followup"
CANDIDATE = STAGE / "generation-003/sol-e1-joint-ranking"
PROBE = STAGE / "mechanical-tools/search-stage-005-run-001"
SAMPLER = "simulation-v1:public-consistent-hidden-resample-v1"
FIXED = (("frontier-feedback-001", "T200-frontier-01", 1, 1, 120),
         ("frontier-feedback-002", "T200-frontier2-03", 2, 5, 86))
ROLE = "full_candidate_policy_remaining_R8_diagnostic"


def hash_value(value):
    """沿原严格JSON计算证据摘要，不舍入排序点。"""
    return hashlib.sha256(tiny.legacy().canonical(value)).hexdigest()


def derived_driver():
    """只改装配和审计语义；逐个AST锚计数，原恢复/采样/驱动函数不重写。"""
    tree, names = tiny.driver_tree()
    changes = []

    def replace(before, after, *, expression=False):
        mode = "eval" if expression else "exec"
        old = ast.parse(textwrap.dedent(before), mode=mode)
        old = old.body if expression else old.body[0]
        new = ast.parse(textwrap.dedent(after), mode=mode) if after else None
        replacement = new.body if new is not None else None
        wanted = ast.dump(old, include_attributes=False)
        hits = []

        class Rewrite(ast.NodeTransformer):
            def visit(self, node):
                if ast.dump(node, include_attributes=False) == wanted:
                    hits.append(node)
                    return replacement
                return super().visit(node)

        Rewrite().visit(tree)
        if len(hits) != 1:
            raise ValueError("原driver AST锚不唯一:" + before)
        changes.append({"before": before, "after": after, "matches": 1})

    tree.body = [node for node in tree.body if not isinstance(node, ast.ClassDef) or node.name != "FirstReceipt"]
    tree.body[0].value = ast.Constant(__doc__)
    replace('from hangma_bot.offline.forced_action import ForceFirstActionPolicy', '')
    replace('''if plan["zero_changed_stop"] or not plan["same_action_negative_control_present"]:
        raise ValueError("无改选或缺同动作负控；不购买续打")''', '')
    replace('approval.get("approved_for_common_continuation")',
            'approval.get("approved_for_t200_full_policy")', expression=True)
    # 精确计划原门继续执行；完整候选与采样身份另在运行前核收据。
    replace('''native = native_parent(source)''', '''native = native_parent(source)
candidate_source = candidate_material(plan, params)
ActionValueExecutor(candidate_source, max_operations=params.max_operations,
                    max_local_collection_size=params.projection_limits.max_nodes)''')
    replace('''current = {"sample": None, "arm": None}''', '''current = {"sample": None, "arm": None}
full_stats = {}''')
    run = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "run")
    record = next(node for node in ast.walk(run) if isinstance(node, ast.FunctionDef) and node.name == "record")
    record.body.insert(-1, ast.parse("audit_focal(row, seat, point, plan, source, current, full_stats)").body[0])
    for block in ast.walk(run):
        if isinstance(getattr(block, "body", None), list):
            block.body = [node for node in block.body if not isinstance(node, ast.FunctionDef) or node.name != "force_record"]
    arm_loop = next(node for node in ast.walk(run) if isinstance(node, ast.For) and
                    isinstance(node.target, ast.Tuple) and [x.id for x in node.target.elts] == ["arm", "forced_key"])
    arm_loop.target = ast.Name("arm", ast.Store())
    arm_loop.iter = ast.parse('("parent", "candidate")', mode="eval").body
    arm_loop.body[:0] = ast.parse('''arm_source = source_text if arm == "parent" else candidate_source
arm_runtime = native if arm == "parent" else None
arm_identity = source["candidate_identity"] if arm == "parent" else plan["candidate_identity"]''').body
    replace('''focal_policy = RouteVipHeuristicPolicy(params.rule_config, source=source_text,
    max_operations=params.max_operations, projection_limits=params.projection_limits, compiled_runtime=native)''',
        '''focal_policy = RouteVipHeuristicPolicy(params.rule_config, source=arm_source,
    max_operations=params.max_operations, projection_limits=params.projection_limits, compiled_runtime=arm_runtime)
if hashlib_source(focal_policy.executor.source) != arm_identity["source_sha256"]:
    raise ValueError("实际本家执行器源码身份不同")''')
    audited = next(node for node in ast.walk(run) if isinstance(node, ast.Assign) and
                   len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "audited")
    audited.value.args[1] = ast.parse('"vip:" + arm_identity["candidate_id"]', mode="eval").body
    replace('''forced = ForceFirstActionPolicy(audited, target_window=window_key_from_json(point["window_key"]),
    forced_action_key=forced_key, policy_id="t199-force-common-P0:" + arm)''', '')
    replace('policies[seat] = FirstReceipt(forced, force_record)', 'policies[seat] = audited')
    replace('''if outcome.status != "complete" or outcome.completed_hands != 8 or forced.force_count != 1:
        raise ValueError("未到完整余桌末/强制首动作不为一次")''',
        '''if outcome.status != "complete" or outcome.completed_hands != 8 or full_stats[f"{sample}:{arm}"]["first_windows"] != 1:
    raise ValueError("未到完整R8终点或首窗完整真实choose不为一次")''')
    replace('forced_key if first_action else delegate["selected_action_key"]',
            'delegate["selected_action_key"]', expression=True)
    replace('''reasons = tuple(reason for reason in decision.degraded_reasons
    if not (first_action and reason == "offline_counterfactual_force_first:" + forced_key))''',
        'reasons = tuple(decision.degraded_reasons)')
    replace('''arm_records = records[before:]''', '''arm_records = records[before:]
check_density(arm_records, seat, full_stats[f"{sample}:{arm}"])''')
    # 原结算/对账照旧；结果标注实际完整策略身份，forced计数恒为零。
    for node in ast.walk(run):
        if isinstance(node, ast.Dict):
            keys = [key.value if isinstance(key, ast.Constant) else None for key in node.keys]
            if "force_count" in keys and "settlements" in keys:
                node.values[keys.index("first_action")] = ast.parse('point["expected_first_by_arm"][arm]', mode="eval").body
                node.values[keys.index("force_count")] = ast.Constant(0)
                node.keys.extend([ast.Constant("effect_role"), ast.Constant("focal_identity"), ast.Constant("focal_audit")])
                node.values.extend([ast.Constant(ROLE), ast.Name("arm_identity", ast.Load()),
                                    ast.parse('dict(full_stats[f"{sample}:{arm}"])', mode="eval").body])
            if "schema" in keys and "forced_first_rows" in keys:
                node.values[keys.index("schema")] = ast.Constant("t200-full-policy-point-close/1")
                node.keys.extend([ast.Constant("effect_role"), ast.Constant("full_policy_audit"), ast.Constant("candidate_identity")])
                node.values.extend([ast.Constant(ROLE), ast.Name("full_stats", ast.Load()),
                                    ast.parse('plan["candidate_identity"]', mode="eval").body])
    replace('''if point["same_action_negative_control"] and results[-2]["settlements"] != results[-1]["settlements"]:
        raise ValueError("同动作负控两臂结算不同，批次失效")''', '')
    ast.fix_missing_locations(tree)
    # 按臂固定源码之外的规则、RNG世界、对手和resume_match调用均未替换。
    changes.append({"structural": "remove FirstReceipt/force_record; per-arm source/runtime/SID; inject focal audit/density; result role; remove first-only equal-outcome control"})
    return tree, names, changes


def hashlib_source(source):
    """真实装配的纯源码摘要；不读取模拟世界。"""
    return hashlib.sha256(source.encode()).hexdigest()


def candidate_material(plan, params):
    """激活原运行根后验真实候选字节及完整身份，任何World前完成。"""
    old = tiny.legacy()
    path = Path(plan["candidate_package_path"]) / "candidate.py"
    if old.pin(path) != plan["candidate_source_pin"]:
        raise ValueError("完整候选源码漂移")
    source = path.read_text()
    if params.identity(source) != plan["candidate_identity"]:
        raise ValueError("完整候选运行源/规则/参数身份不同")
    return source


def audit_focal(row, seat, point, plan, source, current, stats):
    """每窗硬核真实评分SID和密度；首窗核同公开输入及完整机械向量。"""
    if row["seat"] != seat:
        return
    arm, sample = current["arm"], current["sample"]
    identity = source["candidate_identity"] if arm == "parent" else plan["candidate_identity"]
    if row["policy_id"] != "vip:" + identity["candidate_id"]:
        raise ValueError("全程本家SID不是此臂完整候选")
    calls = row.get("scoring_calls", [])
    if not (row["status"] == "chosen" and row["c_self_scored"] and len(calls) == 1 and
            calls[0]["actual_score_calls"] == 1 and calls[0]["full_legal_keys"] and calls[0]["score_completed"]):
        raise ValueError("完整策略本家choose没有恰一次合法全根评分")
    state = stats.setdefault(f"{sample}:{arm}", {"candidate_id": identity["candidate_id"],
        "source_sha256": identity["source_sha256"], "compiled_runtime": "published_P0" if arm == "parent" else None,
        "choose_windows": 0, "score_calls": 0, "first_windows": 0})
    state["choose_windows"] += 1
    state["score_calls"] += 1
    if state["choose_windows"] == 1 and row["window_key"] != point["window_key"]:
        raise ValueError("此臂第一本家choose不是冻结起点")
    if row["window_key"] == point["window_key"]:
        vector = sorted(({"action_key": e["action_key"], "score": e["score"], "trace": e["trace"].get("detail", e["trace"])}
                         for e in row["candidates"]), key=lambda e: (-e["score"], e["action_key"]))
        if (row["observation"] != point["observation"] or row["legal_action_keys"] != point["legal_action_keys"] or
                calls[0]["input_capture"]["view_sha256"] != point["view_sha256"] or
                row["selected_action_key"] != point["expected_first_by_arm"][arm] or
                tiny.legacy().canonical(vector) != tiny.legacy().canonical(point["mechanical_entries_by_arm"][arm])):
            raise ValueError("此臂真实首choose与已闭同源全图/全向量/首选不同")
        state["first_windows"] += 1


def check_density(records, seat, stats):
    """本臂所有实际本家choose均有独立完整score；同首动作不要求同结局。"""
    focal = [record for record in records if record["row"]["seat"] == seat]
    if not (len(focal) == stats["choose_windows"] == stats["score_calls"] and stats["first_windows"] == 1):
        raise ValueError("完整候选的实际choose/score分母不闭")


def prepare(args):
    """仅复核两预声明起点、已闭机械证据和源码装载；不恢复或采样World。"""
    sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))
    from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents
    old = tiny.legacy()
    batch = VipEohBatch.read(STAGE / "AUTHOR-BATCH-001.json")
    candidate = load_vip_parents([args.candidate], batch)[0]
    if candidate["identity"]["candidate_id"] != "caca39fd5a11b344aba01ff03eaddf984bfd7e84983d89b00742e33d796471b5":
        raise ValueError("本八轨迹仅绑定实际返回的Sol E1完整候选")
    closed = old.read(args.probe / "CLOSED.json")
    if not closed["complete"] or closed.get("failures"):
        raise ValueError("前沿机械没有完整闭合")
    import json
    rows = [json.loads(line) for line in (args.probe / "RESULTS.jsonl").read_text().splitlines()]
    files, points, source = {}, [], None
    for folder, label, mother, table, target in FIXED:
        original, bindings, current_source, source_files = tiny.source_material(STAGE / folder / "ORIGIN-BINDINGS.json")
        if source is not None and current_source["candidate_identity"] != source["candidate_identity"]:
            raise ValueError("两起点父身份不同")
        source = current_source
        files.update(source_files)
        matches = [p for p in bindings["points"] if p["case_id"] == label]
        if len(matches) != 1 or (matches[0]["mother"], matches[0]["table_no"], matches[0]["target_row"]) != (mother, table, target):
            raise ValueError("预声明起点漂移")
        point = dict(matches[0])
        vectors, choices = {}, {}
        for arm, identity in (("parent", source["candidate_identity"]), ("candidate", candidate["identity"])):
            repeated = [r for r in rows if r.get("label") == label and r.get("candidate_id") == identity["candidate_id"]]
            if (len(repeated) != 2 or {r["repeat"] for r in repeated} != {0, 1} or
                    any(r["status"] != "scored" or r["score_calls"] != 1 or r["view_sha256"] != point["view_sha256"] or
                        not r["typed_JSON_exact_input"] for r in repeated) or repeated[0]["entries"] != repeated[1]["entries"]):
                raise ValueError("首窗没有两次真实完整同输入机械评分:" + label + ":" + arm)
            vectors[arm] = repeated[0]["entries"]
            if sorted(e["action_key"] for e in vectors[arm]) != sorted(point["legal_action_keys"]):
                raise ValueError("首窗机械未覆盖全部合法根")
            choices[arm] = sorted(vectors[arm], key=lambda e: (-e["score"], e["action_key"]))[0]["action_key"]
        point.update(point_no=len(points) + 1, prefix_file=point["source_origin"]["raw_paths"]["decisions.jsonl.gz"],
            expected_first_by_arm=choices, mechanical_entries_by_arm=vectors,
            same_first_action_not_same_policy_control=choices["parent"] == choices["candidate"])
        points.append(point)
    tree, names, changes = derived_driver()
    if any(not hasattr(old, name) for name in names if name != "checked_plan"):
        raise ValueError("原driver共同helper缺失")
    for path in (Path(__file__), args.probe / "CLOSED.json", args.probe / "RESULTS.jsonl",
                 args.candidate / "candidate.py", args.candidate / "generation.json"):
        files[str(path.resolve())] = old.pin(path)
    template = old.read(tiny.TEMPLATE)
    measurement_path = _project_file(_PROJECT_ROOT, ROOT / ".private/t199-four-step-execution/p0-impact-32-attempt-004/PLAN.json")
    gate = old.measurement_gate(source, measurement_path)
    files[str(measurement_path)] = old.pin(measurement_path)
    files[gate["helper_path"]] = gate["helper_pin"]
    out = Path(args.out).resolve()
    if not out.is_relative_to(OUT.resolve()) or out == OUT.resolve():
        raise ValueError("输出须为独立T200 full-followup新目录")
    out.mkdir(parents=True, exist_ok=False)
    derived = ast.unparse(tree) + "\n"
    (out / "REUSED-DRIVER.py").write_text(derived)
    files[str(out / "REUSED-DRIVER.py")] = old.pin(out / "REUSED-DRIVER.py")
    plan = {"schema": "t200-full-policy-continuation-plan/1", "effect_role": ROLE,
        "candidate_package_path": str(args.candidate.resolve()), "candidate_identity": candidate["identity"],
        "candidate_source_pin": old.pin(args.candidate / "candidate.py"), "parent_identity": source["candidate_identity"],
        "source_impact_plan": str(Path(STAGE / FIXED[0][0] / "ORIGIN-BINDINGS.json")),
        "points": points, "max_continuations": 8, "compatible_samples_per_point": 2, "sampler_version": SAMPLER,
        "slot_paths": source["slot_paths"], "measurement_gate": gate, "files": files,
        "driver_snapshot_path": str(out / "REUSED-DRIVER.py"), "selection_failures": [],
        "World_tables_API": 0, "effects_auto_dispatch": False, "first_action_forced": False,
        "same_first_action_requires_same_outcome": False, "complete_candidate_applies_after_first": True,
        "mechanical_probe_path": str(args.probe.resolve())}
    origins = old.read(STAGE / FIXED[0][0] / "ORIGIN-BINDINGS.json")
    plan.update(source_impact_plan=origins["source_plan_path"], source_impact_plan_pin=old.pin(origins["source_plan_path"]),
                source_origin_manifest=origins["source_composite_path"])
    for key in ("capture_limits", "logical_now", "max_all_seat_choose_windows_per_point", "max_focal_scores_per_point",
                "step_limit_per_continuation", "wall_seconds_per_point"):
        plan[key] = template[key]
    plan["binding_id"] = hash_value(plan)
    old.verify_files(files)
    old.save(out / "RUN-PLAN.json", plan)
    old.save(out / "AST-CHANGES.json", {"changes": changes, "original_driver_pin": old.pin(tiny.OLD / "run_point.py"),
        "derived_driver_pin": old.pin(out / "REUSED-DRIVER.py"), "original_rules_recovery_sampler_resume_match_unchanged": True})
    old.save(out / "PREPARED.json", {"complete": True, "plan_pin": old.pin(out / "RUN-PLAN.json"),
        "binding_id": plan["binding_id"], "scores_World_tables_API": 0, "max_continuations": 8,
        "effect_role": ROLE, "first_choices": [p["expected_first_by_arm"] for p in points],
        "approval_required": {"approved_for_t200_full_policy": True, "plan_pin": old.pin(out / "RUN-PLAN.json"),
            "binding_id": plan["binding_id"], "candidate_id": candidate["identity"]["candidate_id"],
            "candidate_source_pin": plan["candidate_source_pin"], "sampler_version": SAMPLER,
            "allowed_points": [1, 2], "max_remaining_table_continuations": 8}})
    return {"complete": True, "plan": str(out / "RUN-PLAN.json"), "scores_World_tables_API": 0, "max_continuations": 8}


def checked_plan(path):
    """完整策略另schema/role，复用原真实成功来源与四轨迹费用约束。"""
    old = tiny.legacy()
    plan = old.read(path)
    if (plan["schema"] != "t200-full-policy-continuation-plan/1" or plan["effect_role"] != ROLE or
            len(plan["points"]) != 2 or plan["max_continuations"] != 8 or plan["sampler_version"] != SAMPLER or
            plan["first_action_forced"] or not plan["complete_candidate_applies_after_first"]):
        raise ValueError("不是两独立起点八轨迹完整策略冻结计划")
    old.verify_files(plan["files"])
    if hash_value({key: value for key, value in plan.items() if key != "binding_id"}) != plan["binding_id"]:
        raise ValueError("完整策略续打绑定不同")
    source, _ = old.verify_impact(plan["source_impact_plan"])
    old.composite_origins(plan["source_impact_plan"], plan["source_origin_manifest"])
    if source["candidate_identity"] != plan["parent_identity"] or old.pin(plan["source_impact_plan"]) != plan["source_impact_plan_pin"]:
        raise ValueError("完整策略参照不是当前P0成功来源")
    return plan, source


def execute(args):
    """精确根收据后仅注入旧helper及本装配核验，再调用派生原run。"""
    if any(name == "hangma_bot" or name.startswith("hangma_bot.") for name in sys.modules):
        raise ValueError("execute须干净进程，不能混载main")
    old = tiny.legacy()
    plan, _ = checked_plan(args.plan)
    approval = old.read(args.approval)
    if (approval.get("candidate_id") != plan["candidate_identity"]["candidate_id"] or
            approval.get("candidate_source_pin") != plan["candidate_source_pin"] or approval.get("sampler_version") != SAMPLER):
        raise ValueError("缺完整候选／相容采样的精确根收据；0World")
    if not Path(args.output).resolve().is_relative_to(OUT.resolve()):
        raise ValueError("执行输出只允许独立full-followup目录")
    tree, names, _ = derived_driver()
    if Path(plan["driver_snapshot_path"]).read_text() != ast.unparse(tree) + "\n":
        raise ValueError("派生driver不是已冻结的必要AST装配差异")
    module = types.ModuleType("_t200_full_policy_original_driver")
    module.__file__ = plan["driver_snapshot_path"]
    module.__dict__.update({name: checked_plan if name == "checked_plan" else getattr(old, name) for name in names})
    module.__dict__.update(candidate_material=candidate_material, hashlib_source=hashlib_source,
        audit_focal=audit_focal, check_density=check_density)
    sys.modules[module.__name__] = module
    exec(compile(tree, plan["driver_snapshot_path"], "exec"), module.__dict__)
    asyncio.run(module.run(args))
    return {"complete": True, "point": args.point, "effect_role": ROLE}


def main():
    """默认仅prepare；不会自动打开轨迹、自然桌赛或发布入口。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=("prepare", "execute"), default="prepare")
    parser.add_argument("--candidate", type=Path, default=CANDIDATE)
    parser.add_argument("--probe", type=Path, default=PROBE)
    parser.add_argument("--out", type=Path, default=OUT / "prepared-001")
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--point", type=int)
    parser.add_argument("--slot", type=int, default=0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args)
    else:
        if any(getattr(args, field) is None for field in ("plan", "approval", "point", "output")):
            parser.error("execute须--plan/--approval/--point/--output")
        result = execute(args)
    import json
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
