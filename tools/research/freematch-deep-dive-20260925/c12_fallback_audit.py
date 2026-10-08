#!/usr/bin/env python3
"""主审：核对 C12 回退候选在真实窗口上的行为——「改到更慢向听 83」是不是口径假象。"""
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


def shanten_of(entry):
    trace = entry.get("trace") or {}
    for key in ("shanten_after", "combined_shanten", "shanten"):
        value = trace.get(key)
        if type(value) is int:
            return value
    return None


def main() -> int:
    namespace = {"__name__": "frozen"}
    exec(compile(p6_lib.frozen_source(), "frozen", "exec"), namespace)
    parent = namespace["score_actions"]
    cand = p6_lib.compile_candidate(CAND)

    stats = collections.Counter()
    pairs = collections.Counter()
    examples = []
    for row in p6_lib.iter_rooms(p6_lib.ROOMS_PRIMARY + p6_lib.ROOMS_EXTRA):
        view = row["view"]
        try:
            pe = parent(view)["entries"]
            ce = cand(view)["entries"]
        except Exception:
            stats["error"] += 1
            continue
        stats["windows"] += 1
        base = chosen_entry(pe)
        new = chosen_entry(ce)
        if base["action_key"] == new["action_key"]:
            continue
        stats["changed"] += 1
        stats["base_kind_" + kind_of(base["action_key"])] += 1
        stats["new_kind_" + kind_of(new["action_key"])] += 1
        bs, ns = shanten_of(base), shanten_of(new)
        pairs[(bs, ns)] += 1
        if len(examples) < 6:
            hu_entries = [e for e in pe if kind_of(e["action_key"]) == "hu"]
            examples.append({
                "base": base["action_key"], "base_shanten": bs,
                "new": new["action_key"], "new_shanten": ns,
                "hu_shanten": shanten_of(hu_entries[0]) if hu_entries else None,
                "hu_score": hu_entries[0]["score"] if hu_entries else None,
                "new_score": new["score"],
            })
    print("窗口 %d，改选 %d，异常 %d" % (stats["windows"], stats["changed"], stats["error"]))
    print("父代首选动作族：%s" % {k[10:]: v for k, v in stats.items() if k.startswith("base_kind_")})
    print("候选首选动作族：%s" % {k[9:]: v for k, v in stats.items() if k.startswith("new_kind_")})
    print()
    print("(父代 shanten_after, 候选 shanten_after) 分布：%s" % dict(pairs))
    print()
    for e in examples:
        print("  ", e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
