#!/usr/bin/env python3
"""G56：只用父代已接受摸打及当窗规则事实，审计跨窗路线反转入口。"""

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


HERE = Path(__file__).resolve().parent
G10 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g10-route-option-screen-20260927/result.json')
G11 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g11-shape-risk-behavior-20260927/result.json')
G49 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g49-official-behavior-20260927/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g56-route-switch-reach-20260927/result.json')
LAYERS = ("switch", "old_route_legal", "combined_safe", "capacity_safe",
          "near_score", "novel_near_score")


def sha(path: Path) -> str:
    """记录冻结输入与本程序字节摘要，防止结果和分析口径脱钩。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def lead(standard: int | None, seven: int | None) -> str | None:
    """只判两个路线的严格向听顺序；持平／缺失为未知路线意图。"""

    if standard is None or seven is None or standard == seven:
        return None
    return "ordinary" if standard < seven else "seven"


def state(standard: int | None, seven: int | None) -> str:
    """探索性转移表保留持平层；主预登记入口仍仅是严格领先反转。"""

    if standard is None or seven is None:
        return "unknown"
    return "tie" if standard == seven else "ordinary" if standard < seven else "seven"


def _old_actions() -> tuple[dict, dict, dict]:
    """旧候选只用于同窗同动作去重，绝不读取其桌赛结果。"""

    g10 = json.loads(G10.read_text(encoding="utf-8"))
    g11 = json.loads(G11.read_text(encoding="utf-8"))
    g49 = json.loads(G49.read_text(encoding="utf-8"))
    parent_sha = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))["parent_source_sha256"]
    if any(item.get("outcome_blind") is not True or item.get("parent_source_sha256",
            item.get("source_parent_sha256")) != parent_sha for item in (g10, g11, g49)):
        raise ValueError("旧行为清单不是同父代结果盲证据")

    def key(row: dict) -> tuple:
        return row["game_id"], row["round_no"], row["trigger_seq"]

    return (
        {key(row): row["alternate_action"] for row in g10["rows"]},
        {key(row): row["candidate_action"] for row in g11["changed"]},
        {key(row): row["candidate_action"] for row in g49["changed"]},
    )


def _option(facts: dict, parent_combined: int, parent_capacity: int | None,
            parent_score: float, score: object, previous_lead: str) -> dict | None:
    """当前合法弃牌的路线与保护层；公开容量是上界，非摸牌概率。"""

    standard = atlas._int(facts, "standard_shanten_after")
    seven = atlas._int(facts, "seven_pairs_shanten_after")
    combined = atlas._int(facts, "shanten_after")
    if lead(standard, seven) != previous_lead:
        return None
    capacity = atlas._capacity(facts, "useful_tiles")
    gap = (parent_score - float(score)) if type(score) in (int, float) else None
    return {
        "standard": standard, "seven": seven, "combined": combined,
        "combined_capacity": capacity, "score_gap": gap,
        "combined_safe": combined is not None and combined <= parent_combined,
        "capacity_safe": (combined is not None and combined <= parent_combined
                          and parent_capacity is not None and capacity is not None
                          and capacity >= parent_capacity),
    }


def main() -> None:
    """逐层记录入口，后窗只在到达时作为当前可见状态使用。"""

    if OUT.exists():
        raise SystemExit("G56 结果已存在，拒绝覆盖")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    complete_ids = atlas._complete_ids()
    g10, g11, g49 = _old_actions()
    rows, source_counts = longitudinal._draw_rows(complete_ids, frozen)
    by_round: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        by_round[(row["game_id"], row["round_no"], row["seat"])].append(row)

    counts = Counter()
    per_layer: dict[str, dict[str, set]] = {
        layer: {"windows": set(), "tables": set(), "rooms": set()}
        for layer in LAYERS
    }
    groups: dict[str, Counter] = defaultdict(Counter)
    transition_windows = Counter()
    transition_tables: dict[str, set[str]] = defaultdict(set)
    examples = []
    seen = set()
    for sequence in by_round.values():
        sequence.sort(key=lambda row: row["trigger_seq"])
        for prior, current in zip(sequence, sequence[1:]):
            counts["consecutive_normal_draw_pairs"] += 1
            if prior["own_melds"] != current["own_melds"] or prior["after"] != current["before"]:
                counts["unmatched_or_meld_changed"] += 1
                continue
            counts["matched_pairs"] += 1
            if prior["own_melds"] != 0:
                counts["matched_with_meld"] += 1
                continue
            counts["matched_no_meld"] += 1
            white_group = ("with_white" if prior["after"]["白"] >= 1
                           and current["white_count"] >= 1 else "without_continuous_white")
            transition = (white_group + "/" + state(prior["standard"], prior["seven_pairs"])
                          + "_to_" + state(current["standard"], current["seven_pairs"]))
            transition_windows[transition] += 1
            transition_tables[transition].add(current["game_id"])
            previous_lead = lead(prior["standard"], prior["seven_pairs"])
            current_lead = lead(current["standard"], current["seven_pairs"])
            if previous_lead is None or current_lead is None or previous_lead == current_lead:
                continue
            key = current["game_id"], current["round_no"], current["trigger_seq"]
            if key in seen:
                raise ValueError("同一父代路线反转窗口重复")
            seen.add(key)
            direction = previous_lead + "_to_" + current_lead
            counts["strict_route_switch"] += 1
            parent_facts = current["legal"][current["parent_action"]]
            parent_capacity = atlas._capacity(parent_facts, "useful_tiles")
            parent_score = current["scores"].get(current["parent_action"])
            if type(parent_score) not in (int, float):
                raise ValueError("已接受父代评分缺失")
            old = {"g10": g10.get(key), "g11": g11.get(key), "g49": g49.get(key)}
            options = []
            for action, facts in current["legal"].items():
                if not action.startswith("discard:") or action == current["parent_action"]:
                    continue
                data = _option(facts, current["combined"], parent_capacity,
                               float(parent_score), current["scores"].get(action), previous_lead)
                if data is None:
                    continue
                data["action"] = action
                data["same_old"] = [name for name, old_action in old.items()
                                    if action == old_action]
                options.append(data)
            options.sort(key=lambda row: (row["score_gap"] is None,
                                          row["score_gap"] if row["score_gap"] is not None else 0,
                                          row["action"]))
            layer_flags = {
                "switch": True,
                "old_route_legal": bool(options),
                "combined_safe": any(item["combined_safe"] for item in options),
                "capacity_safe": any(item["capacity_safe"] for item in options),
                "near_score": any(item["capacity_safe"] and item["score_gap"] is not None
                                  and 0 <= item["score_gap"] <= 10 for item in options),
                "novel_near_score": any(item["capacity_safe"] and item["score_gap"] is not None
                                        and 0 <= item["score_gap"] <= 10
                                        and not item["same_old"] for item in options),
            }
            for layer, passed in layer_flags.items():
                if not passed:
                    continue
                per_layer[layer]["windows"].add(key)
                per_layer[layer]["tables"].add(current["game_id"])
                per_layer[layer]["rooms"].add(current["room_id"])
                groups[white_group][layer] += 1
                groups[direction][layer] += 1
            if white_group == "with_white":
                examples.append({
                    "room_id": current["room_id"], "game_id": current["game_id"],
                    "round_no": current["round_no"], "seat": current["seat"],
                    "prior_seq": prior["trigger_seq"], "trigger_seq": current["trigger_seq"],
                    "previous_lead": previous_lead, "parent_lead": current_lead,
                    "prior_parent_action": prior["parent_action"],
                    "parent_action": current["parent_action"],
                    "prior_route": {"standard": prior["standard"], "seven": prior["seven_pairs"],
                                    "combined": prior["combined"]},
                    "parent_route": {"standard": current["standard"],
                                     "seven": current["seven_pairs"],
                                     "combined": current["combined"],
                                     "combined_capacity": parent_capacity},
                    "white_count": current["white_count"],
                    "wall_remaining": current["wall_remaining"],
                    "old_actions": old, "layers": layer_flags, "options": options,
                })
    output = {
        "schema": "g56-route-switch-reach/1", "outcome_blind": True,
        "parent_source_sha256": frozen["parent_source_sha256"],
        "frozen_rooms_sha256": sha(atlas.FROZEN),
        "complete_ids_source_sha256": sha(atlas.TRAIN_ROWS),
        "source_script_sha256": sha(Path(longitudinal.__file__)),
        "script_sha256": sha(Path(__file__)),
        "old_behavior_sha256": {"g10": sha(G10), "g11": sha(G11), "g49": sha(G49)},
        "complete_official_tables": len(complete_ids), "official_rooms": len(frozen["rooms"]),
        "source_counts": dict(source_counts), "counts": dict(counts),
        "exploratory_transitions": {
            label: {"windows": windows, "tables": len(transition_tables[label])}
            for label, windows in sorted(transition_windows.items())},
        "layers": {layer: {name: len(values) for name, values in dimensions.items()}
                   for layer, dimensions in per_layer.items()},
        "groups": {group: dict(counter) for group, counter in groups.items()},
        "with_white_rows": examples,
        "boundary": "后窗只有到达时才作为当前可见状态；旧动作仅做去重。路线反转和备选入口均不是收益或正确动作标签。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"counts": output["counts"], "layers": output["layers"],
                      "groups": output["groups"],
                      "exploratory_transitions": output["exploratory_transitions"]},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
