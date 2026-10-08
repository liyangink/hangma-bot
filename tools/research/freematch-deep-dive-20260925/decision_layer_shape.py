#!/usr/bin/env python3
"""决策层结构测量：向听层之间与层内的可选空间有多大（只读）。

回答三个决定「新目标函数能不能有用」的问题：

1. 同一窗口内，候选的向听数跨度是多少？（跨度 0 = 全部候选同向听，
   此时放弃向听没有代价，决策只剩层内的近等价选择）
2. 最小向听层的进张数，比「次小向听层的最优」高多少？
   这个差就是**降一个向听要付出的进张代价**——也是任何「用向听换价值」
   的新目标函数必须跨过的门槛。
3. 最小向听层内，进张数最优与最差相差多少？
   这个差是层内决策的**最大可能赌注**。若它远小于跨层代价，
   说明层内选择几乎不影响结果，任何层内排序项都不可能带来增益。

用法：
    .venv/bin/python review/freematch-deep-dive-20260925/decision_layer_shape.py \
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
import statistics

from decision_leverage import iter_windows


def pct(values, q):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def describe(name, values):
    if not values:
        print("  %s: 无样本" % name)
        return
    print("  %s: n=%d 中位 %g p25 %g p75 %g p90 %g 均值 %.2f 最大 %g"
          % (name, len(values), pct(values, 0.5), pct(values, 0.25),
             pct(values, 0.75), pct(values, 0.9), statistics.fmean(values), max(values)))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit-root", required=True, action="append")
    args = ap.parse_args(argv)

    windows = 0
    span_zero = 0
    spans = []
    cross_cost = []      # 最小层最优进张 - 次小层最优进张
    layer_bet = []       # 最小层内 最优进张 - 最差进张
    layer_sizes = []

    for root in args.audit_root:
        for win in iter_windows(root):
            windows += 1
            cands = win["candidates"]
            by_shanten = {}
            for c in cands:
                by_shanten.setdefault(c["shanten"], []).append(c["support"])
            levels = sorted(by_shanten)
            span = levels[-1] - levels[0]
            spans.append(span)
            if span == 0:
                span_zero += 1
            best = by_shanten[levels[0]]
            layer_sizes.append(len(best))
            layer_bet.append(max(best) - min(best))
            if len(levels) >= 2:
                cross_cost.append(max(best) - max(by_shanten[levels[1]]))

    print("窗口数：%d" % windows)
    print("候选向听跨度全为 0（所有候选同向听）的窗口：%d（%.1f%%）"
          % (span_zero, 100.0 * span_zero / windows))
    print()
    print("-- 候选向听跨度 --")
    describe("跨度", spans)
    print()
    print("-- 降一个向听的进张代价（最小层最优进张 - 次小层最优进张）--")
    describe("跨层代价", cross_cost)
    print()
    print("-- 最小向听层内的赌注（层内最优进张 - 层内最差进张）--")
    describe("层内赌注", layer_bet)
    describe("层内候选数", layer_sizes)
    print()
    if cross_cost and layer_bet:
        print("读法：跨层代价中位 %g，层内赌注中位 %g。"
              % (pct(cross_cost, 0.5), pct(layer_bet, 0.5)))
        print("      层内赌注 / 跨层代价 = %.2f"
              % (pct(layer_bet, 0.5) / max(1.0, pct(cross_cost, 0.5))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())