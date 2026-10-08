#!/usr/bin/env python3
"""G69 事后描述性房级配对重采样；保留同房双方与整桌单局关联。"""

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

from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g69-same-room-route-chain-20260928/route_rounds.jsonl.gz')
OUT = SOURCE.with_name("room_bootstrap.json")
SEED = 20260928
DRAWS = 20000
METRICS = ("any_ready", "high_ready", "ready_then_win", "high_win",
           "high_win_with_prior_high", "high_win_without_prior_high", "win")


def measures(row: dict) -> Counter:
    result = Counter()
    result["starts"] += 1
    ready = row["first_any_ready"] is not None
    high = row["first_high_ready"] is not None
    win = row["status"] == "win"
    high_win = win and row["fan"] >= 2
    result["any_ready"] += ready
    result["high_ready"] += high
    result["ready_then_win"] += ready and win
    result["high_win"] += high_win
    result["high_win_with_prior_high"] += high_win and high
    result["high_win_without_prior_high"] += high_win and not high
    result["win"] += win
    return result


def main() -> None:
    if OUT.exists():
        raise SystemExit("G69 房级描述区间已存在，拒绝覆盖")
    by_room: dict[tuple[str, str, str], Counter] = defaultdict(Counter)
    with gzip.open(SOURCE, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            by_room[row["peer"], row["room"], row["actor"]].update(measures(row))
    rng = np.random.default_rng(SEED)
    summary = {}
    for peer, expected_rooms in (("xuanwu_2346", 15), ("tengshe_0638", 17)):
        rooms = sorted({room for who, room, _ in by_room if who == peer})
        if len(rooms) != expected_rooms:
            raise ValueError("G69 房数不等于同桌强手冻结母体")
        for room in rooms:
            if any(by_room[peer, room, actor]["starts"] != 80 for actor in ("us", "peer")):
                raise ValueError("G69 同房双方不是 80 个完整单局")
        n = len(rooms)
        sampled = rng.integers(0, n, size=(DRAWS, n))
        result = {}
        for metric in METRICS:
            per_room = np.array([
                by_room[peer, room, "peer"][metric] - by_room[peer, room, "us"][metric]
                for room in rooms], dtype=float)
            estimate = float(per_room.sum() / (80 * n))
            replicate = per_room[sampled].sum(axis=1) / (80 * n)
            result[metric] = {"peer_minus_us_per_hand": estimate,
                              "room_bootstrap_95pct": [float(np.quantile(replicate, 0.025)),
                                                       float(np.quantile(replicate, 0.975))],
                              "peer_ahead_rooms": int(np.sum(per_room > 0)),
                              "tied_rooms": int(np.sum(per_room == 0)),
                              "us_ahead_rooms": int(np.sum(per_room < 0))}
        summary[peer] = result
    outcome = {"schema": "g69-room-paired-descriptive-bootstrap/1",
               "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
               "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "seed": SEED, "draws": DRAWS, "metrics": summary,
               "boundary": "事后房级配对描述区间；双方起手牌与真实行动不同，不能消除混杂或作为候选整桌增益置信区间。"}
    OUT.write_text(json.dumps(outcome, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(outcome, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
