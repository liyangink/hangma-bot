#!/usr/bin/env python3
"""主审：把 regret 面板按**真实窗口族比例**重加权，给出线上分布口径的分/桌估计与聚类 CI。

- 族权重来自 real_window_family.py 在全部 32,374 个真实窗口上的测量
  （分母 = 有自由度即候选数 >= 2 的 11,968 窗）。
- 点估计：Δ = Σ_f w_f · mean_f(Δ)，Δ 来自 regret 面板（rows.json 的 arm 2）。
- CI：**按 unit 重抽样**（bootstrap），每次重抽同时重算各格均值再加权，
  因此保留了「同 unit 内窗口相关」这一结构。
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
import math
import os
import random
import statistics
from collections import defaultdict

CF = ".team-work/rollout-regret-v1/prod/cf"
ROWS = ".team-work/rollout-regret-v1/prod/rows.json"
ARMS = ("2", "3", "worst")
RANK_TAG = {"rank1": "1", "rank2": "2", "rank3": "3", "worst": "worst"}

# 真实分布（real_window_family.py 在 32,374 窗上实测），分母 11,968
REAL_COUNTS = {
    ("discard", "discard"): 9415,
    ("pass", "chi"): 704,
    ("peng", "pass"): 577,
    ("chi", "pass"): 504,
    ("hu", "discard"): 279,
    ("pass", "peng"): 260,
    ("chi", "chi"): 88,
    ("gang", "pass"): 40,
    ("gang", "discard"): 33,
    ("peng", "gang"): 6,
    ("discard", "gang"): 3,
    ("pass", "gang"): 1,
    ("hu", "gang"): 1,
}
TOTAL_REAL = sum(REAL_COUNTS.values())


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


def main() -> int:
    rows = json.load(open(ROWS))
    cf = load_cf()
    arm = "2"
    per_unit = defaultdict(list)  # unit -> [(cell, delta)]
    for r in rows:
        key = (r["unit"], r["phase"], r["round_no"], r["trigger_seq"])
        recs = cf.get(key)
        if not recs or arm not in recs or arm not in r.get("cf", {}):
            continue
        anyrec = recs[arm]
        plan = anyrec["prefix_plan"]["candidates"]
        if len(plan) < 2:
            continue
        cell = (kind_of(plan[0]["action_key"]), kind_of(plan[1]["action_key"]))
        per_unit[r["unit"]].append((cell, r["cf"][arm] - r["baseline_score"]))

    units = sorted(per_unit)
    print("参与重加权的 unit：%d，窗：%d" % (len(units), sum(len(v) for v in per_unit.values())))

    def weighted(sample_units):
        num = 0.0
        wsum = 0.0
        cells = defaultdict(list)
        for u in sample_units:
            for cell, d in per_unit[u]:
                cells[cell].append(d)
        for cell, n_real in REAL_COUNTS.items():
            w = n_real / TOTAL_REAL
            vals = cells.get(cell)
            if not vals:
                continue  # 该族在样本里没有 → 不计入（等价于用 0 近似），单独记录
            num += w * statistics.fmean(vals)
            wsum += w
        return num / wsum if wsum else float("nan")

    point = weighted(units)
    missing = [c for c in REAL_COUNTS if not any(c == cell for v in per_unit.values() for cell, _ in v)]
    print("样本中缺席的真实族（按 0 近似）：%s" % (missing or "无"))

    rng = random.Random(20261026)
    boots = []
    for _ in range(2000):
        sample = [units[rng.randrange(len(units))] for _ in range(len(units))]
        boots.append(weighted(sample))
    boots.sort()
    lo = boots[int(0.025 * len(boots))]
    hi = boots[int(0.975 * len(boots))]
    print()
    print("## 真实分布加权的 arm2 regret")
    print("- 点估计 **%+.2f 分/桌**" % point)
    print("- unit bootstrap 95%% CI **[%+.2f, %+.2f]**" % (lo, hi))
    print("- 对照：面板原始口径 %+.2f 分/桌" % statistics.fmean(
        d for v in per_unit.values() for _, d in v))

    print()
    print("## 逐族贡献（族权重 × 族均值）")
    cells = defaultdict(list)
    for v in per_unit.values():
        for cell, d in v:
            cells[cell].append(d)
    print("| 族 | 真实权重 | 样本窗数 | 族均值 | 贡献 |")
    print("| --- | --- | --- | --- | --- |")
    tot = 0.0
    for cell, n_real in sorted(REAL_COUNTS.items(), key=lambda kv: -kv[1]):
        w = n_real / TOTAL_REAL
        vals = cells.get(cell)
        if not vals:
            continue
        m = statistics.fmean(vals)
        tot += w * m
        print("| %s/%s | %.2f%% | %d | %+.2f | %+.3f |" % (cell[0], cell[1], 100 * w, len(vals), m, w * m))
    print("| **合计** | | | | **%+.2f** |" % tot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
