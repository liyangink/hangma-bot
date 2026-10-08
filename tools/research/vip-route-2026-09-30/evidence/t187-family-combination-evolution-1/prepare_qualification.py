"""在作者返回前封存全公开机械面板；只读旧原件，缓存两父已有选择。"""

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
import gzip
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
LAST = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t186-incremental-opportunity-repair-1')
sys.path.insert(0, str(PRIOR))
from common import pin, save


def main():
    """固定333旧状态及22新首分歧，按精确view摘要匹配缓存；不评分或重跑。"""
    target = _project_file(_PROJECT_ROOT, HERE / "QUALIFICATION-PLAN.json")
    assert not target.exists()
    oldplanpath = _project_file(_PROJECT_ROOT, LAST / "JOINT-REVISION-QUALIFICATION-PLAN.json")
    oldgatepath = _project_file(_PROJECT_ROOT, LAST / "joint-revision-qualification/CLOSED.json")
    oldrows = _project_file(_PROJECT_ROOT, LAST / "joint-revision-qualification/rows.jsonl")
    oldplan, oldgate = [json.loads(p.read_text()) for p in (oldplanpath, oldgatepath)]
    assert oldgate["complete"] and oldgate["mechanical_passed"] and oldgate["source_stable"]
    assert oldgate["plan_pin"] == pin(oldplanpath) and oldgate["rows_pin"] == pin(oldrows)
    assert all(pin(Path(p)) == h for p, h in oldplan["files"].items())
    reference = {r["label"]: r for r in map(json.loads, oldrows.read_text().splitlines())}
    familygatepath = _project_file(_PROJECT_ROOT, PRIOR / "AUTHOR-speed-model-output-qualification/CLOSURE.json")
    familygate = json.loads(familygatepath.read_text())
    assert familygate["complete"] and familygate["source_stable"] and familygate["mechanical_passed"]
    assert all(pin(Path(p)) == h for p, h in familygate["files"].items())
    familyrows = {r["view_sha256"]: r for r in familygate["rows"]}
    def reference_choices(digest, last_first):
        """只在完整评分视图摘要一致时复用父A；None表示无缓存，不猜选择。"""
        familyrow = familyrows.get(digest)
        return {"6876": None if familyrow is None else familyrow["candidate_first"], "a0": last_first}
    cases = []
    for original in oldplan["cases"]:
        r = reference[original["label"]]
        assert r["view_sha256"] == original["view_sha256"]
        cases.append({"label": original["label"], "root_id": original["root_id"],
            "classes": original["classes"], "observation": original["observation"],
            "window_key": original["window_key"], "view_sha256": original["view_sha256"],
            "parent_first": r["candidate_first"],
            "cached_parent_first": reference_choices(r["view_sha256"], r["candidate_first"])})
    assert len(cases) == 333
    closedpath = _project_file(_PROJECT_ROOT, LAST / "joint-natural-stage-001-paths/CLOSED.json")
    publicpath = _project_file(_PROJECT_ROOT, LAST / "joint-natural-stage-001-paths/original-public-first-rows.jsonl.gz")
    closed = json.loads(closedpath.read_text())
    assert closed["complete"] and closed["actual_paired_tables_read"] == 32
    assert closed["public_rows_pin"] == pin(publicpath)
    with gzip.open(publicpath, "rt") as stream:
        for line in stream:
            r = json.loads(line)
            child = r["child_original_row"]
            digest = child["scoring_calls"][0]["input_capture"]["view_sha256"]
            cases.append({"label": f"joint-development:{r['root']:03d}:{r['rotation']}",
                "root_id": child["window_key"]["game_id"],
                "classes": ["closed_natural_first_divergence", f"white_count_{child['white_count']}"],
                "observation": child["observation"], "window_key": child["window_key"],
                "view_sha256": digest, "parent_first": child["selected_action_key"],
                "cached_parent_first": reference_choices(digest, child["selected_action_key"])})
    assert len(cases) == 355 and len({c["label"] for c in cases}) == 355
    files = {str(p): pin(p) for p in (Path(__file__), _project_file(_PROJECT_ROOT, HERE / "run_qualification.py"), _project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"),
        _project_file(_PROJECT_ROOT, HERE / "AUTHOR-PREPARATION.json"), oldplanpath, oldgatepath, oldrows, familygatepath, closedpath, publicpath)}
    assert all(pin(Path(p)) == h for p, h in files.items())
    prepared = json.loads((_project_file(_PROJECT_ROOT, HERE / "AUTHOR-PREPARATION.json")).read_text())
    assert prepared["complete"] and len(prepared["parent_identities"]) == 2
    save(target, {"schema": "t187-family-public-qualification/1", "complete": True,
        "candidate_package": str(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-family-model-output")),
        "formal_parent_identities": prepared["parent_identities"], "cases": cases, "files": files,
        "planned_actual_child_scores": len(cases) * 2, "planned_new_parent_scores": 0,
        "cached_6876_views": sum(c["cached_parent_first"]["6876"] is not None for c in cases),
        "cached_a0_views": len(cases), "identity_missing_until_standard_author_return": True,
        "new_scores_worlds_tables_models_HTTP": 0, "strength_or_original_deadline_admission": False})
    print(json.dumps({"complete": True, "cases": len(cases), "planned_child_scores": len(cases) * 2,
        "cached_6876_views": sum(c["cached_parent_first"]["6876"] is not None for c in cases),
        "new_scores_worlds_tables_models_HTTP": 0}))


if __name__ == "__main__":
    main()
