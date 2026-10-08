#!/usr/bin/env python3
"""G60 自由赛官方结果按房重采样；不将单局当独立样本。"""

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

import hashlib
import json
from pathlib import Path
import random
import statistics


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g60-full-r18v2-free-cohort-20260927/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g60-full-r18v2-free-cohort-20260927/room_cluster_analysis.json')
PEERS = ("xuanwu_2346", "astra_0", "tengshe_0638")
SEED = 20260927
DRAWS = 20000


def interval(values: list[float], rng: random.Random) -> list[float]:
    """房级等权 bootstrap 的描述区间；不修正同桌选择偏差。"""

    n = len(values)
    means = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n
                   for _ in range(DRAWS))
    return [round(means[int(DRAWS * .025)], 4),
            round(means[int(DRAWS * .975)], 4)]


def main() -> None:
    """从逐房官方收支复核总差，报告强手配对方向和不确定性。"""

    if OUT.exists():
        raise SystemExit("G60 房级分析已存在，拒绝覆盖")
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    rows = source["room_rows"]
    rng = random.Random(SEED)
    us_rooms = sorted(key.removesuffix("/us") for key in rows if key.endswith("/us"))
    if len(us_rooms) != source["rooms"]:
        raise ValueError("G60 我方逐房账目不全")
    us_scores = [rows[room + "/us"]["net"] / 10 for room in us_rooms]
    result = {
        "schema": "g60-room-cluster-analysis/1",
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "bootstrap_seed": SEED,
        "bootstrap_draws": DRAWS,
        "all_rooms": {"n": len(us_scores),
                      "us_score_per_table_mean": round(statistics.mean(us_scores), 4),
                      "us_score_per_table_95pct": interval(us_scores, rng)},
        "peers": {},
        "boundary": "同桌积分差是观察性描述；房级 bootstrap 只反映已归档房的抽样波动，不消除配对牌山、对手池或选房偏差。",
    }
    for peer in PEERS:
        peer_rooms = sorted(key.removesuffix("/" + peer) for key in rows
                            if key.endswith("/" + peer))
        if not peer_rooms:
            continue
        components = ("net", "win_points", "nonwin_points", "wins",
                      "plain_wins", "fan2plus_wins", "baotou_wins")
        gaps = {field: [rows[room + "/" + peer].get(field, 0) -
                        rows[room + "/us"].get(field, 0)
                        for room in peer_rooms] for field in components}
        score_table = [value / 10 for value in gaps["net"]]
        result["peers"][peer] = {
            "rooms": len(peer_rooms),
            "tables": len(peer_rooms) * 10,
            "peer_minus_us_score_total": sum(gaps["net"]),
            "peer_minus_us_per_table_mean": round(statistics.mean(score_table), 4),
            "peer_minus_us_per_table_95pct": interval(score_table, rng),
            "peer_ahead_rooms": sum(value > 0 for value in gaps["net"]),
            "us_ahead_rooms": sum(value < 0 for value in gaps["net"]),
            "source_gap_totals": {field: sum(values) for field, values in gaps.items()},
            "room_gaps": {room: gaps["net"][index] for index, room
                          in enumerate(peer_rooms)},
        }
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"all_rooms": result["all_rooms"],
                      "peers": {k: {a: b for a, b in v.items() if a != "room_gaps"}
                                for k, v in result["peers"].items()}},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
