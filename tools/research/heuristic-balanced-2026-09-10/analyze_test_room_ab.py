#!/usr/bin/env python3
"""测试房 2 对 2 配对 A/B 的事后分析：同一副牌、同一张桌，按场配对比较两个臂。

数据源：`GET /api/test-rooms/{room}/games`（批次列表）→ `GET /api/test-rooms/{room}/games/{batch}/events`
（免认证赛后原文；`seats` 给座位→身份，`rounds` 给每局结果）。

判据：
1. 每个 batch（= 一场，8 单局）算出四席的场终局分；
2. 每个 batch 内按臂取均值（A/B 臂 vs C/D 臂），得到**同场配对差**；
3. 输出配对差的均值与 95% 区间，以及各臂的胜局数、庄胡率、爆头/七对占比；
4. 同时打印原始每局 scores 是否满足"四条相加为 0"，用来确认分数字段是**每局增量**
   而不是累计值（replay.py 明确警告原始 scores 不能直接当累计积分）。

用法：
  analyze_test_room_ab.py --room t_18dfc9e674b4 --map .private/test-room-.../room.json
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/heuristic-balanced-2026-09-10'

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
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

import httpx

BASE = "https://10.240.169.190:18080"
PORTAL = Path("/Users/liyang/Projects/Opensource/hangma-bot/.private/portal-session/cookie.txt")
Z = 1.959964


def arm_map(room_json: Path):
    """令牌文件 -> 策略名；再与 user_id 关联由调用方补充。"""
    cfg = json.loads(room_json.read_text())
    return {item["slot"]: item.get("strategy", cfg["strategy"]) for item in cfg["identities"]}


def fetch(room: str):
    raw = PORTAL.read_text().strip()
    headers = {"Cookie": raw if "=" in raw else "session=" + raw}
    with httpx.Client(verify=False, timeout=60.0, headers=headers) as client:
        payload = client.get(BASE + "/api/test-rooms/{}/games".format(room)).json()
        # 实测形态是 {"games": [...]}；旧文档写的是裸数组，两种都接受。
        games = payload.get("games") if isinstance(payload, dict) else payload
        docs = {}
        for entry in games:
            batch = entry.get("batch")
            # 免认证端点有 IP 限速：实测连续拉取会 429，必须退避重试（不能当失败跳过，
            # 否则样本会静默变少，把"少了几场"读成结果）。
            for attempt in range(6):
                resp = client.get(BASE + "/api/test-rooms/{}/games/{}/events".format(room, batch))
                if resp.status_code == 200:
                    docs[batch] = resp.json()
                    break
                if resp.status_code != 429:
                    print("batch {} 拉取失败 HTTP {}".format(batch, resp.status_code), file=sys.stderr)
                    break
                time.sleep(2.0 * (attempt + 1))
            time.sleep(0.8)
        return games, docs


def seat_identity(doc):
    """seats[] -> {座位: 身份串}；v30 起只有 AI 昵称与 user_id。"""
    seats = doc.get("seats") or []
    out = {}
    for index, seat in enumerate(seats):
        if isinstance(seat, dict):
            out[index] = seat.get("user_id") or seat.get("name") or "seat{}".format(index)
        else:
            out[index] = str(seat)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--room", required=True)
    parser.add_argument("--map", required=True, dest="room_json")
    parser.add_argument("--user-arm", required=True,
                        help="user_id=arm 的逗号分隔映射（由预检结果得出）")
    args = parser.parse_args()
    user_arm = dict(pair.split("=") for pair in args.user_arm.split(",") if pair)
    games, docs = fetch(args.room)
    print("批次（场）数：", len(docs), " 列表状态：",
          sorted({entry.get("status") for entry in games}))
    if not docs:
        return 1
    deltas_ok = True
    per_game = {}
    kinds = defaultdict(int)
    for batch, doc in sorted(docs.items()):
        seats = seat_identity(doc)
        total = defaultdict(int)
        wins = defaultdict(int)
        for item in doc.get("rounds") or []:
            scores = item.get("scores")
            if not isinstance(scores, list) or len(scores) != 4:
                continue
            if sum(scores) != 0:
                deltas_ok = False
            winner = item.get("winner")
            for seat in range(4):
                total[seat] += scores[seat]
                if winner == seat:
                    wins[seat] += 1
        by_arm = defaultdict(list)
        for seat in range(4):
            identity = seats.get(seat)
            arm = user_arm.get(identity)
            if arm is None:
                continue
            by_arm[arm].append(total[seat])
        if len(by_arm) == 2:
            arms = sorted(by_arm)
            a, b = arms
            per_game[batch] = (statistics.mean(by_arm[a]) - statistics.mean(by_arm[b]), a, b)
        print("batch %-3s %s  分=%s 胜局=%s" % (
            batch, {seats.get(s): user_arm.get(seats.get(s)) for s in range(4)},
            [total[s] for s in range(4)], [wins[s] for s in range(4)]))
    print()
    print("每局 scores 四家和为零：", "是（可作每局增量）" if deltas_ok else "否（口径存疑，勿直接累加）")
    values = [entry[0] for entry in per_game.values()]
    if len(values) >= 2:
        mean = statistics.mean(values)
        se = statistics.stdev(values) / math.sqrt(len(values))
        print("配对差（臂 %s 减 臂 %s）：n=%d 均值=%.3f 95%%CI=[%.3f, %.3f]" % (
            per_game[next(iter(per_game))][1], per_game[next(iter(per_game))][2],
            len(values), mean, mean - Z * se, mean + Z * se))
    else:
        print("样本不足（%d 场），只留原始读数" % len(values))
    return 0


if __name__ == "__main__":
    sys.exit(main())
