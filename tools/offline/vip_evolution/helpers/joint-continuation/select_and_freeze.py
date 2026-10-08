"""成功P032批上按事前公开机械次序选点；不读终分，不恢复World或续打。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = '.private/t199-four-step-execution/joint-continuation'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import asyncio
from collections import Counter
import gzip
import hashlib
import time
from pathlib import Path

from common import HERE, STAGE, RUNNER, activate, canonical, composite_origins, measurement_gate, native_parent, parameters, pin, read, rows, save, verify_files, verify_impact, verify_loaded


def in_scope(row, branch):
    """只按本次公开请求廉价筛门；最终门仍由同一个完整choose确认。"""
    obs, key = row["observation"], row["window_key"]
    state = obs["rule_state"]
    if (obs["observation_issues"] or state["catch_play"] or state["baotou"] or state["chain_count"] != 0
            or obs["chain_piao"] != 0 or obs["remaining_tile_count"] is None):
        return False
    families = {k.split(":")[0] for k in row["legal_action_keys"]}
    if branch == "B":
        return key["phase"] in ("response_peng", "response_chi") and families <= {"pass", "chi", "peng"} and "pass" in families
    return (key["phase"] == "draw" and obs["phase"] == "draw" and obs["turn_seat"] == obs["seat"]
            and obs["drawn_tile"] is not None and obs["gang_draw"] is False and families == {"discard"})


def choose_points(records):
    """先各母首个改选桌，再各母第二桌；负控同上限内，母/桌限制不放宽。"""
    selected, used, mothers = [], set(), Counter()
    changes = sorted((r for r in records if r["changed"]), key=lambda r: (r["task"]["root"], r["task"]["rotation"], r["target_row"]))
    for pass_no in (1, 2):
        for mother in range(1, 9):
            if len(selected) >= 11:
                break
            choices = [r for r in changes if r["task"]["root"] == mother and r["task"]["table_no"] not in used]
            if choices and mothers[mother] < pass_no:
                item = choices[0]
                selected.append(item)
                used.add(item["task"]["table_no"])
                mothers[mother] += 1
    if selected:
        controls = sorted((r for r in records if not r["changed"] and r["task"]["table_no"] not in used
                           and mothers[r["task"]["root"]] < 2), key=lambda r: (r["task"]["root"], r["task"]["rotation"], r["target_row"]))
        if controls:
            selected.append({**controls[0], "same_action_negative_control": True})
    return selected


async def run(args):
    """输出仅在32自然桌关闭后创建；原受限源准入先于任何新规则分析。"""
    source_path = Path(args.source_plan).resolve()
    source, origins, table_files, origin_plans = composite_origins(source_path, args.origin_manifest)
    measurement = measurement_gate(source, args.measurement_plan)
    approval = read(args.approval)
    if not (approval.get("approved_for_mechanical_selection") is True
            and approval.get("source_impact_plan_pin") == pin(source_path)
            and approval.get("source_origin_manifest_pin") == pin(args.origin_manifest)
            and approval.get("measurement_plan_pin") == measurement["plan_pin"]
            and approval.get("branch") == args.branch
            and approval.get("max_new_source_scores") == 256):
        raise ValueError("缺本批冻结的256评分机械选择资源绑定；0规则/评分/续打")
    tasks = sorted(source["tasks"], key=lambda t: (t["root"], t["rotation"]))
    from binding import check_plan
    mechanical = check_plan(RUNNER / "MECHANICAL-PLAN-2.json")
    closed_mech = read(STAGE / "strategy-mechanical-interpreted-2/FILE-CLOSED.json")
    if not closed_mech["complete"] or closed_mech["binding_id"] != mechanical["binding_id"]:
        raise ValueError("H0真正机械封存缺失")
    activate(source)
    from hangma_bot import bootstrap
    from hangma_bot.hangma.engine import HangmaRules
    from hangma_bot.kernel.observation import CompetitionContext
    from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
    from hangma_bot.policy.interface import DecisionBudget, DecisionRequest
    from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
    from hangma_bot.offline.vip_route_development import VipDevelopmentAuditPolicy
    from runtime_policy import T199RoutePolicy
    from root_selection_draft import rank_root_entries
    params = parameters(source)
    sources = {name: Path(row["path"]).read_text() for name, row in mechanical["sources"].items()}
    if params.identity(sources["parent"]) != source["candidate_identity"] or sources["parent"] != bootstrap.VIP_S03_SOURCE:
        raise ValueError("H0主公式与当前P0原S03不同")
    policy = T199RoutePolicy(params.rule_config, sources=sources, params=source["candidate_identity"]["params"],
        projection_limits=params.projection_limits, variant=args.branch, binding_id=mechanical["binding_id"],
        compiled_runtimes={"parent": native_parent(source)})
    rules = HangmaRules(params.rule_config)
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    counts = {"new_rule_analyses": 0, "new_source_scores": 0, "reused_parent_root_vectors": 0,
              "candidate_choose_attempts": 0, "eligible_public_windows": 0, "historical_world_recoveries": 0, "continuations": 0, "API": 0}
    save(output / "START.json", {"source_plan_pin": pin(source_path), "approval_pin": pin(args.approval),
        "branch": args.branch, "max_new_source_scores": 256, "source_tables": 32, "source_mothers": 8})
    records, failures, scanned = [], [], []
    raw = (output / "SELECTOR-views.jsonl.gz").open("x+b")
    capture = ScoringInputCapture(raw, limits=ScoringInputCaptureLimits.from_json(source["capture_limits"]))
    audit_stream = gzip.open(output / "SELECTOR-decisions.jsonl.gz", "xb")
    current = {"table_no": None, "source_row": None}

    def audit_sink(row):
        """原受限执行器真实调用费用；图在评分前捕获，失败不按预留冒充actual。"""
        audit_stream.write(canonical({**current, "row": row}) + b"\n")
        audit_stream.flush()
        counts["new_source_scores"] += sum(c["actual_score_calls"] for c in row.get("scoring_calls", []))

    for task in tasks:
        if time.monotonic() - started > 300:
            scanned.append({"table_no": task["table_no"], "status": "selection_wall_budget_exhausted_unknown"})
            break
        origin = origins[task["table_no"]]
        views = {v["view_sha256"]: v["view"] for _, v in rows(origin["raw_paths"]["views.jsonl.gz"])}
        control = None
        for row_no, row in rows(origin["raw_paths"]["decisions.jsonl.gz"]):
            if time.monotonic() - started > 300:
                scanned.append({"table_no": task["table_no"], "status": "selection_wall_budget_exhausted_unknown"})
                break
            if row["seat"] != task["focal_physical_seat"] or not in_scope(row, args.branch):
                continue
            try:
                calls = row["scoring_calls"]
                if row["status"] != "chosen" or len(calls) != 1 or not row["c_self_scored"]:
                    raise ValueError("来源焦点不是完整真实评分")
                sha = calls[0]["input_capture"]["view_sha256"]
                view = views[sha]
                if hashlib.sha256(canonical(view)).hexdigest() != sha:
                    raise ValueError("来源完整图摘要不同")
                entries = [{"action_key": c["action_key"], "score": c["score"], "trace": c["trace"]} for c in row["candidates"]]
                parent = sorted(entries, key=lambda e: (-e["score"], e["action_key"]))
                if parent[0]["action_key"] != row["selected_action_key"]:
                    raise ValueError("原P0实际首选与原分排序不符")
                public_request = {"observation": row["observation"], "window_key": row["window_key"],
                                  "rules": {"completeness": "complete"}, "rejected_attempts": []}
                if args.branch == "A":
                    if len(parent) < 2 or parent[0]["score"] != parent[1]["score"]:
                        continue
                    counts["reused_parent_root_vectors"] += 1
                    order = rank_root_entries(public_request, view, entries)
                    chosen = order.entries[0]["action_key"]
                    trace = dict(order.trace)
                else:
                    # C只扫存在本窄信用消费者的直接根；无此事实不白做规则/评分。
                    if args.branch == "C":
                        waitings = [n["waiting"] for n in view["nodes"] if n["kind"] == "wait"]
                        if not any(w["structure"]["standard_shanten"] > 0 and w["structure"]["seven_pairs_shanten"] == 0
                                   and w["structure"]["whites_held"] in (0, 1) for w in waitings):
                            continue
                    if counts["candidate_choose_attempts"] >= 256:
                        scanned.append({"table_no": task["table_no"], "status": "budget_exhausted_unknown"})
                        break
                    counts["new_rule_analyses"] += 1
                    observation = observation_from_json(row["observation"])
                    analysis = rules.analyze(observation, route_limits=params.route_limits)
                    if analysis.completeness.value != "complete" or sorted(c.action_key for c in analysis.legal_candidates) != sorted(row["legal_action_keys"]):
                        raise ValueError("同P0重新分析合法根不同")
                    request = DecisionRequest(observation, CompetitionContext("t199-mechanism-selection", None, None, None,
                        None, (), 0), analysis, "t199-selector:" + str(row_no), row["window_key"]["trigger_seq"],
                        window_key_from_json(row["window_key"]), ())
                    counts["candidate_choose_attempts"] += 1
                    current.update(table_no=task["table_no"], source_row=row_no)
                    policy.executor = policy.dispatch  # 不叠上一个公开状态的审计包装
                    wrapped = VipDevelopmentAuditPolicy(policy, "t199-" + args.branch + "-H0-selector",
                        lambda: dict(current), audit_sink, challenger=True, capture=capture)
                    answer = await wrapped.choose(request, DecisionBudget(860.0, 861.0, 862.0))
                    if hashlib.sha256(canonical(policy.last_view.candidate_view())).hexdigest() != sha:
                        raise ValueError("新choose同源完整图不同；不借旧图支付")
                    if {c.action_key for c in answer.candidates} != set(row["legal_action_keys"]):
                        raise ValueError("新choose根集合不完整")
                    chosen = answer.candidates[0].action_key
                    trace = dict(policy.last_root_order.trace)
                counts["eligible_public_windows"] += 1
                item = {"task": task, "target_row": row_no, "window_key": row["window_key"], "observation": row["observation"],
                    "legal_action_keys": row["legal_action_keys"], "view_sha256": sha, "parent_first": row["selected_action_key"],
                    "candidate_first": chosen, "changed": chosen != row["selected_action_key"], "same_action_negative_control": False,
                    "selection_trace": trace, "prefix_file": origin["raw_paths"]["decisions.jsonl.gz"],
                    "source_origin": origin}
                if item["changed"]:
                    records.append(item)
                    break
                control = control or item
            except Exception as error:
                failures.append({"table_no": task["table_no"], "target_row": row_no, "type": type(error).__name__, "message": str(error)})
                break  # 原unknown/失败不换一个有利点
        if control is not None:
            records.append(control)
    audit_stream.close()
    try:
        terminal = capture.finish()
    finally:
        raw.close()
    if not terminal["terminal"]["terminal_valid"]:
        failures.append({"stage": "selector_capture", "message": "评分输入捕获终态未闭"})
    points = choose_points(records)
    files = {**table_files, **mechanical["files"], str(source_path): pin(source_path),
        str(args.approval): pin(args.approval), str(_project_file(_PROJECT_ROOT, HERE / "GATES.json")): pin(_project_file(_PROJECT_ROOT, HERE / "GATES.json"))}
    files[measurement["plan_path"]] = measurement["plan_pin"]
    files[measurement["helper_path"]] = measurement["helper_pin"]
    for name in ("common.py", "select_and_freeze.py", "run_point.py", "summarize.py"):
        files[str(_project_file(_PROJECT_ROOT, HERE / name))] = pin(_project_file(_PROJECT_ROOT, HERE / name))
    for name in ("START.json", "SELECTOR-views.jsonl.gz", "SELECTOR-decisions.jsonl.gz"):
        files[str(output / name)] = pin(output / name)
    result = {"schema": "t199-common-P0-continuation-plan/1", "branch": args.branch, "candidate": "H0",
        "source_impact_plan": str(source_path), "source_impact_plan_pin": pin(source_path), "source_core_id": source["candidate_identity"]["candidate_id"],
        "source_origin_manifest": str(Path(args.origin_manifest).resolve()), "source_origin_manifest_pin": pin(args.origin_manifest),
        "source_table_origins": origins,
        "measurement_gate": measurement,
        "source_mother_count": 8, "mechanical_binding_id": mechanical["binding_id"], "sources": mechanical["sources"],
        "max_selection_source_scores": 256, "max_selection_monotonic_seconds": 300,
        "selection_counts": counts, "selection_failures": failures, "selection_unknown": scanned,
        "selector_capture": terminal, "source_formula_identities": {name: params.identity(text) for name, text in sources.items()},
        "points": points, "max_continuations": len(points) * 4, "compatible_samples_per_point": 2, "slot_paths": source["slot_paths"],
        "sample_key_template": read(_project_file(_PROJECT_ROOT, HERE / "GATES.json"))["sample_key_template"], "Rounds": 8, "endpoint": "current_complete_table_end",
        "zero_changed_stop": not any(p["changed"] for p in points), "coverage_unknown": len([p for p in points if p["changed"]]) < 11,
        "same_action_negative_control_present": any(p["same_action_negative_control"] for p in points), "files": files,
        "capture_limits": {"max_view_json_bytes": 67108864, "max_total_json_bytes": 134217728, "max_unique_views": 4096},
        "max_focal_scores_per_point": 4096, "max_all_seat_choose_windows_per_point": 24000,
        "logical_now": 800.0, "step_limit_per_continuation": 100000,
        "wall_seconds_per_point": 600, "mechanism_only_not_strength_or_deadline_admission": True,
        "loaded_modules": verify_loaded(source), "elapsed_monotonic_seconds": time.monotonic() - started}
    result["binding_id"] = hashlib.sha256(canonical(result)).hexdigest()
    save(output / "PLAN.json", result)
    save(output / "SELECTION-ROWS.json", {"records": records, "counts": counts, "failures": failures, "unknown": scanned})
    print({"branch": args.branch, "points": len(points), "max_remaining_table_continuations": len(points) * 4,
           "source_mothers": len({p["task"]["root"] for p in points}), "new_source_scores": counts["new_source_scores"],
           "continuations_executed": 0, "coverage_unknown": result["coverage_unknown"], "failures": len(failures)})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-plan", required=True)
    parser.add_argument("--origin-manifest", required=True)
    parser.add_argument("--measurement-plan", required=True)
    parser.add_argument("--approval", required=True)
    parser.add_argument("--branch", choices=("A", "B", "C"), required=True)
    parser.add_argument("--output", required=True)
    asyncio.run(run(parser.parse_args()))
