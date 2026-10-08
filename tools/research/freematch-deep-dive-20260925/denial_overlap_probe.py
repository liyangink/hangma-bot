#!/usr/bin/env python3
"""主审：DENIAL25 的改选里，有多少已经被父代自带的 river_part（熟张 +3）覆盖？"""
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

CAND = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates/OPTY-R18-C17-DENIAL25.py')


def kind_of(key):
    return key.split(":", 1)[0] if ":" in key else key


def chosen_entry(entries):
    return min(entries, key=lambda e: (-float(e["score"]), e["action_key"]))


def main() -> int:
    namespace = {"__name__": "frozen"}
    exec(compile(p6_lib.frozen_source(), "frozen", "exec"), namespace)
    parent = namespace["score_actions"]
    cand = p6_lib.compile_candidate(CAND)

    c = collections.Counter()
    fam = collections.Counter()
    for row in p6_lib.iter_rooms(p6_lib.ROOMS_PRIMARY + p6_lib.ROOMS_EXTRA):
        view = row["view"]
        try:
            pe = parent(view)["entries"]
            ce = cand(view)["entries"]
        except Exception:
            c["error"] += 1
            continue
        c["windows"] += 1
        base = chosen_entry(pe)
        new = chosen_entry(ce)
        if base["action_key"] == new["action_key"]:
            continue
        c["changed"] += 1
        bt = base.get("trace") or {}
        nt = new.get("trace") or {}
        c["base_discard" if kind_of(base["action_key"]) == "discard" else "base_other"] += 1
        c["new_discard" if kind_of(new["action_key"]) == "discard" else "new_other"] += 1
        if kind_of(base["action_key"]) == "discard" and kind_of(new["action_key"]) == "discard":
            bf = float(bt.get("river_part") or 0.0)
            nf = float(nt.get("river_part") or 0.0)
            fam[(bf, nf)] += 1
    print("窗口 %d，改选 %d（%.2f%%），异常 %d"
          % (c["windows"], c["changed"], 100.0 * c["changed"] / max(1, c["windows"]), c["error"]))
    print("父代首选动作族：discard %d / 其他 %d" % (c["base_discard"], c["base_other"]))
    print("候选首选动作族：discard %d / 其他 %d" % (c["new_discard"], c["new_other"]))
    print()
    print("改选窗里 (父代 river_part, 候选 river_part) 分布：")
    for k, v in fam.most_common(10):
        print("  %s : %d" % (k, v))
    same = sum(v for (a, b), v in fam.items() if a == b)
    diff = sum(v for (a, b), v in fam.items() if a != b)
    tot = same + diff
    if tot:
        print()
        print("熟张状态相同：%d（%.1f%%）；不同：%d（%.1f%%）"
              % (same, 100.0 * same / tot, diff, 100.0 * diff / tot))
        print("⇒ 不同比例 = 父代自带的 river_part 在本可区分、却没区分的那部分窗口上的占比。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
