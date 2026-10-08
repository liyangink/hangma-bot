#!/usr/bin/env python3
"""G16 冻结父代持白弃牌后的本人摸牌续行暴露，不读取结算。"""

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

import g11_cross_family_action_atlas as atlas


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g16-white-continuation-exposure-20260927/result.json')


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _wall_bin(value: object) -> str:
    """剩余墙张数是官方动作前观察中的张数；异常值单独留痕。"""

    if type(value) is not int or value < 0:
        return "unknown"
    if value < 40:
        return "lt40"
    if value < 60:
        return "40to59"
    return "ge60"


def main() -> None:
    """只读已核完整桌的父代动作；输出母体及后续本人摸牌计数。"""

    if OUT.exists():
        raise SystemExit("G16 输出已存在，拒绝覆盖")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    complete_ids = atlas._complete_ids()
    if len(complete_ids) != 909 or len(frozen["rooms"]) != 91:
        raise ValueError("G16 冻结完整桌母体漂移")
    by_round: dict[tuple[str, int, int], list[dict]] = defaultdict(list)
    counts = Counter()
    for room in frozen["rooms"]:
        audit = atlas.source.ROOT / room["audit_dir"]
        decisions = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decisions.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结房决策文件字节数漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("冻结房父代源码摘要漂移")
        accepted = atlas.source._accepted(decisions)
        for context, raw, plan in atlas.source.screen._iter_decisions(audit):
            game_id = context.get("game_id")
            if (game_id not in complete_ids or
                    (raw.get("window_key") or {}).get("phase") != "draw"):
                continue
            ranked = sorted(plan.get("candidates") or [],
                            key=lambda item: item.get("rank", 10**9))
            if not ranked or not isinstance(ranked[0].get("action_key"), str):
                counts["unranked_draw"] += 1
                continue
            action = ranked[0]["action_key"]
            if accepted.get(context.get("decision_id")) != action:
                counts["draw_parent_not_accepted"] += 1
                continue
            observation = raw.get("observation") or {}
            seat, melds = observation.get("seat"), observation.get("melds")
            hand, drawn = observation.get("my_hand"), observation.get("drawn_tile")
            seq, round_no = context.get("trigger_seq"), context.get("round_no")
            if (type(seat) is not int or type(seq) is not int or type(round_no) is not int
                    or not isinstance(melds, list) or not 0 <= seat < len(melds)
                    or not isinstance(melds[seat], list)):
                counts["draw_identity_unknown"] += 1
                continue
            hand_valid = (isinstance(hand, list)
                          and all(isinstance(tile, str) for tile in hand)
                          and len(hand) == 14 - 3 * len(melds[seat]))
            if not hand_valid:
                counts["draw_hand_unknown_" + action.split(":", 1)[0]] += 1
                continue
            drawn_valid = (hand_valid and isinstance(drawn, str) and drawn in hand)
            if not drawn_valid:
                counts["draw_without_physical_drawn_tile_" + action.split(":", 1)[0]] += 1
                continue
            if action.startswith("discard:") and action.split(":", 1)[1] not in hand:
                raise ValueError("已接受弃牌不在本人暗手")
            white_before_draw = hand.count("白") - (drawn == "白")
            event = {"seq": seq, "action": action,
                     "white_before_draw": white_before_draw,
                     "white_after_discard": (hand.count("白") - (action == "discard:白")
                                             if action.startswith("discard:") else None),
                     "baotou_before": (observation.get("rule_state") or {}).get("baotou") is True,
                     "wall_bin": _wall_bin(observation.get("remaining_tile_count"))}
            by_round[(game_id, round_no, seat)].append(event)
            counts["accepted_draw"] += 1

    totals = Counter()
    tables: dict[str, set[str]] = defaultdict(set)
    by_white: dict[str, Counter] = defaultdict(Counter)
    by_wall: dict[str, Counter] = defaultdict(Counter)
    for (game_id, _, _), events in by_round.items():
        events.sort(key=lambda event: event["seq"])
        if len({event["seq"] for event in events}) != len(events):
            raise ValueError("同一桌单局座位的摸牌事件序号重复")
        for index, event in enumerate(events):
            held = event["white_after_discard"]
            if not event["action"].startswith("discard:") or held is None or held < 1:
                continue
            totals["parent_keeps_white"] += 1
            tables["parent_keeps_white"].add(game_id)
            white_counts = by_white[str(held)]
            wall_counts = by_wall[event["wall_bin"]]
            for row in (white_counts, wall_counts):
                row["parent_keeps_white"] += 1
            for distance, label in ((1, "next"), (2, "second")):
                if index + distance >= len(events):
                    continue
                following = events[index + distance]
                totals[label + "_own_draw"] += 1
                tables[label + "_own_draw"].add(game_id)
                for row in (white_counts, wall_counts):
                    row[label + "_own_draw"] += 1
                if following["white_before_draw"] >= 1:
                    totals[label + "_still_holds_white_before_draw"] += 1
                    for row in (white_counts, wall_counts):
                        row[label + "_still_holds_white_before_draw"] += 1
                if following["baotou_before"]:
                    totals[label + "_baotou_before_draw"] += 1
                if following["action"].startswith("hu:") or following["action"] == "hu":
                    totals[label + "_accepted_hu"] += 1
    if totals["parent_keeps_white"] != 23_165:
        raise ValueError(f"G16 持白父代母体 {totals['parent_keeps_white']} 与 G14 的 23,165 窗不符；扫描 {dict(counts)}")
    result = {"schema": "g16-white-continuation-exposure/1",
              "observational_parent_path": True,
              "analysis_script_sha256": _sha(Path(__file__)),
              "source_frozen_rooms_sha256": _sha(atlas.FROZEN),
              "source_complete_ids_sha256": _sha(atlas.TRAIN_ROWS),
              "parent_source_sha256": frozen["parent_source_sha256"],
              "official_rooms": len(frozen["rooms"]),
              "complete_official_tables": len(complete_ids),
              "scan_counts": dict(sorted(counts.items())),
              "totals": dict(sorted(totals.items())),
              "table_coverage": {name: len(ids) for name, ids in sorted(tables.items())},
              "by_white_after_discard": {key: dict(sorted(value.items()))
                                         for key, value in sorted(by_white.items())},
              "by_wall_remaining": {key: dict(sorted(value.items()))
                                    for key, value in sorted(by_wall.items())},
              "boundary": "冻结父代实际后续本人摸牌仅检验暴露，不是改选反事实或收益概率；未出现后续窗口的原因不在本项判定。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"totals": result["totals"], "table_coverage": result["table_coverage"],
                      "by_white_after_discard": result["by_white_after_discard"]},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
