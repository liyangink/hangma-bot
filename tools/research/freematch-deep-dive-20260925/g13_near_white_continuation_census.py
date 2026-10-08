#!/usr/bin/env python3
"""G13 结果盲续行普查：近爆头留白改选是否确有前后本人正常摸打窗口。"""

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
import g12_reserved_white_route_audit as g12
from hangma_bot.hangma.hand_analysis import any_tile_win
from hangma_bot.kernel.actions import Tile


HERE = Path(__file__).resolve().parent
G10 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g10-route-option-screen-20260927/result.json')
G12 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g12-reserved-white-route-audit-20260927/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g13-near-white-continuation-20260927/result.json')


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _matched(left: dict, right: dict) -> bool:
    """前一弃后 13 张恰等于后一摸前 13 张，且本人副露数未变。"""

    return left["own_melds"] == right["own_melds"] and left["after"] == right["before"]


def _parent_need(row: dict | None) -> int | None:
    if row is None:
        return None
    return g12._reserved_white_need(row["after"], row["own_melds"])


def _same_draw_static_baotou(current: dict, next_row: dict, action: str) -> list[str]:
    """条件固定父代下一张摸牌，枚举改选后第二次弃牌的静态任意听见证。

    只检验牌型数学，不模拟对手对首弃的响应或第二窗的完整合法性。
    这是赛后压力题，下一张摸牌绝不能成为前窗线上触发输入。
    """

    full = current["before"].copy()
    full[current["drawn_tile"]] += 1
    alternate_after = g11._after_discard(full, action)
    if alternate_after is None or alternate_after["白"] != current["after"]["白"]:
        raise ValueError("G12 改选不是与父代相同白板数的合法首弃")
    second_full = alternate_after.copy()
    second_full[next_row["drawn_tile"]] += 1
    if sum(second_full.values()) != 14 - 3 * current["own_melds"]:
        raise ValueError("条件第二次摸牌手牌维度不符")
    witnesses = []
    for code in sorted(second_full):
        after = g11._after_discard(second_full, "discard:" + code)
        if after is None:
            continue
        tiles = tuple(Tile(tile) for tile, amount in after.items() for _ in range(amount))
        if any_tile_win(tiles, current["own_melds"]):
            witnesses.append("discard:" + code)
    return witnesses


def main() -> None:
    """只用冻结父代轨迹的已确认动作和动作前规则事实，不读结算标签。"""

    if OUT.exists():
        raise SystemExit("G13 近爆头续行普查已存在，拒绝覆盖")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    g10 = json.loads(G10.read_text(encoding="utf-8"))
    g12_result = json.loads(G12.read_text(encoding="utf-8"))
    if (g10.get("outcome_blind") is not True
            or g12_result.get("outcome_blind") is not True
            or g10.get("source_parent_sha256") != frozen["parent_source_sha256"]
            or g12_result.get("parent_source_sha256") != frozen["parent_source_sha256"]
            or g12_result.get("frozen_rooms_sha256") != _sha(atlas.FROZEN)):
        raise ValueError("冻结父代或结果盲输入摘要不一致")
    complete_ids = atlas._complete_ids()
    if len(complete_ids) != g12_result["complete_official_tables"]:
        raise ValueError("核验完整桌母体变化")
    g10_windows = {(item["game_id"], item["round_no"], item["trigger_seq"])
                   for item in g10["rows"]}
    draw_rows, draw_counts = g11._draw_rows(complete_ids, frozen)
    by_round: dict[tuple, list[dict]] = defaultdict(list)
    for row in draw_rows:
        by_round[(row["game_id"], row["round_no"], row["seat"])].append(row)
    positions = {}
    for key, sequence in by_round.items():
        sequence.sort(key=lambda item: item["trigger_seq"])
        for index, row in enumerate(sequence):
            identity = (*key, row["trigger_seq"])
            if identity in positions:
                raise ValueError("本人正常摸打窗口重复")
            positions[identity] = (sequence, index)
    counts = Counter()
    scopes: dict[str, set[str]] = defaultdict(set)
    records = []
    for source in g12_result["improved_rows"]:
        alt = source["best_by_group"]["any"]
        if alt["reserve_need"] > 2:
            continue
        counts["near_need_le2_all"] += 1
        key = (source["game_id"], source["round_no"], source["trigger_seq"])
        if key in g10_windows:
            counts["near_g10_surface_window"] += 1
            continue
        counts["near_outside_g10_window"] += 1
        scopes["near_outside_g10"].add(source["game_id"])
        sequence, index = positions[(*key[:2], source["seat"], key[2])]
        current = sequence[index]
        if (current["parent_action"] != source["parent_action"]
                or current["white_count"] != source["white_count"]
                or current["own_melds"] != source["own_melds"]):
            raise ValueError("G12 与正常摸打源动作不一致")
        previous = sequence[index - 1] if index > 0 else None
        next_row = sequence[index + 1] if index + 1 < len(sequence) else None
        previous_matched = previous is not None and _matched(previous, current)
        next_matched = next_row is not None and _matched(current, next_row)
        if previous_matched:
            counts["matched_previous_normal_draw"] += 1
            scopes["matched_previous"].add(source["game_id"])
        if next_matched:
            counts["matched_next_normal_draw"] += 1
            scopes["matched_next"].add(source["game_id"])
        if previous_matched and next_matched:
            counts["matched_both_sides"] += 1
            scopes["matched_both"].add(source["game_id"])
        next_legal_baotou = None
        next_parent_baotou = None
        alternate_next_static_baotou = None
        if next_matched:
            next_legal_baotou = sum(
                action.startswith("discard:") and facts.get("baotou_after") is True
                for action, facts in next_row["legal"].items())
            next_parent_baotou = (next_row["legal"][next_row["parent_action"]]
                                  .get("baotou_after") is True)
            if next_legal_baotou:
                counts["next_parent_state_has_legal_baotou_discard"] += 1
                scopes["next_parent_has_baotou_option"].add(source["game_id"])
            if next_parent_baotou:
                counts["next_parent_chose_baotou_discard"] += 1
            alternate_next_static_baotou = _same_draw_static_baotou(
                current, next_row, alt["action"])
            if alternate_next_static_baotou:
                counts["alternate_same_draw_static_baotou"] += 1
                scopes["alternate_same_draw_static_baotou"].add(source["game_id"])
                if not next_legal_baotou:
                    counts["alternate_static_baotou_parent_path_none"] += 1
                    scopes["alternate_static_parent_none"].add(source["game_id"])
        if alt["reserve_need"] == 1:
            counts["near_need_one_outside_g10"] += 1
            scopes["near_need_one_outside_g10"].add(source["game_id"])
        if "lex_capacity_seven_safe" in source["best_by_group"]:
            counts["near_has_safe_option_outside_g10"] += 1
            scopes["near_has_safe_option_outside_g10"].add(source["game_id"])
        records.append({
            "room_id": source["room_id"], "game_id": source["game_id"],
            "round_no": source["round_no"], "seat": source["seat"],
            "trigger_seq": source["trigger_seq"],
            "white_count": source["white_count"],
            "wall_remaining": source["wall_remaining"],
            "parent_action": source["parent_action"],
            "alternate": alt, "parent_reserved_need": source["parent_reserved_need"],
            "parent_standard": source["parent_standard"],
            "parent_combined": source["parent_combined"],
            "parent_seven_pairs": source["parent_seven_pairs"],
            "safe_option": source["best_by_group"].get("lex_capacity_seven_safe"),
            "previous_matched": previous_matched,
            "previous_seq": previous["trigger_seq"] if previous_matched else None,
            "previous_parent_reserved_need": _parent_need(previous) if previous_matched else None,
            "next_matched": next_matched,
            "next_seq": next_row["trigger_seq"] if next_matched else None,
            "next_parent_reserved_need": _parent_need(next_row) if next_matched else None,
            "next_legal_baotou_discards_on_parent_path": next_legal_baotou,
            "next_parent_chose_baotou_discard": next_parent_baotou,
            "alternate_same_draw_static_baotou_discards": alternate_next_static_baotou,
        })
    if len(records) != counts["near_outside_g10_window"]:
        raise ValueError("近爆头窗记录数不一致")
    result = {"schema": "g13-near-white-continuation/1", "outcome_blind": True,
              "frozen_rooms_sha256": _sha(atlas.FROZEN), "g10_sha256": _sha(G10),
              "g12_sha256": _sha(G12), "parent_source_sha256": frozen["parent_source_sha256"],
              "complete_official_tables": len(complete_ids),
              "source_draw_counts": dict(sorted(draw_counts.items())),
              "counts": dict(sorted(counts.items())),
              "scopes": {name: {"complete_tables": len(ids),
                                "conditional_gain_for_plus2_all_tables":
                                    2 * len(complete_ids) / len(ids)}
                         for name, ids in sorted(scopes.items())},
              "records": records,
              "boundary": "后一本人摸打及其摸牌是父代真实路径的赛后条件压力题，绝不作为前窗触发输入或完整桌反事实；改选后第二弃仅验静态牌型，未验对手响应/完整合法性。未出现后窗也可能因胡牌/鸣牌/终局而缺失。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "records"},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
