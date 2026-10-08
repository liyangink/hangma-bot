#!/usr/bin/env python3
"""只读复算前三百四十一房的三白一番合法胡支持域与实际结局。

只使用动作前本人观察和生产规则保存的条件路线来分层；官方后续事件
只标记已经执行的动作结局，不把它当未执行动作的反事实。结果写标准输出。
"""

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
from hashlib import sha256
import json
from pathlib import Path
import sys


ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
STATE = _project_file(_PROJECT_ROOT, ROOT / "runs/auto-match-watchdog/auto-match-watchdog-state.json")
G256 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g256-hu-continue-visible-residual-20260929/result.json')
OFFICIAL = _project_file(_PROJECT_ROOT, ROOT / "artifacts/sessions/r18-sse-freematch-campaign-20260925b/official")
PARTICIPANT = "u_13495c3d79c8"
ROOM_LIMIT = 341
LAST_ROOM = "a_3c88ffedb01f"


def white_count(observation: dict) -> int:
    """兼容官方 14 张已含摸牌与模拟 13 张另列摸牌的手牌形态。"""

    hand = list(observation["my_hand"])
    meld_count = len(observation["melds"][observation["seat"]])
    expected = 14 - 3 * meld_count
    if len(hand) == expected - 1:
        hand.append(observation["drawn_tile"])
    if len(hand) != expected:
        raise ValueError("摸牌窗口暗手张数不符合副露数")
    return hand.count("白")


def route_summary(action: dict) -> dict:
    """提取执行合法弃牌后的一摸条件番与公开未见物理容量上界。"""

    facts = action.get("facts") or {}
    value = action.get("value_facts") or {}
    routes = []
    for route in value.get("routes") or []:
        settlement = route["conditional_settlement"]
        routes.append({
            "fan": settlement["fan"],
            "details": list(settlement["details"]),
            "capacity": sum(tile["remaining_estimate"] for tile in route["useful_tiles"]),
            "tiles": [
                [tile["code"], tile["remaining_estimate"]]
                for tile in route["useful_tiles"]
            ],
        })
    return {
        "action_key": action["action_key"],
        "standard_shanten_after": facts.get("standard_shanten_after"),
        "seven_pairs_shanten_after": facts.get("seven_pairs_shanten_after"),
        "baotou_after": facts.get("baotou_after"),
        "coverage": value.get("coverage"),
        "routes": routes,
    }


def extract_rows(rooms: list[dict]) -> tuple[list[dict], Counter]:
    """将同一决策的输入、父代计划和官方提交回执按标识配对。"""

    counts: Counter = Counter()
    rows = []
    seen = set()
    for room in rooms:
        if room.get("terminal_reason") != "tournament_finished":
            continue
        audit = _project_file(_PROJECT_ROOT, ROOT / room["audit_dir"] / "participants" / PARTICIPANT / "decisions.jsonl")
        if not audit.is_file():
            raise ValueError(f"缺官方审计：{room['room_id']}")
        pending = {}
        with audit.open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                if '"kind": "decision_input"' in line:
                    counts["decision_input"] += 1
                    # 大审计中先检查观察的原始手牌，避免解析百万条无关大 JSON。
                    start = line.find('"my_hand": [')
                    stop = line.find("]", start)
                    if start < 0 or stop < 0 or line[start:stop].count('"白"') < 2:
                        continue
                    record = json.loads(line)
                    request = record["payload"]["request"]
                    observation = request["observation"]
                    if observation["phase"] != "draw" or white_count(observation) != 3:
                        continue
                    counts["three_white_draw"] += 1
                    legal = request["rules"]["legal_candidates"]
                    hu = next((item for item in legal if item["action_key"] == "hu"), None)
                    if hu is None:
                        continue
                    counts["three_white_legal_hu"] += 1
                    settlement = hu["value_facts"]["immediate_settlement"]
                    if settlement["fan"] != 1:
                        continue
                    context = record["context"]
                    key = (context["game_id"], context["round_no"], context["trigger_seq"])
                    if key in seen:
                        raise ValueError(f"同窗决策输入重复：{key}")
                    seen.add(key)
                    alternatives = [
                        route_summary(item) for item in legal
                        if item["action_key"].startswith("discard:")
                        and item["action_key"] != "discard:白"
                    ]
                    if not alternatives:
                        raise ValueError(f"没有合法非白续行动作：{key}")
                    row = {
                        "room_id": room["room_id"], "game_id": context["game_id"],
                        "round_no": context["round_no"], "trigger_seq": context["trigger_seq"],
                        "seat": observation["seat"],
                        "wall_remaining": observation["remaining_tile_count"],
                        "current_baotou": observation["rule_state"]["baotou"],
                        "current_chain_count": observation["rule_state"]["chain_count"],
                        "immediate_hu_focal_delta": settlement["score_delta"][observation["seat"]],
                        "parent_action": None, "accepted_action": None,
                        "nonwhite_alternatives": alternatives,
                    }
                    rows.append(row)
                    pending[context["decision_id"]] = row
                elif '"kind": "decision_planned"' in line and pending:
                    record = json.loads(line)
                    row = pending.get(record["context"]["decision_id"])
                    if row is not None:
                        plan = record["payload"].get("returned_plan") or {}
                        row["parent_action"] = (plan.get("candidates") or [{}])[0].get("action_key")
                elif '"kind": "submission_outcome"' in line and pending:
                    record = json.loads(line)
                    row = pending.get(record["context"]["decision_id"])
                    if row is not None and record["payload"].get("outcome_type") == "SubmitAccepted":
                        row["accepted_action"] = record["payload"].get("action_key")
        if any(row["parent_action"] is None or row["accepted_action"] is None
               for row in pending.values()):
            raise ValueError(f"合法胡窗缺计划或已接受提交：{room['room_id']}")
    return rows, counts


def official_sources(game_ids: set[str]) -> dict[str, Path]:
    """按官方下载时间确定性选择一份已缓存牌谱，校验同游戏摘要。"""

    selected = {}
    for path in sorted(OFFICIAL.glob("**/source.json")):
        source = json.loads(path.read_text(encoding="utf-8"))
        game_id = source.get("game_id")
        if game_id not in game_ids:
            continue
        key = (source["captured_at"], str(path))
        previous = selected.get(game_id)
        if previous is None or key > previous[0]:
            selected[game_id] = (key, path.with_name("events.json"))
    if set(selected) != game_ids:
        raise ValueError(f"牌谱缺失：{sorted(game_ids - set(selected))}")
    return {game_id: pair[1] for game_id, pair in selected.items()}


def attach_actual_outcomes(rows: list[dict]) -> None:
    """只把已执行行动的后续官方终局记为观察结果。"""

    sources = official_sources({row["game_id"] for row in rows})
    cache = {}
    for row in rows:
        game_id = row["game_id"]
        if game_id not in cache:
            cache[game_id] = json.loads(sources[game_id].read_text(encoding="utf-8"))
        doc = cache[game_id]
        if doc["game_id"] != game_id or doc["room_id"] != row["room_id"]:
            raise ValueError(f"牌谱来源与审计身份不符：{game_id}")
        # events.json 的 blocks 是分页块，同一单局可出现多个块。
        events = {}
        for block in doc["blocks"]:
            if block["round_no"] != row["round_no"]:
                continue
            for event in block["events"]:
                old = events.get(event["seq"])
                if old is not None and old != event:
                    raise ValueError(f"牌谱相同 seq 内容冲突：{game_id}")
                events[event["seq"]] = event
        timeline = [events[seq] for seq in sorted(events)]
        ends = [event for event in timeline if event["type"] == "round_ended"]
        if len(ends) != 1 or ends[0]["seq"] <= row["trigger_seq"]:
            raise ValueError(f"单局终局事件缺失或不唯一：{game_id}/{row['round_no']}")
        end = ends[0]
        data = end["data"]
        next_own_draw = next((event["seq"] for event in timeline
                             if event["seq"] > row["trigger_seq"]
                             and event["type"] == "tile_drawn"
                             and event["seat"] == row["seat"]), None)
        if data.get("draw"):
            outcome = "draw"
        elif end["seat"] == row["seat"]:
            outcome = f"own_fan_{data['fan']}"
        else:
            outcome = "other_win"
        row["actual_outcome"] = {
            "kind": outcome, "end_seq": end["seq"], "fan": data.get("fan"),
            "focal_delta": data["scores"][row["seat"]],
            "next_own_draw_seq": next_own_draw,
            "official_source": str(sources[game_id].relative_to(ROOT)),
        }
        if row["accepted_action"] == "hu" and (
            outcome != "own_fan_1"
            or data["scores"][row["seat"]] != row["immediate_hu_focal_delta"]
        ):
            raise ValueError(f"已提交一番胡与官方结算不一致：{game_id}/{row['round_no']}")


def summarize(rows: list[dict], base_counts: Counter) -> dict:
    """按父代胡／继续、房和一摸条件路线分开汇总。"""

    result = {"base_counts": dict(base_counts), "hu1_rooms": len({r["room_id"] for r in rows}),
              "hu1_games": len({r["game_id"] for r in rows}),
              "hu1_rounds": len({(r["game_id"], r["round_no"]) for r in rows})}
    for group, group_rows in (
        ("parent_hu", [r for r in rows if r["parent_action"] == "hu"]),
        ("parent_continue", [r for r in rows if r["parent_action"] != "hu"]),
    ):
        max_fan = Counter()
        actual = Counter()
        preserved = []
        new_baotou = 0
        chosen_new_baotou = 0
        for row in group_rows:
            alternatives = row["nonwhite_alternatives"]
            maximum = max((route["fan"] for action in alternatives
                           for route in action["routes"] if route["capacity"] > 0), default=0)
            max_fan[maximum] += 1
            if any(action["baotou_after"] is True for action in alternatives):
                new_baotou += 1
            chosen = next((action for action in alternatives
                           if action["action_key"] == row["parent_action"]), None)
            if (chosen is not None and row["current_baotou"] is False
                    and chosen["baotou_after"] is True):
                chosen_new_baotou += 1
            actual[row["actual_outcome"]["kind"]] += 1
            options = [action for action in alternatives
                       if action["coverage"] == "complete"
                       and any(route["fan"] >= 4 and route["capacity"] > 0
                               for route in action["routes"])
                       and any(route["fan"] == 1 and route["capacity"] > 0
                               for route in action["routes"])]
            if options:
                best = min(options, key=lambda action: (
                    -sum(route["capacity"] for route in action["routes"] if route["fan"] >= 4),
                    -sum(route["capacity"] for route in action["routes"] if route["fan"] == 1),
                    action["action_key"],
                ))
                preserved.append({
                    "room_id": row["room_id"], "game_id": row["game_id"],
                    "round_no": row["round_no"], "trigger_seq": row["trigger_seq"],
                    "action_key": best["action_key"],
                    "standard_shanten_after": best["standard_shanten_after"],
                    "seven_pairs_shanten_after": best["seven_pairs_shanten_after"],
                    "baotou_after": best["baotou_after"],
                    "high_fan_capacity": sum(route["capacity"] for route in best["routes"]
                                             if route["fan"] >= 4),
                    "ordinary_fan1_capacity": sum(route["capacity"] for route in best["routes"]
                                                  if route["fan"] == 1),
                    "high_fan_routes": [route for route in best["routes"] if route["fan"] >= 4],
                })
        result[group] = {
            "windows": len(group_rows), "rooms": len({r["room_id"] for r in group_rows}),
            "games": len({r["game_id"] for r in group_rows}),
            "max_one_draw_fan": dict(sorted(max_fan.items())),
            "any_new_baotou": new_baotou,
            "chosen_action_new_baotou": chosen_new_baotou,
            "actual_outcomes": dict(sorted(actual.items())),
            "with_high4_and_ordinary_fan1": len(preserved),
            "with_high4_and_ordinary_fan1_rooms": len({r["room_id"] for r in preserved}),
            "high4_preserving_options": preserved,
        }
    return result


def main() -> None:
    """冻结房间前缀；只读审计和缓存牌谱；输出确定性 JSON。"""

    state = json.loads(STATE.read_text(encoding="utf-8"))
    rooms = state["rooms"][:ROOM_LIMIT]
    if len(rooms) != ROOM_LIMIT or rooms[-1]["room_id"] != LAST_ROOM:
        raise ValueError("watchdog 前 341 房身份与本审计冻结前缀不符")
    room_ids = [room["room_id"] for room in rooms]
    if len(set(room_ids)) != ROOM_LIMIT:
        raise ValueError("房间前缀重复")
    rows, base_counts = extract_rows(rooms)
    attach_actual_outcomes(rows)
    if any(row["parent_action"] != row["accepted_action"] for row in rows):
        raise ValueError("父代首选与已接受动作不一致，需另审拒绝／降级")
    g256 = json.loads(G256.read_text(encoding="utf-8"))
    old = [item for item in g256["all_window_summaries"]
           if item["white_count"] == 3 and item["immediate_fan"] == 1]
    current_keys = {(row["game_id"], row["round_no"], row["trigger_seq"], row["seat"])
                    for row in rows}
    old_keys = {(item["game_id"], item["round_no"], item["draw_seq"], item["seat"])
                for item in old}
    summary = summarize(rows, base_counts)
    summary["g256_three_white_hu1"] = {
        "windows": len(old), "rooms": len({item["room_id"] for item in old}),
        "classes": dict(sorted(Counter(item["class"] for item in old).items())),
        "overlap_exact_windows_with_parent_audit": len(old_keys & current_keys),
        "overlap_rooms_with_parent_audit": len(
            {item["room_id"] for item in old} & {row["room_id"] for row in rows}),
        "room_341_in_g256": LAST_ROOM in {item["room_id"] for item in g256["all_window_summaries"]},
    }
    result = {
        "schema": "g285-three-white-hu-support/1",
        "scope": "watchdog 前 341 房中已完成房的我方正常摸牌审计；官方缓存牌谱只用于已执行动作的终局核验",
        "fixed_room_prefix_count": ROOM_LIMIT,
        "fixed_room_prefix_last": LAST_ROOM,
        "fixed_room_ids_sha256": sha256(json.dumps(room_ids, ensure_ascii=False,
                                             separators=(",", ":")).encode()).hexdigest(),
        "finished_rooms": sum(room.get("terminal_reason") == "tournament_finished" for room in rooms),
        "sources": {
            "watchdog_state": str(STATE.relative_to(ROOT)),
            "audit": "各 room.audit_dir/participants/u_13495c3d79c8/decisions.jsonl",
            "official": "artifacts/sessions/r18-sse-freematch-campaign-20260925b/official/**/events.json",
            "g256": str(G256.relative_to(ROOT)),
        },
        "summary": summary,
        "rows": rows,
        "limits": "一摸条件番与公开未见容量不是墙中概率；官方后续只说明已执行动作的结果，不是未执行动作的反事实收益。",
    }
    json.dump(result, sys.stdout, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
