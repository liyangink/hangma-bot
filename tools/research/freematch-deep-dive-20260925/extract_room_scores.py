#!/usr/bin/env python3
"""自由赛房级与单局级得分提取（只读，无网络）。

数据来源：官方下载的 events.json（每个 dl-* 目录一份），其中
- "seats" 按座位顺序给出 user_id（座位 0..3）
- "rounds" 每局给出 scores（四座分数向量）、winner（座位号）、dealer、
  is_draw、multiplier

本脚本把每房每场的 8 局分数按我方座位累加，输出：
- 房级：我方全场分、四座名次、与首名差距
- 局级：每局我方得分、是否我方胡、是否他胡、是否流局、庄家座位
用法：
    .venv/bin/python review/freematch-deep-dive-20260925/extract_room_scores.py [--out JSON]
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
import glob
import json
import os
import sys


def load_rooms(root: str = "artifacts/sessions"):
    """返回 [(mtime, room_id, session_tag, game_id, payload)...]，按 mtime 排序。

    **必须按 game_id 去重。** 官方牌谱按 dl-* 分片下载，同一场会被重复下载
    （2026-09-25 实测 7 个 game_id 有冗余副本，其中一个下载了 3 份）。
    不去重会把同一局的分数重复计入，2026-09-25 就因此把 -835 报成了 -863。
    去重口径：同一 game_id 保留 mtime 最新的一份；rounds 逐字相同时结果不变，
    不一致时保留最新并记录，供人工核对。
    """
    latest = {}
    patterns = [
        os.path.join(root, "*", "official", "dl-*", "events.json"),
        # 部分完赛房（例如接线修复前的 a_acc191732472）没有落在 artifacts/sessions/，
        # 而是由 datamart 归档到 datasets/derived/<池>/official/<房>/official/dl-*/。
        # 只扫 artifacts 会漏掉这些房，导致本地口径小于官方周榜口径。
        os.path.join("datasets", "derived", "*", "official", "*", "official", "dl-*", "events.json"),
        # 更深一层的目录（2026-09-26 第 51 轮发现）：完赛房也可能落在
        # artifacts/sessions/<tag>/official/<x>/official/dl-*/，只扫单层会漏房。
        # 2026-09-25 的 a_c6c4ed2f7d6e（+224）就是这样被漏掉的，正是当时
        # 与官方周榜对账时「差 +224」的来源。
        os.path.join(root, "*", "official", "**", "dl-*", "events.json"),
    ]
    paths = []
    for pattern in patterns:
        paths.extend(glob.glob(pattern, recursive=True))
    for path in sorted(set(paths)):
        try:
            with open(path) as fh:
                payload = json.load(fh)
        except (OSError, ValueError):
            continue
        game_id = payload.get("game_id")
        if not game_id:
            continue
        tag = path.split(os.sep)[2]
        candidate = (os.path.getmtime(path), payload.get("room_id"), tag, game_id, payload)
        prior = latest.get(game_id)
        if prior is None or candidate[0] >= prior[0]:
            latest[game_id] = candidate
    out = sorted(latest.values(), key=lambda r: r[0])
    return out


def analyze(payload, me):
    seats = [s.get("user_id") for s in payload.get("seats") or []]
    if me not in seats:
        return None
    my = seats.index(me)
    rounds = payload.get("rounds") or []
    total = [0, 0, 0, 0]
    per_round = []
    for rnd in rounds:
        sc = rnd.get("scores") or [0, 0, 0, 0]
        for i in range(min(4, len(sc))):
            total[i] += sc[i]
        per_round.append({
            "round_no": rnd.get("round_no"),
            "dealer": rnd.get("dealer"),
            "winner": rnd.get("winner"),
            "is_draw": rnd.get("is_draw"),
            "multiplier": rnd.get("multiplier"),
            "scores": sc,
            "my_score": sc[my] if my < len(sc) else None,
            "i_won": rnd.get("winner") == my,
            "i_dealt": rnd.get("dealer") == my,
        })
    order = sorted(range(4), key=lambda i: -total[i])
    return {
        "room_id": payload.get("room_id"),
        "game_id": payload.get("game_id"),
        "status": payload.get("status"),
        "seat_user_ids": seats,
        "my_seat": my,
        "totals": total,
        "my_total": total[my],
        "my_rank": order.index(my) + 1,
        "top_total": max(total),
        "gap_to_top": max(total) - total[my],
        "rounds": per_round,
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--me", default="u_13495c3d79c8", help="我方 user_id")
    ap.add_argument("--root", default="artifacts/sessions")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    games = []
    for _mt, room, tag, game_id, payload in load_rooms(args.root):
        a = analyze(payload, args.me)
        if a is None:
            continue
        a["session_tag"] = tag
        games.append(a)

    by_room = {}
    for g in games:
        by_room.setdefault(g["room_id"], []).append(g)

    rooms = []
    for rid, gs in by_room.items():
        rooms.append({
            "room_id": rid,
            "session_tag": gs[0]["session_tag"],
            "games": len(gs),
            "my_total": sum(g["my_total"] for g in gs),
            "my_rank1": sum(1 for g in gs if g["my_rank"] == 1),
            "my_rank4": sum(1 for g in gs if g["my_rank"] == 4),
            "mean_gap_to_top": round(sum(g["gap_to_top"] for g in gs) / len(gs), 2),
        })
    rooms.sort(key=lambda r: r["room_id"])

    print(f"房数 {len(rooms)}  场数 {len(games)}  我方合计 {sum(r['my_total'] for r in rooms)}")
    print(f"{'room':<20}{'tag':<40}{'场':>3}{'我方分':>8}{'第1':>5}{'第4':>5}{'均差首名':>9}")
    for r in rooms:
        print(f"{r['room_id']:<20}{r['session_tag']:<40}{r['games']:>3}{r['my_total']:>8}"
              f"{r['my_rank1']:>5}{r['my_rank4']:>5}{r['mean_gap_to_top']:>9}")

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w") as fh:
            json.dump({"rooms": rooms, "games": games}, fh, ensure_ascii=False, indent=1)
        print(f"写出 {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
