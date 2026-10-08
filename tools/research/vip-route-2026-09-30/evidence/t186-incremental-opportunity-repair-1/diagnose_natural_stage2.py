"""只读已闭64桌的首改选与大牌损失；不读取正在运行的第三阶段。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t186-incremental-opportunity-repair-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import gzip
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0, str(PRIOR))
from common import canonical, pin, save
from diagnose_prior_first_divergences import first_divergence, compact_candidate
from analyze_prior_diverging_hands import hand_account
from t185_prepare_confirmation import background_priority, postprocess_lock


def main():
    """核全部32配对，保持正负与同动作对照；结算只是策略路径观察。"""
    background_priority()
    with postprocess_lock("t186_closed_stage2_path_diagnosis"):
        stage = _project_file(_PROJECT_ROOT, HERE / "natural-stage-002-dispatch")
        paths = [stage / n for n in ("CLOSED.json", "READOUT-CLOSED.json", "SUMMARY.json")]
        dispatch, readout, summary = [json.loads(p.read_text()) for p in paths]
        assert dispatch["complete"] and dispatch["resources_released"]
        assert readout["complete"] and readout["source_stable"] and readout["actual_tables"] == 64
        assert summary["complete"] and summary["independent_roots"] == 8
        assert summary["readout_pin"] == pin(paths[1])
        assert dispatch["plan_pin"] == readout["plan_pin"] == summary["plan_pin"]
        files = {str(p): pin(p) for p in paths + [Path(__file__),
            _project_file(_PROJECT_ROOT, PRIOR / "diagnose_prior_first_divergences.py"), _project_file(_PROJECT_ROOT, PRIOR / "analyze_prior_diverging_hands.py")]}
        directory = _project_file(_PROJECT_ROOT, HERE / "natural-stage-002-paths")
        directory.mkdir(exist_ok=False)
        save(directory / "START.json", {"files": files, "all_paired_tables": 32,
            "new_scores_worlds_tables_models_HTTP": 0, "stage3_data_read": False})
        rows, failure, groups = [], None, defaultdict(Counter)
        started = time.monotonic()
        try:
            with (directory / "rows.jsonl").open("x") as output, \
                    gzip.open(directory / "original-public-first-rows.jsonl.gz", "xb") as public:
                for source in summary["sources"]:
                    for pair in source["paired_tables"]:
                        root, seat = source["root"], pair["rotation"]
                        dirs = [_project_file(_PROJECT_ROOT, HERE / "natural-development" / f"root-{root:03d}" /
                            f"seat-{seat}-arm-{arm}") for arm in (0, 1)]
                        closures = []
                        for d in dirs:
                            for name in ("CLOSURE.json", "focal-decisions.jsonl.gz"):
                                p = d / name
                                assert readout["files"][str(p)] == pin(p)
                                files[str(p)] = pin(p)
                            closed = json.loads((d / "CLOSURE.json").read_text())
                            assert closed["complete"] and closed["failure"] is None
                            assert len(closed["settlements"]) == len(closed["pairing_proofs"]) == 8
                            closures.append(closed)
                        status, originals = first_divergence(*(d / "focal-decisions.jsonl.gz" for d in dirs))
                        row = {"root": root, "rotation": seat, "root_id": source["root_id"],
                            **status, "table_delta": pair["delta"],
                            "whole_table_not_first_action_causal_effect": True}
                        if originals:
                            a, b = originals
                            turn = a["window_key"]["round_no"]
                            proofs = [c["pairing_proofs"][turn - 1] for c in closures]
                            assert all(proofs[0][k] == proofs[1][k] for k in
                                ("physical_wall_sha256", "actual_initial_sha256", "dealer_seat"))
                            accounts = [hand_account(c["settlements"][turn - 1]["settlement"], seat) for c in closures]
                            pa, ca = a["selected_action_key"], b["selected_action_key"]
                            row.update(round_no=turn, trigger_seq=a["window_key"]["trigger_seq"],
                                white_count=a["white_count"], remaining_tile_count=a["observation"]["remaining_tile_count"],
                                parent_action=pa, child_action=ca,
                                switch=pa.split(":")[0] + "->" + ca.split(":")[0],
                                parent_hand=accounts[0], child_hand=accounts[1],
                                first_hand_delta={k: accounts[1][k] - accounts[0][k] for k in
                                    ("net", "ordinary_income", "large_income", "payments")},
                                parent_scores=[compact_candidate(a, k) for k in (pa, ca)],
                                child_scores=[compact_candidate(b, k) for k in (pa, ca)])
                            public.write(canonical({"root": root, "rotation": seat,
                                "parent_original_row": a, "child_original_row": b}) + b"\n")
                        elif status["status"] == "all_focal_choices_same":
                            assert pair["delta"]["net"] == 0
                            assert closures[0]["settlements"] == closures[1]["settlements"]
                        row["aligned_round_large_loss_observations"] = []
                        for turn in range(1, 9):
                            accounts = [hand_account(c["settlements"][turn - 1]["settlement"], seat) for c in closures]
                            if accounts[1]["large_income"] < accounts[0]["large_income"]:
                                proofs = [c["pairing_proofs"][turn - 1] for c in closures]
                                row["aligned_round_large_loss_observations"].append({
                                    "round_no": turn, "parent_hand": accounts[0], "child_hand": accounts[1],
                                    "same_physical_wall": proofs[0]["physical_wall_sha256"] == proofs[1]["physical_wall_sha256"],
                                    "same_actual_initial_state": proofs[0]["actual_initial_sha256"] == proofs[1]["actual_initial_sha256"],
                                    "post_first_divergence_paths_not_isolated_action_effect": True})
                        group = groups[row.get("switch", row["status"])]
                        group["paired_tables"] += 1
                        for k in ("net", "ordinary_hu_income", "large_hu_income", "payments"):
                            group["associated_table_" + k] += pair["delta"][k]
                        for k, v in row.get("first_hand_delta", {}).items():
                            group["first_hand_" + k] += v
                        rows.append(row)
                        output.write(canonical(row).decode() + "\n")
                assert len(rows) == 32
                for k in ("net", "ordinary_hu_income", "large_hu_income", "payments"):
                    assert sum(r["table_delta"][k] for r in rows) == summary["mean_delta_per_complete_table"][k] * 32
                assert all(pin(Path(p)) == h for p, h in files.items())
        except BaseException as error:
            failure = {"type": type(error).__name__, "message": str(error)}
        stable = all(pin(Path(p)) == h for p, h in files.items())
        complete = failure is None and len(rows) == 32 and stable
        result = {"complete": complete, "failure": failure, "source_stable": stable,
            "actual_paired_tables_read": len(rows), "files": files,
            "status_counts": dict(Counter(r["status"] for r in rows)), "by_first_switch": dict(groups),
            "large_loss_pairs": [{k:r[k] for k in ("root", "rotation", "table_delta", "aligned_round_large_loss_observations")}
                | {"first_switch": r.get("switch"), "first_round_no": r.get("round_no")}
                for r in rows if r["table_delta"]["large_hu_income"] < 0],
            "rows_pin": pin(directory / "rows.jsonl"), "public_rows_pin": pin(directory / "original-public-first-rows.jsonl.gz"),
            "elapsed_monotonic_seconds": time.monotonic() - started,
            "new_scores_worlds_tables_models_HTTP": 0, "stage3_data_read": False,
            "natural_strength_or_single_action_causal_admission": False}
        save(directory / "CLOSED.json", result)
        assert complete, "只读诊断失败，原记录保留，不重做牌桌"
        print(json.dumps({k:result[k] for k in ("complete", "actual_paired_tables_read", "status_counts", "by_first_switch", "large_loss_pairs")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
