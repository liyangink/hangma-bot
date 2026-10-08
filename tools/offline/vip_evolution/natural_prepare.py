"""文件级派生T199首8母自然桌工具；0规则/score/World/API，执行另需根批准。"""
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
import copy
import hashlib
import json
import sys
from pathlib import Path
import tiny_followup as tiny

ROOT, STAGE = tiny.ROOT, tiny.STAGE
OLD = _project_file(_PROJECT_ROOT, ROOT / ".private/t199-four-step-execution/natural-development-tools")
T199 = OLD.parent
OUT = STAGE / "natural-development-001"
CANDIDATE = STAGE / "generation-003/sol-e1-joint-ranking"
CID = "caca39fd5a11b344aba01ff03eaddf984bfd7e84983d89b00742e33d796471b5"

FOCAL = '''"""完整候选装配；P0为环境锚，Sol全程独立受限评分。"""
from pathlib import Path
from common import pin

def build_focal(parameters,plan,native):
    """核候选字节和完整身份，再用公开策略；不冒用P0编译公式。"""
    from hangma_bot.policy.route_vip_heuristic import RouteVipHeuristicPolicy
    source=Path(plan["challenger_source"]["path"]).read_text()
    assert pin(plan["challenger_source"]["path"])==plan["challenger_source"]["pin"]
    assert parameters.identity(source)==plan["challenger_identity"]
    policy=RouteVipHeuristicPolicy(parameters.rule_config,source=source,max_operations=parameters.max_operations,
        projection_limits=parameters.projection_limits,compiled_runtime=None)
    assert policy.executor.source==source
    return policy

def check_focal_row(row,plan):
    """实际SID、全合法根、完整独立score及评分前捕获，失败不补分。"""
    import math
    assert row["policy_id"]==plan["focal_policy_id"]=="vip:"+plan["challenger_identity"]["candidate_id"]
    assert row["status"]=="chosen" and row["c_self_scored"] and len(row["scoring_calls"])==1
    call=row["scoring_calls"][0]
    assert call["actual_score_calls"]==1 and call["score_completed"] and call["full_legal_keys"] and call["status"]=="SCORED"
    assert sorted(call["scored_action_keys"])==sorted(row["legal_action_keys"])
    assert sorted(e["action_key"] for e in row["candidates"])==sorted(row["legal_action_keys"])
    assert all(math.isfinite(e["score"]) for e in row["candidates"])
    assert call["input_capture"]["status"]=="stored" and call["input_capture"]["saved_before_score"]
    row["actual_challenger_identity"]={"candidate_id":plan["challenger_identity"]["candidate_id"],
        "source_sha256":plan["challenger_identity"]["source_sha256"],"compiled_runtime":None}
'''

AUDITED = '''def audited_choices(path,closed,plan):
    """完整候选逐窗审计；无逐窗父反事实重评分，无旧同分比较器断言。"""
    from focal import check_focal_row
    count=focal_count=0;information=Counter();own=closed["task"]["focal_physical_seat"]
    with gzip.open(path,"rt") as stream:
        for line in stream:
            row=json.loads(line);count+=1
            assert row["status"]=="chosen" and row["selected_action_key"] in row["legal_action_keys"]
            assert row["original_reasons_preserved"] and not row["true_degradation_reasons"]
            assert not true_degradations(row["degraded_reasons"],row["policy_id"],plan,focal=row["seat"]==own,observation=row["observation"])
            obs=row["observation"]
            assert all(event["seq"]<=obs["consumed_seq"] for event in obs["public_history"])
            assert all(not event["tiles"] for event in obs["public_history"] if event["kind"]=="tile_drawn" and event["seat"]!=obs["seat"])
            if row["seat"]!=own:information.update(row["degraded_reasons"]);continue
            check_focal_row(row,plan);focal_count+=1
    assert count==closed["all_seat_window_count"] and focal_count==closed["focal_score_calls"]
    return count,focal_count,[],Counter({"full_challenger_policy":focal_count}),information
'''


def materialize(out):
    """仅常量、焦点装配与审计做必要AST变化；原worker/controller无变化。"""
    old = tiny.legacy()
    changes = []
    for name in ("common.py", "worker.py", "controller.py", "run_table.py", "close_natural_diagnostic.py"):
        tree = ast.parse((OLD / name).read_text())
        original = ast.dump(tree, include_attributes=False)
        if name == "common.py":
            for node in tree.body:
                if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "STAGE":
                    node.value = ast.parse(f"Path({str(T199)!r})", mode="eval").body
            approved = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "execution_approved")
            approved.body.append(ast.parse('assert approval.get("challenger_id")==plan["challenger_identity"]["candidate_id"]').body[0])
        if name == "run_table.py":
            imp = next(n for n in tree.body if isinstance(n, ast.ImportFrom) and n.module == "focal")
            imp.names.append(ast.alias("check_focal_row"))
            record = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "record")
            record.body.insert(2, ast.parse('if row["seat"]==task["focal_physical_seat"]:\n    check_focal_row(row,plan)').body[0])
            run = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "run")
            assertion = ast.parse('assert all(decision.window_key==row["window_key"] and decision.action_key==row["selected_action_key"] for decision,row in zip(outcome.decisions,rows))').body[0]
            try_block = next(n for n in run.body if isinstance(n, ast.Try))
            try_block.body.insert(-1, assertion)
            for node in ast.walk(tree):
                if isinstance(node, ast.Dict):
                    keys = [k.value if isinstance(k, ast.Constant) else None for k in node.keys]
                    if "schema" in keys and "natural_full_table" in keys:
                        node.values[keys.index("schema")] = ast.Constant("t200-full-candidate-natural-table/1")
                        node.keys += [ast.Constant("challenger_identity"), ast.Constant("environment_identity")]
                        node.values += [ast.parse('plan["challenger_identity"]', mode="eval").body, ast.parse('plan["candidate_identity"]', mode="eval").body]
        if name == "close_natural_diagnostic.py":
            tree.body = [ast.parse(AUDITED).body[0] if isinstance(n, ast.FunctionDef) and n.name == "audited_choices" else n for n in tree.body]
            main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
            for block in ast.walk(main):
                if isinstance(getattr(block, "body", None), list):
                    block.body = [n for n in block.body if not (isinstance(n, ast.Assert) and "t199_natural_comparator" in ast.unparse(n))]
            for node in ast.walk(main):
                if isinstance(node, ast.Constant) and node.value == "A-H0":
                    node.value = "Sol-E1-full"
                if isinstance(node, ast.Tuple) and [getattr(e, "value", None) for e in node.elts] == ["runtime_policy", "t199_natural_comparator", "t199_natural_measurement"]:
                    node.elts = [ast.Constant("t199_natural_measurement")]
                if isinstance(node, ast.Dict):
                    keys = [k.value if isinstance(k, ast.Constant) else None for k in node.keys]
                    if "schema" in keys and "paired_mother_summary" in keys:
                        node.values[keys.index("schema")] = ast.Constant("t200-Sol-full-first8-natural-development/1")
                        for key, expr in (("challenger_identity", 'plan["challenger_identity"]'), ("investment_policy", 'plan["investment_policy"]')):
                            node.keys.append(ast.Constant(key)); node.values.append(ast.parse(expr, mode="eval").body)
                        node.keys += [ast.Constant("whole_challenger_choose"), ast.Constant("next_budget_granted")]
                        node.values += [ast.Constant(True), ast.Constant(False)]
                    if "actual_loaded_comparator" in keys:
                        node.values[keys.index("actual_loaded_comparator")] = ast.Constant(None)
            final_save = next(n for n in main.body if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call) and getattr(n.value.func, "id", None) == "save")
            index = main.body.index(final_save)
            main.body[index:index] = ast.parse('''positive=sum(value>0 for value in net_mothers)
without_best=(sum(net_mothers)-max(net_mothers))/7
summary["investment_readback"]={"mean_delta_per_table":estimate,"rough_target_per_table":8.0,"positive_mothers":positive,
    "leave_best_mother_out_mean":without_best,"single_source_dependency":without_best<=0,
    "clear_signal_screen_met":estimate>=8.0 and positive>=5 and without_best>0,
    "default_if_weak":"stop this version effect expansion; return to evolution","automatic_expansion_or_confirmation":False}''').body
        ast.fix_missing_locations(tree)
        compile(tree, str(out / name), "exec")
        (out / name).write_text(ast.unparse(tree) + "\n")
        changes.append({"name": name, "original_pin": old.pin(OLD / name), "unchanged_AST": original == ast.dump(tree, include_attributes=False)})
    (out / "focal.py").write_text(FOCAL)
    compile(FOCAL, str(out / "focal.py"), "exec")
    return changes


def main():
    """仅创建新计划并核成功32个参考及源码；不导入hangma或打开执行入口。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    out = parser.parse_args().out.resolve()
    if not out.is_relative_to(STAGE.resolve()) or out == STAGE.resolve():
        raise ValueError("须为T200新隔离目录")
    old = tiny.legacy()
    composite = T199 / "p0-impact-32-attempt-004/COMPOSITE-ORIGINS.json"
    reference_path = T199 / "p0-impact-32-attempt-003/PLAN.json"
    reference, tables, files, _ = old.composite_origins(reference_path, composite)
    measurement_path = T199 / "p0-impact-32-attempt-004/PLAN.json"
    measurement = old.read(measurement_path)
    identity = old.read(CANDIDATE / "generation.json")["identity"]
    assert identity["candidate_id"] == CID and identity["params"] == reference["candidate_identity"]["params"]
    assert identity["deps_digest"] == reference["candidate_identity"]["deps_digest"]
    assert identity["source_manifest"] == reference["candidate_identity"]["source_manifest"]
    assert old.pin(CANDIDATE / "candidate.py")["sha256"] == identity["source_sha256"]
    assert measurement["candidate_identity"] == reference["candidate_identity"] and measurement["runtime_files"] == reference["runtime_files"]
    out.mkdir(parents=True, exist_ok=False)
    changes = materialize(out)
    original = old.read(OLD / "PLAN.json")
    plan = copy.deepcopy(reference)
    paths = [Path(__file__), CANDIDATE / "candidate.py", CANDIDATE / "generation.json", measurement_path,
        T199 / "joint-continuation/common.py", STAGE / "natural-interface-preparation-001/README.md", STAGE / "full-followup/AGGREGATE-001.json"]
    names = ("common.py", "focal.py", "worker.py", "controller.py", "run_table.py", "close_natural_diagnostic.py")
    paths += [out / name for name in names] + [OLD / name for name in names]
    files.update(measurement["files"])
    files.update({str(p.resolve()): old.pin(p) for p in paths})
    challenger_source = {"path": str((CANDIDATE / "candidate.py").resolve()), "pin": old.pin(CANDIDATE / "candidate.py")}
    plan.update(schema="t200-first8-full-challenger-natural-development/1", purpose="Sol完整策略首8母32child开发；弱停，不确认",
        output_directory=str(out), reference_plan_path=str(reference_path), reference_plan_pin=old.pin(reference_path),
        composite_origins_path=str(composite), composite_origins_pin=old.pin(composite), composite_references={str(k): v for k, v in tables.items()},
        measurement_plan_path=str(measurement_path), measurement_plan_pin=old.pin(measurement_path),
        informational_reason_allowlist_by_policy_id=measurement["informational_reason_allowlist_by_policy_id"],
        informational_reason_evidence=measurement["informational_reason_evidence"], files=files,
        challenger_identity=identity, challenger_source=challenger_source, selected_variant="Sol-E1-full", selected_source=challenger_source,
        comparator={"path": "none_full_formula_no_root_comparator", "pin": None},
        parent_execution_id=reference["compiled_runtime"]["manifest"]["original_execution_id"],
        pilot_ordinals=[0], remaining_ordinals=list(range(1, 32)), planned_table_instances=32, planned_completed_hands=256,
        actual_new_planned_table_instances=32, worker_count=4, requested_nice=19, requested_low_IO=3,
        strength_admission=False, original_deadline_admitted=False, main_changed=False, natural_choose_each_window=True,
        forced_first_actions=0, single_arm=True, reference_only_no_parent_rescores=True, pilot_reused_never_repeated=True,
        expansion_16_32_or_confirmation_allowed=False, retry_failed_table_allowed=False, record_costs_actual=True,
        prepare_business_import_rule_score_world_table_API_calls=0,
        investment_policy={"rough_target_net_delta_per_table": 8.0, "independent_unit": "8mothers; each four rotations",
            "positive_mothers_screen_minimum": 5, "leave_best_mother_out_positive_required": True,
            "mother_debits": "ordinary/high-fan/payment/dealer/nondealer; retain reverse losses",
            "weak_signal_action": "stop version expansion and return to evolution", "automatic_16_32_or_confirmation": False,
            "engineering_screen_not_p_value_or_release": True})
    for key in ("clock_mode", "logical_now", "wall_seconds_per_table", "step_limit_per_table", "capture_limits"):
        plan[key] = original[key]
    plan["binding_id"] = hashlib.sha256(old.canonical(plan)).hexdigest()
    plan["focal_policy_id"] = "vip:" + CID
    plan["binding_digest_excludes"] = ["binding_id", "focal_policy_id", "binding_digest_excludes"]
    old.verify_files(files)
    assert len(plan["tasks"]) == 32 and {task["root"] for task in plan["tasks"]} == set(range(1, 9))
    for task in plan["tasks"]:
        assert tables[task["table_no"]]["task"] == task
    assert not any(name == "hangma_bot" or name.startswith("hangma_bot.") for name in sys.modules)
    old.save(out / "PLAN.json", plan)
    old.save(out / "AST-CHANGES.json", {"changes": changes, "focal": "public full policy; compiledNone; exact challenger identity",
        "original_rule_drive_match_sampler_opponents": True, "scores_World_API": 0})
    old.save(out / "FILE-ONLY-CLOSED.json", {"complete": True, "plan_pin": old.pin(out / "PLAN.json"), "binding_id": plan["binding_id"],
        "candidate_identity_environment_anchor": plan["candidate_identity"]["candidate_id"], "challenger_id": CID,
        "new_child_tables": 32, "reused_parent_tables": 32, "actual_scores_rules_World_API": 0, "actual_hangma_modules": 0,
        "worker_count": 4, "nice": 19, "reference_origins_attempt003": 24, "reference_origins_attempt004": 8,
        "approval_required": {"approved_for_natural_pilot": True, "approved_for_remaining_natural_development": True,
            "plan_pin": old.pin(out / "PLAN.json"), "binding_id": plan["binding_id"], "selected_variant": "Sol-E1-full", "challenger_id": CID,
            "max_new_tables": 32, "pilot_ordinals": [0], "remaining_ordinals": list(range(1, 32))}, "dispatch_started": False})
    print(json.dumps({"complete": True, "plan": str(out / "PLAN.json"), "plan_pin": old.pin(out / "PLAN.json"),
        "binding_id": plan["binding_id"], "scores_World_API": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
