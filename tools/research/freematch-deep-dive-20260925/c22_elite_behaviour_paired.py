#!/usr/bin/env python3
"""C22：**周榜强手在同一局里到底做了什么不同**（用官方榜单做标签、同局配对）。

数据：`review/baotou-anatomy-20260925/rounds.jsonl`（每局四座逐座字段，含 `user_id`）
      + `datasets/leaderboard/snapshots/*/leaderboard-week.json`（周榜 top-32 user_id）。

设计：同一局内把四座分成三组——**我方 / 周榜强手 / 其他对手**——对每个可观测行为量做
「组内均值」与「同局配对差」（我方 − 强手、其他 − 强手）。配对消掉了牌山、庄家轮转与局况。

必须与结论同读的限制：
* 榜单是**快照**标签（近似）——另用全时段榜做稳定性对照；
* 这是**观察性**比较：强手可能恰恰因为打得多而出现在这些局里；
* 多重比较：本表一次报 10 个量，单个量的 CI 需按此打折（未做正式校正，只报全部量）。
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
ROUNDS = _project_file(_PROJECT_ROOT, 'review/baotou-anatomy-20260925/rounds.jsonl')
LB = _project_file(_PROJECT_ROOT, ROOT / "datasets" / "leaderboard" / "snapshots")

FEATURES = [
    ("entered_baotou", "曾进入爆头"),
    ("entry_turn", "爆头进入巡目"),
    ("first_tenpai_turn", "首次听牌巡目"),
    ("first_std_tenpai_turn", "首次普通型听牌巡目"),
    ("melds_end", "终局副露数"),
    ("whites_drawn", "摸到财神张数"),
    ("whites_discarded", "弃财神张数"),
    ("whites_end", "终局手留财神"),
    ("discards_n", "弃牌次数"),
    ("draws_n", "摸牌次数"),
]


def load_board(name: str):
    paths = sorted(glob.glob(str(_project_file(_PROJECT_ROOT, LB / "*" / ("leaderboard-%s.json" % name)))))
    payload = json.load(open(paths[-1], encoding="utf-8"))
    ids = {}
    for row in payload.get("top") or []:
        if row.get("user_id"):
            ids[row["user_id"]] = row
    prev = (payload.get("prev") or {}).get("top") or []
    for row in prev:
        if row.get("user_id"):
            ids.setdefault(row["user_id"], row)
    return ids


def main() -> int:
    week = load_board("week")
    alltime = load_board("all")
    print("周榜标签 %d 人；全时段榜标签 %d 人" % (len(week), len(alltime)))
    rows = [json.loads(line) for line in ROUNDS.open(encoding="utf-8") if line.strip()]
    print("局数 =", len(rows))

    for tag, board in (("week", week), ("all", alltime)):
        # per-round group membership
        totals = {key: {"me": [], "elite": [], "other": []} for key, _ in FEATURES}
        won = {"me": [0, 0], "elite": [0, 0], "other": [0, 0]}
        paired = {key: {"me_minus_elite": [], "other_minus_elite": []} for key, _ in FEATURES}
        rooms_per_round = []
        for row in rows:
            room = row.get("room_id")
            seats = row.get("seats") or []
            group_of = {}
            for seat_row in seats:
                if seat_row.get("is_me"):
                    group_of[seat_row["seat"]] = "me"
                elif seat_row.get("user_id") in board:
                    group_of[seat_row["seat"]] = "elite"
                else:
                    group_of[seat_row["seat"]] = "other"
            if "elite" not in group_of.values():
                continue
            rooms_per_round.append(room)
            row_fan = row.get("fan")
            winner = row.get("winner_seat")
            for seat_row in seats:
                group = group_of[seat_row["seat"]]
                won[group][0] += 1
                if row.get("is_draw"):
                    continue
                if winner == seat_row["seat"] and isinstance(row_fan, (int, float)):
                    won[group][1] += 1
                for key, _label in FEATURES:
                    value = seat_row.get(key)
                    if isinstance(value, bool):
                        value = int(value)
                    if isinstance(value, (int, float)):
                        totals[key][group].append(value)
            elite_values = {key: [] for key, _ in FEATURES}
            other_values = {key: [] for key, _ in FEATURES}
            me_values = {key: [] for key, _ in FEATURES}
            for seat_row in seats:
                group = group_of[seat_row["seat"]]
                target = {"me": me_values, "elite": elite_values, "other": other_values}[group]
                for key, _label in FEATURES:
                    value = seat_row.get(key)
                    if isinstance(value, bool):
                        value = int(value)
                    if isinstance(value, (int, float)):
                        target[key].append(float(value))
            for key, _label in FEATURES:
                if elite_values[key] and me_values[key]:
                    paired[key]["me_minus_elite"].append(statistics.fmean(me_values[key]) - statistics.fmean(elite_values[key]))
                if elite_values[key] and other_values[key]:
                    paired[key]["other_minus_elite"].append(statistics.fmean(other_values[key]) - statistics.fmean(elite_values[key]))

        print()
        print("== 标签：%s榜（含强手的局 %d 局）" % ("周" if tag == "week" else "全时段", len(rooms_per_round)))
        print("| 量 | 我方 | 强手 | 其他 | 我方−强手（同局配对） | 95% CI | 其他−强手 |")
        print("| --- | --- | --- | --- | --- | --- | --- |")
        for key, label in FEATURES:
            cells = totals[key]
            me_mean = statistics.fmean(cells["me"]) if cells["me"] else float("nan")
            el_mean = statistics.fmean(cells["elite"]) if cells["elite"] else float("nan")
            ot_mean = statistics.fmean(cells["other"]) if cells["other"] else float("nan")
            values = paired[key]["me_minus_elite"]
            lo = hi = float("nan")
            if values:
                rng = random.Random(5)
                means = []
                for _ in range(1200):
                    picked = [rng.choice(values) for _ in values]
                    means.append(statistics.fmean(picked))
                means.sort()
                lo, hi = means[30], means[1170]
            other_values = paired[key]["other_minus_elite"]
            other_mean = statistics.fmean(other_values) if other_values else float("nan")
            print("| %s | %.4f | %.4f | %.4f | %+.4f | [%+.4f, %+.4f] | %+.4f |"
                  % (label, me_mean, el_mean, ot_mean, statistics.fmean(values) if values else 0.0, lo, hi, other_mean))
        for group in ("me", "elite", "other"):
            n, w = won[group]
            if n:
                print("%s：该组座位-局数 %d，胡牌率 %.2f%%" % (group, n, 100.0 * w / n))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
