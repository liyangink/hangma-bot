#!/usr/bin/env python3
"""四间开发房玄武吃碰响应机会的官方动作与冻结父代同窗基线。"""

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

import g05_strong_draw_reconstruction as g05
import anatomy_lib as anatomy
import c31_action_layer_gap as c31
from extract_room_scores import load_rooms


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g05-response-dev-behavior-01')
ROOMS = (
    "a_f8ddc4c3bd9b", "a_d773a8e428a0",
    "a_852fb97c102e", "a_2a8aa14dc8a1",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run() -> dict:
    """只评价固定四房的合法吃碰机会，不读取留出房动作。"""
    selected = []
    for _, room, _, game_id, doc in load_rooms():
        if room in ROOMS:
            users = [seat.get("user_id") for seat in doc.get("seats") or []]
            if g05.XUANWU in users:
                selected.append((room, game_id, doc, users.index(g05.XUANWU)))
    by_room = Counter(room for room, *_ in selected)
    if any(by_room[room] != 10 for room in ROOMS):
        raise ValueError("四开发房不是各十场：" + str(by_room))
    parent = c31.load_parent()
    rows = []
    counts = {room: Counter() for room in ROOMS}
    for room, game_id, doc, target in selected:
        scores = [0, 0, 0, 0]
        metadata = c31.round_metadata(doc)
        for round_no, events, start_hands in anatomy.round_blocks(doc):
            counts[room]["rounds"] += 1
            if start_hands is None:
                counts[room]["excluded_missing_start_hands_rounds"] += 1
                continue
            dealer = metadata.get(round_no, {}).get("dealer")
            if dealer is None:
                counts[room]["excluded_unknown_dealer_rounds"] += 1
                continue
            snaps = c31.reconstruct(events, start_hands, scores, dealer)
            for seq in sorted(snaps):
                snap = snaps[seq]
                if snap["tile"] == c31.WEALTH or target == snap["discarder"]:
                    continue
                phases = []
                if target in c31._peng_members(snap["discarder"], snap["tile"], snap["owner"]):
                    phases.append("response_peng")
                if target in c31._chi_members(snap["discarder"], snap["tile"], snap["owner"]):
                    phases.append("response_chi")
                if not phases:
                    continue
                counts[room]["potential_response_windows"] += 1
                window, _per_phase, audit = c31.evaluate_window(
                    snap, target, phases, game_id, round_no, parent)
                counts[room].update(audit)
                if window is None:
                    counts[room]["excluded_no_legal_chi_or_peng"] += 1
                    continue
                actual = bool(snap["claim_seat"] == target
                              and snap["claim_kind"] in {"peng", "chi", "gang"})
                plan = bool(window["margin"] > 0)
                rows.append({
                    "room_id": room, "game_id": game_id, "round_no": round_no,
                    "discard_seq": seq, "seat": target,
                    "actual_claim": actual, "parent_claim": plan,
                    "actual_kind": snap["claim_kind"] if actual else None,
                    "parent_margin": window["margin"],
                    "parent_claim_key": window["claim"]["action_key"],
                    "wall_remaining": window["observation"].remaining_tile_count,
                    "dealer": target == dealer,
                    "baotou": window["observation"].rule_state.baotou,
                    "white_count": sum(tile.code == c31.WEALTH for tile in window["observation"].my_hand),
                    "own_meld_count": len(window["observation"].melds[target]),
                })
                counts[room]["opportunities"] += 1
                counts[room]["actual_claim"] += actual
                counts[room]["parent_claim"] += plan
                counts[room]["actual_claim_parent_claim"] += actual and plan
                counts[room]["actual_claim_parent_pass"] += actual and not plan
                counts[room]["actual_pass_parent_claim"] += not actual and plan
                counts[room]["actual_pass_parent_pass"] += not actual and not plan
            ended = next((event for event in events if event.get("type") == "round_ended"), None)
            if ended is None:
                raise ValueError("缺权威局结算")
            delta = (ended.get("data") or {}).get("scores")
            if not isinstance(delta, list) or len(delta) != 4:
                raise ValueError("局分数向量缺失")
            scores = [a + b for a, b in zip(scores, delta)]
    keys = {(row["game_id"], row["round_no"], row["discard_seq"], row["seat"])
            for row in rows}
    if len(keys) != len(rows):
        raise ValueError("同一响应机会重复")
    return {
        "schema": "g05-response-dev-behavior/1",
        "script_sha256": digest(Path(__file__)),
        "c31_reconstruction_sha256": digest(Path(c31.__file__)),
        "room_counts": {room: dict(sorted(value.items())) for room, value in counts.items()},
        "selected_games": {room: sorted(game_id for selected_room, game_id, _, _ in selected
                                        if selected_room == room) for room in ROOMS},
        "windows": rows,
        "no_outcome_value_used_as_action_quality_label": True,
    }


def main() -> None:
    """输出结果与可复核窗口，保留每房分母且拒绝覆盖。"""
    if OUT.exists():
        raise FileExistsError("开发房响应结果目录已存在，拒绝覆盖")
    payload = run()
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(
        json.dumps({key: value for key, value in payload.items() if key != "windows"},
                   ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (_project_file(_PROJECT_ROOT, OUT / "windows.json")).write_text(
        json.dumps({"schema": "g05-response-dev-windows/1", "windows": payload["windows"]},
                   ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({room: payload["room_counts"][room] for room in ROOMS},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
