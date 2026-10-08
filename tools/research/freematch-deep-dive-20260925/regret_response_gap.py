#!/usr/bin/env python3
"""主审：响应窗里父代到底以多大的分差选了「过」——决定 +5.54 是否可能是设计伪影。"""
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
from collections import defaultdict


CF = ".team-work/rollout-regret-v1/prod/cf"
ROWS = ".team-work/rollout-regret-v1/prod/rows.json"
ARMS = ("2", "3", "worst")
RANK_TAG = {"rank1": "1", "rank2": "2", "rank3": "3", "worst": "worst"}


def kind_of(key):
    return key.split(":", 1)[0] if ":" in key else key


def load_cf():
    out = defaultdict(dict)
    for path in glob.glob(os.path.join(CF, "*.json")):
        name = os.path.basename(path)[:-5]
        if name.endswith("-worst"):
            tag, base = "worst", name[:-6]
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


def q(vals, p):
    s = sorted(vals)
    k = (len(s) - 1) * p
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


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
        if not recs:
            continue
        anyrec = None
        for a in ARMS:
            if a in recs:
                anyrec = recs[a]
                break
        if anyrec is None:
            continue
        plan = anyrec["prefix_plan"]["candidates"]
        if len(plan) != 2:
            continue
        tk, ak = kind_of(plan[0]["action_key"]), kind_of(plan[1]["action_key"])
        gap = plan[1]["total_score"] - plan[0]["total_score"]
        d = r["cf"]["2"] - r["baseline_score"] if "2" in r["cf"] else None
        cells[(tk, ak)].append((gap, d, r["unit"], plan[0]["total_score"], plan[1]["total_score"]))

    print("## 二元响应窗：首选与次选的分差分布，以及强制次选的 Δ\n")
    print("| (首选,次选) | 窗数 | 分差中位 | 分差均值 | 分差 Q1 | 分差 Q3 | Δ 均值 | 95% CI | 分差>60 占比 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for (tk, ak), items in sorted(cells.items(), key=lambda kv: -len(kv[1])):
        if len(items) < 40:
            continue
        gaps = [x[0] for x in items]
        ds = [(x[2], x[1]) for x in items if x[1] is not None]
        res = unit_ci(ds) if len(ds) >= 20 else None
        big = sum(1 for g in gaps if g < -60) / len(gaps)
        print("| (%s,%s) | %d | %+.1f | %+.1f | %+.1f | %+.1f | %s | %s | %.1f%% |"
              % (tk, ak, len(items), statistics.median(gaps), statistics.fmean(gaps),
                 q(gaps, .25), q(gaps, .75),
                 ("%+.2f" % res[0]) if res else "—",
                 ("[%+.2f, %+.2f]" % (res[2], res[3])) if res else "—",
                 100.0 * big))
    print()
    print("说明：分差 = 次选总分 − 首选总分（负数 = 父代更偏好首选）。")
    print("「分差>60 占比」列的是 分差 < −60 的比例，即把鸣牌常数提高 60 也翻不过来的窗口占比。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
