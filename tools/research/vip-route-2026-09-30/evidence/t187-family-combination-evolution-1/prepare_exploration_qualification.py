"""将第二次真实作者绑定原355状态，复用e8的精确同图全评分。"""

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
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0, str(PRIOR))
from common import pin, save
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents


def main():
    """读取完整原件后冻结独立执行计划；不更改旧面板、评分或来源顺序。"""
    target = _project_file(_PROJECT_ROOT, HERE / "EXPLORATION-QUALIFICATION-PLAN.json")
    assert not target.exists()
    original = _project_file(_PROJECT_ROOT, HERE / "QUALIFICATION-PLAN.json")
    plan = json.loads(original.read_text())
    assert plan["complete"] and all(pin(Path(p)) == h for p, h in plan["files"].items())
    gatepath = _project_file(_PROJECT_ROOT, HERE / "qualification/CLOSED.json")
    gate = json.loads(gatepath.read_text())
    rows_path = _project_file(_PROJECT_ROOT, HERE / "qualification/rows.jsonl")
    assert gate["complete"] and gate["mechanical_passed"] and gate["source_stable"]
    assert gate["rows_pin"] == pin(rows_path)
    reference = {r["label"]: r for r in map(json.loads, rows_path.read_text().splitlines())}
    assert len(reference) == len(plan["cases"]) == 355
    for case in plan["cases"]:
        row = reference[case["label"]]
        assert row["view_sha256"] == case["view_sha256"]
        case["parent_first"] = row["candidate_first"]
        case["cached_parent_first"]["e8"] = row["candidate_first"]
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json"))
    package = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-explore-model-output")
    proposal = load_vip_parents([package], batch)[0]
    parents_path = _project_file(_PROJECT_ROOT, HERE / "SECOND-AUTHOR-PREPARATION.json")
    prepared = json.loads(parents_path.read_text())
    actual_parents = load_vip_parents([Path(p) for p in prepared["formal_parent_paths"]], batch)
    assert [p["identity"] for p in actual_parents] == prepared["formal_parent_identities"]
    assert actual_parents[1]["identity"] == gate["identity"]
    plan.update({"candidate_package": str(package), "candidate_identity": proposal["identity"],
        "formal_parent_identities": prepared["formal_parent_identities"],
        "identity_missing_until_standard_author_return": False,
        "original_case_plan_pin": pin(original), "same_cases_count_and_order": True,
        "primary_comparison_cached_e8": True,
        "new_scores_worlds_tables_models_HTTP": 0})
    for p in (Path(__file__), _project_file(_PROJECT_ROOT, HERE / "run_exploration_qualification.py"), original, gatepath,
              rows_path, parents_path, package / "candidate.py", package / "generation.json"):
        plan["files"][str(p)] = pin(p)
    save(target, plan)
    print(json.dumps({"complete": True, "cases": 355, "planned_child_scores": 710,
        "candidate_id": proposal["identity"]["candidate_id"], "new_scores_models_HTTP": 0}))


if __name__ == "__main__":
    main()
