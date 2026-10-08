#!/usr/bin/env python3
"""C21：**与周榜头部选手同局时的实测差距**（用官方榜单当标签，不用模拟）。

数据：`review/freematch-deep-dive-20260925/room-scores.json`（620 局，含每局 `seat_user_ids`
与 `totals`、每轮 `winner`/`scores`/`multiplier`）+ `datasets/leaderboard/snapshots/*/leaderboard-week.json`。

为什么这条比模拟更有说服力：同局 = 同一副牌山、同一套庄家轮转、同一个对手池，
所以「我方 vs 头部选手」的差是**配对**的，不含牌山与对手池的混杂。

口径与限制（必须与结论同读）：
* 榜单是**快照**，用最新快照给历史对局打标签属于**近似**（选手可能当时还没上榜）；
  因此另报「全时段榜（leaderboard-all）」标签作为稳定性对照。
* 分数向量座位序 = 0/1/2/3，与 `seat_user_ids` 同序。
* 聚类单位 = 房；CI 用房间级 bootstrap。
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

import collections
import glob
import json
import random
import statistics
import sys
from pathlib import Path

ROOT = _PROJECT_ROOT
SCORES = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/room-scores.json')
LB = _project_file(_PROJECT_ROOT, ROOT / "datasets" / "leaderboard" / "snapshots")


def latest_board(name: str):
    paths = sorted(glob.glob(str(_project_file(_PROJECT_ROOT, LB / "*" / ("leaderboard-%s.json" % name)))))
    if not paths:
        return {}, {}
    payload = json.load(open(paths[-1], encoding="utf-8"))
    rows = payload.get("top") or []
    ids = {}
    for row in rows:
        uid = row.get("user_id")
        if uid:
            ids[uid] = row
    return ids, payload


def boot_ci(values, clusters, iters=2000, seed=7):
    """按房聚类的 bootstrap：resample rooms with replacement."""
    by_room = collections.defaultdict(list)
    for value, room in zip(values, clusters):
        by_room[room].append(value)
    room_ids = list(by_room)
    if not room_ids:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    means = []
    for _ in range(iters):
        picked = [rng.choice(room_ids) for _ in room_ids]
        pool = [v for room in picked for v in by_room[room]]
        means.append(statistics.fmean(pool))
    means.sort()
    return (means[int(0.025 * iters)], means[int(0.975 * iters)])


def main() -> int:
    data = json.load(open(SCORES, encoding="utf-8"))
    week_ids, week_payload = latest_board("week")
    all_ids, all_payload = latest_board("all")
    print("周榜标签 %d 人；全时段榜标签 %d 人" % (len(week_ids), len(all_ids)))
    if week_payload:
        prev = week_payload.get("prev") or {}
        for row in (prev.get("top") or [])[:3]:
            uid = row.get("user_id")
            if uid:
                week_ids.setdefault(uid, row)
    games = data["games"]

    buckets = {"week": collections.defaultdict(list), "all": collections.defaultdict(list)}
    room_of = {}
    rounds = {"week": collections.defaultdict(lambda: {"me": 0.0, "them": 0.0, "n": 0}),
              "all": collections.defaultdict(lambda: {"me": 0.0, "them": 0.0, "n": 0})}
    # 只统计「该局确有榜上选手」的轮次；上一版把无榜局也计入分母，会稀释对手均值。
    elite_rounds = {"week": collections.defaultdict(lambda: {"me": 0.0, "them": 0.0, "n": 0}),
                    "all": collections.defaultdict(lambda: {"me": 0.0, "them": 0.0, "n": 0})}
    for game in games:
        ids = game.get("seat_user_ids") or []
        totals = game.get("totals") or []
        my_seat = game.get("my_seat")
        if my_seat is None or len(ids) != 4 or len(totals) != 4:
            continue
        room = game["room_id"]
        for tag, board in (("week", week_ids), ("all", all_ids)):
            hits = [i for i, uid in enumerate(ids) if i != my_seat and uid in board]
            key = "elite_present" if hits else "no_elite"
            buckets[tag][key].append((float(totals[my_seat]), room))
            if hits:
                best = max(float(totals[i]) for i in hits)
                buckets[tag]["paired_vs_best"].append((float(totals[my_seat]) - best, room))
            for round_row in game.get("rounds") or ():
                winner = round_row.get("winner")
                scores = round_row.get("scores") or []
                if winner is None or len(scores) != 4:
                    continue
                if hits:
                    cell = elite_rounds[tag][room]
                    cell["n"] += 1
                    cell["me"] += float(scores[my_seat])
                    cell["them"] += statistics.fmean(float(scores[i]) for i in hits)
        room_of[game["game_id"]] = room

    for tag in ("week", "all"):
        elite = buckets[tag]["elite_present"]
        none = buckets[tag]["no_elite"]
        print()
        print("== 标签：%s榜（最新快照）" % ("周" if tag == "week" else "全时段"))
        for name, rows in (("有榜上选手", elite), ("无榜上选手", none)):
            if not rows:
                continue
            values = [v for v, _ in rows]
            rooms = [r for _, r in rows]
            lo, hi = boot_ci(values, rooms)
            print("  %s：局数 %d，我方每局均分 %+.3f（房聚类 95%% CI [%+.3f, %+.3f]），房间数 %d"
                  % (name, len(values), statistics.fmean(values), lo, hi, len(set(rooms))))
        paired = buckets[tag].get("paired_vs_best") or []
        if paired:
            values = [v for v, _ in paired]
            rooms = [r for _, r in paired]
            lo, hi = boot_ci(values, rooms)
            print("  与同局最强榜上选手的**配对差**（我方 − 其最高分）：%+.3f，CI [%+.3f, %+.3f]，局数 %d"
                  % (statistics.fmean(values), lo, hi, len(values)))
            wins = sum(1 for v in values if v > 0)
            print("  我方在该局分数高于该选手的比例 = %.1f%%（%d/%d）" % (100.0 * wins / len(values), wins, len(values)))
        cell = elite_rounds[tag]
        if cell:
            my_round = sum(c["me"] for c in cell.values())
            their_round = sum(c["them"] for c in cell.values())
            n_round = sum(c["n"] for c in cell.values())
            print("  逐轮口径（**只含有榜上选手的局**）：总轮数 %d，我方每轮 %+.4f，榜上选手（同局均值）每轮 %+.4f，差 %+.4f"
                  % (n_round, my_round / n_round, their_round / n_round,
                     (my_round - their_round) / n_round))

    # --- 追加：逐轮差的房聚类 CI 与「房间第一名率」 ---
    for tag in ("week", "all"):
        cell = elite_rounds[tag]
        if cell:
            per_room = []
            for room, c in cell.items():
                if c["n"] > 0:
                    per_room.append((c["me"] - c["them"]) / c["n"])
            if per_room:
                mean = statistics.fmean(per_room)
                rng = random.Random(11)
                means = []
                for _ in range(2000):
                    picked = [rng.choice(per_room) for _ in per_room]
                    means.append(statistics.fmean(picked))
                means.sort()
                print("  [%s] 逐轮差的房聚类 95%% CI = [%+.4f, %+.4f]（房间数 %d）"
                      % (tag, means[50], means[1950], len(per_room)))
    # 房间级：某房冠军率（我们四座总分最高）
    room_totals = collections.defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
    room_has_elite = {}
    for game in games:
        ids = game.get("seat_user_ids") or []
        totals = game.get("totals") or []
        if len(ids) != 4 or len(totals) != 4:
            continue
        room = game["room_id"]
        for seat in range(4):
            room_totals[room][seat] += float(totals[seat])
        my_seat = game.get("my_seat")
        if my_seat is None:
            continue
        has = any(i != my_seat and uid in week_ids for i, uid in enumerate(ids))
        room_has_elite[room] = room_has_elite.get(room) or has
    firsts = {"elite": [0, 0], "no_elite": [0, 0]}
    for room, totals in room_totals.items():
        if room not in room_has_elite:
            continue
        me_index = None
        for game in games:
            if game["room_id"] == room:
                me_index = game.get("my_seat")
                break
        if me_index is None:
            continue
        top = max(totals)
        key = "elite" if room_has_elite[room] else "no_elite"
        firsts[key][0] += 1
        if abs(totals[me_index] - top) < 1e-9:
            firsts[key][1] += 1
    for key in ("elite", "no_elite"):
        n, w = firsts[key]
        if n:
            print("  房间第一名率（%s）= %.1f%%（%d/%d）"
                  % ("有榜上选手" if key == "elite" else "无榜上选手", 100.0 * w / n, w, n))
    print()
    print("可用局数 =", len(games))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
