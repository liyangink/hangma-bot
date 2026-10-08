#!/usr/bin/env python3
"""P33 补充：只用「立刻胡番数」分层的单独报告（主审指定的最干净先验检验）。

- P24（主池）：全部状态立刻胡番 = 1 ⇒ 结构性无对照；只报 1 番层的点估计与 CI。
- P86-02（补充批次，同配对工装、另一侧轴：弃胡有靶）：1 番 vs 2 番的层间差。
本脚本不改变预登记的任何判定规则，只是把 Q1 要求的番数分层单独成表。
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

import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = _PROJECT_ROOT
OUT = _project_file(_PROJECT_ROOT, ROOT / ".team-work/p33-deferral-heterogeneity")
SEED = 20260925
BOOT = 10000


def load():
    walls = list(csv.DictReader(open(_project_file(_PROJECT_ROOT, OUT / "paired_walls.csv"), encoding="utf-8")))
    states = list(csv.DictReader(open(_project_file(_PROJECT_ROOT, OUT / "states.csv"), encoding="utf-8")))
    pool = list(csv.DictReader(open(_project_file(_PROJECT_ROOT, OUT / "pool_rows.csv"), encoding="utf-8")))
    for s in states:
        s["hu_fan"] = float(s["hu_fan"]) if s["hu_fan"] not in ("", "None") else None
        s["route_fan"] = float(s["route_fan"]) if s["route_fan"] not in ("", "None") else None
        s["route_over_hu_ratio"] = (float(s["route_over_hu_ratio"])
                                    if s["route_over_hu_ratio"] not in ("", "None") else None)
    for w in walls:
        w["delta_table_defer_minus_hu"] = float(w["delta_table_defer_minus_hu"])
    return walls, states, pool


def root_means(walls, batch):
    per = defaultdict(list)
    for w in walls:
        if w["batch"] == batch:
            per[w["root_id"]].append(w["delta_table_defer_minus_hu"])
    return {r: float(np.mean(v)) for r, v in per.items()}


def boot_diff(a, b, b_iter=BOOT, seed=SEED):
    """两独立层（根级）均值差的 bootstrap 区间。"""
    a, b = np.array(a, dtype=float), np.array(b, dtype=float)
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(b_iter):
        da = a[rng.integers(0, len(a), len(a))].mean()
        db = b[rng.integers(0, len(b), len(b))].mean()
        diffs.append(da - db)
    diffs = np.array(diffs)
    return float(diffs.mean()), float(np.quantile(diffs, 0.025)), float(np.quantile(diffs, 0.975))


def main() -> int:
    walls, states, pool = load()
    lines = []

    def say(m=""):
        print(m)
        lines.append(m)

    p24 = [s for s in states if s["batch"] == "P24"]
    p86 = [s for s in states if s["batch"] == "P86-02"]
    rm24, rm86 = root_means(walls, "P24"), root_means(walls, "P86-02")

    say("## A. P24 主池：立刻胡番数分层")
    fans24 = sorted({s["hu_fan"] for s in p24})
    pool24_fans = sorted({float(p["hu_fan"]) for p in pool if p["pool"] == "P24_pool"})
    say(f"- 16 个开发状态的立刻胡番：{fans24}（全部 1 番）；P24 合格窗池 95 行的 hu_fan：{pool24_fans}")
    say(f"- ⇒ **P24 在构造上是 100%「立刻胡番 = 1」，没有 2 番/4 番对照，番数分层在 P24 上不可识别**（不是数据缺失，是池定义的结果）")
    v = [rm24[s["root_id"]] for s in p24]
    arr = np.array(v, dtype=float)
    rng = np.random.default_rng(SEED)
    idx = rng.integers(0, arr.size, size=(BOOT, arr.size))
    ci = np.quantile(arr[idx].mean(axis=1), [0.025, 0.975])
    se = arr.std(ddof=1) / math.sqrt(arr.size)
    say(f"- 1 番层（= 全部 16 根）：Δ̄ {np.mean(v):.4f} 分/桌，"
        f"根级 bootstrap 95% CI [{ci[0]:.3f}, {ci[1]:.3f}]（与主表同口径：B={BOOT}，seed={SEED}）")

    say()
    say("## B. P86-02 补充批次：1 番 vs 2 番（同一配对工装、弃胡有靶的一侧）")
    g1 = [s for s in p86 if s["hu_fan"] == 1]
    g2 = [s for s in p86 if s["hu_fan"] == 2]
    v1 = [rm86[s["root_id"]] for s in g1]
    v2 = [rm86[s["root_id"]] for s in g2]
    say(f"- 1 番层：{len(g1)} 根，Δ̄（弃胡−立刻胡）{np.mean(v1):.3f} 分/桌，逐根 {[round(x,1) for x in sorted(v1)]}")
    say(f"- 2 番层：{len(g2)} 根，Δ̄ {np.mean(v2):.3f} 分/桌，逐根 {[round(x,1) for x in sorted(v2)]}")
    d, lo, hi = boot_diff(v2, v1)
    say(f"- 层间差（2 番 − 1 番）：{d:.3f} 分/桌，根级 bootstrap 95% CI [{lo:.3f}, {hi:.3f}]"
        f"{'（**不含 0**）' if lo > 0 or hi < 0 else '（含 0）'}")
    say(f"- 注：本批 1 番层的爆头路线 fan = 2，2 番层 = 4 ⇒ 路线 fan ÷ 立刻胡 fan 恒为 2，"
        f"番数分层实际检验的是「×2 的绝对增幅」，不是比值。")
    say(f"- 本批没有「立刻胡 4 番」的状态（P85 合格池 142 行里 4 番仅 1 行）⇒ 4 番层**未测**。")

    say()
    say("## C. 两侧轴的机制对照（不同池，不可直接合并）")
    say(f"- P24（立刻胡 1 番、**无靶**）：弃胡 {np.mean(v):.3f} 分/桌（亏）")
    say(f"- P86-02（立刻胡 1 番、有靶）：弃胡 +{np.mean(v1):.3f} 分/桌（赚）")
    say(f"- P86-02（立刻胡 2 番、有靶）：弃胡 +{np.mean(v2):.3f} 分/桌（赚更多）")
    say("- 读数：这条轴的价值由 **是否存在爆头靶** 决定符号，由 **番数水平** 决定幅度；"
        "父代「有靶才弃胡」的开关位置与两侧数据都自洽。")

    payload = {
        "p24_fan_values": fans24,
        "p24_pool_fan_values": pool24_fans,
        "p24_fan1": {"n_roots": len(v), "mean": float(np.mean(v))},
        "p86_fan1": {"n_roots": len(g1), "mean": float(np.mean(v1)), "roots": v1},
        "p86_fan2": {"n_roots": len(g2), "mean": float(np.mean(v2)), "roots": v2},
        "fan2_minus_fan1": {"mean": d, "boot_ci95": [lo, hi]},
    }
    (_project_file(_PROJECT_ROOT, OUT / "fan_strata.json")).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (_project_file(_PROJECT_ROOT, OUT / "fan_strata.log")).write_text("\n".join(lines) + "\n", encoding="utf-8")
    say()
    say(f"写出 {_project_file(_PROJECT_ROOT, OUT/'fan_strata.json')} / {_project_file(_PROJECT_ROOT, OUT/'fan_strata.log')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
