#!/usr/bin/env python3
"""主审：把两条验证通道的**分辨率**算清楚——决定什么样的改进是可被证明的。

（1）自由赛真实对局：非配对，每场对手不同，SD 大，样本不可控；
（2）paired_study 同墙四座轮转：配对，分辨率高得多。
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

import glob
import json
import math
import os
import statistics

ROOM_SCORES = "review/freematch-deep-dive-20260925/room-scores.json"


def main() -> int:
    # ---- 1. 自由赛 ----
    with open(ROOM_SCORES) as fh:
        data = json.load(fh)
    games = data["games"]
    my = [g["my_total"] for g in games]
    n = len(my)
    m = statistics.fmean(my)
    sd = statistics.stdev(my)
    se = sd / math.sqrt(n)
    print("## 自由赛场级")
    print("- 场数 %d，均分 %+.3f，SD %.2f，SE %.3f，95%% CI [%+.2f, %+.2f]"
          % (n, m, sd, se, m - 1.96 * se, m + 1.96 * se))
    need = lambda d: math.ceil(((1.96 + 0.8416) ** 2) * (sd ** 2) / (d ** 2))
    print("- 要在 80%% 功效、双侧 5%% 下检出下列效应，需要的场数：")
    for delta in (0.5, 1.0, 2.0, 3.0):
        g = need(delta)
        print("  - +%.1f 分/场 ⇒ **%s 场 ≈ %s 房**（按每房 10 场）" % (delta, format(g, ","), format(math.ceil(g / 10), ",")))

    # ---- 2. paired_study ----
    print()
    print("## paired_study（同墙四座轮转，配对）")
    print("| 批次 | 桌数 | 独立根 | 每臂 Δ 的根级 SE | 95%% 半宽 |")
    print("| --- | --- | --- | --- | --- |")
    for out in ("p21-second-choice", "p21b-near-tie", "p17-seeds", "p7-screening", "p5-screening"):
        path = os.path.join("review", "freematch-deep-dive-20260925", out, "result.json")
        if not os.path.exists(path):
            continue
        d = json.load(open(path))
        roots = d.get("root_clusters") or []
        arms = [k for k in (d.get("descriptive_mean_delta_vs_baseline_per_table") or {})]
        for arm in arms:
            vals = []
            for r in roots:
                v = (r.get("delta_vs_baseline_per_table") or {}).get(arm)
                if v is not None:
                    vals.append(v)
            if len(vals) < 5:
                continue
            se = statistics.stdev(vals) / math.sqrt(len(vals))
            print("| %s | %s | %d | %.2f | ±%.2f |"
                  % (out, arm.split("/")[-1][:38], d.get("complete_tables"), se, 1.96 * se))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
