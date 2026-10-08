"""封存已返回作者与363状态全评分；不收活条件续打。"""

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
import hashlib
import io
import json
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, HERE.parent / "t185-evidence-prioritized-joker-evolution-1")))
from common import pin, save
from t185_prepare_confirmation import background_priority


def main():
    """核生成、费用和全评分已闭，逐字节保存，原件保留。"""
    background_priority()
    target = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-QUALIFICATION-EVIDENCE-ARCHIVE.json")
    archive_path = _project_file(_PROJECT_ROOT, HERE / "AUTHOR-AND-QUALIFICATION-CLOSED.tar.gz")
    assert not target.exists() and not archive_path.exists()
    generation = json.loads((_project_file(_PROJECT_ROOT, HERE / "AUTHOR-model-output/generation.json")).read_text())
    gate = json.loads((_project_file(_PROJECT_ROOT, HERE / "qualification/CLOSED.json")).read_text())
    assert generation["status"] == "loaded_not_admitted" and generation["identity_stable"]
    assert generation["billing"]["status"] == "settled"
    assert gate["complete"] and gate["source_stable"] and gate["mechanical_passed"]
    assert gate["identity"] == generation["identity"] and gate["actual_score_attempts"] == 726
    names = [
        "AUTHOR-BATCH.json", "AUTHOR-BATCH.vip-eoh-ledger.json", "AUTHOR-PREPARATION.json",
        "AUTHOR-FEEDBACK.txt", "AUTHOR-START.json", "prepare_author.py", "run_author.py",
        "QUALIFICATION-PLAN.json", "QUALIFICATION-PLAN-V2.json", "LATER-QUALIFICATION-CASES.json",
        "prepare_qualification.py", "run_qualification.py", "prepare_later_qualification.py",
        "run_qualification_v2.py", "archive_author_qualification.py",
    ]
    paths = [_project_file(_PROJECT_ROOT, HERE / n) for n in names]
    for directory in ("AUTHOR-model-output", "qualification"):
        paths.extend(
            p for p in (_project_file(_PROJECT_ROOT, HERE / directory)).rglob("*")
            if p.is_file() and not p.is_symlink() and "code_snapshot" not in p.parts
        )
    originals = {str(p.relative_to(HERE)): pin(p) for p in paths}
    with tarfile.open(archive_path, "x:gz") as stored:
        for p in sorted(paths):
            raw = p.read_bytes()
            item = tarfile.TarInfo(str(p.relative_to(HERE)))
            item.size, item.mode, item.mtime = len(raw), 0o644, 0
            stored.addfile(item, io.BytesIO(raw))
    with tarfile.open(archive_path, "r:gz") as stored:
        assert sorted(stored.getnames()) == sorted(originals)
        for relative, expected in originals.items():
            raw = stored.extractfile(relative).read()
            assert {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()} == expected
    assert all(pin(_project_file(_PROJECT_ROOT, HERE / p)) == h for p, h in originals.items())
    proof = {
        "complete": True, "archive": archive_path.name, "archive_pin": pin(archive_path),
        "originals": originals, "verified_exact_bytes": True,
        "originals_retained_unchanged": True, "active_condition_excluded": True,
        "actual_completed_score_calls": 726, "actual_API_calls": 1,
        "source_stable_at_archive": True, "new_scores_models_worlds_tables_HTTP": 0,
    }
    save(target, proof)
    print(json.dumps({"complete": True, "members": len(originals),
                      "archive_bytes": archive_path.stat().st_size}))


if __name__ == "__main__":
    main()
