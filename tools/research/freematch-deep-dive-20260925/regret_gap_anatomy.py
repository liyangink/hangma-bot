#!/usr/bin/env python3
"""主审：父代首选 vs 次选的分差究竟由哪一项造成，以及该项分差大小与 regret 的关系。"""
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
from collections import Counter, defaultdict

ARMS = ("2", "3", "worst")


def top_support(r):
    return r["parent_total_top"] + 100.0 * r["shanten_after_top"] - r["parent_modifier_top"]


def arm_support(r, arm):
    return r["parent_total"][arm] + 100.0 * r["parent_shanten"][arm] - r["parent_modifier"][arm]


def has_arm(r, arm):
    return arm in r["parent_shanten"]


def ci(per):
    vals = list(per.values())
    m = statistics.fmean(vals)
    se = statistics.stdev(vals) / math.sqrt(len(vals))
    return m, len(vals), m - 1.96 * se, m + 1.96 * se


def unit_mean(rows, arm):
    per = defaultdict(list)
    for r in rows:
        per[r["unit"]].append(r["cf"][arm] - r["baseline_score"])
    return {k: statistics.fmean(v) for k, v in per.items()}


def main() -> int:
    rows = json.load(open(".team-work/rollout-regret-v1/prod/rows.json"))

    print("## 1. 首选 vs 次选（臂2）分差来源的联合归类\n")
    c = Counter()
    for r in rows:
        if not has_arm(r, "2"):
            continue
        ds = r["parent_shanten"]["2"] - r["shanten_after_top"]
        dm = r["parent_modifier"]["2"] - r["parent_modifier_top"]
        du = arm_support(r, "2") - top_support(r)
        tags = []
        if ds != 0:
            tags.append("向听:%+d" % ds)
        if abs(dm) > 1e-9:
            tags.append("修饰")
        if abs(du) > 1e-9:
            tags.append("support")
        c["+".join(tags) if tags else "完全并列"] += 1
    for k, v in c.most_common():
        print("- %-24s %4d 窗（%.1f%%）" % (k, v, 100.0 * v / len(rows)))

    print("\n## 2. 仅修饰项不同的窗口：修饰分差的分布与 regret\n")
    sub = []
    for r in rows:
        if not has_arm(r, "2"):
            continue
        ds = r["parent_shanten"]["2"] - r["shanten_after_top"]
        dm = r["parent_modifier"]["2"] - r["parent_modifier_top"]
        du = arm_support(r, "2") - top_support(r)
        if ds == 0 and abs(du) <= 1e-9 and abs(dm) > 1e-9:
            sub.append((dm, r))
    dms = [x for x, _ in sub]
    print("窗数 %d；Δmodifier 中位 %+.1f，均值 %+.1f，min %+.1f，max %+.1f"
          % (len(sub), statistics.median(dms), statistics.fmean(dms), min(dms), max(dms)))
    print("\n| Δ修饰区间 | 窗数 | unit 数 | regret 均值 | 95%% CI |")
    print("| --- | --- | --- | --- | --- |")
    for lo, hi, label in ((-1000, -30, "< -30"), (-30, -10, "[-30,-10)"), (-10, -1e-9, "(-10,0)"),
                          (1e-9, 10, "(0,10]"), (10, 30, "(10,30]"), (30, 1000, "> 30")):
        part = [r for x, r in sub if lo <= x < hi]
        if len(part) < 20:
            continue
        per = unit_mean(part, "2")
        m, n, a, b = ci(per)
        print("| %s | %d | %d | %+.2f | [%+.2f, %+.2f] |" % (label, len(part), n, m, a, b))

    print("\n## 3. 修饰项符号分解（recover: 修饰差来自哪个字段不易反推，改看方向）\n")
    neg = [r for x, r in sub if x < 0]
    pos = [r for x, r in sub if x > 0]
    for name, part in (("替代被修饰项扣分（Δmod<0）", neg), ("替代被修饰项加分（Δmod>0）", pos)):
        if len(part) < 20:
            continue
        per = unit_mean(part, "2")
        m, n, a, b = ci(per)
        print("- %s：窗 %d，unit %d，regret %+.2f [%+.2f, %+.2f]" % (name, len(part), n, m, a, b))

    print("\n## 4. 完全并列窗口（臂2 与首选完全同分）的 regret\n")
    tie = [r for r in rows if has_arm(r, "2")
           and r["parent_shanten"]["2"] == r["shanten_after_top"]
           and abs(r["parent_modifier"]["2"] - r["parent_modifier_top"]) <= 1e-9
           and abs(arm_support(r, "2") - top_support(r)) <= 1e-9]
    per = unit_mean(tie, "2")
    m, n, a, b = ci(per)
    print("窗 %d，unit %d，regret %+.2f [%+.2f, %+.2f]" % (len(tie), n, m, a, b))

    print("\n## 5. 向听不同的窗口（臂2）\n")
    sh = [r for r in rows if has_arm(r, "2") and r["parent_shanten"]["2"] != r["shanten_after_top"]]
    per = unit_mean(sh, "2")
    m, n, a, b = ci(per)
    print("窗 %d，unit %d，regret %+.2f [%+.2f, %+.2f]" % (len(sh), n, m, a, b))
    print("（正数=向听更差的替代反而更好）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
