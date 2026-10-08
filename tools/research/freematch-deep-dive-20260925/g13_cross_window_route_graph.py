#!/usr/bin/env python3
"""G13 结果盲本人动作链：把摸打、鸣/过、胡/继续接到同一单局。"""

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


HERE = Path(__file__).resolve().parent
G10 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g10-route-option-screen-20260927/result.json')
G11 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g11-shape-risk-behavior-20260927/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g13-cross-window-route-graph-20260927')


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _number(value: object) -> float | None:
    return float(value) if type(value) in (int, float) else None


def _route(facts: dict) -> dict:
    """完整保留未知值；规则事实不允许把缺失的牌型当 0。"""

    return {"standard": atlas._int(facts, "standard_shanten_after"),
            "combined": atlas._int(facts, "shanten_after"),
            "seven": atlas._int(facts, "seven_pairs_shanten_after"),
            "standard_support": g11._support_shape(facts, "standard_useful_tiles"),
            "combined_support": g11._support_shape(facts, "useful_tiles"),
            "seven_support": g11._support_shape(facts, "seven_pairs_useful_tiles"),
            "baotou_after": facts.get("baotou_after")}


def _not_worse(candidate: int | None, reference: int | None) -> bool:
    return candidate is not None and reference is not None and candidate <= reference


def _markers(parent_key: str, alternative_key: str, parent: dict, alternate: dict,
             *, current_baotou: bool) -> list[str]:
    """结果盲、只凭规则事实给合法改选贴非互斥路线标签。"""

    a, b = parent_key.split(":", 1)[0], alternative_key.split(":", 1)[0]
    markers = []
    if a == b == "discard":
        if (_not_worse(alternate["combined"], parent["combined"])
                and alternate["standard"] is not None and parent["standard"] is not None
                and alternate["standard"] < parent["standard"]):
            markers.append("discard_standard_route")
        if (_not_worse(alternate["combined"], parent["combined"])
                and alternate["seven"] is not None and parent["seven"] is not None
                and alternate["seven"] < parent["seven"]):
            markers.append("discard_seven_route")
        p, q = parent["standard_support"], alternate["standard_support"]
        if (parent["standard"] == alternate["standard"]
                and parent["standard"] is not None and p is not None and q is not None
                and q[1] > p[1] and q[0] >= p[0]
                and _not_worse(alternate["combined"], parent["combined"])):
            markers.append("discard_broader_standard")
        if current_baotou and alternative_key == "discard:白" and parent_key != "discard:白":
            markers.append("discard_piao_instead")
    if (parent["baotou_after"] is False and alternate["baotou_after"] is True
            and b in ("discard", "chi", "peng", "gang")):
        markers.append("enter_baotou")
    if a == "pass" and b in ("chi", "peng", "gang"):
        markers.append("pass_to_claim")
    if a in ("chi", "peng", "gang") and b == "pass":
        markers.append("claim_to_pass")
    if a == "hu" and b in ("discard", "gang", "pass"):
        markers.append("hu_to_continue")
    if a in ("discard", "gang", "pass") and b == "hu":
        markers.append("continue_to_hu")
    return markers


def _hand_projection(observation: dict, phase: str, parent_key: str,
                     own_melds: int | None) -> tuple[Counter | None, Counter | None]:
    """返回动作前 13-3m 张与已执行动作后 13-3m 张；不猜鸣牌后的手。"""

    hand = observation.get("my_hand")
    if own_melds is None or not isinstance(hand, list) or not all(isinstance(t, str) for t in hand):
        return None, None
    current = Counter(hand)
    if phase == "draw":
        drawn = observation.get("drawn_tile")
        if len(hand) != 14 - 3 * own_melds or not isinstance(drawn, str) or current[drawn] < 1:
            return None, None
        before = current.copy()
        before.subtract([drawn])
        before += Counter()
    elif phase.startswith("response_"):
        if len(hand) != 13 - 3 * own_melds:
            return None, None
        before = current.copy()
    else:
        return None, None
    family = parent_key.split(":", 1)[0]
    if family == "pass":
        return before, current
    if family == "discard":
        code = parent_key.split(":", 1)[1]
        if current[code] < 1:
            raise ValueError("已接受弃牌不在本人动作前手牌")
        after = current.copy()
        after.subtract([code])
        after += Counter()
        return before, after
    return before, None


def _matched(left: dict, right: dict) -> bool:
    """父代实际路径上一动作后的暗牌等于下一动作前暗牌。"""

    return (left["own_melds"] == right["own_melds"]
            and left["_after"] is not None and right["_before"] is not None
            and left["_after"] == right["_before"])


def _brief(event: dict | None) -> dict | None:
    if event is None:
        return None
    return {name: event[name] for name in
            ("trigger_seq", "phase", "parent_action", "white_count", "own_melds",
             "wall_remaining", "baotou_before", "parent_route")}


def main() -> None:
    """从冻结父代明确接受的全部本人窗口构造路线图；不读结算标签。"""

    if OUT.exists():
        raise SystemExit("G13 跨窗路线图谱目录已存在，拒绝覆盖")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    complete_ids = atlas._complete_ids()
    g10 = json.loads(G10.read_text(encoding="utf-8"))
    g11_behavior = json.loads(G11.read_text(encoding="utf-8"))
    if (g10.get("outcome_blind") is not True
            or g10.get("source_parent_sha256") != frozen["parent_source_sha256"]
            or g11_behavior.get("parent_source_sha256") != frozen["parent_source_sha256"]):
        raise ValueError("冻结父代与旧失败行为摘要不符")
    g10_actions = {(row["game_id"], row["round_no"], row["trigger_seq"]):
                   row["alternate_action"] for row in g10["rows"]}
    g11_actions = {(row["game_id"], row["round_no"], row["trigger_seq"]):
                   row["candidate_action"] for row in g11_behavior["changed"]}
    events = []
    counts = Counter()
    by_round = defaultdict(list)
    seen = set()
    for room in frozen["rooms"]:
        audit = atlas.source.ROOT / room["audit_dir"]
        file = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if file.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结房动作文件字节数漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("冻结房父代源码摘要漂移")
        accepted = atlas.source._accepted(file)
        for context, raw, plan in atlas.source.screen._iter_decisions(audit):
            game_id, round_no = context.get("game_id"), context.get("round_no")
            if game_id not in complete_ids:
                continue
            phase = (raw.get("window_key") or {}).get("phase")
            if phase != "draw" and not (isinstance(phase, str) and phase.startswith("response_")):
                continue
            ranked = sorted(plan.get("candidates") or [], key=lambda item: item.get("rank", 10**9))
            if not ranked or not isinstance(ranked[0].get("action_key"), str):
                counts["unranked"] += 1
                continue
            parent_key = ranked[0]["action_key"]
            if accepted.get(context.get("decision_id")) != parent_key:
                counts["parent_not_accepted"] += 1
                continue
            observation = raw.get("observation") or {}
            seat, melds = observation.get("seat"), observation.get("melds")
            if (type(round_no) is not int or type(context.get("trigger_seq")) is not int
                    or type(seat) is not int or not isinstance(melds, list)
                    or not 0 <= seat < len(melds) or not isinstance(melds[seat], list)):
                counts["identity_unknown"] += 1
                continue
            key = (game_id, round_no, seat, context["trigger_seq"], phase)
            if key in seen:
                raise ValueError("本人动作窗重复")
            seen.add(key)
            candidates = (raw.get("rules") or {}).get("legal_candidates") or []
            legal = {item["action_key"]: item.get("facts") or {} for item in candidates}
            if len(legal) != len(candidates) or parent_key not in legal:
                raise ValueError("已接受父代动作规则事实缺失或重复")
            parent_route = _route(legal[parent_key])
            scores = {item.get("action_key"): _number(item.get("total_score")) for item in ranked}
            parent_score = scores.get(parent_key)
            own_melds = len(melds[seat])
            before, after = _hand_projection(observation, phase, parent_key, own_melds)
            current_baotou = (observation.get("rule_state") or {}).get("baotou") is True
            if phase == "draw":
                parent_baotou = parent_route["baotou_after"]
                counts["draw_parent_baotou_" + str(parent_baotou)] += 1
                if any(facts.get("baotou_after") is True for facts in legal.values()):
                    counts["draw_any_legal_baotou_after_true"] += 1
                    counts["draw_any_legal_baotou_parent_" + str(parent_baotou)] += 1
                if current_baotou:
                    counts["draw_already_baotou"] += 1
                    if "discard:白" in legal:
                        counts["draw_already_baotou_legal_discard_white"] += 1
                        if parent_key == "discard:白":
                            counts["draw_already_baotou_parent_discard_white"] += 1
            opportunity_actions = defaultdict(list)
            for alternative_key, facts in legal.items():
                if alternative_key == parent_key:
                    continue
                alternate = _route(facts)
                for marker in _markers(parent_key, alternative_key, parent_route, alternate,
                                       current_baotou=current_baotou):
                    score = scores.get(alternative_key)
                    opportunity_actions[marker].append({
                        "action": alternative_key,
                        "parent_score_gap": (None if score is None or parent_score is None
                                             else parent_score - score),
                        "route": alternate})
            for options in opportunity_actions.values():
                options.sort(key=lambda item: (item["parent_score_gap"] is None,
                                               item["parent_score_gap"] if item["parent_score_gap"] is not None else 0,
                                               item["action"]))
            event = {"room_id": room["room_id"], "game_id": game_id,
                     "round_no": round_no, "seat": seat,
                     "trigger_seq": context["trigger_seq"], "phase": phase,
                     "parent_action": parent_key,
                     "parent_route": parent_route, "parent_score": parent_score,
                     "white_count": (observation.get("my_hand") or []).count("白"),
                     "own_melds": own_melds,
                     "wall_remaining": observation.get("remaining_tile_count"),
                     "baotou_before": current_baotou,
                     "opportunities": dict(opportunity_actions),
                     "_before": before, "_after": after,
                     "_order": len(events)}
            events.append(event)
            by_round[(game_id, round_no, seat)].append(event)
            counts["accepted_" + phase + "_" + parent_key.split(":", 1)[0]] += 1
    opportunities = []
    scope = defaultdict(set)
    window_scope = defaultdict(set)
    overlap = defaultdict(Counter)
    edges = Counter()
    for sequence in by_round.values():
        sequence.sort(key=lambda item: (item["trigger_seq"], item["_order"]))
        for index, current in enumerate(sequence):
            previous = sequence[index - 1] if index > 0 else None
            following = sequence[index + 1] if index + 1 < len(sequence) else None
            if following is not None:
                edges["consecutive_own_window"] += 1
                if _matched(current, following):
                    edges["matched_concealed_hand"] += 1
            if not current["opportunities"]:
                continue
            action_id = (current["game_id"], current["round_no"], current["trigger_seq"])
            for marker, options in current["opportunities"].items():
                scope[marker].add(current["game_id"])
                window_scope[marker].add((*action_id, current["phase"]))
                if following is not None:
                    overlap[marker]["has_next_parent_window"] += 1
                    if _matched(current, following):
                        overlap[marker]["next_parent_hand_matched"] += 1
                if previous is not None:
                    overlap[marker]["has_previous_parent_window"] += 1
                    if _matched(previous, current):
                        overlap[marker]["previous_parent_hand_matched"] += 1
                if current["white_count"]:
                    overlap[marker]["with_white"] += 1
                old_g10, old_g11 = g10_actions.get(action_id), g11_actions.get(action_id)
                overlap[marker]["g10_same_action"] += sum(item["action"] == old_g10 for item in options)
                overlap[marker]["g11_same_action"] += sum(item["action"] == old_g11 for item in options)
                opportunities.append({
                    "room_id": current["room_id"], "game_id": current["game_id"],
                    "round_no": current["round_no"], "seat": current["seat"],
                    "trigger_seq": current["trigger_seq"], "phase": current["phase"],
                    "marker": marker, "parent_action": current["parent_action"],
                    "parent_route": current["parent_route"],
                    "white_count": current["white_count"],
                    "own_melds": current["own_melds"],
                    "wall_remaining": current["wall_remaining"],
                    "baotou_before": current["baotou_before"],
                    "options": options,
                    "g10_old_action": old_g10, "g11_old_action": old_g11,
                    "previous_parent": _brief(previous),
                    "previous_hand_matched": previous is not None and _matched(previous, current),
                    "next_parent": _brief(following),
                    "next_hand_matched": following is not None and _matched(current, following)})
    OUT.mkdir(parents=True)
    rows_path = _project_file(_PROJECT_ROOT, OUT / "opportunities.jsonl.gz")
    with rows_path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            for row in opportunities:
                compressed.write((json.dumps(row, ensure_ascii=False, sort_keys=True,
                                             separators=(",", ":")) + "\n").encode("utf-8"))
    result = {"schema": "g13-cross-window-route-graph/1", "outcome_blind": True,
              "analysis_script_sha256": _sha(Path(__file__)),
              "source_frozen_rooms_sha256": _sha(atlas.FROZEN),
              "source_complete_ids_sha256": _sha(atlas.TRAIN_ROWS),
              "g10_sha256": _sha(G10), "g11_behavior_sha256": _sha(G11),
              "parent_source_sha256": frozen["parent_source_sha256"],
              "complete_official_tables": len(complete_ids),
              "official_rooms": len(frozen["rooms"]),
              "accepted_events": len(events), "event_counts": dict(sorted(counts.items())),
              "edge_counts": dict(sorted(edges.items())),
              "opportunity_rows": len(opportunities),
              "opportunity_sha256": _sha(rows_path),
              "markers": {name: {"windows": len(window_scope[name]),
                                 "complete_tables": len(scope[name]),
                                 "conditional_gain_for_plus2_all_tables":
                                     2 * len(complete_ids) / len(scope[name]),
                                 **dict(sorted(overlap[name].items()))}
                          for name in sorted(scope)},
              "boundary": "只联结冻结父代已接受动作；未来本人窗口仅作赛后链路审计，不进入前窗触发。鸣牌后手牌不猜。胡后无父代续行是结局截断，不证明弃胡后无价值。静态规则机会不是因果收益。"}
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"accepted_events": result["accepted_events"],
                      "opportunity_rows": result["opportunity_rows"],
                      "edge_counts": result["edge_counts"],
                      "markers": result["markers"]}, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
