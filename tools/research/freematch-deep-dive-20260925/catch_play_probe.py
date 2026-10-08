#!/usr/bin/env python3
"""圈主（抓打圈）机制在真实自由赛里的出现频率与对我方动作面的影响。"""
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

import collections
import sys
from pathlib import Path

ROOT = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / ".team-work" / "p6-baotou-route")))

import p6_lib  # noqa: E402


def main() -> int:
    phase_cp = collections.Counter()
    cp_vals = collections.Counter()
    total = 0
    keys_seen = collections.Counter()
    for row in p6_lib.iter_rooms(p6_lib.ROOMS_PRIMARY + p6_lib.ROOMS_EXTRA):
        total += 1
        view = row["view"]
        vis = view.get("visible_state") or {}
        rs = vis.get("rule_state") or {}
        keys_seen.update(rs.keys())
        cp = rs.get("catch_play")
        cp_vals[repr(cp)] += 1
    print("真实窗口 %d" % total)
    print("rule_state 字段：%s" % dict(keys_seen))
    print("catch_play 取值分布：%s" % dict(cp_vals))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
