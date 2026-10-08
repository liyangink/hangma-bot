#!/usr/bin/env python3
"""四开发房结果盲解剖玄武与 R18 v2 的不同弃牌。"""

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

import c31_action_layer_gap as c31
import g05_parent_dev_behavior as baseline
from hangma_bot.application.audit_codec import observation_from_json
from hangma_bot.hangma.interface import RuleCompleteness


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g05-discard-divergence-01')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def score_bucket(gap: object) -> str:
    if type(gap) not in (int, float) or gap < 0:
        return "unknown"
    if gap == 0:
        return "tie"
    if gap <= 10:
        return "0_to_10"
    return "over_10"


def facts(candidate: object) -> dict:
    """保留规则明确提供的距离、容量与爆头事实；未知仍为 null。"""
    value = candidate.facts
    return {
        "shanten": value.shanten_after,
        "standard_shanten": value.standard_shanten_after,
        "seven_pairs_shanten": value.seven_pairs_shanten_after,
        "useful_remaining": sum(tile.remaining_estimate for tile in value.useful_tiles)
        if value.useful_tiles is not None else None,
        "baotou_after": value.baotou_after,
    }


def compare(actual: dict, parent: dict) -> dict:
    """只比较同观察规则事实；正距离差表示强手弃牌更慢。"""
    output = {}
    for name in ("shanten", "standard_shanten", "seven_pairs_shanten",
                 "useful_remaining"):
        a, p = actual[name], parent[name]
        output[name + "_actual_minus_parent"] = a - p if a is not None and p is not None else None
    output["baotou_actual_gain"] = (
        parent["baotou_after"] is False and actual["baotou_after"] is True
    )
    slower = output["shanten_actual_minus_parent"]
    improved_other = []
    for name in ("standard_shanten", "seven_pairs_shanten"):
        delta = output[name + "_actual_minus_parent"]
        if delta is not None and delta < 0 and actual[name] is not None and actual[name] <= 1:
            improved_other.append(name)
    output["slow_with_near_other_family_or_baotou"] = (
        slower is not None and slower >= 1
        and (bool(improved_other) or output["baotou_actual_gain"])
    )
    output["near_other_family"] = improved_other
    return output


def main() -> None:
    """固定四开发房来源，逐窗核实合法动作后按房/桌/单局计数。"""
    if OUT.exists():
        raise FileExistsError("证据目录已存在，拒绝覆盖")
    input_hashes = {}
    rows = []
    counts = defaultdict(Counter)
    for source in baseline.DISCARD_DIRS:
        path = _project_file(_PROJECT_ROOT, HERE / "evidence" / source / "windows.json")
        input_hashes[source] = digest(path)
        source_rows = json.loads(path.read_text(encoding="utf-8"))["windows"]
        for row in source_rows:
            actual_key = row["actual_action"]
            parent_key = row["parent_top_action"]
            if not (actual_key.startswith("discard:")
                    and parent_key.startswith("discard:")
                    and actual_key != parent_key):
                continue
            room = row["room_id"]
            counts[room]["different_discard"] += 1
            observation = observation_from_json(row["observation"])
            analysis = c31.RULES.analyze(observation, value_limits=c31.VALUE_LIMITS)
            if analysis.completeness is not RuleCompleteness.COMPLETE:
                counts[room]["rule_analysis_incomplete"] += 1
                continue
            candidates = {candidate.action_key: candidate
                          for candidate in analysis.legal_candidates}
            if actual_key not in candidates or parent_key not in candidates:
                counts[room]["missing_legal_action"] += 1
                continue
            if (candidates[actual_key].facts.completeness is not RuleCompleteness.COMPLETE
                    or candidates[parent_key].facts.completeness is not RuleCompleteness.COMPLETE):
                counts[room]["candidate_facts_incomplete"] += 1
                continue
            a = facts(candidates[actual_key])
            p = facts(candidates[parent_key])
            comparison = compare(a, p)
            gap = row["parent_score_gap_top_minus_actual"]
            bucket = score_bucket(gap)
            counts[room]["bucket:" + bucket] += 1
            delta = comparison["shanten_actual_minus_parent"]
            counts[room]["shanten_delta:" + str(delta)] += 1
            counts[room]["slow_with_near_other_family_or_baotou"] += (
                comparison["slow_with_near_other_family_or_baotou"]
            )
            rows.append({
                "room_id": room,
                "game_id": row["game_id"],
                "round_no": row["round_no"],
                "draw_seq": row["draw_seq"],
                "actual_action": actual_key,
                "parent_action": parent_key,
                "score_bucket": bucket,
                "parent_score_gap": gap,
                "actual_facts": a,
                "parent_facts": p,
                "comparison": comparison,
                "dealer": observation.seat == observation.dealer_seat,
                "wall_remaining": observation.remaining_tile_count,
                "white_count": sum(tile.code == "白" for tile in observation.my_hand),
            })
    keys = {(row["game_id"], row["round_no"], row["draw_seq"]) for row in rows}
    if len(keys) != len(rows):
        raise ValueError("重复强手动作窗口")
    special = [row for row in rows if row["comparison"]["slow_with_near_other_family_or_baotou"]]
    total = Counter()
    for room_counts in counts.values():
        total.update(room_counts)
    result = {
        "schema": "g05-discard-divergence/1",
        "script_sha256": digest(Path(__file__)),
        "source_sha256": input_hashes,
        "room_counts": {room: dict(sorted(value.items())) for room, value in sorted(counts.items())},
        "total_counts": dict(sorted(total.items())),
        "different_discard_windows": len(rows),
        "different_discard_games": len({row["game_id"] for row in rows}),
        "different_discard_episodes": len({(row["game_id"], row["round_no"]) for row in rows}),
        "special_slow_windows": len(special),
        "special_slow_rooms": len({row["room_id"] for row in special}),
        "special_slow_episodes": len({(row["game_id"], row["round_no"]) for row in special}),
        "outcome_labels_opened": False,
    }
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (_project_file(_PROJECT_ROOT, OUT / "windows.json")).write_text(
        json.dumps({"schema": "g05-discard-divergence-windows/1", "windows": rows},
                   ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"total_counts": result["total_counts"],
                      "special_slow_episodes": result["special_slow_episodes"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
