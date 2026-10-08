#!/usr/bin/env python3
"""G172：官方已接受父代弃牌的多白板次级普通路线入口普查。"""

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
import g11_longitudinal_route_audit as g11
import g14_discard_width_baseline as width


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G172-MULTIWHITE-SECONDARY-ROUTE-CENSUS-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g172-multiwhite-secondary-route-census-20260928/result.json')


def sha(path: Path) -> str:
    """绑定冻结来源、预登记和本程序原始字节。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def vector(facts: dict, field: str) -> tuple[tuple[str, int], ...] | None:
    """生产逐码公开未见上界；未知与已知空集合不同。"""
    raw = facts.get(field)
    if raw is None or not isinstance(raw, list):
        return None
    result = []
    seen = set()
    for item in raw:
        if not isinstance(item, dict):
            return None
        code = item.get("code")
        count = item.get("remaining_estimate")
        if (not isinstance(code, str) or code in seen
                or type(count) is not int or not 0 <= count <= 4):
            return None
        seen.add(code)
        result.append((code, count))
    return tuple(sorted(result))


def _score(value) -> int | float | None:
    """原策略总分仅用于纯平手分层，未知不当作零。"""
    if type(value) not in (int, float):
        return None
    return value


def main() -> None:
    """仅看行动前规则与已接受父代弃牌，不读取结算或未来事件。"""
    if OUT.exists():
        raise FileExistsError("G172 结果已存在，拒绝覆盖")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    complete = atlas._complete_ids()
    if len(complete) != 909:
        raise ValueError("G172 冻结官方完整桌母体漂移")
    rows, coverage = g11._draw_rows(complete, frozen)
    strata = defaultdict(Counter)
    scopes = defaultdict(lambda: {"rooms": set(), "games": set(), "hands": set()})
    selected = []
    for row in rows:
        white = row["white_count"]
        if white < 1:
            continue
        stratum = "1" if white == 1 else "2plus"
        counts = strata[stratum]
        counts["accepted_draw_discard"] += 1
        if row["after"]["白"] != white:
            continue
        counts["parent_keeps_all_white"] += 1
        parent_key = row["parent_action"]
        parent_facts = row["legal"][parent_key]
        parent_shape = width._shape(parent_facts)
        if (parent_shape["seven_shanten"] is None
                or parent_shape["standard_shanten"] is None
                or parent_shape["combined_shanten"] is None
                or parent_shape["seven_shanten"]
                != parent_shape["combined_shanten"]
                or parent_shape["standard_shanten"]
                <= parent_shape["seven_shanten"]):
            continue
        counts["seven_strictly_leads_standard"] += 1
        parent_combined = vector(parent_facts, "useful_tiles")
        parent_seven = vector(parent_facts, "seven_pairs_useful_tiles")
        parent_standard = vector(parent_facts, "standard_useful_tiles")
        if any(item is None for item in (
                parent_combined, parent_seven, parent_standard)):
            counts["parent_vector_unknown"] += 1
            continue
        full = row["before"].copy()
        full[row["drawn_tile"]] += 1
        alternatives = []
        for key, facts in row["legal"].items():
            if key == parent_key or not key.startswith("discard:") or key == "discard:白":
                continue
            after = g11._after_discard(full, key)
            if after is None or after["白"] != white:
                continue
            shape = width._shape(facts)
            if (shape["combined_shanten"] != parent_shape["combined_shanten"]
                    or shape["seven_shanten"] != parent_shape["seven_shanten"]):
                continue
            combined = vector(facts, "useful_tiles")
            seven = vector(facts, "seven_pairs_useful_tiles")
            standard = vector(facts, "standard_useful_tiles")
            if combined is None or seven is None or standard is None:
                counts["alternate_vector_unknown"] += 1
                continue
            if combined != parent_combined or seven != parent_seven:
                continue
            if shape["standard_shanten"] is None:
                continue
            if shape["standard_shanten"] < parent_shape["standard_shanten"]:
                marker = "standard_shanten_better"
            elif (shape["standard_shanten"] == parent_shape["standard_shanten"]
                    and sum(value > 0 for _, value in standard)
                    > sum(value > 0 for _, value in parent_standard)
                    and sum(value for _, value in standard)
                    > sum(value for _, value in parent_standard)):
                marker = "same_shanten_strictly_wider"
            else:
                continue
            tie = (_score(row["scores"].get(key)) is not None
                   and _score(row["scores"].get(key))
                   == _score(row["scores"].get(parent_key)))
            alternatives.append({
                "action": key,
                "marker": marker,
                "pure_policy_score_tie": tie,
                "standard_shanten": shape["standard_shanten"],
                "standard_types": sum(value > 0 for _, value in standard),
                "standard_public_capacity_upper": sum(value for _, value in standard),
                "parent_minus_alternate_score": (None if _score(row["scores"].get(key))
                                                 is None or _score(row["scores"].get(parent_key))
                                                 is None else row["scores"][parent_key]
                                                 - row["scores"][key]),
            })
        if not alternatives:
            continue
        counts["any_secondary_route_improvement"] += 1
        room, game = row["room_id"], row["game_id"]
        hand = (game, row["round_no"], row["seat"])
        scopes[stratum]["rooms"].add(room)
        scopes[stratum]["games"].add(game)
        scopes[stratum]["hands"].add(hand)
        for marker in set(item["marker"] for item in alternatives):
            counts[marker] += 1
        if any(item["pure_policy_score_tie"] for item in alternatives):
            counts["any_pure_policy_score_tie"] += 1
        best = min(alternatives, key=lambda item: (
            item["standard_shanten"], -item["standard_types"],
            -item["standard_public_capacity_upper"], item["action"]))
        selected.append({
            "room_id": room, "game_id": game, "round_no": row["round_no"],
            "seat": row["seat"], "trigger_seq": row["trigger_seq"],
            "white_before": white, "wall_remaining": row["wall_remaining"],
            "parent_action": parent_key,
            "parent_standard_shanten": parent_shape["standard_shanten"],
            "parent_standard_types": sum(value > 0 for _, value in parent_standard),
            "parent_standard_public_capacity_upper": sum(
                value for _, value in parent_standard),
            "parent_seven_shanten": parent_shape["seven_shanten"],
            "parent_combined_vector": parent_combined,
            "parent_seven_vector": parent_seven,
            "best_alternative": best,
            "eligible_alternative_count": len(alternatives),
            "pure_tie_alternative_count": sum(
                item["pure_policy_score_tie"] for item in alternatives),
        })
    payload = {
        "schema": "g172-multiwhite-secondary-route-census/1",
        "outcome_blind": True,
        "input_sha256": {
            "prereg": sha(PREREG),
            "script": sha(Path(__file__)),
            "frozen_rooms": sha(atlas.FROZEN),
        },
        "parent_source_sha256": frozen["parent_source_sha256"],
        "complete_official_tables": len(complete),
        "source_accepted_draw_discards": coverage["accepted_normal_draw_discards"],
        "strata": {key: dict(sorted(value.items()))
                   for key, value in sorted(strata.items())},
        "scopes": {key: {name: len(ids) for name, ids in value.items()}
                   for key, value in sorted(scopes.items())},
        "rows": selected,
        "boundary": "已看官方父代房的行动前规则事实入口普查，不含结果或隐藏信息。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False,
                              sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"strata": payload["strata"], "scopes": payload["scopes"],
                      "selected_windows": len(selected)},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
