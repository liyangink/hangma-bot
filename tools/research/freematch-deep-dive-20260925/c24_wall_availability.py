#!/usr/bin/env python3
"""C24 前置：墙深（remaining_tile_count）在真实窗口里的可用性与分布。

动机：父代打分 base = -100*shanten + round(support,1) **完全不含墙深**，
而可见状态里其实有官方的 wall_remaining（含 20 张保留区）。
若墙深可用且分布足够宽，则「墙短时向听差更贵」是一条从未被测过的决策轴。
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
import statistics
import sys
from pathlib import Path

ROOT = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / ".team-work" / "p6-baotou-route")))

import p6_lib  # noqa: E402


def main() -> int:
    values = []
    missing = 0
    windows = 0
    by_phase = collections.Counter()
    shanten_by_wall = collections.defaultdict(collections.Counter)
    for row in p6_lib.iter_rooms(p6_lib.ROOMS_PRIMARY + p6_lib.ROOMS_EXTRA):
        view = row["view"]
        visible = view.get("visible_state") or {}
        windows += 1
        w = visible.get("remaining_tile_count")
        by_phase[str(visible.get("phase"))] += 1
        if w is None or w is True or w is False:
            missing += 1
        else:
            values.append(int(w))
        # 父代首选动作的向听（用审计的 plan_rank1 与候选表交叉）
        key = row.get("plan_rank1")
        best = None
        for action in view.get("actions") or ():
            if action.get("action_key") == key:
                sh = action.get("shanten_after")
                if isinstance(sh, int) and sh >= 0:
                    best = sh
                break
        if best is not None and isinstance(w, int):
            bucket = "w<30" if w < 30 else ("w<50" if w < 50 else ("w<70" if w < 70 else "w>=70"))
            shanten_by_wall[bucket][best] += 1
    print("窗口数 =", windows, "；墙深缺失 =", missing, "（%.3f%%）" % (100.0 * missing / max(1, windows)))
    if values:
        ordered = sorted(values)
        print("墙深分布：min %d p10 %d p25 %d 中位 %d p75 %d p90 %d max %d"
              % (ordered[0], ordered[int(0.10 * len(ordered))], ordered[int(0.25 * len(ordered))],
                 ordered[len(ordered) // 2], ordered[int(0.75 * len(ordered))], ordered[int(0.90 * len(ordered))],
                 ordered[-1]))
        print("均值 %.2f；<30 占比 %.2f%%；<50 占比 %.2f%%" % (statistics.fmean(values),
              100.0 * sum(1 for v in values if v < 30) / len(values),
              100.0 * sum(1 for v in values if v < 50) / len(values)))
    print("phase 分布 =", dict(by_phase))
    print()
    print("父代实际提交动作的向听 × 墙深桶：")
    for bucket in ("w>=70", "w<70", "w<50", "w<30"):
        cell = shanten_by_wall.get(bucket)
        if not cell:
            continue
        total = sum(cell.values())
        dist = {k: round(100.0 * v / total, 1) for k, v in sorted(cell.items())}
        print("  %-6s n=%5d  向听分布 %s" % (bucket, total, dist))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
