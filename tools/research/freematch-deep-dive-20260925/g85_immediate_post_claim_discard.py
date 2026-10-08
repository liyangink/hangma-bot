#!/usr/bin/env python3
"""G85：用官方紧接的弃牌核对独有强手鸣牌后的规则分支。"""

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
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, HERE.parents[0] / "baotou-anatomy-20260925")))

import anatomy_lib as anatomy
import c31_action_layer_gap as c31
import g76_confirmed_response_atlas as g76
from extract_room_scores import load_rooms


SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g76-confirmed-response-atlas-20260928/rows.jsonl.gz')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G85-IMMEDIATE-POST-CLAIM-DISCARD-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g85-immediate-post-claim-discard-20260928/result.json')
SOURCE_SHA = "2a26d239e79ce863311b4be2681a86a9d7d94b50648ab4f4a5355f6d3cd08fc6"


def sha(path: Path) -> str:
    """记录不可变发现集及执行源码摘要。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def official_followup(events: list[dict], discard_seq: int, seat: int,
                      accepted_key: str) -> tuple[str | None, str]:
    """只认紧接已接受吃碰的本人弃牌；事件间有其他动作即删失。"""
    anchors = [i for i, event in enumerate(events) if event.get("seq") == discard_seq]
    if len(anchors) != 1 or events[anchors[0]].get("type") != "tile_discarded":
        raise ValueError("物理弃牌序号丢失或非唯一")
    claim_index = None
    for i in range(anchors[0] + 1, len(events)):
        event = events[i]
        if event.get("type") in ("pass", "timeout"):
            continue
        if event.get("type") in ("chi", "peng"):
            claim_index = i
        break
    if claim_index is None:
        return None, "no_immediate_claim"
    claim = events[claim_index]
    if claim.get("seat") != seat or g76.action_key(claim) != accepted_key:
        raise ValueError("已接受鸣牌与 G76 目标不符")
    if claim_index + 1 >= len(events):
        return None, "no_following_event"
    following = events[claim_index + 1]
    if following.get("type") != "tile_discarded" or following.get("seat") != seat:
        return None, "not_immediate_own_discard"
    tile = following.get("tile")
    if tile not in c31.TILE_ORDER:
        raise ValueError("即时弃牌不在规范牌码表")
    return tile, "matched"


def support(tiles) -> tuple[int | None, int | None]:
    """返回有效牌码数和公开未见张容量；缺计数时保持未知。"""
    if tiles is None:
        return None, None
    rows = list(tiles)
    if any(type(item.remaining_estimate) is not int for item in rows):
        return None, None
    return sum(item.remaining_estimate > 0 for item in rows), sum(
        item.remaining_estimate for item in rows)


def facts_summary(candidate) -> dict:
    """读取生产规则事实，不重算普通型或有效牌算法。"""
    facts = candidate.facts
    if facts is None:
        return {"known": False}
    codes, capacity = support(facts.useful_tiles)
    standard_codes, standard_capacity = support(facts.standard_useful_tiles)
    return {"known": facts.completeness.value == "complete",
            "combined_shanten": facts.shanten_after,
            "standard_shanten": facts.standard_shanten_after,
            "codes": codes, "capacity": capacity,
            "standard_codes": standard_codes,
            "standard_capacity": standard_capacity}


def main() -> None:
    """对 88 个冻结独有鸣牌逐窗复算并写不可覆盖的发现集结果。"""
    if OUT.exists():
        raise SystemExit("G85 证据已存在，拒绝覆盖")
    if sha(SOURCE) != SOURCE_SHA:
        raise ValueError("G76 输入摘要漂移")
    source = [json.loads(line) for line in gzip.open(SOURCE, "rt", encoding="utf-8")]
    targets = {(row["game_id"], row["round_no"], row["discard_seq"], row["seat"],
                row["phase"]): row for row in source
               if row["actor"] == "peer" and row["actual"] == "claim" and
                  row["parent_key"] == "pass" and row["r6_key"] == "pass"}
    if len(targets) != 88:
        raise ValueError("独有鸣牌母体数漂移")
    by_round = defaultdict(list)
    for key, row in targets.items():
        by_round[key[:2]].append((key, row))
    parent = c31.load_parent()
    found = set()
    rows = []
    for _, room, _, game_id, doc in load_rooms():
        if game_id not in {key[0] for key in targets}:
            continue
        scores = [0, 0, 0, 0]
        metadata = c31.round_metadata(doc)
        for round_no, events, start_hands in anatomy.round_blocks(doc):
            group = by_round.get((game_id, round_no), ())
            if group:
                dealer = metadata[round_no]["dealer"]
                snaps = c31.reconstruct(events, start_hands, scores, dealer)
                for key, target in group:
                    if target["room"] != room:
                        raise ValueError("G76 房间与官方场次不符")
                    actual_tile, match_status = official_followup(
                        events, key[2], key[3], target["accepted_key"])
                    snap = snaps[key[2]]
                    window, _, _ = c31.evaluate_window(
                        snap, key[3], [key[4]], game_id, round_no, parent)
                    if window is None or window["degraded"] or window["margin"] != target["parent_margin"]:
                        raise ValueError("G76 目标规则事实或父代分差漂移")
                    accepted = {item["action_key"]: item for item in window["view"]["actions"]}.get(
                        target["accepted_key"])
                    if accepted is None:
                        raise ValueError("已接受鸣牌不在合法动作表")
                    branches = accepted.get("followup_branches")
                    if branches is None:
                        raise ValueError("已接受吃碰无合法跟打分支载荷")
                    legal_tiles = {item["followup_discard"] for item in branches}
                    best = accepted.get("best_followup_discard")
                    if best not in legal_tiles:
                        raise ValueError("最佳跟打不在合法分支")
                    if actual_tile is not None and actual_tile not in legal_tiles:
                        raise ValueError("官方即时跟打不在生产合法分支")
                    claim_rule = next((candidate for candidate in window["analysis"].legal_candidates
                                       if candidate.action_key == target["accepted_key"]), None)
                    if claim_rule is None:
                        raise ValueError("鸣牌规则动作不可解析")
                    post = c31.post_claim_observation(window["observation"], claim_rule.action)
                    if post is None:
                        raise ValueError("鸣后公开观察构造失败")
                    post_analysis = c31.RULES.analyze(post)
                    post_discards = {candidate.action_key.removeprefix("discard:"): candidate
                                     for candidate in post_analysis.legal_candidates
                                     if candidate.action_key.startswith("discard:")}
                    if set(post_discards) != legal_tiles:
                        raise ValueError("鸣后弃牌全集与前置规则分支不一致")
                    best_facts = facts_summary(post_discards[best])
                    actual_facts = (facts_summary(post_discards[actual_tile])
                                    if actual_tile is not None else None)
                    rows.append({"peer": target["peer"], "room": room,
                                 "game_id": game_id, "round_no": round_no,
                                 "discard_seq": key[2], "seat": key[3], "phase": key[4],
                                 "accepted_key": target["accepted_key"],
                                 "followup_status": match_status,
                                 "actual_followup": actual_tile,
                                 "parent_best_followup": best,
                                 "legal_followup_count": len(legal_tiles),
                                 "best_facts": best_facts,
                                 "actual_facts": actual_facts})
                    found.add(key)
            ended = next(event for event in events if event.get("type") == "round_ended")
            scores = [a + b for a, b in zip(scores, ended["data"]["scores"])]
    if found != set(targets):
        raise ValueError("G76 目标未全部重建")
    summaries = {}
    for peer in ("xuanwu_2346", "tengshe_0638"):
        selected = [row for row in rows if row["peer"] == peer]
        counts = Counter()
        by_room: dict[str, Counter] = defaultdict(Counter)
        for row in selected:
            local = Counter()
            local["targets"] = 1
            if row["followup_status"] != "matched":
                local["censored:" + row["followup_status"]] = 1
            else:
                local["matched"] = 1
                same = row["actual_followup"] == row["parent_best_followup"]
                local["same_as_best" if same else "different_from_best"] = 1
                local["actual_discards_white"] = row["actual_followup"] == c31.WEALTH
                if not same:
                    left, right = row["best_facts"], row["actual_facts"]
                    if not left["known"] or not right["known"]:
                        local["incomplete_facts"] = 1
                    else:
                        for field in ("combined_shanten", "standard_shanten", "codes",
                                      "capacity", "standard_codes", "standard_capacity"):
                            a, b = left[field], right[field]
                            local[field + ":unknown" if a is None or b is None else
                                  field + (":more" if b > a else ":less" if b < a else ":same")] += 1
                        if (left["standard_shanten"] is not None and
                                right["standard_shanten"] is not None and
                                right["standard_shanten"] <= left["standard_shanten"]):
                            local["ordinary_shanten_protected"] = 1
                            if (right["standard_codes"] is not None and
                                    left["standard_codes"] is not None and
                                    right["standard_codes"] > left["standard_codes"] and
                                    right["standard_capacity"] is not None and
                                    left["standard_capacity"] is not None and
                                    right["standard_capacity"] <= left["standard_capacity"]):
                                local["ordinary_more_codes_capacity_not_more"] = 1
            counts.update(local)
            by_room[row["room"]].update(local)
        summaries[peer] = {"counts": dict(sorted(counts.items())),
                           "rooms": {room: dict(sorted(value.items()))
                                     for room, value in sorted(by_room.items())},
                           "rooms_with_different_followup": sum(
                               value["different_from_best"] > 0 for value in by_room.values()),
                           "rooms_with_tradeoff": sum(
                               value["ordinary_more_codes_capacity_not_more"] > 0
                               for value in by_room.values())}
    OUT.parent.mkdir(parents=True)
    result = {"schema": "g85-immediate-post-claim-discard/1", "exploratory": True,
              "outcome_labels_opened": False,
              "source_sha256": {"g76_rows": sha(SOURCE), "prereg": sha(PREREG),
                                "script": sha(Path(__file__))},
              "summaries": summaries,
              "rows": sorted(rows, key=lambda row: (row["peer"], row["room"], row["game_id"],
                                                  row["round_no"], row["discard_seq"])),
              "boundary": "已接受强手动作是发现集行为，不是价值或收益真值。"}
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(summaries, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
