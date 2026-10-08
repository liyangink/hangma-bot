#!/usr/bin/env python3
"""G64 同桌房聚类重采样：只量化已发生胡牌时序的房间波动。"""

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
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g64-strong-win-timing-20260928/result.json')
OUT = SOURCE.with_name("room_bootstrap.json")
METRICS = ("early_wins_le6", "late_wins_ge7", "late_plain", "late_fan2plus",
           "dealer_starts", "dealer_wins")


def summary(actor: dict) -> Counter:
    """本人实际达成的早/晚胡，庄位另列观察性计数。"""

    result = Counter()
    result["dealer_starts"] = int(actor["dealer"])
    if actor["status"] == "win":
        turn = actor["win_turn"]
        result["early_wins_le6" if turn <= 6 else "late_wins_ge7"] += 1
        if turn >= 7:
            result["late_plain" if actor["fan"] == 1 else "late_fan2plus"] += 1
        result["dealer_wins"] += int(actor["dealer"])
    return result


def percentile(values: list[float], q: float) -> float:
    """固定有序样本的线性分位数；单位为每张完整桌的次数差。"""

    values.sort()
    position = (len(values) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def main() -> None:
    """房级成对重采样，不把同房 80 局误当独立实验。"""

    if OUT.exists():
        raise SystemExit("G64 聚类结果已存在，拒绝覆盖")
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    if source["schema"] != "g64-strong-win-timing-result/1":
        raise ValueError("G64 输入结构漂移")
    rooms: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    for row in source["rows"]:
        peer, room = row["peer"], row["room"]
        us, opponent = summary(row["actors"]["us"]), summary(row["actors"][peer])
        for metric in METRICS:
            rooms[peer][room][metric] += opponent[metric] - us[metric]
    result = {"schema": "g64-strong-win-timing-room-bootstrap/1",
              "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "draws": 20_000, "seed": 20260928,
              "unit": "强手减我方，按同桌房重采样，每完整桌实际次数差",
              "peers": {}}
    for peer, by_room in sorted(rooms.items()):
        expected = 15 if peer == "xuanwu_2346" else 17
        if len(by_room) != expected:
            raise ValueError("G64 聚类房数漂移")
        observations = list(by_room.values())
        rng = random.Random(20260928 + (1 if peer == "xuanwu_2346" else 2))
        draws = {metric: [] for metric in METRICS}
        for _ in range(20_000):
            sample = [observations[rng.randrange(expected)] for _ in range(expected)]
            for metric in METRICS:
                draws[metric].append(sum(room[metric] for room in sample) / (expected * 10))
        result["peers"][peer] = {metric: {
            "point": sum(room[metric] for room in observations) / (expected * 10),
            "ci95": [percentile(draws[metric], 0.025), percentile(draws[metric], 0.975)],
        } for metric in METRICS}
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(result["peers"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
