#!/usr/bin/env python3
"""G140：结果盲选出强手与冻结父代不同弃牌的普通型爆头前驱面板。"""

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

from collections import Counter
import hashlib
import json
from pathlib import Path

import c31_action_layer_gap as c31
import g61_strong_draw_batch as g61
import g138_official_plain_baotou_opportunity as g138
from hangma_bot.kernel.actions import Hu
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G140-PLAIN-BAOTOU-PRECURSOR-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g140-plain-baotou-precursor-20260928/selection.json')


def classify(row: dict, *, peer: str, room: str) -> dict | None:
    """仅以行动前可见状态和强手／父代动作筛选，不读取赛后结果。"""
    actual, parent = row["actual_action"], row["parent_top_action"]
    if (actual == parent or not actual.startswith("discard:")
            or not parent.startswith("discard:")
            or actual == "discard:白" or parent == "discard:白"
            or row["remaining_tile_count"] <= 20):
        return None
    obs = observation_from_json(row["observation"])
    white = sum(tile.code == "白" for tile in obs.my_hand)
    if white < 1:
        return None
    rules = c31.RULES.analyze(obs, value_limits=c31.VALUE_LIMITS)
    legal = {item.action_key: item for item in rules.legal_candidates}
    if (actual not in legal or parent not in legal or
            len(legal) != len(rules.legal_candidates) or
            any(isinstance(item.action, Hu) for item in rules.legal_candidates)):
        return None
    a, p = legal[actual], legal[parent]
    if a.facts is None or p.facts is None:
        return None
    sa, sp = a.facts.standard_shanten_after, p.facts.standard_shanten_after
    if type(sa) is not int or sa not in (0, 1) or sp != sa:
        return None
    for candidate in (a, p):
        mass, complete = g138.action_opportunity(candidate)
        if not complete or mass["plain_baotou"] > 0:
            return None
    marker = (peer, room, row["game_id"], row["round_no"], row["draw_seq"])
    if (obs.game_id, obs.round_no, obs.snapshot_seq) != marker[2:]:
        raise ValueError("G140 重建窗口身份不符")
    return {"peer": peer, "room": room, "game_id": row["game_id"],
            "round_no": row["round_no"], "draw_seq": row["draw_seq"],
            "actual_action": actual, "parent_action": parent,
            "white_before": white, "white_stratum": "1" if white == 1 else "2plus",
            "own_meld_count": len(obs.melds[obs.seat]),
            "standard_shanten_after": sa,
            "wall_remaining": obs.remaining_tile_count,
            "selection_sha256": hashlib.sha256(
                "|".join(map(str, marker)).encode("utf-8")).hexdigest()}


def main() -> None:
    """每强手×房×白板层固定一个最小哈希行动窗。"""
    if OUT.exists():
        raise FileExistsError("G140 已有选样，拒绝覆盖")
    source = json.loads((g61.OUT / "result.json").read_text(encoding="utf-8"))
    if source["outcome_labels_opened"] is not False or len(source["units"]) != 32:
        raise ValueError("G140 G61 行动前来源不符")
    chosen = {}
    counts = Counter()
    source_sha = {}
    for unit in sorted(source["units"]):
        peer, room = unit.split("/", 1)
        path = g61.room_dir((peer, room)) / "windows.json"
        if g61.sha(path) != source["units"][unit]["windows_sha256"]:
            raise ValueError("G140 原房逐窗摘要漂移")
        source_sha[unit] = g61.sha(path)
        for row in json.loads(path.read_text(encoding="utf-8"))["windows"]:
            counts["raw_windows"] += 1
            record = classify(row, peer=peer, room=room)
            if record is None:
                continue
            stratum = unit + "/white_" + record["white_stratum"]
            counts["eligible"] += 1
            counts["eligible/white_" + record["white_stratum"]] += 1
            previous = chosen.get(stratum)
            if previous is None or record["selection_sha256"] < previous["selection_sha256"]:
                chosen[stratum] = record
    if counts["raw_windows"] != 17938:
        raise ValueError("G140 G61 32 单元强手窗口总数漂移")
    result = {"schema": "g140-plain-baotou-precursor-selection/1",
              "input_sha256": {"g61_result": g61.sha(g61.OUT / "result.json"),
                                "prereg": g61.sha(PREREG),
                                "script": g61.sha(Path(__file__)),
                                "g61_windows_by_unit": source_sha},
              "counts": dict(sorted(counts.items())),
              "selected": [chosen[key] for key in sorted(chosen)],
              "selected_count": len(chosen),
              "missing_strata": sorted(
                  unit + "/white_" + white
                  for unit in source["units"] for white in ("1", "2plus")
                  if unit + "/white_" + white not in chosen),
              "boundary": "已看强手房的行动前研发面板，非结果或收益确认。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True,
                              indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"raw_windows": counts["raw_windows"],
                      "eligible": counts["eligible"],
                      "selected_count": len(chosen),
                      "missing_strata": len(result["missing_strata"])},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
