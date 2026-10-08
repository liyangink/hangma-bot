#!/usr/bin/env python3
"""G137：对 G136 官方同房强手胡型收入差按房聚类描述波动。"""

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

import g136_current_free_win_type_audit as free


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g137-current-free-room-cluster-20260928/result.json')
FIELDS = ("net", "win_income", "nonwin_income", "income_plain",
          "income_plain_baotou", "income_seven_pairs_baotou",
          "wins_plain", "wins_plain_baotou", "wins_seven_pairs_baotou")


def interval(values: list[float], rng: random.Random) -> dict[str, float]:
    """固定种子房级自助法区间；仅描述同桌轨迹，不代表干预效果。"""
    n = len(values)
    means = sorted(sum(rng.choices(values, k=n)) / n for _ in range(20000))
    return {"mean": sum(values) / n, "bootstrap_95_low": means[500],
            "bootstrap_95_high": means[19500]}


def main() -> None:
    """每个强手用同房十桌差，避免把 80 个单局伪作独立。"""
    if OUT.exists():
        raise FileExistsError("G137 已有证据，拒绝覆盖")
    source = json.loads(free.OUT.read_text(encoding="utf-8"))
    cohort = json.loads(free.SOURCE.read_text(encoding="utf-8"))
    if (source["complete_rooms"] != 220 or source["complete_tables"] != 2200
            or source["complete_hands"] != 17600):
        raise ValueError("G137 G136 母体不符")
    rows = []
    groups = source["room_groups"]
    for name in free.PEERS:
        for room, entry in sorted(cohort["included"].items()):
            if name not in entry["peer"]:
                continue
            ours = groups[room + "/us_vs_" + name]
            theirs = groups[room + "/" + name]
            if not (ours["hands"] == theirs["hands"] == 80):
                raise ValueError("G137 强手同房单局数不符")
            delta = {field: (theirs.get(field, 0) - ours.get(field, 0)) / 10
                     for field in FIELDS}
            if (abs(delta["win_income"] + delta["nonwin_income"]
                    - delta["net"]) > 1e-9):
                raise ValueError("G137 房级收支不守恒")
            rows.append({"peer": name, "room": room,
                         "peer_minus_us_per_table": delta})
    rng = random.Random(20260928)
    by_peer = {}
    for name, frozen in cohort["by_peer"].items():
        selected = [row for row in rows if row["peer"] == name]
        if len(selected) != frozen["rooms"]:
            raise ValueError("G137 同房房数不符")
        stats = {field: interval([r["peer_minus_us_per_table"][field]
                                  for r in selected], rng)
                 for field in FIELDS}
        if abs(stats["net"]["mean"] - frozen["peer_minus_our_per_table"]) > 1e-9:
            raise ValueError("G137 同房净分与 G122 不符")
        by_peer[name] = {"rooms": len(selected), "tables": len(selected) * 10,
                         "paired_room_bootstrap": stats}
    output = {"schema": "g137-current-free-room-cluster/1",
              "input_sha256": {"g136": hashlib.sha256(free.OUT.read_bytes()).hexdigest(),
                               "g122": hashlib.sha256(free.SOURCE.read_bytes()).hexdigest(),
                               "script": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
              "bootstrap_seed": 20260928, "bootstrap_samples": 20000,
              "paired_room_rows": rows, "by_peer": by_peer,
              "boundary": "同房观察差的房级波动；配桌和策略非随机，区间不是策略因果效应。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, ensure_ascii=False, sort_keys=True,
                              indent=2) + "\n", encoding="utf-8")
    print(json.dumps(by_peer, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
