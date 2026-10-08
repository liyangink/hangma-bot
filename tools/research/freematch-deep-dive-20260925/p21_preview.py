#!/usr/bin/env python3
"""p21 中途预览：候选臂（非胡层次选）vs r18_v2 的配对分差。**不是最终结果**，只用于早发现管道故障。"""
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
import re
import statistics
from collections import defaultdict

STAGES = "review/freematch-deep-dive-20260925/p21-second-choice/stages"


def main() -> int:
    per = defaultdict(dict)
    for path in glob.glob(os.path.join(STAGES, "*.json")):
        name = os.path.basename(path)[:-5]
        m = re.match(r"^(.*-s\d-)(r18_v2|candidate@.*)$", name)
        if not m:
            continue
        unit, arm = m.group(1), m.group(2)
        try:
            d = json.load(open(path))
        except Exception:
            continue
        score = d.get("stage", {}).get("focal_stage_score")
        us = d.get("stage", {}).get("usable")
        if score is None or not us:
            continue
        per[unit]["candidate" if arm.startswith("candidate@") else "r18_v2"] = score

    both = {u: v for u, v in per.items() if len(v) == 2}
    print("已完成配对 unit：%d" % len(both))
    if not both:
        return 0
    diffs = [v["candidate"] - v["r18_v2"] for v in both.values()]
    cand = [v["candidate"] for v in both.values()]
    base = [v["r18_v2"] for v in both.values()]
    print("- 候选臂均值 %.2f，父代均值 %.2f" % (statistics.fmean(cand), statistics.fmean(base)))
    print("- 配对差均值 **%+.2f 分/桌**，SD %.2f，SE %.2f" % (
        statistics.fmean(diffs), statistics.stdev(diffs), statistics.stdev(diffs) / math.sqrt(len(diffs))))
    print("- 朴素 95%% CI [%+.2f, %+.2f]" % (
        statistics.fmean(diffs) - 1.96 * statistics.stdev(diffs) / math.sqrt(len(diffs)),
        statistics.fmean(diffs) + 1.96 * statistics.stdev(diffs) / math.sqrt(len(diffs))))
    print("- 候选更好 %d，父代更好 %d，相同 %d" % (
        sum(1 for d in diffs if d > 0), sum(1 for d in diffs if d < 0), sum(1 for d in diffs if d == 0)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
