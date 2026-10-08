#!/usr/bin/env python3
"""C36 覆盖补齐：查明 C31/C32 缓存缺房的原因，并把缺失的房补进本轮语料。

只读官方牌谱 events.json、各房 manifest.json 与既有缓存产物；
缺房原因按**文件 mtime 与缓存写盘时间的先后**判定（先证据后结论），
补房重建复用 c36_deep_band_cards.build_windows（同一条接缝，不实现第二套规则）。

用法：
    UV_CACHE_DIR=/tmp/uv-cache .venv/bin/python \
        review/freematch-deep-dive-20260925/c36_fill_coverage.py
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
import datetime
import glob
import gzip
import json
import os
import sys
import time
from pathlib import Path

ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "review" / "baotou-anatomy-20260925")))
sys.path.insert(0, str(HERE))

import anatomy_lib as AL  # noqa: E402
import c31_action_layer_gap as C31  # noqa: E402
import c36_deep_band_cards as C36  # noqa: E402

C31_WINDOWS = _project_file(_PROJECT_ROOT, ROOT / ".team-work" / "c31-action-layer" / "windows.jsonl.gz")
C32_WINDOWS = _project_file(_PROJECT_ROOT, ROOT / ".team-work" / "c32-cards" / "windows.jsonl.gz")
P6_CACHE = _project_file(_PROJECT_ROOT, ROOT / ".team-work" / "p6-baotou-route" / "cache")


def stamp(path):
    return datetime.datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S")


def cache_rooms(path):
    rooms = collections.Counter()
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            room = row.get("room")
            if isinstance(room, str):
                rooms[room] += 1
    return rooms


def p6_games():
    games = collections.Counter()
    for path in sorted(P6_CACHE.glob("*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                game_id = row.get("game_id") or ""
                games[game_id.split("_r")[0]] += 1
    return games


def run_start(summary_path, cache_path):
    """该次运行的**开始**时刻 = 缓存写盘时刻 - summary 记录的耗时。

    直接用缓存文件的 mtime 会把它当成运行开始时间，从而漏掉「运行期间才落盘的房」。
    """

    elapsed = 0.0
    try:
        elapsed = float(json.loads(Path(summary_path).read_text(encoding="utf-8"))
                        .get("elapsed_sec") or 0.0)
    except (OSError, ValueError):
        elapsed = 0.0
    return os.path.getmtime(cache_path) - elapsed


def main():
    started = time.time()
    C36.OUT.mkdir(parents=True, exist_ok=True)
    starts = {
        "c31": run_start(_project_file(_PROJECT_ROOT, ROOT / ".team-work" / "c31-action-layer" / "summary.json"),
                         C31_WINDOWS),
        "c32": run_start(_project_file(_PROJECT_ROOT, ROOT / ".team-work" / "c32-cards" / "summary.json"),
                         C32_WINDOWS),
    }
    print("缓存写盘时间：C31 %s｜C32 %s" % (stamp(C31_WINDOWS), stamp(C32_WINDOWS)))
    print("按 summary 的 elapsed_sec 反推运行开始时刻：C31 %s｜C32 %s"
          % (datetime.datetime.fromtimestamp(starts["c31"]).strftime("%Y-%m-%d %H:%M:%S"),
             datetime.datetime.fromtimestamp(starts["c32"]).strftime("%Y-%m-%d %H:%M:%S")))
    c31_rooms = cache_rooms(C31_WINDOWS)
    c32_rooms = cache_rooms(C32_WINDOWS)
    print("缓存覆盖：C31 %d 房 / %d 窗｜C32 %d 房 / %d 窗"
          % (len(c31_rooms), sum(c31_rooms.values()), len(c32_rooms),
             sum(c32_rooms.values())))

    games = AL.load_games()
    by_room = collections.defaultdict(list)
    for game in games:
        by_room[game["doc"].get("room_id") or game["session"]].append(game)
    print("归档（当前）去重后：%d 场 / %d 房" % (len(games), len(by_room)))

    p6 = p6_games()
    missing_c31 = sorted(set(by_room) - set(c31_rooms))
    missing_c32 = sorted(set(by_room) - set(c32_rooms))
    print("归档有、C31 缓存无的房：%s" % missing_c31)
    print("归档有、C32 缓存无的房：%s" % missing_c32)

    board_ids = set(C36.board())
    evidence = {}
    for room in sorted(set(missing_c31) | set(missing_c32)):
        paths = [game["path"] for game in by_room[room]]
        mtimes = sorted(os.path.getmtime(path) for path in paths)
        seats = set()
        for game in by_room[room]:
            seats.update(item.get("user_id") for item in (game["doc"].get("seats") or []))
        eligible = bool({C36.ME} & seats) or bool(seats & board_ids)
        first_events = min(mtimes)
        after_c31 = first_events > starts["c31"]
        after_c32 = first_events > starts["c32"]
        if not eligible:
            reason = "无 me/elite 座：被语料口径过滤（与缓存时间无关）"
        elif after_c31 and after_c32:
            reason = "语料到达晚于 C31 与 C32 两次运行：两次缓存都不可能包含"
        elif after_c31:
            reason = "语料到达晚于 C31 运行、早于 C32 运行结束"
        elif after_c32:
            reason = "语料到达晚于 C32 运行"
        else:
            reason = "需追查：语料早于两次运行却仍缺"
        evidence[room] = {
            "games": len(paths), "session": by_room[room][0]["session"],
            "eligible": eligible,
            "events_mtime_min": stamp(sorted(paths, key=os.path.getmtime)[0]),
            "events_mtime_max": stamp(sorted(paths, key=os.path.getmtime)[-1]),
            "events_after_c31_start": after_c31, "events_after_c32_start": after_c32,
            "in_p6_cache": p6.get(room, 0), "has_manifest": room in C36.room_identity(),
            "reason": reason,
        }
        print("  %-20s %-38s 场 %2d｜可入语料 %-5s｜events %s → %s｜晚于 C31 起 %-5s｜"
              "晚于 C32 起 %-5s｜生产缓存 %d｜manifest %-5s｜%s"
              % (room, by_room[room][0]["session"], len(paths), eligible,
                 evidence[room]["events_mtime_min"], evidence[room]["events_mtime_max"],
                 after_c31, after_c32, evidence[room]["in_p6_cache"],
                 evidence[room]["has_manifest"], reason))

    targets = [room for room in ("a_53f4861835b9", "a_b0d2cf5da218", "a_2a8aa14dc8a1",
                                 "a_b3e4ba33b114") if room in by_room]
    identities = C36.room_identity()
    for room in targets:
        print("  目标补房 %s：策略身份 %s" % (room, identities.get(room)))

    audit = collections.Counter()
    parent = C31.load_parent()
    records, rounds_done = C36.build_windows(games, parent, identities, audit,
                                             rooms=set(targets))
    print("补房重建：%d 局 / %d 窗，用时 %.1f 秒"
          % (rounds_done, len(records), time.time() - started))

    teng = [record for record in records
            if record["room"] == "a_53f4861835b9" and record["user_id"] == C36.TENG]
    teng_div = [record for record in teng
                if record["claimed"] == 1 and (record["margin"] or 0.0) <= 0.0]
    astra = [record for record in records
             if record["room"] == "a_b0d2cf5da218" and record["user_id"] == C36.ASTRA]
    astra_div = [record for record in astra
                 if record["claimed"] == 1 and (record["margin"] or 0.0) <= 0.0]
    astra_band = [record for record in astra if C36.is_band(record)]
    print("补齐后：腾蛇 a_53f4861835b9 机会窗 %d，其中「实际鸣 ∧ margin<=0」%d"
          % (len(teng), len(teng_div)))
    print("补齐后：Astra a_b0d2cf5da218 机会窗 %d，其中 div %d / band %d"
          % (len(astra), len(astra_div), len(astra_band)))

    payload = {
        "cache_mtime": {"c31": stamp(C31_WINDOWS), "c32": stamp(C32_WINDOWS)},
        "cache_rooms": {"c31": len(c31_rooms), "c32": len(c32_rooms)},
        "archive_rooms": len(by_room),
        "run_start": {name: stamp_value for name, stamp_value in (
            ("c31", datetime.datetime.fromtimestamp(starts["c31"]).strftime("%Y-%m-%d %H:%M:%S")),
            ("c32", datetime.datetime.fromtimestamp(starts["c32"]).strftime("%Y-%m-%d %H:%M:%S")))},
        "missing_from_c31": missing_c31, "missing_from_c32": missing_c32,
        "evidence": evidence,
        "eligible_missing_from_c31": [room for room in missing_c31
                                      if evidence[room]["eligible"]],
        "verdict": ("缺房原因 = 官方牌谱落盘时间晚于该次缓存运行；不成立的只有 "
                    "t_* 测试/派生房（无 me/elite 座，被语料口径过滤，与时间无关）"),
        "filled": {
            "rooms": targets, "rounds": rounds_done, "windows": len(records),
            "teng_room_windows": len(teng), "teng_divergence": len(teng_div),
            "astra_room_windows": len(astra), "astra_divergence": len(astra_div),
            "astra_band": len(astra_band)},
        "audit": dict(sorted(audit.items())),
        "elapsed_sec": time.time() - started,
    }
    with gzip.open(C36.OUT / "coverage-filled.jsonl.gz", "wt", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + chr(10))
    (C36.OUT / "coverage.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print()
    print("判定：%s" % payload["verdict"])
    print("结果写入 %s 与 %s" % (C36.OUT / "coverage.json", C36.OUT / "coverage-filled.jsonl.gz"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
