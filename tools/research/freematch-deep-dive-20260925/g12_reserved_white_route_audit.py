#!/usr/bin/env python3
"""G12 结果盲审计：保留一张白板作将时，自然面子还缺几张。"""

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
from hangma_bot.hangma.hand_analysis import _need_std
from hangma_bot.hangma.internal_types import counts_from_tiles
from hangma_bot.kernel.actions import Tile


HERE = Path(__file__).resolve().parent
FROZEN = atlas.FROZEN
G11_BEHAVIOR = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g11-shape-risk-behavior-20260927/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g12-reserved-white-route-audit-20260927/result.json')


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _reserved_white_need(hand: Counter, melds: int) -> int | None:
    """留 1 张白与未来任意牌配将，其余暗牌距自然面子的最小缺口。"""

    if hand["白"] < 1:
        return None
    codes = []
    for code, count in hand.items():
        codes.extend([Tile(code)] * count)
    counts = counts_from_tiles(tuple(codes))
    if counts[33] != hand["白"] or sum(counts) != 13 - 3 * melds:
        raise ValueError("保留白板路线的手牌维度不符")
    # 只借用生产 hand_analysis 调用的同一分组数学；不另造胡牌/向听规则。
    # 当前 13-3*m 张暗牌保留 1 白，余 12-3*m 张恰够 4-m 个面子。
    return _need_std(counts[:33], counts[33] - 1, 4 - melds, False)


def _capacity(facts: dict, field: str) -> int | None:
    shape = g11._support_shape(facts, field)
    return None if shape is None else shape[0]


def main() -> None:
    """在冻结父代已接受的正常摸牌弃牌窗口查路线缺口，不读取任何后续结果。"""

    if OUT.exists():
        raise SystemExit("G12 留白路线审计已存在，拒绝覆盖")
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    behavior = json.loads(G11_BEHAVIOR.read_text(encoding="utf-8"))
    complete_ids = atlas._complete_ids()
    if behavior["parent_source_sha256"] != frozen["parent_source_sha256"]:
        raise ValueError("G11 行为父代身份与 G12 冻结父代不符")
    g11_by_window = {(row["game_id"], row["round_no"], row["trigger_seq"]): row["candidate_action"]
                     for row in behavior["changed"]}
    rows, base_counts = g11._draw_rows(complete_ids, frozen)
    counts = Counter(base_counts)
    scopes = defaultdict(set)
    examples = []
    improved_rows = []
    for row in rows:
        if row["white_count"] not in (1, 2):
            continue
        counts["parent_one_or_two_white_normal_draws"] += 1
        full = row["before"].copy()
        full[row["drawn_tile"]] += 1
        parent_after = row["after"]
        parent_need = _reserved_white_need(parent_after, row["own_melds"])
        if parent_need is None:
            counts["parent_discarded_only_white"] += 1
            continue
        parent_facts = row["legal"][row["parent_action"]]
        if parent_need == 0:
            counts["parent_reserved_need_zero"] += 1
            if parent_facts.get("baotou_after") is not True:
                raise ValueError("留一白、自然面子已成但规则未判爆头")
        parent_standard = row["standard"]
        parent_combined = row["combined"]
        parent_seven = atlas._int(parent_facts, "seven_pairs_shanten_after")
        parent_std_cap = _capacity(parent_facts, "standard_useful_tiles")
        parent_cap = _capacity(parent_facts, "useful_tiles")
        if parent_std_cap is None or parent_cap is None:
            counts["parent_route_support_unknown"] += 1
            continue
        both_capacities_nondecrease = []
        shanten_nonworse = []
        lex_capacity_safe = []
        lex_capacity_seven_safe = []
        all_improved = []
        for action, facts in row["legal"].items():
            if not action.startswith("discard:") or action == row["parent_action"]:
                continue
            after = g11._after_discard(full, action)
            if after is None or after["白"] != parent_after["白"]:
                continue
            need = _reserved_white_need(after, row["own_melds"])
            if need is None or need >= parent_need:
                continue
            if need == 0 and facts.get("baotou_after") is not True:
                raise ValueError("可替代弃牌的留白缺口为零但规则未判爆头")
            standard = atlas._int(facts, "standard_shanten_after")
            combined = atlas._int(facts, "shanten_after")
            seven = atlas._int(facts, "seven_pairs_shanten_after")
            std_cap = _capacity(facts, "standard_useful_tiles")
            cap = _capacity(facts, "useful_tiles")
            score = row["scores"].get(action)
            if (None in (standard, combined, std_cap, cap)
                    or type(score) not in (int, float)):
                continue
            candidate = {"action": action, "reserve_need": need,
                         "standard": standard, "combined": combined,
                         "seven_pairs": seven,
                         "standard_capacity": std_cap, "combined_capacity": cap,
                         "parent_score_gap": float(row["scores"][row["parent_action"]]) - float(score),
                         "baotou_after": facts.get("baotou_after")}
            all_improved.append(candidate)
            if standard <= parent_standard and combined <= parent_combined:
                shanten_nonworse.append(candidate)
                if std_cap >= parent_std_cap and cap >= parent_cap:
                    both_capacities_nondecrease.append(candidate)
                # 有效牌容量只在同一向听档可比；向听严格下降时不强求下一档容量不减。
                if ((standard < parent_standard or std_cap >= parent_std_cap)
                        and (combined < parent_combined or cap >= parent_cap)):
                    lex_capacity_safe.append(candidate)
                    if ((parent_seven is None and seven is None)
                            or (parent_seven is not None and seven is not None
                                and seven <= parent_seven)):
                        lex_capacity_seven_safe.append(candidate)
        if not all_improved:
            continue
        key = (row["game_id"], row["round_no"], row["trigger_seq"])
        counts["any_reserved_white_need_improvement"] += 1
        scopes["any"].add(row["game_id"])
        best_by_group = {}
        for name, group in (("shanten_nonworse", shanten_nonworse),
                            ("both_capacities_nondecrease", both_capacities_nondecrease),
                            ("lex_capacity_safe", lex_capacity_safe),
                            ("lex_capacity_seven_safe", lex_capacity_seven_safe)):
            if group:
                counts[name] += 1
                scopes[name].add(row["game_id"])
        for name, group in (("any", all_improved),
                            ("shanten_nonworse", shanten_nonworse),
                            ("both_capacities_nondecrease", both_capacities_nondecrease),
                            ("lex_capacity_safe", lex_capacity_safe),
                            ("lex_capacity_seven_safe", lex_capacity_seven_safe)):
            if not group:
                continue
            best = min(group, key=lambda item: (item["reserve_need"],
                                                item["parent_score_gap"], item["action"]))
            best_by_group[name] = best
            if g11_by_window.get(key) == best["action"]:
                counts[name + "_g11_same_action"] += 1
            if len(examples) < 80:
                examples.append({"room_id": row["room_id"], "game_id": row["game_id"],
                                 "round_no": row["round_no"], "seat": row["seat"],
                                 "trigger_seq": row["trigger_seq"],
                                 "white_count": row["white_count"],
                                 "own_melds": row["own_melds"],
                                 "parent_action": row["parent_action"],
                                 "parent_reserved_need": parent_need,
                                 "parent_standard": parent_standard,
                                 "parent_standard_capacity": parent_std_cap,
                                 "group": name, "best": best,
                                 "g11_same_action": g11_by_window.get(key) == best["action"]})
        improved_rows.append({"room_id": row["room_id"], "game_id": row["game_id"],
                              "round_no": row["round_no"], "seat": row["seat"],
                              "trigger_seq": row["trigger_seq"],
                              "white_count": row["white_count"],
                              "own_melds": row["own_melds"],
                              "wall_remaining": row["wall_remaining"],
                              "parent_action": row["parent_action"],
                              "parent_reserved_need": parent_need,
                              "parent_standard": parent_standard,
                              "parent_combined": parent_combined,
                              "parent_seven_pairs": parent_seven,
                              "parent_standard_capacity": parent_std_cap,
                              "parent_combined_capacity": parent_cap,
                              "best_by_group": best_by_group,
                              "g11_action": g11_by_window.get(key)})
    result = {"schema": "g12-reserved-white-route-audit/2", "outcome_blind": True,
              "frozen_rooms_sha256": _sha(FROZEN),
              "g11_behavior_sha256": _sha(G11_BEHAVIOR),
              "parent_source_sha256": frozen["parent_source_sha256"],
              "complete_official_tables": len(complete_ids),
              "counts": dict(sorted(counts.items())),
              "scopes": {name: {"complete_tables": len(ids),
                                "conditional_gain_for_plus2_all_tables":
                                    2 * len(complete_ids) / len(ids)}
                         for name, ids in sorted(scopes.items())},
              "first_examples": examples,
              "improved_rows": improved_rows,
              "boundary": "留一白成面子缺口仅是标准型爆头结构目标，不含七对爆头、未来摸牌概率或最终积分；输入只为动作前本人可见手牌和生产规则事实。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ("first_examples", "improved_rows")},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
