"""作者返回前冻结原355状态，不复制21MB重复材料，不按提案改变题目。"""

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
SOURCE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t187-family-combination-evolution-1')
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, HERE.parent / "t185-evidence-prioritized-joker-evolution-1")))
from common import pin, save


def main():
    """以明确路径与哈希复用完整原观察和76评分；实际子代仍评分710次。"""
    target = _project_file(_PROJECT_ROOT, HERE / "QUALIFICATION-PLAN.json")
    assert not target.exists()
    material_path = _project_file(_PROJECT_ROOT, SOURCE / "EXPLORATION-QUALIFICATION-PLAN.json")
    gate_path = _project_file(_PROJECT_ROOT, SOURCE / "exploration-qualification/CLOSED.json")
    rows_path = _project_file(_PROJECT_ROOT, SOURCE / "exploration-qualification/rows.jsonl")
    material, gate = [json.loads(p.read_text()) for p in (material_path, gate_path)]
    assert gate["complete"] and gate["mechanical_passed"] and gate["source_stable"]
    assert gate["plan_pin"] == pin(material_path) and gate["rows_pin"] == pin(rows_path)
    assert all(pin(Path(p)) == h for p, h in material["files"].items())
    assert len(material["cases"]) == 355
    prep = json.loads((_project_file(_PROJECT_ROOT, HERE / "AUTHOR-PREPARATION.json")).read_text())
    assert gate["identity"] == prep["formal_parent_identities"][1]
    paths = [
        Path(__file__), _project_file(_PROJECT_ROOT, HERE / "run_qualification.py"), _project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"),
        _project_file(_PROJECT_ROOT, HERE / "AUTHOR-PREPARATION.json"), material_path, gate_path, rows_path,
    ]
    save(target, {
        "complete": True, "formal_parent_identities": prep["formal_parent_identities"],
        "cases_source_file": str(material_path), "cached_76_rows_file": str(rows_path),
        "ordered_case_labels": [c["label"] for c in material["cases"]],
        "planned_actual_child_scores": 710, "cached_parent_new_scores": 0,
        "source_case_count": 355, "files": {str(p): pin(p) for p in paths},
        "candidate_identity_missing_until_real_author": True,
        "same_cases_count_and_order": True, "new_scores_worlds_models_HTTP": 0,
        "strength_or_original_deadline_admission": False,
    })
    print(json.dumps({"complete": True, "views": 355, "planned_child_scores": 710,
                      "reference_plan_bytes": material_path.stat().st_size,
                      "new_plan_bytes": target.stat().st_size}))


if __name__ == "__main__":
    main()
