#!/usr/bin/env python3
"""主审独立复算：爆头占胡比例、均番值、均胡牌分（全量房，官方 events）。

这是本会话引用最多的数字（「我们爆头 15% vs 榜上 29%」），此前由分析 agent 产出。
本脚本直接从官方 round_ended 事件的 data.detail / data.fan / data.scores 重算，
不依赖任何派生数据集。
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
import statistics

ME = "u_13495c3d79c8"


def iter_rooms():
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
        if not game_id:
            continue
        prior = seen.get(game_id)
        if prior is None or os.path.getmtime(path) >= prior[0]:
            seen[game_id] = (os.path.getmtime(path), payload)
    return [payload for _mt, payload in seen.values()]


def main() -> int:
    stats = {"me": collections.Counter(), "opp": collections.Counter()}
    fan_me, fan_opp = [], []
    pts_me, pts_opp = [], []
    rooms = set()
    for payload in iter_rooms():
        seats = [s.get("user_id") for s in payload.get("seats") or []]
        if ME not in seats or len(seats) != 4:
            continue
        me = seats.index(ME)
        rooms.add(payload.get("room_id"))
        for block in payload.get("blocks") or []:
            for event in block.get("events") or []:
                if event.get("type") != "round_ended":
                    continue
                data = event.get("data") or {}
                winner = event.get("seat")
                detail = data.get("detail") or []
                fan = data.get("fan")
                scores = data.get("scores") or []
                if not (type(winner) is int and 0 <= winner < 4) or not scores:
                    continue
                group = "me" if winner == me else "opp"
                stats[group]["wins"] += 1
                if any("爆头" in str(item) for item in detail):
                    stats[group]["baotou"] += 1
                if type(fan) is int:
                    (fan_me if group == "me" else fan_opp).append(fan)
                if winner < len(scores):
                    (pts_me if group == "me" else pts_opp).append(scores[winner])

    print("房数 %d" % len(rooms))
    print()
    print("| 量 | 我方 | 对手（三座合计） |")
    print("| --- | --- | --- |")
    m, o = stats["me"], stats["opp"]
    print("| 胡牌次数 | %d | %d |" % (m["wins"], o["wins"]))
    print("| 爆头胡次数 | %d | %d |" % (m["baotou"], o["baotou"]))
    print("| **爆头占胡比例** | **%.2f%%** | **%.2f%%** |"
          % (100.0*m["baotou"]/max(1,m["wins"]), 100.0*o["baotou"]/max(1,o["wins"])))
    print("| 均番值 | %.3f | %.3f |" % (statistics.fmean(fan_me), statistics.fmean(fan_opp)))
    print("| 均胡牌分 | %.2f | %.2f |" % (statistics.fmean(pts_me), statistics.fmean(pts_opp)))
    print()
    print("注：对手是三座合计，逐座均值未加权处理，仅作量级对照。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())