#!/usr/bin/env python3
"""主审：C12 回退窗口的立刻胡番数分布——判断它是不是「番值不变的空转」。"""
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

CAND = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates/OPTY-R18-C12-DEFERFALLBACK-ALL.py')


def kind_of(key):
    return key.split(":", 1)[0] if ":" in key else key


def chosen_entry(entries):
    return min(entries, key=lambda e: (-float(e["score"]), e["action_key"]))


def main() -> int:
    namespace = {"__name__": "frozen"}
    exec(compile(p6_lib.frozen_source(), "frozen", "exec"), namespace)
    parent = namespace["score_actions"]
    cand = p6_lib.compile_candidate(CAND)

    fans = collections.Counter()
    all_fans = collections.Counter()
    baotou_now = collections.Counter()
    for row in p6_lib.iter_rooms(p6_lib.ROOMS_PRIMARY + p6_lib.ROOMS_EXTRA):
        view = row["view"]
        try:
            pe = parent(view)["entries"]
            ce = cand(view)["entries"]
        except Exception:
            continue
        base = chosen_entry(pe)
        new = chosen_entry(ce)
        top = base
        info = (top.get("trace") or {}).get("hu_vs_nonwealth_baotou_cf") or {}
        if "hu" in {kind_of(e["action_key"]) for e in pe}:
            all_fans[info.get("hu_fan")] += 1
        if base["action_key"] == new["action_key"]:
            continue
        fans[info.get("hu_fan")] += 1
        vis = view.get("visible_state") or {}
        rs = vis.get("rule_state") or {}
        baotou_now[bool(rs.get("baotou"))] += 1
    print("## 全部 hu 合法窗的立刻胡番数（父代 trace.hu_fan）")
    print("   ", dict(sorted(all_fans.items(), key=lambda kv: (kv[0] is None, kv[0]))))
    print()
    print("## C12 改选窗（83 个）的立刻胡番数")
    print("   ", dict(sorted(fans.items(), key=lambda kv: (kv[0] is None, kv[0]))))
    print()
    print("## C12 改选窗里，我方当前是否已处于爆头态（rule_state.baotou）")
    print("   ", dict(baotou_now))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
