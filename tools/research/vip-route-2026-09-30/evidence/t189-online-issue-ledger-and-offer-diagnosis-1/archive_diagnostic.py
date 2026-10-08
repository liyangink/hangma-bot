"""逐字节封存24状态48评分及只读诊断，排除可能更新的状态文档。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t189-online-issue-ledger-and-offer-diagnosis-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import fcntl
import hashlib
import io
import json
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, HERE.parent / "t185-evidence-prioritized-joker-evolution-1")))
from common import OLD, pin, save
from t185_prepare_confirmation import background_priority


def main():
    """核全评分、原解释和研究槽释放，精确恢复全部成员，原件保留。"""
    background_priority()
    output, archive = _project_file(_PROJECT_ROOT, HERE / "DIAGNOSTIC-EVIDENCE-ARCHIVE.json"), _project_file(_PROJECT_ROOT, HERE / "DIAGNOSTIC-CLOSED.tar.gz")
    assert not output.exists() and not archive.exists()
    closed = json.loads((_project_file(_PROJECT_ROOT, HERE / "diagnostic/CLOSED.json")).read_text())
    summary = json.loads((_project_file(_PROJECT_ROOT, HERE / "DIAGNOSTIC-SUMMARY.json")).read_text())
    assert closed["complete"] and closed["source_stable"] and closed["actual_score_calls"] == 48
    assert closed["all_original_scores_traces_and_choices_exact"] and summary["complete"]
    assert all(pin(Path(p)) == h for p, h in summary["files"].items())
    with (OLD / ".resource-scheduling-worker-0.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    names = ["prepare_diagnostic.py", "run_diagnostic.py", "DIAGNOSTIC-PLAN.json", "instrument-c70.py",
        "summarize_diagnostic.py", "SUMMARY-FIRST-FAILED.json", "summarize_diagnostic-v2.py",
        "DIAGNOSTIC-SUMMARY.json", "archive_diagnostic.py"]
    paths = [_project_file(_PROJECT_ROOT, HERE / n) for n in names]
    paths.extend(p for p in (_project_file(_PROJECT_ROOT, HERE / "diagnostic")).rglob("*") if p.is_file() and not p.is_symlink())
    originals = {str(p.relative_to(HERE)): pin(p) for p in paths}
    assert len(originals) == len(paths)
    with tarfile.open(archive, "x:gz") as stored:
        for path in sorted(paths):
            raw = path.read_bytes()
            info = tarfile.TarInfo(str(path.relative_to(HERE)))
            info.size, info.mode, info.mtime = len(raw), 0o644, 0
            stored.addfile(info, io.BytesIO(raw))
    with tarfile.open(archive, "r:gz") as stored:
        assert sorted(stored.getnames()) == sorted(originals)
        for relative, expected in originals.items():
            raw = stored.extractfile(relative).read()
            assert {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()} == expected
    assert all(pin(_project_file(_PROJECT_ROOT, HERE / relative)) == expected for relative, expected in originals.items())
    save(output, {"complete": True, "archive": archive.name, "archive_pin": pin(archive),
        "originals": originals, "verified_exact_bytes": True, "originals_retained_unchanged": True,
        "resources_released": True, "actual_score_calls": 48, "public_states": 24,
        "new_scores_worlds_tables_models_HTTP": 0, "mutable_status_documents_excluded": True})
    print(json.dumps({"complete": True, "members": len(originals), "archive_bytes": archive.stat().st_size}))


if __name__ == "__main__":
    main()
