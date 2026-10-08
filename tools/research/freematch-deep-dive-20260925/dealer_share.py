#!/usr/bin/env python3
"""庄家持有率核算：我们的亏空里有多少来自「坐庄次数」而不是「打得差」。

杭麻得分为「底分 × 番 ×（庄家 ×8 / 闲家 ×1）」，庄家位价值极高。
如果我们在整个样本里坐庄的比例低于 1/4，那就是一个结构性亏空，
而不是任何单个决策的错误。本脚本直接从官方 rounds 的 dealer 字段统计。

同时报告：
- 各座位坐庄局数占比（期望各 1/4）
- 我方在庄局/闲局的得分与胡牌率
- 我方胡牌后续庄的比例（庄家自摸胡是否续庄）
- 连庄段长度分布

用法：
    .venv/bin/python review/freematch-deep-dive-20260925/dealer_share.py
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
import collections
import glob
import json
import os


def iter_games():
    paths = []
    paths.extend(glob.glob(os.path.join("artifacts", "sessions", "*", "official", "dl-*", "events.json")))
    paths.extend(glob.glob(os.path.join("datasets", "derived", "*", "official", "*", "official", "dl-*", "events.json")))
    seen = {}
    for path in sorted(set(paths)):
        try:
            with open(path) as fh:
                payload = json.load(fh)
        except (OSError, ValueError):
            continue
        game_id = payload.get("game_id")
        if game_id:
            prior = seen.get(game_id)
            if prior is None or os.path.getmtime(path) >= prior[0]:
                seen[game_id] = (os.path.getmtime(path), payload)
    return [payload for _mt, payload in seen.values()]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--me", default="u_13495c3d79c8")
    args = ap.parse_args(argv)

    dealer_rounds = collections.Counter()
    score_by_role = collections.defaultdict(list)
    wins_by_role = collections.Counter()
    rounds_by_role = collections.Counter()
    streak_len = collections.Counter()
    total_rounds = 0
    games = 0

    for payload in iter_games():
        seats = [s.get("user_id") for s in payload.get("seats") or []]
        if args.me not in seats or len(seats) != 4:
            continue
        me = seats.index(args.me)
        rounds = payload.get("rounds") or []
        if not rounds:
            continue
        games += 1
        prev_dealer = None
        run = 0
        for rnd in rounds:
            dealer = rnd.get("dealer")
            winner = rnd.get("winner")
            scores = rnd.get("scores") or []
            if not (type(dealer) is int and 0 <= dealer < 4):
                continue
            if len(scores) < 4:
                continue
            total_rounds += 1
            dealer_rounds[dealer] += 1
            role = "dealer" if dealer == me else "non_dealer"
            rounds_by_role[role] += 1
            score_by_role[role].append(scores[me])
            if winner == me:
                wins_by_role[role] += 1
            if prev_dealer == dealer:
                run += 1
            else:
                if run:
                    streak_len[run] += 1
                run = 1
            prev_dealer = dealer
        if run:
            streak_len[run] += 1

    print("场数 %d，局数 %d" % (games, total_rounds))
    print()
    print("| 座位 | 坐庄局数 | 占比 | 期望占比 |")
    print("| --- | --- | --- | --- |")
    for seat in range(4):
        mark = "（我方）" if seat == 0 else ""
        print("| 座位 %d | %d | %.2f%% | 25.00%% |"
              % (seat, dealer_rounds[seat], 100.0 * dealer_rounds[seat] / total_rounds))
    print()
    print("我方坐庄 %d 局（%.2f%%），闲家 %d 局"
          % (rounds_by_role["dealer"],
             100.0 * rounds_by_role["dealer"] / total_rounds,
             rounds_by_role["non_dealer"]))
    print()
    for role in ("dealer", "non_dealer"):
        values = score_by_role[role]
        if not values:
            continue
        print("%s：均分 %+.2f，局数 %d，我方胡牌率 %.2f%%"
              % (role, sum(values) / len(values), len(values),
                 100.0 * wins_by_role[role] / len(values)))
    print()
    print("连庄段长度分布（段长 → 段数）：", dict(sorted(streak_len.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())