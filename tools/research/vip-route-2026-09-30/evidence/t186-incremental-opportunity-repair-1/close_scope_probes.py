"""合并两份已闭公开评分探针，核查等待修订与继承弃牌的实际范围。"""

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
from archive_stage1_evidence import archive


def main():
    """只读原评分及终态，按公开状态核数值与首选；不再评分或运行牌桌。"""
    records, changes, files = [], [], {str(Path(__file__)): pin(Path(__file__))}
    configurations = [
        ("formal-parent-scope-probe", "SCOPE-PROBE-PLAN.json", 27, 18),
        ("formal-parent-scope-probe-stage2", "SCOPE-PROBE-STAGE2-PLAN.json", 29, 24),
    ]
    archive_paths = [_project_file(_PROJECT_ROOT, HERE / "AUTHOR-NEXT-FEEDBACK-DRAFT.json"), _project_file(_PROJECT_ROOT, HERE / "AUTHOR-NEXT-FEEDBACK-DRAFT.txt")]
    for dirname, planname, expected_cases, expected_without_hu in configurations:
        directory, planpath = _project_file(_PROJECT_ROOT, HERE / dirname), _project_file(_PROJECT_ROOT, HERE / planname)
        closedpath = directory / "CLOSED.json"
        terminal = json.loads(closedpath.read_text())
        plan = json.loads(planpath.read_text())
        assert terminal["complete"] and terminal["failure"] is None and terminal["source_stable"]
        assert terminal["plan_pin"] == pin(planpath)
        assert all(pin(Path(p)) == h for p, h in plan["files"].items())
        assert terminal["rows_pin"] == pin(directory / "rows.jsonl")
        assert terminal["actual_score_attempts"] == 2 * expected_cases
        assert terminal["capture"]["terminal"]["terminal_valid"]
        rows = [json.loads(line) for line in (directory / "rows.jsonl").read_text().splitlines()]
        assert len(rows) == terminal["actual_completed_cases"] == expected_cases
        assert [r["label"] for r in rows] == [c["label"] for c in plan["cases"]]
        unanchored = []
        for row, case in zip(rows, plan["cases"]):
            assert row["view_sha256"] == case["view_sha256"]
            numeric_equal = [(e["action_key"], e["score"]) for e in row["entries"][0]] == [
                (e["action_key"], e["score"]) for e in row["entries"][1]]
            assert numeric_equal == row["full_numeric_scores_equal"]
            assert row["first_equal"] == (row["formal_parent_first"] == row["new_candidate_first"])
            if not row["has_current_hu"]:
                unanchored.append(row)
                assert numeric_equal and row["first_equal"]
            if not row["first_equal"]:
                changes.append({"probe_directory": dirname, "original_window_key": case["window_key"], **{k: row[k] for k in (
                    "label", "view_sha256", "white_count", "has_current_hu", "formal_parent_first",
                    "new_candidate_first", "operations", "score_monotonic_seconds")}})
        assert len(unanchored) == expected_without_hu == terminal["without_current_hu_cases"]
        records.append({"directory": dirname, "plan_pin": pin(planpath), "closed_pin": pin(closedpath),
                        "actual_cases": len(rows), "actual_scores": 2 * len(rows),
                        "without_current_hu_cases": len(unanchored)})
        for p in directory.iterdir():
            if p.is_file():
                archive_paths.append(p)
                files[str(p)] = pin(p)
        archive_paths.append(planpath)
        files[str(planpath)] = pin(planpath)
    # 换座的完整公开view及事件序号可以不同；独立来源由原game_id核对。
    changed_roots = {c["original_window_key"]["game_id"] for c in changes}
    assert len(changes) == 2 and len(changed_roots) == 1
    result = {"complete": True, "files": files, "probes": records, "actual_cases": 56,
              "actual_scores": 112, "without_current_hu_cases": 42,
              "without_current_hu_full_numeric_scores_equal": True,
              "actual_changed_first_choices": changes, "changed_independent_development_roots": len(changed_roots),
              "scope": "正式9adb父代与357e修订，已闭前16开发来源的全部首分歧公开状态；不是全状态证明",
              "strength_or_original_deadline_admission": False, "new_scores_worlds_tables_models_HTTP": 0}
    resultpath = _project_file(_PROJECT_ROOT, HERE / "FORMAL-PARENT-SCOPE-READBACK-006.json")
    assert not resultpath.exists()
    save(resultpath, result)
    assert all(pin(Path(p)) == h for p, h in files.items())
    archive_paths.extend([resultpath, _project_file(_PROJECT_ROOT, HERE / "SCOPE-READBACK-DEVELOPMENT-FAILURE-006.json"),
                          _project_file(_PROJECT_ROOT, HERE / "close_scope_probes-original-failed-006.py.gz")])
    manifestpath = _project_file(_PROJECT_ROOT, HERE / "SCOPE-EVIDENCE-ARCHIVE-006.json")
    assert not manifestpath.exists()
    save(manifestpath, {"archive": archive("SCOPE-CLOSED-AND-FEEDBACK-DRAFT-006.tar.gz", archive_paths),
                       "original_files_retained_unchanged": True,
                       "draft_not_sent_to_model": True, "new_scores_worlds_tables_models_HTTP": 0,
                       "restore": "先核归档及成员摘要；已有不同摘要的目标不得覆盖；恢复后逐文件复核。"})
    print(json.dumps({"complete": True, "actual_prior_scores": 112, "without_hu_equal": 42,
                      "first_changes": len(changes), "changed_independent_roots": 1,
                      "new_scores_worlds_tables_models_HTTP": 0}))


if __name__ == "__main__":
    main()
