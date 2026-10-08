"""旧全512桌闭合后的联合候选首分歧诊断；不读取当前开发中途分数。"""

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
import itertools
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

from common import HERE, OLD, ROOT, canonical, pin, save
import t185_close_development as dev
from t185_prepare_confirmation import background_priority, postprocess_lock


def compact_candidate(row, action):
    """原完整评分中取指定动作的小摘要，不重评分，不补事实或输出解释。"""
    found = [c for c in row["candidates"] if c["action_key"] == action]
    dev.require(len(found) == 1, "首分歧动作没有唯一原评分")
    return found[0]


def first_divergence(parent_path, child_path):
    """逐行比较直到首次改选；改选前公开观察、窗口、完整图及选择须相同。

    只读已自然完结的旧桌，返回原两行及可复查前缀摘要；后续结算不是
    本次动作的因果效应。前缀状态不一致或长度不齐时显式记未知。
    """
    prefix, count = hashlib.sha256(), 0
    with gzip.open(parent_path, "rb") as parent, gzip.open(child_path, "rb") as child:
        for position, pair in enumerate(itertools.zip_longest(parent, child)):
            if None in pair:
                return {"status": "prefix_unknown", "reason": "未改选前原序列长度不一致",
                    "equal_prefix_rows": count, "prefix_sha256": prefix.hexdigest()}, None
            a, b = (dev.decode(line) for line in pair)
            for row in (a, b):
                dev.require(row["status"] == "chosen" and row["c_self_scored"] is True and
                    not row["degraded_reasons"] and len(row["scoring_calls"]) == 1 and
                    row["scoring_calls"][0]["score_completed"] is True and
                    row["scoring_calls"][0]["input_capture"]["saved_before_score"] is True, "原首分歧前有评分缺口")
            if canonical(a["observation"]) != canonical(b["observation"]) or a["window_key"] != b["window_key"]:
                return {"status": "prefix_unknown", "reason": "首改选前公开观察或窗口不一致",
                    "equal_prefix_rows": count, "prefix_sha256": prefix.hexdigest()}, None
            a_sha = a["scoring_calls"][0]["input_capture"]["view_sha256"]
            b_sha = b["scoring_calls"][0]["input_capture"]["view_sha256"]
            dev.require(a_sha == b_sha and set(a["legal_action_keys"]) == set(b["legal_action_keys"]), "同公开状态的实际图或合法根不同")
            if a["selected_action_key"] != b["selected_action_key"]:
                return {"status": "first_divergence", "equal_prefix_rows": count,
                    "prefix_sha256": prefix.hexdigest(), "original_row_position_zero_based": position,
                    "view_sha256": a_sha, "observation_sha256": hashlib.sha256(canonical(a["observation"])).hexdigest()}, (a, b)
            prefix.update(canonical({"observation": a["observation"], "window_key": a["window_key"],
                "view_sha256": a_sha, "selected_action_key": a["selected_action_key"]}) + b"\n")
            count += 1
    return {"status": "all_focal_choices_same", "equal_prefix_rows": count, "prefix_sha256": prefix.hexdigest()}, None


def main():
    """固定旧联合候选全部128配对桌；选例标签用于诊断，不作独立强度来源。"""
    background_priority()
    with postprocess_lock("prior_closed_joint_first_divergence_diagnosis"):
        old, old_pin = dev.read(OLD / "DEVELOPMENT-CLOSED.json")
        resource, resource_pin = dev.read(OLD / "RESOURCE-SCHEDULING-CLOSED.json")
        plan, plan_pin = dev.read(OLD / "DEVELOPMENT-PLAN.json")
        dev.require(old["complete"] is True and old["actual_table_instances"] == 512 and
            old["completed_hand_instances"] == 4096 and resource["complete"] is True, "旧批未完整闭合")
        arm_index = 2
        arm = plan["candidates"][arm_index - 1]
        comparison = next(c for c in old["candidates"] if c["candidate_id"] == arm["identity"]["candidate_id"])
        dev.require(arm["label"] == "AUTHOR-joint-1-model-output" and len(comparison["sources"]) == 32, "旧联合候选身份或来源错误")
        out = _project_file(_PROJECT_ROOT, HERE / "prior-joint-first-divergences")
        out.mkdir(exist_ok=False)
        files = {str(p): pin(p) for p in (Path(__file__), _project_file(_PROJECT_ROOT, HERE / "common.py"), OLD / "DEVELOPMENT-CLOSED.json",
            OLD / "RESOURCE-SCHEDULING-CLOSED.json", OLD / "DEVELOPMENT-PLAN.json", Path(arm["source_file"]))}
        save(out / "START.json", {"candidate_identity": arm["identity"], "old_closed_pin": old_pin,
            "old_resource_pin": resource_pin, "old_plan_pin": plan_pin, "files": files,
            "planned_paired_complete_tables": 128, "new_scores_worlds_tables_model_calls_HTTP": 0,
            "current_development_data_read": False, "post_selected_diagnostic_not_independent_confirmation": True})
        rows, failure, groups = [], None, defaultdict(lambda: Counter())
        actual_full_rows_bytes, started = 0, time.monotonic()
        try:
            with gzip.open(out / "original-public-first-rows.jsonl.gz", "xb") as full, (out / "rows.jsonl").open("x") as stream:
                for index, root in enumerate(plan["roots"], 1):
                    source = comparison["sources"][index - 1]
                    dev.require(source["root_id"] == root["root_id"], "旧来源顺序不同")
                    for rotation in (0, 1, 2, 3):
                        directories = [OLD / "natural-development" / f"root-{index:03d}" / f"seat-{rotation}-arm-{a}" for a in (0, arm_index)]
                        paths = [d / "focal-decisions.jsonl.gz" for d in directories]
                        for path in paths:
                            actual = pin(path)
                            dev.require(old["files"].get(str(path)) == actual, "旧原决策流未绑定有效闭合")
                            files[str(path)] = actual
                        result, originals = first_divergence(*paths)
                        pair = source["paired_tables"][rotation]
                        dev.require(pair["rotation"] == rotation, "旧四座配对顺序不同")
                        row = {"root_id": root["root_id"], "root_index": index, "rotation": rotation, **result,
                            "complete_table_delta": pair["delta"], "table_delta_not_first_action_causal_effect": True,
                            "original_decision_files": [str(p) for p in paths]}
                        if originals is not None:
                            a, b = originals
                            pa, ca = a["selected_action_key"], b["selected_action_key"]
                            oldscores = [compact_candidate(a, key) for key in (pa, ca)]
                            newscores = [compact_candidate(b, key) for key in (pa, ca)]
                            white = a["white_count"]
                            dev.require(type(white) is int and 0 <= white <= 4 and b["white_count"] == white, "当前公开白数不同")
                            row.update(round_no=a["window_key"]["round_no"], trigger_seq=a["window_key"]["trigger_seq"],
                                phase=a["phase"], white_count_at_first_divergence=white,
                                white_count_is_not_initial_hand_stratum=True,
                                is_dealer_at_divergence=a["observation"]["dealer_seat"] == rotation,
                                remaining_tile_count=a["observation"]["remaining_tile_count"],
                                parent_action=pa, child_action=ca, parent_scores=oldscores, child_scores=newscores,
                                parent_selected_minus_alternative=oldscores[0]["score"] - oldscores[1]["score"],
                                child_selected_minus_alternative=newscores[1]["score"] - newscores[0]["score"])
                            original_row = {"root_id": root["root_id"], "rotation": rotation,
                                "parent_original_row": a, "child_original_row": b}
                            raw = canonical(original_row) + b"\n"
                            actual_full_rows_bytes += len(raw)
                            dev.require(actual_full_rows_bytes <= 67108864, "原公开首分歧行超过64MiB预算，保留失败")
                            full.write(raw)
                            category = str(white)
                            groups[category]["first_divergences"] += 1
                            groups[category]["whole_table_net_delta_associated"] += pair["delta"]["net"]
                            groups[category]["whole_table_ordinary_income_delta_associated"] += pair["delta"]["ordinary_hu_income"]
                            groups[category]["whole_table_large_income_delta_associated"] += pair["delta"]["large_hu_income"]
                            groups[category]["whole_table_payment_delta_associated"] += pair["delta"]["payments"]
                        rows.append(row)
                        stream.write(canonical(row).decode() + "\n")
                        stream.flush()
                dev.require(len(rows) == 128 and sum(r["complete_table_delta"]["net"] for r in rows) == comparison["net_delta_sum_128_tables"],
                    "全部128桌分账与原全批净差不一致")
        except BaseException as error:
            failure = {"type": type(error).__name__, "message": str(error), "completed_pairs": len(rows)}
        finally:
            stable = all(pin(Path(p)) == h for p, h in files.items())
            good = [r for r in rows if r["status"] == "first_divergence"]
            statuses = dict(Counter(r["status"] for r in rows))
            switches = dict(Counter(r["parent_action"].split(":")[0] + "->" + r["child_action"].split(":")[0] for r in good))
            complete = failure is None and len(rows) == 128 and stable
            save(out / "CLOSED.json", {"complete": complete, "failure": failure, "source_stable": stable,
                "files": files, "candidate_identity": arm["identity"], "actual_paired_complete_tables_read": len(rows),
                "status_counts": statuses, "first_divergence_action_switches": switches,
                "white_count_at_divergence_groups_descriptive_not_causal_or_initial_strata": dict(groups),
                "associated_table_deltas_not_single_action_causal_estimates": True,
                "first_divergence_draws": sum(r["phase"] == "draw" for r in good),
                "first_divergence_response": sum(r["phase"] != "draw" for r in good),
                "net_delta_sum_all_128_complete_tables": sum(r["complete_table_delta"]["net"] for r in rows),
                "original_first_rows_uncompressed_bytes": actual_full_rows_bytes,
                "rows_file_pin": pin(out / "rows.jsonl"), "original_first_rows_pin": pin(out / "original-public-first-rows.jsonl.gz"),
                "elapsed_monotonic_seconds": time.monotonic() - started,
                "new_scores_worlds_tables_model_calls_HTTP": 0,
                "current_development_data_read": False, "new_strength_or_causal_admission": False})
        dev.require(complete, "旧批首分歧诊断未完整，原失败保留")
        print(json.dumps({"complete": complete, "statuses": statuses, "switches": switches, "white_groups": dict(groups)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
