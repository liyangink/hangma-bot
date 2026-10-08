"""把全部未覆盖的后续首次分歧纳入机械检查；不按候选结果挑题。"""

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
import gzip
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t187-family-combination-evolution-1')
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, HERE.parent / "t185-evidence-prioritized-joker-evolution-1")))
from common import pin, save


def main():
    """原计划保留，新计划增加所有同首手后续分歧，仍复用76完整评分。"""
    target = _project_file(_PROJECT_ROOT, HERE / "QUALIFICATION-PLAN-V2.json")
    assert not target.exists()
    original_path = _project_file(_PROJECT_ROOT, HERE / "QUALIFICATION-PLAN.json")
    original = json.loads(original_path.read_text())
    assert original["complete"] and all(pin(Path(p)) == h for p, h in original["files"].items())
    material = json.loads(Path(original["cases_source_file"]).read_text())
    used = {c["view_sha256"] for c in material["cases"]}
    source_path = _project_file(_PROJECT_ROOT, HERE / "LATER-DIVERGENCES-PUBLIC.jsonl.gz")
    closed_path = _project_file(_PROJECT_ROOT, HERE / "LATER-DIVERGENCES-CLOSED.json")
    closed = json.loads(closed_path.read_text())
    assert closed["complete"] and closed["public_rows_pin"] == pin(source_path)
    extra = []
    with gzip.open(source_path, "rt") as stream:
        for line in stream:
            row = json.loads(line)
            c = row["C"]
            digest = c["scoring_calls"][0]["input_capture"]["view_sha256"]
            if digest in used:
                continue
            used.add(digest)
            extra.append({
                "label": f"later:{row['target']:03d}:{row['sample']}:{row['shared_focal_actions']}",
                "root_id": c["window_key"]["game_id"],
                "classes": ["later_first_divergence", f"white_count_{c['white_count']}"],
                "observation": c["observation"], "window_key": c["window_key"],
                "view_sha256": digest, "parent_first": c["selected_action_key"],
                "cached_parent_first": {"6876": None, "current_76": c["selected_action_key"]},
                "original_target": row["target"], "original_sample": row["sample"],
                "same_public_prefix_verified": True,
            })
    assert len(extra) == closed["all_same_first_but_later_changed"] == 8
    extra_path = _project_file(_PROJECT_ROOT, HERE / "LATER-QUALIFICATION-CASES.json")
    save(extra_path, {"complete": True, "cases": extra, "new_scores_worlds_models_HTTP": 0})
    original["extra_cases_file"] = str(extra_path)
    original["ordered_case_labels"].extend(c["label"] for c in extra)
    original["planned_actual_child_scores"] = 2 * len(original["ordered_case_labels"])
    original["source_case_count"] = len(original["ordered_case_labels"])
    original["original_355_case_plan_pin"] = pin(original_path)
    for p in (Path(__file__), _project_file(_PROJECT_ROOT, HERE / "run_qualification_v2.py"), original_path, extra_path, source_path, closed_path):
        original["files"][str(p)] = pin(p)
    save(target, original)
    print(json.dumps({"complete": True, "original_views": 355, "all_new_later_views": 8,
                      "total_views": 363, "planned_actual_child_scores": 726,
                      "candidate_output_not_read": True}))


if __name__ == "__main__":
    main()
