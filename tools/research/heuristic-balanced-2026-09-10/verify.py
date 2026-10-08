"""只读复核夜间战役特征；按房间重采样，不改写原报告或在线数据。"""

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

import collections
import json
import random
import sys
from pathlib import Path

source = Path(sys.argv[1])
rows = [json.loads(line) for line in (source / "features-v10.jsonl").open()]
profiles = json.loads((source / "opponents.json").read_text())
pressure = {row["user_id"] for row in profiles["dominators"]}
counts = collections.defaultdict(lambda: [0, 0, 0])
rooms = collections.defaultdict(lambda: [0, 0, 0, 0])
dealer_loss = collections.Counter()
for row in rows:
    own = row["my_seat"]
    dealer = row["dealer"] == own
    bucket = counts["dealer" if dealer else "nondealer"]
    bucket[0] += 1
    bucket[1] += int(row["own_win"])
    bucket[2] += row["own_score"]
    slot = 0 if dealer else 2
    rooms[row["room"]][slot] += 1
    rooms[row["room"]][slot + 1] += int(row["own_win"])
    if dealer and row["own_score"] < 0:
        dealer_loss[row["fan"]] -= row["own_score"]
    for seat in range(4):
        group = "own" if seat == own else "pressure" if row["seat_users"][seat] in pressure else "other"
        whites = row["seat_stats"][str(seat)]["whites_drawn"]
        labels = ["draw_white>=1"] if whites >= 1 else []
        if whites == 1:
            labels.append("draw_white=1")
        for label in labels:
            bucket = counts[group + ":" + label]
            bucket[0] += 1
            bucket[1] += int(row["winner"] == seat and not row["is_draw"])
            bucket[2] += row["scores"][seat]

# 每个数组依次为庄家单局数/胡数、闲家单局数/胡数；房间是抽样单位。
rng = random.Random(20260910)
groups = list(rooms.values())
differences = []
for _ in range(10000):
    sample = [0, 0, 0, 0]
    for _ in groups:
        selected = groups[rng.randrange(len(groups))]
        sample = [a + b for a, b in zip(sample, selected)]
    differences.append(sample[1] / sample[0] - sample[3] / sample[2])
differences.sort()
upgrades = json.loads((source / "upgrade-outcome.json").read_text())["rows"]
upgrade_summary = {}
for dealer in (False, True):
    selected = [row for row in upgrades if row["is_dealer"] == dealer]
    upgrade_summary["dealer" if dealer else "nondealer"] = {
        "hands": len(selected),
        "wins": sum(row["own_win"] for row in selected),
        "immediate_score": sum(row["immediate"] for row in selected),
        "actual_score": sum(row["own_score"] for row in selected),
    }
print(json.dumps({
    "schema_note": "counts 数组依次为座位单局数、胡数、座位净分合计；CI 单位为概率差",
    "rooms": len(rooms), "hands": len(rows), "counts": dict(counts),
    "dealer_minus_nondealer_95ci": [differences[250], differences[9750]],
    "dealer_loss_by_winner_fan": dict(dealer_loss),
    "upgrade_summary": upgrade_summary,
}, ensure_ascii=False, indent=2))
