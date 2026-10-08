#!/usr/bin/env python3
"""向听/进张兑换率的决策杠杆扫描（只读）。

冻结父代把 1 个向听步长定价为 100，把 1 张有效牌定价为 1。
上一张测量显示：接受「多一个向听」平均能换回 21 张有效牌（中位）。
所以 100 这个定价相当于把向听当成有效牌的 5 倍——这是父代最强的单一偏置。

本脚本在**真实记录的候选集**上重算 argmax，扫描向听系数 c：

    total = -c * shanten + support

并统计相对 c=100 的首选改选率。改选率就是「这个系数值不值得花完整桌预算」
的第一道门。

注意：为了让改动可归因，这里只重算主项，不复现父代的熟张/风险/财神/风格小项。
因此得到的是**主项自身的改选率**，是任何完整候选改选率的上界近似。

用法：
    .venv/bin/python review/freematch-deep-dive-20260925/shanten_coefficient_reach.py \
        --audit-root artifacts/sessions/<房>/audit
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

import argparse

from decision_leverage import iter_windows

BASE_COEFFICIENT = 100.0


def pick(cands, coefficient):
    """按 -coefficient*向听 + 进张 取首选；完全同分时按 action_key 保持确定性。"""
    best = None
    for c in cands:
        score = -coefficient * c["shanten"] + c["support"]
        key = (score, str(c["action_key"]))
        if best is None or key > best[0]:
            best = (key, c)
    return best[1]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit-root", required=True, action="append")
    ap.add_argument("--coefficients", default="90,80,70,60,50,40,30,20,10,0")
    args = ap.parse_args(argv)

    coefficients = [float(x) for x in args.coefficients.split(",") if x.strip()]
    windows = []
    for root in args.audit_root:
        windows.extend(iter_windows(root))

    baseline = [pick(w["candidates"], BASE_COEFFICIENT)["action_key"] for w in windows]
    print("窗口数 %d；基准系数 %g" % (len(windows), BASE_COEFFICIENT))
    print()
    print("| 向听系数 | 改选窗口 | 改选率 |")
    print("| --- | --- | --- |")
    for coefficient in coefficients:
        changed = 0
        for win, base_key in zip(windows, baseline):
            if pick(win["candidates"], coefficient)["action_key"] != base_key:
                changed += 1
        print("| %g | %d | %.2f%% |"
              % (coefficient, changed, 100.0 * changed / len(windows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())