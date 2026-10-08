#!/usr/bin/env python3
"""G11 结果盲纵向审计：本人两次正常摸打之间的普通型路线退化。"""

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
FROZEN = atlas.FROZEN
G10 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g10-route-option-screen-20260927/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g11-longitudinal-route-audit-20260927/result.json')


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hand(observation: dict) -> tuple[Counter, Counter, int] | None:
    """返回动作前 14/11 张、去当前摸牌后的前态及副露数；非正常摸牌弃权。"""

    seat, melds = observation.get("seat"), observation.get("melds")
    if (type(seat) is not int or not isinstance(melds, list) or not 0 <= seat < len(melds)
            or not isinstance(melds[seat], list)):
        return None
    count = len(melds[seat])
    hand, drawn = observation.get("my_hand"), observation.get("drawn_tile")
    if not isinstance(hand, list) or not isinstance(drawn, str) or len(hand) != 14 - 3 * count:
        return None
    full = Counter(hand)
    if full[drawn] <= 0:
        return None
    before = full.copy()
    before[drawn] -= 1
    if before[drawn] == 0:
        del before[drawn]
    return full, before, count


def _after_discard(full: Counter, action: str) -> Counter | None:
    if not action.startswith("discard:"):
        return None
    tile = action.split(":", 1)[1]
    if full[tile] <= 0:
        return None
    after = full.copy()
    after[tile] -= 1
    if after[tile] == 0:
        del after[tile]
    return after


def _support_shape(facts: dict, field: str) -> tuple[int, int] | None:
    """返回公开剩余有效张容量与正支持牌种数；未知不按零处理。"""

    entries = facts.get(field)
    if not isinstance(entries, list):
        return None
    values = [item.get("remaining_estimate") for item in entries]
    if any(type(value) is not int or value < 0 for value in values):
        return None
    return sum(values), sum(value > 0 for value in values)


def _draw_rows(complete_ids: set[str], frozen: dict) -> tuple[list[dict], Counter]:
    """只索引明确接受且可逐张复原的正常本人摸牌弃牌窗口。"""

    rows = []
    counts = Counter()
    for room in frozen["rooms"]:
        audit = atlas.source.ROOT / room["audit_dir"]
        file = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if file.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结房决策文件字节数漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("冻结 R18 v2 父代源码摘要漂移")
        accepted = atlas.source._accepted(file)
        for context, raw, plan in atlas.source.screen._iter_decisions(audit):
            if context.get("game_id") not in complete_ids:
                continue
            if (raw.get("window_key") or {}).get("phase") != "draw":
                continue
            ranked = sorted(plan.get("candidates") or [],
                            key=lambda item: item.get("rank", 10**9))
            if not ranked or not isinstance(ranked[0].get("action_key"), str):
                counts["draw_unranked"] += 1
                continue
            parent = ranked[0]["action_key"]
            if not parent.startswith("discard:") or accepted.get(context.get("decision_id")) != parent:
                counts["draw_not_accepted_parent_discard"] += 1
                continue
            parsed = _hand(raw["observation"])
            if parsed is None:
                counts["draw_not_normal_with_visible_tile"] += 1
                continue
            full, before, own_melds = parsed
            after = _after_discard(full, parent)
            if after is None:
                raise ValueError("已接受父代弃牌不在本人完整手牌")
            candidates = (raw.get("rules") or {}).get("legal_candidates") or []
            legal = {item["action_key"]: item.get("facts") or {} for item in candidates}
            if len(legal) != len(candidates) or parent not in legal:
                raise ValueError("已接受父代动作规则事实缺失或键重复")
            current = legal[parent]
            standard = atlas._int(current, "standard_shanten_after")
            combined = atlas._int(current, "shanten_after")
            if standard is None or combined is None:
                counts["draw_route_unknown"] += 1
                continue
            scores = {item["action_key"]: item.get("total_score") for item in ranked}
            traces = {item["action_key"]: ((item.get("score_trace") or {}).get("detail") or {})
                      for item in ranked}
            rows.append({"room_id": room["room_id"], "game_id": context["game_id"],
                         "round_no": context["round_no"], "seat": raw["observation"]["seat"],
                         "trigger_seq": context["trigger_seq"], "parent_action": parent,
                         "drawn_tile": raw["observation"]["drawn_tile"],
                         "own_melds": own_melds, "before": before, "after": after,
                         "standard": standard, "combined": combined,
                         "seven_pairs": atlas._int(current, "seven_pairs_shanten_after"),
                         "white_count": full["白"],
                         "legal": legal, "scores": scores, "traces": traces,
                         "wall_remaining": raw["observation"].get("remaining_tile_count")})
            counts["accepted_normal_draw_discards"] += 1
    return rows, counts


def main() -> None:
    """只用前一已确认手牌与当前动作前合法事实；后续积分/未来墙不入样本。"""

    if OUT.exists():
        raise SystemExit("G11 纵向路线审计已存在，拒绝覆盖")
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    complete_ids = atlas._complete_ids()
    g10 = json.loads(G10.read_text(encoding="utf-8"))
    if g10.get("outcome_blind") is not True or g10.get("source_parent_sha256") != frozen["parent_source_sha256"]:
        raise ValueError("G10 结果盲对照或父代身份不符")
    g10_windows = {(row["game_id"], row["round_no"], row["trigger_seq"])
                   for row in g10["rows"]}
    rows, counts = _draw_rows(complete_ids, frozen)
    by_round = defaultdict(list)
    seen = set()
    for row in rows:
        key = (row["game_id"], row["round_no"], row["seat"], row["trigger_seq"])
        if key in seen:
            raise ValueError("已接受正常摸打窗口重复")
        seen.add(key)
        by_round[key[:3]].append(row)
    regressions = []
    scopes = defaultdict(set)
    width_counts = Counter()
    width_scopes = defaultdict(set)
    width_rows = []
    for sequence in by_round.values():
        sequence.sort(key=lambda row: row["trigger_seq"])
        for prior, current in zip(sequence, sequence[1:]):
            counts["consecutive_normal_draw_pairs"] += 1
            if prior["own_melds"] != current["own_melds"]:
                counts["meld_changed_between_draws"] += 1
                continue
            if prior["after"] != current["before"]:
                counts["hand_not_same_plus_one_draw"] += 1
                continue
            counts["mechanically_matched_pairs"] += 1
            parent_facts = current["legal"][current["parent_action"]]
            tsumogiri = "discard:" + current["drawn_tile"]
            stay_facts = current["legal"].get(tsumogiri)
            if stay_facts is not None and tsumogiri != current["parent_action"]:
                parent_shape = _support_shape(parent_facts, "standard_useful_tiles")
                stay_shape = _support_shape(stay_facts, "standard_useful_tiles")
                stay_standard = atlas._int(stay_facts, "standard_shanten_after")
                stay_combined = atlas._int(stay_facts, "shanten_after")
                parent_score = current["scores"].get(current["parent_action"])
                stay_score = current["scores"].get(tsumogiri)
                if (parent_shape is not None and stay_shape is not None
                        and stay_standard is not None and stay_combined is not None
                        and type(parent_score) in (int, float)
                        and type(stay_score) in (int, float)):
                    width_counts["comparable_stay_previous_hand"] += 1
                    if stay_standard == prior["standard"] == current["standard"]:
                        width_counts["same_ordinary_shanten"] += 1
                        more_breadth = stay_shape[1] > parent_shape[1]
                        more_capacity = stay_shape[0] > parent_shape[0]
                        if more_breadth:
                            width_counts["stay_more_tile_types"] += 1
                        if more_capacity:
                            width_counts["stay_more_capacity"] += 1
                        if more_breadth and stay_shape[0] >= parent_shape[0]:
                            width_counts["stay_breadth_and_capacity_not_lower"] += 1
                            width_scopes["breadth_and_capacity_not_lower"].add(current["game_id"])
                            same_combined = stay_combined <= current["combined"]
                            if same_combined:
                                width_counts["same_combined"] += 1
                                width_scopes["same_combined"].add(current["game_id"])
                            key = (current["game_id"], current["round_no"], current["trigger_seq"])
                            if key in g10_windows:
                                width_counts["g10_overlap"] += 1
                            elif same_combined:
                                width_counts["same_combined_outside_g10"] += 1
                                width_scopes["same_combined_outside_g10"].add(current["game_id"])
                            gap = float(parent_score) - float(stay_score)
                            width_counts["score_gap_" + ("zero" if gap == 0 else
                                                         "le_10" if 0 < gap <= 10 else
                                                         "gt_10" if gap > 10 else "negative")] += 1
                            width_rows.append({
                                "room_id": current["room_id"], "game_id": key[0],
                                "round_no": key[1], "seat": current["seat"],
                                "prior_seq": prior["trigger_seq"], "trigger_seq": key[2],
                                "drawn_tile": current["drawn_tile"],
                                "parent_action": current["parent_action"],
                                "stay_action": tsumogiri,
                                "ordinary_shanten": current["standard"],
                                "parent_standard_shape": list(parent_shape),
                                "stay_standard_shape": list(stay_shape),
                                "parent_combined_shanten": current["combined"],
                                "stay_combined_shanten": stay_combined,
                                "parent_combined_shape": _support_shape(parent_facts, "useful_tiles"),
                                "stay_combined_shape": _support_shape(stay_facts, "useful_tiles"),
                                "parent_seven_pairs_shanten": current["seven_pairs"],
                                "stay_seven_pairs_shanten": atlas._int(stay_facts, "seven_pairs_shanten_after"),
                                "parent_score": float(parent_score),
                                "stay_score": float(stay_score),
                                "parent_score_trace": {
                                    key: current["traces"].get(current["parent_action"], {}).get(key)
                                    for key in ("base_score", "river_part", "risk_units", "style_part")},
                                "stay_score_trace": {
                                    key: current["traces"].get(tsumogiri, {}).get(key)
                                    for key in ("base_score", "river_part", "risk_units", "style_part")},
                                "score_gap": gap, "white_count": current["white_count"],
                                "wall_remaining": current["wall_remaining"],
                                "g10_window_overlap": key in g10_windows})
            if current["standard"] <= prior["standard"]:
                continue
            counts["ordinary_route_regression"] += 1
            preserve = []
            for action, facts in current["legal"].items():
                if not action.startswith("discard:"):
                    continue
                standard = atlas._int(facts, "standard_shanten_after")
                combined = atlas._int(facts, "shanten_after")
                score = current["scores"].get(action)
                if standard is None or combined is None or type(score) not in (int, float):
                    continue
                if standard <= prior["standard"]:
                    preserve.append({"action": action, "standard": standard,
                                     "combined": combined, "score": float(score),
                                     "standard_support": atlas._capacity(facts, "standard_useful_tiles"),
                                     "combined_support": atlas._capacity(facts, "useful_tiles"),
                                     "seven_pairs": atlas._int(facts, "seven_pairs_shanten_after")})
            preserve.sort(key=lambda row: (-row["score"], row["action"]))
            if not preserve:
                counts["regression_no_legal_preserve"] += 1
                continue
            best = preserve[0]
            score_parent = current["scores"].get(current["parent_action"])
            if type(score_parent) not in (int, float):
                counts["regression_parent_score_unknown"] += 1
                continue
            same_combined = [item for item in preserve if item["combined"] <= current["combined"]]
            tsumogiri_preserves = any(item["action"] == tsumogiri for item in preserve)
            key = (current["game_id"], current["round_no"], current["trigger_seq"])
            record = {"room_id": current["room_id"], "game_id": key[0],
                      "round_no": key[1], "seat": current["seat"],
                      "prior_seq": prior["trigger_seq"], "trigger_seq": key[2],
                      "prior_action": prior["parent_action"],
                      "parent_action": current["parent_action"],
                      "drawn_tile": current["drawn_tile"],
                      "prior_standard_shanten": prior["standard"],
                      "parent_standard_shanten": current["standard"],
                      "parent_combined_shanten": current["combined"],
                      "parent_seven_pairs_shanten": current["seven_pairs"],
                      "prior_seven_pairs_shanten": prior["seven_pairs"],
                      "white_count": current["white_count"],
                      "own_melds": current["own_melds"],
                      "wall_remaining": current["wall_remaining"],
                      "preserve_options": len(preserve),
                      "same_or_better_combined_options": len(same_combined),
                      "best_preserve": best,
                      "parent_score": float(score_parent),
                      "best_preserve_score_gap": float(score_parent) - best["score"],
                      "tsumogiri_preserves": tsumogiri_preserves,
                      "g10_window_overlap": key in g10_windows}
            regressions.append(record)
            for name, passed in (("any_preserve", True),
                                 ("same_combined_preserve", bool(same_combined)),
                                 ("tsumogiri_preserve", tsumogiri_preserves),
                                 ("g10_overlap", key in g10_windows)):
                if passed:
                    counts[name + "_windows"] += 1
                    scopes[name].add(current["game_id"])
    result = {"schema": "g11-longitudinal-route-audit/1", "outcome_blind": True,
              "frozen_rooms_sha256": _sha(FROZEN), "g10_screen_sha256": _sha(G10),
              "parent_source_sha256": frozen["parent_source_sha256"],
              "complete_official_tables": len(complete_ids),
              "counts": dict(sorted(counts.items())),
              "scopes": {name: {"complete_tables": len(ids),
                                "conditional_gain_for_plus2_all_tables":
                                    2 * len(complete_ids) / len(ids)}
                         for name, ids in sorted(scopes.items())},
              "width_counts": dict(sorted(width_counts.items())),
              "width_scopes": {name: {"complete_tables": len(ids),
                                       "conditional_gain_for_plus2_all_tables":
                                           2 * len(complete_ids) / len(ids)}
                               for name, ids in sorted(width_scopes.items())},
              "width_rows": width_rows,
              "regression_rows": regressions,
              "boundary": "只审父代自然轨迹中连续正常本人摸打的动作前手牌与合法事实；后一窗仅在到达时可见，非前一窗的预言或收益标签。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ("regression_rows", "width_rows")},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
