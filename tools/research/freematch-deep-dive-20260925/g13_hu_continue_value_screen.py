#!/usr/bin/env python3
"""G13 胡/继续结果盲价值筛查：即时净分与下一次本人摸胡条件见证分离。"""

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
import math
from pathlib import Path

import g11_cross_family_action_atlas as atlas


HERE = Path(__file__).resolve().parent
GRAPH = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g13-cross-window-route-graph-20260927/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g13-hu-continue-value-screen-20260927')


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _settlement(raw: object, seat: int) -> dict | None:
    """只收生产结算的四座分向量；未知不记零。"""

    if not isinstance(raw, dict):
        return None
    fan, delta = raw.get("fan"), raw.get("score_delta")
    if (type(fan) is not int or fan < 1 or not isinstance(delta, list)
            or len(delta) != 4 or any(type(x) is not int for x in delta)):
        return None
    if sum(delta) != 0:
        raise ValueError("生产结算分向量不守恒")
    details = raw.get("details")
    if not isinstance(details, list) or not all(isinstance(x, str) for x in details):
        return None
    return {"fan": fan, "score_delta_by_physical_seat": delta,
            "focal_delta": delta[seat], "details": details}


def _route_value(route: dict, seat: int) -> dict | None:
    """条件见证保持条件身份与公开容量，绝不解释成真实摸牌概率。"""

    settlement = _settlement(route.get("conditional_settlement"), seat)
    tiles = route.get("useful_tiles")
    if settlement is None or not isinstance(tiles, list):
        return None
    by_tile = {}
    for tile in tiles:
        if not isinstance(tile, dict):
            return None
        code, count = tile.get("code"), tile.get("remaining_estimate")
        if (not isinstance(code, str) or type(count) is not int
                or count < 0 or count > 4 or code in by_tile):
            return None
        by_tile[code] = count
    if not by_tile:
        return None
    conditions = route.get("conditions")
    if not isinstance(conditions, dict):
        return None
    return {"settlement": settlement,
            "public_capacity_upper": sum(by_tile.values()),
            "tile_types_with_public_capacity": sum(v > 0 for v in by_tile.values()),
            "public_remaining_by_tile": by_tile,
            "draw_kind": conditions.get("draw_kind"),
            "followup_discard": route.get("followup_discard")}


def _choice(candidate: dict, seat: int, immediate_delta: int) -> dict:
    """一个非胡合法动作的单次本人后继条件价值，未知覆盖显式记录。"""

    value = candidate.get("value_facts") or {}
    raw_routes = value.get("routes")
    known = []
    malformed = 0
    for route in raw_routes if isinstance(raw_routes, list) else []:
        parsed = _route_value(route, seat) if isinstance(route, dict) else None
        if parsed is None:
            malformed += 1
        else:
            known.append(parsed)
    best = (max(known, key=lambda item: (item["settlement"]["focal_delta"],
                                         item["public_capacity_upper"]))
            if known else None)
    better_by_tile: dict[str, int] = {}
    for route in known:
        if route["settlement"]["focal_delta"] <= immediate_delta:
            continue
        for code, count in route["public_remaining_by_tile"].items():
            better_by_tile[code] = max(better_by_tile.get(code, 0), count)
    return {"action": candidate["action_key"], "value_coverage": value.get("coverage"),
            "route_count": len(known), "malformed_route_count": malformed,
            "best_one_draw_route": best,
            "better_than_now_hu_tile_types": sum(v > 0 for v in better_by_tile.values()),
            "better_than_now_hu_public_capacity_upper": sum(better_by_tile.values())}


def _band_ratio(h: int, b: int | None) -> str:
    """H/B 是零失败损失、单次成功且无对手抢胡的必要成功率；并非估计值。"""

    if b is None:
        return "unknown"
    if b <= h:
        return "one_draw_max_le_immediate"
    if h <= 0:
        return "immediate_nonpositive"
    ratio = h / b
    return ("required_le_quarter" if ratio <= 0.25 else
            "required_le_half" if ratio <= 0.5 else
            "required_le_three_quarters" if ratio <= 0.75 else
            "required_gt_three_quarters")


def main() -> None:
    """只读已确认父代动作和当窗规则/分值事实；不读终局或未来墙。"""

    if OUT.exists():
        raise SystemExit("G13 胡/继续筛查目录已存在，拒绝覆盖")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    if (graph.get("outcome_blind") is not True
            or graph.get("source_frozen_rooms_sha256") != _sha(atlas.FROZEN)
            or graph.get("parent_source_sha256") != frozen["parent_source_sha256"]):
        raise ValueError("跨窗父代身份漂移")
    complete_ids = atlas._complete_ids()
    if len(complete_ids) != graph["complete_official_tables"]:
        raise ValueError("核验完整桌母体漂移")
    rows = []
    counts = Counter()
    scopes = defaultdict(set)
    for room in frozen["rooms"]:
        audit = atlas.source.ROOT / room["audit_dir"]
        file = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if file.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结父代决策文件字节数漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("冻结父代源码摘要漂移")
        accepted = atlas.source._accepted(file)
        for context, raw, plan in atlas.source.screen._iter_decisions(audit):
            if context.get("game_id") not in complete_ids:
                continue
            if (raw.get("window_key") or {}).get("phase") != "draw":
                continue
            ranked = sorted(plan.get("candidates") or [],
                            key=lambda item: item.get("rank", 10**9))
            if not ranked or accepted.get(context.get("decision_id")) != ranked[0].get("action_key"):
                continue
            candidates = (raw.get("rules") or {}).get("legal_candidates") or []
            legal = {candidate["action_key"]: candidate for candidate in candidates}
            if len(legal) != len(candidates):
                raise ValueError("合法候选键重复")
            hu = legal.get("hu")
            if hu is None:
                continue
            observation = raw.get("observation") or {}
            seat = observation.get("seat")
            if type(seat) is not int or not 0 <= seat < 4:
                raise ValueError("合法胡窗口本人座位缺失")
            immediate = _settlement((hu.get("value_facts") or {}).get("immediate_settlement"), seat)
            if immediate is None:
                counts["hu_immediate_unknown"] += 1
                continue
            parent = ranked[0]["action_key"]
            if parent not in legal:
                raise ValueError("已接受父代动作不在合法集合")
            if parent != "hu" and not (parent.startswith("discard:") or parent.startswith("gang:")):
                counts["parent_other_family"] += 1
                continue
            options = [_choice(candidate, seat, immediate["focal_delta"])
                       for candidate in candidates
                       if candidate["action_key"].startswith(("discard:", "gang:"))]
            parent_choice = next((option for option in options if option["action"] == parent), None)
            best = max((option for option in options if option["best_one_draw_route"] is not None),
                       key=lambda option: (
                           option["best_one_draw_route"]["settlement"]["focal_delta"],
                           option["best_one_draw_route"]["public_capacity_upper"]),
                       default=None)
            best_delta = (None if best is None else
                          best["best_one_draw_route"]["settlement"]["focal_delta"])
            selected = parent_choice if parent != "hu" else best
            selected_delta = (None if selected is None or selected["best_one_draw_route"] is None
                              else selected["best_one_draw_route"]["settlement"]["focal_delta"])
            kind = "parent_hu" if parent == "hu" else "parent_continue"
            counts[kind] += 1
            scopes[kind].add(context["game_id"])
            if best_delta is None:
                counts[kind + "_all_continue_route_unknown"] += 1
            else:
                counts[kind + "_" + _band_ratio(immediate["focal_delta"], best_delta)] += 1
            if selected_delta is not None:
                counts[kind + "_selected_" + _band_ratio(immediate["focal_delta"], selected_delta)] += 1
            if kind == "parent_continue" and parent_choice is not None:
                if parent_choice["best_one_draw_route"] is None:
                    counts["parent_continue_own_route_unknown"] += 1
                if parent_choice["better_than_now_hu_public_capacity_upper"] > 0:
                    counts["parent_continue_own_better_witness"] += 1
                    scopes["parent_continue_own_better_witness"].add(context["game_id"])
            if kind == "parent_hu" and best is not None:
                if best["better_than_now_hu_public_capacity_upper"] > 0:
                    counts["parent_hu_some_better_witness"] += 1
                    scopes["parent_hu_some_better_witness"].add(context["game_id"])
            scores = {item.get("action_key"): item.get("total_score") for item in ranked}
            parent_score, hu_score = scores.get(parent), scores.get("hu")
            if (type(parent_score) in (int, float) and type(hu_score) in (int, float)
                    and math.isfinite(float(parent_score)) and math.isfinite(float(hu_score))):
                score_gap = round(float(parent_score) - float(hu_score), 6)
            else:
                score_gap = None
            rows.append({"room_id": room["room_id"], "game_id": context["game_id"],
                         "round_no": context["round_no"],
                         "trigger_seq": context["trigger_seq"], "seat": seat,
                         "parent_action": parent,
                         "white_count": (observation.get("my_hand") or []).count("白"),
                         "baotou_before": (observation.get("rule_state") or {}).get("baotou"),
                         "chain_count": (observation.get("rule_state") or {}).get("chain_count"),
                         "wall_remaining": observation.get("remaining_tile_count"),
                         "immediate_hu": immediate,
                         "parent_minus_hu_policy_score": score_gap,
                         "best_legal_continue": best,
                         "parent_continue": parent_choice,
                         "all_continue_options": options})
    if (counts["parent_hu"] != graph["event_counts"]["accepted_draw_hu"]
            or counts["parent_continue"] != graph["markers"]["continue_to_hu"]["windows"]):
        raise ValueError("胡/继续已确认窗口数与跨窗图谱不符")
    OUT.mkdir(parents=True)
    stream_path = _project_file(_PROJECT_ROOT, OUT / "rows.jsonl.gz")
    with stream_path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            for row in rows:
                compressed.write((json.dumps(row, ensure_ascii=False, sort_keys=True,
                                             separators=(",", ":")) + "\n").encode("utf-8"))
    result = {"schema": "g13-hu-continue-value-screen/1", "outcome_blind": True,
              "analysis_script_sha256": _sha(Path(__file__)),
              "source_frozen_rooms_sha256": _sha(atlas.FROZEN),
              "cross_window_graph_sha256": _sha(GRAPH),
              "parent_source_sha256": frozen["parent_source_sha256"],
              "complete_official_tables": len(complete_ids),
              "counts": dict(sorted(counts.items())),
              "scopes": {name: {"complete_tables": len(ids),
                                "conditional_gain_for_plus2_all_tables":
                                    2 * len(complete_ids) / len(ids)}
                         for name, ids in sorted(scopes.items())},
              "rows": len(rows), "rows_sha256": _sha(stream_path),
              "boundary": "立即胡 score_delta 是当窗可确定积分；继续路线仅为生产规则的下一次本人摸牌条件见证，未见牌容量不是概率，缺少对手先胡、抓打圈后继和全程收益。H/B 只是在零失败损失和一跳成功假设下的必要成功率，不是估计成功率；高条件番不证明弃胡净增益。"}
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"counts": result["counts"], "scopes": result["scopes"]},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
