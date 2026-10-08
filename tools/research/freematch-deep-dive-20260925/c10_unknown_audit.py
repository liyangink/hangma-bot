#!/usr/bin/env python3
"""检查 C10 候选是否会违反「未知动作必须沉底」这一父代不变量。"""
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

CAND = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates/OPTY-R18-C10-SECONDCHOICE.py')


def chosen_entry(entries):
    return min(entries, key=lambda e: (-float(e["score"]), e["action_key"]))


def main() -> int:
    namespace = {"__name__": "frozen"}
    exec(compile(p6_lib.frozen_source(), "frozen", "exec"), namespace)
    parent = namespace["score_actions"]
    cand = p6_lib.compile_candidate(CAND)

    stats = collections.Counter()
    for row in p6_lib.iter_rooms(p6_lib.ROOMS_PRIMARY + p6_lib.ROOMS_EXTRA):
        view = row["view"]
        stats["windows"] += 1
        try:
            pe = parent(view)["entries"]
            ce = cand(view)["entries"]
        except Exception:
            stats["error"] += 1
            continue
        pchosen = chosen_entry(pe)
        cchosen = chosen_entry(ce)
        if cchosen["action_key"] == pchosen["action_key"]:
            continue
        stats["changed"] += 1
        if (cchosen.get("trace") or {}).get("unknown") is True:
            stats["changed_to_unknown"] += 1
        # 被降级的那个（父代首选）是否是 unknown
        if (pchosen.get("trace") or {}).get("unknown") is True:
            stats["demoted_unknown"] += 1
    total = max(1, stats["windows"])
    print("窗口 %d，异常 %d" % (stats["windows"], stats["error"]))
    print("改选 %d (%.2f%%)" % (stats["changed"], 100.0 * stats["changed"] / total))
    print("改选到的动作是 unknown：%d (%.2f%% of changed)" % (
        stats["changed_to_unknown"],
        100.0 * stats["changed_to_unknown"] / max(1, stats["changed"])))
    print("被降级的父代首选是 unknown：%d" % stats["demoted_unknown"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
