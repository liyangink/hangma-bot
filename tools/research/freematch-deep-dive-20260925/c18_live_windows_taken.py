#!/usr/bin/env python3
"""C18 前置诊断（第二步）：有「可加权番」的窗口里，父代实际提交的是不是它？

第一步已证：hand_progress 动作里 88.5% 没有 routes；有 routes 的 91% 番值恒为 1；
只有 1.202% 的动作 fan_weighted > 0，只出现在 2.71% 的窗口。

本步回答：这 2.71% 的窗口里，**父代实际提交（plan_rank1）的动作**是不是那张可加权弃牌？
若绝大多数已经是，则「按番值加权选牌」在弃牌层**已经吃满**，C18 的零改选率有两个独立原因：
（a）事实里几乎没有番；（b）有的那一点点，父代已经拿走。
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
P6 = _project_file(_PROJECT_ROOT, ROOT / ".team-work" / "p6-baotou-route")
sys.path.insert(0, str(P6))

import p6_lib  # noqa: E402


def fan_weighted_of(action) -> float:
    total = 0.0
    routes = action.get("routes")
    if not routes:
        return 0.0
    for route in routes:
        settlement = route.get("conditional_settlement")
        fan = None
        if settlement is not None:
            raw = settlement.get("fan")
            if raw is not None and raw is not True and raw is not False:
                fan = float(raw)
        if fan is None or fan <= 1.0:
            continue
        support = 0.0
        for tile in route.get("useful_tiles") or ():
            remaining = tile.get("remaining_estimate")
            if remaining is None or remaining is True or remaining is False:
                continue
            support += float(remaining)
        total += support * (fan - 1.0)
    return total


def main() -> int:
    windows = 0
    live_windows = 0
    taken = 0
    not_taken_examples = []
    best_values = collections.Counter()
    for row in p6_lib.iter_rooms(p6_lib.ROOMS_PRIMARY + p6_lib.ROOMS_EXTRA):
        view = row["view"]
        windows += 1
        live = {}
        for action in view.get("actions") or ():
            if action.get("fact_kind") != "hand_progress":
                continue
            shanten = action.get("shanten_after")
            if shanten is None or shanten is True or shanten is False or shanten < 0:
                continue
            value = fan_weighted_of(action)
            if value > 0:
                live[action.get("action_key")] = value
        if not live:
            continue
        live_windows += 1
        best = max(live.values())
        best_values[round(best, 1)] += 1
        submitted = row.get("plan_rank1")
        if submitted in live:
            taken += 1
        elif len(not_taken_examples) < 10:
            not_taken_examples.append((row.get("game_id"), submitted, sorted(live.items(), key=lambda kv: -kv[1])[:3]))
    print("窗口数 =", windows)
    print("含可加权动作的窗口 =", live_windows)
    print("其中父代实际提交的就是某张可加权动作 = %d (%.2f%%)" % (taken, 100.0 * taken / max(1, live_windows)))
    print("未取走的窗口数 =", live_windows - taken)
    print("窗口内最佳 fan_weighted 取值分布（前 12）= ", dict(sorted(best_values.items(), key=lambda kv: -kv[1])[:12]))
    print()
    print("未取走样例（game_id, 实际提交, 前三名可加权动作）：")
    for item in not_taken_examples:
        print("  ", item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
