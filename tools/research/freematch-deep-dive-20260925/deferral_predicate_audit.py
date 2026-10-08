#!/usr/bin/env python3
"""主审：hu 合法窗里，弃胡覆盖为什么没触发——按 degrade_reason 分档。

覆盖定义见 r18_integrated_positive_v2.py:658-817。
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
import json
import sys
from pathlib import Path

ROOT = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / ".team-work" / "p6-baotou-route")))

import p6_lib  # noqa: E402


def kind_of(key):
    return key.split(":", 1)[0] if ":" in key else key


def chosen_entry(entries):
    return min(entries, key=lambda e: (-float(e["score"]), e["action_key"]))


def main() -> int:
    namespace = {"__name__": "frozen"}
    exec(compile(p6_lib.frozen_source(), "frozen", "exec"), namespace)
    parent = namespace["score_actions"]

    reasons = collections.Counter()
    took = 0
    total = 0
    hu_fans = collections.Counter()
    for row in p6_lib.iter_rooms(p6_lib.ROOMS_PRIMARY + p6_lib.ROOMS_EXTRA):
        view = row["view"]
        try:
            entries = parent(view)["entries"]
        except Exception:
            continue
        if not entries:
            continue
        kinds = {kind_of(e["action_key"]) for e in entries}
        if "hu" not in kinds:
            continue
        total += 1
        chosen = chosen_entry(entries)
        tr = chosen.get("trace") or {}
        info = tr.get("hu_vs_nonwealth_baotou_cf") or {}
        if kind_of(chosen["action_key"]) == "hu":
            took += 1
        reasons[str(info.get("degrade_reason"))] += 1
        if info.get("hu_fan") is not None:
            hu_fans[info.get("hu_fan")] += 1
    print("hu 合法窗 %d；其中父代选 hu %d、弃胡 %d" % (total, took, total - took))
    print()
    print("## 弃胡覆盖的 degrade_reason 分布\n")
    for k, v in reasons.most_common():
        print("- %-46s %4d  (%.1f%%)" % (k, v, 100.0 * v / total))
    print()
    print("## 立刻胡的番数分布（trace.hu_fan）\n")
    for k, v in sorted(hu_fans.items(), key=lambda kv: (kv[0] is None, kv[0])):
        print("- 番 %s：%d" % (k, v))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
