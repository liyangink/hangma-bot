#!/usr/bin/env python3
"""仅用依法可见规则事实筛查留一财神浮牌的爆头距离改选入口。"""

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
import math
from pathlib import Path

from hangma_bot.hangma import hand_analysis
from hangma_bot.hangma._standard import need as standard_need
from hangma_bot.hangma.internal_types import counts_from_tiles
from hangma_bot.kernel.actions import Tile

import g8_public_response_training_rows as source


HERE = Path(__file__).resolve().parent
FROZEN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-two-white-next-draw-20260927/frozen_rooms.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g9-floating-white-distance-screen-20260927/result.json')


def _capacity(facts: dict, name: str) -> int | None:
    """公开有效张缺失保留未知，不能用空列表或零补上。"""
    raw = facts.get(name)
    if not isinstance(raw, list):
        return None
    values = [item.get("remaining_estimate") for item in raw]
    if any(type(value) is not int or not 0 <= value <= 4 for value in values):
        return None
    return sum(values)


def _distance(after_hand: Counter, meld_count: int) -> tuple[int, int | None, int]:
    """固定留一白后的普通面子与七对结构缺数；仅为离线研究代理。"""
    counts = counts_from_tiles(tuple(Tile(code) for code, amount in after_hand.items()
                                     for _ in range(amount)))
    whites = counts[33]
    if whites < 1:
        raise ValueError("浮牌距离要求至少保留一张白板")
    standard = standard_need(counts[:33], whites - 1, 4 - meld_count, False)
    seven = None if meld_count else 6 - min(6, hand_analysis._chiitoi_pairs(counts[:33], whites - 1))
    return standard, seven, min(standard, seven) if seven is not None else standard


def _same_or_better(a: dict, b: dict) -> bool:
    """先保护父代综合向听与即时有效容量，再比较浮牌结构。"""
    if (type(a.get("shanten_after")) is not int or
            type(b.get("shanten_after")) is not int or
            a["shanten_after"] != b["shanten_after"]):
        return False
    for name in ("standard_shanten_after", "seven_pairs_shanten_after"):
        av, bv = a.get(name), b.get(name)
        if av is None and bv is None:
            continue
        if type(av) is not int or type(bv) is not int or bv > av:
            return False
    a_support = _capacity(a, "useful_tiles")
    b_support = _capacity(b, "useful_tiles")
    return a_support is not None and b_support is not None and b_support >= a_support


def main() -> None:
    """冻结窗口选择和排除计数；没有任何赛后收益字段。"""
    if OUT.exists():
        raise SystemExit("浮牌距离筛查结果已存在，拒绝覆盖")
    frozen_bytes = FROZEN.read_bytes()
    frozen = json.loads(frozen_bytes)
    totals = Counter()
    by_room = {}
    selected_rows = []
    examples = []
    for room in frozen["rooms"]:
        room_id = room["room_id"]
        audit = source.ROOT / room["audit_dir"]
        decision_file = audit / "participants" / source.ACTOR / "decisions.jsonl"
        if decision_file.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结房动作审计字节数漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("冻结父代源码身份漂移")
        accepted = source._accepted(decision_file)
        seen = set()
        counts = Counter()
        for context, request, plan in source.screen._iter_decisions(audit):
            observation = request.get("observation") or {}
            if observation.get("phase") != "draw":
                continue
            key = (context["game_id"], context["round_no"], context["trigger_seq"])
            if key in seen:
                raise ValueError("同一摸牌动作窗口重复")
            seen.add(key)
            planned = plan.get("candidates") or []
            if not planned or not str(planned[0].get("action_key", "")).startswith("discard:"):
                continue
            chosen = planned[0]["action_key"]
            if chosen == "discard:白":
                continue
            counts["parent_nonwhite_discard_draw"] += 1
            if accepted.get(context["decision_id"]) != chosen:
                counts["parent_not_accepted"] += 1
                continue
            hand = list(observation.get("my_hand") or [])
            drawn = observation.get("drawn_tile")
            seat = observation.get("seat")
            melds = observation.get("melds")
            if drawn is not None and len(hand) % 3 == 1:
                hand.append(drawn)
            if hand.count("白") < 1 or type(seat) is not int or not 0 <= seat < 4 or not isinstance(melds, list) or len(melds) != 4:
                counts["not_eligible_hand"] += 1
                continue
            meld_count = len(melds[seat])
            if len(hand) != 14 - 3 * meld_count:
                counts["hand_length_mismatch"] += 1
                continue
            legal = {action.get("action_key"): action.get("facts")
                     for action in (request.get("rules") or {}).get("legal_candidates") or []
                     if isinstance(action.get("facts"), dict)}
            a = legal.get(chosen)
            if a is None:
                counts["parent_facts_missing"] += 1
                continue
            scores = {entry.get("action_key"): entry.get("total_score") for entry in planned}
            hand_counter = Counter(hand)
            distances = {}
            for action_key, facts in legal.items():
                if not isinstance(action_key, str) or not action_key.startswith("discard:") or action_key == "discard:白":
                    continue
                tile = action_key[8:]
                if hand_counter[tile] < 1:
                    raise ValueError("合法弃牌不存在于本人手牌")
                after = hand_counter.copy()
                after[tile] -= 1
                after += Counter()
                distances[action_key] = _distance(after, meld_count)
                if distances[action_key][2] == 0 and facts.get("baotou_after") is False:
                    counts["zero_distance_rule_denies_baotou"] += 1
            if chosen not in distances:
                counts["parent_distance_missing"] += 1
                continue
            counts["eligible_with_white"] += 1
            best = []
            for action_key, b in legal.items():
                if action_key == chosen or action_key not in distances or not _same_or_better(a, b):
                    continue
                if distances[action_key][2] >= distances[chosen][2]:
                    continue
                score = scores.get(action_key)
                if type(score) not in (int, float) or not math.isfinite(score):
                    continue
                best.append((distances[action_key][2], -float(score), action_key))
            if not best:
                continue
            _distance_best, _score_neg, alternate = min(best)
            b = legal[alternate]
            a_support = [_capacity(a, name) for name in ("useful_tiles", "standard_useful_tiles", "seven_pairs_useful_tiles")]
            b_support = [_capacity(b, name) for name in ("useful_tiles", "standard_useful_tiles", "seven_pairs_useful_tiles")]
            novel = a_support == b_support and all(a.get(name) == b.get(name) for name in (
                "standard_shanten_after", "seven_pairs_shanten_after"))
            g6_like = (chosen[8:] not in "东南西北中发白" and alternate[8:] in "东南西北中发" and
                       a_support[1] is not None and b_support[1] is not None and b_support[1] > a_support[1] and
                       a_support[2] is not None and b_support[2] is not None and b_support[2] >= a_support[2])
            score_a = scores.get(chosen)
            score_b = scores.get(alternate)
            row = {"room_id": room_id, "game_id": key[0], "round_no": key[1],
                   "trigger_seq": key[2], "white_count": hand.count("白"),
                   "parent_action": chosen, "alternate_action": alternate,
                   "parent_distance": distances[chosen], "alternate_distance": distances[alternate],
                   "parent_score": score_a, "alternate_score": score_b,
                   "support_a": a_support, "support_b": b_support,
                   "novel_same_immediate_facts": novel, "g6_like": g6_like}
            selected_rows.append(row)
            counts["distance_improvement_windows"] += 1
            if novel:
                counts["novel_same_immediate_facts"] += 1
            if g6_like:
                counts["g6_like"] += 1
            if len(examples) < 20:
                examples.append(row)
        totals.update(counts)
        by_room[room_id] = dict(sorted(counts.items()))
    if totals["zero_distance_rule_denies_baotou"]:
        raise ValueError("浮牌距离为零却与规则爆头事实不符，先复核数学语义")
    novel = [row for row in selected_rows if row["novel_same_immediate_facts"]]
    result = {"schema": "g9-floating-white-distance-screen/1",
              "source_frozen_rooms_sha256": hashlib.sha256(frozen_bytes).hexdigest(),
              "source_parent_sha256": frozen["parent_source_sha256"],
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "prereg_sha256": hashlib.sha256((_project_file(_PROJECT_ROOT, HERE / "G9-FLOATING-WHITE-DISTANCE-PREREG-2026-09-27.md")).read_bytes()).hexdigest(),
              "totals": dict(sorted(totals.items())), "by_room": by_room,
              "distance_improvement": {"windows": len(selected_rows),
                                       "rooms": len({row["room_id"] for row in selected_rows}),
                                       "complete_table_ids": len({row["game_id"] for row in selected_rows})},
              "novel_same_immediate_facts": {"windows": len(novel),
                                             "rooms": len({row["room_id"] for row in novel}),
                                             "complete_table_ids": len({row["game_id"] for row in novel})},
              "by_white_count": dict(sorted(Counter(str(row["white_count"]) for row in selected_rows).items())),
              "parent_score_gap_to_alternate": dict(sorted(Counter(
                  "0" if row["parent_score"] == row["alternate_score"] else
                  "le10" if isinstance(row["parent_score"], (int, float)) and
                  row["parent_score"] - row["alternate_score"] <= 10 else "gt10"
                  for row in selected_rows).items())),
              "examples_first_20": examples,
              "novel_exposure_gate_passed": len(novel) >= 100 and
                  len({row["room_id"] for row in novel}) >= 30 and
                  len({row["game_id"] for row in novel}) >= 100,
              "boundary": "仅结果盲动作入口；距离是限定浮牌构造代理，不代表收益"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ("by_room", "examples_first_20")},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
