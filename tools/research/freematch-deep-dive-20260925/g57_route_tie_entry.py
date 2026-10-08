#!/usr/bin/env python3
"""G57：连续持白摸打进入普通型／七对型持平时的合法动作入口。"""

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
import g11_longitudinal_route_audit as longitudinal
import g56_route_switch_reach as g56


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g57-route-tie-entry-20260927/result.json')
LAYERS = ("tie_entry", "old_route_legal", "combined_safe", "capacity_safe",
          "white_safe", "baotou_safe", "near_score", "novel_near_score")


def sha(path: Path) -> str:
    """返回冻结来源和程序字节摘要。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """仅用上一已执行弃牌确认历史与当前依法可见生产事实。"""

    if OUT.exists():
        raise SystemExit("G57 结果已存在，拒绝覆盖")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    complete_ids = atlas._complete_ids()
    g10, g11, g49 = g56._old_actions()
    rows, source_counts = longitudinal._draw_rows(complete_ids, frozen)
    by_round: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        by_round[(row["game_id"], row["round_no"], row["seat"])].append(row)

    counts = Counter()
    scopes = {layer: {"windows": set(), "tables": set(), "rooms": set()}
              for layer in LAYERS}
    directions: dict[str, Counter] = defaultdict(Counter)
    details = []
    seen = set()
    for sequence in by_round.values():
        sequence.sort(key=lambda item: item["trigger_seq"])
        for prior, current in zip(sequence, sequence[1:]):
            counts["consecutive_normal_draw_pairs"] += 1
            if prior["own_melds"] != current["own_melds"] or prior["after"] != current["before"]:
                continue
            counts["matched_pairs"] += 1
            if prior["own_melds"] != 0:
                continue
            counts["matched_no_meld"] += 1
            if prior["after"]["白"] < 1 or current["white_count"] < 1:
                continue
            counts["continuous_white"] += 1
            previous_lead = g56.lead(prior["standard"], prior["seven_pairs"])
            if previous_lead is None or current["standard"] is None or current["seven_pairs"] is None:
                continue
            if current["standard"] != current["seven_pairs"]:
                continue
            key = current["game_id"], current["round_no"], current["trigger_seq"]
            if key in seen:
                raise ValueError("持白路线持平入口重复")
            seen.add(key)
            direction = previous_lead + "_to_tie"
            parent = current["parent_action"]
            parent_facts = current["legal"][parent]
            parent_capacity = atlas._capacity(parent_facts, "useful_tiles")
            parent_white_after = current["white_count"] - (parent == "discard:白")
            parent_baotou = parent_facts.get("baotou_after")
            parent_score = current["scores"].get(parent)
            if type(parent_score) not in (int, float):
                raise ValueError("已接受父代评分缺失")
            old = {"g10": g10.get(key), "g11": g11.get(key), "g49": g49.get(key)}
            options = []
            for action, facts in current["legal"].items():
                if not action.startswith("discard:") or action == parent:
                    continue
                standard = atlas._int(facts, "standard_shanten_after")
                seven = atlas._int(facts, "seven_pairs_shanten_after")
                if g56.lead(standard, seven) != previous_lead:
                    continue
                combined = atlas._int(facts, "shanten_after")
                capacity = atlas._capacity(facts, "useful_tiles")
                score = current["scores"].get(action)
                gap = float(parent_score) - float(score) if type(score) in (int, float) else None
                alt_baotou = facts.get("baotou_after")
                combined_safe = combined is not None and combined <= current["combined"]
                capacity_safe = (combined_safe and parent_capacity is not None
                                 and capacity is not None and capacity >= parent_capacity)
                white_safe = (capacity_safe and current["white_count"]
                              - (action == "discard:白") >= parent_white_after)
                baotou_safe = (white_safe and type(parent_baotou) is bool
                               and type(alt_baotou) is bool
                               and (not parent_baotou or alt_baotou))
                options.append({
                    "action": action, "standard": standard, "seven": seven,
                    "combined": combined, "combined_capacity": capacity,
                    "white_after": current["white_count"] - (action == "discard:白"),
                    "baotou_after": alt_baotou, "score_gap": gap,
                    "combined_safe": combined_safe, "capacity_safe": capacity_safe,
                    "white_safe": white_safe, "baotou_safe": baotou_safe,
                    "same_old": [name for name, old_action in old.items()
                                 if action == old_action],
                })
            options.sort(key=lambda item: (item["score_gap"] is None,
                                           item["score_gap"] if item["score_gap"] is not None else 0,
                                           item["action"]))
            flags = {
                "tie_entry": True,
                "old_route_legal": bool(options),
                "combined_safe": any(item["combined_safe"] for item in options),
                "capacity_safe": any(item["capacity_safe"] for item in options),
                "white_safe": any(item["white_safe"] for item in options),
                "baotou_safe": any(item["baotou_safe"] for item in options),
                "near_score": any(item["baotou_safe"] and item["score_gap"] is not None
                                  and 0 <= item["score_gap"] <= 10 for item in options),
                "novel_near_score": any(item["baotou_safe"] and item["score_gap"] is not None
                                        and 0 <= item["score_gap"] <= 10
                                        and not item["same_old"] for item in options),
            }
            for layer, passed in flags.items():
                if not passed:
                    continue
                scopes[layer]["windows"].add(key)
                scopes[layer]["tables"].add(current["game_id"])
                scopes[layer]["rooms"].add(current["room_id"])
                directions[direction][layer] += 1
            details.append({
                "room_id": current["room_id"], "game_id": current["game_id"],
                "round_no": current["round_no"], "seat": current["seat"],
                "prior_seq": prior["trigger_seq"], "trigger_seq": current["trigger_seq"],
                "previous_lead": previous_lead,
                "prior_parent_action": prior["parent_action"], "parent_action": parent,
                "prior_route": {"standard": prior["standard"], "seven": prior["seven_pairs"],
                                "combined": prior["combined"]},
                "parent_route": {"standard": current["standard"],
                                 "seven": current["seven_pairs"],
                                 "combined": current["combined"],
                                 "combined_capacity": parent_capacity,
                                 "white_after": parent_white_after,
                                 "baotou_after": parent_baotou},
                "white_count": current["white_count"],
                "wall_remaining": current["wall_remaining"],
                "old_actions": old, "layers": flags, "options": options,
            })
    output = {
        "schema": "g57-route-tie-entry/1", "outcome_blind": True,
        "parent_source_sha256": frozen["parent_source_sha256"],
        "frozen_rooms_sha256": sha(atlas.FROZEN),
        "complete_ids_source_sha256": sha(atlas.TRAIN_ROWS),
        "source_script_sha256": sha(Path(longitudinal.__file__)),
        "g56_script_sha256": sha(Path(g56.__file__)),
        "script_sha256": sha(Path(__file__)),
        "complete_official_tables": len(complete_ids), "official_rooms": len(frozen["rooms"]),
        "source_counts": dict(source_counts), "counts": dict(counts),
        "layers": {layer: {name: len(values) for name, values in dimensions.items()}
                   for layer, dimensions in scopes.items()},
        "directions": {direction: dict(counter) for direction, counter in directions.items()},
        "rows": details,
        "boundary": "本窗备选仅用当前合法生产事实；上一已确认动作只作为可见路线历史。入口频率不是收益或正确弃牌标签。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"counts": output["counts"], "layers": output["layers"],
                      "directions": output["directions"]}, ensure_ascii=False, sort_keys=True,
                     indent=2))


if __name__ == "__main__":
    main()
