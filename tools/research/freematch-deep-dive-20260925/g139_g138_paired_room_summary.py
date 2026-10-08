#!/usr/bin/env python3
"""G139：G138 行动前爆头机会的同房聚类，并与 G136 已发生胡型对账。"""

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
import random

import g136_current_free_win_type_audit as free
import g138_official_plain_baotou_opportunity as opportunity


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g139-plain-baotou-opportunity-room-summary-20260928/result.json')
PEER_NAMES = {"xuanwu_2346": "玄武-2346", "tengshe_0638": "腾蛇-0638"}
FIELDS = ("offered_hands_per_100", "kept_hands_per_100",
          "same_meld_white_first_offer_per_100",
          "official_plain_baotou_wins_per_table", "official_plain_wins_per_table")


def percentile_ci(values: list[float], rng: random.Random) -> dict[str, float]:
    """固定种子按房重采样；区间仅描述观察性同房波动。"""
    n = len(values)
    draws = sorted(sum(rng.choices(values, k=n)) / n for _ in range(20000))
    return {"mean": sum(values) / n, "bootstrap_95_low": draws[500],
            "bootstrap_95_high": draws[19500]}


def main() -> None:
    """强手－我方的机会进入差只在相同已核房内对比。"""
    if OUT.exists():
        raise FileExistsError("G139 已有证据，拒绝覆盖")
    g138 = json.loads(opportunity.OUT.read_text(encoding="utf-8"))
    g136 = json.loads(free.OUT.read_text(encoding="utf-8"))
    if (g138["strong_room_units"] != 32 or g138["actor_hands"] != 5120
            or g138["normal_draw_discard_windows"] != 36080
            or g136["complete_rooms"] != 220):
        raise ValueError("G139 行动前或官方结算母体不符")
    rows = []
    generic_high = Counter()
    generic_windows = Counter()
    with gzip.open(opportunity.g69.ROWS, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            name = row["peer"] + "/" + row["actor"]
            generic_windows[name] += 1
            actual = row["actual"]
            generic_high[name] += actual is not None and actual["high_capacity"] > 0
    first_by_unit: dict[tuple[str, str, str], int] = {}
    for record in g138["first_plain_baotou_rows"]:
        prior = record["previous_normal_draw"]
        if (prior is not None
                and record["first_meld_count"] == prior["meld_count"]
                and record["first_white_before"] == prior["white_before"]):
            key = record["peer"], record["room"], record["actor"]
            first_by_unit[key] = first_by_unit.get(key, 0) + 1
    for unit in sorted({key.rsplit("/", 1)[0]
                        for key in g138["room_hand_groups"]}):
        peer, room = unit.split("/", 1)
        if peer not in PEER_NAMES:
            raise ValueError("G139 未知强手单元")
        actor_peer = g138["room_hand_groups"][unit + "/peer"]
        actor_us = g138["room_hand_groups"][unit + "/us"]
        official_peer = g136["room_groups"][room + "/" + PEER_NAMES[peer]]
        official_us = g136["room_groups"][room + "/us_vs_" + PEER_NAMES[peer]]
        if not (actor_peer["hands"] == actor_us["hands"]
                == official_peer["hands"] == official_us["hands"] == 80):
            raise ValueError("G139 同房八十单局口径不符")
        prefix = "plain_baotou/"
        offered = actor_peer[prefix + "hands_offered"] - actor_us[prefix + "hands_offered"]
        kept = actor_peer[prefix + "hands_kept"] - actor_us[prefix + "hands_kept"]
        if offered != kept:
            raise ValueError("G139 普通型爆头机会与实际保留不相等")
        rows.append({"peer": peer, "room": room,
                     "peer_minus_us": {
                         "offered_hands_per_100": offered * 100 / 80,
                         "kept_hands_per_100": kept * 100 / 80,
                         "same_meld_white_first_offer_per_100":
                             (first_by_unit.get((peer, room, "peer"), 0)
                              - first_by_unit.get((peer, room, "us"), 0)) * 100 / 80,
                         "official_plain_baotou_wins_per_table":
                             (official_peer.get("wins_plain_baotou", 0)
                              - official_us.get("wins_plain_baotou", 0)) / 10,
                         "official_plain_wins_per_table":
                             (official_peer.get("wins_plain", 0)
                              - official_us.get("wins_plain", 0)) / 10,
                     }})
    rng = random.Random(20260928)
    by_peer = {}
    for peer in PEER_NAMES:
        selected = [row for row in rows if row["peer"] == peer]
        expected = 15 if peer == "xuanwu_2346" else 17
        if len(selected) != expected:
            raise ValueError("G139 强手房数不符")
        by_peer[peer] = {
            "rooms": len(selected), "tables": len(selected) * 10,
            "generic_fan2plus_actual_windows": {
                actor: generic_high[peer + "/" + actor]
                for actor in ("peer", "us")},
            "same_meld_white_first_offer_counts": {
                actor: sum(count for (p, _room, a), count in first_by_unit.items()
                           if p == peer and a == actor)
                for actor in ("peer", "us")},
            "paired_room_bootstrap": {
                field: percentile_ci([row["peer_minus_us"][field]
                                      for row in selected], rng)
                for field in FIELDS},
            "action_windows": {
                actor: {
                    axis: {
                        "windows": g138["window_groups"][peer + "/" + actor + "/" + axis]["windows"],
                        "plain_baotou_opportunity":
                            g138["window_groups"][peer + "/" + actor + "/" + axis].get(
                                "plain_baotou/opportunity_yes", 0),
                    }
                    for axis in ("meld_no", "meld_yes", "white_1", "white_2plus",
                                 "turn_le6", "turn_ge7")}
                for actor in ("peer", "us")},
        }
        for actor in ("peer", "us"):
            name = peer + "/" + actor
            if (generic_windows[name] != g138["window_groups"][name + "/all"]["windows"]
                    or generic_high[name] <
                    g138["window_groups"][name + "/all"]["plain_baotou/actual_kept"]):
                raise ValueError("G139 普通型爆头不是旧二番以上路线的子集")
    output = {"schema": "g139-plain-baotou-opportunity-room-summary/1",
              "input_sha256": {"g138": hashlib.sha256(opportunity.OUT.read_bytes()).hexdigest(),
                               "g136": hashlib.sha256(free.OUT.read_bytes()).hexdigest(),
                               "g69_windows": hashlib.sha256(opportunity.g69.ROWS.read_bytes()).hexdigest(),
                               "script": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
              "bootstrap_seed": 20260928, "bootstrap_samples": 20000,
              "paired_room_rows": rows, "by_peer": by_peer,
              "boundary": "机会是本座行动前规则可见的条件下一摸支持；"
                          "同房差仍受起手、先胡截尾、已做动作影响，非候选因果效果。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, ensure_ascii=False, sort_keys=True,
                              indent=2) + "\n", encoding="utf-8")
    print(json.dumps({peer: value["paired_room_bootstrap"]
                      for peer, value in by_peer.items()},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
