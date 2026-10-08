"""第一小批全对账且费用条件通过后追加8个新来源；不改已闭结果或公式。"""

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
from four_worker_campaign import validate


def main():
    """按预先规则买下一64桌；累计128桌仍为开发，不能自动进入独立确认。"""
    first = _project_file(_PROJECT_ROOT, HERE / "NATURAL-STAGE-001-PLAN.json")
    plan, original_pin, _ = validate(first)
    d = Path(plan["dispatch_directory"])
    closed = json.loads((d / "CLOSED.json").read_text())
    summary = json.loads((d / "SUMMARY.json").read_text())
    follow = _project_file(_PROJECT_ROOT, HERE / "natural-stage-001-followup/CLOSED.json")
    assert json.loads(follow.read_text())["complete"]
    assert closed["complete"] and closed["resources_released"] and closed["worker_returncodes"] == [0]*4
    assert summary["complete"] and summary["actual_complete_tables"] == 64 and summary["independent_roots"] == 8
    assert summary["plan_pin"] == original_pin and summary["candidate_identity"] == plan["candidates"][0]["identity"]
    means = summary["mean_delta_per_complete_table"]
    eligible = means["net"] > 0 or (means["large_hu_income"] > 0 and means["net"] >= -10)
    assert eligible and summary["exploratory_next_stage_budget_eligible"]
    next_plan = copy.deepcopy(plan)
    path = _project_file(_PROJECT_ROOT, HERE / "NATURAL-STAGE-002-PLAN.json")
    next_plan.update(purpose="exploratory_stage_002", plan_path=str(path), root_indices=list(range(9,17)),
        dispatch_directory=str(_project_file(_PROJECT_ROOT, HERE / "natural-stage-002-dispatch")), prior_stage_plans=[str(first)],
        new_sources_only=True, cumulative_planned_complete_tables=128)
    next_plan["tasks"] = [{"ordinal":o,"root":i,"rotation":r,"arm":a} for o,(i,r,a) in
        enumerate((i,r,a) for i in range(9,17) for r in range(4) for a in range(2))]
    for p in [Path(__file__), first, d / "CLOSED.json", d / "SUMMARY.json", d / "READOUT-CLOSED.json", follow,
              _project_file(_PROJECT_ROOT, HERE / "finish_natural_stage-v2.py"), _project_file(_PROJECT_ROOT, HERE / "read_natural_cumulative.py")]:
        next_plan["files"][str(p)] = pin(p)
    save(path, next_plan)
    _,_,lanes = validate(path)
    print(json.dumps({"frozen_new_sources":8,"new_planned_tables":64,"cumulative_planned_tables":128,
        "same_candidate_id":plan["candidates"][0]["identity"]["candidate_id"],"workers":len(lanes),"actual_new_tables":0}))


if __name__ == "__main__":
    main()
