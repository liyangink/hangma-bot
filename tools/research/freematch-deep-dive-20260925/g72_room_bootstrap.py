#!/usr/bin/env python3
"""G72 探索性房级重采样；仅描述已发生路线差，不估计鸣牌因果效应。"""

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
import hashlib
import json
from pathlib import Path
import random


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g72-win-route-provenance-20260928/result.json')
OUT = SOURCE.with_name("room_bootstrap.json")
SEED = 20260928
DRAWS = 20_000


def percentile(sorted_values: list[float], fraction: float) -> float:
    """最近秩百分位；索引取 ceil(n*p)-1。"""

    from math import ceil

    return sorted_values[max(0, ceil(len(sorted_values) * fraction) - 1)]


def main() -> None:
    if OUT.exists():
        raise SystemExit("G72 房级描述区间已存在，拒绝覆盖")
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    if data["schema"] != "g72-win-route-provenance/1":
        raise ValueError("G72 源结果版本不符")
    room_counts: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    for row in data["rows"]:
        if row["fan"] < 2:
            continue
        source = "claim" if row["origin"] in ("chi", "peng") else "draw"
        room_counts[row["peer"]][row["room"]][(row["actor"], source)] += 1
    out = {}
    for peer, expected_rooms in (("xuanwu_2346", 15), ("tengshe_0638", 17)):
        rooms = sorted(room_counts[peer])
        if len(rooms) != expected_rooms:
            raise ValueError("G72 强手房数不符")
        rng = random.Random(SEED)
        peer_result = {}
        for source in ("claim", "draw"):
            deltas = [room_counts[peer][room][("peer", source)] -
                      room_counts[peer][room][("us", source)] for room in rooms]
            samples = sorted(sum(deltas[rng.randrange(len(rooms))] for _ in rooms)
                             / (len(rooms) * 80) * 100 for _ in range(DRAWS))
            peer_result[source] = {"peer_minus_us_count": sum(deltas),
                                   "percentage_points_per_round": sum(deltas) / (len(rooms) * 80) * 100,
                                   "room_bootstrap_95": [percentile(samples, .025),
                                                          percentile(samples, .975)]}
        out[peer] = peer_result
    result = {"schema": "g72-room-bootstrap/1", "exploratory": True,
              "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "seed": SEED, "draws": DRAWS,
              "unit": "room, with 80 rounds per actor; shared peer room counted within each peer group",
              "results": out}
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
