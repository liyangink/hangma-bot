#!/usr/bin/env python3
"""G14 静态独有留白窗口的下一本人摸牌条件压力测试；未来摸牌只供赛后诊断。"""

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

import g11_cross_family_action_atlas as atlas
import g11_longitudinal_route_audit as g11
from hangma_bot.hangma.hand_analysis import _need_std, analyse_hand_progress, any_tile_win
from hangma_bot.hangma.internal_types import TILE_ORDER, counts_from_tiles
from hangma_bot.kernel.actions import Tile


HERE = Path(__file__).resolve().parent
FRONTIER = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-white-reserve-frontier-20260927')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-novel-next-draw-stress-20260927/result.json')


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _codes(hand: Counter) -> tuple[Tile, ...]:
    return tuple(Tile(code) for code, count in hand.items() for _ in range(count))


def _reserve_need(hand: Counter, melds: int) -> int:
    counts = counts_from_tiles(_codes(hand))
    return _need_std(counts[:33], 0, 4 - melds, True)


def _physical_natural_width(hand: Counter, melds: int, need: int) -> int:
    """只数物理可有的自然牌种，未知他家占用不当 0。"""

    width = 0
    for code in TILE_ORDER[:33]:
        if hand[code] >= 4:
            continue
        next_hand = hand.copy()
        next_hand[code] += 1
        width += _reserve_need(next_hand, melds) < need
    return width


def _best_second(full: Counter, melds: int, required_whites: int) -> dict | None:
    """理想化下一摸后可弃任意自然牌的最优形状；不作合法策略声明。"""

    options = []
    for code in sorted(full):
        if code == "白":
            continue
        after = g11._after_discard(full, "discard:" + code)
        if after is None or after["白"] != required_whites:
            continue
        need = _reserve_need(after, melds)
        width = _physical_natural_width(after, melds, need)
        summary = analyse_hand_progress(_codes(after), melds)
        options.append({"action": "discard:" + code, "natural_draws_needed": need,
                        "natural_physical_tile_types": width,
                        "standard_shanten": summary.standard_shanten,
                        "seven_shanten": summary.chiitoi_shanten,
                        "combined_shanten": summary.shanten,
                        "static_any_tile_win": any_tile_win(_codes(after), melds)})
    if not options:
        return None
    return min(options, key=lambda item: (item["natural_draws_needed"],
                                          -item["natural_physical_tile_types"],
                                          item["action"]))


def main() -> None:
    """只在冻结 G14 静态新入口上施加父代实际下一摸牌，不读终局积分。"""

    if OUT.exists():
        raise SystemExit("G14 两窗口压力测试已存在，拒绝覆盖")
    frontier = json.loads((_project_file(_PROJECT_ROOT, FRONTIER / "result.json")).read_text(encoding="utf-8"))
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    if (frontier.get("outcome_blind") is not True
            or frontier["rows_sha256"] != _sha(_project_file(_PROJECT_ROOT, FRONTIER / "rows.jsonl.gz"))
            or frontier["parent_source_sha256"] != frozen["parent_source_sha256"]):
        raise ValueError("G14 白板前沿输入漂移")
    targets = {}
    with gzip.open(_project_file(_PROJECT_ROOT, FRONTIER / "rows.jsonl.gz"), "rt", encoding="utf-8") as stream:
        for line in stream:
            item = json.loads(line)
            if item["best_natural_novel"] is None:
                continue
            key = (item["game_id"], item["round_no"], item["seat"], item["trigger_seq"])
            if key in targets:
                raise ValueError("独有窗口键重复")
            targets[key] = item
    if len(targets) != frontier["counts"]["any_natural_wider_without_conventional_type_gain"]:
        raise ValueError("G14 静态独有窗口数漂移")
    rows, _ = g11._draw_rows(atlas._complete_ids(), frozen)
    by_round = defaultdict(list)
    for row in rows:
        by_round[(row["game_id"], row["round_no"], row["seat"])].append(row)
    counts = Counter()
    results = []
    for (game_id, round_no, seat, seq), target in targets.items():
        sequence = sorted(by_round[(game_id, round_no, seat)],
                          key=lambda row: row["trigger_seq"])
        index = next((i for i, row in enumerate(sequence)
                      if row["trigger_seq"] == seq), None)
        if index is None:
            raise ValueError("G14 目标不在 G11 真实正常弃牌母体")
        counts["target_windows"] += 1
        if index + 1 == len(sequence):
            counts["no_later_normal_discard"] += 1
            continue
        first, next_row = sequence[index], sequence[index + 1]
        if first["own_melds"] != next_row["own_melds"] or first["after"] != next_row["before"]:
            counts["next_normal_hand_unmatched"] += 1
            continue
        counts["next_normal_hand_matched"] += 1
        old_white = first["after"]["白"]
        alternative_action = target["best_natural_novel"]["action"]
        alternative_after = g11._after_discard(first["before"] + Counter({first["drawn_tile"]: 1}),
                                                alternative_action)
        if alternative_after is None or alternative_after["白"] != old_white:
            raise ValueError("替代前弃牌无法保留相同白板")
        drawn = next_row["drawn_tile"]
        parent_full = first["after"] + Counter({drawn: 1})
        alternate_full = alternative_after + Counter({drawn: 1})
        if parent_full != next_row["before"] + Counter({drawn: 1}):
            raise ValueError("真实父代下一摸牌不符")
        parent_best = _best_second(parent_full, first["own_melds"], old_white + (drawn == "白"))
        alternate_best = _best_second(alternate_full, first["own_melds"], old_white + (drawn == "白"))
        if parent_best is None or alternate_best is None:
            counts["second_discard_projection_unknown"] += 1
            continue
        comparison = ("better_natural_need" if alternate_best["natural_draws_needed"] < parent_best["natural_draws_needed"]
                      else "equal_need_wider" if (alternate_best["natural_draws_needed"] == parent_best["natural_draws_needed"]
                                                   and alternate_best["natural_physical_tile_types"] > parent_best["natural_physical_tile_types"])
                      else "same_or_worse")
        counts[comparison] += 1
        results.append({"game_id": game_id, "round_no": round_no, "seat": seat,
                        "first_trigger_seq": seq, "next_trigger_seq": next_row["trigger_seq"],
                        "conditional_next_drawn_tile": drawn,
                        "first_parent_action": first["parent_action"],
                        "first_alternative_action": alternative_action,
                        "parent_best_second": parent_best,
                        "alternate_best_second": alternate_best,
                        "comparison": comparison,
                        "actual_parent_second_action": next_row["parent_action"],
                        "boundary": "下一摸牌来自父代赛后轨迹，仅条件压力测试；第二弃牌未作完整动作窗口合法性重判"})
    result = {"schema": "g14-novel-next-draw-stress/1", "outcome_blind": True,
              "frontier_result_sha256": _sha(_project_file(_PROJECT_ROOT, FRONTIER / "result.json")),
              "frontier_rows_sha256": _sha(_project_file(_PROJECT_ROOT, FRONTIER / "rows.jsonl.gz")),
              "parent_source_sha256": frozen["parent_source_sha256"],
              "analysis_script_sha256": _sha(Path(__file__)),
              "counts": dict(sorted(counts.items())), "rows": results,
              "boundary": "只对 G14 独有静态入口施加父代实际下一摸牌；不保证改前弃牌后下一摸仍发生，第二弃牌未作规则合法性重判，不能估算净收益。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(result["counts"], ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
