#!/usr/bin/env python3
"""G45：冻结官方弃牌后，即时响应及我方下一次积极行动机会的赛后审计。"""

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

import g8_public_response_training_rows as g8


HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-public-response-training-20260927')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g45-response-chain-20260927/result.json')


def immediate_response(events: list[dict], index: int, actor: int) -> tuple[str, int | None, int | None]:
    """只在本次弃牌后的首个非过牌事件判定即时鸣牌；返回种类、鸣牌座位及事件下标。"""

    tile = events[index].get("tile")
    for offset in range(index + 1, len(events)):
        event = events[offset]
        kind = event.get("type")
        if kind == "pass":
            continue
        if kind == "timeout":
            if (event.get("data") or {}).get("kind") == "response":
                continue
            return "unknown", None, None
        if kind in ("chi", "peng"):
            if event.get("seat") != actor and event.get("tile") == tile:
                return kind, event["seat"], offset
            return "unknown", None, None
        if kind == "gang":
            data = event.get("data") or {}
            if data.get("kind") == "ming" and event.get("seat") != actor and event.get("tile") == tile:
                return "ming_gang", event["seat"], offset
            return "none", None, None
        if kind in ("tile_drawn", "tile_discarded", "round_ended"):
            return "none", None, None
        return "unknown", None, None
    return "unknown", None, None


def next_positive_opportunity(events: list[dict], index: int, actor: int) -> tuple[str, int | None]:
    """找下一次本人摸牌/积极鸣牌或本小局终局；过牌不算获得牌的机会。"""

    for offset in range(index + 1, len(events)):
        event = events[offset]
        kind = event.get("type")
        if kind == "tile_drawn" and event.get("seat") == actor:
            return "own_draw", offset
        if kind in ("chi", "peng", "gang") and event.get("seat") == actor:
            return "own_claim", offset
        if kind == "round_ended":
            data = event.get("data") or {}
            if data.get("draw"):
                return "draw_end", offset
            if event.get("seat") == actor:
                return "own_hu_end", offset
            if type(event.get("seat")) is int:
                return "other_hu_end", offset
            return "unknown_end", offset
        if kind == "tile_discarded" and event.get("seat") == actor:
            return "own_discard_without_draw_or_claim", offset
    return "missing_end", None


def previous_discard_seat(events: list[dict], start: int, end: int) -> int | None:
    """在下一次本人鸣牌前追溯最近弃牌座位；只用官方事件，不读暗手。"""

    for event in reversed(events[start + 1:end]):
        if event.get("type") == "tile_discarded":
            return event.get("seat")
    return None


def direct_feed(events: list[dict], claim_index: int, own_claim_index: int, claimant: int) -> bool:
    """他家本次鸣后立即弃出的牌被我方鸣，期间不跨任何摸牌或其他鸣牌。"""

    material = [event for event in events[claim_index + 1:own_claim_index]
                if event.get("type") in ("tile_drawn", "tile_discarded", "chi", "peng", "gang", "round_ended")]
    own_claim = events[own_claim_index]
    return (len(material) == 1 and material[0].get("type") == "tile_discarded"
            and material[0].get("seat") == claimant
            and own_claim.get("type") in ("chi", "peng", "gang")
            and own_claim.get("tile") == material[0].get("tile"))


def main() -> None:
    """与 G8 冻结标签逐行对账；只保存聚合与少量序号样例，避免复制全知牌谱。"""

    if OUT.exists():
        raise SystemExit("G45 结果已存在，拒绝覆盖")
    metadata = json.loads((_project_file(_PROJECT_ROOT, SOURCE / "result.json")).read_text(encoding="utf-8"))
    packed = _project_file(_PROJECT_ROOT, SOURCE / "rows.jsonl.gz")
    digest = hashlib.sha256(packed.read_bytes()).hexdigest()
    if digest != metadata["rows_gzip_sha256"]:
        raise ValueError("G8 冻结行摘要漂移")
    targets = {}
    with gzip.open(packed, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            key = row["game_id"], row["round_no"], row["discard_seq"]
            if key in targets:
                raise ValueError("G8 冻结弃牌键重复")
            targets[key] = (row["room_id"], row["label_claim"], row["features"]["tile"])
    if len(targets) != 62975:
        raise ValueError("G8 冻结弃牌数漂移")

    counts = Counter()
    by_room = defaultdict(Counter)
    examples = defaultdict(list)
    matched = set()
    rooms = set(metadata["source_rooms"])
    games = set()
    for _mtime, room, _tag, game_id, doc in g8.load_rooms():
        if room not in rooms:
            continue
        actor_seats = [seat.get("user_id") for seat in doc.get("seats") or []]
        if g8.ACTOR not in actor_seats:
            raise ValueError("官方房缺本人座位")
        actor = actor_seats.index(g8.ACTOR)
        games.add(game_id)
        for round_no, events, _start_hands in g8.round_blocks(doc):
            if any(type(event.get("seq")) is not int for event in events):
                raise ValueError("官方事件缺序号")
            for index, event in enumerate(events):
                if event.get("type") != "tile_discarded" or event.get("seat") != actor:
                    continue
                key = game_id, round_no, event["seq"]
                target = targets.get(key)
                if target is None:
                    continue
                if key in matched:
                    raise ValueError("官方已执行弃牌重复")
                matched.add(key)
                expected_room, label_claim, tile = target
                if room != expected_room or event.get("tile") != tile:
                    raise ValueError("G8 动作与官方牌码/房间错配")
                kind, claimant, claim_index = immediate_response(events, index, actor)
                prior = g8._response(events, index)
                if prior == "unknown" or kind == "unknown":
                    raise ValueError("G8 已定标弃牌在 G45 无法定标")
                if (kind != "none") != bool(label_claim) or (prior == "claim") != bool(label_claim):
                    raise ValueError("G45 即时响应与 G8 冻结标签冲突")
                opportunity, next_index = next_positive_opportunity(events, index, actor)
                if opportunity in ("missing_end", "unknown_end", "own_discard_without_draw_or_claim"):
                    raise ValueError("下一次本人积极行动/终局无法审计")
                group = "claimed" if label_claim else "not_claimed"
                counts[f"response|{kind}"] += 1
                counts[f"opportunity|{group}|{opportunity}"] += 1
                by_room[room][f"response|{kind}"] += 1
                by_room[room][f"opportunity|{group}|{opportunity}"] += 1
                if claimant is not None:
                    relative = (claimant - actor) % 4
                    counts[f"claimant_relative|{kind}|{relative}"] += 1
                    if opportunity == "own_claim" and next_index is not None:
                        source = previous_discard_seat(events, index, next_index)
                        fed_by_claimant = source == claimant
                        counts[f"own_claim_after_opponent_claim|fed_by_initial_claimant|{fed_by_claimant}"] += 1
                        if claim_index is None:
                            raise ValueError("他家鸣牌缺事件下标")
                        directly_fed = direct_feed(events, claim_index, next_index, claimant)
                        counts[f"own_claim_after_opponent_claim|direct_feed|{directly_fed}"] += 1
                        if directly_fed:
                            counts[f"direct_feed|{kind}"] += 1
                            by_room[room]["direct_feed"] += 1
                        sample_key = "fed_by_claimant" if fed_by_claimant else "fed_by_other"
                        if len(examples[sample_key]) < 8:
                            examples[sample_key].append({"room_id": room, "game_id": game_id,
                                                         "round_no": round_no, "discard_seq": event["seq"],
                                                         "claim_kind": kind, "claimant_relative": relative,
                                                         "own_claim_seq": events[next_index]["seq"],
                                                         "direct_feed": directly_fed})
    if len(matched) != len(targets) or len(games) != metadata["counts"]["official_games"]:
        raise ValueError("G8 冻结样本官方全覆盖不符")
    if set(by_room) != rooms:
        raise ValueError("G8 冻结房覆盖不符")
    result = {"schema": "g45-response-chain/1", "source_rows_gzip_sha256": digest,
              "parent_source_sha256": metadata["parent_source_sha256"],
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "source_frozen_rooms_sha256": hashlib.sha256(g8.FROZEN.read_bytes()).hexdigest(),
              "rooms": len(by_room), "games": len(games), "executed_discards": len(matched),
              "counts": dict(sorted(counts.items())),
              "by_room": {room: dict(sorted(value.items())) for room, value in sorted(by_room.items())},
              "examples": dict(examples),
              "boundary": "官方完整牌谱仅作赛后标签；G8 已执行弃牌的观察关联，不含备选弃牌反事实；下一次积极行动只计本人摸牌或吃碰杠，过牌不算得牌。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("by_room", "examples")},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
