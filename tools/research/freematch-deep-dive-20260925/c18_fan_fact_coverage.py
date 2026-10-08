#!/usr/bin/env python3
"""C18 前置诊断：规则事实里到底有没有「可加权的番」？

在全部真实窗口上统计（只读 view，不跑任何策略搜索）：
  1. hand_progress 动作里 value_coverage 的分布；
  2. routes 的条数分布；
  3. routes 上 conditional_settlement.fan 的取值分布；
  4. 由此算出的 fan_weighted = Σ_routes Σ_useful remaining×(fan−1) 的分布，
     以及「所有动作的 fan_weighted 都为 0」的窗口占比。

若第 4 项几乎全是 0，则「番值加权进张」这一层在弃牌窗口上**没有可加权的番**，
C18 的零改选率就不是「父代已经最优」，而是「事实里没有这个维度」。
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


def main() -> int:
    windows = 0
    hand_progress_actions = 0
    coverage = collections.Counter()
    route_counts = collections.Counter()
    fan_values = collections.Counter()
    live_windows = 0
    windows_with_routes = 0
    fan_weighted_nonzero = 0
    sample_rows = []
    for row in p6_lib.iter_rooms(p6_lib.ROOMS_PRIMARY + p6_lib.ROOMS_EXTRA):
        view = row["view"]
        windows += 1
        window_live = False
        window_has_routes = False
        best_fan_weighted = 0.0
        for action in view.get("actions") or ():
            if action.get("fact_kind") != "hand_progress":
                continue
            shanten = action.get("shanten_after")
            if shanten is None or shanten is True or shanten is False or shanten < 0:
                continue
            hand_progress_actions += 1
            cov = action.get("value_coverage")
            coverage[str(cov)] += 1
            routes = action.get("routes")
            if not routes:
                route_counts[0] += 1
                continue
            route_counts[len(routes)] += 1
            window_has_routes = True
            total = 0.0
            for route in routes:
                settlement = route.get("conditional_settlement")
                fan = None
                if settlement is not None:
                    raw = settlement.get("fan")
                    if raw is not None and raw is not True and raw is not False:
                        fan = float(raw)
                fan_values[str(fan)] += 1
                if fan is None or fan <= 1.0:
                    continue
                support = 0.0
                for tile in route.get("useful_tiles") or ():
                    remaining = tile.get("remaining_estimate")
                    if remaining is None or remaining is True or remaining is False:
                        continue
                    support += float(remaining)
                total += support * (fan - 1.0)
                if support > 0 and len(sample_rows) < 12:
                    sample_rows.append((row.get("game_id"), action.get("action_key"), fan, support, cov))
            if total > 0:
                fan_weighted_nonzero += 1
                window_live = True
                if total > best_fan_weighted:
                    best_fan_weighted = total
        if window_has_routes:
            windows_with_routes += 1
        if window_live:
            live_windows += 1

    print("窗口数 =", windows)
    print("hand_progress 动作数 =", hand_progress_actions)
    print("value_coverage 分布 =", dict(coverage))
    print("routes 条数分布（前 8）= ", dict(sorted(route_counts.items())[:8]))
    print("conditional_settlement.fan 取值分布 =", dict(sorted(fan_values.items(), key=lambda kv: str(kv[0]))[:10]))
    print("有 routes 的窗口 = %d (%.2f%%)" % (windows_with_routes, 100.0 * windows_with_routes / max(1, windows)))
    print("fan_weighted > 0 的动作 = %d (%.3f%%)" % (fan_weighted_nonzero, 100.0 * fan_weighted_nonzero / max(1, hand_progress_actions)))
    print("含「可加权动作」的窗口 = %d (%.2f%%)" % (live_windows, 100.0 * live_windows / max(1, windows)))
    print()
    print("样例（game_id, action_key, fan, route_support, coverage）：")
    for item in sample_rows:
        print("  ", item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
