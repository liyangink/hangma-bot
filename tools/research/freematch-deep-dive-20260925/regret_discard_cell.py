#!/usr/bin/env python3
"""主审：在真实权重最大的 (discard, discard) 格里，把首选与次选的分差拆到分项。"""
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
from collections import Counter, defaultdict

CF = ".team-work/rollout-regret-v1/prod/cf"
ROWS = ".team-work/rollout-regret-v1/prod/rows.json"
ARMS = ("2", "3", "worst")
RANK_TAG = {"rank1": "1", "rank2": "2", "rank3": "3", "worst": "worst"}
PARTS = ("wealth_part", "wealth_discard_part", "river_part", "style_part")


def kind_of(key):
    return key.split(":", 1)[0] if ":" in key else key


def load_cf():
    out = defaultdict(dict)
    for path in glob.glob(os.path.join(CF, "*.json")):
        name = os.path.basename(path)[:-5]
        if name.endswith("-worst"):
            base, tag = name[:-6], "worst"
        else:
            base, _, tag = name.rpartition("-")
        rank = RANK_TAG.get(tag)
        if rank is None:
            continue
        try:
            payload = json.load(open(path))
        except Exception:
            continue
        w = payload.get("task", {}).get("window_record", {}).get("window")
        if not w:
            continue
        out[(payload.get("unit"), w.get("phase"), w.get("round_no"), w.get("trigger_seq"))][rank] = payload
    return out


def unit_ci(pairs):
    per = defaultdict(list)
    for u, v in pairs:
        per[u].append(v)
    vals = [statistics.fmean(v) for v in per.values()]
    m = statistics.fmean(vals)
    se = statistics.stdev(vals) / math.sqrt(len(vals))
    return m, len(vals), m - 1.96 * se, m + 1.96 * se


def main() -> int:
    rows = json.load(open(ROWS))
    cf = load_cf()
    cells = defaultdict(list)
    for r in rows:
        key = (r["unit"], r["phase"], r["round_no"], r["trigger_seq"])
        recs = cf.get(key)
        if not recs or "2" not in recs or "2" not in r.get("cf", {}):
            continue
        plan = recs["2"]["prefix_plan"]["candidates"]
        if len(plan) < 2:
            continue
        if (kind_of(plan[0]["action_key"]), kind_of(plan[1]["action_key"])) != ("discard", "discard"):
            continue
        t1 = plan[0].get("trace") or {}
        t2 = plan[1].get("trace") or {}
        d = {}
        for k in ("shanten_after",):
            d[k] = t2.get(k, 0) - t1.get(k, 0)
        for k in PARTS:
            d[k] = (t2.get(k) or 0.0) - (t1.get(k) or 0.0)
        d["risk_units"] = (t2.get("risk_units") or 0.0) - (t1.get("risk_units") or 0.0)
        d["base"] = (t2.get("base_score") or 0.0) - (t1.get("base_score") or 0.0)
        d["total"] = float(plan[1]["total_score"]) - float(plan[0]["total_score"])
        d["delta"] = r["cf"]["2"] - r["baseline_score"]
        d["unit"] = r["unit"]
        d["key1"] = plan[0]["action_key"]
        d["key2"] = plan[1]["action_key"]
        cells["all"].append(d)

    items = cells["all"]
    print("(discard,discard) 窗数：%d\n" % len(items))
    print("## 1. 分项差的中位数（次选 − 首选）\n")
    for k in ("total", "base", "shanten_after", "wealth_part", "wealth_discard_part", "river_part", "risk_units", "style_part"):
        vals = [x[k] for x in items]
        nz = sum(1 for v in vals if abs(v) > 1e-9)
        print("- %-22s 中位 %+8.2f  非零窗 %5d (%.1f%%)" % (k, statistics.median(vals), nz, 100.0 * nz / len(vals)))

    print()
    print("## 2. 只有某一项不同时的 regret\n")
    print("| 唯一分差项 | 窗数 | unit | Δ 均值 | 95% CI |")
    print("| --- | --- | --- | --- | --- |")
    for only in ("shanten_after", "wealth_part", "wealth_discard_part", "river_part", "risk_units", "style_part"):
        sub = []
        for x in items:
            others = [k for k in ("shanten_after", "wealth_part", "wealth_discard_part", "river_part", "risk_units", "style_part") if k != only]
            if abs(x[only]) > 1e-9 and all(abs(x[k]) <= 1e-9 for k in others):
                sub.append((x["unit"], x["delta"]))
        if len(sub) < 30:
            continue
        res = unit_ci(sub)
        print("| %s | %d | %d | %+.2f | [%+.2f, %+.2f] |" % (only, len(sub), res[1], res[0], res[2], res[3]))

    print()
    print("## 3. 「基础项之外全为零」的窗口（即分差纯粹来自向听与 support）\n")
    sub = []
    for x in items:
        if all(abs(x[k]) <= 1e-9 for k in ("wealth_part", "wealth_discard_part", "river_part", "risk_units", "style_part")):
            sub.append((x["unit"], x["delta"]))
    if len(sub) >= 30:
        res = unit_ci(sub)
        print("- 窗 %d，unit %d，Δ %+.2f [%+.2f, %+.2f]" % (len(sub), res[1], res[0], res[2], res[3]))
    print()
    print("## 3b. 「有任一修饰项不同」的窗口\n")
    sub = []
    for x in items:
        if any(abs(x[k]) > 1e-9 for k in ("wealth_part", "wealth_discard_part", "river_part", "risk_units", "style_part")):
            sub.append((x["unit"], x["delta"]))
    if len(sub) >= 30:
        res = unit_ci(sub)
        print("- 窗 %d，unit %d，Δ %+.2f [%+.2f, %+.2f]" % (len(sub), res[1], res[0], res[2], res[3]))
    print()
    print("## 4. 分差绝对值的分布（看父代到底以多大分差分开首选与次选）\n")
    tot = sorted(abs(x["total"]) for x in items)
    for p in (0.1, 0.25, 0.5, 0.75, 0.9):
        print("- P%-4s |Δtotal| = %.1f" % (int(p * 100), tot[int(p * (len(tot) - 1))]))
    print()
    dsh = Counter(x["shanten_after"] for x in items)
    print("Δ向听分布：%s" % dict(sorted(dsh.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
