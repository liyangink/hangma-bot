"""封存首新自由赛已闭包并实际恢复验签，不改运行原件或再发网络请求。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/first-free-room-archive'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from hangma_bot.adapters.recording.bundle import extract_bundle


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def main():
    """以低CPU/IO优先级复制原归档；内部逐成员由公开归档接口核验。"""
    os.nice(15)
    priority = subprocess.run(["taskpolicy", "-b", "-p", str(os.getpid())], capture_output=True)
    assert priority.returncode == 0
    assert json.loads((_project_file(_PROJECT_ROOT, HERE / "FIRST-FREE-ROOM-CLOSED.json")).read_text())["resources_zero"]
    job = _project_file(_PROJECT_ROOT, ROOT / "artifacts/sessions/t191-live-batch-001-free/postgame/20261005T133350Z-da2c76bd")
    report = json.loads((job / "report.json").read_text())
    assert report["audit_complete"] and report["bundle_verified"]
    original = job / report["archive"]
    raw = original.read_bytes()
    expected = report["archive_sha256"]
    assert hashlib.sha256(raw).hexdigest() == expected
    out = _project_file(_PROJECT_ROOT, HERE / "first-free-room-archive")
    out.mkdir(exist_ok=False)
    target = out / "closed-room.tar.gz"
    shutil.copy2(original, target)
    assert target.read_bytes() == raw
    (out / "closed-room.tar.gz.sha256").write_text(expected + "  " + target.name + "\n")
    with tempfile.TemporaryDirectory(prefix="t191-first-free-restore-") as temporary:
        result = extract_bundle(target, Path(temporary))
        assert result["ok"] is True
        files_count = result.get("files_checked", result.get("files_total"))
    value = {"schema": "t191-first-free-archive-verified/1", "complete": True,
        "archive": str(target.relative_to(ROOT)), "bytes": len(raw), "sha256": expected,
        "original_archive": str(original.relative_to(ROOT)),
        "all_members_actually_restored_and_verified": True, "files_checked": files_count,
        "actual_extract_report_keys": sorted(result), "original_preserved": True,
        "cpu_nice": 15, "io_priority_exit_code": priority.returncode,
        "new_models_worlds_scores_tables_HTTP": 0,
        "no_strength_full_score_or_official_tournament_pass_claim": True}
    with (out / "VERIFIED.json").open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(value, ensure_ascii=False))


if __name__ == "__main__":
    main()
