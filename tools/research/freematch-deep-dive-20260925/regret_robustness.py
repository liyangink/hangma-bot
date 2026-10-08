#!/usr/bin/env python3
"""主审：生产 regret 的稳健性诊断与分层（回答「+2.49 是不是被少数极端窗拉起来的」）。

只用 .team-work/rollout-regret-v1/prod/rows.json；不产生新桌。
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

import json
import math
import statistics
from collections import defaultdict

ARMS = ("2", "3", "worst")


def q(vals, p):
    s = sorted(vals)
    if not s:
        return float("nan")
    k = (len(s) - 1) * p
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def unit_mean(rows, arm):
    per = defaultdict(list)
    for r in rows:
        if arm not in r["cf"]:
            continue
        per[r["unit"]].append(r["cf"][arm] - r["baseline_score"])
    return {k: statistics.fmean(v) for k, v in per.items()}


def ci(per_unit):
    vals = list(per_unit.values())
    n = len(vals)
    m = statistics.fmean(vals)
    se = statistics.stdev(vals) / math.sqrt(n) if n > 1 else float("nan")
    return m, n, m - 1.96 * se, m + 1.96 * se


def main() -> int:
    rows = json.load(open(".team-work/rollout-regret-v1/prod/rows.json"))
    print("窗口 %d，unit %d\n" % (len(rows), len({r["unit"] for r in rows})))

    print("## 1. 每臂 regret 的分布（分/桌，窗级）\n")
    print("| 臂 | 均值 | 中位 | Q1 | Q3 | 去尾5%%均值 | \\|Δ\\|>50 占比 | \\|Δ\\|>100 占比 | 正占比 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for arm in ARMS:
        v = [r["cf"][arm] - r["baseline_score"] for r in rows if arm in r["cf"]]
        s = sorted(v)
        k = max(1, int(0.05 * len(s)))
        trimmed = statistics.fmean(s[k:len(s) - k])
        big50 = sum(1 for x in v if abs(x) > 50) / len(v)
        big100 = sum(1 for x in v if abs(x) > 100) / len(v)
        pos = sum(1 for x in v if x > 0) / len(v)
        print("| %s | %+.2f | %+.1f | %+.1f | %+.1f | %+.2f | %.1f%% | %.1f%% | %.1f%% |"
              % (arm, statistics.fmean(v), statistics.median(v), q(v, .25), q(v, .75),
                 trimmed, 100 * big50, 100 * big100, 100 * pos))

    print("\n## 2. unit 级符号检验（每 unit 内先取均值）\n")
    for arm in ARMS:
        per = unit_mean(rows, arm)
        pos = sum(1 for x in per.values() if x > 0)
        neg = sum(1 for x in per.values() if x < 0)
        print("- 臂 %s：unit 均值 >0 的 %d 个，<0 的 %d 个，=0 的 %d 个；二项检验 p=%.3f"
              % (arm, pos, neg, len(per) - pos - neg,
                 _binom_p(pos, pos + neg)))

    print("\n## 3. 分层：phase × 首选动作族\n")
    print("| 分层 | 臂 | 窗数 | unit 数 | Δ 均值 | 95%% CI |")
    print("| --- | --- | --- | --- | --- | --- |")
    keys = {
        "phase": lambda r: r["phase"],
        "kind": lambda r: r["top_action_kind"],
        "melds": lambda r: str(r["self_melds"]),
        "dealer": lambda r: "庄" if r["is_dealer"] else "闲",
        "mix": lambda r: r["mix"],
        "round": lambda r: str(r["round_no"]),
        "hand": lambda r: str(r["hand_size"]),
    }
    for kname, fn in keys.items():
        for value in sorted({fn(r) for r in rows}):
            for arm in ARMS:
                sub = [r for r in rows if fn(r) == value and arm in r["cf"]]
                if len(sub) < 60:
                    continue
                per = unit_mean(sub, arm)
                m, n, lo, hi = ci(per)
                print("| %s=%s | %s | %d | %d | %+.2f | [%+.2f, %+.2f] |"
                      % (kname, value, arm, len(sub), n, m, lo, hi))
    return 0


def _binom_p(k, n):
    if n == 0:
        return float("nan")
    # 双尾精确二项检验 p=0.5
    from math import comb
    tot = 2.0 ** n
    lo = sum(comb(n, i) for i in range(0, min(k, n - k) + 1)) / tot
    return min(1.0, 2 * lo)


if __name__ == "__main__":
    raise SystemExit(main())
