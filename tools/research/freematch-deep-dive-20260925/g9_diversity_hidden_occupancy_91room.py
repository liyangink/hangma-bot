#!/usr/bin/env python3
"""按预登记在冻结 91 房复核宽进张对真实牌墙容量的隐藏占用增量。"""

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

import numpy as np

import c31_action_layer_gap as c31
import diversity_hidden_occupancy as prior
import g8_public_response_training_rows as source


HERE = Path(__file__).resolve().parent
FROZEN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-two-white-next-draw-20260927/frozen_rooms.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g9-diversity-hidden-occupancy-91room-20260927/result.json')


def _estimate(rows: list[dict], field: str, *, seed: int) -> dict:
    """先按房分组，再重抽房；报告窗口加权均值与房间独立区间。"""
    by_room = defaultdict(list)
    for row in rows:
        by_room[row["room_id"]].append(row[field])
    rooms = sorted(by_room)
    if not rooms:
        return {"windows": 0, "rooms": 0, "mean": None, "room_bootstrap_95": None}
    sums = np.asarray([sum(by_room[room]) for room in rooms], dtype=float)
    counts = np.asarray([len(by_room[room]) for room in rooms], dtype=float)
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(rooms), size=(20000, len(rooms)))
    samples = sums[indices].sum(axis=1) / counts[indices].sum(axis=1)
    return {"windows": len(rows), "rooms": len(rooms), "mean": float(sums.sum() / counts.sum()),
            "room_bootstrap_95": [float(np.quantile(samples, 0.025)),
                                  float(np.quantile(samples, 0.975))]}


def _room_snapshots(documents: dict[str, dict]) -> dict[tuple, dict]:
    """官方赛后暗手仅作窗口标签，快照只沿当前序号以前事件重建。"""
    snapshots = {}
    for game_id, doc in documents.items():
        metadata = c31.round_metadata(doc)
        for round_no, events, start_hands in prior.anatomy.round_blocks(doc):
            if not start_hands:
                continue
            dealer = (metadata.get(round_no) or {}).get("dealer")
            if dealer is None:
                continue
            for seq, snap in c31.reconstruct(events, start_hands, [0, 0, 0, 0], dealer).items():
                key = (game_id, round_no, seq)
                if key in snapshots:
                    raise ValueError("官方同局弃牌序号重复")
                snapshots[key] = snap
    return snapshots


def main() -> None:
    """只用公开事实挑动作，暗手只计算预登记的墙容量标签。"""
    if OUT.exists():
        raise SystemExit("G9 91 房隐藏占用结果已存在，拒绝覆盖")
    frozen_bytes = FROZEN.read_bytes()
    frozen = json.loads(frozen_bytes)
    selected = {row["room_id"] for row in frozen["rooms"]}
    docs = defaultdict(dict)
    fingerprints = []
    for _mtime, room, _tag, game_id, doc in source.load_rooms():
        if room not in selected:
            continue
        docs[room][game_id] = doc
        fingerprints.append((game_id, hashlib.sha256(
            json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()))
    rows = []
    by_room = {}
    totals = Counter()
    room_order = {row["room_id"]: index for index, row in enumerate(frozen["rooms"])}
    for room in frozen["rooms"]:
        room_id = room["room_id"]
        audit = source.ROOT / room["audit_dir"]
        decision_file = audit / "participants" / source.ACTOR / "decisions.jsonl"
        if decision_file.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结房动作审计漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("冻结父代源码身份漂移")
        accepted = source._accepted(decision_file)
        snapshots = _room_snapshots(docs[room_id])
        counts = Counter()
        seen = set()
        for context, request, plan in source.screen._iter_decisions(audit):
            key = (context["game_id"], context["round_no"], context["trigger_seq"])
            phase = (request.get("window_key") or {}).get("phase")
            if (*key, phase) in seen:
                raise ValueError("同一动作窗口重复")
            seen.add((*key, phase))
            pair = prior._alternatives(request, plan)
            if pair is None:
                continue
            counts["public_candidate_pair"] += 1
            chosen, alternate, a_useful, b_useful, gap, width_gain, route_safe = pair
            if accepted.get(context["decision_id"]) != chosen:
                counts["parent_plan_not_accepted"] += 1
                continue
            snap = snapshots.get((key[0], key[1], key[2] + 1))
            if snap is None:
                counts["official_snapshot_missing"] += 1
                continue
            observation = request["observation"]
            seat = observation["seat"]
            if snap["discarder"] != seat or snap["tile"] != chosen[8:]:
                counts["official_discard_mismatch"] += 1
                continue
            hand = list(observation["my_hand"])
            drawn = observation.get("drawn_tile")
            if drawn is not None and len(hand) % 3 == 1:
                hand.append(drawn)
            expected = Counter(hand)
            expected[chosen[8:]] -= 1
            expected += Counter()
            if expected != Counter(snap["hands"][seat]):
                counts["own_hand_mismatch"] += 1
                continue
            others = Counter()
            for other_seat, hand in enumerate(snap["hands"]):
                if other_seat != seat:
                    others.update(hand)
            a_counts = [amount - others[code] for code, amount in a_useful.items()]
            b_counts = [amount - others[code] for code, amount in b_useful.items()]
            if any(value < 0 for value in a_counts + b_counts):
                counts["negative_wall_capacity"] += 1
                continue
            wall_remaining = observation.get("remaining_tile_count")
            if type(wall_remaining) is not int or wall_remaining < 20:
                counts["invalid_wall_count"] += 1
                continue
            unknown = wall_remaining + sum(others.values())
            public_by_code = dict(a_useful)
            if any(public_by_code.get(code, amount) != amount
                   for code, amount in b_useful.items()):
                counts["counterfactual_capacity_mismatch"] += 1
                continue
            public_by_code.update(b_useful)
            if sum(public_by_code.values()) > unknown:
                counts["invalid_unknown_pool"] += 1
                continue
            a_wall, b_wall = sum(a_counts), sum(b_counts)
            row = {"room_id": room_id, "game_id": key[0], "gap": gap,
                   "route_safe": route_safe, "width_gain": width_gain,
                   "wall_capacity_difference": b_wall - a_wall,
                   "zero_wall_difference": int(b_wall == 0) - int(a_wall == 0)}
            rows.append(row)
            counts["matched"] += 1
        by_room[room_id] = dict(sorted(counts.items()))
        totals.update(counts)
    groups = {}
    for gap in (0, -1, -2):
        subset = [row for row in rows if row["route_safe"] and row["gap"] == gap]
        first = [row for row in subset if room_order[row["room_id"]] < 45]
        second = [row for row in subset if room_order[row["room_id"]] >= 45]
        groups[str(gap)] = {
            "wall_capacity_difference": _estimate(subset, "wall_capacity_difference", seed=20260927+gap),
            "first_45_rooms": _estimate(first, "wall_capacity_difference", seed=20261027+gap),
            "last_46_rooms": _estimate(second, "wall_capacity_difference", seed=20261127+gap),
            "zero_wall_difference": _estimate(subset, "zero_wall_difference", seed=20261227+gap),
            "complete_table_ids": len({row["game_id"] for row in subset}),
        }
    primary = groups["0"]["wall_capacity_difference"]
    halves = (groups["0"]["first_45_rooms"], groups["0"]["last_46_rooms"])
    qualified = primary["windows"] >= 100 and primary["rooms"] >= 30
    directional = qualified and primary["room_bootstrap_95"][0] > 0 and all(
        half["mean"] is not None and half["mean"] > 0 for half in halves)
    fingerprint = hashlib.sha256(json.dumps(sorted(fingerprints), separators=(",", ":")).encode()).hexdigest()
    result = {"schema": "g9-diversity-hidden-occupancy-91room/1",
              "source_rooms": len(frozen["rooms"]), "source_official_games": len(fingerprints),
              "source_frozen_rooms_sha256": hashlib.sha256(frozen_bytes).hexdigest(),
              "source_parent_sha256": frozen["parent_source_sha256"],
              "official_docs_fingerprint_sha256": fingerprint,
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "totals": dict(sorted(totals.items())), "by_room": by_room,
              "groups": groups, "primary_sample_qualified": qualified,
              "current_pool_hidden_occupancy_directional": directional,
              "boundary": "赛后暗手只用于墙容量标签；不读终局分或未来墙，不构成策略收益"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "by_room"},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
