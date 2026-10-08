#!/usr/bin/env python3
"""G77：在 G76 发现集的独有强手鸣牌上，核对动作前可见的一摸条件胡路线。"""

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
import gzip
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, HERE.parents[0] / "baotou-anatomy-20260925")))

import anatomy_lib as anatomy
import c31_action_layer_gap as c31
from extract_room_scores import load_rooms


SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g76-confirmed-response-atlas-20260928/rows.jsonl.gz')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g77-claim-route-facts-20260928/result.json')


def route_summary(action: dict) -> dict:
    """直接读取生产规则的条件胡路线；不把条件番数当成无条件收益。"""
    routes = action.get("routes") or ()
    fans = []
    for route in routes:
        settlement = route.get("conditional_settlement") or {}
        fan = settlement.get("fan")
        if type(fan) is int:
            fans.append(fan)
    return {"route_count": len(routes), "max_fan": max(fans, default=None),
            "high_fan_routes": sum(fan >= 2 for fan in fans),
            "best_followup_discard": action.get("best_followup_discard")}


def standard_summary(action: dict) -> dict:
    """普通型单独向听及公开有效张；与综合向听和七对分开记账。"""
    shanten = action.get("standard_shanten_after")
    useful = action.get("standard_useful_tiles")
    if type(shanten) is not int or useful is None:
        return {"shanten": None, "width": None}
    width = 0
    for tile in useful:
        remaining = tile.get("remaining_estimate")
        if type(remaining) is not int or remaining < 0:
            return {"shanten": shanten, "width": None}
        width += remaining
    return {"shanten": shanten, "width": width}


def main() -> None:
    if OUT.exists():
        raise SystemExit("G77 证据已存在，拒绝覆盖")
    source = [json.loads(line) for line in gzip.open(SOURCE, "rt", encoding="utf-8")]
    targets = {(row["game_id"], row["round_no"], row["discard_seq"], row["seat"],
                row["phase"]): row for row in source
               if row["actor"] == "peer" and row["actual"] == "claim" and
                  row["parent_key"] == "pass" and row["r6_key"] == "pass"}
    if len(targets) != 88:
        raise ValueError("G76 独有强手鸣牌数漂移")
    games = {key[0] for key in targets}
    parent = c31.load_parent()
    found = set()
    rows = []
    for _, _room, _, game_id, doc in load_rooms():
        if game_id not in games:
            continue
        scores = [0, 0, 0, 0]
        metadata = c31.round_metadata(doc)
        for round_no, events, start_hands in anatomy.round_blocks(doc):
            if any(key[0] == game_id and key[1] == round_no for key in targets):
                dealer = metadata[round_no]["dealer"]
                snaps = c31.reconstruct(events, start_hands, scores, dealer)
                for key, target in targets.items():
                    if key[0] != game_id or key[1] != round_no:
                        continue
                    snap = snaps[key[2]]
                    window, _phases, _audit = c31.evaluate_window(
                        snap, key[3], [key[4]], game_id, round_no, parent)
                    if window is None or window["degraded"] or window["margin"] != target["parent_margin"]:
                        raise ValueError("G76 目标窗口规则事实或父代分差漂移")
                    claims = {item["action_key"]: item for item in window["view"]["actions"]}
                    accepted = claims.get(target["accepted_key"])
                    if accepted is None:
                        raise ValueError("G76 已接受鸣牌不在合法动作表")
                    pas = route_summary(window["pass"])
                    claim = route_summary(accepted)
                    pass_standard = standard_summary(window["pass"])
                    claim_standard = standard_summary(accepted)
                    rows.append({"peer": target["peer"], "room": target["room"],
                                 "game_id": game_id, "round_no": round_no,
                                 "discard_seq": key[2], "seat": key[3], "phase": key[4],
                                 "accepted_key": target["accepted_key"],
                                 "white_count": target["white_count"],
                                 "parent_margin": target["parent_margin"],
                                 "pass_shanten": target["pass_shanten"],
                                 "claim_shanten": target["claim_shanten"],
                                 "pass_width": target["pass_width"],
                                 "claim_width": target["claim_width"],
                                 "pass_route": pas, "claim_route": claim,
                                 "pass_standard": pass_standard,
                                 "claim_standard": claim_standard})
                    found.add(key)
            ended = next(event for event in events if event.get("type") == "round_ended")
            delta = ended["data"]["scores"]
            scores = [a + b for a, b in zip(scores, delta)]
    if found != set(targets):
        raise ValueError("G76 独有强手鸣牌窗口未全部复现")
    counts = {}
    for peer in ("xuanwu_2346", "tengshe_0638"):
        selected = [row for row in rows if row["peer"] == peer]
        c = Counter()
        for row in selected:
            claim_fan, pass_fan = row["claim_route"]["max_fan"], row["pass_route"]["max_fan"]
            c["windows"] += 1
            c["pass_high"] += pass_fan is not None and pass_fan >= 2
            c["claim_high"] += claim_fan is not None and claim_fan >= 2
            c["claim_high_pass_not"] += (claim_fan is not None and claim_fan >= 2 and
                                          (pass_fan is None or pass_fan < 2))
            c["claim_no_route"] += claim_fan is None
            c["pass_no_route"] += pass_fan is None
            c["combined_same_or_better_width"] += (row["pass_shanten"] == row["claim_shanten"] and
                                                    row["claim_width"] >= row["pass_width"])
            left, right = row["pass_standard"], row["claim_standard"]
            c["ordinary_standard_protected"] += (left["shanten"] is not None and
                                                 right["shanten"] is not None and
                                                 right["shanten"] <= left["shanten"] and
                                                 left["width"] is not None and
                                                 right["width"] is not None and
                                                 right["width"] >= left["width"])
        counts[peer] = dict(c)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    result = {"schema": "g77-claim-route-facts/1", "exploratory": True,
              "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "counts": counts,
              "rows": sorted(rows, key=lambda r: (r["peer"], r["room"], r["game_id"],
                                                r["round_no"], r["discard_seq"])),
              "boundary": "条件胡番数是规则见证而非可兑现概率；动作来自强手已看牌谱，不能当收益标签。"}
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(counts, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
