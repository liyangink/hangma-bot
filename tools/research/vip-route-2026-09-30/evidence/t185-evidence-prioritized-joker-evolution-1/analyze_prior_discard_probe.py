"""只读已闭合102弃牌诊断，分开汇总最快进张、牌型并集和自然面子准备。"""

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
from collections import Counter
from pathlib import Path

from common import HERE, ROOT, canonical, pin, save
import t185_close_development as dev
from t185_prepare_confirmation import background_priority, postprocess_lock


def comparison(parent, selected):
    """同一公开图比较两弃后事实；不把宽度支配当成效用或因果支配。"""
    matched = all(parent[k] == selected[k] for k in
        ("combined_shanten", "whites_held", "meld_set_count"))
    result = {"same_combined_shanten_white_meld": matched,
        "combined_shanten": [parent["combined_shanten"], selected["combined_shanten"]],
        "standard_shanten": [parent["standard_shanten"], selected["standard_shanten"]],
        "seven_pairs_shanten": [parent["seven_pairs_shanten"], selected["seven_pairs_shanten"]],
        "natural_draw_lower_bound": [parent["natural_set_draw_lower_bound"], selected["natural_set_draw_lower_bound"]],
        "natural_discard_lower_bound": [parent["natural_set_discard_lower_bound"], selected["natural_set_discard_lower_bound"]]}
    for field in ("combined_improvement", "family_union_improvement", "natural_set_improvement"):
        a, b = parent[field], selected[field]
        result[field] = {"width": [a["compatible_width"], b["compatible_width"]],
            "exact_public_unseen_capacity_sum": [a["exact_public_unseen_capacity_sum"], b["exact_public_unseen_capacity_sum"]]}
    return result


def main():
    """闭合评分与逐行输出、全冻结源码及捕获原件核齐，零新评分/世界/桌/HTTP。"""
    background_priority()
    with postprocess_lock("closed_discard_probe_summary"):
        folder = _project_file(_PROJECT_ROOT, HERE / "prior-discard-formula-probe")
        closed, closed_pin = dev.read(folder / "CLOSED.json")
        plan, plan_pin = dev.read(folder / "PLAN.json")
        dev.require(closed["complete"] and closed["failure"] is None and closed["source_stable"] and
            closed["actual_cases"] == 102 and closed["actual_score_attempts"] == 408 and
            closed["plan_pin"] == plan_pin, "弃牌诊断不完整或分母不符")
        rows = [dev.decode(line) for line in (folder / "rows.jsonl").read_bytes().splitlines()]
        dev.require(canonical(rows) == canonical(closed["rows"]), "诊断原行与闭合结果不同")
        captured = closed["capture"]["terminal"]
        dev.require(captured["terminal_valid"] and captured["verified_unique_views"] == 102 and
            pin(folder / "views.jsonl.gz")["sha256"] == captured["compressed_sha256"], "真实输入捕获未验齐")
        files = {**closed["files"], str(folder / "CLOSED.json"): closed_pin,
            str(folder / "PLAN.json"): plan_pin, str(folder / "rows.jsonl"): pin(folder / "rows.jsonl"),
            str(folder / "views.jsonl.gz"): pin(folder / "views.jsonl.gz"), str(Path(__file__)): pin(Path(__file__))}
        dev.require(all(pin(Path(p)) == h for p, h in files.items()) and
            all(pin(_project_file(_PROJECT_ROOT, ROOT / p)) == h for p, h in plan["source_manifest"].items()), "闭合原件或框架漂移")
        response, response_pin = dev.read(_project_file(_PROJECT_ROOT, HERE / "prior-response-formula-probe/CLOSED.json"))
        dev.require(response["complete"] and response["actual_cases"] == 26 and response["actual_score_attempts"] == 104,
            "对应响应诊断不是原26窗")
        keys = lambda rows: {(r["root_id"], r["rotation"]) for r in rows}
        dev.require(len(keys(rows)) == 102 and len(keys(response["rows"])) == 26 and
            not keys(rows) & keys(response["rows"]), "102弃牌与26响应来源重复")
        original, original_pin = dev.read(_project_file(_PROJECT_ROOT, HERE / "prior-joint-first-divergences/CLOSED.json"))
        original_rows = [dev.decode(line) for line in (_project_file(_PROJECT_ROOT, HERE / "prior-joint-first-divergences/rows.jsonl")).read_bytes().splitlines()]
        dev.require(original["complete"] and keys(rows) | keys(response["rows"]) == keys(original_rows),
            "没有覆盖原全部128首分歧")
        files.update({str(_project_file(_PROJECT_ROOT, HERE / "prior-response-formula-probe/CLOSED.json")): response_pin,
            str(_project_file(_PROJECT_ROOT, HERE / "prior-joint-first-divergences/CLOSED.json")): original_pin})
        arms = []
        for index in (None, 1, 2, 3):
            counts, changes, widths_by_white = Counter(), [], {}
            broad_sources = set()
            for row in rows:
                parent_key = row["old_parent_first"]
                dev.require(row["outputs"][0]["first"] == parent_key, "父代首选与真实原决策不同")
                chosen = row["old_joint_first"] if index is None else row["outputs"][index]["first"]
                counts["all_windows"] += 1
                if chosen == parent_key:
                    counts["unchanged"] += 1
                    continue
                counts["changed"] += 1
                counts["changed_white_" + str(row["white_count"])] += 1
                detail = {k: row[k] for k in ("root_id", "rotation", "round_no", "trigger_seq", "white_count")}
                detail.update(parent_action=parent_key, selected_action=chosen)
                if chosen not in row["discard_metrics"]:
                    counts["changed_to_nondiscard"] += 1
                    detail["comparison"] = None
                else:
                    facts = comparison(row["discard_metrics"][parent_key], row["discard_metrics"][chosen])
                    detail["comparison"] = facts
                    counts["changed_to_discard"] += 1
                    if facts["same_combined_shanten_white_meld"]:
                        counts["matched_fastest_distance_white_meld"] += 1
                        a, b = facts["combined_improvement"]["width"]
                        direction = "wider" if b > a else "narrower" if b < a else "equal"
                        counts["primary_width_" + direction] += 1
                        widths_by_white.setdefault(str(row["white_count"]), Counter())[direction] += 1
                        if direction == "wider":
                            broad_sources.add(row["root_id"])
                    else:
                        counts["distance_white_or_meld_changed"] += 1
                    a, b = facts["natural_draw_lower_bound"]
                    counts["natural_need_" + ("more" if b > a else "less" if b < a else "equal")] += 1
                changes.append(detail)
            identity = "old_failed_joint_candidate" if index is None else rows[0]["outputs"][index]["candidate_id"]
            arms.append({"candidate_id": identity, "counts": dict(counts), "changed_cases": changes,
                "matched_primary_wider_sources": sorted(broad_sources),
                "matched_primary_width_by_current_white": {k: dict(v) for k, v in widths_by_white.items()},
                "same_128_panel_response_changes": None if index is None else
                    sum(r["outputs"][index]["first"] != r["old_parent_first"] for r in response["rows"])})
        dev.require(all(pin(Path(p)) == h for p, h in files.items()), "汇总期间原件漂移")
        save(_project_file(_PROJECT_ROOT, HERE / "PRIOR-DISCARD-MECHANISM-SUMMARY-010.json"), {"complete": True, "files": files,
            "actual_closed_score_attempts_this_probe": 408, "actual_cases": 102,
            "current_white_strata_at_first_divergence_not_initial_counts": dict(Counter(str(r["white_count"]) for r in rows)),
            "all_128_old_first_divergences_current_probes_covered": True, "arms": arms,
            "non_full_table_scoring_attempts_previous_3464_plus_this_408": 3872,
            "new_scores_worlds_tables_model_calls_HTTP_in_summary": 0,
            "current_development_data_read": False, "strength_or_causal_or_deadline_admission": False,
            "unchanged_current_frozen_candidates_sources_selection_confirmation_thresholds": True,
            "scope": "旧失败路径的后选择诊断，不是自然随机或独立确认；公开未见容量包含暗牌，非墙内概率；自然面子宽度不含将；宽度与自然缺张必须联合看用途价值"})
        print({"complete": True, "actual_probe_scores": 408, "arms": [{"candidate_id": a["candidate_id"], "counts": a["counts"]} for a in arms]}, flush=True)


if __name__ == "__main__":
    main()
