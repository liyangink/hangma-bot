#!/usr/bin/env python3
"""我方自由赛成绩的统计显著性核算（只读）。

回答一个问题：-863 分是「真的弱」还是「高方差的噪声」？
统计单位分别取单局（game）与房（room，聚类单位），并给出：
- 局级均值/标准差/标准误/95% 置信区间
- 房级均值/标准差/标准误/95% 置信区间（房是聚类单位，主口径）
- 房内 bootstrap（对房重抽样，保留房内相关性）的 95% 区间
- 名次分布（每局第 1/2/3/4 名占比）
- 要把「每局 +5 分」的优势做到 95% 显著，需要多少局/多少房

用法：
    .venv/bin/python review/freematch-deep-dive-20260925/score_significance.py
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
import json
import math
import random
import statistics


def load(path: str):
    with open(path) as fh:
        return json.load(fh)


def ci95(values):
    """正态近似 95% 区间（均值 ± 1.96·SE）。"""
    n = len(values)
    if n < 2:
        return None
    mean = statistics.fmean(values)
    sd = statistics.stdev(values)
    se = sd / math.sqrt(n)
    return {"n": n, "mean": mean, "sd": sd, "se": se,
            "lo": mean - 1.96 * se, "hi": mean + 1.96 * se}


def cluster_bootstrap(rooms, draws=20000, seed=20260925):
    """按房整块重抽样的 bootstrap：保留房内相关，房为聚类单位。"""
    rng = random.Random(seed)
    per_room = [r["my_total"] for r in rooms]
    game_counts = [r["games"] for r in rooms]
    means = []
    for _ in range(draws):
        pick = [rng.randrange(len(per_room)) for _ in per_room]
        tot = sum(per_room[i] for i in pick)
        n = sum(game_counts[i] for i in pick)
        means.append(tot / n)
    means.sort()
    return {"lo": means[int(0.025 * draws)], "hi": means[int(0.975 * draws)],
            "median": means[draws // 2]}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", default="review/freematch-deep-dive-20260925/room-scores.json")
    ap.add_argument("--exclude-tags", nargs="*", default=[],
                    help="排除的会话标签（例如只保留 09-25 SSE 房）")
    ap.add_argument("--only-tags", nargs="*", default=None)
    args = ap.parse_args(argv)

    data = load(args.scores)
    games = [g for g in data["games"]
             if (args.only_tags is None or g.get("session_tag") in args.only_tags)
             and g.get("session_tag") not in args.exclude_tags]
    rooms = [r for r in data["rooms"]
             if (args.only_tags is None or r.get("session_tag") in args.only_tags)
             and r.get("session_tag") not in args.exclude_tags]

    per_game = [g["my_total"] for g in games]
    per_room = [r["my_total"] for r in rooms]

    print("== 自由赛成绩显著性核算 ==")
    print(f"房数 {len(rooms)}，场数 {len(games)}")
    gci = ci95(per_game)
    rci = ci95(per_room)
    print("\n-- 单局口径 --")
    print(f"  均值 {gci['mean']:+.2f} 分/局，标准差 {gci['sd']:.1f}，"
          f"95% CI [{gci['lo']:+.2f}, {gci['hi']:+.2f}]")
    print("\n-- 房级口径（聚类单位，主口径）--")
    print(f"  均值 {rci['mean']:+.2f} 分/房，标准差 {rci['sd']:.1f}，"
          f"95% CI [{rci['lo']:+.2f}, {rci['hi']:+.2f}]")
    cb = cluster_bootstrap(rooms)
    print(f"  房级 cluster bootstrap 95% CI [{cb['lo']:+.2f}, {cb['hi']:+.2f}]"
          f"（中位 {cb['median']:+.2f}）")

    ranks = [0, 0, 0, 0]
    for g in games:
        ranks[g["my_rank"] - 1] += 1
    print("\n-- 每局名次分布 --")
    for i, c in enumerate(ranks):
        print(f"  第{i+1}名 {c:>4} 次 ({100.0*c/len(games):5.1f}%)")

    print("\n-- 要把「每局 +delta」做到 95% 显著所需样本量 --")
    sd_game = gci["sd"]
    sd_room = rci["sd"]
    for delta in (2, 5, 10):
        n_games = (1.96 * sd_game / delta) ** 2
        n_rooms = (1.96 * sd_room / delta) ** 2
        print(f"  +{delta} 分/局 → 约 {math.ceil(n_games)} 局"
              f"（约 {math.ceil(n_games/10.2)} 房）；房级口径约 {math.ceil(n_rooms)} 房")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
