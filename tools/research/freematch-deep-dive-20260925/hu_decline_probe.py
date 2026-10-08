#!/usr/bin/env python3
"""主审：真实窗口里「hu 合法但父代没选 hu」的次数——判定 Q4.1 的「14 张已胡」是不是弃胡。"""
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


def kind_of(key):
    return key.split(":", 1)[0] if ":" in key else key


def chosen_entry(entries):
    return min(entries, key=lambda e: (-float(e["score"]), e["action_key"]))


def main() -> int:
    namespace = {"__name__": "frozen"}
    exec(compile(p6_lib.frozen_source(), "frozen", "exec"), namespace)
    parent = namespace["score_actions"]

    stats = collections.Counter()
    by_phase = collections.Counter()
    examples = []
    for row in p6_lib.iter_rooms(p6_lib.ROOMS_PRIMARY + p6_lib.ROOMS_EXTRA):
        view = row["view"]
        stats["windows"] += 1
        try:
            entries = parent(view)["entries"]
        except Exception:
            stats["error"] += 1
            continue
        if not entries:
            continue
        kinds = {kind_of(e["action_key"]) for e in entries}
        if "hu" not in kinds:
            continue
        stats["hu_legal"] += 1
        chosen = chosen_entry(entries)
        if kind_of(chosen["action_key"]) == "hu":
            stats["took_hu"] += 1
            continue
        stats["declined_hu"] += 1
        vis = view.get("visible_state") or {}
        win = view.get("window") or {}
        by_phase[str(win.get("phase") or row.get("phase"))] += 1
        if len(examples) < 15:
            examples.append({
                "phase": win.get("phase"),
                "round_no": win.get("round_no"),
                "trigger_seq": win.get("trigger_seq"),
                "chosen": chosen["action_key"],
                "chosen_score": chosen["score"],
                "hu_scores": [e["score"] for e in entries if kind_of(e["action_key"]) == "hu"],
                "hand": vis.get("my_hand"),
                "melds": (vis.get("melds") or [None])[vis.get("seat")] if isinstance(vis.get("seat"), int) else None,
            })
    print("真实窗口 %d" % stats["windows"])
    print("- hu 出现在合法候选里：%d" % stats["hu_legal"])
    print("- 父代选了 hu：%d" % stats["took_hu"])
    print("- **父代没选 hu（弃胡）**：%d" % stats["declined_hu"])
    print("- 弃胡的 phase 分布：%s" % dict(by_phase))
    print()
    print("逐例（前 15）：")
    for e in examples:
        print("  ", e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
