"""只读四桌S02与两次公开选择的真实成本，不把样本比例外推为总体加速。"""

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
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0, str(PRIOR))
from common import pin, save


def main():
    """直接汇总已记录单调时钟秒数；新评分、世界、牌桌和HTTP均为零。"""
    readout_path = _project_file(_PROJECT_ROOT, HERE / "runtime-preflight-dispatch/READOUT-CLOSED.json")
    readout = json.loads(readout_path.read_text())
    assert readout["complete"] and readout["source_stable"] and readout["actual_tables"] == 4
    files = {str(p): pin(p) for p in (Path(__file__), readout_path)}
    tables = []
    for seat in range(4):
        directory = _project_file(_PROJECT_ROOT, HERE / "runtime-preflight-tables/root-001" / f"seat-{seat}-arm-0")
        paths = [directory / x for x in ("CLOSURE.json", "focal-decisions.jsonl.gz")]
        for p in paths:
            assert readout["files"][str(p)] == pin(p)
            files[str(p)] = pin(p)
        closure = json.loads(paths[0].read_text())
        assert closure["complete"] and closure["failure"] is None
        values = []
        with gzip.open(paths[1], "rt") as stream:
            for line in stream:
                row = json.loads(line)
                assert row["c_self_scored"] and len(row["scoring_calls"]) == 1
                call = row["scoring_calls"][0]
                assert call["score_completed"] and call["actual_score_calls"] == 1
                values.append(call["score_monotonic_seconds"])
        assert len(values) == closure["actual_focal_score_calls"]
        tables.append({"rotation": seat, "actual_scores": len(values),
            "table_wall_seconds": closure["elapsed_monotonic_seconds"],
            "candidate_score_only_seconds": sum(values), "max_one_score_seconds": max(values)})
    total_score = sum(t["candidate_score_only_seconds"] for t in tables)
    total_wall = sum(t["table_wall_seconds"] for t in tables)
    public_choice = []
    for mode in ("plain", "profile"):
        path = _project_file(_PROJECT_ROOT, HERE / f"closed-choice-cost-v2-{mode}/CLOSED.json")
        d = json.loads(path.read_text())
        assert d["complete"] and d["source_stable"] and d["actual_score_calls"] == 1
        assert d["full_output_matches_closed_qualification"] and d["actual_operations"] == 781876
        files[str(path)] = pin(path)
        public_choice.append({"mode": mode, "label": d["label"], "phases_seconds": d["phases"],
            "actual_scores_preexisting": 1, "logical_wide_budget_not_online_deadline": True})
    assert all(pin(Path(p)) == h for p, h in files.items())
    output = _project_file(_PROJECT_ROOT, HERE / "COST-READBACK.json")
    assert not output.exists(), "只读报告不得覆盖原结果"
    save(output, {"complete": True, "files": files, "known_S02_one_source_four_rotations": tables,
        "total_candidate_score_seconds": total_score, "sum_table_wall_seconds": total_wall,
        "score_only_share_of_sum_table_wall": total_score / total_wall,
        "remaining_wall_not_cpu_function_attribution": True,
        "four_rotations_not_four_independent_sources": True,
        "not_new_candidate_population_cost_estimate": True, "public_choice_existing_records": public_choice,
        "profile_instrumentation_changes_cost_do_not_compare_absolute_times": True,
        "rules_phase_between_processes_unexplained_do_not_infer_acceleration": True,
        "production_source_or_formula_changed": False, "new_scores_worlds_tables_models_HTTP": 0})
    print(json.dumps({"complete": True, "actual_tables_read": 4, "actual_scores_read": 1410,
        "score_only_share": total_score / total_wall, "new_scores_worlds_tables_models_HTTP": 0}))


if __name__ == "__main__":
    main()
