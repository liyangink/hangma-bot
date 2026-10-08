"""条件原件闭合且有跨来源机制信号后，仅准备a0的新8来源64完整桌。"""

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
from four_worker_campaign import validate
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents


def main():
    """费用资格非强度判断；不用已暴露32来源，不自动派发下一阶段。"""
    path = _project_file(_PROJECT_ROOT, HERE / "JOINT-NATURAL-STAGE-001-PLAN.json")
    assert not path.exists()
    budget_path = _project_file(_PROJECT_ROOT, HERE / "JOINT-NATURAL-SMALL-BUDGET-PREDECLARED.json")
    budget = json.loads(budget_path.read_text())
    assert budget["condition_result_unknown_when_frozen"] and budget["preparer_pin"] == pin(Path(__file__))
    condition_path = _project_file(_PROJECT_ROOT, HERE / "JOINT-REVISION-CONDITION-CLOSED.json")
    condition = json.loads(condition_path.read_text())
    terminal_path = _project_file(_PROJECT_ROOT, HERE / "joint-revision-condition/DISPATCH-CLOSED.json")
    followup_path = _project_file(_PROJECT_ROOT, HERE / "joint-revision-condition-followup/CLOSED.json")
    terminal, followup = (json.loads(p.read_text()) for p in (terminal_path, followup_path))
    assert condition["complete"] and condition["source_stable"] and condition["resources_released"]
    assert condition["counts"]["single_hand_dispatched"] == 320 and condition["historical_and_conditional_not_pooled"]
    assert terminal["complete"] and terminal["all_processes_naturally_waited"] and terminal["worker_returncodes"] == [0] * 4
    assert followup["complete"] and followup["reader_returncode"] == 0
    assert condition["plan_pin"] == terminal["plan_pin"] == followup["plan_pin"] == pin(_project_file(_PROJECT_ROOT, HERE / "JOINT-REVISION-CONDITION-PLAN.json"))
    sampled = condition["public_compatible_uniform"]
    assert sampled["sum_C_minus_A"]["net"] > 0, "条件总净差非正，停止小桌费用而非证明无效"
    positive_roots = [r["root_id"] for r in sampled["source_groups"] if r["sum_C_minus_A"]["net"] > 0]
    assert len(positive_roots) >= 2, "条件正差没有跨两个来源，不扩大桌费用"
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
    package = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-joint-revision-model-output")
    proposal = load_vip_parents([package], batch)[0]
    gatepath = _project_file(_PROJECT_ROOT, HERE / "joint-revision-qualification/CLOSED.json")
    gate = json.loads(gatepath.read_text())
    assert gate["complete"] and gate["mechanical_passed"] and gate["identity"] == proposal["identity"]
    old = json.loads((_project_file(_PROJECT_ROOT, PRIOR / "CONFIRMATION-PLAN.json")).read_text())
    parent = old["parent"]  # 线上S02；条件A357e不是完整桌验收基线。
    poolpath = _project_file(_PROJECT_ROOT, HERE / "FRESH-ROOTS-BEFORE-AUTHOR.json")
    pool = json.loads(poolpath.read_text())
    assert len(pool["development"]) == 64 and len(pool["independent_confirmation"]) == 128 and not pool["wall_generated"]
    assert not {r["seed"] for r in pool["development"]} & {r["seed"] for r in pool["independent_confirmation"]}
    roots = list(range(33, 41))
    assert all(not (_project_file(_PROJECT_ROOT, HERE / f"natural-development/root-{i:03d}")).exists() for i in roots)
    # 第一提案全部已闭阶段仅曝光001—032，不能把旧来源包装成新确认。
    for i in range(1, 4):
        prior = json.loads((_project_file(_PROJECT_ROOT, HERE / f"NATURAL-STAGE-{i:03d}-PLAN.json")).read_text())
        assert not set(prior["root_indices"]) & set(roots)
        assert json.loads((_project_file(_PROJECT_ROOT, HERE / f"natural-stage-{i:03d}-dispatch/CLOSED.json")).read_text())["complete"]
    child = {"label": "joint-main-route-settlement-base-a0c7218a", "identity": proposal["identity"],
        "source_file": str(package / "candidate.py"), "package": str(package), "qualification_file": str(gatepath)}
    tasks = [{"ordinal": o, "root": i, "rotation": r, "arm": a} for o, (i, r, a) in
        enumerate((i, r, a) for i in roots for r in range(4) for a in range(2))]
    files = [Path(__file__), budget_path, _project_file(_PROJECT_ROOT, HERE / "four_worker_campaign.py"), _project_file(_PROJECT_ROOT, HERE / "full_table_runtime.py"),
        _project_file(_PROJECT_ROOT, HERE / "staged_readout.py"), _project_file(_PROJECT_ROOT, HERE / "read_natural_stage.py"), _project_file(_PROJECT_ROOT, HERE / "STAGED-DEVELOPMENT-PROTOCOL.md"),
        _project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"), poolpath, condition_path, terminal_path, followup_path, gatepath,
        _project_file(_PROJECT_ROOT, HERE / "JOINT-REVISION-CONDITION-PLAN.json"), package / "candidate.py", package / "generation.json",
        Path(parent["source_file"]), _project_file(_PROJECT_ROOT, PRIOR / "CONFIRMATION-PLAN.json"), _project_file(_PROJECT_ROOT, PRIOR / "confirmation-dispatch/CLOSED.json"),
        _project_file(_PROJECT_ROOT, PRIOR / "t185_run_development.py"), _project_file(_PROJECT_ROOT, PRIOR / "t185_close_development.py"), _project_file(_PROJECT_ROOT, PRIOR / "evaluation_sharding.py"),
        _project_file(_PROJECT_ROOT, PRIOR / "readout_compat.py")]
    plan = {"schema": "t186-staged-development/1", "purpose": "joint_revision_exploratory_stage_001", "plan_path": str(path),
        "cpu_worker_count": 4, "rounds": 8, "rotations": [0, 1, 2, 3], "root_indices": roots,
        "roots": pool["development"], "parent": parent, "candidates": [child], "tasks": tasks,
        "planned_table_instances": 64, "maximum_actual_complete_table_instances": 64,
        "independent_confirmation_auto_dispatch": False, "next_stage_auto_dispatch": False,
        "dispatch_directory": str(_project_file(_PROJECT_ROOT, HERE / "joint-natural-stage-001-dispatch")),
        "output_directory": str(_project_file(_PROJECT_ROOT, HERE / "natural-development")),
        "prior_closed_pin": pin(_project_file(_PROJECT_ROOT, PRIOR / "confirmation-dispatch/CLOSED.json")),
        "files": {str(p): pin(p) for p in files}, "source_manifest": old["source_manifest"],
        "wall_seconds_per_table": 600, "minimum_free_bytes": 8589934592,
        "capture_limits": old["capture_limits"], "step_limit": old["step_limit"],
        "initial_dealer_physical": 0, "initial_scores_0_1_2_3": [0, 0, 0, 0],
        "bootstrap": {"replicates": 25000, "seed": 1862005, "unit": "independent_mother_four_seat_mean", "exploratory_not_time_uniform": True},
        "next_stage_budget": {"mean_net_positive_or_large_income_positive_and_mean_net_at_least": -10.0,
            "otherwise": "待修订或未决，不自动扩大；非已证明策略弱"},
        "execution_backend": "python_formula_with_current_native_hangma_distance",
        "conditional_budget_evidence": {"closed_pin": pin(condition_path), "positive_root_groups": positive_roots,
            "historical_controls_must_report_separately": True, "signal_not_natural_strength": True},
        "no_online_deadline_or_strength_admission": True}
    save(path, plan)
    _, _, lanes = validate(path)
    print(json.dumps({"prepared": True, "planned_tables": 64, "independent_roots": 8, "cpu_workers": len(lanes), "actual_tables": 0}))


if __name__ == "__main__":
    main()
