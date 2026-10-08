"""封存四桌已知S02执行器预检；这是工程费用，不是新候选成绩。"""

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
from hangma_bot.offline.vip_eoh_generate import VipEohBatch
from four_worker_campaign import validate


def main():
    """仅用已暴露旧来源及S02四换座，验证真实四worker与收据闭合。"""
    old = json.loads((_project_file(_PROJECT_ROOT, PRIOR / "CONFIRMATION-PLAN.json")).read_text())
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
    parent = old["parent"]
    assert batch.identity(Path(parent["source_file"]).read_text()) == parent["identity"]
    path = (_project_file(_PROJECT_ROOT, HERE / "RUNTIME-PREFLIGHT-PLAN.json")).resolve()
    files = [Path(__file__), _project_file(_PROJECT_ROOT, HERE / "four_worker_campaign.py"), _project_file(_PROJECT_ROOT, HERE / "full_table_runtime.py"),
        _project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"), Path(parent["source_file"]), _project_file(_PROJECT_ROOT, PRIOR / "CONFIRMATION-PLAN.json"),
        _project_file(_PROJECT_ROOT, PRIOR / "confirmation-dispatch/CLOSED.json"), _project_file(_PROJECT_ROOT, PRIOR / "t185_run_development.py"),
        _project_file(_PROJECT_ROOT, PRIOR / "t185_close_development.py"), _project_file(_PROJECT_ROOT, PRIOR / "evaluation_sharding.py")]
    plan = {"schema": "t186-staged-development/1", "purpose": "runtime_preflight", "plan_path": str(path),
        "cpu_worker_count": 4, "rounds": 8, "rotations": [0, 1, 2, 3], "root_indices": [1],
        "roots": old["roots"][:64], "parent": parent, "candidates": [],
        "tasks": [{"ordinal": r, "root": 1, "rotation": r, "arm": 0} for r in range(4)],
        "planned_table_instances": 4, "independent_confirmation_auto_dispatch": False,
        "dispatch_directory": str(_project_file(_PROJECT_ROOT, HERE / "runtime-preflight-dispatch")),
        "output_directory": str(_project_file(_PROJECT_ROOT, HERE / "runtime-preflight-tables")),
        "prior_closed_pin": pin(_project_file(_PROJECT_ROOT, PRIOR / "confirmation-dispatch/CLOSED.json")),
        "files": {str(p): pin(p) for p in files}, "source_manifest": old["source_manifest"],
        "wall_seconds_per_table": 600, "minimum_free_bytes": 8589934592,
        "capture_limits": old["capture_limits"], "step_limit": old["step_limit"],
        "initial_dealer_physical": 0, "initial_scores_0_1_2_3": [0, 0, 0, 0],
        "not_candidate_strength_or_actual_speedup_evidence": True}
    save(path, plan)
    _, _, lanes = validate(path)
    print(json.dumps({"prepared": True, "planned_infrastructure_tables": 4,
        "actual_tables": 0, "lane_sizes": [len(v) for v in lanes]}))


if __name__ == "__main__":
    main()
