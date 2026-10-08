"""复用同一14来源诊断，比较新c70与线上S02；不按新成绩重选题。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t188-joint-score-mechanism-1'

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
SOURCE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t187-family-combination-evolution-1')
sys.path.insert(0, str(PRIOR))
from common import pin, save
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents


def main():
    """原公开窗口、隐藏抽样键、对手与预算不变；绑定全新真实评分。"""
    target = _project_file(_PROJECT_ROOT, HERE / "CONDITION-PLAN.json")
    assert not target.exists()
    original = _project_file(_PROJECT_ROOT, SOURCE / "EXPLORATION-CONDITION-PLAN.json")
    plan = json.loads(original.read_text())
    assert all(pin(Path(p)) == h for p, h in plan["files"].items())
    old_closed = json.loads((_project_file(_PROJECT_ROOT, SOURCE / "EXPLORATION-CONDITION-CLOSED.json")).read_text())
    assert old_closed["complete"] and old_closed["source_stable"]
    gatepath = _project_file(_PROJECT_ROOT, HERE / "qualification/CLOSED.json")
    rowsfile = _project_file(_PROJECT_ROOT, HERE / "qualification/rows.jsonl")
    gate = json.loads(gatepath.read_text())
    assert gate["complete"] and gate["mechanical_passed"] and gate["source_stable"]
    assert gate["rows_pin"] == pin(rowsfile)
    rows = {r["label"]: r for r in map(json.loads, rowsfile.read_text().splitlines())}
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
    package = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-model-output")
    child = load_vip_parents([package], batch)[0]
    assert child["identity"] == gate["identity"]
    assert batch.identity(Path(plan["arms_sources"]["parent"]["source_file"]).read_text()) == plan["arms_sources"]["parent"]["identity"]
    assert len(plan["targets"]) == 14 and plan["planned_single_hand_continuations"] == 84
    for t in plan["targets"]:
        row = rows[t["case"]["label"]]
        assert row["view_sha256"] == t["case"]["view_sha256"]
        assert sorted(e["action_key"] for e in row["entries"]) == t["case"]["legal_action_keys"]
        t["candidate_first"] = row["candidate_first"]
        t["parent_first"] = None
    plan["arms_sources"]["child"] = {"source_file": str(package / "candidate.py"), "identity": child["identity"]}
    for p in (Path(__file__), original, gatepath, rowsfile, _project_file(_PROJECT_ROOT, HERE / "QUALIFICATION-PLAN-V2.json"),
              _project_file(_PROJECT_ROOT, HERE / "run_condition.py"), _project_file(_PROJECT_ROOT, HERE / "close_condition.py"),
              package / "candidate.py", package / "generation.json"):
        plan["files"][str(p)] = pin(p)
    plan.update({"original_condition_plan_pin": pin(original), "same_14_target_count_and_order": True,
        "no_fresh_random_confirmation_pool_read": True,
        "C": "c70c1d80持续自行选择，首手与新已闭机械评分核同；不强制动作",
        "new_condition_target_coverage_for_all_78_switches": False,
        "sampling_and_environment_unchanged": True})
    save(target, plan)
    print(json.dumps({"complete": True, "targets": 14, "planned_single_hands": 84,
        "cpu_worker_count": 4, "candidate_id": child["identity"]["candidate_id"],
        "actual_scores_models_HTTP_worlds_tables": 0}))


if __name__ == "__main__":
    main()
