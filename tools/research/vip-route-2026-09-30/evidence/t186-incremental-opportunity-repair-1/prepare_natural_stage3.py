"""累计16来源全闭且费用准入后追加16新来源；不得自动进入独立确认。"""

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
import copy
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0, str(PRIOR))
from common import pin, save
from four_worker_campaign import validate, free_slots


def main():
    """按原费用协议封存新增128桌；保留原两阶段，使用来源017—032。"""
    second = _project_file(_PROJECT_ROOT, HERE / "NATURAL-STAGE-002-PLAN.json")
    plan, original_pin, _ = validate(second)
    directory = Path(plan["dispatch_directory"])
    closed = json.loads((directory / "CLOSED.json").read_text())
    summary = json.loads((directory / "CUMULATIVE-SUMMARY.json").read_text())
    follow = _project_file(_PROJECT_ROOT, HERE / "natural-stage-002-followup/CLOSED.json")
    assert json.loads(follow.read_text())["complete"]
    assert closed["complete"] and closed["resources_released"] and closed["worker_returncodes"] == [0]*4
    assert summary["complete"] and summary["actual_complete_tables"] == 128 and summary["independent_roots"] == 16
    assert summary["plan_pin"] == original_pin and summary["candidate_identity"] == plan["candidates"][0]["identity"]
    assert all(pin(Path(p)) == h for p,h in summary["files"].items())
    means = summary["mean_delta_per_complete_table"]
    assert means["net"] > 0 or (means["large_hu_income"] > 0 and means["net"] >= -10)
    assert summary["exploratory_next_stage_budget_eligible"] and summary["new_block_net_direction"] > 0
    free_slots()
    next_plan = copy.deepcopy(plan)
    path = _project_file(_PROJECT_ROOT, HERE / "NATURAL-STAGE-003-PLAN.json")
    assert not path.exists()
    next_plan.update(purpose="exploratory_stage_003", plan_path=str(path), root_indices=list(range(17,33)),
        dispatch_directory=str(_project_file(_PROJECT_ROOT, HERE / "natural-stage-003-dispatch")),
        prior_stage_plans=plan["prior_stage_plans"]+[str(second)], new_sources_only=True,
        planned_table_instances=128, maximum_actual_complete_table_instances=128,
        cumulative_planned_complete_tables=256)
    next_plan["tasks"] = [{"ordinal":o,"root":i,"rotation":r,"arm":a} for o,(i,r,a) in
        enumerate((i,r,a) for i in range(17,33) for r in range(4) for a in range(2))]
    for task in next_plan["tasks"]:
        destination = Path(plan["output_directory"])/f"root-{task['root']:03d}"/f"seat-{task['rotation']}-arm-{task['arm']}"
        assert not destination.exists()
    for p in (Path(__file__), second, directory/"CLOSED.json", directory/"CUMULATIVE-SUMMARY.json",
        directory/"SUMMARY.json", directory/"READOUT-CLOSED.json", follow,
        _project_file(_PROJECT_ROOT, HERE/"finish_natural_stage-v3.py"), _project_file(_PROJECT_ROOT, HERE/"read_natural_cumulative-v2.py"), _project_file(_PROJECT_ROOT, HERE/"CUMULATIVE-READER-PREFLIGHT.json")):
        next_plan["files"][str(p)] = pin(p)
    save(path, next_plan)
    _,_,lanes = validate(path)
    print(json.dumps({"frozen_new_sources":16,"new_planned_tables":128,"cumulative_planned_tables":256,
        "same_candidate_id":plan["candidates"][0]["identity"]["candidate_id"],"workers":len(lanes),"actual_new_tables":0}))


if __name__ == "__main__":
    main()
