#!/usr/bin/env python3
"""C24 直接检验：父代是否「最小向听优先」（lexicographic）。

对全部 32,374 个真实窗口：取父代实际提交的动作（plan_rank1）的 shanten_after，
与同一窗口全部合法候选的 shanten_after 最小值比较。
若「提交动作的向听 > 候选最小向听」的窗口数为 0，则父代在每一个真实窗口里都是最小向听优先。
"""
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
    windows = 0
    suboptimal = 0
    examples = []
    better_by = collections.Counter()
    for row in p6_lib.iter_rooms(p6_lib.ROOMS_PRIMARY + p6_lib.ROOMS_EXTRA):
        windows += 1
        view = row["view"]
        key = row.get("plan_rank1")
        submitted = None
        best = None
        for action in view.get("actions") or ():
            sh = action.get("shanten_after")
            if isinstance(sh, int) and sh >= 0:
                if best is None or sh < best:
                    best = sh
                if action.get("action_key") == key:
                    submitted = sh
        if submitted is None or best is None:
            continue
        if submitted > best:
            suboptimal += 1
            better_by[submitted - best] += 1
            if len(examples) < 8:
                examples.append((row.get("game_id"), key, submitted, best))
    rate = 100.0 * suboptimal / max(1, windows)
    print("窗口数 =", windows, "；提交动作向听 > 同窗最小向听的窗口数 =", suboptimal, "（%.4f%%）" % rate)
    print("超出量分布 =", dict(better_by))
    print("样例（game_id, 提交动作, 其向听, 同窗最小向听）：")
    for item in examples:
        print("  ", item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
