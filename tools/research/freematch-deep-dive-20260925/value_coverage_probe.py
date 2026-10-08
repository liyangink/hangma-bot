#!/usr/bin/env python3
"""主审：真实窗口里「未知动作」（value_coverage 不完整 → 被沉底）的占比。

如果这个占比不可忽略，那么提高 ValueAnalysisLimits 的预算就是一个从未测过的
**资源轴**（不改任何打分，只让更多候选拿到已生产事实）。
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
    namespace = {"__name__": "frozen"}
    exec(compile(p6_lib.frozen_source(), "frozen", "exec"), namespace)
    parent = namespace["score_actions"]

    c = collections.Counter()
    cover = collections.Counter()
    for row in p6_lib.iter_rooms(p6_lib.ROOMS_PRIMARY + p6_lib.ROOMS_EXTRA):
        view = row["view"]
        c["windows"] += 1
        try:
            entries = parent(view)["entries"]
        except Exception:
            c["error"] += 1
            continue
        c["entries"] += len(entries)
        for e in entries:
            t = e.get("trace") or {}
            if t.get("unknown") is True:
                c["unknown"] += 1
        for action in view.get("actions") or []:
            if action.get("is_legal") is True:
                cover[str(action.get("value_coverage"))] += 1
    print("窗口 %d，条目 %d，unknown 条目 %d（%.4f%%）"
          % (c["windows"], c["entries"], c["unknown"],
             100.0 * c["unknown"] / max(1, c["entries"])))
    print("异常 %d" % c["error"])
    print()
    print("## 合法动作的 value_coverage 分布（政策拿到的原始事实）")
    tot = sum(cover.values()) or 1
    for k, v in cover.most_common():
        print("- %-12s %7d  (%.2f%%)" % (k, v, 100.0 * v / tot))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
