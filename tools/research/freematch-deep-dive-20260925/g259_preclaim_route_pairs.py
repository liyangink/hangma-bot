#!/usr/bin/env python3
"""G259：结果盲审计吃碰前普通型／七对近路线的强手动作对与负控。"""

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

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import c31_action_layer_gap as c31
import c32_cards as c32
import g05_strong_draw_reconstruction as g05
import g17_one_draw_value_gap as g17
import g18_strict_two_draw_probe as g18
import g49_natural_route_policy as g49
import g52_g49_shared_horizon_probe as g52_probe
import g52_shared_horizon as g52
import g61_strong_draw_shape_profile as shape_code
import g87_post_claim_score_trace as g87
from hangma_bot.application.audit_codec import rule_candidate_to_json
from hangma_bot.hangma.candidate_facts import FactsAnalysisError
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
G61 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g61-strong-draw-action-atlas-20260927')
G11_SCORER = "G11-SHAPE-RISK-PARETO-V1.py"
PEERS = ("xuanwu_2346", "tengshe_0638")


def sha(path: Path) -> str:
    """为冻结输入、脚本和输出计算字节级 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    """读取本地已冻结结果盲 JSON，不访问赛事网络或赛后标签。"""

    return json.loads(path.read_text(encoding="utf-8"))


def key(peer: str, room: str, window: dict) -> tuple:
    """强手、房、桌、单局、官方摸牌序号、座位共同定位动作窗。"""

    return (peer, room, window["game_id"], window["round_no"],
            window["draw_seq"], window["seat"])


def score_entries(result: dict) -> dict[str, dict]:
    """校验旧评分器全量合法候选输出，并按动作键索引。"""

    if result.get("status") != "SCORED":
        raise ValueError("冻结评分器未返回 SCORED")
    entries = {entry["action_key"]: entry for entry in result["entries"]}
    if len(entries) != len(result["entries"]):
        raise ValueError("评分动作键重复")
    return entries


def top(entries: dict[str, dict]) -> str:
    """按 G05 的分数降序、动作键升序选择。"""

    return g87.argmax({name: float(entry["score"]) for name, entry in entries.items()})


def white_bucket(hand: list[str]) -> str:
    """把行动前白板实持数归为 0、1、至少 2。"""

    count = hand.count("白")
    return "2plus" if count >= 2 else str(count)


def context(observation: dict, parent_fact: dict) -> str:
    """同情境只用行动前可见状态和父代合法弃牌后的规则向听。"""

    seat = observation["seat"]
    opponent_max = max(len(melds) for i, melds in enumerate(observation["melds"])
                       if i != seat)
    wall = observation["remaining_tile_count"]
    if parent_fact["seven"] is None:
        raise ValueError("近路线情境缺七对向听")
    return "|".join((
        white_bucket(observation["my_hand"]),
        str(parent_fact["combined"]),
        str(parent_fact["ordinary"] - parent_fact["seven"]),
        "0-29" if wall < 30 else "30-54" if wall < 55 else "55plus",
        "2plus" if opponent_max >= 2 else str(opponent_max),
    ))


def retained_white(observation: dict, action: str) -> int:
    """候选弃牌后的白板实持数，不把白板预绑定到普通或七对路线。"""

    if not action.startswith("discard:"):
        raise ValueError("动作不是弃牌")
    return observation["my_hand"].count("白") - (action == "discard:白")


def support_delta(parent: dict | None, other: dict | None) -> dict | None:
    """保留有效牌逐码公开容量及码数、容量差；零余量不算有效码。"""

    if parent is None or other is None:
        return None
    return {
        "codes": other["codes"] - parent["codes"],
        "capacity": other["capacity"] - parent["capacity"],
        "parent_by_tile": {k: v for k, v in parent["by_tile"].items() if v > 0},
        "other_by_tile": {k: v for k, v in other["by_tile"].items() if v > 0},
    }


def pair(parent: dict, other: dict, observation: dict) -> dict:
    """强手或备选减父代的两路线动作事实；只在同向听层比较有效牌。"""

    result = {
        "parent_shanten": {name: parent[name] for name in ("ordinary", "seven", "combined")},
        "other_shanten": {name: other[name] for name in ("ordinary", "seven", "combined")},
        "shanten_delta": {name: other[name] - parent[name]
                          for name in ("ordinary", "seven", "combined")},
        "white_retained_parent": retained_white(observation, parent["action"]),
        "white_retained_other": retained_white(observation, other["action"]),
        "baotou_parent": parent["baotou_after"],
        "baotou_other": other["baotou_after"],
    }
    for name, shanten in (("ordinary", "ordinary"), ("seven", "seven"),
                          ("combined", "combined")):
        field = "support" if name == "combined" else name + "_support"
        result[name + "_support"] = (
            support_delta(parent[field], other[field])
            if result["shanten_delta"][shanten] == 0 else None
        )
    return result


def trade(pair_data: dict) -> bool:
    """旧路线同层时普通型双宽、七对公开容量下降的观察性取舍。"""

    if any(value != 0 for value in pair_data["shanten_delta"].values()):
        return False
    ordinary = pair_data["ordinary_support"]
    seven = pair_data["seven_support"]
    return (ordinary is not None and seven is not None and
            ordinary["codes"] > 0 and ordinary["capacity"] > 0 and
            seven["capacity"] < 0 and
            pair_data["white_retained_other"] == pair_data["white_retained_parent"])


def fact(action: str, candidate) -> dict:
    """把生产规则事实转换成与冻结 G61 牌形事实同口径的记录。"""

    result = shape_code.fact(candidate.facts)
    if result is None or result["completeness"] != "complete":
        raise ValueError("合法弃牌的规则事实不完整")
    return dict(result, action=action)


def candidate_mass(candidate, seat: int) -> int | None:
    """复用 G17 一次本人普通自摸的公开容量×本人结算条件质量。"""

    return g17._one_draw_mass(rule_candidate_to_json(candidate), seat)


def plan_for(entries: dict[str, dict]) -> SimpleNamespace:
    """为冻结 G49 单窗选择器提供与 R18 排序等价的只读最小计划。"""

    ordered = sorted(entries.values(), key=lambda e: (-e["score"], e["action_key"]))
    return SimpleNamespace(candidates=tuple(SimpleNamespace(
        action_key=e["action_key"], total_score=e["score"]) for e in ordered))


def two_draw_pair(observation, candidates: dict, parent: str, strong: str,
                  config: RuleConfig) -> dict:
    """同一观察下两臂各计算两次本人摸牌条件值，不模拟未来实际牌墙。"""

    result = {}
    try:
        for label, action in (("parent", parent), ("strong", strong)):
            root = g52.evaluate_root(
                observation, rule_candidate_to_json(candidates[action]), config)
            result[label] = {**g18._summary(root), "routes": g52_probe._route_summary(root)}
    except (ValueError, FactsAnalysisError) as exc:
        return {"unavailable": type(exc).__name__ + ": " + str(exc)[:180]}
    return {"parent": result["parent"], "strong": result["strong"],
            "unrestricted_s1_delta": (
                result["strong"]["conditional_value"]["1.0"]["unrestricted"] -
                result["parent"]["conditional_value"]["1.0"]["unrestricted"]),
            "restricted_s1_delta": (
                result["strong"]["conditional_value"]["1.0"]["restricted"] -
                result["parent"]["conditional_value"]["1.0"]["restricted"])}


def write_jsonl(path: Path, rows: list[dict]) -> None:
    """原子语义拒绝覆盖已有机读证据。"""

    with path.open("x", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True,
                                    allow_nan=False) + "\n")


def main() -> None:
    """筛近路线严格目标、全量同格父代一致负控与小范围条件二摸。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path,
                        default=_project_file(_PROJECT_ROOT, HERE / "evidence/g259-preclaim-route-pairs-20260929"))
    args = parser.parse_args()
    out = args.output_dir
    if out.exists() and any(out.iterdir()):
        raise SystemExit("输出目录已有文件，拒绝覆盖")

    batch = read(_project_file(_PROJECT_ROOT, G61 / "result.json"))
    shape = read(_project_file(_PROJECT_ROOT, G61 / "shape_profile.json"))
    if (batch["outcome_labels_opened"] is not False or
            shape["outcome_labels_opened"] is not False or len(batch["units"]) != 32):
        raise ValueError("G61 冻结观察或结果盲标志漂移")
    strict = {}
    for row in shape["strict_discard_rows"]:
        if row["own_meld_count"] != 0 or row["parent_fact"]["seven"] is None:
            continue
        if abs(row["parent_fact"]["ordinary"] - row["parent_fact"]["seven"]) > 1:
            continue
        k = (row["peer"], row["room"], row["game_id"], row["round_no"], row["draw_seq"])
        if k in strict:
            raise ValueError("G61 严格近路线目标重复")
        strict[k] = row
    if len(strict) != 668:
        raise ValueError("G61 近路线严格目标分母漂移")

    target_windows, control_windows = [], []
    source_sha = {}
    no_meld = Counter()
    for unit, manifest in sorted(batch["units"].items()):
        peer, room = unit.split("/", 1)
        if peer not in PEERS:
            raise ValueError("未知强手")
        path = _project_file(_PROJECT_ROOT, G61 / "rooms" / f"{peer}--{room}" / "windows.json")
        if sha(path) != manifest["windows_sha256"]:
            raise ValueError("G61 房窗口摘要漂移：" + unit)
        source_sha[unit] = manifest["windows_sha256"]
        windows = read(path)["windows"]
        if len(windows) != manifest["counts"]["legal_verified_windows"]:
            raise ValueError("G61 合法窗口数漂移")
        for window in windows:
            if window["own_meld_count"] != 0:
                continue
            no_meld[peer] += 1
            k = key(peer, room, window)
            if k[:5] in strict:
                target_windows.append((peer, room, window, strict[k[:5]]))
            elif window["parent_agrees"]:
                control_windows.append((peer, room, window))
    if len(target_windows) != 668 or len({key(p, r, w) for p, r, w, _ in target_windows}) != 668:
        raise ValueError("目标与 G61 逐窗观察未一一对账")

    parent_scorer = c31.load_parent()
    g11_scorer, _ = c32.load_scorer(G11_SCORER)
    if g11_scorer is None:
        raise ValueError("G11 评分器未装配")
    config = RuleConfig(ruleset_version="hangma-mvp-v10-public-counts",
                        base_score=1, you_cai_bi_kao=False)
    target_rows = []
    target_contexts = set()
    trade_contexts = set()
    for peer, room, window, frozen in target_windows:
        obs_json = window["observation"]
        if obs_json["melds"][obs_json["seat"]]:
            raise ValueError("目标已副露，不属于吃碰前七对路线")
        observation = observation_from_json(obs_json)
        request = g87.request_for(observation)
        candidates = {item.action_key: item for item in request.rules.legal_candidates}
        view = g05.build_scoring_view(request, value_limits=c31.VALUE_LIMITS).candidate_view()
        entries = score_entries(parent_scorer(view))
        g11 = score_entries(g11_scorer(view))
        if (top(entries) != window["parent_top_action"] or
                set(entries) != set(window["legal_action_keys"]) or
                frozen["strong_action"] != window["actual_action"] or
                frozen["parent_action"] != window["parent_top_action"] or
                abs(entries[frozen["parent_action"]]["score"] -
                    entries[frozen["strong_action"]]["score"] -
                    frozen["parent_score_gap"]) > 1e-8):
            raise ValueError("目标动作、合法候选或 R18 原分差漂移")
        parent = dict(frozen["parent_fact"], action=frozen["parent_action"])
        strong = dict(frozen["strong_fact"], action=frozen["strong_action"])
        delta = pair(parent, strong, obs_json)
        ctx = context(obs_json, parent)
        target_contexts.add((peer, ctx))
        try:
            g49_action, g49_info = g49.select(request, plan_for(entries))
        except (ValueError, FactsAnalysisError) as exc:
            g49_action, g49_info = None, {"reason": "unavailable", "type": type(exc).__name__}
        parent_candidate = candidates[parent["action"]]
        strong_candidate = candidates[strong["action"]]
        row = {
            "peer": peer, "room": room, "game_id": window["game_id"],
            "round_no": window["round_no"], "draw_seq": window["draw_seq"],
            "seat": window["seat"], "context": ctx,
            "parent_action": parent["action"], "strong_action": strong["action"],
            "pair": delta, "route_trade": trade(delta),
            "parent_score_gap": frozen["parent_score_gap"],
            "parent_risk_units": entries[parent["action"]]["trace"].get("risk_units"),
            "strong_risk_units": entries[strong["action"]]["trace"].get("risk_units"),
            "first_hu_mass_parent": candidate_mass(parent_candidate, observation.seat),
            "first_hu_mass_strong": candidate_mass(strong_candidate, observation.seat),
            "old_tops": {"g11": top(g11), "g49": g49_action or parent["action"],
                         "g88": parent["action"], "g210": parent["action"]},
            "g49_reason": g49_info["reason"],
        }
        if row["route_trade"]:
            trade_contexts.add((peer, ctx))
        # 两摸量具只用在近路线、同层路线取舍且当前综合至多一向听的目标。
        if row["route_trade"] and parent["combined"] <= 1:
            row["two_draw"] = two_draw_pair(
                observation, candidates, parent["action"], strong["action"], config)
        target_rows.append(row)

    control_rows = []
    control_no_meld = Counter(peer for peer, _, _ in control_windows)
    for peer, room, window in control_windows:
        obs_json = window["observation"]
        if obs_json["melds"][obs_json["seat"]]:
            raise ValueError("一致窗已副露")
        observation = observation_from_json(obs_json)
        request = g87.request_for(observation)
        candidates = {item.action_key: item for item in request.rules.legal_candidates}
        action = window["parent_top_action"]
        if action not in candidates:
            raise ValueError("一致窗父代弃牌不合法")
        parent = fact(action, candidates[action])
        if parent["seven"] is None or abs(parent["ordinary"] - parent["seven"]) > 1:
            continue
        ctx = context(obs_json, parent)
        if (peer, ctx) not in target_contexts:
            continue
        view = g05.build_scoring_view(request, value_limits=c31.VALUE_LIMITS).candidate_view()
        entries = score_entries(parent_scorer(view))
        if (top(entries) != action or action != window["actual_action"] or
                set(entries) != set(window["legal_action_keys"])):
            raise ValueError("一致窗父代或合法候选漂移")
        alternatives = []
        for name, candidate in candidates.items():
            if name == action or not name.startswith("discard:"):
                continue
            other = fact(name, candidate)
            delta = pair(parent, other, obs_json)
            if trade(delta):
                alternatives.append({
                    "action": name, "pair": delta,
                    "parent_score_gap": entries[action]["score"] - entries[name]["score"],
                    "parent_risk_units": entries[action]["trace"].get("risk_units"),
                    "other_risk_units": entries[name]["trace"].get("risk_units"),
                })
        closest = min(alternatives, key=lambda a: (a["parent_score_gap"], a["action"])) if alternatives else None
        control_row = {
            "peer": peer, "room": room, "game_id": window["game_id"],
            "round_no": window["round_no"], "draw_seq": window["draw_seq"],
            "seat": window["seat"], "context": ctx,
            "same_context_as_route_trade_target": (peer, ctx) in trade_contexts,
            "agreed_action": action, "parent_shanten": {
                name: parent[name] for name in ("ordinary", "seven", "combined")},
            "route_trade_alternative_count": len(alternatives),
            "closest_route_trade_alternative": closest,
        }
        if closest is not None and parent["combined"] <= 1:
            control_row["two_draw"] = two_draw_pair(
                observation, candidates, action, closest["action"], config)
        control_rows.append(control_row)

    target_rows.sort(key=lambda row: key(row["peer"], row["room"], row))
    control_rows.sort(key=lambda row: key(row["peer"], row["room"], row))
    controls_by_context_room = defaultdict(Counter)
    control_trades_by_context_room = defaultdict(Counter)
    targets_by_context_room = defaultdict(Counter)
    trade_by_context_room = defaultdict(Counter)
    for row in control_rows:
        controls_by_context_room[(row["peer"], row["context"])][row["room"]] += 1
        if row["route_trade_alternative_count"] > 0:
            control_trades_by_context_room[(row["peer"], row["context"])][row["room"]] += 1
    for row in target_rows:
        group = (row["peer"], row["context"])
        targets_by_context_room[group][row["room"]] += 1
        if row["route_trade"]:
            trade_by_context_room[group][row["room"]] += 1
    for row in target_rows:
        group = (row["peer"], row["context"])
        row["other_room_same_context_controls"] = sum(
            n for room, n in controls_by_context_room[group].items() if room != row["room"])
        row["other_room_same_context_trade_available_controls"] = sum(
            n for room, n in control_trades_by_context_room[group].items()
            if room != row["room"])
        row["other_room_same_context_targets"] = sum(
            n for room, n in targets_by_context_room[group].items() if room != row["room"])
        row["other_room_same_context_route_trades"] = sum(
            n for room, n in trade_by_context_room[group].items() if room != row["room"])

    by_peer, by_unit = {}, {}
    for peer in PEERS:
        ts = [row for row in target_rows if row["peer"] == peer]
        cs = [row for row in control_rows if row["peer"] == peer]
        counts = Counter()
        for row in ts:
            counts["targets"] += 1
            counts["route_trade_targets"] += row["route_trade"]
            combined_support = row["pair"]["combined_support"]
            counts["route_trade_combined_capacity_higher"] += (
                row["route_trade"] and combined_support["capacity"] > 0)
            counts["route_trade_combined_capacity_lower"] += (
                row["route_trade"] and combined_support["capacity"] < 0)
            counts["route_trade_old_unmatched"] += row["route_trade"] and all(
                name != row["strong_action"] for name in row["old_tops"].values())
            counts["target_other_room_control"] += row["other_room_same_context_controls"] > 0
            counts["trade_other_room_trade"] += row["route_trade"] and row[
                "other_room_same_context_route_trades"] > 0
            counts["trade_other_room_trade_control"] += (
                row["route_trade"] and
                row["other_room_same_context_trade_available_controls"] > 0)
            counts["g11_matches_strong"] += row["old_tops"]["g11"] == row["strong_action"]
            counts["g49_matches_strong"] += row["old_tops"]["g49"] == row["strong_action"]
            counts["first_hu_mass_strong_higher"] += (
                row["first_hu_mass_parent"] is not None and
                row["first_hu_mass_strong"] is not None and
                row["first_hu_mass_strong"] > row["first_hu_mass_parent"])
            counts["two_draw_evaluated"] += "two_draw" in row
            counts["two_draw_complete"] += "two_draw" in row and "unavailable" not in row["two_draw"]
            if "two_draw" in row and "unavailable" not in row["two_draw"]:
                delta = row["two_draw"]["unrestricted_s1_delta"]
                counts["two_draw_unrestricted_positive"] += delta > 1e-9
                counts["two_draw_unrestricted_negative"] += delta < -1e-9
                counts["two_draw_sign_matches_combined_capacity"] += (
                    (delta > 1e-9 and combined_support["capacity"] > 0) or
                    (delta < -1e-9 and combined_support["capacity"] < 0))
        for row in cs:
            counts["controls"] += 1
            counts["control_route_trade_available"] += row["route_trade_alternative_count"] > 0
            counts["control_in_trade_context"] += row["same_context_as_route_trade_target"]
            counts["control_trade_available_in_trade_context"] += (
                row["same_context_as_route_trade_target"] and
                row["route_trade_alternative_count"] > 0)
            counts["control_trade_available_in_trade_context_combined_le1"] += (
                row["same_context_as_route_trade_target"] and
                row["route_trade_alternative_count"] > 0 and
                row["parent_shanten"]["combined"] <= 1)
            counts["control_two_draw_evaluated"] += "two_draw" in row
            counts["control_two_draw_complete"] += (
                "two_draw" in row and "unavailable" not in row["two_draw"])
            if "two_draw" in row and "unavailable" not in row["two_draw"]:
                delta = row["two_draw"]["unrestricted_s1_delta"]
                capacity = row["closest_route_trade_alternative"]["pair"][
                    "combined_support"]["capacity"]
                counts["control_two_draw_unrestricted_positive"] += delta > 1e-9
                counts["control_two_draw_unrestricted_negative"] += delta < -1e-9
                counts["control_two_draw_sign_matches_combined_capacity"] += (
                    (delta > 1e-9 and capacity > 0) or
                    (delta < -1e-9 and capacity < 0))
        by_peer[peer] = dict(sorted(counts.items()))
        for room in sorted({row["room"] for row in ts + cs}):
            unit_ts = [row for row in ts if row["room"] == room]
            unit_cs = [row for row in cs if row["room"] == room]
            by_unit[peer + "/" + room] = {
                "targets": len(unit_ts), "controls": len(unit_cs),
                "route_trade_targets": sum(row["route_trade"] for row in unit_ts),
                "route_trade_combined_capacity_lower": sum(
                    row["route_trade"] and row["pair"]["combined_support"]["capacity"] < 0
                    for row in unit_ts),
                "route_trade_old_unmatched": sum(
                    row["route_trade"] and all(name != row["strong_action"]
                                               for name in row["old_tops"].values())
                    for row in unit_ts),
                "control_route_trade_available": sum(
                    row["route_trade_alternative_count"] > 0 for row in unit_cs),
                "control_trade_available_in_trade_context": sum(
                    row["same_context_as_route_trade_target"] and
                    row["route_trade_alternative_count"] > 0 for row in unit_cs),
            }

    out.mkdir(parents=True, exist_ok=True)
    target_file = out / "target_pairs.jsonl"
    control_file = out / "matched_controls.jsonl"
    write_jsonl(target_file, target_rows)
    write_jsonl(control_file, control_rows)
    result = {
        "schema": "g259-preclaim-route-pairs/1", "result_blind": True,
        "selection": "本人零副露；父代弃后普通型与七对向听绝对差≤1；强手严格分歧。负控为同强手、同可见情境格且父代与强手一致窗。",
        "context_fields": ["white_before_bucket", "parent_combined_shanten",
                           "parent_ordinary_minus_seven", "wall_remaining_bucket",
                           "opponent_max_melds_bucket"],
        "source_sha256": {"script": sha(Path(__file__)),
                          "g61_result": sha(_project_file(_PROJECT_ROOT, G61 / "result.json")),
                          "g61_shape": sha(_project_file(_PROJECT_ROOT, G61 / "shape_profile.json")),
                          "g61_windows_by_unit": source_sha,
                          "g11_scorer": sha(_project_file(_PROJECT_ROOT, HERE / "candidates" / G11_SCORER)),
                          "g49_selector": sha(_project_file(_PROJECT_ROOT, HERE / "g49_natural_route_policy.py")),
                          "g52_horizon": sha(_project_file(_PROJECT_ROOT, HERE / "g52_shared_horizon.py"))},
        "evidence_sha256": {"target_pairs.jsonl": sha(target_file),
                            "matched_controls.jsonl": sha(control_file)},
        "denominator": {"g61_clean": batch["totals"]["legal_verified_windows"],
                        "no_meld_by_peer": dict(no_meld),
                        "parent_agree_no_meld_by_peer": dict(control_no_meld),
                        "near_route_strict_targets": len(target_rows),
                        "same_context_agree_controls": len(control_rows),
                        "peer_room_units": len(batch["units"]),
                        "physical_rooms": len({row["room"] for row in target_rows})},
        "by_peer": by_peer, "by_peer_room": by_unit,
        "boundary": "只用行动前 PlayerObservation、生产 HangmaRules、冻结 R18 与旧候选；短时两摸仅条件同局继续，不读实际未来牌墙/他家暗手/终局。强手吻合不是收益。",
    }
    (out / "result.json").open("x", encoding="utf-8").write(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2,
                   allow_nan=False) + "\n")
    print(json.dumps({"denominator": result["denominator"], "by_peer": by_peer},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
