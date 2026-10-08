#!/usr/bin/env python3
"""主审：起手向听分层下的胜负与番值——我方 vs 对手（同局配对）。

数据：.team-work/hand-quality-v1/records.jsonl（每座每巡向听、起手向听、首次听牌）
      review/baotou-anatomy-20260925/rounds.jsonl（winner、fan、detail、scores、爆头）
按 (game_id, round_no) join。
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

import json
import math
import statistics
from collections import Counter, defaultdict

HQ = ".team-work/hand-quality-v1/records.jsonl"
BT = "review/baotou-anatomy-20260925/rounds.jsonl"
ME = "u_13495c3d79c8"


def load(path):
    out = {}
    with open(path) as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except Exception:
                continue
            out[(d.get("game_id"), d.get("round_no"))] = d
    return out


def wilson(k, n):
    if n == 0:
        return (float("nan"),) * 3
    p = k / n
    se = math.sqrt(p * (1 - p) / n)
    return p, p - 1.96 * se, p + 1.96 * se


def main() -> int:
    hq, bt = load(HQ), load(BT)
    keys = [k for k in hq if k in bt]
    print("hand-quality 局 %d，baotou 局 %d，join %d" % (len(hq), len(bt), len(keys)))

    rows = []
    winner_mismatch = 0
    for k in keys:
        a, b = hq[k], bt[k]
        users = a.get("users") or []
        my_seat = None
        for i, u in enumerate(users):
            if u == ME:
                my_seat = i
        if my_seat is None:
            continue
        if a.get("winner") != b.get("winner_seat"):
            winner_mismatch += 1
        rows.append((a, b, my_seat))
    print("含我方座位 %d 局；winner 口径不一致 %d" % (len(rows), winner_mismatch))

    # 每座记录
    per_seat = []  # (round_key, seat, is_me, start_shanten, won, win_pts, baotou, fan, is_dealer)
    for a, b, my_seat in rows:
        winner = a.get("winner")
        scores = b.get("scores") or [0, 0, 0, 0]
        detail = b.get("detail") or []
        fan = b.get("fan")
        seats_bt = {s.get("seat"): s for s in (b.get("seats") or [])}
        for sd in a.get("seats") or []:
            seat = sd.get("seat")
            if seat is None:
                continue
            won = (winner == seat)
            per_seat.append({
                "seat": seat,
                "is_me": seat == my_seat,
                "start": sd.get("start_shanten"),
                "won": won,
                "pts": scores[seat] if won else None,
                "baotou": bool(seats_bt.get(seat, {}).get("final_baotou")) if won else False,
                "fan": fan if won else None,
                "detail": detail if won else [],
                "dealer": a.get("dealer") == seat,
                "melds": sd.get("melds"),
            })
    print("座位-局 %d" % len(per_seat))

    print()
    print("## 1. 按「本座起手向听」分层：胡率与均胡牌分（我方 vs 对手）\n")
    print("| 起手向听 | 分组 | 座位-局 | 胡率 | 95% CI | 均胡牌分 | 爆头率 | 均番 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for band, lo, hi in (("0-1", 0, 1), ("2", 2, 2), ("3", 3, 3), ("4", 4, 4), ("5+", 5, 99)):
        for label, pred in (("我方", True), ("对手", False)):
            sub = [x for x in per_seat if x["is_me"] == pred and x["start"] is not None and lo <= x["start"] <= hi]
            n = len(sub)
            if n < 50:
                continue
            w = sum(1 for x in sub if x["won"])
            p, a1, b1 = wilson(w, n)
            pts = [x["pts"] for x in sub if x["won"] and x["pts"] is not None]
            bt_rate = sum(1 for x in sub if x["baotou"]) / w if w else float("nan")
            fans = [x["fan"] for x in sub if x["fan"] is not None]
            print("| %s | %s | %d | %.2f%% | [%.2f, %.2f] | %.2f | %.1f%% | %.3f |"
                  % (band, label, n, 100 * p, 100 * a1, 100 * b1,
                     statistics.fmean(pts) if pts else float("nan"),
                     100 * bt_rate, statistics.fmean(fans) if fans else float("nan")))

    print()
    print("## 2. 同局配对：按「我方起手向听」分层的四家对照\n")
    print("| 我方起手 | 组 | 座位-局 | 胡率 | 均胡牌分 | 爆头率 |")
    print("| --- | --- | --- | --- | --- | --- |")
    by_round = defaultdict(list)
    for a, b, my_seat in rows:
        pass
    # 重算：按局分组
    round_map = {}
    for a, b, my_seat in rows:
        round_map[(a["game_id"], a["round_no"])] = (a, b, my_seat)
    for band, lo, hi in ((">=4", 4, 99), ("<=3", 0, 3)):
        mine, theirs = [], []
        for a, b, my_seat in rows:
            sd_me = None
            for sd in a.get("seats") or []:
                if sd.get("seat") == my_seat:
                    sd_me = sd
            if sd_me is None or sd_me.get("start_shanten") is None:
                continue
            if not (lo <= sd_me["start_shanten"] <= hi):
                continue
            for x in per_seat:
                pass
            break
        # 上面的循环方式太低效，改用直接过滤
        for a, b, my_seat in rows:
            sds = {sd.get("seat"): sd for sd in (a.get("seats") or [])}
            me = sds.get(my_seat)
            if me is None or me.get("start_shanten") is None:
                continue
            if not (lo <= me["start_shanten"] <= hi):
                continue
            winner = a.get("winner")
            scores = b.get("scores") or [0, 0, 0, 0]
            seats_bt = {s.get("seat"): s for s in (b.get("seats") or [])}
            for seat in range(4):
                rec = {"won": winner == seat,
                       "pts": scores[seat] if winner == seat else None,
                       "baotou": bool(seats_bt.get(seat, {}).get("final_baotou")) if winner == seat else False}
                (mine if seat == my_seat else theirs).append(rec)
        for label, sub in (("我方", mine), ("对手三座", theirs)):
            n = len(sub)
            if n == 0:
                continue
            w = sum(1 for x in sub if x["won"])
            pts = [x["pts"] for x in sub if x["pts"] is not None]
            bt_rate = sum(1 for x in sub if x["baotou"]) / w if w else float("nan")
            print("| %s | %s | %d | %.2f%% | %.2f | %.1f%% |"
                  % (band, label, n, 100 * w / n, statistics.fmean(pts) if pts else float("nan"), 100 * bt_rate))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
