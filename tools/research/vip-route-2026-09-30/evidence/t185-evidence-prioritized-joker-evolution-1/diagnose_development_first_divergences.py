"""只读已闭合T185开发批的首分歧及当局分账，不改变确认选择。

同一公开前缀和起手／牌山可定位配对路径的首次变化；后继策略仍不同，
因此单局差及整桌差均不能当作一次动作的孤立因果收益。
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
import time
from collections import Counter, defaultdict
from pathlib import Path

from common import HERE, canonical, pin, save
import t185_close_development as dev
import diagnose_prior_first_divergences as prefix_tools
import analyze_prior_diverging_hands as account_tools
from t185_prepare_confirmation import (
    background_priority, postprocess_lock, require_development_dispatch,
)


def main():
    """固定全部三候选各128配对桌；零重评分、不读取确认牌山或成绩。"""
    background_priority()
    with postprocess_lock("t185_closed_development_first_divergences"):
        require_development_dispatch()
        closed, closed_pin = dev.read(_project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-CLOSED.json"))
        plan, plan_pin = dev.read(_project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-PLAN.json"))
        dev.require(closed["complete"] is True and closed["actual_table_instances"] == 512 and
            closed["completed_hand_instances"] == 4096 and len(plan["candidates"]) == 3,
            "开发批或固定三候选未全闭合")
        dev.frozen(plan)
        out = _project_file(_PROJECT_ROOT, HERE / "development-first-divergences")
        out.mkdir(exist_ok=False)
        files = {str(p): pin(p) for p in (
            Path(__file__), Path(prefix_tools.__file__), Path(account_tools.__file__),
            _project_file(_PROJECT_ROOT, HERE / "common.py"), _project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-CLOSED.json"), _project_file(_PROJECT_ROOT, HERE / "DEVELOPMENT-PLAN.json"),
            _project_file(_PROJECT_ROOT, HERE / "development-dispatch/CLOSED.json"),
        )}
        for arm in plan["candidates"]:
            p = Path(arm["source_file"])
            files[str(p)] = pin(p)
        save(out / "START.json", {
            "development_closed_pin": closed_pin, "development_plan_pin": plan_pin,
            "files": files, "planned_paired_complete_tables_read": 384,
            "selected_candidate_id_unchanged": closed["selected_candidate_id_for_confirmation_preparation"],
            "new_scores_worlds_tables_model_calls_HTTP": 0,
            "confirmation_data_read": False, "post_selected_diagnosis_not_new_admission": True,
        })
        rows, failure, summaries = [], None, []
        full_bytes, started = 0, time.monotonic()
        try:
            with gzip.open(out / "original-public-first-rows.jsonl.gz", "xb") as originals, \
                    (out / "rows.jsonl").open("x") as stream:
                for arm_index, arm in enumerate(plan["candidates"], 1):
                    comparison = closed["candidates"][arm_index - 1]
                    dev.require(comparison["candidate_id"] == arm["identity"]["candidate_id"],
                        "开发候选顺序或身份漂移")
                    local, by_switch, by_white = [], defaultdict(Counter), defaultdict(Counter)
                    for index, root in enumerate(plan["roots"], 1):
                        source = comparison["sources"][index - 1]
                        dev.require(source["root_id"] == root["root_id"] and source["seed"] == root["seed"],
                            "开发来源不对应")
                        for rotation in (0, 1, 2, 3):
                            directories = [_project_file(_PROJECT_ROOT, HERE / "natural-development" / f"root-{index:03d}" /
                                f"seat-{rotation}-arm-{a}") for a in (0, arm_index)]
                            paths = [d / "focal-decisions.jsonl.gz" for d in directories]
                            closures = []
                            for directory, path in zip(directories, paths):
                                closure_path = directory / "CLOSURE.json"
                                for p in (path, closure_path):
                                    actual_pin = pin(p)
                                    dev.require(closed["files"].get(str(p)) == actual_pin,
                                        "原开发决策或终态未绑定全批闭合")
                                    files[str(p)] = actual_pin
                                c, _ = dev.read(closure_path)
                                dev.require(c["complete"] is True and c["failure"] is None and
                                    c["focal_seat"] == rotation and len(c["settlements"]) ==
                                    len(c["pairing_proofs"]) == 8, "原桌状态、座位或单局数无效")
                                closures.append(c)
                            pair = source["paired_tables"][rotation]
                            dev.require(pair["rotation"] == rotation, "四换座配对顺序漂移")
                            result, public_pair = prefix_tools.first_divergence(*paths)
                            row = {
                                "candidate_id": comparison["candidate_id"], "arm_index": arm_index,
                                "root_id": root["root_id"], "root_index": index, "rotation": rotation,
                                **result, "whole_table_delta": pair["delta"],
                                "original_decision_files": [str(p) for p in paths],
                                "continuation_policies_differ_not_isolated_action_effect": True,
                            }
                            if public_pair is not None:
                                a, b = public_pair
                                n = a["window_key"]["round_no"]
                                proofs = [c["pairing_proofs"][n - 1] for c in closures]
                                dev.require(all(p["round_no"] == n for p in proofs) and
                                    proofs[0]["physical_wall_sha256"] == proofs[1]["physical_wall_sha256"] and
                                    proofs[0]["actual_initial_sha256"] == proofs[1]["actual_initial_sha256"] and
                                    proofs[0]["dealer_seat"] == proofs[1]["dealer_seat"] and
                                    proofs[0]["focal_initial_white_count"] == proofs[1]["focal_initial_white_count"],
                                    "首分歧当局起手、牌山、庄位或起手白数不同")
                                settlements = [c["settlements"][n - 1] for c in closures]
                                dev.require(all(s["evidence"] == "public_export_hand_settlement" and
                                    s["round_no"] == n for s in settlements), "当局结算来源不同")
                                accounts = [account_tools.hand_account(s["settlement"], rotation)
                                    for s in settlements]
                                delta = {k: accounts[1][k] - accounts[0][k] for k in
                                    ("net", "own_hu", "ordinary_income", "large_income", "payments")}
                                pa, ca = a["selected_action_key"], b["selected_action_key"]
                                white = a["white_count"]
                                dev.require(type(white) is int and 0 <= white <= 4 and b["white_count"] == white,
                                    "首分歧公开白数无效或不同")
                                switch = pa.split(":")[0] + "->" + ca.split(":")[0]
                                row.update(
                                    round_no=n, trigger_seq=a["window_key"]["trigger_seq"], phase=a["phase"],
                                    white_count_at_first_divergence=white,
                                    first_diverging_hand_initial_white_count=proofs[0]["focal_initial_white_count"],
                                    remaining_tile_count=a["observation"]["remaining_tile_count"],
                                    is_dealer=a["observation"]["dealer_seat"] == rotation,
                                    parent_action=pa, child_action=ca, switch=switch,
                                    parent_scores=[prefix_tools.compact_candidate(a, k) for k in (pa, ca)],
                                    child_scores=[prefix_tools.compact_candidate(b, k) for k in (pa, ca)],
                                    same_first_hand_initial_and_wall_proof=proofs[0],
                                    parent_hand=accounts[0], child_hand=accounts[1],
                                    first_diverging_hand_delta=delta,
                                )
                                raw = canonical({"candidate_id": comparison["candidate_id"],
                                    "root_id": root["root_id"], "rotation": rotation,
                                    "parent_original_row": a, "child_original_row": b}) + b"\n"
                                full_bytes += len(raw)
                                dev.require(full_bytes <= 134217728, "原公开行超过128MiB诊断预算")
                                originals.write(raw)
                                for group in (by_switch[switch], by_white[str(white)]):
                                    group["count"] += 1
                                    group["whole_table_net_delta_associated"] += pair["delta"]["net"]
                                    for key, value in delta.items():
                                        group[key + "_first_hand_delta"] += value
                            elif result["status"] == "all_focal_choices_same":
                                dev.require(pair["delta"]["net"] == 0 and
                                    closures[0]["settlements"] == closures[1]["settlements"],
                                    "全部本人选择相同时结算仍不同，不能视为等效")
                            local.append(row)
                            rows.append(row)
                            stream.write(canonical(row).decode() + "\n")
                            stream.flush()
                    dev.require(len(local) == 128 and sum(r["whole_table_delta"]["net"] for r in local) ==
                        comparison["net_delta_sum_128_tables"], "候选全部128桌净差不对账")
                    summaries.append({
                        "candidate_id": comparison["candidate_id"],
                        "status_counts": dict(Counter(r["status"] for r in local)),
                        "net_delta_sum_128_tables": comparison["net_delta_sum_128_tables"],
                        "by_switch": dict(by_switch), "by_current_white_descriptive": dict(by_white),
                    })
        except BaseException as error:
            failure = {"type": type(error).__name__, "message": str(error), "completed_pairs": len(rows)}
        stable = all(pin(Path(p)) == h for p, h in files.items())
        complete = failure is None and len(rows) == 384 and len(summaries) == 3 and stable
        save(out / "CLOSED.json", {
            "complete": complete, "failure": failure, "source_stable": stable, "files": files,
            "actual_paired_complete_tables_read": len(rows), "candidate_summaries": summaries,
            "development_closed_pin": closed_pin, "development_plan_pin": plan_pin,
            "rows_file_pin": pin(out / "rows.jsonl"),
            "original_first_rows_pin": pin(out / "original-public-first-rows.jsonl.gz"),
            "original_first_rows_uncompressed_bytes": full_bytes,
            "elapsed_monotonic_seconds": time.monotonic() - started,
            "new_scores_worlds_tables_model_calls_HTTP": 0, "confirmation_data_read": False,
            "selected_candidate_id_unchanged": closed["selected_candidate_id_for_confirmation_preparation"],
            "post_selected_path_diagnosis_not_independent_strength_or_single_action_causal_evidence": True,
        })
        dev.require(complete, "开发首分歧诊断未完整；保留原失败，不自动重做")
        print({"complete": True, "pairs": len(rows), "new_scores_worlds_tables_model_calls_HTTP": 0,
            "candidate_summaries": summaries}, flush=True)


if __name__ == "__main__":
    main()
