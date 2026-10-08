"""封存第二作者条件续打全部原件；停止完整桌费用，不删除失败。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t187-family-combination-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import json
from archive_first_stage import HERE, archive, save
from t185_prepare_confirmation import background_priority


def main():
    """所有自然终态、真实评分、资源与费用结论核齐才精确归档。"""
    background_priority()
    target = _project_file(_PROJECT_ROOT, HERE / "EXPLORATION-CONDITION-EVIDENCE-ARCHIVE.json")
    assert not target.exists()
    closed = json.loads((_project_file(_PROJECT_ROOT, HERE / "EXPLORATION-CONDITION-CLOSED.json")).read_text())
    budget = json.loads((_project_file(_PROJECT_ROOT, HERE / "EXPLORATION-PILOT-BUDGET-DECISION.json")).read_text())
    assert closed["complete"] and closed["source_stable"] and closed["resources_released"]
    assert closed["counts"]["single_hand_dispatched"] == 84
    assert budget["complete"] and not budget["64_table_pilot_budget_eligible"]
    paths = [p for p in (_project_file(_PROJECT_ROOT, HERE / "exploration-condition")).rglob("*") if p.is_file() and not p.is_symlink()]
    paths.extend(_project_file(_PROJECT_ROOT, HERE / name) for name in ["EXPLORATION-CONDITION-PLAN.json", "EXPLORATION-CONDITION-CLOSED.json",
        "EXPLORATION-PILOT-BUDGET-DECISION.json", "prepare_exploration_condition.py", "run_exploration_condition.py",
        "close_exploration_condition.py", "close_exploration_budget.py", "archive_exploration_condition.py"])
    proof = archive("EXPLORATION-CONDITION-CLOSED.tar.gz", paths)
    proof.update({"complete": True, "actual_single_hands": 84,
        "actual_score_calls": closed["counts"]["actual_score_calls"], "actual_complete_tables": 0,
        "scope": "第二作者84单局条件续打全原件及负费用结论", "new_scores_models_HTTP_worlds_tables": 0})
    save(target, proof)
    print(json.dumps({"complete": True, "members": len(proof["originals"]),
        "raw_bytes": proof["uncompressed_bytes"], "archive_bytes": proof["archive_pin"]["bytes"]}))


if __name__ == "__main__":
    main()
