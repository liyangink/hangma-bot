#!/usr/bin/env python3
"""门禁稳健性分析：均值为正**不足以**认证候选（重尾伪证）。

动机（round 15 实测）：门禁原判据是"均值 > 0 且按根聚类 95% 区间下界 > 0"。对重尾候选
这条判据会**在大样本下认证一个完全无效的候选**。实测 v2_value_upgrade_v1 对 Tier-A：

- 符号检验 p = 0.773（有效根上正 98 / 负 94，就是掷硬币）；
- 但把同一批观测自助外推，"均值判据通过率"随样本量单调上升：
  n=288 -> 14.5%、n=1024 -> 41.8%、n=2900 -> 87.0%、n=10000 -> 100%。

⇒ 样本量越大越容易伪证。因此必须在**有效根**（差值非零）上做符号检验，并要求它显著偏向候选。

本脚本对每个候选池化全部可得门禁跑，输出均值/中位数/5% 截尾均值/符号检验，
并做上面那条外推演示。只读 results.jsonl，不重跑模拟。

用法：
  measure_gate_robustness.py --out review/.../gate-robustness.json
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/heuristic-balanced-2026-09-10'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import collections
import glob
import json
import math
import random
import statistics
from pathlib import Path

Z = 1.959964
REVIEW = _project_file(_PROJECT_ROOT, 'review/heuristic-balanced-2026-09-10')

# 每个候选：跑目录模式、基线、候选
CANDIDATES = (
    ("tier_a", "Tier-A vs V2", "weighted_heuristic_v2", "v2_hu_upgrade_v1",
     ["gate-hu-vs-v2-development", "gate-pool-homogeneous", "gate-repeat-14*"]),
    ("value", "value vs Tier-A", "v2_hu_upgrade_v1", "v2_value_upgrade_v1", ["gate-value-*"]),
    ("tier_b", "tierB vs Tier-A", "v2_hu_upgrade_v1", "v2_hu_upgrade_tierb_v1", ["gate-tierb-*"]),
    ("dealer", "dealer vs Tier-A", "v2_hu_upgrade_v1", "v2_hu_upgrade_dealer_v1", ["gate-dealer-*"]),
)


def root_deltas(patterns, baseline, candidate):
    """池化多个门禁跑，返回 {跑:根 -> 该根的桌内积分差均值}。"""
    out = {}
    for pattern in patterns:
        for directory in sorted(glob.glob(str(_project_file(_PROJECT_ROOT, REVIEW / pattern)))):
            path = Path(directory) / "results.jsonl"
            if not path.exists():
                continue
            pairs = collections.defaultdict(dict)
            for line in path.open(encoding="utf-8"):
                row = json.loads(line)
                key = (row["scenario_id"], tuple(row["seat_permutation"]))
                pairs[key][row["policy_ids_by_seat"][row["seat_permutation"][0]]] = row
            per_root = collections.defaultdict(list)
            for key, arms in pairs.items():
                base_row, cand_row = arms.get(baseline), arms.get(candidate)
                if base_row is None or cand_row is None:
                    continue
                per_root[key[0]].append(
                    cand_row["scores_after"][cand_row["seat_permutation"][0]]
                    - base_row["scores_after"][base_row["seat_permutation"][0]])
            for scenario, values in per_root.items():
                out[Path(directory).name + ":" + scenario] = statistics.mean(values)
    return out


def summarize(values):
    """均值（含根聚类区间）+ 中位数 + 5% 截尾均值 + 符号检验。"""
    ordered = sorted(values)
    n = len(ordered)
    mean = statistics.mean(ordered)
    sd = statistics.stdev(ordered)
    se = sd / math.sqrt(n)
    trim = int(n * 0.05)
    positive = sum(1 for value in ordered if value > 0)
    negative = sum(1 for value in ordered if value < 0)
    informative = positive + negative
    if informative:
        z = (positive - informative / 2) / math.sqrt(informative / 4)
        p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    else:
        z, p = 0.0, 1.0
    return dict(
        roots=n, mean=mean, ci95=[mean - Z * se, mean + Z * se],
        median=statistics.median(ordered),
        trimmed_mean=(statistics.mean(ordered[trim:n - trim]) if n > 2 * trim and trim
                      else mean),
        positive=positive, negative=negative, zero=n - informative,
        sign_z=z, sign_p=p,
        extremes=[ordered[0], ordered[-1]])


def heavy_tail_risk(values, sizes=(288, 1024, 2900, 10000), reps=400, seed=20260912):
    """自助外推：若均值判据的样本量继续加大，同一批观测有多容易被"通过"。"""
    rng = random.Random(seed)
    out = {}
    for size in sizes:
        passed = 0
        for _ in range(reps):
            sample = [rng.choice(values) for _ in range(size)]
            sd = statistics.stdev(sample)
            if statistics.mean(sample) - Z * sd / math.sqrt(size) > 0:
                passed += 1
        out[str(size)] = passed / reps
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    report = dict(schema="gate-robustness/1", candidates={})
    for key, label, baseline, candidate, patterns in CANDIDATES:
        values = root_deltas(patterns, baseline, candidate)
        if len(values) < 5:
            continue
        entry = summarize(list(values.values()))
        entry["label"] = label
        entry["runs"] = len({name.split(":")[0] for name in values})
        # 只有无效候选才需要那条外推演示；对强阳候选跑它没有意义且费时。
        if entry["sign_p"] > 0.05:
            entry["naive_mean_pass_rate"] = heavy_tail_risk(list(values.values()))
        report["candidates"][key] = entry
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + chr(10),
                              encoding="utf-8")
    for key, entry in report["candidates"].items():
        print("%-8s %-18s 跑=%2d 根=%4d 均值=%7.3f CI=[%6.3f,%6.3f] 中位=%6.2f 截尾=%7.3f 正/负=%3d/%3d p=%.4f" % (
            key, entry["label"], entry["runs"], entry["roots"], entry["mean"],
            entry["ci95"][0], entry["ci95"][1], entry["median"], entry["trimmed_mean"],
            entry["positive"], entry["negative"], entry["sign_p"]))
        if "naive_mean_pass_rate" in entry:
            print("         均值判据外推通过率：" + ", ".join(
                "n=%s -> %.1f%%" % (size, 100 * rate)
                for size, rate in entry["naive_mean_pass_rate"].items()))


if __name__ == "__main__":
    main()
