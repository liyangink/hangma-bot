#!/usr/bin/env python3
"""数据盘点：官方牌谱去重、房数、局数、我方座位分布。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/baotou-anatomy-20260925'

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
import sys
from collections import Counter

ME = "u_13495c3d79c8"


def iter_events_paths():
    paths = []
    paths.extend(glob.glob(os.path.join("artifacts", "sessions", "*", "official", "dl-*", "events.json")))
    paths.extend(glob.glob(os.path.join("datasets", "derived", "*", "official", "*", "official", "dl-*", "events.json")))
    return sorted(set(paths))


def main():
    paths = iter_events_paths()
    seen = {}
    dup = 0
    for path in paths:
        try:
            payload = json.load(open(path, encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print("坏文件", path, exc)
            continue
        gid = payload.get("game_id")
        if not gid:
            continue
        if gid in seen:
            dup += 1
            if os.path.getmtime(path) < seen[gid][0]:
                continue
        seen[gid] = (os.path.getmtime(path), path, payload)
    print("events.json 文件 %d；唯一 game_id %d；重复副本 %d" % (len(paths), len(seen), dup))
    rooms = Counter()
    rounds = 0
    me_in = 0
    seats4 = 0
    for _m, _p, doc in seen.values():
        seats = [s.get("user_id") for s in doc.get("seats") or []]
        rooms[doc.get("room_id")] += 1
        if len(seats) == 4:
            seats4 += 1
        if ME in seats:
            me_in += 1
            rounds += len(doc.get("blocks") or [])
    print("唯一房间 %d；含我方的牌谱 %d；含我方单局 %d" % (len(rooms), me_in, rounds))
    print("四座齐全牌谱 %d" % seats4)
    # 座位分布
    seatc = Counter()
    for _m, _p, doc in seen.values():
        seats = [s.get("user_id") for s in doc.get("seats") or []]
        if ME in seats:
            seatc[seats.index(ME)] += 1
    print("我方座位分布", dict(sorted(seatc.items())))
    # block 字段
    for _m, _p, doc in seen.values():
        for blk in doc.get("blocks") or []:
            print("block keys:", sorted(blk.keys()))
            ev = blk.get("events") or []
            print("event types:", sorted({e.get("type") for e in ev}))
            if ev:
                print("sample events:", json.dumps(ev[:3], ensure_ascii=False)[:1500])
            break
        break


if __name__ == "__main__":
    main()
