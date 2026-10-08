#!/usr/bin/env python3
"""爆头（任意听）价值项的决策可达性（只读）。

三个独立分析一致指出：我们的失分不是「胡得少」而是「胡得小」，
而单次分值的最大单一变量是爆头（番值 ×2）。
规则模块已经在每个候选上给出 `baotou_after`，所以「加一个爆头奖励项」是机械可行的。

但先要问：它能不能改变决策？本脚本在真实候选集上测量：

1. 同一窗口内候选的 `baotou_after` 是否不一致（不一致才可能被排序项区分）；
2. 爆头候选是否常常出现在**更差向听**的层（若是，奖励必须大于 100 才能选中）；
3. 给定奖励 B，首选改选率是多少。

用法：
    .venv/bin/python review/freematch-deep-dive-20260925/value_term_reach.py \
        --audit-root <audit> [--audit-root ...]
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

SHANTEN_COEFFICIENT = 100.0


def score(candidate, bonus):
    total = -SHANTEN_COEFFICIENT * candidate["shanten"] + candidate["support"]
    if candidate["baotou_after"] is True:
        total += bonus
    return total


def pick(candidates, bonus):
    best = None
    for candidate in candidates:
        key = (score(candidate, bonus), str(candidate["action_key"]))
        if best is None or key > best[0]:
            best = (key, candidate)
    return best[1]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit-root", required=True, action="append")
    ap.add_argument("--bonuses", default="20,50,100,150,200,400,800")
    args = ap.parse_args(argv)

    bonuses = [float(x) for x in args.bonuses.split(",") if x.strip()]
    windows = []
    for root in args.audit_root:
        windows.extend(iter_windows(root))

    total = len(windows)
    varies = 0
    any_true = 0
    baotou_worse_shanten = 0
    baotou_at_min = 0
    for win in windows:
        flags = {c["baotou_after"] for c in win["candidates"]}
        if flags == {True}:
            any_true += 1
        elif True in flags:
            any_true += 1
        if len(flags) > 1:
            varies += 1
        best_shanten = min(c["shanten"] for c in win["candidates"])
        trues = [c for c in win["candidates"] if c["baotou_after"] is True]
        if trues:
            if min(c["shanten"] for c in trues) == best_shanten:
                baotou_at_min += 1
            else:
                baotou_worse_shanten += 1

    print("窗口数 %d" % total)
    print("候选 baotou_after 取值不一致的窗口：%d (%.2f%%)" % (varies, 100.0 * varies / total))
    print("存在 baotou_after 为 True 候选的窗口：%d (%.2f%%)" % (any_true, 100.0 * any_true / total))
    print("  其中爆头候选可达最小向听：%d" % baotou_at_min)
    print("  其中爆头候选只在更差向听层（需要跨层奖励）：%d" % baotou_worse_shanten)
    print()
    baseline = [pick(w["candidates"], 0.0)["action_key"] for w in windows]
    print("| 爆头奖励 B | 改选窗口 | 改选率 |")
    print("| --- | --- | --- |")
    for bonus in bonuses:
        changed = sum(1 for win, base in zip(windows, baseline)
                      if pick(win["candidates"], bonus)["action_key"] != base)
        print("| %g | %d | %.2f%% |" % (bonus, changed, 100.0 * changed / total))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())