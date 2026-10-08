#!/usr/bin/env python3
"""主审：从 regret 批次的逐桌产物里取回候选全表，看父代首选与次选到底差在哪。

数据：.team-work/rollout-regret-v1/prod/cf/*.json 的 task.window_record.candidates，
含每个候选的 action_key / is_emergency / total_score / 完整 trace（分项 + shanten_after）。
真值来自 prod/rows.json。
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
import os
from collections import Counter, defaultdict

CF = ".team-work/rollout-regret-v1/prod/cf"
ROWS = ".team-work/rollout-regret-v1/prod/rows.json"
ARMS = ("2", "3", "worst")
RANK_FILE = {"1": "rank1", "2": "rank2", "3": "rank3", "worst": "worst"}


def suit_of(key):
    tile = key.split(":", 1)[1] if ":" in key else key
    if tile in ("东", "南", "西", "北", "中", "发", "白"):
        return "字牌"
    last = tile[-1]
    if last == "w":
        return "万"
    if last == "t":
        return "条"
    if last == "b":
        return "筒"
    return "未知"


def load_windows():
    out = defaultdict(dict)
    for path in glob.glob(os.path.join(CF, "*.json")):
        name = os.path.basename(path)[:-5]
        unit = name.split("-w")[0]
        tag = name.rsplit("-", 1)[1]
        rank = None
        for r, t in RANK_FILE.items():
            if t == tag:
                rank = r
        if rank is None:
            continue
        try:
            payload = json.load(open(path))
        except Exception:
            continue
        out[unit][rank] = payload
    return out


def main() -> int:
    rows = json.load(open(ROWS))
    win = load_windows()
    truth = {r["unit"]: r for r in rows}
    units = [u for u in win if u in truth]
    print("unit 数：%d（含 rank1 的 %d）" % (len(units), sum(1 for u in units if "1" in win[u])))

    emerg_top = 0
    top_suit = Counter()
    tie_windows = 0
    tie_top_is_emerg = 0
    tie_second_is_emerg = 0
    n_plan = Counter()
    seen1 = 0
    for u in units:
        rec = win[u].get("1")
        if rec is None:
            # rank1 只跑了 16 个 unit；其余 unit 用任一臂的 prefix_plan 取回同一份计划。
            for a in ARMS:
                if a in win[u]:
                    rec = win[u][a]
                    break
        if rec is None:
            continue
        seen1 += 1
        cands = rec["prefix_plan"]["candidates"]
        t = truth[u]
        n_plan[len(cands)] += 1
        top = cands[0]
        if top.get("is_emergency"):
            emerg_top += 1
        top_suit[suit_of(top["action_key"])] += 1
        if "2" in t.get("parent_total", {}) and t["parent_total"]["2"] == t["parent_total_top"]:
            tie_windows += 1
            if top.get("is_emergency"):
                tie_top_is_emerg += 1
            if len(cands) > 1 and cands[1].get("is_emergency"):
                tie_second_is_emerg += 1
    print("父代首选是紧急候选：%d / %d = %.1f%%" % (emerg_top, seen1, 100.0 * emerg_top / max(1, seen1)))
    print("父代首选的牌张类别分布：%s" % dict(top_suit))
    print("完全并列窗口：%d；其中首选是紧急 %d、次选是紧急 %d" % (tie_windows, tie_top_is_emerg, tie_second_is_emerg))
    print("n_plan 分布：%s" % dict(sorted(n_plan.items())))

    print()
    print("| 臂 | 窗 | 首选紧急 | 替代紧急 | 同牌类 | 首选字牌 | 替代字牌 | Δ向听=0 | 替代与首选同牌 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for arm in ARMS:
        stats = Counter()
        for u in units:
            if arm not in win[u]:
                continue
            cands = win[u][arm]["prefix_plan"]["candidates"]
            top = cands[0]
            t = truth[u]
            if arm not in t.get("parent_total", {}):
                continue
            alt_key = win[u][arm]["forced_action_key"]
            idx = None
            for i, c in enumerate(cands):
                if c["action_key"] == alt_key:
                    idx = i
            if idx is None:
                continue
            alt = cands[idx]
            stats["n"] += 1
            if top.get("is_emergency"):
                stats["top_emerg"] += 1
            if alt.get("is_emergency"):
                stats["alt_emerg"] += 1
            if suit_of(top["action_key"]) == suit_of(alt["action_key"]):
                stats["same_suit"] += 1
            if suit_of(top["action_key"]) == "字牌":
                stats["top_honor"] += 1
            if suit_of(alt["action_key"]) == "字牌":
                stats["alt_honor"] += 1
            if t["parent_shanten"][arm] == t["shanten_after_top"]:
                stats["ds0"] += 1
            if idx == 0:
                stats["same_tile"] += 1
        n = max(1, stats["n"])
        print("| %s | %d | %.1f%% | %.1f%% | %.1f%% | %.1f%% | %.1f%% | %.1f%% | %.1f%% |"
              % (arm, stats["n"], 100.0 * stats["top_emerg"] / n, 100.0 * stats["alt_emerg"] / n,
                 100.0 * stats["same_suit"] / n, 100.0 * stats["top_honor"] / n,
                 100.0 * stats["alt_honor"] / n, 100.0 * stats["ds0"] / n,
                 100.0 * stats["same_tile"] / n))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
