#!/usr/bin/env python3
"""G203：官方父代多白近听后续正常摸牌资格与先胡截尾。"""

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
import random

from extract_room_scores import load_rooms
import g65_next_draw_survival as g65
import g201_multiwhite_near_ready_select as g201
from hangma_bot.application.audit_codec import observation_from_json
from hangma_bot.hangma.catch_play import analyze_catch_play
from hangma_bot.hangma.engine import _build_context


HERE = Path(__file__).resolve().parent
PLAN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G203-FUTURE-CATCH-PLAY-REACH-PREREG-2026-09-29.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g203-future-catch-play-reach-20260929/result.json')
BOOT_SEED = 20261229203
BOOT_REPS = 10_000


def digest(path: Path) -> str:
    """绑定选择合同及程序原始字节。"""

    return sha256(path.read_bytes()).hexdigest()


def window_mode(raw_observation: dict) -> str:
    """以生产抓打圈解析确认当前本人权限，未知不能填成自由出牌。"""

    observation = observation_from_json(raw_observation)
    circle = analyze_catch_play(observation)
    if circle.issue:
        return "unknown"
    return "restricted" if circle.restricts(observation.seat) else "free"


def source_rows() -> tuple[list[dict], dict[str, dict], set[str]]:
    """只从行动前玩家观察与官方接受表选根，顺序扫描后继权威观察。"""

    frozen = json.loads(g201.g189.atlas.FROZEN.read_text(encoding="utf-8"))
    complete = g201.g189.atlas._complete_ids()
    if len(frozen["rooms"]) != 91 or len(complete) != 909:
        raise ValueError("G203 冻结官方房或完整桌母体漂移")
    roots = []
    room_sources = {}
    seen = set()
    for room in frozen["rooms"]:
        audit = g201.g189.atlas.source.ROOT / room["audit_dir"]
        decisions = audit / "participants" / g201.g189.atlas.source.ACTOR / "decisions.jsonl"
        if decisions.stat().st_size != room["decision_bytes"]:
            raise ValueError("G203 冻结父代接受文件字节数漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("G203 冻结 R18 v2 源码身份漂移")
        accepted = g201.g189.atlas.source._accepted(decisions)
        room_sources[room["room_id"]] = {"audit_dir": room["audit_dir"],
                                         "decision_bytes": room["decision_bytes"]}
        active: dict[tuple, list[dict]] = defaultdict(list)
        last_seq: dict[tuple, int] = {}
        for context, raw, plan in g201.g189.atlas.source.screen._iter_decisions(audit):
            game_id = context.get("game_id")
            if (game_id not in complete
                    or (raw.get("window_key") or {}).get("phase") != "draw"):
                continue
            o = raw["observation"]
            key = (game_id, context.get("round_no"), o.get("seat"))
            seq = context.get("trigger_seq")
            if type(seq) is not int or seq <= last_seq.get(key, -1):
                raise ValueError("G203 同一座位正常摸打序号非严格递增")
            last_seq[key] = seq
            if active[key]:
                mode = window_mode(o)
                for root in active[key]:
                    # 杠补牌可夹在正常摸牌之间；先保留本单局全部权威观察，
                    # 再以官方事件序号选前三次正常摸牌，避免把补牌误占额度。
                    root["future_observations"].append({"seq": seq, "mode": mode,
                                                        "gang_draw": o.get("gang_draw")})
            ranked = sorted(plan.get("candidates") or [],
                            key=lambda item: item.get("rank", 10**9))
            if not ranked:
                continue
            parent = ranked[0].get("action_key")
            # 官方开局已配牌后的首次出牌使用 seq=0，并非摸牌事件。
            if (seq == 0 or o.get("gang_draw") is True
                    or accepted.get(context.get("decision_id")) != parent
                    or not isinstance(parent, str)
                    or not parent.startswith("discard:") or parent == "discard:白"):
                continue
            obs = observation_from_json(o)
            if (obs.phase != "draw" or obs.turn_seat != obs.seat
                    or type(obs.remaining_tile_count) is not int
                    or obs.remaining_tile_count <= 32
                    or len(obs.melds[obs.seat]) != 0
                    or obs.rule_state.catch_play):
                continue
            white = sum(tile.code == "白" for tile in _build_context(obs).full_hand())
            if white < 2:
                continue
            legal = {item["action_key"]: item for item in
                     (raw.get("rules") or {}).get("legal_candidates") or []}
            if parent not in legal:
                raise ValueError("G203 已接受父代弃牌不在合法集合")
            facts = legal[parent].get("facts") or {}
            if type(facts.get("standard_shanten_after")) is not int or facts["standard_shanten_after"] not in (0, 1):
                continue
            identity = (room["room_id"], game_id, context["round_no"], seq, obs.seat)
            if identity in seen:
                raise ValueError("G203 同一父代正常摸打根重复")
            seen.add(identity)
            row = {"room_id": identity[0], "game_id": identity[1],
                   "round_no": identity[2], "trigger_seq": identity[3],
                   "seat": identity[4], "white_before": white,
                   "wall_remaining": obs.remaining_tile_count,
                   "standard_shanten_after": facts["standard_shanten_after"],
                   "parent_action": parent, "g201_like": False,
                   "future_observations": []}
            selected = g201.candidate({"room_id": identity[0], "game_id": game_id,
                                       "round_no": identity[2], "trigger_seq": seq},
                                      raw, ranked, parent)
            if selected is not None:
                row["g201_like"] = True
                row["alternate_action"] = selected["alternate_action"]
            roots.append(row)
            active[key].append(row)
    return roots, room_sources, complete


def official_events(roots: list[dict], complete: set[str]) -> tuple[dict, dict]:
    """只提取目标完整桌官方事件并保存事件投影摘要，不留他家暗手。"""

    needed = {row["game_id"] for row in roots}
    docs = {}
    hashes = {}
    for _mtime, room, _tag, game_id, doc in load_rooms():
        if game_id not in needed:
            continue
        if game_id not in complete or room != game_id.split("_r", 1)[0]:
            raise ValueError("G203 官方场次与冻结完整桌身份矛盾")
        if game_id in docs:
            raise ValueError("G203 官方完整桌去重后仍重复")
        events = g65.event_index(doc)
        docs[game_id] = events
        encoded = json.dumps(events, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8")
        hashes[game_id] = sha256(encoded).hexdigest()
    if set(docs) != needed:
        raise ValueError("G203 本地官方完整桌事件缺失")
    return docs, hashes


def classify(root: dict, events: list[dict]) -> dict:
    """严格核根弃牌后，把三个未来正常摸牌与吸收终点分别计数。"""

    seat, seq = root["seat"], root["trigger_seq"]
    positions = {event["seq"]: index for index, event in enumerate(events)}
    position = positions.get(seq)
    # 官方首巡开局配牌后的出牌可携非零 trigger_seq，但牌谱没有 tile_drawn；
    # 仅凭审计 phase=draw 无法识别，按当前官方事件剔除而不读取后续标签。
    if position is None:
        first = events[0]
        if (first.get("seq") == seq + 1 and first.get("type") == "tile_discarded"
                and first.get("seat") == seat
                and "discard:" + str(first.get("tile")) == root["parent_action"]):
            return {"status": "ineligible_root", "reason": "本单局开局出牌无对应摸牌事件"}
        raise ValueError(f"G203 冻结父代根序号不在官方事件链：{root['game_id']} "
                         f"r{root['round_no']} seq={seq} first={first}")
    if ((events[position].get("type") != "tile_drawn"
         or events[position].get("seat") != seat)):
        raise ValueError(f"G203 根不是官方本人正常摸牌：{root['game_id']} "
                         f"r{root['round_no']} seq={seq} seat={seat} "
                         f"official={events[position] if position is not None else None}")
    if (events[position].get("data") or {}).get("gang_replenish"):
        return {"status": "ineligible_root", "reason": "官方杠后补牌不是正常摸牌"}
    material = next((event for event in events[position + 1:]
                     if event.get("type") not in ("pass", "timeout")), None)
    if (material is None or material.get("type") != "tile_discarded"
            or material.get("seat") != seat
            or "discard:" + str(material.get("tile")) != root["parent_action"]):
        raise ValueError("G203 官方根后首实质弃牌与已接受父代不符")
    discard_seq = material["seq"]
    terminal = [event for event in events if event.get("type") == "round_ended"]
    if len(terminal) != 1 or terminal[0]["seq"] <= discard_seq:
        raise ValueError("G203 根后官方唯一终局缺失")
    end = terminal[0]
    post = [event for event in events if discard_seq < event["seq"] < end["seq"]]
    normal = [event for event in post
              if event.get("type") == "tile_drawn" and event.get("seat") == seat
              and not (event.get("data") or {}).get("gang_replenish")]
    replacement = [event for event in post
                   if event.get("type") == "tile_drawn" and event.get("seat") == seat
                   and (event.get("data") or {}).get("gang_replenish")]
    own_claims = [event for event in post
                  if event.get("seat") == seat and event.get("type") in ("chi", "peng", "gang")]
    available = {entry["seq"]: entry for entry in root["future_observations"]
                 if entry.get("gang_draw") is not True}
    steps = []
    for ordinal in range(1, 4):
        if len(normal) >= ordinal:
            future = normal[ordinal - 1]
            observation = available.get(future["seq"])
            if observation is None:
                return {"status": "unavailable", "reason": "未来正常摸牌缺权威观察",
                        "missing_seq": future["seq"]}
            steps.append({"kind": "reach_" + observation["mode"],
                          "seq": future["seq"],
                          "prior_own_claims": sum(event["seq"] < future["seq"] for event in own_claims),
                          "prior_replacement_draws": sum(event["seq"] < future["seq"] for event in replacement)})
        elif (end.get("data") or {}).get("draw"):
            steps.append({"kind": "wall_draw_before", "seq": end["seq"]})
        elif end.get("seat") == seat:
            steps.append({"kind": "own_win_before", "seq": end["seq"]})
        else:
            steps.append({"kind": "other_win_before", "seq": end["seq"]})
    return {"status": "complete", "root_discard_seq": discard_seq,
            "terminal_kind": ("wall_draw" if (end.get("data") or {}).get("draw") else
                              "own_win" if end.get("seat") == seat else "other_win"),
            "terminal_seq": end["seq"],
            "own_claim_count": len(own_claims),
            "replacement_draw_count": len(replacement),
            "steps": steps}


def rate_interval(rows: list[dict], predicate, denominator) -> dict:
    """以房为聚类单位重采样公开时序比例，不把相关窗作独立根。"""

    by_room = defaultdict(list)
    for row in rows:
        by_room[row["room_id"]].append(row)
    rooms = sorted(by_room)
    if not rooms:
        return {"numerator": 0, "denominator": 0, "rate": None, "room_bootstrap_95": None}
    numerator = sum(predicate(row) for row in rows)
    total = sum(denominator(row) for row in rows)
    if total == 0:
        return {"numerator": numerator, "denominator": 0, "rate": None,
                "room_bootstrap_95": None}
    room_parts = [(sum(predicate(row) for row in by_room[room]),
                   sum(denominator(row) for row in by_room[room])) for room in rooms]
    rng = random.Random(BOOT_SEED + len(rows) + total)
    sampled = []
    for _ in range(BOOT_REPS):
        pairs = [room_parts[rng.randrange(len(rooms))] for _ in rooms]
        den = sum(value[1] for value in pairs)
        if den:
            sampled.append(sum(value[0] for value in pairs) / den)
    sampled.sort()
    return {"numerator": numerator, "denominator": total,
            "rate": numerator / total,
            "room_bootstrap_95": [sampled[int(0.025 * len(sampled))],
                                  sampled[int(0.975 * len(sampled)) - 1]] if sampled else None}


def summary(rows: list[dict]) -> dict:
    """三次本人正常摸牌的互斥分区及受限条件率。"""

    eligible = [row for row in rows if row["outcome"]["status"] != "ineligible_root"]
    complete = [row for row in eligible if row["outcome"]["status"] == "complete"]
    result = {"screened_roots": len(rows), "ineligible_roots": len(rows) - len(eligible),
              "roots": len(eligible), "complete": len(complete),
              "unavailable": len(eligible) - len(complete),
              "rooms": len({row["room_id"] for row in complete}),
              "own_claim_roots": sum(row["outcome"]["own_claim_count"] > 0
                                     for row in complete),
              "replacement_roots": sum(row["outcome"]["replacement_draw_count"] > 0
                                       for row in complete),
              "steps": {}}
    for index in range(3):
        counts = Counter(row["outcome"]["steps"][index]["kind"] for row in complete)
        if sum(counts.values()) != len(complete):
            raise ValueError("G203 未来摸牌互斥分区不守恒")
        reached = lambda row, i=index: row["outcome"]["steps"][i]["kind"].startswith("reach_")
        restricted = lambda row, i=index: row["outcome"]["steps"][i]["kind"] == "reach_restricted"
        result["steps"][str(index + 1)] = {
            "counts": dict(sorted(counts.items())),
            "restricted_among_reached": rate_interval(complete, restricted, reached)}
    reached_any = lambda row: row["outcome"]["steps"][0]["kind"].startswith("reach_")
    all_free = lambda row: (reached_any(row)
                           and all(step["kind"] == "reach_free"
                                   for step in row["outcome"]["steps"]
                                   if step["kind"].startswith("reach_")))
    result["all_reached_first_three_free"] = rate_interval(complete, all_free, reached_any)
    result["other_win_before_third"] = rate_interval(
        complete,
        lambda row: row["outcome"]["steps"][2]["kind"] == "other_win_before",
        lambda row: True)
    return result


def main() -> None:
    """结果盲根选择后才读官方未来事件；输出保留全部缺证原因。"""

    if OUT.exists():
        raise FileExistsError("G203 结果已存在，拒绝覆盖")
    roots, room_sources, complete = source_rows()
    if not roots:
        raise ValueError("G203 多白近听父代窗口无覆盖")
    gold = json.loads(g201.OUT.read_text(encoding="utf-8"))
    gold_keys = {(row["room_id"], row["game_id"], row["round_no"],
                  row["trigger_seq"], row["seat"]) for row in gold["selected"]}
    roots_by_key = {(row["room_id"], row["game_id"], row["round_no"],
                     row["trigger_seq"], row["seat"]): row for row in roots}
    if any(key not in roots_by_key or not roots_by_key[key]["g201_like"] for key in gold_keys):
        raise ValueError("G203 八窗金例不在主层")
    docs, game_hashes = official_events(roots, complete)
    for index, root in enumerate(roots, 1):
        events = docs[root["game_id"]][root["round_no"]]
        root["outcome"] = classify(root, events)
        del root["future_observations"]
        if index % 500 == 0:
            print(json.dumps({"roots_labeled": index, "total": len(roots)}), flush=True)
    main_rows = [row for row in roots if row["g201_like"]]
    main_summary, all_summary = summary(main_rows), summary(roots)
    gate = (main_summary["complete"] >= 20 and main_summary["rooms"] >= 10)
    for stats in (main_summary, all_summary):
        for item in stats["steps"].values():
            value = item["restricted_among_reached"]
            if (value["rate"] is None or value["room_bootstrap_95"] is None
                    or value["rate"] > 0.10 or value["room_bootstrap_95"][1] > 0.20):
                gate = False
    payload = {
        "schema": "g203-future-catch-play-reach/1",
        "source_sha256": {"plan": digest(PLAN), "script": digest(Path(__file__)),
                          "frozen_rooms": digest(g201.g189.atlas.FROZEN),
                          "g201_selection": digest(g201.OUT),
                          "g65_script": digest(Path(g65.__file__))},
        "source_rooms": room_sources,
        "official_event_sha256_by_game": game_hashes,
        "main_summary": main_summary, "all_near_summary": all_summary,
        "unrestricted_relevance_gate": gate,
        "gold_eight_status": {"found": len(gold_keys),
                              "complete": sum(roots_by_key[key]["outcome"]["status"] == "complete"
                                              for key in gold_keys)},
        "rows": roots,
        "boundary": "官方父代已执行动作的赛后时序标签；不含备选反事实抓打圈、墙后验或策略收益。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                              indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"main": main_summary, "all_near": all_summary,
                      "gate": gate}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
