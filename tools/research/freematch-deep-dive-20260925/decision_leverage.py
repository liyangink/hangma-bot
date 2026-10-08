#!/usr/bin/env python3
"""决策杠杆测量：任何新评分项最多能改变多少决策（只读）。

背景：冻结父代的基础分是 `-100 × 向听 + 有效牌剩余张数之和`。
本脚本从真实决策审计里重算每个窗口的候选分，回答三个问题：

1. 每个窗口有几个候选达到最小向听？（=1 时任何同层排序项都无法影响结果）
2. 在达到最小向听的候选之间，进张数的差距分布是什么？
   （这个差距就是「一个新项要多大量级才能翻转选择」）
3. 对给定的项量级 M，有多大比例的窗口会被翻转？

这里的翻转率是**上界**：它假设新项恰好偏向次优候选，实际改选率只会更低。

用法：
    .venv/bin/python review/freematch-deep-dive-20260925/decision_leverage.py \
        --audit-root artifacts/sessions/<房>/audit --out out.json
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
import glob
import json
import os
import statistics


def _support(facts):
    """有效牌剩余张数之和；任一计数不可用时按父代口径视为不可用。"""
    tiles = facts.get("useful_tiles")
    if not isinstance(tiles, list) or not tiles:
        return None
    total = 0
    for tile in tiles:
        amount = tile.get("remaining_estimate")
        if type(amount) is not int:
            return None
        total += amount
    return total


def iter_windows(audit_root):
    """产出每个决策窗口的候选 (action_key, shanten, support, baotou)。"""
    pattern = os.path.join(audit_root, "runs", "*", "participants", "*", "decisions.jsonl")
    for path in sorted(glob.glob(pattern)):
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get("kind") != "decision_input":
                    continue
                request = ((row.get("payload") or {}).get("request") or {})
                rules = request.get("rules") or {}
                candidates = rules.get("legal_candidates") or []
                window = request.get("window_key") or {}
                out = []
                for cand in candidates:
                    facts = cand.get("facts")
                    if not isinstance(facts, dict):
                        continue
                    if facts.get("fact_kind") != "hand_progress":
                        continue
                    shanten = facts.get("shanten_after")
                    if type(shanten) is not int:
                        continue
                    support = _support(facts)
                    if support is None:
                        continue
                    out.append({
                        "action_key": cand.get("action_key"),
                        "shanten": shanten,
                        "support": support,
                        "baotou_after": facts.get("baotou_after"),
                    })
                if len(out) >= 2:
                    yield {"game_id": window.get("game_id"),
                           "phase": window.get("phase"),
                           "candidates": out}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit-root", required=True, action="append")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    windows = 0
    unique_min = 0
    tie_sizes = {}
    margins = []          # 同最小向听层内，最优与次优进张数之差
    baotou_varies = 0
    leverage = {m: 0 for m in (1, 3, 5, 10, 20, 50, 100)}

    for root in args.audit_root:
        for win in iter_windows(root):
            windows += 1
            cands = win["candidates"]
            best_shanten = min(c["shanten"] for c in cands)
            layer = [c for c in cands if c["shanten"] == best_shanten]
            tie_sizes[len(layer)] = tie_sizes.get(len(layer), 0) + 1
            if len(layer) == 1:
                unique_min += 1
                continue
            ordered = sorted((c["support"] for c in layer), reverse=True)
            margin = ordered[0] - ordered[1]
            margins.append(margin)
            if len({c["baotou_after"] for c in layer}) > 1:
                baotou_varies += 1
            for mag in leverage:
                if margin <= mag:
                    leverage[mag] += 1

    print("窗口数（>=2 个有事实的候选）：%d" % windows)
    print("最小向听层只有唯一候选的窗口：%d（%.1f%%）——这些窗口任何同层排序项都无法影响"
          % (unique_min, 100.0 * unique_min / windows))
    print()
    print("最小向听层候选个数分布：")
    for size in sorted(tie_sizes):
        print("  %d 个候选: %6d 窗口 (%.1f%%)"
              % (size, tie_sizes[size], 100.0 * tie_sizes[size] / windows))
    print()
    if margins:
        margins.sort()
        print("同层进张数差距（最优 - 次优）分布，n=%d：" % len(margins))
        for q, label in ((0.10, "p10"), (0.25, "p25"), (0.50, "中位"),
                         (0.75, "p75"), (0.90, "p90"), (0.99, "p99")):
            print("  %s = %d" % (label, margins[min(len(margins) - 1, int(q * len(margins)))]))
        print("  均值 = %.1f" % statistics.fmean(margins))
        print()
        print("一个新增项量级为 M 时，**最多**能翻转的窗口比例（上界）：")
        for mag in sorted(leverage):
            print("  M=%3d → %6d 窗口 (%.2f%%)"
                  % (mag, leverage[mag], 100.0 * leverage[mag] / windows))
    print()
    print("同层 baotou_after 取值不一致的窗口：%d (%.2f%%)"
          % (baotou_varies, 100.0 * baotou_varies / windows))

    if args.out:
        with open(args.out, "w") as fh:
            json.dump({"windows": windows, "unique_min_layer": unique_min,
                       "tie_sizes": tie_sizes, "margins": margins[:200000],
                       "leverage_upper_bound": leverage,
                       "baotou_varies": baotou_varies}, fh, indent=1)
        print("写出 " + args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())