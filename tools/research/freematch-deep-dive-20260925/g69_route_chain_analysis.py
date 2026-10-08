#!/usr/bin/env python3
"""G69：同房双方正常摸打的一摸胡入口、终止竞争与强手同窗动作对照。"""

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
import time

import c31_action_layer_gap as c31
import g61_strong_draw_batch as g61
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
G61 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g61-strong-draw-action-atlas-20260927')
G64 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g64-strong-win-timing-20260928')
G69 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g69-same-room-route-chain-20260928')
ROWS = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g69-same-room-route-chain-20260928/route_windows.jsonl.gz')
ROUNDS = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g69-same-room-route-chain-20260928/route_rounds.jsonl.gz')
RESULT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g69-same-room-route-chain-20260928/route_result.json')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_windows(path: Path) -> tuple[list[dict], str]:
    """读取原文或无损 gzip，返回原始 JSON 字节摘要作规则输入绑定。"""

    if path.suffix == ".gz":
        with gzip.open(path, "rb") as stream:
            raw = stream.read()
    else:
        raw = path.read_bytes()
    return json.loads(raw)["windows"], hashlib.sha256(raw).hexdigest()


def route_facts(candidate, seat: int) -> dict | None:
    """只读生产下一次普通自摸结算见证；缺证据返回未知而非零。"""

    value = candidate.value_facts
    if value is None or value.coverage.value != "complete":
        return None
    types = set()
    plain = high = 0
    capacity = 0
    for route in value.routes:
        if route.followup_discard is not None or route.conditions.draw_kind != "normal":
            raise ValueError("G69 普通弃牌的一摸胡路线含后继弃牌或非普通摸牌")
        fan = route.conditional_settlement.fan
        delta = route.conditional_settlement.score_delta
        if type(fan) is not int or fan < 1 or len(delta) != 4 or delta[seat] <= 0:
            raise ValueError("G69 一摸胡结算非法")
        for useful in route.useful_tiles:
            if useful.code in types or not 0 <= useful.remaining_estimate <= 4:
                raise ValueError("G69 一摸胡牌码重复或容量越界")
            types.add(useful.code)
            amount = useful.remaining_estimate
            capacity += amount
            if fan == 1:
                plain += amount
            else:
                high += amount
    facts = candidate.facts
    std_need = facts.standard_shanten_after if facts is not None else None
    std_support = (sum(item.remaining_estimate for item in facts.standard_useful_tiles)
                   if facts is not None and facts.standard_useful_tiles is not None else None)
    return {"any_capacity": capacity, "plain_capacity": plain, "high_capacity": high,
            "tile_types": len(types), "standard_shanten": std_need,
            "standard_support": std_support,
            "baotou_after": facts.baotou_after if facts is not None else None}


def analyze_window(row: dict, *, peer: str, actor: str) -> dict:
    """强手与我方严格同口径重算，不读取后继事件或真实暗手。"""

    observation = observation_from_json(row["observation"])
    seat = observation.seat
    rules = c31.RULES.analyze(observation, value_limits=c31.VALUE_LIMITS)
    legal = {candidate.action_key: candidate for candidate in rules.legal_candidates}
    action = row["actual_action"]
    if action not in legal or not action.startswith("discard:"):
        raise ValueError("G69 已核本人真实弃牌不在合法候选")
    actual = route_facts(legal[action], seat)
    parent_key = row["parent_top_action"]
    parent = (route_facts(legal[parent_key], seat)
              if actor == "peer" and parent_key.startswith("discard:") and parent_key in legal else None)
    ordinal = len(observation.discards[seat]) + 1
    if ordinal < 1:
        raise ValueError("G69 本人行动序号非法")
    return {"peer": peer, "actor": actor, "room": row["room_id"],
            "game_id": row["game_id"], "round_no": row["round_no"],
            "draw_seq": row["draw_seq"], "seat": seat, "action_ordinal": ordinal,
            "white_before": row["observation"]["my_hand"].count("白"),
            "wall_remaining": row["remaining_tile_count"],
            "actual_action": action, "parent_action": parent_key if actor == "peer" else None,
            "parent_score_gap": row["parent_score_gap_top_minus_actual"] if actor == "peer" else None,
            "actual": actual, "parent": parent}


def outcome_index() -> dict[tuple, dict]:
    """只用 G64 已逐局核对的官方结算和事前起手分层。"""

    doc = json.loads((_project_file(_PROJECT_ROOT, G64 / "result.json")).read_text(encoding="utf-8"))
    if doc["schema"] != "g64-strong-win-timing-result/1" or len(doc["rows"]) != 2560:
        raise ValueError("G69 G64 单局结算范围漂移")
    index = {}
    for row in doc["rows"]:
        key = (row["peer"], row["room"], row["game_id"], row["round_no"])
        if key in index:
            raise ValueError("G69 同强手单位的单局结算重复")
        index[key] = row
    return index


def round_record(key: tuple, outcome: dict, windows: list[dict], actor: str) -> dict:
    """入口须发生在真实弃牌之后；终局只是随后竞争结果。"""

    participant = outcome["actors"]["us" if actor == "us" else key[0]]
    complete = [window for window in windows if window["actual"] is not None]
    ready = [window for window in complete if window["actual"]["any_capacity"] > 0]
    plain = [window for window in complete if window["actual"]["plain_capacity"] > 0]
    high = [window for window in complete if window["actual"]["high_capacity"] > 0]
    first = min((window["action_ordinal"] for window in ready), default=None)
    first_plain = min((window["action_ordinal"] for window in plain), default=None)
    first_high = min((window["action_ordinal"] for window in high), default=None)
    if any(window["action_ordinal"] > participant["completed_discards"] for window in windows):
        raise ValueError("G69 当前本人弃牌序号超过官方单局终止弃牌数")
    if participant["status"] == "win" and first is not None and not first < participant["win_turn"]:
        raise ValueError("G69 获胜之前一摸入口序号不合时序")
    return {"peer": key[0], "room": key[1], "game_id": key[2], "round_no": key[3],
            "actor": actor, "seat": participant["seat"],
            "start_white": participant["start_white"], "dealer": participant["dealer"],
            "status": participant["status"], "fan": participant["fan"],
            "win_turn": participant["win_turn"],
            "completed_discards": participant["completed_discards"],
            "clean_windows": len(windows), "complete_windows": len(complete),
            "unknown_windows": len(windows) - len(complete),
            "first_any_ready": first, "first_plain_ready": first_plain,
            "first_high_ready": first_high}


def aggregate_rounds(records: list[dict]) -> dict:
    """以强手－房－单局为主要描述单位，条件比例不作因果比较。"""

    groups: dict[str, Counter] = defaultdict(Counter)
    rooms: dict[str, set[str]] = defaultdict(set)
    for row in records:
        white = "2plus" if row["start_white"] >= 2 else str(row["start_white"])
        for axis in ("all", "start_white_" + white,
                     "dealer_" + ("yes" if row["dealer"] else "no")):
            name = row["peer"] + "/" + row["actor"] + "/" + axis
            c = groups[name]
            c["starts"] += 1
            c["clean_windows"] += row["clean_windows"]
            c["unknown_windows"] += row["unknown_windows"]
            c["wins"] += row["status"] == "win"
            c["plain_wins"] += row["status"] == "win" and row["fan"] == 1
            c["high_wins"] += row["status"] == "win" and row["fan"] >= 2
            c["other_win"] += row["status"] == "other_win"
            c["draw"] += row["status"] == "draw"
            for path in ("any", "plain", "high"):
                first = row["first_" + path + "_ready"]
                if first is not None:
                    c[path + "_ready_rounds"] += 1
                    c[path + "_first_le6"] += first <= 6
                    c[path + "_first_ge7"] += first >= 7
                    c[path + "_ready_then_win"] += row["status"] == "win"
                    c[path + "_ready_then_other_win"] += row["status"] == "other_win"
                    c[path + "_ready_then_draw"] += row["status"] == "draw"
            c["win_without_observed_any_ready"] += row["status"] == "win" and row["first_any_ready"] is None
            rooms[name].add(row["room"])
    return {name: {**dict(sorted(c.items())), "rooms": len(rooms[name])}
            for name, c in sorted(groups.items())}


def aggregate_action_pairs(rows: list[dict]) -> dict:
    """同窗父代反事实仅比较入口，不外推强手的真实后续。"""

    groups: dict[str, Counter] = defaultdict(Counter)
    rooms: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row["actor"] != "peer":
            continue
        for axis in ("all", "le6" if row["action_ordinal"] <= 6 else "ge7"):
            name = row["peer"] + "/" + axis
            c = groups[name]
            c["clean_windows"] += 1
            if row["actual"] is None or row["parent"] is None:
                c["not_comparable"] += 1
                continue
            c["comparable"] += 1
            changed = row["actual_action"] != row["parent_action"]
            c["action_changed"] += changed
            c["strict_changed"] += changed and row["parent_score_gap"] > 0
            for path in ("any", "plain", "high"):
                actual = row["actual"][path + "_capacity"] > 0
                parent = row["parent"][path + "_capacity"] > 0
                class_name = "actual_only" if actual and not parent else "parent_only" if parent and not actual else "both" if actual else "neither"
                c[path + "_" + class_name] += 1
                if changed and row["parent_score_gap"] > 0:
                    c[path + "_strict_" + class_name] += 1
            rooms[name].add(row["room"])
    return {name: {**dict(sorted(c.items())), "rooms": len(rooms[name])}
            for name, c in sorted(groups.items())}


def main() -> None:
    if RESULT.exists() or ROWS.exists() or ROUNDS.exists():
        raise SystemExit("G69 行动链证据已存在，拒绝覆盖")
    g61_doc = json.loads((_project_file(_PROJECT_ROOT, G61 / "result.json")).read_text(encoding="utf-8"))
    g69_doc = json.loads((_project_file(_PROJECT_ROOT, G69 / "batch_result.json")).read_text(encoding="utf-8"))
    if (len(g61_doc["units"]) != 32 or g61_doc["outcome_labels_opened"] is not False or
            g69_doc["completed_rooms"] != 31 or g69_doc["errors"]):
        raise ValueError("G69 强手/我方重建未覆盖完整 31 房")
    official = outcome_index()
    by_round: dict[tuple, list[dict]] = defaultdict(list)
    windows = []
    started = time.perf_counter()
    for unit, record in sorted(g61_doc["units"].items()):
        peer, room = unit.split("/", 1)
        strong_path = _project_file(_PROJECT_ROOT, G61 / "rooms" / (peer + "--" + room) / "windows.json")
        us_path = _project_file(_PROJECT_ROOT, G69 / "rooms" / room / "windows.json.gz")
        strong_windows, strong_sha = load_windows(strong_path)
        us_windows, us_sha = load_windows(us_path)
        if (strong_sha != record["windows_sha256"] or
                us_sha != g69_doc["rooms"][room]["windows_sha256"] or
                sha(us_path) != g69_doc["rooms"][room]["windows_gzip_sha256"]):
            raise ValueError("G69 强手/我方逐窗来源摘要漂移")
        for actor, source in (("peer", strong_windows), ("us", us_windows)):
            for row in source:
                if row["room_id"] != room:
                    raise ValueError("G69 窗口房号不一致")
                key = (peer, room, row["game_id"], row["round_no"])
                if key not in official:
                    raise ValueError("G69 正常摸打窗口没有官方完整单局")
                analyzed = analyze_window(row, peer=peer, actor=actor)
                expected_seat = official[key]["actors"][peer if actor == "peer" else "us"]["seat"]
                if analyzed["seat"] != expected_seat:
                    raise ValueError("G69 当前窗口座位不等于官方同房身份")
                windows.append(analyzed)
                by_round[(*key, actor)].append(analyzed)
    rounds = []
    for key, outcome in sorted(official.items()):
        for actor in ("us", "peer"):
            source = sorted(by_round.get((*key, actor), []), key=lambda item: item["draw_seq"])
            if len({item["draw_seq"] for item in source}) != len(source):
                raise ValueError("G69 单局本人正常摸打窗口重复")
            rounds.append(round_record(key, outcome, source, actor))
    if len(rounds) != 5120:
        raise ValueError("G69 官方双方单局不完整")
    result = {"schema": "g69-same-room-route-chain/1",
              "source_sha256": {"g61_result": sha(_project_file(_PROJECT_ROOT, G61 / "result.json")),
                                "g69_batch": sha(_project_file(_PROJECT_ROOT, G69 / "batch_result.json")),
                                "g64_result": sha(_project_file(_PROJECT_ROOT, G64 / "result.json")),
                                "analysis_script": sha(Path(__file__))},
              "window_count": len(windows), "round_count": len(rounds),
              "round_groups": aggregate_rounds(rounds),
              "action_pairs": aggregate_action_pairs(windows),
              "elapsed_seconds": round(time.perf_counter() - started, 2),
              "boundary": "同房观察性双方行动链；G05 正常摸打限定子集；入口为当前生产规则下一次普通自摸正容量，不是牌墙概率；同窗父代反事实不外推后续。"}
    with gzip.open(ROWS, "wt", encoding="utf-8") as stream:
        for row in windows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    with gzip.open(ROUNDS, "wt", encoding="utf-8") as stream:
        for row in rounds:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    RESULT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"window_count": len(windows), "round_count": len(rounds),
                      "round_groups": {k: v for k, v in result["round_groups"].items() if k.endswith("/all")},
                      "action_pairs": result["action_pairs"]}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
