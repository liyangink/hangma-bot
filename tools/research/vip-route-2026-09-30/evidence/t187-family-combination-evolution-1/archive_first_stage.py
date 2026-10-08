"""将已闭小批读回与成本诊断原件压缩归档；不删除或改写冻结原件。"""

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
import io
import json
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1')
sys.path.insert(0, str(PRIOR))
from common import pin, save


def archive(name, paths):
    """仅收普通文件，逐字节读回核验；恢复前须核目标，禁止覆盖不同原件。"""
    target = _project_file(_PROJECT_ROOT, HERE / name)
    assert not target.exists()
    unique = sorted(set(paths))
    originals = {str(p.relative_to(HERE)): pin(p) for p in unique}
    with tarfile.open(target, "x:gz") as output:
        for p in unique:
            assert p.is_file() and not p.is_symlink()
            raw = p.read_bytes()
            item = tarfile.TarInfo(str(p.relative_to(HERE)))
            item.size, item.mode, item.mtime = len(raw), 0o644, 0
            output.addfile(item, io.BytesIO(raw))
    with tarfile.open(target, "r:gz") as stored:
        assert sorted(stored.getnames()) == sorted(originals)
        for member_name, expected in originals.items():
            raw = stored.extractfile(member_name).read()
            import hashlib
            assert {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()} == expected
    assert all(pin(_project_file(_PROJECT_ROOT, HERE / p)) == h for p, h in originals.items())
    return {"archive": target.name, "archive_pin": pin(target), "originals": originals,
        "uncompressed_bytes": sum(p["bytes"] for p in originals.values()),
        "original_files_retained_unchanged": True, "verified_exact_bytes": True}


def main():
    """只封存首作者已闭实验；不混入第二作者、总费用账和待判机械任务。"""
    from t185_prepare_confirmation import background_priority
    background_priority()
    target = _project_file(_PROJECT_ROOT, HERE / "FIRST-STAGE-EVIDENCE-ARCHIVE.json")
    assert not target.exists()
    mechanical = json.loads((_project_file(_PROJECT_ROOT, HERE / "qualification/CLOSED.json")).read_text())
    conditional = json.loads((_project_file(_PROJECT_ROOT, HERE / "CONDITION-CLOSED.json")).read_text())
    budget = json.loads((_project_file(_PROJECT_ROOT, HERE / "PILOT-BUDGET-DECISION.json")).read_text())
    assert mechanical["complete"] and mechanical["mechanical_passed"] and mechanical["source_stable"]
    assert conditional["complete"] and conditional["source_stable"] and conditional["resources_released"]
    assert budget["complete"] and not budget["64_table_pilot_budget_eligible"]
    paths = []
    excludes = ("SECOND-", "EXPLORATION-", "prepare_second", "run_second", "prepare_exploration", "run_exploration")
    for p in HERE.iterdir():
        if not p.is_file() or p.is_symlink() or p.suffix not in (".py", ".json", ".txt", ".gz"):
            continue
        if p.name.startswith(excludes) or ".vip-eoh-ledger." in p.name or p.name == target.name:
            continue
        paths.append(p)
    for dirname in ("AUTHOR-family-model-output", "AUTHOR-family-metadata-repaired", "qualification", "condition"):
        for p in (_project_file(_PROJECT_ROOT, HERE / dirname)).rglob("*"):
            if p.is_file() and not p.is_symlink() and "code_snapshot" not in p.parts:
                paths.append(p)
    proof = archive("FIRST-STAGE-CLOSED-EVIDENCE.tar.gz", paths)
    proof.update({"complete": True, "scope": "首实际作者及零API修复、355机械状态、84条件续打的已闭原件",
        "actual_first_author_calls": 1, "metadata_replay_API_calls": 0,
        "actual_mechanical_score_calls": 710, "actual_conditional_score_calls": 2842,
        "actual_single_hands": 84, "actual_complete_tables": 0,
        "second_author_and_dynamic_total_ledger_excluded": True,
        "new_scores_models_HTTP_worlds_tables": 0})
    save(target, proof)
    print(json.dumps({"complete": True, "members": len(proof["originals"]),
        "raw_bytes": proof["uncompressed_bytes"], "archive_bytes": proof["archive_pin"]["bytes"],
        "verified_exact_bytes": proof["verified_exact_bytes"]}))


if __name__ == "__main__":
    main()
