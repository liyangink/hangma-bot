#!/usr/bin/env python3
"""G122：在 G111 冻结名单之外追加最新已归档完整自由赛房。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

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
from pathlib import Path
import tempfile
from datetime import datetime, timezone

import g111_current_free_cohort_snapshot as g111


HERE = Path(__file__).resolve().parent
PRIOR = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g111-current-free-cohort-20260928/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g122-current-free-cohort-20260928/result.json')


def sha(path: Path) -> str:
    """绑定上一快照与本次增量核查程序。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """复用 G111 权威房/桌核查，并逐房守恒已冻结的 217 房。"""
    if OUT.exists():
        raise FileExistsError("G122 已冻结，拒绝覆盖")
    old = json.loads(PRIOR.read_text(encoding="utf-8"))
    original = g111.OUT
    with tempfile.TemporaryDirectory(prefix="hangma-g122-") as directory:
        g111.OUT = Path(directory) / "snapshot.json"
        try:
            g111.main()
            result = json.loads(g111.OUT.read_text(encoding="utf-8"))
        finally:
            g111.OUT = original
    if old["complete_rooms"] != 217 or not set(old["included"]).issubset(result["included"]):
        raise ValueError("G122 G111 旧房没有全部保留")
    for room, row in old["included"].items():
        if row != result["included"][room]:
            raise ValueError("G122 旧完整房事实漂移：" + room)
    if (result["complete_rooms"] < 219 or
            result["complete_tables"] != result["complete_rooms"] * 10):
        raise ValueError("G122 最新完整房数或桌数不守恒")
    added = sorted(set(result["included"]) - set(old["included"]))
    if (len(added) != result["complete_rooms"] - old["complete_rooms"] or
            sum(result["included"][room]["our_score"] for room in added)
            != result["our_score"] - old["our_score"]):
        raise ValueError("G122 新增房与全体积分未守恒")
    result["schema"] = "g122-current-free-cohort-snapshot/1"
    result["source_sha256"].update({"g111_snapshot": sha(PRIOR),
                                    "g122_script": sha(Path(__file__))})
    result["captured_at_utc"] = datetime.now(timezone.utc).isoformat()
    result["added_since_g111"] = {
        room: result["included"][room]["our_score"] for room in added}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"complete_rooms": result["complete_rooms"],
                      "complete_tables": result["complete_tables"],
                      "our_score": result["our_score"],
                      "our_per_table": result["our_per_table"],
                      "added_since_g111": result["added_since_g111"]},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
