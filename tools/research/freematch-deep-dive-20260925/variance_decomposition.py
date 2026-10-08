#!/usr/bin/env python3
"""主审：配对评价的方差分解——分辨率该靠「更多牌山根」还是「每根更多桌」？

背景：本会话所有配对批次的根级 Δ 的 SD ≈ 16 分/桌。要靠更多样本把分辨率做细，
必须先知道这 16 分里有多少是「根内噪声」（多跑几张桌就能平均掉）、
多少是「根间异质性」（只能靠更多根）。
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
import os
import re
import statistics
from collections import defaultdict


def load(out_dir):
    per_unit = {}
    for path in glob.glob(os.path.join(out_dir, "stages", "*.json")):
        name = os.path.basename(path)[:-5]
        matched = re.match(r"^(.*-s\d-)(r18_v2|candidate@.*)$", name)
        if not matched:
            continue
        unit, arm = matched.group(1), matched.group(2)
        try:
            d = json.load(open(path))
        except Exception:
            continue
        st = d.get("stage") or {}
        score = st.get("focal_stage_score")
        if score is None or st.get("error"):
            continue
        per_unit.setdefault(unit, {})[arm] = score
    return per_unit


def main() -> int:
    for out_dir in ("review/freematch-deep-dive-20260925/p29-denial",
                    "review/freematch-deep-dive-20260925/p27-tie-swap",
                    "review/freematch-deep-dive-20260925/p21b-near-tie"):
        if not os.path.isdir(out_dir):
            continue
        per_unit = load(out_dir)
        arms = sorted({a for v in per_unit.values() for a in v})
        if len(arms) < 2:
            continue
        base, cand = arms[0], arms[1]
        by_root = defaultdict(list)
        n_units = 0
        for unit, v in per_unit.items():
            if base not in v or cand not in v:
                continue
            delta = (v[cand] - v[base]) / 2.0   # 一个 stage = 两张桌
            root = unit.split("-s")[0]
            by_root[root].append(delta)
            n_units += 1
        roots = {k: v for k, v in by_root.items() if len(v) >= 2}
        if not roots:
            continue
        all_deltas = [x for v in roots.values() for x in v]
        root_means = [statistics.fmean(v) for v in roots.values()]
        grand = statistics.fmean(all_deltas)
        within = sum((x - statistics.fmean(v)) ** 2 for v in roots.values() for x in v)
        within_df = sum(len(v) - 1 for v in roots.values())
        between = sum(len(v) * (statistics.fmean(v) - grand) ** 2 for v in roots.values())
        between_df = len(roots) - 1
        ms_within = within / within_df if within_df else float("nan")
        ms_between = between / between_df if between_df else float("nan")
        n_per_root = statistics.fmean([len(v) for v in roots.values()])
        print("## %s" % out_dir.split("/")[-1])
        print("- 配对 unit %d，根 %d，平均每根 %.1f 个 unit（每个 unit = 2 张桌）"
              % (n_units, len(roots), n_per_root))
        print("- 全部 unit 级 Δ：均值 %+.2f，SD %.2f" % (grand, statistics.stdev(all_deltas)))
        print("- 根均值级 Δ：SD %.2f" % statistics.stdev(root_means))
        print("- **根内均方 MS_within = %.1f（SD %.2f）**" % (ms_within, ms_within ** 0.5))
        print("- **根间均方 MS_between = %.1f（SD %.2f）**" % (ms_between, ms_between ** 0.5))
        print("- 根间占比 ICC ≈ %.3f（= (MS_between - MS_within) / (MS_between + (k-1)MS_within) 的粗估：%.3f）"
              % ((ms_between - ms_within) / ms_between if ms_between else float("nan"),
                 max(0.0, (ms_between - ms_within) / (ms_between + (n_per_root - 1) * ms_within))
                 if ms_between else float("nan")))
        # 分辨率对比：同样的 unit 预算，摊到更多根 vs 每根更多 unit
        tot_units = len(all_deltas)
        for label, n_roots, k in (("当前配置", len(roots), n_per_root),
                                  ("同预算·更多根·每根 4 unit", int(tot_units / 4), 4),
                                  ("同预算·更少根·每根 32 unit", int(tot_units / 32), 32)):
            if n_roots < 2:
                continue
            var = (ms_between / k if k else 0) + (ms_within / k if k else 0)
            se = (var / n_roots) ** 0.5
            print("  - %-26s 根 %4d × 每根 %2d unit ⇒ 均值的 SE ≈ %.3f 分/桌（半宽 ±%.2f）"
                  % (label, n_roots, k, se, 1.96 * se))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
