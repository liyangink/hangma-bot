#!/usr/bin/env python3
"""主审：把生产 regret 按「父代分差来自哪一项」分层。

数据：.team-work/rollout-regret-v1/prod/rows.json（1,600 窗，每窗 3 个替代臂）。
注意口径：首选臂（rank 1）没有存进 cf/parent_* 字典，它的表分是 baseline_score，
分项是 parent_total_top / shanten_after_top / parent_modifier_top。
作者的 parent_gap[arm] = parent_total[arm] - parent_total_top（本脚本逐位复算通过）。

父代总分可逆分解：
    parent_total = -100 * shanten + support + modifier
⇒ support_implied = parent_total + 100 * shanten - modifier

本脚本回答：父代在哪个「货币」上把首选和次选分开时，它是对的？
统计单位：unit（层内先对 unit 取均值，再跨 unit 求均值与 95% CI），与作者口径一致。
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


def top_support(r):
    return r["parent_total_top"] + 100.0 * r["shanten_after_top"] - r["parent_modifier_top"]


def arm_support(r, arm):
    return r["parent_total"][arm] + 100.0 * r["parent_shanten"][arm] - r["parent_modifier"][arm]


def cluster_ci(per_unit):
    vals = list(per_unit.values())
    n = len(vals)
    if n < 2:
        return None
    m = statistics.fmean(vals)
    sd = statistics.stdev(vals)
    se = sd / math.sqrt(n)
    return m, sd, n, m - 1.96 * se, m + 1.96 * se


def agg(rows, arm):
    per_unit = defaultdict(list)
    for r in rows:
        per_unit[r["unit"]].append(r["cf"][arm] - r["baseline_score"])
    per_unit = {k: statistics.fmean(v) for k, v in per_unit.items()}
    return per_unit, cluster_ci(per_unit)


def has_arm(r, arm):
    return arm in r["parent_shanten"] and arm in r["parent_total"]


def stratum(r, arm, kind):
    if not has_arm(r, arm):
        return False
    ds = r["parent_shanten"][arm] - r["shanten_after_top"]
    dm = r["parent_modifier"][arm] - r["parent_modifier_top"]
    du = arm_support(r, arm) - top_support(r)
    if kind == "shanten_only":
        return ds != 0 and dm == 0
    if kind == "support_only":
        return ds == 0 and dm == 0 and abs(du) > 1e-9
    if kind == "support_lower":
        return ds == 0 and dm == 0 and du < 0
    if kind == "modifier_only":
        return ds == 0 and dm != 0
    if kind == "tie":
        return ds == 0 and dm == 0 and abs(du) <= 1e-9
    if kind == "all":
        return True
    raise AssertionError(kind)


def main() -> int:
    rows = json.load(open(".team-work/rollout-regret-v1/prod/rows.json"))
    print("窗口总数 %d，unit 数 %d" % (len(rows), len({r["unit"] for r in rows})))

    print("\n## 0. 首选与各替代的分项差（全部窗口，中位数）\n")
    print("| 臂 | 窗数 | Δ向听=0 | Δ向听中位 | Δsupport 中位 | Δmodifier 中位 | Δtotal 中位 |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for arm in ARMS:
        ds, du, dm, dt = [], [], [], []
        for r in rows:
            if not has_arm(r, arm):
                continue
            ds.append(r["parent_shanten"][arm] - r["shanten_after_top"])
            du.append(arm_support(r, arm) - top_support(r))
            dm.append(r["parent_modifier"][arm] - r["parent_modifier_top"])
            dt.append(r["parent_total"][arm] - r["parent_total_top"])
        print("| %s | %d | %d | %+.1f | %+.1f | %+.1f | %+.1f |"
              % (arm, len(ds), sum(1 for x in ds if x == 0),
                 statistics.median(ds), statistics.median(du),
                 statistics.median(dm), statistics.median(dt)))

    print("\n## 1. 分差来源分层：替代臂相对父代首选的桌分差（分/桌，正=替代更好）\n")
    print("| 分层 | 臂 | 窗数 | unit 数 | Δ 均值 | unit 聚类 95% CI |")
    print("| --- | --- | --- | --- | --- | --- |")
    for kind in ("all", "shanten_only", "support_only", "support_lower", "modifier_only", "tie"):
        for arm in ARMS:
            sub = [r for r in rows if stratum(r, arm, kind)]
            if len(sub) < 20:
                continue
            pu, ci = agg(sub, arm)
            print("| %s | %s | %d | %d | %+.2f | [%+.2f, %+.2f] |"
                  % (kind, arm, len(sub), ci[2], ci[0], ci[3], ci[4]))

    print("\n## 2. 纯 support 竞争窗口的规模\n")
    for kind, label in (("support_only", "纯 support（Δ向听=0 且 Δ修饰=0）"),
                        ("tie", "完全并列")):
        n = sum(1 for r in rows if sum(1 for a in ARMS if stratum(r, a, kind)) == len(ARMS))
        print("- 三个替代臂全部落在「%s」的窗口：%d / %d = %.1f%%"
              % (label, n, len(rows), 100.0 * n / len(rows)))

    print("\n## 3. 纯 support 层内：regret 对 Δsupport 的 OLS\n")
    xs, ys, us = [], [], []
    for r in rows:
        for arm in ARMS:
            if stratum(r, arm, "support_only"):
                xs.append(arm_support(r, arm) - top_support(r))
                ys.append(r["cf"][arm] - r["baseline_score"])
                us.append(r["unit"])
    n = len(xs)
    if n >= 30:
        byu = defaultdict(lambda: [[], []])
        for x, y, u in zip(xs, ys, us):
            byu[u][0].append(x)
            byu[u][1].append(y)
        ux = [statistics.fmean(a) for a, _ in byu.values()]
        uy = [statistics.fmean(b) for _, b in byu.values()]
        mux, muy = statistics.fmean(ux), statistics.fmean(uy)
        usxx = sum((x - mux) ** 2 for x in ux)
        usxy = sum((x - mux) * (y - muy) for x, y in zip(ux, uy))
        uslope = usxy / usxx if usxx else float("nan")
        ress = [y - muy - uslope * (x - mux) for x, y in zip(ux, uy)]
        s2 = sum(e * e for e in ress) / max(1, len(ux) - 2)
        se = math.sqrt(s2 / usxx) if usxx else float("nan")
        mx, my = statistics.fmean(xs), statistics.fmean(ys)
        sxx = sum((x - mx) ** 2 for x in xs)
        sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        slope = sxy / sxx if sxx else float("nan")
        print("窗数 %d，unit 数 %d" % (n, len(ux)))
        print("- 窗口级斜率 %.4f 分/父代分" % slope)
        print("- unit 聚类斜率 %.4f，95%% CI [%.4f, %.4f]" % (uslope, uslope - 1.96 * se, uslope + 1.96 * se))
        print("- 解读：Δsupport 定义为「替代 − 首选」，父代正是靠 Δsupport<0 否掉替代。")
        print("  斜率为负 => 替代 support 越低桌分越差 => 父代方向对；")
        print("  斜率为正 => 父代的 support 优势反向预测桌分 => support 是错的货币。")

    print("\n## 4. 同一窗口内 首选 vs 各替代 的 support 优势分布\n")
    rank_counts = defaultdict(int)
    for r in rows:
        ranks = [arm for arm in ARMS if has_arm(r, arm) and arm_support(r, arm) > top_support(r) + 1e-9]
        rank_counts[len(ranks)] += 1
    for k in sorted(rank_counts):
        print("- 有 %d 个替代的 support 高于首选：%d 窗" % (k, rank_counts[k]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
