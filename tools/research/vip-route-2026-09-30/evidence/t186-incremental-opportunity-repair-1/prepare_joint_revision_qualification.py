"""为新联合公式封存公开机械面板，复用已核357e父分而非重算父代。"""

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
import gzip
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0, str(PRIOR))
from common import pin, save
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents


def main():
    """原221状态加三个已闭自然阶段全部首分歧；不是指定动作答案或强度门。"""
    target = _project_file(_PROJECT_ROOT, HERE / "JOINT-REVISION-QUALIFICATION-PLAN.json")
    assert not target.exists()
    batchpath = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-BATCH.json")
    batch = VipEohBatch.read(batchpath)
    package = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-joint-revision-model-output")
    proposal = load_vip_parents([package], batch)[0]
    oldgate = _project_file(_PROJECT_ROOT, HERE / "qualification/CLOSED.json")
    gate = json.loads(oldgate.read_text())
    assert gate["complete"] and gate["mechanical_passed"] and gate["source_stable"]
    assert all(pin(Path(p)) == h for p, h in gate["files"].items())
    parent = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-resource-release-metadata-repaired")
    parents = load_vip_parents([parent], batch)
    assert gate["identity"] == parents[0]["identity"]
    referencefile = _project_file(_PROJECT_ROOT, HERE / "qualification/rows.jsonl")
    assert gate["rows_pin"] == pin(referencefile)
    reference = {r["label"]: r for r in map(json.loads, referencefile.read_text().splitlines())}
    oldcases = _project_file(_PROJECT_ROOT, HERE / "CASES.json")
    cases = []
    for original in json.loads(oldcases.read_text())["cases"]:
        r = reference[original["label"]]
        cases.append({"label": original["label"], "root_id": original["root_id"],
            "classes": original["classes"], "observation": original["observation"],
            "window_key": original["window_key"], "view_sha256": r["view_sha256"],
            "parent_first": r["candidate_first"]})
    assert len(cases) == 221
    files = {str(p): pin(p) for p in (Path(__file__), _project_file(_PROJECT_ROOT, HERE / "run_joint_revision_qualification.py"),
        batchpath, oldgate, referencefile, oldcases, parent / "generation.json", parent / "candidate.py",
        package / "generation.json", package / "candidate.py")}
    for stage in (1, 2, 3):
        directory = _project_file(_PROJECT_ROOT, HERE / f"natural-stage-{stage:03d}-paths")
        closedpath = directory / "CLOSED.json"
        closed = json.loads(closedpath.read_text())
        assert closed["complete"] and closed["source_stable"]
        raw = directory / "original-public-first-rows.jsonl.gz"
        assert closed["public_rows_pin"] == pin(raw)
        files[str(raw)] = pin(raw)
        files[str(closedpath)] = pin(closedpath)
        with gzip.open(raw, "rt") as stream:
            for line in stream:
                r = json.loads(line)
                child = r["child_original_row"]
                cases.append({"label": f"development-stage{stage}:{r['root']:03d}:{r['rotation']}",
                    "root_id": child["window_key"]["game_id"],
                    "classes": ["closed_natural_first_divergence", f"white_count_{child['white_count']}"],
                    "observation": child["observation"], "window_key": child["window_key"],
                    "view_sha256": child["scoring_calls"][0]["input_capture"]["view_sha256"],
                    "parent_first": child["selected_action_key"]})
    assert len({c["label"] for c in cases}) == len(cases) <= 512
    assert all(pin(Path(p)) == h for p, h in files.items())
    result = {"schema": "t186-joint-revision-public-qualification/1", "complete": True,
              "candidate_identity": proposal["identity"], "formal_parent_identity": parents[0]["identity"],
              "cases": cases, "files": files, "planned_actual_scores": len(cases) * 2,
              "cached_parent_scores_new_charge": 0, "strength_or_original_deadline_admission": False,
              "new_scores_worlds_tables_models_HTTP": 0}
    save(target, result)
    print(json.dumps({"prepared": True, "public_cases": len(cases), "planned_scores": len(cases) * 2,
                      "new_parent_scores": 0, "new_worlds_tables_models_HTTP": 0}))


if __name__ == "__main__":
    main()
