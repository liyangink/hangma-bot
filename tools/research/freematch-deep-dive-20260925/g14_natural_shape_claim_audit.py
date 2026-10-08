#!/usr/bin/env python3
"""G14：旧自然宽面改选的同窗合法鸣牌机会复核；赛后暗手仅作标签。"""

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
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np

import c31_action_layer_gap as c31
import g8_public_response_training_rows as source
import g9_diversity_hidden_occupancy_91room as hidden


HERE = Path(__file__).resolve().parent
FROZEN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-two-white-next-draw-20260927/frozen_rooms.json')
G11 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g11-shape-risk-behavior-20260927/result.json')
G14 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-white-reserve-frontier-20260927')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-natural-shape-claim-audit-20260927/result.json')


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _opportunity(snap: dict, discarder: int, tile: str, wall_remaining: int) -> dict:
    """借生产规则算每家吃碰明杠合法候选，不自行推断牌型。"""

    members_peng, members_chi = c31.C23.window_members(discarder, tile, snap["owner"])
    result = {"peng": False, "chi": False, "ming_gang": False}
    for seat in sorted(set(members_peng) | set(members_chi)):
        melds = snap["melds"][seat]
        chi_count = sum(group["kind"] == "chi" for group in melds)
        peng_codes = tuple(group["tiles"][0] for group in melds
                           if group["kind"] == "peng")
        shapes = c31.C23.claim_shapes(
            snap["hands"][seat], seat, discarder, tile, snap["seq"],
            chi_count, peng_codes,
            snap["owner"] is not None and seat != snap["owner"],
            seat in members_peng, seat in members_chi, wall_remaining,
        )
        for kind in result:
            result[kind] |= shapes[kind]
    result["any"] = any(result.values())
    return result


def _estimate(rows: list[dict], field: str, seed: int) -> dict:
    """以房间为独立重采样单元，窗口加权报告成对差值。"""

    by_room = defaultdict(list)
    for row in rows:
        by_room[row["room_id"]].append(row[field])
    rooms = sorted(by_room)
    if not rooms:
        return {"windows": 0, "rooms": 0, "mean": None, "room_bootstrap_95": None}
    sums = np.asarray([sum(by_room[room]) for room in rooms], dtype=float)
    counts = np.asarray([len(by_room[room]) for room in rooms], dtype=float)
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(rooms), size=(20_000, len(rooms)))
    samples = sums[indices].sum(axis=1) / counts[indices].sum(axis=1)
    return {"windows": len(rows), "rooms": len(rooms),
            "mean": float(sums.sum() / counts.sum()),
            "room_bootstrap_95": [float(np.quantile(samples, 0.025)),
                                  float(np.quantile(samples, 0.975))]}


def main() -> None:
    """只用 G11/G14 冻结行为选窗口，读取官方赛后暗手标定合法机会。"""

    if OUT.exists():
        raise SystemExit("G14 鸣牌机会结果已存在，拒绝覆盖")
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    old = json.loads(G11.read_text(encoding="utf-8"))
    frontier = json.loads((_project_file(_PROJECT_ROOT, G14 / "result.json")).read_text(encoding="utf-8"))
    if (old.get("outcome_blind") is not True or
            old["parent_source_sha256"] != frozen["parent_source_sha256"] or
            frontier.get("outcome_blind") is not True or
            frontier["parent_source_sha256"] != frozen["parent_source_sha256"] or
            frontier["rows_sha256"] != _sha(_project_file(_PROJECT_ROOT, G14 / "rows.jsonl.gz"))):
        raise ValueError("冻结母体、行为或前沿身份漂移")
    same_frontier = {}
    with gzip.open(_project_file(_PROJECT_ROOT, G14 / "rows.jsonl.gz"), "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if not row["same_action_g11"]:
                continue
            key = (row["game_id"], row["round_no"], row["trigger_seq"])
            if key in same_frontier:
                raise ValueError("G14 前沿键重复")
            same_frontier[key] = row
    targets = defaultdict(dict)
    for row in old["changed"]:
        key = (row["game_id"], row["round_no"], row["trigger_seq"])
        if key not in same_frontier:
            continue
        match = same_frontier[key]
        if (row["parent_action"] != match["parent_action"] or
                row["candidate_action"] != match["alternative_action"] or
                row["white_count"] < 1 or
                "discard:白" in (row["parent_action"], row["candidate_action"])):
            raise ValueError("G11/G14 主组动作或持白身份不一致")
        targets[row["room_id"]][key] = row
    if sum(map(len, targets.values())) != len(same_frontier):
        raise ValueError("G14 主组未全部匹配 G11 改选")

    docs = defaultdict(dict)
    for _mtime, room_id, _tag, game_id, doc in source.load_rooms():
        if room_id in targets:
            docs[room_id][game_id] = doc

    rows = []
    counts = Counter()
    room_order = {room["room_id"]: i for i, room in enumerate(frozen["rooms"])}
    for room in frozen["rooms"]:
        room_id = room["room_id"]
        if room_id not in targets:
            continue
        audit = source.ROOT / room["audit_dir"]
        decisions = audit / "participants" / source.ACTOR / "decisions.jsonl"
        if decisions.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结父代审计大小漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("冻结父代源码身份漂移")
        accepted = source._accepted(decisions)
        snapshots = hidden._room_snapshots(docs[room_id])
        seen = set()
        for context, request, plan in source.screen._iter_decisions(audit):
            key = (context["game_id"], context["round_no"], context["trigger_seq"])
            target = targets[room_id].get(key)
            if target is None:
                continue
            if key in seen:
                raise ValueError("同一弃牌窗口重复")
            seen.add(key)
            parent = target["parent_action"]
            alternate = target["candidate_action"]
            ranked = sorted(plan.get("candidates") or [],
                            key=lambda item: item.get("rank", 10**9))
            legal = {item["action_key"] for item in
                     (request.get("rules") or {}).get("legal_candidates") or []}
            if (not ranked or ranked[0].get("action_key") != parent or
                    accepted.get(context["decision_id"]) != parent or
                    parent not in legal or alternate not in legal or
                    (request.get("window_key") or {}).get("phase") != "draw"):
                raise ValueError("父代接受、正常摸打或备选合法性不符")
            snap = snapshots.get((key[0], key[1], key[2] + 1))
            observation = request["observation"]
            seat = observation["seat"]
            parent_tile = parent.split(":", 1)[1]
            alternate_tile = alternate.split(":", 1)[1]
            if snap is None or snap["discarder"] != seat or snap["tile"] != parent_tile:
                raise ValueError("官方弃牌响应前快照不符")
            hand = list(observation["my_hand"])
            drawn = observation.get("drawn_tile")
            if drawn is not None and len(hand) % 3 == 1:
                hand.append(drawn)
            expected = Counter(hand)
            expected[parent_tile] -= 1
            expected += Counter()
            if expected != Counter(snap["hands"][seat]):
                raise ValueError("官方快照本人暗手与动作审计不符")
            wall_remaining = observation.get("remaining_tile_count")
            if type(wall_remaining) is not int:
                raise ValueError("官方剩余牌墙数缺失")
            p = _opportunity(snap, seat, parent_tile, wall_remaining)
            a = _opportunity(snap, seat, alternate_tile, wall_remaining)
            actual_claim = snap["claim_seat"] is not None
            if actual_claim and not p["any"]:
                raise ValueError("已执行父代弃牌实际被鸣，量具却无合法机会")
            rows.append({"room_id": room_id, "game_id": key[0],
                         "round_no": key[1], "trigger_seq": key[2],
                         "white_count": target["white_count"],
                         "parent_action": parent, "alternate_action": alternate,
                         "parent_opportunity": p, "alternate_opportunity": a,
                         "actual_parent_claim": actual_claim,
                         "any_difference": int(a["any"]) - int(p["any"]),
                         "peng_difference": int(a["peng"]) - int(p["peng"]),
                         "chi_difference": int(a["chi"]) - int(p["chi"]),
                         "ming_gang_difference": int(a["ming_gang"]) - int(p["ming_gang"])})
            counts["matched"] += 1
            counts["parent_actual_claim"] += actual_claim
            counts["only_alternate_has_any_opportunity"] += a["any"] and not p["any"]
            counts["only_parent_has_any_opportunity"] += p["any"] and not a["any"]
        if seen != set(targets[room_id]):
            raise ValueError("目标房缺 G11/G14 窗口")
    if len(rows) != len(same_frontier):
        raise ValueError("鸣牌机会主组未全量覆盖")
    measures = {field: _estimate(rows, field, 20260927 + i)
                for i, field in enumerate(("any_difference", "peng_difference",
                                           "chi_difference", "ming_gang_difference"))}
    halves = {label: _estimate([row for row in rows if
                              (room_order[row["room_id"]] < 45) == first],
                             "any_difference", 20261027 + i)
              for i, (label, first) in enumerate((("first_45_rooms", True),
                                                   ("last_46_rooms", False)))}
    primary = measures["any_difference"]
    result = {"schema": "g14-natural-shape-claim-audit/1", "outcome_blind": True,
              "source_frozen_rooms_sha256": _sha(FROZEN),
              "source_g11_result_sha256": _sha(G11),
              "source_g14_result_sha256": _sha(_project_file(_PROJECT_ROOT, G14 / "result.json")),
              "source_g14_rows_sha256": _sha(_project_file(_PROJECT_ROOT, G14 / "rows.jsonl.gz")),
              "script_sha256": _sha(Path(__file__)),
              "counts": dict(sorted(counts.items())),
              "measures": measures, "halves": halves,
              "sample_qualified": len(rows) >= 100 and primary["rooms"] >= 30,
              "boundary": "赛后他家暗手只作同窗合法鸣牌机会标签；机会不等于实际选择，不能证明旧候选负分成因，更不能进入线上特征。",
              "rows": rows}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "rows"},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
