#!/usr/bin/env python3
"""G229：多白近听牌强手与 R18 首选分歧的行动前牌形图谱。"""

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
from hashlib import sha256
import json
from pathlib import Path

import g196_three_draw_competing_route_pilot as g196
import g220_future_qualification_audit as g220
import g228_multiwhite_future_qualification as g228
import g223_visible_multi_action_route as g223
import g87_post_claim_score_trace as g87
from hangma_bot.hangma import hand_analysis
from hangma_bot.hangma.internal_types import counts_from_tiles
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
PLAN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G229-MULTIWHITE-STRONG-DISAGREEMENT-PLAN-2026-09-29.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g229-multiwhite-strong-disagreement-20260929/result.json')


def digest(path: Path) -> str:
    """原文摘要用于重放和审计，不把历史赢家内容送进规则事实。"""
    return sha256(path.read_bytes()).hexdigest()


def _width(tiles) -> tuple[int, int]:
    """生产普通有效牌的正公开容量种数和总数。"""
    if tiles is None:
        raise ValueError("G229 普通型逐码有效牌未知")
    capacities = [item.remaining_estimate for item in tiles]
    if any(type(amount) is not int or amount < 0 for amount in capacities):
        raise ValueError("G229 逐码容量非法")
    return sum(amount > 0 for amount in capacities), sum(capacities)


def _natural_need(hand, meld_count: int) -> int:
    """用生产普通型数学核去白后的自然成面缺口。"""
    counts = counts_from_tiles(hand)
    return hand_analysis._need_std(counts[:33], 0, 4 - meld_count, True)


def _outcome(actor: dict) -> str:
    """强手本局已发生结算，仅用于观察性分层。"""
    if actor["status"] == "win":
        fan = actor["fan"]
        if type(fan) is not int or fan < 1:
            raise ValueError("G229 胜局番值缺失")
        return "plain_win" if fan == 1 else "special_win"
    if actor["status"] in ("other_win", "draw"):
        return actor["status"]
    raise ValueError("G229 强手终局状态未知")


def _width_category(parent: tuple[int, int], actual: tuple[int, int]) -> str:
    """同层进张宽度二维比较；混合变化不得强行合成一个方向。"""
    if actual[0] > parent[0] and actual[1] > parent[1]:
        return "both_wider"
    if actual[0] < parent[0] and actual[1] < parent[1]:
        return "both_narrower"
    if actual == parent:
        return "same_total_width"
    return "mixed_width"


def summarize(rows: list[dict]) -> dict:
    """分别看窗口和首次分歧单局，不将共享房的窗口当独立桌赛。"""
    groups = {"all": rows}
    for peer in ("tengshe_0638", "xuanwu_2346"):
        groups[peer] = [row for row in rows if row["peer"] == peer]
    result = {}
    for name, group in groups.items():
        categories = Counter(row["width_category"] for row in group)
        by_category = {}
        for category in sorted(categories):
            layer = [row for row in group if row["width_category"] == category]
            by_category[category] = {
                "windows": len(layer),
                "rooms": len({row["room"] for row in layer}),
                "seat_hands": len({tuple(row["seat_hand"]) for row in layer}),
                "actual_outcome": dict(sorted(Counter(
                    row["actual_outcome"] for row in layer).items())),
                "standard_shanten_actual_better_equal_worse": [
                    sum(row.get("standard_shanten_delta") is not None
                        and row["standard_shanten_delta"] < 0 for row in layer),
                    sum(row.get("standard_shanten_delta") == 0 for row in layer),
                    sum(row.get("standard_shanten_delta") is not None
                        and row["standard_shanten_delta"] > 0 for row in layer),
                ],
                "natural_need_actual_better_equal_worse": [
                    sum(row.get("natural_need_delta") is not None
                        and row["natural_need_delta"] < 0 for row in layer),
                    sum(row.get("natural_need_delta") == 0 for row in layer),
                    sum(row.get("natural_need_delta") is not None
                        and row["natural_need_delta"] > 0 for row in layer),
                ],
            }
        result[name] = {
            "windows": len(group), "rooms": len({row["room"] for row in group}),
            "seat_hands": len({tuple(row["seat_hand"]) for row in group}),
            "categories": dict(sorted(categories.items())),
            "by_category": by_category,
        }
    return result


def main() -> None:
    """锁 G228/G61 来源，重算当前生产规则事实，再打开 G64 描述性终局。"""
    if OUT.exists():
        raise FileExistsError("G229 图谱结果已存在，拒绝覆盖")
    selection_path = g228.OUT / "selection.json"
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    if (selection["schema"] != "g228-multiwhite-future-selection/1"
            or len(selection["rows"]) != 351):
        raise ValueError("G228 冻结行动前来源漂移")
    visible = g220.windows()
    final = json.loads(g220.G64.read_text(encoding="utf-8"))
    if final["schema"] != "g64-strong-win-timing-result/1":
        raise ValueError("G64 官方终局来源不符")
    outcomes = {(item["peer"], item["room"], item["game_id"], item["round_no"]):
                item["actors"][item["peer"]] for item in final["rows"]}
    rows = []
    for source in selection["rows"]:
        if source["parent_agrees"]:
            continue
        identity = tuple(source["identity"])
        record = visible[identity]
        actor = outcomes[identity[:4]]
        observation = observation_from_json(record["observation"])
        request = g87.request_for(observation)
        legal = {item.action_key: item for item in request.rules.legal_candidates}
        actual = legal.get(record["actual_action"])
        parent = legal.get(record["parent_top_action"])
        if actual is None or parent is None or actual.facts is None or parent.facts is None:
            raise ValueError("G229 两动作不在当前生产规则合法集合")
        row = {
            "identity": list(identity), "peer": identity[0], "room": identity[1],
            "seat_hand": list(identity[:4] + (identity[5],)),
            "draw_seq": identity[4],
            "actual_action": record["actual_action"],
            "parent_action": record["parent_top_action"],
            "parent_score_gap_frozen": record["parent_score_gap_top_minus_actual"],
            "actual_outcome": _outcome(actor),
            "actual_fan": actor["fan"], "actual_score": actor["score"],
            "whites_before": source["whites_before"],
            "wall": source["wall"], "own_melds": source["own_melds"],
        }
        if not record["parent_top_action"].startswith("discard:"):
            row["width_category"] = "parent_non_discard"
            row["parent_action_family"] = record["parent_top_action"].split(":", 1)[0]
        else:
            full = g196._build_context(observation).full_hand()
            meld_count = len(observation.melds[observation.seat])
            actual_width = _width(actual.facts.standard_useful_tiles)
            parent_width = _width(parent.facts.standard_useful_tiles)
            actual_hand = g196._drop(full, record["actual_action"].split(":", 1)[1])
            parent_hand = g196._drop(full, record["parent_top_action"].split(":", 1)[1])
            actual_need = _natural_need(actual_hand, meld_count)
            parent_need = _natural_need(parent_hand, meld_count)
            row.update({
                "width_category": _width_category(parent_width, actual_width),
                "actual_standard_width": actual_width,
                "parent_standard_width": parent_width,
                "standard_shanten_delta": (actual.facts.standard_shanten_after
                                           - parent.facts.standard_shanten_after),
                "seven_pairs_shanten_actual": actual.facts.seven_pairs_shanten_after,
                "seven_pairs_shanten_parent": parent.facts.seven_pairs_shanten_after,
                "baotou_actual": actual.facts.baotou_after,
                "baotou_parent": parent.facts.baotou_after,
                "natural_need_actual": actual_need,
                "natural_need_parent": parent_need,
                "natural_need_delta": actual_need - parent_need,
            })
        rows.append(row)
    if len(rows) != 115 or len({tuple(row["seat_hand"]) for row in rows}) != 79:
        raise ValueError("G229 分歧窗口或独立座位单局规模漂移")
    first = {}
    for row in sorted(rows, key=lambda item: item["draw_seq"]):
        first.setdefault(tuple(row["seat_hand"]), row)
    result = {
        "schema": "g229-multiwhite-strong-disagreement/1",
        "source_sha256": {
            "plan": digest(PLAN), "script": digest(Path(__file__)),
            "g228_selection": digest(selection_path),
            "g61_result": digest(g220.G61 / "result.json"),
            "g64_result": digest(g220.G64),
            "production_hand_analysis": digest(
                _project_file(_PROJECT_ROOT, HERE.parents[1] / "src/hangma_bot/hangma/hand_analysis.py")),
        },
        "all_windows": summarize(rows),
        "first_per_seat_hand": summarize(list(first.values())),
        "rows": rows,
        "boundary": "强手动作与旧冻结 R18 首选的当前生产规则牌形对账；本局终局只为观察性分层，无备选反事实。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    g223.write_new(OUT, result)
    print(json.dumps({"all_windows": result["all_windows"],
                      "first_per_seat_hand": result["first_per_seat_hand"]},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
