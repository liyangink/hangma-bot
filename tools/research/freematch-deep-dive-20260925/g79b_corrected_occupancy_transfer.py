#!/usr/bin/env python3
"""G79B：修正三家公开副露特征后，在预冻结七房一次性评分。"""

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
import copy
import hashlib
import json
from pathlib import Path

import numpy as np

import g79_tile_occupancy_transfer as core


HERE = Path(__file__).resolve().parent
MANIFEST = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g79b-corrected-occupancy-transfer-20260928/manifest.json')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G79B-CORRECTED-OCCUPANCY-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g79b-corrected-occupancy-transfer-20260928/result.json')


def _negative_control(snap: dict, seat: int) -> None:
    """变动他家暗手牌码、保持张数，线上特征须逐位相同。"""

    X, n, H, wall = core._features(snap, seat)
    changed = copy.deepcopy(snap)
    for other in range(4):
        if other == seat:
            continue
        amount = sum(changed["hands"][other].values())
        changed["hands"][other].clear()
        changed["hands"][other]["赛后负控伪牌"] = amount
    a, b, h, w = core._features(changed, seat)
    if not (np.array_equal(X, a) and np.array_equal(n, b) and (H, wall) == (h, w)):
        raise ValueError("他家暗手牌码进入了玩家可见特征")


def main() -> None:
    """90 房重训预登记模型、七个完整新房评分，不从 G79A 迁移系数。"""

    if OUT.exists():
        raise SystemExit("G79B 结果已存在，拒绝覆盖")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    frozen = {room: set(games) for room, games in manifest["room_games"].items()}
    g60 = json.loads(core.G60.read_text(encoding="utf-8"))
    old = {row["room_id"] for row in json.loads(core.G9.read_text(encoding="utf-8"))["rooms"]}
    dev = set(g60["included"]) & old
    if len(dev) != 90 or len(frozen) != 7 or sum(map(len, frozen.values())) != 70:
        raise ValueError("预登记 G79B 房数/桌数漂移")
    if set(frozen) & set(g60["included"]):
        raise ValueError("外部房与 G60 训练/前一评分房重合")
    expected = {game for room in dev for game in g60["included"][room]}
    expected |= {game for games in frozen.values() for game in games}

    windows: dict[str, list[core.Window]] = {"dev": [], "external": []}
    found = set()
    round_counts = Counter()
    doc_digests = []
    negative_control_done = False
    for _, room, _, game_id, doc in core.load_rooms():
        if game_id not in expected:
            continue
        if game_id in found:
            continue
        if room in frozen and game_id not in frozen[room]:
            raise ValueError("新房官方桌不在预冻结清单")
        if room in dev and game_id not in g60["included"][room]:
            raise ValueError("训练房官方桌不在 G60 清单")
        found.add(game_id)
        if room in frozen and (doc.get("status") != "finished" or len(doc.get("rounds") or []) != 8):
            raise ValueError("新房冻结官方桌不是 finished/八局")
        doc_digests.append((game_id, hashlib.sha256(json.dumps(
            doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()).hexdigest()))
        seats = [seat.get("user_id") for seat in doc.get("seats") or []]
        if len(seats) != 4 or seats.count(core.g59.US) != 1:
            raise ValueError("官方桌缺我方唯一座位")
        actor = seats.index(core.g59.US)
        metadata = core.c31.round_metadata(doc)
        group = "external" if room in frozen else "dev"
        for round_no, events, start_hands in core.anatomy.round_blocks(doc):
            if start_hands is None or len(start_hands) != 4:
                raise ValueError("官方单局缺完整起手")
            dealer = (metadata.get(round_no) or {}).get("dealer")
            if dealer is None:
                raise ValueError("官方单局庄位未知")
            snapshots = core.c31.reconstruct(events, start_hands, [0, 0, 0, 0], dealer)
            own = [snap for _, snap in sorted(snapshots.items()) if snap["discarder"] == actor]
            for position in core.POSITIONS:
                if len(own) < position:
                    continue
                snap = own[position - 1]
                if group == "dev" and not negative_control_done:
                    _negative_control(snap, actor)
                    negative_control_done = True
                windows[group].append(core._window(snap, room, position))
            round_counts[group] += 1
        if len(found) % 100 == 0:
            print(json.dumps({"games": len(found), "rounds": dict(round_counts)},
                             ensure_ascii=False), flush=True)
    if found != expected or len(found) != 970 or round_counts != {"dev": 7200, "external": 560}:
        raise ValueError("G79B 训练/新房官方桌或单局覆盖漂移")
    if not negative_control_done:
        raise ValueError("特征信息负控未执行")

    beta, fit = core._fit(windows["dev"])
    by_room: dict[str, dict] = defaultdict(lambda: {"windows": 0, "baseline_sse": 0.0,
                                                    "model_sse": 0.0, "sse_difference": 0.0})
    by_position: dict[str, dict] = defaultdict(lambda: {"windows": 0, "baseline_sse": 0.0,
                                                        "model_sse": 0.0})
    for window in windows["external"]:
        base, model = core._predict(window, beta)
        truth = window.hidden.astype(float)
        base_error = float(np.sum(np.square(truth - base)))
        model_error = float(np.sum(np.square(truth - model)))
        room = by_room[window.room]
        room["windows"] += 1
        room["baseline_sse"] += base_error
        room["model_sse"] += model_error
        room["sse_difference"] += model_error - base_error
        position = by_position[str(window.position)]
        position["windows"] += 1
        position["baseline_sse"] += base_error
        position["model_sse"] += model_error
    if set(by_room) != set(frozen):
        raise ValueError("G79B 七外部房未全覆盖")
    overall = {key: sum(row[key] for row in by_room.values())
               for key in ("windows", "baseline_sse", "model_sse", "sse_difference")}
    overall["mean_sse_difference_per_window"] = overall["sse_difference"] / overall["windows"]
    interval = core._bootstrap(by_room)
    result = {
        "schema": "g79b-corrected-occupancy-transfer/1", "preregistered": True,
        "negative_control_passed": negative_control_done,
        "source_sha256": {"manifest": core.sha(MANIFEST), "prereg": core.sha(PREREG),
                          "corrected_core": core.sha(Path(core.__file__)),
                          "script": core.sha(Path(__file__)),
                          "official_docs_fingerprint": hashlib.sha256(json.dumps(
                              sorted(doc_digests), separators=(",", ":")
                          ).encode()).hexdigest()},
        "coverage": {"dev_rooms": len(dev), "external_rooms": len(frozen),
                     "dev_rounds": round_counts["dev"], "external_rounds": round_counts["external"],
                     "dev_windows": len(windows["dev"]), "external_windows": len(windows["external"])},
        "model": {"features": core.FEATURES, "ridge": core.RIDGE,
                  "coefficients": dict(zip(core.FEATURES, map(float, beta))), "fit": fit},
        "external": {"overall": overall, "by_room": dict(sorted(by_room.items())),
                     "by_position": dict(sorted(by_position.items())),
                     "room_bootstrap_95": interval,
                     "rooms_model_better": sum(row["sse_difference"] < 0 for row in by_room.values()),
                     "rooms_model_worse": sum(row["sse_difference"] > 0 for row in by_room.values()),
                     "pass": overall["mean_sse_difference_per_window"] < 0 and interval[1] < 0},
        "boundary": "首版 G79A 不合预登记；七房仅验证修正的牌码占用预测，非动作收益。",
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"coverage": result["coverage"], "model": result["model"],
                      "external": {key: value for key, value in result["external"].items()
                                   if key != "by_room"}}, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
