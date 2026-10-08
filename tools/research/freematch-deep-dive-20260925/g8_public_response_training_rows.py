#!/usr/bin/env python3
"""冻结已执行弃牌的公开前态与官方被鸣标签；验证房暂不读取。"""

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
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys

import natural_shape_loss_screen as screen
from extract_room_scores import load_rooms

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "review" / "baotou-anatomy-20260925")))
from anatomy_lib import round_blocks


FROZEN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-two-white-next-draw-20260927/frozen_rooms.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-public-response-training-20260927')
ACTOR = screen.PARTICIPANT


def _response(events: list[dict], index: int) -> str:
    """只读本次弃牌后的官方响应轨迹；非响应超时视为无法定标。"""

    discarder = events[index]
    for event in events[index + 1:]:
        kind = event["type"]
        if kind == "pass":
            continue
        if kind == "timeout":
            if (event.get("data") or {}).get("kind") == "response":
                continue
            return "unknown"
        if kind in ("chi", "peng"):
            return "claim" if event.get("seat") != discarder["seat"] and event.get("tile") == discarder["tile"] else "unknown"
        if kind == "gang":
            data = event.get("data") or {}
            return "claim" if (data.get("kind") == "ming" and event.get("seat") != discarder["seat"]
                               and event.get("tile") == discarder["tile"]) else "none"
        if kind in ("tile_drawn", "tile_discarded", "round_ended"):
            return "none"
        return "unknown"
    return "unknown"


def _official_index(rooms: set[str]) -> tuple[dict[tuple, dict], Counter, set[str]]:
    """仅为训练房构造弃牌已执行事件索引，不保留四家赛后暗手。"""

    index = {}
    counts = Counter()
    games = set()
    for _mtime, room, _tag, game_id, doc in load_rooms():
        if room not in rooms:
            continue
        seats = [seat.get("user_id") for seat in doc.get("seats") or []]
        if ACTOR not in seats:
            raise ValueError("冻结官方房缺本人座位")
        actor = seats.index(ACTOR)
        games.add(game_id)
        for round_no, events, _start_hands in round_blocks(doc):
            for position, event in enumerate(events):
                if event["type"] != "tile_discarded" or event.get("seat") != actor:
                    continue
                key = (game_id, round_no, event["seq"])
                if key in index:
                    raise ValueError("官方弃牌事件重复")
                label = _response(events, position)
                index[key] = {"tile": event["tile"], "seat": actor, "label": label}
                counts[f"official_{label}"] += 1
    counts["official_rooms"] = len(rooms)
    counts["official_games"] = len(games)
    return index, counts, games


def _accepted(decisions: Path) -> dict[str, str]:
    """按决策 ID 索引官方明确接受的动作；不把计划首选当已执行。"""

    accepted = {}
    with decisions.open(encoding="utf-8") as stream:
        for line in stream:
            entry = json.loads(line)
            if entry.get("kind") != "submission_outcome":
                continue
            payload = entry.get("payload") or {}
            if payload.get("outcome_type") != "SubmitAccepted":
                continue
            decision_id = payload.get("decision_id")
            action_key = payload.get("action_key")
            if not decision_id or not action_key:
                raise ValueError("已接受提交缺决策或动作标识")
            if decision_id in accepted and accepted[decision_id] != action_key:
                raise ValueError("单决策接受了不同动作")
            accepted[decision_id] = action_key
    return accepted


def _feature_row(observation: dict, legal: dict, plan_item: dict, *, tile: str) -> dict:
    """严格白名单投影：候选风险分来自父代当时评分，不读后续事件。"""

    seat = observation["seat"]
    rivers = observation["discards"]
    melds = observation["melds"]
    if len(rivers) != 4 or len(melds) != 4:
        raise ValueError("公开牌河/副露座位维度不正确")
    detail = ((plan_item.get("score_trace") or {}).get("detail") or {})
    risk = detail.get("risk_units")
    if type(risk) not in (int, float):
        raise ValueError("父代已执行弃牌缺风险评分量")
    shanten = (legal.get("facts") or {}).get("shanten_after")
    if type(shanten) is not int:
        raise ValueError("已执行弃牌缺合法向听事实")
    hand = list(observation.get("my_hand") or [])
    drawn = observation.get("drawn_tile")
    if drawn is not None and len(hand) % 3 == 1:
        # 审计合同允许本次摸牌单列；完整 14-3×副露张中不能再补一次。
        hand.append(drawn)
    return {"tile": tile, "seat": seat, "dealer_relative":
            (observation["dealer_seat"] - seat) % 4,
            "wall_remaining": observation.get("remaining_tile_count"),
            "shanten_after": shanten, "risk_units": float(risk),
            "white_count": hand.count("白"),
            "own_tile_count": hand.count(tile),
            "public_tile_count": sum(river.count(tile) for river in rivers) +
            sum(sum(group.get("tiles", []).count(tile) for group in seat_melds)
                for seat_melds in melds),
            "river_lengths_relative": [len(rivers[(seat + delta) % 4]) for delta in (1, 2, 3)],
            "meld_lengths_relative": [len(melds[(seat + delta) % 4]) for delta in (1, 2, 3)],
            "same_tile_river_relative": [rivers[(seat + delta) % 4].count(tile)
                                         for delta in (1, 2, 3)],
            "catch_play": bool((observation.get("rule_state") or {}).get("catch_play"))}


def main() -> None:
    """用冻结房生成训练集，逐房及错配计数；验证房文件不在读集。"""

    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot-rooms", type=int, default=0,
                        help="仅检查冻结清单前 N 房，不生成正式训练集")
    args = parser.parse_args()
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    if args.pilot_rooms < 0 or args.pilot_rooms > len(frozen["rooms"]):
        raise ValueError("pilot-rooms 超出冻结房范围")
    selected_rooms = frozen["rooms"][:args.pilot_rooms] if args.pilot_rooms else frozen["rooms"]
    rooms = {room["room_id"] for room in selected_rooms}
    if not args.pilot_rooms and len(rooms) != 91:
        raise ValueError("冻结训练房不再是 91 间")
    official, counts, official_games = _official_index(rooms)
    records = []
    by_room = defaultdict(Counter)
    seen = set()
    missing_games = set()
    for room in selected_rooms:
        audit = _project_file(_PROJECT_ROOT, ROOT / room["audit_dir"])
        decisions = audit / "participants" / ACTOR / "decisions.jsonl"
        if decisions.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结审计字节数漂移")
        release = (json.loads((audit / "manifest.json").read_text(encoding="utf-8")).get("payload") or {}).get("policy_release") or {}
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("父代源码摘要漂移")
        accepted = _accepted(decisions)
        for context, request, plan in screen._iter_decisions(audit):
            if (request.get("window_key") or {}).get("phase") != "draw":
                continue
            decision_id = context.get("decision_id")
            action_key = accepted.get(decision_id)
            if not action_key:
                counts["draw_not_accepted"] += 1
                continue
            if not action_key.startswith("discard:"):
                counts["draw_accepted_non_discard"] += 1
                continue
            tile = action_key.split(":", 1)[1]
            key = (context["game_id"], context["round_no"], context["trigger_seq"] + 1)
            if key in seen:
                counts["draw_duplicate"] += 1
                continue
            seen.add(key)
            event = official.get(key)
            if event is None:
                if key[0] not in official_games:
                    counts["missing_official_game_discard"] += 1
                    missing_games.add(key[0])
                else:
                    counts["official_seq_missing"] += 1
                continue
            if event["tile"] != tile or event["seat"] != request["observation"]["seat"]:
                counts["official_action_mismatch"] += 1
                continue
            if event["label"] == "unknown":
                counts["label_unknown"] += 1
                continue
            legal = [candidate for candidate in (request.get("rules") or {}).get("legal_candidates") or []
                     if candidate.get("action_key") == action_key]
            ranked = [candidate for candidate in plan.get("candidates") or []
                      if candidate.get("action_key") == action_key]
            if len(legal) != 1 or len(ranked) != 1:
                counts["missing_accepted_action_facts"] += 1
                continue
            features = _feature_row(request["observation"], legal[0], ranked[0], tile=tile)
            record = {"room_id": room["room_id"], "game_id": key[0],
                      "round_no": key[1], "discard_seq": key[2],
                      "label_claim": int(event["label"] == "claim"),
                      "features": features}
            records.append(record)
            by_room[room["room_id"]][event["label"]] += 1
            counts[f"train_{event['label']}"] += 1
    if counts["official_action_mismatch"] or counts["official_seq_missing"]:
        raise ValueError("审计接受动作与官方事件序列不一致，先修测量链：" +
                         repr(dict(sorted(counts.items()))))
    if not records or len(by_room) != len(rooms):
        raise ValueError("训练行或房级覆盖不全")
    out_dir = _project_file(_PROJECT_ROOT, OUT / f"pilot-{args.pilot_rooms}") if args.pilot_rooms else OUT
    out_dir.mkdir(parents=True, exist_ok=True)
    rows_path = out_dir / "rows.jsonl.gz"
    plain_hasher = hashlib.sha256()
    with rows_path.open("wb") as stream:
        with gzip.GzipFile(fileobj=stream, mode="wb", filename="", mtime=0) as compressed:
            for record in records:
                line = (json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
                plain_hasher.update(line)
                compressed.write(line)
    digest = hashlib.sha256(rows_path.read_bytes()).hexdigest()
    result = {"schema": "g8-public-response-training/1", "train_only": True,
              "parent_source_sha256": frozen["parent_source_sha256"],
              "source_rooms": sorted(rooms), "rows_gzip_sha256": digest,
              "rows_plain_sha256": plain_hasher.hexdigest(),
              "missing_official_games_excluded": sorted(missing_games),
              "counts": dict(sorted(counts.items())),
              "by_room": {room: dict(sorted(values.items())) for room, values in sorted(by_room.items())},
              "boundary": "只配对 SubmitAccepted 已执行弃牌与官方事件；训练特征均取动作前观察，不打开验证房"}
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                                     encoding="utf-8")
    print(json.dumps(result["counts"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
