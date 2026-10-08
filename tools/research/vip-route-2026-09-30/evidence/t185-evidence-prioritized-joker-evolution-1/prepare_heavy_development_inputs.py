"""从已闭合开发批按工作量封存性能输入，零新评分，不读取确认成绩。

模拟器内测时长包含研究捕获和后台资源影响，不是官方动作余量。本工具
不按时长、终分或胡型选样，不替换原39个官方请求及其原截止。
"""

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
import gzip
import hashlib
import time
from collections import Counter
from pathlib import Path

from common import HERE, canonical, pin, save
import t185_close_development as dev
from t185_prepare_confirmation import (
    background_priority, postprocess_lock, require_development_dispatch,
)


GROUPS = {
    "operations": "candidate_operations",
    "graph_bytes": "captured_graph_json_bytes",
    "target_evaluations": "target_distance_evaluation_count",
    "waiting_witnesses": "waiting_draw_witness_count",
    "self_gang": "candidate_operations",
    "exposed_gang": "candidate_operations",
    "replacement": "candidate_operations",
    "response": "candidate_operations",
}


def tags(row):
    """只用公开合法动作和已知补牌状态筛工作量类别；未知补牌不补零。"""
    result = {"operations", "graph_bytes", "target_evaluations", "waiting_witnesses"}
    keys, obs = row["legal_action_keys"], row["observation"]
    if any(k.startswith(("gang:concealed:", "gang:added:")) for k in keys):
        result.add("self_gang")
    if any(k.startswith("gang:exposed:") for k in keys):
        result.add("exposed_gang")
    chain = obs["chain_piao"]
    if obs["gang_draw"] is True or (type(chain) is int and chain > 0):
        result.add("replacement")
    if row["phase"] != "draw":
        result.add("response")
    return result


def main():
    """父代及唯一选中候选的全部256桌，八组各取四个不同公开图的最大值。"""
    background_priority()
    with postprocess_lock("t185_closed_development_heavy_input_preparation"):
        require_development_dispatch()
        closed, closed_pin = dev.read(_project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-CLOSED.json"))
        plan, plan_pin = dev.read(_project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-PLAN.json"))
        dev.require(closed["complete"] and closed["source_stable"] and
            closed["actual_table_instances"] == 512 and len(plan["roots"]) == 32,
            "开发全批尚未有效闭合")
        dev.frozen(plan)
        selected = closed["selected_candidate_id_for_confirmation_preparation"]
        child_index = next(i for i, a in enumerate(plan["candidates"], 1)
            if a["identity"]["candidate_id"] == selected)
        tables = sorted((r for r in closed["tables"] if r["arm_index"] in (0, child_index)),
            key=lambda r: (r["root_id"], r["rotation"], r["arm_index"]))
        dev.require(len(tables) == 256, "父子原完整桌分母不同")
        out = _project_file(_PROJECT_ROOT, HERE / "development-heavy-inputs")
        out.mkdir(exist_ok=False)
        files = {str(p): pin(p) for p in (Path(__file__), _project_file(_PROJECT_ROOT, HERE / "common.py"),
            _project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-CLOSED.json"), _project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-PLAN.json"),
            _project_file(_PROJECT_ROOT, HERE / "development-dispatch/CLOSED.json"))}
        save(out / "PLAN.json", {
            "files": files, "development_closed_pin": closed_pin, "development_plan_pin": plan_pin,
            "selected_candidate_id": selected, "complete_tables_to_scan": 256,
            "groups": GROUPS, "per_group_distinct_view_limit": 4, "maximum_unique_views": 32,
            "ranking": "metric降序、原文件名与原行位置升序；每组按公开图摘要去重",
            "no_selection_by_outcome_or_observed_seconds": True,
            "maximum_selected_raw_view_bytes": 536870912,
            "new_rule_analyses_scores_worlds_tables_model_calls_HTTP": 0,
            "original_39_official_requests_and_deadlines_unchanged": True,
            "confirmation_data_read": False, "deadline_or_strength_admission": False,
        })
        best = {name: {} for name in GROUPS}
        eligible_counts, families = Counter(), Counter()
        scanned, expected_count, failure = 0, 0, None
        started, raw_bytes, cases = time.monotonic(), 0, []
        try:
            for table in tables:
                index = next(i for i, r in enumerate(plan["roots"], 1) if r["root_id"] == table["root_id"])
                directory = _project_file(_PROJECT_ROOT, HERE / "natural-development" / f"root-{index:03d}" / \
                    f"seat-{table['rotation']}-arm-{table['arm_index']}")
                original = directory / "focal-decisions.jsonl.gz"
                for p in (original, directory / "CLOSURE.json"):
                    actual = pin(p)
                    dev.require(closed["files"].get(str(p)) == actual, "原开发流或终态漂移")
                    files[str(p)] = actual
                closure, _ = dev.read(directory / "CLOSURE.json")
                expected_count += closure["actual_focal_decisions"]
                arm = plan["parent"] if table["arm_index"] == 0 else plan["candidates"][child_index - 1]
                local = 0
                with gzip.open(original, "rb") as stream:
                    for position, raw in enumerate(stream):
                        row = dev.decode(raw)
                        dev.require(row["status"] == "chosen" and row["c_self_scored"] is True and
                            not row["degraded_reasons"] and row["arm"] == table["arm_index"] and
                            row["root_id"] == table["root_id"] and row["rotation"] == table["rotation"] and
                            row["seat"] == table["rotation"] and
                            row["source_identity"] == arm["identity"]["candidate_id"] and
                            len(row["scoring_calls"]) == 1, "原评分、身份或调用数不同")
                        call = row["scoring_calls"][0]
                        capture = call["input_capture"]
                        dev.require(call["score_completed"] is True and capture["saved_before_score"] is True and
                            call["candidate_operations"] == row["candidate_operations"], "原捕获或计量无效")
                        metrics = {"candidate_operations": row["candidate_operations"],
                            "captured_graph_json_bytes": capture["json_bytes"],
                            "target_distance_evaluation_count": call["target_distance_evaluation_count"],
                            "waiting_draw_witness_count": call["waiting_draw_witness_count"]}
                        dev.require(all(type(v) is int and v >= 0 for v in metrics.values()), "工作量非非负整数")
                        identity = (str(original), position)
                        groups = tags(row)
                        sha = capture["view_sha256"]
                        for group in groups:
                            eligible_counts[group] += 1
                            metric = GROUPS[group]
                            entry = {"origin": str(original), "position": position, "original_row": row,
                                "original_line_sha256": hashlib.sha256(raw).hexdigest(),
                                "metrics": metrics, "identity": identity, "view_sha256": sha}
                            prior = best[group].get(sha)
                            order = lambda e: (-e["metrics"][metric], e["identity"])
                            if prior is None or order(entry) < order(prior):
                                best[group][sha] = entry
                            if len(best[group]) > 4:
                                keep = sorted(best[group].values(), key=order)[:4]
                                best[group] = {e["view_sha256"]: e for e in keep}
                        families.update(row["action_families"])
                        local += 1
                dev.require(local == closure["actual_focal_decisions"], "原逐桌评分行数不同")
                scanned += local
            dev.require(scanned == expected_count, "全部父子原评分分母不齐")
            selections = {}
            for group, entries in best.items():
                for entry in entries.values():
                    sha = entry["view_sha256"]
                    bucket = selections.setdefault(sha, [])
                    bucket.append((group, entry))
            dev.require(0 < len(selections) <= 32, "重型图数量超出计划")
            by_view_file = {}
            for sha, entries in selections.items():
                representative = min((e for _, e in entries), key=lambda e: e["identity"])
                source = Path(representative["origin"]).with_name("views.jsonl.gz")
                by_view_file.setdefault(source, []).append((sha, entries, representative))
            with gzip.open(out / "original-heavy-views.jsonl.gz", "xb") as output:
                for path in sorted(by_view_file):
                    actual = pin(path)
                    dev.require(closed["files"].get(str(path)) == actual, "原捕获图漂移")
                    files[str(path)] = actual
                    needed = {sha: (entries, representative) for sha, entries, representative in by_view_file[path]}
                    found = set()
                    with gzip.open(path, "rb") as stream:
                        for raw in stream:
                            record = dev.decode(raw)
                            sha = record["view_sha256"]
                            if sha not in needed:
                                continue
                            dev.require(sha not in found and
                                hashlib.sha256(canonical(record["view"])).hexdigest() == sha and
                                record["json_bytes"] == len(canonical(record["view"])), "原完整图重复或摘要无效")
                            raw_bytes += len(raw)
                            dev.require(raw_bytes <= 536870912, "重型原公开图超过512MiB计划")
                            output.write(raw)
                            entries, representative = needed[sha]
                            cases.append({"view_sha256": sha, "original_view_file": str(path),
                                "original_view_line_sha256": hashlib.sha256(raw).hexdigest(),
                                "original_decision_file": representative["origin"],
                                "original_decision_position_zero_based": representative["position"],
                                "original_decision_line_sha256": representative["original_line_sha256"],
                                "original_public_decision": representative["original_row"],
                                "workload": record["view"]["workload"],
                                "selected_for": [{"group": group, "metric": GROUPS[group],
                                    "metric_value": e["metrics"][GROUPS[group]], "origin": e["origin"],
                                    "position_zero_based": e["position"]} for group, e in sorted(entries)],
                                "original_source_scores_not_new_winner_gold_unless_same_identity": True,
                                "simulation_game_not_official_original_deadline": True})
                            found.add(sha)
                    dev.require(found == set(needed), "重型原完整图缺失")
            dev.require(len(cases) == len(selections), "封存重型图数量不同")
            cases.sort(key=lambda r: r["view_sha256"])
            save(out / "CASES.json", {"cases": cases, "new_scores_rule_analyses": 0})
        except BaseException as error:
            failure = {"type": type(error).__name__, "message": str(error), "scanned_decisions": scanned,
                "stored_cases": len(cases)}
        stable = all(pin(Path(p)) == h for p, h in files.items())
        complete = failure is None and scanned == expected_count and len(cases) > 0 and stable
        result = {"complete": complete, "failure": failure, "source_stable": stable, "files": files,
            "plan_pin": pin(out / "PLAN.json"), "scanned_complete_tables": 256,
            "actual_and_expected_decisions": [scanned, expected_count], "selected_unique_views": len(cases),
            "eligible_counts": dict(eligible_counts), "action_family_presence_counts": dict(families),
            "group_selection": {g: [{"view_sha256": e["view_sha256"], "metric_value": e["metrics"][GROUPS[g]]}
                for e in sorted(v.values(), key=lambda e: (-e["metrics"][GROUPS[g]], e["identity"]))]
                for g, v in best.items()}, "selected_raw_view_bytes": raw_bytes,
            "elapsed_monotonic_seconds": time.monotonic() - started,
            "new_rule_analyses_scores_worlds_tables_model_calls_HTTP": 0,
            "confirmation_data_read": False, "deadline_or_strength_admission": False}
        if complete:
            result["cases_pin"] = pin(out / "CASES.json")
            result["original_heavy_views_pin"] = pin(out / "original-heavy-views.jsonl.gz")
        save(out / "CLOSED.json", result)
        dev.require(complete, "重型输入准备未完整；保留原失败，不自动重做")
        print({"complete": True, "decisions_scanned": scanned, "selected_views": len(cases),
            "eligible_counts": dict(eligible_counts), "new_rule_analyses_scores_worlds_tables_model_calls_HTTP": 0}, flush=True)


if __name__ == "__main__":
    main()
