"""T200 第二阶段五点前沿行为筛选：父5次、单候选两重复10次，至多15评分。

默认prepare只核验并冻结现有公开捕获，0规则/评分/World/桌/API。
execute须根对精确计划及独立阶段预算的收据；不改第一阶段224次账。
持续时间为单调时钟秒，机械改选不授增强、动作时限或发布资格。
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
import gzip
import json
import math
from pathlib import Path
import signal
import sys
import time

import mechanical_probe as helper

FRONTIER = helper.STAGE / "frontier-feedback-001"
DEFAULT_OUT = helper.TOOLS / "frontier-stage-002-prepared-001"
CASE_IDS = tuple(f"T200-frontier-{number:02d}" for number in range(1, 6))


def entries(rows, unwrap=False):
    """保存精确全向量并剥外层旧审计包装；不舍入、不只比较首选。"""
    return sorted(({"action_key": row["action_key"], "score": row["score"],
                    "trace": row["trace"].get("detail", row["trace"]) if unwrap else row["trace"]}
                   for row in rows),
                  key=lambda row: (-row["score"], row["action_key"]))


def prepare(output, candidate=None):
    """冻结已封五点与P0父全向量；候选可待回传后在另一新目录单独绑定。"""
    from hangma_bot.offline.vip_eoh_generate import load_vip_parents
    batch, parent = helper.current_parent()
    closed = helper.read(FRONTIER / "CLOSED.json")
    binding = helper.read(FRONTIER / "CURRENT-P0-BINDING.json")
    if (closed.get("complete") is not True or closed.get("point_count") != 5 or
            closed.get("mothers") != [1, 2, 3] or binding["candidate_identity"] != parent["identity"]):
        raise ValueError("前沿未完整闭合或不是当前精确P0父")
    files = helper.producer_files()
    for path in (Path(__file__), Path(helper.__file__), FRONTIER / "CLOSED.json",
                 FRONTIER / "CURRENT-P0-BINDING.json", helper.BATCH,
                 helper.PARENT / "generation.json", helper.PARENT / "candidate.py"):
        files[str(path.resolve())] = helper.pin(path)
    windows = []
    for label in CASE_IDS:
        path = FRONTIER / "cases" / (label + ".json")
        expected = closed["case_pins"][str(path.relative_to(FRONTIER))]
        if helper.pin(path) != expected:
            raise ValueError("已封前沿case漂移:" + label)
        case = helper.read(path)
        legal = sorted(case["legal_action_keys"])
        vector = entries(case["parent_entries"], unwrap=True)
        dto = case["public_view"]
        if (case["case_id"] != label or helper.digest(dto) != case["view_sha256"] or
                sorted(action["action_key"] for action in dto["actions"]) != legal or
                sorted(row["action_key"] for row in vector) != legal or
                any(not math.isfinite(row["score"]) for row in vector) or
                vector[0]["action_key"] != case["parent_first"] or
                any(node["gap_kind"] is not None for node in dto["nodes"])):
            raise ValueError("前沿完整图／父向量不一致:" + label)
        files[str(path.resolve())] = expected
        windows.append({"label": label, "kind": case["kind"], "mother": case["mother"],
            "case_path": str(path.resolve()), "view_sha256": case["view_sha256"],
            "legal_action_keys": legal, "parent_first": case["parent_first"], "parent_entries": vector})
    if len({window["view_sha256"] for window in windows}) != 5:
        raise ValueError("五点完整图不独立，不能重复消费评分")
    packages = [parent]
    if candidate is not None:
        candidate = Path(candidate).resolve()
        if not candidate.is_relative_to(helper.STAGE.resolve()) or candidate == helper.PARENT.resolve():
            raise ValueError("只能绑定T200内一个实际回传的候选包")
        materials = load_vip_parents([candidate], batch)
        if materials[0]["identity"]["candidate_id"] == parent["identity"]["candidate_id"]:
            raise ValueError("候选不得冒用父身份")
        packages += materials
        for name in ("generation.json", "candidate.py"):
            files[str(candidate / name)] = helper.pin(candidate / name)
    helper.verify(files)
    out = helper.new_directory(output)
    budget = {"schema": "t200-frontier-stage-budget/1", "stage": "002_frontier_behavior",
        "parent_score_calls": 5, "candidate_score_calls": 10, "maximum_score_calls": 15,
        "wall_clock_seconds": 180, "previous_stage_224_ledger_modified": False,
        "World_tables_API": 0, "effect_budget_approved": False}
    helper.save(out / "STAGE-BUDGET.json", budget)
    plan = {"schema": "t200-five-frontier-run-plan/1", "windows": windows, "window_count": 5,
        "packages": [{key: material[key] for key in ("path", "identity", "record_sha256", "source_sha256")}
                     for material in packages], "files": files,
        "budget_path": str(out / "STAGE-BUDGET.json"), "budget_pin": helper.pin(out / "STAGE-BUDGET.json"),
        "maximum_score_calls": 15, "wall_clock_seconds": 180, "candidate_repeats": 2,
        "execution_enabled": False, "candidate_binding_pending": candidate is None,
        "effects_auto_dispatch": False, "strength_deadline_release_admission": False}
    helper.save(out / "RUN-PLAN.json", plan)
    helper.save(out / "PREPARED.json", {"complete": True, "plan_pin": helper.pin(out / "RUN-PLAN.json"),
        "budget_pin": plan["budget_pin"], "candidate_binding_pending": candidate is None,
        "rule_score_World_tables_API_calls": 0, "actual_score_calls": 0,
        "approval_required": {"approved_for_t200_frontier": True,
            "plan_pin": helper.pin(out / "RUN-PLAN.json"), "stage_budget_pin": plan["budget_pin"],
            "maximum_score_calls": 15, "wall_clock_seconds": 180}})
    return {"complete": True, "plan": str(out / "RUN-PLAN.json"), "score_calls": 0,
            "candidate_binding_pending": candidate is None, "maximum_score_calls": 15}


def execute(plan_path, approval_path, output):
    """五次父精确复核先行；每点候选两重复，计入所有失败尝试且不重试。"""
    from hangma_bot.hangma.engine import HangmaRules
    from hangma_bot.kernel.observation import CompetitionContext
    from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
    from hangma_bot.policy.interface import DecisionRequest
    from hangma_bot.policy.route_vip_heuristic import build_vip_route_scoring_view
    from hangma_bot.policy.action_value_executor import ActionValueExecutor, WorkloadExceeded
    from hangma_bot.offline.vip_eoh_generate import load_vip_parents
    from hangma_bot.offline.vip_eoh_probe_v2 import validate_trace
    began = time.monotonic()
    plan_path = Path(plan_path).resolve()
    plan, approval = helper.read(plan_path), helper.read(approval_path)
    if (plan.get("schema") != "t200-five-frontier-run-plan/1" or plan["candidate_binding_pending"] or
            len(plan["packages"]) != 2 or plan["window_count"] != 5 or
            tuple(window["label"] for window in plan["windows"]) != CASE_IDS or
            plan["maximum_score_calls"] != 15 or plan["wall_clock_seconds"] != 180 or
            plan["candidate_repeats"] != 2 or approval.get("approved_for_t200_frontier") is not True or
            approval.get("plan_pin") != helper.pin(plan_path) or
            approval.get("stage_budget_pin") != plan["budget_pin"] or
            approval.get("maximum_score_calls") != 15 or approval.get("wall_clock_seconds") != 180 or
            helper.pin(plan["budget_path"]) != plan["budget_pin"]):
        raise ValueError("缺根对一个实际候选及第二阶段15次／180秒的精确批准")
    helper.verify(plan["files"])
    batch, parent = helper.current_parent()
    materials = load_vip_parents([Path(package["path"]) for package in plan["packages"]], batch)
    if materials[0]["identity"] != parent["identity"]:
        raise ValueError("父身份漂移")
    for material, frozen in zip(materials, plan["packages"]):
        if any(material[key] != frozen[key] for key in ("identity", "record_sha256", "source_sha256")):
            raise ValueError("实际候选或父包与精确计划不同")
    executors = [ActionValueExecutor(material["source"], max_operations=batch.max_operations,
                  max_local_collection_size=batch.projection_limits.max_nodes) for material in materials]
    out = helper.new_directory(output)
    helper.save(plan_path.parent / "EXECUTION-CLAIM.json", {"plan_pin": helper.pin(plan_path),
        "approval_pin": helper.pin(approval_path), "output": str(out), "one_execution_only": True})
    costs = {"rule_calls": 0, "projection_calls": 0, "score_calls": 0, "parent_score_calls": 0,
             "candidate_score_calls": 0, "World_advances": 0, "table_instances": 0, "model_calls": 0}
    helper.save(out / "START.json", {"plan_pin": helper.pin(plan_path), "approval_pin": helper.pin(approval_path),
        "stage_budget_pin": plan["budget_pin"], "packages": plan["packages"],
        "elapsed_clock": "time.monotonic_seconds", "official_deadline_claim": False})
    rules, views, parent_rows, results, failures, differences = HangmaRules(batch.rule_config), {}, {}, [], [], []

    def check_budget():
        if time.monotonic() - began >= 180 or costs["score_calls"] >= 15:
            raise TimeoutError("第二阶段评分／单调秒预算耗尽")

    def expired(signum, frame):
        raise TimeoutError("第二阶段180秒总预算耗尽")

    previous_handler = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, max(0.001, 180 - (time.monotonic() - began)))
    try:
        with (out / "RESULTS.jsonl").open("xb") as stream, gzip.open(out / "ACTUAL-VIEWS.jsonl.gz", "xb") as captures:
            for package_index, repeats in ((0, 1), (1, 2)):
                for item in plan["windows"]:
                    label, input_error = item["label"], None
                    if package_index == 0:
                        try:
                            check_budget()
                            case = helper.read(item["case_path"])
                            obs = observation_from_json(case["observation"])
                            key = window_key_from_json(case["window_key"])
                            costs["rule_calls"] += 1
                            analysis = rules.analyze(obs, route_limits=batch.route_limits)
                            if analysis.completeness.value != "complete":
                                raise ValueError("规则分析不完整")
                            legal = sorted(candidate.action_key for candidate in analysis.legal_candidates)
                            request = DecisionRequest(obs, CompetitionContext("t200-frontier", None, None, None,
                                None, (), 0), analysis, label, key.trigger_seq, key, ())
                            costs["projection_calls"] += 1
                            view = build_vip_route_scoring_view(request, batch.rule_config, limits=batch.projection_limits)
                            dto = json.loads(helper.canonical(view.candidate_view()))
                            captures.write(helper.canonical({"label": label, "view_sha256": helper.digest(dto), "view": dto}) + b"\n")
                            captures.flush()
                            if (legal != item["legal_action_keys"] or dto != case["public_view"] or
                                    helper.digest(dto) != item["view_sha256"] or any(node.gap_kind is not None for node in view.nodes)):
                                raise ValueError("真实typed tuple图与同窗P0捕获完整JSON不一致")
                            views[label] = view
                        except (Exception, WorkloadExceeded) as error:
                            input_error = {"type": type(error).__name__, "reason": str(error)}
                    elif parent_rows[label]["status"] != "scored":
                        input_error = {"type": "ParentUnclosed", "reason": "父精确复核失败，不消耗该点候选评分"}
                    repetitions = []
                    for repeat in range(repeats):
                        executor = executors[package_index]
                        row = {"label": label, "kind": item["kind"], "package_index": package_index,
                            "candidate_id": materials[package_index]["identity"]["candidate_id"], "repeat": repeat,
                            "view_sha256": item["view_sha256"], "status": "not_scored", "score_calls": 0,
                            "entries": [], "typed_JSON_exact_input": label in views}
                        tick = time.monotonic()
                        try:
                            if input_error is not None:
                                raise ValueError(input_error["reason"])
                            check_budget()
                            row["score_calls"] = 1
                            costs["score_calls"] += 1
                            costs["parent_score_calls" if package_index == 0 else "candidate_score_calls"] += 1
                            scored = executor.score_vip_route(views[label])
                            row["executor_status"] = scored.status
                            row["entries"] = entries([{"action_key": entry.action_key, "score": entry.score,
                                "trace": json.loads(helper.canonical(dict(entry.trace)))} for entry in scored.entries])
                            if scored.status != "SCORED":
                                raise ValueError("候选未完整SCORED")
                            if (sorted(entry["action_key"] for entry in row["entries"]) != item["legal_action_keys"] or
                                    any(not math.isfinite(entry["score"]) for entry in row["entries"])):
                                raise ValueError("合法根／有限评分不完整")
                            for entry in row["entries"]:
                                validate_trace(entry["trace"])
                            if helper.digest(views[label].candidate_view()) != item["view_sha256"]:
                                raise ValueError("评分改变typed输入")
                            if package_index == 0 and helper.canonical(row["entries"]) != helper.canonical(item["parent_entries"]):
                                raise ValueError("实测父精确全向量与当前P0捕获不同")
                            if time.monotonic() - began >= 180:
                                raise TimeoutError("本次评分返回时第二阶段预算已耗尽")
                            row.update(status="scored", first=row["entries"][0]["action_key"])
                        except (Exception, WorkloadExceeded) as error:
                            row.update(status="unfinished", error={"type": type(error).__name__, "reason": str(error)})
                            if input_error is not None:
                                row["input_error"] = input_error
                            failures.append({"label": label, "package_index": package_index, "repeat": repeat, **row["error"]})
                        finally:
                            row.update(counted_operations=executor.last_operation_count if row["score_calls"] else None,
                                       score_monotonic_seconds=time.monotonic() - tick)
                        repetitions.append(row)
                        results.append(row)
                        stream.write(helper.canonical(row) + b"\n")
                        stream.flush()
                    if package_index == 0:
                        parent_rows[label] = repetitions[0]
                    elif all(row["status"] == "scored" for row in repetitions):
                        if repetitions[0]["entries"] != repetitions[1]["entries"]:
                            failures.append({"label": label, "stage": "candidate_determinism"})
                        else:
                            differences.append({"label": label, "parent_first": parent_rows[label]["first"],
                                "candidate_first": repetitions[0]["first"],
                                "first_changed": parent_rows[label]["first"] != repetitions[0]["first"]})
        helper.verify(plan["files"])
    except (Exception, WorkloadExceeded) as error:
        failures.append({"stage": "execute", "type": type(error).__name__, "reason": str(error)})
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
    summary = {"schema": "t200-five-frontier-result/1", "complete": not failures and len(results) == 15,
        "plan_pin": helper.pin(plan_path), "approval_pin": helper.pin(approval_path), "costs": costs,
        "failures": failures, "differences": differences, "observed_call_rows": len(results), "planned_call_rows": 15,
        "elapsed_monotonic_seconds": time.monotonic() - began,
        "stage_budget_pin": plan["budget_pin"], "previous_stage_224_ledger_modified": False,
        "strength_deadline_release_admission": False, "effect_budget_approved": False, "effects_auto_dispatch": False}
    helper.save(out / "CLOSED.json", summary)
    return {"complete": summary["complete"], "costs": costs, "failures": len(failures), "output": str(out)}


def main():
    """默认prepare为零消耗；一个实际gen须独立prepare和根收据才能execute。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=("prepare", "execute"), default="prepare")
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--approval", type=Path)
    args = parser.parse_args()
    sys.addaudithook(helper.deny_external)
    if args.command == "prepare":
        result = prepare(args.out, args.candidate)
    else:
        if args.plan is None or args.approval is None:
            parser.error("execute须--plan及--approval")
        result = execute(args.plan, args.approval, args.out)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0 if result["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
