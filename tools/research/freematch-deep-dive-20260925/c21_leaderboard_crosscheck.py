#!/usr/bin/env python3
"""C21b：**用官方周榜反算我们的账**——把「重建的房分」与平台自己的数字对拍。

平台侧（`leaderboard-week.json` 的 `me`）给的是本次会话账号的
`rooms` / `firsts` / `score`；我方侧有 `room-scores.json`（从官方 events.json 全量复算）。

若两者在同一时间窗内对得上，那么：
  * 我们的房分重建**经过平台自身的交叉验证**；
  * 「每房净分」这个目标量有平台口径背书，不是我们自说自话。

对拍方式（避开周界与账号口径的麻烦）：取两个相邻快照，用**增量**比——
平台增量 = (rooms₂−rooms₁, score₂−score₁)；我方增量 = 同一时间窗内该账号的房数与该账号各房 `my_total` 之和。
房的时间用审计目录 mtime 近似（房结束时写入），误差 ±1 分钟量级。
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
import os
import sys
import datetime as dt
from pathlib import Path

ROOT = _PROJECT_ROOT
SCORES = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/room-scores.json')
SNAPS = _project_file(_PROJECT_ROOT, ROOT / "datasets" / "leaderboard" / "snapshots")
ACCOUNT = "u_13495c3d79c8"


def main() -> int:
    data = json.load(open(SCORES, encoding="utf-8"))
    games = data["games"]
    rooms = {row["room_id"]: row for row in data["rooms"]}

    # 每房：时间（取该房任一局的 audit 目录 mtime）与我们该房各局 my_total 之和
    room_time = {}
    for path in glob.glob(str(_project_file(_PROJECT_ROOT, ROOT / "artifacts" / "sessions" / "*" / "audit" / "runs" / "*"))):
        name = os.path.basename(path)
        room_time.setdefault(name, os.path.getmtime(path))
    # 更稳：按 room_id 找 —— 房分记录里没有 run_id，改用事件文件时间
    room_file_time = {}
    for pattern in ("artifacts/sessions/*/official/**/events.json",
                    "datasets/derived/*/official/**/events.json"):
        for path in glob.glob(str(_project_file(_PROJECT_ROOT, ROOT / pattern)), recursive=True):
            base = os.path.basename(os.path.dirname(path))
            if base not in room_file_time or os.path.getmtime(path) > room_file_time[base]:
                room_file_time[base] = os.path.getmtime(path)

    account_room_total = collections.defaultdict(float)
    account_room_games = collections.Counter()
    for game in games:
        ids = game.get("seat_user_ids") or []
        if ACCOUNT not in ids:
            continue
        account_room_total[game["room_id"]] += float(game.get("my_total") or 0.0)
        account_room_games[game["room_id"]] += 1

    rows = []
    for path in sorted(glob.glob(str(_project_file(_PROJECT_ROOT, SNAPS / "*" / "leaderboard-week.json")))):
        payload = json.load(open(path, encoding="utf-8"))
        me = payload.get("me") or {}
        if me.get("user_id") != ACCOUNT:
            continue
        rows.append((payload.get("as_of"), me.get("rooms"), me.get("firsts"), me.get("score")))
    rows.sort()
    print("| 快照时刻 | rooms | firsts | score |")
    print("| --- | --- | --- | --- |")
    for as_of, rooms_n, firsts, score in rows:
        print("| %s | %s | %s | %s |" % (dt.datetime.fromtimestamp(as_of).strftime("%m-%d %H:%M"), rooms_n, firsts, score))
    print()
    print("| 窗口 | 平台 rooms 增量 | 平台 score 增量 | 我方复算房数 | 我方复算分 | 差 |")
    print("| --- | --- | --- | --- | --- | --- |")
    for (t1, r1, _f1, s1), (t2, r2, _f2, s2) in zip(rows, rows[1:]):
        picked = []
        for room_id in account_room_total:
            stamp = room_file_time.get(room_id)
            if stamp is None:
                continue
            if t1 <= stamp <= t2:
                picked.append(room_id)
        mine = sum(account_room_total[room_id] for room_id in picked)
        print("| %s → %s | %s | %s | %d | %+.0f | %s |"
              % (dt.datetime.fromtimestamp(t1).strftime("%m-%d %H:%M"),
                 dt.datetime.fromtimestamp(t2).strftime("%m-%d %H:%M"),
                 (r2 - r1) if (isinstance(r2, int) and isinstance(r1, int)) else "?",
                 (s2 - s1) if (isinstance(s2, int) and isinstance(s1, int)) else "?",
                 len(picked), mine,
                 ((s2 - s1) - mine) if (isinstance(s2, int) and isinstance(s1, int)) else "?"))
    print()
    missing = [room_id for room_id in account_room_total if room_id not in room_file_time]
    print("我方复算覆盖房数 = %d（其中取不到时间戳 %d 个）" % (len(account_room_total), len(missing)))
    print("我方复算总分 = %+.0f" % sum(account_room_total.values()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
