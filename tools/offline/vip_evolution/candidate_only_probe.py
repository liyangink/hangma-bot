"""T200 cache12 的候选单独探针；复用已实测父向量，不重评分父代。

prepare/validate 为0评分绑定。execute 要求根批准精确计划，只使用生产
typed规则/投影与原受限执行器，每窗候选两次，完整分母24次评分。
持续时间是单调秒；不调用模型，不恢复WorldState，不跑桌或授效果准入。
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
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
STAGE = _project_file(_PROJECT_ROOT, '.private/t200-eoh-fast-evolution')
sys.path.insert(0, str(HERE))
from make_cache_panel import load_file, tools, validate_windows

PANEL = _project_file(_PROJECT_ROOT, '.private/t200-eoh-fast-evolution/mechanical-tools/cache-panel-001/PANEL.json')
CACHE_PLAN = _project_file(_PROJECT_ROOT, '.private/t200-eoh-fast-evolution/mechanical-tools/cache-binding-001/RUN-PLAN.json')
CACHE = _project_file(_PROJECT_ROOT, '.private/t200-eoh-fast-evolution/mechanical-tools/cache-run-001')
DEFAULT_CANDIDATE = _project_file(_PROJECT_ROOT, '.private/t200-eoh-fast-evolution/generation-001/e1-natural-explore-R1')
E1_ID = "dead70da6a872ac501c57093c81eda05ce9f28ee31ad9cb58f871062fd40b9d0"


def reference_rows(core, panel):
    """复核真实cache父重复与完整输入；只读既有24父评分，不重新计算。"""
    closed, start = core.read(_project_file(_PROJECT_ROOT, CACHE / "CLOSED.json")), core.read(_project_file(_PROJECT_ROOT, CACHE / "START.json"))
    if (closed["complete"] is not True or closed["failures"] or
        closed["plan_pin"] != core.pin(CACHE_PLAN) or start["plan_pin"] != closed["plan_pin"] or
        closed["costs"]["score_calls"] != 48):
        raise ValueError("cache12原实测没有完整闭合")
    views = {}
    with gzip.open(_project_file(_PROJECT_ROOT, CACHE / "ACTUAL-VIEWS.jsonl.gz"), "rt") as stream:
        for line in stream:
            row = json.loads(line)
            if core.digest(row["view"]) != row["view_sha256"]:
                raise ValueError("cache实测完整图SHA不同")
            views[row["label"]] = row
    grouped = {}
    with (_project_file(_PROJECT_ROOT, CACHE / "RESULTS.jsonl")).open() as stream:
        for line in stream:
            row = json.loads(line)
            if row["package_index"] == 0:
                grouped.setdefault(row["label"], []).append(row)
    references = {}
    for window in panel["windows"]:
        label = window["label"]
        rows = grouped[label]
        view = views[label]
        if (len(rows) != 2 or {r["repeat"] for r in rows} != {0, 1} or
            rows[0]["entries"] != rows[1]["entries"] or
            view["view_sha256"] != window["captured_view_sha256"] or view["view"] != window["captured_view"]):
            raise ValueError("cache原父两重复/实测typed图不同")
        for row in rows:
            if (row["candidate_id"] != panel["parent_identity"]["candidate_id"] or
                row["status"] != "scored" or row["score_calls"] != 1 or
                row["typed_JSON_exact_input"] is not True or row["view_sha256"] != view["view_sha256"]):
                raise ValueError("cache父原评分身份或完整性不同")
        if ({e["action_key"]: e["score"] for e in rows[0]["entries"]} !=
            {e["action_key"]: e["score"] for e in window["parent_entries"]}):
            raise ValueError("cache父精确向量与面板原件不同")
        references[label] = rows[0]
    return references


def prepare(candidate, output):
    """冻结新候选、cache父实测与当前12图，原费用留存，0评分。"""
    from hangma_bot.offline.vip_eoh_generate import load_vip_parents
    core = tools()
    panel, batch, parent = core.checked_panel(PANEL)
    validate_windows(panel, core)
    references = reference_rows(core, panel)
    material = load_vip_parents([candidate], batch)[0]
    if material["identity"]["candidate_id"] != E1_ID:
        raise ValueError("本轮仅绑定已指定E1-R1")
    files = {**panel["files"], str(PANEL): core.pin(PANEL), str(CACHE_PLAN): core.pin(CACHE_PLAN)}
    for path in (Path(__file__).resolve(), _project_file(_PROJECT_ROOT, HERE / "make_cache_panel.py"), candidate / "generation.json",
                 candidate / "candidate.py", *(_project_file(_PROJECT_ROOT, CACHE / name) for name in
                 ("START.json", "CLOSED.json", "RESULTS.jsonl", "ACTUAL-VIEWS.jsonl.gz"))):
        files[str(path.resolve())] = core.pin(path)
    prior = (_project_file(_PROJECT_ROOT, STAGE / "mechanical-tools/baseline-check-001/CLOSED.json"),
             _project_file(_PROJECT_ROOT, STAGE / "mechanical-tools/run-001/CLOSED.json"), _project_file(_PROJECT_ROOT, CACHE / "CLOSED.json"),
             _project_file(_PROJECT_ROOT, STAGE / "mechanical-tools/e1-run-001/CLOSED.json"))
    counts = []
    for path in prior:
        row = core.read(path)
        if row["complete"] is not True:
            raise ValueError("此前计费原件未闭")
        files[str(path)] = core.pin(path)
        counts.append(row.get("costs", row.get("counts"))["score_calls"])
    known_prior = sum(counts)
    if known_prior != 200 or known_prior + 24 > 240:
        raise ValueError("不是当前200评分账或追加24超过上限")
    core.verify(files)
    out = core.new_directory(output)
    core.save(out / "REFERENCES.json", references)
    files[str(out / "REFERENCES.json")] = core.pin(out / "REFERENCES.json")
    plan = {"schema": "t200-candidate-only-cache-plan/1", "panel_path": str(PANEL),
        "candidate_path": str(candidate.resolve()), "candidate_identity": material["identity"],
        "candidate_record_sha256": material["record_sha256"], "parent_identity": parent["identity"],
        "reference_rows_path": str(out / "REFERENCES.json"), "files": files,
        "window_count": 12, "repeats": 2, "planned_candidate_scores": 24, "parent_scores": 0,
        "prior_known_score_calls": known_prior, "cumulative_after_planned": known_prior + 24,
        "cumulative_ceiling": 240, "wall_clock_seconds": 180, "execution_enabled": False,
        "World_tables_API": 0, "automatic_effect_dispatch": False}
    core.save(out / "RUN-PLAN.json", plan)
    core.save(out / "PREPARED.json", {"complete": True, "plan_pin": core.pin(out / "RUN-PLAN.json"),
        "candidate_id": E1_ID, "cached_real_parent_vectors": 12, "planned_candidate_scores": 24,
        "actual_scores_rules_World_tables_API": 0, "parent_loader_entries": 1,
        "candidate_loader_entries": 1, "known_prior_scores": known_prior, "planned_cumulative": known_prior + 24})
    return {"complete": True, "plan": str(out / "RUN-PLAN.json"), "plan_pin": core.pin(out / "RUN-PLAN.json"),
            "planned_candidate_scores": 24, "actual_scores_rules_World_tables_API": 0}


def checked(plan_path):
    """首尾精确冻结和当前候选装载；构造不是评分。"""
    from hangma_bot.offline.vip_eoh_generate import load_vip_parents
    core = tools()
    plan = core.read(plan_path)
    if (plan["schema"] != "t200-candidate-only-cache-plan/1" or plan["planned_candidate_scores"] != 24 or
        plan["window_count"] != 12 or plan["repeats"] != 2 or plan["parent_scores"] != 0 or
        plan["prior_known_score_calls"] + 24 != plan["cumulative_after_planned"] or
        plan["cumulative_after_planned"] > 240):
        raise ValueError("不是冻结24候选评分计划")
    core.verify(plan["files"])
    panel, batch, parent = core.checked_panel(Path(plan["panel_path"]))
    validate_windows(panel, core)
    material = load_vip_parents([Path(plan["candidate_path"])], batch)[0]
    if (material["identity"] != plan["candidate_identity"] or
        material["record_sha256"] != plan["candidate_record_sha256"] or
        parent["identity"] != plan["parent_identity"]):
        raise ValueError("父/候选完整身份漂移")
    return core, plan, panel, batch, material, core.read(plan["reference_rows_path"])


def execute(plan_path, approval_path, output):
    """重建同SHA的生产typed输入，只运行候选24评分；失败保留分母，不重试父。"""
    core, plan, panel, batch, material, references = checked(plan_path)
    approval = core.read(approval_path)
    if (approval.get("approved_for_t200_candidate_only") is not True or
        approval.get("plan_pin") != core.pin(plan_path) or approval.get("maximum_score_calls") != 24):
        raise ValueError("缺根对精确候选单独24评分的批准")
    from hangma_bot.hangma.engine import HangmaRules
    from hangma_bot.kernel.observation import CompetitionContext
    from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
    from hangma_bot.policy.interface import DecisionRequest
    from hangma_bot.policy.route_vip_heuristic import build_vip_route_scoring_view
    from hangma_bot.policy.action_value_executor import ActionValueExecutor, WorkloadExceeded
    from hangma_bot.offline.vip_eoh_probe_v2 import validate_trace
    executor = ActionValueExecutor(material["source"], max_operations=batch.max_operations,
                                  max_local_collection_size=batch.projection_limits.max_nodes)
    rules = HangmaRules(batch.rule_config)
    out = core.new_directory(output)
    costs = {"rule_calls": 0, "projection_calls": 0, "candidate_score_calls": 0,
             "parent_score_calls": 0, "model_calls": 0, "World_advances": 0, "table_instances": 0}
    core.save(out / "START.json", {"plan_pin": core.pin(plan_path), "approval_pin": core.pin(approval_path),
        "candidate_id": E1_ID, "source_sha256": material["source_sha256"], "parent_score_calls": 0,
        "planned_candidate_score_calls": 24, "elapsed_clock": "time.monotonic_seconds"})
    failures, rows, differences = [], [], []
    began = time.monotonic()
    with (out / "RESULTS.jsonl").open("xb") as stream:
        for item in panel["windows"]:
            view, dto, error = None, None, None
            try:
                obs = observation_from_json(item["observation"])
                key = window_key_from_json(item["window_key"])
                costs["rule_calls"] += 1
                analysis = rules.analyze(obs, route_limits=batch.route_limits)
                if analysis.completeness.value != "complete" or sorted(c.action_key for c in analysis.legal_candidates) != item["legal_action_keys"]:
                    raise ValueError("当前完整合法根与原输入不同")
                request = DecisionRequest(obs, CompetitionContext("t200-candidate-only", None, None, None,
                    None, (), 0), analysis, item["label"], key.trigger_seq, key, ())
                costs["projection_calls"] += 1
                view = build_vip_route_scoring_view(request, batch.rule_config, limits=batch.projection_limits)
                dto = json.loads(core.canonical(view.candidate_view()))
                if dto != item["captured_view"] or core.digest(dto) != references[item["label"]]["view_sha256"]:
                    raise ValueError("候选typed完整输入与真实cache父原图不同")
                if any(node.gap_kind is not None for node in view.nodes):
                    raise ValueError("完整图有事实/计算缺口")
            except (Exception, WorkloadExceeded) as exc:
                error = {"type": type(exc).__name__, "reason": str(exc)}
                failures.append({"label": item["label"], "stage": "input", **error})
            repeated = []
            for repeat in range(2):
                row = {"label": item["label"], "candidate_id": E1_ID, "repeat": repeat,
                    "status": "unfinished", "score_calls": 0, "entries": [],
                    "view_sha256": item["captured_view_sha256"], "typed_JSON_exact_input": error is None,
                    "parent_score_calls": 0, "cached_parent_reference_id": plan["parent_identity"]["candidate_id"]}
                tick = time.monotonic()
                if error:
                    row["error"] = error
                else:
                    try:
                        if costs["candidate_score_calls"] >= 24 or time.monotonic() - began >= plan["wall_clock_seconds"]:
                            raise ValueError("固定候选评分或单调秒预算耗尽")
                        row["score_calls"] = 1
                        costs["candidate_score_calls"] += 1
                        scored = executor.score_vip_route(view)
                        if scored.status != "SCORED":
                            raise ValueError("候选没有完成SCORED")
                        entries = sorted(({"action_key": e.action_key, "score": e.score,
                             "trace": json.loads(core.canonical(dict(e.trace)))} for e in scored.entries),
                             key=lambda entry: (-entry["score"], entry["action_key"]))
                        if sorted(e["action_key"] for e in entries) != item["legal_action_keys"]:
                            raise ValueError("候选没有完整合法根评分")
                        for entry in entries:
                            validate_trace(entry["trace"])
                        if core.digest(view.candidate_view()) != row["view_sha256"]:
                            raise ValueError("候选改变typed输入")
                        row.update(status="scored", entries=entries, first=entries[0]["action_key"])
                    except (Exception, WorkloadExceeded) as exc:
                        row["error"] = {"type": type(exc).__name__, "reason": str(exc)}
                        failures.append({"label": item["label"], "repeat": repeat, **row["error"]})
                row.update(counted_operations=executor.last_operation_count,
                           score_monotonic_seconds=time.monotonic() - tick)
                rows.append(row)
                repeated.append(row)
                stream.write(core.canonical(row) + b"\n")
                stream.flush()
            if all(row["status"] == "scored" for row in repeated):
                if repeated[0]["entries"] != repeated[1]["entries"]:
                    failures.append({"label": item["label"], "stage": "determinism"})
                else:
                    row, base = repeated[0], references[item["label"]]
                    changed = row["first"] != base["first"]
                    honor = changed and core.equivalent_honor_swap(dto, base["first"], row["first"],
                        {e["action_key"]: e["score"] for e in base["entries"]},
                        {e["action_key"]: e["score"] for e in row["entries"]})
                    differences.append({"label": item["label"], "parent_first": base["first"],
                        "candidate_first": row["first"], "first_changed": changed,
                        "equivalent_honor_permutation_only": honor, "meaningful_development_change": changed and not honor})
    try:
        core.verify(plan["files"])
    except Exception as exc:
        failures.append({"stage": "final_source_pins", "type": type(exc).__name__, "reason": str(exc)})
    meaningful = sum(row["meaningful_development_change"] for row in differences)
    summary = {"schema": "t200-candidate-only-cache-result/1", "complete": not failures and len(rows) == 24,
        "plan_pin": core.pin(plan_path), "approval_pin": core.pin(approval_path), "candidate_id": E1_ID,
        "costs": costs, "failures": failures, "differences": differences, "observed_call_rows": len(rows),
        "meaningful_first_changes": meaningful, "no_change_or_only_equivalent_honors_stop_effect_budget": meaningful == 0,
        "prior_known_score_calls": plan["prior_known_score_calls"],
        "known_cumulative_score_calls": plan["prior_known_score_calls"] + costs["candidate_score_calls"],
        "elapsed_monotonic_seconds": time.monotonic() - began, "source_pins_stable": not any(f.get("stage") == "final_source_pins" for f in failures),
        "parent_exact_vectors_reused_no_rescore": True, "automatic_effect_dispatch": False,
        "effect_budget_approved": False, "strength_deadline_release_admission": False}
    core.save(out / "CLOSED.json", summary)
    return {"complete": summary["complete"], "costs": costs, "meaningful_first_changes": meaningful,
            "failures": len(failures), "known_cumulative_score_calls": summary["known_cumulative_score_calls"]}


def main():
    """候选单独24评分必须经根收据；准备不触碰动作服务或世界。"""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    prep.add_argument("--out", type=Path, default=_project_file(_PROJECT_ROOT, STAGE / "mechanical-tools/e1-cache-only-binding-001"))
    check = commands.add_parser("validate")
    check.add_argument("--plan", type=Path, required=True)
    run = commands.add_parser("execute")
    for field in ("plan", "approval", "out"):
        run.add_argument("--" + field, type=Path, required=True)
    args = parser.parse_args()
    core = tools()
    sys.addaudithook(core.deny_external)
    if args.command == "prepare":
        result = prepare(args.candidate, args.out)
    elif args.command == "validate":
        _, plan, _, _, _, _ = checked(args.plan)
        result = {"complete": True, "plan_pin": core.pin(args.plan), "planned_candidate_scores": 24,
                  "actual_scores_rules_World_tables_API": 0, "planned_cumulative": plan["cumulative_after_planned"]}
    else:
        result = execute(args.plan, args.approval, args.out)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0 if result["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
