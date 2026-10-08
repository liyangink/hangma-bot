"""条件信号闭合后封存第一批64完整桌；不自动购买后续阶段或独立确认。"""

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
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0, str(PRIOR))
from common import pin, save
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents
from four_worker_campaign import validate


def main():
    """新来源先64桌；条件均值仅支持买小批，不冒充自然总体增强。"""
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
    original = json.loads((_project_file(_PROJECT_ROOT, PRIOR / "CONFIRMATION-PLAN.json")).read_text())
    parent = original["parent"]
    package = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-resource-release-metadata-repaired")
    proposal = load_vip_parents([package], batch)[0]
    gate = json.loads((_project_file(_PROJECT_ROOT, HERE / "qualification/CLOSED.json")).read_text())
    condition = json.loads((_project_file(_PROJECT_ROOT, HERE / "OPPORTUNITY-PROBE-CLOSED-v2.json")).read_text())
    assert gate["complete"] and gate["mechanical_passed"] and gate["source_stable"] and gate["identity"] == proposal["identity"]
    assert condition["complete"] and condition["source_stable"] and condition["resources_released"] and condition["counts"]["single_hand_dispatched"] == 108
    assert sum(t["four_conditional_C_minus_A"]["net"] for t in condition["target_summaries"]) > 0
    assert sum(t["four_conditional_C_minus_A"]["net"] > 0 for t in condition["target_summaries"]) >= 2
    pool = json.loads((_project_file(_PROJECT_ROOT, HERE / "FRESH-ROOTS-BEFORE-AUTHOR.json")).read_text())
    assert pool["not_in_author_prompt"] and not pool["wall_generated"] and len(pool["development"]) == 64 and len(pool["independent_confirmation"]) == 128
    assert not {r["seed"] for r in pool["development"]} & {r["seed"] for r in pool["independent_confirmation"]}
    child = {"label": "held-white-release-357e", "identity": proposal["identity"],
        "source_file": str(package / "candidate.py"), "package": str(package), "qualification_file": str(_project_file(_PROJECT_ROOT, HERE / "qualification/CLOSED.json"))}
    path = _project_file(_PROJECT_ROOT, HERE / "NATURAL-STAGE-001-PLAN.json")
    tasks = [{"ordinal": o, "root": i, "rotation": r, "arm": a} for o, (i, r, a) in
        enumerate((i, r, a) for i in range(1, 9) for r in range(4) for a in range(2))]
    files = [Path(__file__), _project_file(_PROJECT_ROOT, HERE / "four_worker_campaign.py"), _project_file(_PROJECT_ROOT, HERE / "full_table_runtime.py"), _project_file(_PROJECT_ROOT, HERE / "staged_readout.py"),
        _project_file(_PROJECT_ROOT, HERE / "read_natural_stage.py"), _project_file(_PROJECT_ROOT, HERE / "STAGED-DEVELOPMENT-PROTOCOL.md"), _project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"),
        _project_file(_PROJECT_ROOT, HERE / "FRESH-ROOTS-BEFORE-AUTHOR.json"), _project_file(_PROJECT_ROOT, HERE / "OPPORTUNITY-PROBE-CLOSED-v2.json"),
        _project_file(_PROJECT_ROOT, HERE / "opportunity-probe-v2/DISPATCH-CLOSED.json"), _project_file(_PROJECT_ROOT, HERE / "qualification/CLOSED.json"),
        package / "candidate.py", package / "generation.json", package / "DERIVATION.json",
        _project_file(_PROJECT_ROOT, HERE / "AUTHOR-resource-release-model-output/generation.json"), Path(parent["source_file"]),
        _project_file(_PROJECT_ROOT, PRIOR / "CONFIRMATION-PLAN.json"), _project_file(_PROJECT_ROOT, PRIOR / "confirmation-dispatch/CLOSED.json"),
        _project_file(_PROJECT_ROOT, PRIOR / "t185_run_development.py"), _project_file(_PROJECT_ROOT, PRIOR / "t185_close_development.py"), _project_file(_PROJECT_ROOT, PRIOR / "evaluation_sharding.py"),
        _project_file(_PROJECT_ROOT, PRIOR / "readout_compat.py")]
    plan = {"schema": "t186-staged-development/1", "purpose": "exploratory_stage_001", "plan_path": str(path),
        "cpu_worker_count": 4, "rounds": 8, "rotations": [0, 1, 2, 3], "root_indices": list(range(1, 9)),
        "roots": pool["development"], "parent": parent, "candidates": [child], "tasks": tasks,
        "planned_table_instances": 64, "maximum_actual_complete_table_instances": 64,
        "independent_confirmation_auto_dispatch": False, "next_stage_auto_dispatch": False,
        "dispatch_directory": str(_project_file(_PROJECT_ROOT, HERE / "natural-stage-001-dispatch")), "output_directory": str(_project_file(_PROJECT_ROOT, HERE / "natural-development")),
        "prior_closed_pin": pin(_project_file(_PROJECT_ROOT, PRIOR / "confirmation-dispatch/CLOSED.json")),
        "files": {str(p): pin(p) for p in files}, "source_manifest": original["source_manifest"],
        "wall_seconds_per_table": 600, "minimum_free_bytes": 8589934592,
        "capture_limits": original["capture_limits"], "step_limit": original["step_limit"],
        "initial_dealer_physical": 0, "initial_scores_0_1_2_3": [0, 0, 0, 0],
        "bootstrap": {"replicates": 25000, "seed": 1861005, "unit": "independent_mother_four_seat_mean", "exploratory_not_time_uniform": True},
        "next_stage_budget": {"mean_net_positive_or_large_income_positive_and_mean_net_at_least": -10.0,
            "otherwise": "待修订或未决，不自动扩大；非已证明策略弱"},
        "execution_backend": "python_formula_with_current_native_hangma_distance",
        "conditional_controls_boundary": "失胡类别来自已暴露历史；四个公开相容样本并未重现他家先胡风险，不把控制同选当风险校准成功。",
        "no_online_deadline_or_strength_admission": True}
    save(path, plan)
    _, _, lanes = validate(path)
    print(json.dumps({"prepared": True, "planned_tables": 64, "independent_roots": 8, "cpu_workers": len(lanes), "actual_tables": 0}))


if __name__ == "__main__":
    main()
