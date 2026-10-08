#!/usr/bin/env python3
"""G258：结果盲地连接 G61/G253/G87 的动作对，并构造同情境一致窗负控。

目标动作事实直接复用 G61；目标 R18 评分分量直接复用 G87。只对 G61
父代与强手一致的已吃碰后正常摸打重算生产规则和冻结评分，找同层宽面
备选是否也存在。决不打开官方赛后事件、未来牌墙或终局积分。
"""

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
import ast
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

import c31_action_layer_gap as c31
import c32_cards as c32
import g05_strong_draw_reconstruction as g05
import g61_strong_draw_shape_profile as g61_shape
import g87_post_claim_score_trace as g87
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
EVIDENCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence')
G61 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g61-strong-draw-action-atlas-20260927')
G253 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g253-postclaim-residual-support-20260929/result.json')
G87 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g87-post-claim-score-trace-20260928/result.json')
G88 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g88-post-claim-familiar-behavior-20260928/result.json')
G210 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g210-post-claim-guarded-familiar-20260929/result.json')
G11_SCORER = "G11-SHAPE-RISK-PARETO-V1.py"
G88_SCORER = "G88-POST-CLAIM-FAMILIAR-BIAS-V1.py"
PEERS = ("xuanwu_2346", "tengshe_0638")


def sha(path: Path) -> str:
    """返回冻结输入或本脚本的 SHA-256，不改动源文件。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    """读取本仓结果盲冻结 JSON；调用方只访问事前字段。"""

    return json.loads(path.read_text(encoding="utf-8"))


def key(row: dict) -> tuple:
    """官方房、桌、局、摸牌序号与座位共同定位一个玩家动作窗。"""

    return (row["peer"], row["room"], row["game_id"], row["round_no"],
            row["draw_seq"], row["seat"])


def score_map(result: dict) -> dict[str, dict]:
    """只接受完整的合法候选评分结果，按动作键建立索引。"""

    if result.get("status") != "SCORED":
        raise ValueError("冻结评分器未返回 SCORED")
    entries = {entry["action_key"]: entry for entry in result["entries"]}
    if len(entries) != len(result["entries"]):
        raise ValueError("评分结果动作键重复")
    return entries


def top(entries: dict[str, dict]) -> str:
    """使用 G05 冻结的分数降序、动作键升序选择。"""

    return g87.argmax({action: float(entry["score"])
                       for action, entry in entries.items()})


def context(feature: dict) -> str:
    """G253 粗格上增加当时可见的积分位置与本人副露种类。"""

    return "|".join((feature["white"], feature["own_chi_peng_melds"],
                     feature["wall_remaining"], feature["opponent_max_melds"],
                     feature["score_position"], feature["own_meld_kinds"]))


def observation_feature(window: dict) -> dict:
    """复用 G253 的玩家可见情境提取，避免另造一套观察定义。"""

    from g253_postclaim_residual_support_audit import features

    return features(window)


def retained_white(observation: dict, action: str) -> int:
    """候选弃牌后的白板实持数；只由行动前本人手牌和动作键计算。"""

    if not action.startswith("discard:"):
        raise ValueError("目标动作不是弃牌")
    return observation["my_hand"].count("白") - (action == "discard:白")


def pair(parent: dict, alternate: dict, *, observation: dict) -> dict:
    """逐动作规则事实差，方向一律为备选减父代，保留逐码公开容量。"""

    p = parent["ordinary_support"]
    a = alternate["ordinary_support"]
    if p is None or a is None:
        raise ValueError("已副露弃牌缺普通型有效牌事实")
    pp = {tile: count for tile, count in p["by_tile"].items() if count > 0}
    aa = {tile: count for tile, count in a["by_tile"].items() if count > 0}
    added = {tile: aa[tile] for tile in sorted(aa.keys() - pp.keys())}
    removed = {tile: pp[tile] for tile in sorted(pp.keys() - aa.keys())}
    changed = {tile: aa[tile] - pp[tile] for tile in sorted(aa.keys() & pp.keys())
               if aa[tile] != pp[tile]}
    return {
        "ordinary_shanten_parent": parent["ordinary"],
        "ordinary_shanten_alternate": alternate["ordinary"],
        "combined_shanten_parent": parent["combined"],
        "combined_shanten_alternate": alternate["combined"],
        "seven_pairs_shanten_parent": parent["seven"],
        "seven_pairs_shanten_alternate": alternate["seven"],
        "ordinary_codes_delta": a["codes"] - p["codes"],
        "ordinary_capacity_delta": a["capacity"] - p["capacity"],
        "ordinary_parent_by_tile": pp,
        "ordinary_alternate_by_tile": aa,
        "new_positive_codes": added,
        "lost_positive_codes": removed,
        "changed_shared_code_capacity": changed,
        "baotou_parent": parent["baotou_after"],
        "baotou_alternate": alternate["baotou_after"],
        "white_retained_parent": retained_white(observation, parent["action"]),
        "white_retained_alternate": retained_white(observation, alternate["action"]),
    }


def fact(action: str, candidate) -> dict:
    """从生产规则的候选事实生成与 G61 形状画像同口径的动作记录。"""

    value = g61_shape.fact(candidate.facts)
    if value is None or value["completeness"] != "complete":
        raise ValueError("合法弃牌缺完整规则事实")
    value["action"] = action
    return value


def risk_units(entry: dict) -> float | None:
    """冻结 R18 候选 trace 内的公开邻家风险单位，可空时不放行护栏。"""

    value = entry["trace"].get("risk_units")
    return float(value) if type(value) in (int, float) else None


def pair_with_score(parent: dict, alternate: dict, observation: dict,
                    parent_entry: dict, alternate_entry: dict) -> dict:
    """把动作特异规则差和父代原评分差放在同一记录。"""

    result = pair(parent, alternate, observation=observation)
    p_risk, a_risk = risk_units(parent_entry), risk_units(alternate_entry)
    gap = float(parent_entry["score"]) - float(alternate_entry["score"])
    components = {
        name: g87.component(parent_entry["trace"], name)
              - g87.component(alternate_entry["trace"], name)
        for name in g87.COMPONENTS
    }
    if abs(gap - sum(components.values())) > 1e-8:
        raise ValueError("负控评分分量与原评分差不守恒")
    result.update({
        "parent_score_gap": gap,
        "parent_risk_units": p_risk,
        "alternate_risk_units": a_risk,
        "risk_not_worse": p_risk is not None and a_risk is not None and a_risk <= p_risk,
        "parent_minus_alternate_components": components,
    })
    return result


def choose_challenger(alternatives: list[dict]) -> dict | None:
    """负控中选父代原分最高的双宽备选，避免人为挑最低分稻草人。"""

    if not alternatives:
        return None
    return min(alternatives, key=lambda row: (row["parent_score_gap"],
                                              row["alternate_action"]))


def write_jsonl(path: Path, rows: list[dict]) -> None:
    """一次性写入机读逐窗证据；已有文件一律拒绝覆盖。"""

    with path.open("x", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")


def main() -> None:
    """连接冻结动作对、重算同情境一致窗，并按强手和官方房汇总。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path,
                        default=_project_file(_PROJECT_ROOT, EVIDENCE / "g258-postclaim-action-pairs-20260929"))
    args = parser.parse_args()
    out = args.output_dir
    if out.exists() and any(out.iterdir()):
        raise SystemExit("输出目录已有文件，拒绝覆盖")

    g61 = read_json(_project_file(_PROJECT_ROOT, G61 / "result.json"))
    shape = read_json(_project_file(_PROJECT_ROOT, G61 / "shape_profile.json"))
    g253 = read_json(G253)
    g87_data = read_json(G87)
    g88 = read_json(G88)
    g210 = read_json(G210)
    if (g61["outcome_labels_opened"] is not False or
            shape["outcome_labels_opened"] is not False or
            g253["outcome_labels_opened"] is not False or
            g87_data["terminal_score_labels_opened"] is not False or
            g88["outcome_blind"] is not True or g210["outcome_blind"] is not True):
        raise ValueError("冻结输入不满足结果盲边界")
    if len(g253["target_rows"]) != 1083 or len(g87_data["rows"]) != 1083:
        raise ValueError("G253/G87 目标分母漂移")
    targets = {key(row): row for row in g253["target_rows"]}
    traces = {key(row): row for row in g87_data["rows"]}
    if len(targets) != 1083 or set(targets) != set(traces):
        raise ValueError("G253/G87 目标键不等或重复")
    shapes = {(row["peer"], row["room"], row["game_id"], row["round_no"],
               row["draw_seq"]): row for row in shape["strict_discard_rows"]}
    if len(shapes) != len(shape["strict_discard_rows"]):
        raise ValueError("G61 牌形画像动作窗键重复")
    g88_rows = {key(row): row for row in g88["rows"] if row["panel"] == "g61"}
    if set(g88_rows) != set(targets):
        raise ValueError("G88/G253 G61 目标键不等")
    g210_rows = {}
    for row in g210["rows"]:
        if row["panel"] != "g61":
            continue
        raw = ast.literal_eval(row["key"]) if isinstance(row["key"], str) else row["key"]
        if not isinstance(raw, list) or len(raw) != 4:
            raise ValueError("G210 键格式漂移")
        k = tuple(raw)
        if k in g210_rows:
            raise ValueError("G210 键重复")
        g210_rows[k] = row

    parent_scorer = c31.load_parent()
    g11_scorer, _ = c32.load_scorer(G11_SCORER)
    g88_scorer, _ = c32.load_scorer(G88_SCORER)
    if g11_scorer is None or g88_scorer is None:
        raise ValueError("旧候选评分器不可装配")
    target_contexts = {(row["peer"], context(row["feature"])) for row in targets.values()}
    target_context_shanten = {
        (row["peer"], context(row["feature"]), shapes[key(row)[:5]]["parent_fact"]["ordinary"])
        for row in targets.values()
    }
    target_rows, control_rows = [], []
    seen = set()
    full_postclaim = Counter()
    source_hashes = {}
    for unit, manifest in sorted(g61["units"].items()):
        peer, room = unit.split("/", 1)
        if peer not in PEERS:
            raise ValueError("未知同房强手")
        path = _project_file(_PROJECT_ROOT, G61 / "rooms" / f"{peer}--{room}" / "windows.json")
        if sha(path) != manifest["windows_sha256"]:
            raise ValueError("G61 逐房观察摘要漂移：" + unit)
        source_hashes[unit] = manifest["windows_sha256"]
        windows = read_json(path)["windows"]
        if len(windows) != manifest["counts"]["legal_verified_windows"]:
            raise ValueError("G61 逐房窗口数漂移")
        for window in windows:
            obs_json = window["observation"]
            if not any(m["kind"] in ("chi", "peng")
                       for m in obs_json["melds"][obs_json["seat"]]):
                continue
            full_postclaim[peer] += 1
            feature = observation_feature(window)
            fine = context(feature)
            k = (peer, room, window["game_id"], window["round_no"],
                 window["draw_seq"], window["seat"])
            if k in targets:
                if k in seen:
                    raise ValueError("目标动作窗重复")
                seen.add(k)
                target = targets[k]
                trace = traces[k]
                shape_row = shapes.get(k[:5])
                if shape_row is None:
                    raise ValueError("G61 未保存目标规则动作对")
                if (target["feature"] != feature or
                        target["strong_action"] != window["actual_action"] or
                        target["parent_action"] != window["parent_top_action"] or
                        trace["parent_action"] != target["parent_action"] or
                        trace["strong_action"] != target["strong_action"]):
                    raise ValueError("G61/G253/G87 同窗动作或情境漂移")
                observation = observation_from_json(obs_json)
                request = g87.request_for(observation)
                view = g05.build_scoring_view(request, value_limits=c31.VALUE_LIMITS).candidate_view()
                g11_entries = score_map(g11_scorer(view))
                g88_entries = score_map(g88_scorer(view))
                g11_top, g88_top = top(g11_entries), top(g88_entries)
                if g88_top != g88_rows[k]["candidate_action"]:
                    raise ValueError("G88 旧候选动作与冻结证据漂移")
                proposed = g210_rows.get(k[2:])
                if proposed is not None and proposed["room"] != room:
                    raise ValueError("G210 提案房号漂移")
                g210_top = (proposed["alternate_action"] if proposed is not None and
                            proposed["accepted"] else target["parent_action"])
                pf = dict(shape_row["parent_fact"], action=target["parent_action"])
                af = dict(shape_row["strong_fact"], action=target["strong_action"])
                delta = pair(pf, af, observation=obs_json)
                if (delta["ordinary_codes_delta"] != target["ordinary_codes_delta"] or
                        delta["ordinary_capacity_delta"] != target["ordinary_capacity_delta"] or
                        abs(trace["parent_gap"] - target["parent_score_gap"]) > 1e-8):
                    raise ValueError("G61/G253/G87 规则或评分差漂移")
                if abs(trace["parent_gap"] - sum(
                        trace["component_parent_minus_strong"].values())) > 1e-8:
                    raise ValueError("目标评分分量与原评分差不守恒")
                pr = trace["parent_trace"].get("risk_units")
                ar = trace["strong_trace"].get("risk_units")
                if type(pr) not in (int, float) or type(ar) not in (int, float):
                    raise ValueError("G87 目标风险单位缺失")
                delta.update({
                    "parent_score_gap": trace["parent_gap"],
                    "parent_risk_units": float(pr),
                    "alternate_risk_units": float(ar),
                    "risk_not_worse": ar <= pr,
                    "parent_minus_alternate_components": trace["component_parent_minus_strong"],
                })
                target_rows.append({
                    "peer": peer, "room": room, "game_id": k[2], "round_no": k[3],
                    "draw_seq": k[4], "seat": k[5], "context": fine,
                    "ordinary_shanten": pf["ordinary"],
                    "feature": feature, "parent_action": target["parent_action"],
                    "strong_action": target["strong_action"], "action_pair": delta,
                    "old_tops": {"g11": g11_top, "g88": g88_top,
                                 "g210": g210_top, "risk0": trace["risk0_top"]},
                })
                continue
            if (not window["parent_agrees"] or (peer, fine) not in target_contexts):
                continue
            observation = observation_from_json(obs_json)
            request = g87.request_for(observation)
            view = g05.build_scoring_view(request, value_limits=c31.VALUE_LIMITS).candidate_view()
            parent_entries = score_map(parent_scorer(view))
            g11_entries = score_map(g11_scorer(view))
            g88_entries = score_map(g88_scorer(view))
            parent_action = top(parent_entries)
            if (parent_action != window["parent_top_action"] or
                    parent_action != window["actual_action"] or
                    set(parent_entries) != set(window["legal_action_keys"])):
                raise ValueError("负控冻结父代或合法候选漂移")
            candidates = {candidate.action_key: candidate
                          for candidate in request.rules.legal_candidates}
            if set(candidates) != set(parent_entries):
                raise ValueError("负控规则候选与评分候选不一致")
            pf = fact(parent_action, candidates[parent_action])
            pentry = parent_entries[parent_action]
            wider = []
            guarded = []
            same_support = []
            equal_width_different_support = []
            same_layer_alternatives = 0
            for action, candidate in candidates.items():
                if action == parent_action or not action.startswith("discard:"):
                    continue
                if retained_white(obs_json, action) != retained_white(obs_json, parent_action):
                    continue
                af = fact(action, candidate)
                if af["ordinary"] != pf["ordinary"]:
                    continue
                same_layer_alternatives += 1
                delta = pair_with_score(pf, af, obs_json, pentry, parent_entries[action])
                candidate_record = {"alternate_action": action, **delta}
                if (delta["ordinary_parent_by_tile"] ==
                        delta["ordinary_alternate_by_tile"]):
                    same_support.append(candidate_record)
                elif (delta["ordinary_codes_delta"] == 0 and
                      delta["ordinary_capacity_delta"] == 0):
                    equal_width_different_support.append(candidate_record)
                if delta["ordinary_codes_delta"] > 0 and delta["ordinary_capacity_delta"] > 0:
                    wider.append(candidate_record)
                    if delta["risk_not_worse"]:
                        guarded.append(candidate_record)
            control_rows.append({
                "peer": peer, "room": room, "game_id": k[2], "round_no": k[3],
                "draw_seq": k[4], "seat": k[5], "context": fine,
                "ordinary_shanten": pf["ordinary"],
                "same_context_and_shanten_as_a_target": (
                    peer, fine, pf["ordinary"]) in target_context_shanten,
                "feature": feature, "parent_and_strong_action": parent_action,
                "same_layer_alternative_count": same_layer_alternatives,
                "both_wider_alternative_count": len(wider),
                "risk_guarded_both_wider_alternative_count": len(guarded),
                "same_support_alternative_count": len(same_support),
                "equal_width_different_support_alternative_count": len(
                    equal_width_different_support),
                "closest_both_wider_alternative": choose_challenger(wider),
                "closest_guarded_both_wider_alternative": choose_challenger(guarded),
                "closest_same_support_alternative": choose_challenger(same_support),
                "closest_equal_width_different_support_alternative": choose_challenger(
                    equal_width_different_support),
                "old_tops": {"g11": top(g11_entries), "g88": top(g88_entries)},
            })

    if seen != set(targets) or Counter(row["peer"] for row in target_rows) != {
            "xuanwu_2346": 434, "tengshe_0638": 649}:
        raise ValueError("1,083 个目标窗口未全量对账")
    if full_postclaim != {"xuanwu_2346": 3379, "tengshe_0638": 3856}:
        raise ValueError("G253 已吃碰分母漂移")
    target_rows.sort(key=key)
    control_rows.sort(key=key)
    control_by_context_room = defaultdict(Counter)
    control_by_context_shanten_room = defaultdict(Counter)
    for row in control_rows:
        control_by_context_room[(row["peer"], row["context"])][row["room"]] += 1
        control_by_context_shanten_room[(row["peer"], row["context"],
                                         row["ordinary_shanten"])][row["room"]] += 1
    for row in target_rows:
        groups = control_by_context_room[(row["peer"], row["context"])]
        row["other_room_same_context_controls"] = sum(
            count for room, count in groups.items() if room != row["room"])
        groups = control_by_context_shanten_room[(row["peer"], row["context"],
                                                   row["ordinary_shanten"])]
        row["other_room_same_context_and_shanten_controls"] = sum(
            count for room, count in groups.items() if room != row["room"])

    by_peer, by_room = {}, {}
    for peer in PEERS:
        target_peer = [row for row in target_rows if row["peer"] == peer]
        control_peer = [row for row in control_rows if row["peer"] == peer]
        counter = Counter()
        rooms = defaultdict(set)
        for row in target_peer:
            pair_data = row["action_pair"]
            old = row["old_tops"]
            strong = row["strong_action"]
            both = (pair_data["ordinary_codes_delta"] > 0 and
                    pair_data["ordinary_capacity_delta"] > 0)
            exact_support = (pair_data["ordinary_parent_by_tile"] ==
                             pair_data["ordinary_alternate_by_tile"])
            equal_width = (pair_data["ordinary_codes_delta"] == 0 and
                           pair_data["ordinary_capacity_delta"] == 0)
            counter["targets"] += 1
            counter["target_both_wider"] += both
            counter["target_both_wider_risk_not_worse"] += both and pair_data["risk_not_worse"]
            counter["target_exact_same_ordinary_support"] += exact_support
            counter["target_equal_width_different_support"] += equal_width and not exact_support
            counter["target_strong_risk_higher"] += (
                pair_data["alternate_risk_units"] > pair_data["parent_risk_units"])
            counter["target_strong_risk_lower"] += (
                pair_data["alternate_risk_units"] < pair_data["parent_risk_units"])
            counter["target_strong_risk_equal"] += (
                pair_data["alternate_risk_units"] == pair_data["parent_risk_units"])
            counter["target_white_retained_diff"] += (
                pair_data["white_retained_parent"] != pair_data["white_retained_alternate"])
            counter["target_seven_available"] += pair_data["seven_pairs_shanten_parent"] is not None
            counter["target_baotou_diff"] += (
                pair_data["baotou_parent"] != pair_data["baotou_alternate"])
            counter["target_has_other_room_fine_control"] += row["other_room_same_context_controls"] > 0
            counter["target_has_other_room_fine_shanten_control"] += (
                row["other_room_same_context_and_shanten_controls"] > 0)
            for name, action in old.items():
                counter[f"target_{name}_matches_strong"] += action == strong
            old_match = any(action == strong for action in old.values())
            counter["target_no_old_matches_strong"] += not old_match
            counter["target_both_wider_no_old_match"] += both and not old_match
            rooms["targets"].add(row["room"])
            if both:
                rooms["target_both_wider"].add(row["room"])
            if both and not old_match:
                rooms["target_both_wider_no_old_match"].add(row["room"])
        for row in control_peer:
            counter["controls"] += 1
            same_shanten = row["same_context_and_shanten_as_a_target"]
            counter["control_same_shanten_context"] += same_shanten
            counter["control_both_wider_available"] += row["both_wider_alternative_count"] > 0
            counter["control_both_wider_available_same_shanten_context"] += (
                same_shanten and row["both_wider_alternative_count"] > 0)
            counter["control_guarded_both_wider_available"] += (
                row["risk_guarded_both_wider_alternative_count"] > 0)
            counter["control_same_support_alternative_available"] += (
                row["same_support_alternative_count"] > 0)
            counter["control_equal_width_different_support_available"] += (
                row["equal_width_different_support_alternative_count"] > 0)
            counter["control_g11_changes"] += row["old_tops"]["g11"] != row["parent_and_strong_action"]
            counter["control_g88_changes"] += row["old_tops"]["g88"] != row["parent_and_strong_action"]
            rooms["controls"].add(row["room"])
            if row["both_wider_alternative_count"]:
                rooms["control_both_wider_available"].add(row["room"])
            if same_shanten:
                rooms["control_same_shanten_context"].add(row["room"])
        by_peer[peer] = {"counts": dict(sorted(counter.items())),
                         "rooms": {name: len(values) for name, values in sorted(rooms.items())}}
        for room in sorted(rooms["targets"] | rooms["controls"]):
            ts = [row for row in target_peer if row["room"] == room]
            cs = [row for row in control_peer if row["room"] == room]
            by_room[peer + "/" + room] = {
                "targets": len(ts), "controls": len(cs),
                "target_exact_same_ordinary_support": sum(
                    row["action_pair"]["ordinary_parent_by_tile"] ==
                    row["action_pair"]["ordinary_alternate_by_tile"] for row in ts),
                "target_equal_width_different_support": sum(
                    row["action_pair"]["ordinary_codes_delta"] == 0 and
                    row["action_pair"]["ordinary_capacity_delta"] == 0 and
                    row["action_pair"]["ordinary_parent_by_tile"] !=
                    row["action_pair"]["ordinary_alternate_by_tile"] for row in ts),
                "target_strong_risk_higher": sum(
                    row["action_pair"]["alternate_risk_units"] >
                    row["action_pair"]["parent_risk_units"] for row in ts),
                "target_both_wider": sum(row["action_pair"]["ordinary_codes_delta"] > 0 and
                                         row["action_pair"]["ordinary_capacity_delta"] > 0
                                         for row in ts),
                "target_both_wider_no_old_match": sum(
                    row["action_pair"]["ordinary_codes_delta"] > 0 and
                    row["action_pair"]["ordinary_capacity_delta"] > 0 and
                    all(action != row["strong_action"] for action in row["old_tops"].values())
                    for row in ts),
                "control_both_wider_available": sum(row["both_wider_alternative_count"] > 0
                                                     for row in cs),
                "control_same_shanten_context": sum(
                    row["same_context_and_shanten_as_a_target"] for row in cs),
                "control_both_wider_available_same_shanten_context": sum(
                    row["same_context_and_shanten_as_a_target"] and
                    row["both_wider_alternative_count"] > 0 for row in cs),
                "control_guarded_both_wider_available": sum(
                    row["risk_guarded_both_wider_alternative_count"] > 0 for row in cs),
                "control_same_support_available": sum(
                    row["same_support_alternative_count"] > 0 for row in cs),
                "control_equal_width_different_support_available": sum(
                    row["equal_width_different_support_alternative_count"] > 0
                    for row in cs),
                "control_g88_changes": sum(
                    row["old_tops"]["g88"] != row["parent_and_strong_action"]
                    for row in cs),
            }

    out.mkdir(parents=True, exist_ok=True)
    pairs_file = out / "target_pairs.jsonl"
    controls_file = out / "matched_controls.jsonl"
    write_jsonl(pairs_file, target_rows)
    write_jsonl(controls_file, control_rows)
    result = {
        "schema": "g258-postclaim-action-pairs/2",
        "result_blind": True,
        "source_sha256": {
            "script": sha(Path(__file__)), "g61": sha(_project_file(_PROJECT_ROOT, G61 / "result.json")),
            "g61_shape": sha(_project_file(_PROJECT_ROOT, G61 / "shape_profile.json")), "g253": sha(G253),
            "g87": sha(G87), "g88": sha(G88), "g210": sha(G210),
            "g11_scorer": sha(_project_file(_PROJECT_ROOT, HERE / "candidates" / G11_SCORER)),
            "g88_scorer": sha(_project_file(_PROJECT_ROOT, HERE / "candidates" / G88_SCORER)),
            "g61_windows_by_unit": source_hashes,
        },
        "evidence_sha256": {"target_pairs.jsonl": sha(pairs_file),
                            "matched_controls.jsonl": sha(controls_file)},
        "denominator": {"postclaim_by_peer": dict(full_postclaim),
                        "strict_target_windows": len(target_rows),
                        "fine_context_parent_agree_controls": len(control_rows),
                        "same_shanten_fine_context_parent_agree_controls": sum(
                            row["same_context_and_shanten_as_a_target"]
                            for row in control_rows),
                        "peer_room_units": len(g61["units"]),
                        "physical_rooms": len({row["room"] for row in target_rows})},
        "context_fields": ("white", "own_chi_peng_melds", "wall_remaining",
                           "opponent_max_melds", "score_position", "own_meld_kinds"),
        "by_peer": by_peer,
        "by_peer_room": by_room,
        "boundary": "只读行动前 PlayerObservation、生产规则和冻结评分；官方强手动作是观察标签，负控也是观察标签。公开未见容量不代表牌墙概率，未执行备选无因果收益标签。",
    }
    (out / "result.json").open("x", encoding="utf-8").write(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"denominator": result["denominator"], "by_peer": by_peer},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
