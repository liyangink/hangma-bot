"""归档已闭112评分和只读诊断；排除正在写入的真实作者输出及账本。"""

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
    """逐成员核原字节及源文件不变；保留全部原件，不重复评分。"""
    background_priority()
    output = _project_file(_PROJECT_ROOT, HERE / "DIAGNOSTICS-EVIDENCE-ARCHIVE.json")
    archive_path = _project_file(_PROJECT_ROOT, HERE / "CLOSED-DIAGNOSTICS.tar.gz")
    assert not output.exists() and not archive_path.exists()
    gate = json.loads((_project_file(_PROJECT_ROOT, HERE / "probes/CLOSED.json")).read_text())
    first = json.loads((_project_file(_PROJECT_ROOT, HERE / "FIRST-CHOICE-CLOSED.json")).read_text())
    later = json.loads((_project_file(_PROJECT_ROOT, HERE / "LATER-DIVERGENCES-CLOSED.json")).read_text())
    assert gate["complete"] and gate["source_stable"] and gate["actual_score_calls"] == 112
    assert first["complete"] and later["complete"]
    names = [
        "read_first_choices.py", "FIRST-CHOICE-PLAN.json", "FIRST-CHOICE-CLOSED.json",
        "FIRST-CHOICES.jsonl.gz", "prepare_probes.py", "run_probes.py", "PROBE-PREPARATION.json",
        "probe-I.py", "probe-D.py", "probe-E.py", "probe-DE.py", "read_later_divergences.py",
        "LATER-DIVERGENCES-PUBLIC.jsonl.gz", "LATER-DIVERGENCES-CLOSED.json", "archive_diagnostics.py",
    ]
    paths = [_project_file(_PROJECT_ROOT, HERE / name) for name in names]
    paths.extend(p for p in (_project_file(_PROJECT_ROOT, HERE / "probes")).rglob("*") if p.is_file() and not p.is_symlink())
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
    assert all(pin(_project_file(_PROJECT_ROOT, HERE / relative)) == h for relative, h in originals.items())
    save(output, {
        "complete": True, "archive": archive_path.name, "archive_pin": pin(archive_path),
        "originals": originals, "verified_exact_bytes": True,
        "originals_retained_unchanged": True, "active_author_and_ledger_excluded": True,
        "actual_completed_score_calls": 112, "new_scores_models_worlds_tables_HTTP": 0,
    })
    print(json.dumps({"complete": True, "members": len(originals),
                      "archive_bytes": archive_path.stat().st_size}))


if __name__ == "__main__":
    main()
