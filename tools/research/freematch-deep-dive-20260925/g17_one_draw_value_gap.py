#!/usr/bin/env python3
"""G17 结果盲：同即时牌效下比较留白弃牌的一摸条件结算质量。"""

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
import g14_discard_width_baseline as width


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g17-one-draw-value-gap-20260927/result.json')
ROWS = OUT.with_name("rows.jsonl.gz")
G10 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g10-route-option-screen-20260927/result.json')
G11 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g11-shape-risk-behavior-20260927/result.json')


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _one_draw_mass(action: dict, seat: int) -> int | None:
    """一次普通自摸的互斥条件净分质量；事实不全时保留未知。"""

    facts = action.get("value_facts") or {}
    if facts.get("coverage") != "complete":
        return None
    seen: set[str] = set()
    mass = 0
    for route in facts.get("routes") or []:
        if (route.get("followup_discard") is not None or
                (route.get("conditions") or {}).get("draw_kind") != "normal"):
            return None
        settlement = route.get("conditional_settlement") or {}
        delta = settlement.get("score_delta")
        if (not isinstance(delta, list) or len(delta) != 4 or
                type(delta[seat]) is not int or delta[seat] <= 0):
            return None
        useful = route.get("useful_tiles")
        if not isinstance(useful, list) or not useful:
            return None
        for tile in useful:
            code, remaining = tile.get("code"), tile.get("remaining_estimate")
            if (not isinstance(code, str) or code in seen or
                    type(remaining) is not int or not 0 <= remaining <= 4):
                return None
            seen.add(code)
            mass += remaining * delta[seat]
    return mass


def _vector(facts: dict, name: str) -> tuple[tuple[str, int], ...] | None:
    """保留有效牌逐牌身份与未见容量，避免总量相同掩盖区别。"""

    entries = facts.get(name)
    if not isinstance(entries, list):
        return None
    values = []
    for item in entries:
        code, remaining = item.get("code"), item.get("remaining_estimate")
        if not isinstance(code, str) or type(remaining) is not int:
            return None
        values.append((code, remaining))
    if len({code for code, _ in values}) != len(values):
        return None
    return tuple(sorted(values))


def _comparable(parent: dict, other: dict) -> bool:
    """只比较同向听、普通/综合当前公开有效容量不退的弃牌。"""

    if (parent["standard_shanten"] is None or
            parent["combined_shanten"] is None or
            other["standard_shanten"] != parent["standard_shanten"] or
            other["combined_shanten"] != parent["combined_shanten"]):
        return False
    if (parent["seven_shanten"] is not None and
            (other["seven_shanten"] is None or
             other["seven_shanten"] > parent["seven_shanten"])):
        return False
    for family in ("standard", "combined"):
        p, q = parent[family], other[family]
        if p is None or q is None or q[0] < p[0]:
            return False
    return True


def main() -> None:
    """扫描冻结父代已接受窗口；不读取未来摸牌、结算和他家暗手。"""

    if OUT.exists() or ROWS.exists():
        raise SystemExit("G17 结果已存在，拒绝覆盖")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    complete = atlas._complete_ids()
    g10 = json.loads(G10.read_text(encoding="utf-8"))
    g11_old = json.loads(G11.read_text(encoding="utf-8"))
    if (len(complete) != 909 or len(frozen["rooms"]) != 91 or
            g10.get("outcome_blind") is not True or
            g11_old.get("outcome_blind") is not True or
            g10.get("source_parent_sha256") != frozen["parent_source_sha256"] or
            g11_old.get("parent_source_sha256") != frozen["parent_source_sha256"]):
        raise ValueError("G17 父代、负控或完整桌母体漂移")
    old_g10 = {(r["game_id"], r["round_no"], r["trigger_seq"]): r["alternate_action"]
               for r in g10["rows"]}
    old_g11 = {(r["game_id"], r["round_no"], r["trigger_seq"]): r["candidate_action"]
               for r in g11_old["changed"]}
    counts = Counter()
    scopes: dict[str, set[str]] = defaultdict(set)
    rows = []
    for room in frozen["rooms"]:
        audit = atlas.source.ROOT / room["audit_dir"]
        decisions = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decisions.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结房动作审计字节数漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("冻结房父代源码摘要漂移")
        accepted = atlas.source._accepted(decisions)
        for context, raw, plan in atlas.source.screen._iter_decisions(audit):
            game_id = context.get("game_id")
            if (game_id not in complete or
                    (raw.get("window_key") or {}).get("phase") != "draw"):
                continue
            ranked = sorted(plan.get("candidates") or [],
                            key=lambda item: item.get("rank", 10**9))
            if not ranked or not isinstance(ranked[0].get("action_key"), str):
                continue
            parent_key = ranked[0]["action_key"]
            if (not parent_key.startswith("discard:") or
                    accepted.get(context.get("decision_id")) != parent_key):
                continue
            observation = raw.get("observation") or {}
            hand = g11._hand(observation)
            if hand is None:
                continue
            full, _, _ = hand
            parent_after = g11._after_discard(full, parent_key)
            if parent_after is None:
                raise ValueError("已接受弃牌不在本人完整手牌")
            counts["accepted_normal_discard"] += 1
            if parent_after["白"] < 1:
                continue
            counts["parent_keeps_white"] += 1
            legal_list = (raw.get("rules") or {}).get("legal_candidates") or []
            legal = {action.get("action_key"): action for action in legal_list}
            if len(legal) != len(legal_list) or parent_key not in legal:
                raise ValueError("生产合法动作缺失或重复")
            if "hu" in legal:
                counts["legal_immediate_hu"] += 1
                continue
            seat = observation.get("seat")
            if type(seat) is not int or not 0 <= seat < 4:
                raise ValueError("本人座位无效")
            parent_action = legal[parent_key]
            parent_facts = parent_action.get("facts") or {}
            parent_shape = width._shape(parent_facts)
            parent_mass = _one_draw_mass(parent_action, seat)
            if parent_mass is None:
                counts["parent_one_draw_unknown"] += 1
                continue
            counts["parent_one_draw_complete"] += 1
            score_by_key = {item.get("action_key"): item.get("total_score") for item in ranked}
            parent_score = score_by_key.get(parent_key)
            if type(parent_score) not in (int, float):
                counts["parent_score_unknown"] += 1
                continue
            candidates = []
            for key, action in legal.items():
                if not isinstance(key, str) or not key.startswith("discard:") or key == parent_key:
                    continue
                after = g11._after_discard(full, key)
                if after is None or after["白"] != parent_after["白"]:
                    continue
                facts = action.get("facts") or {}
                shape = width._shape(facts)
                if not _comparable(parent_shape, shape):
                    continue
                mass = _one_draw_mass(action, seat)
                if mass is None:
                    counts["comparable_alternative_one_draw_unknown"] += 1
                    continue
                counts["comparable_known_alternative"] += 1
                if mass <= parent_mass:
                    continue
                score = score_by_key.get(key)
                if type(score) not in (int, float):
                    continue
                same_summary = (shape["standard"] == parent_shape["standard"] and
                                shape["combined"] == parent_shape["combined"])
                same_vector = all(
                    _vector(facts, name) == _vector(parent_facts, name)
                    and _vector(facts, name) is not None
                    for name in ("standard_useful_tiles", "useful_tiles")
                )
                candidates.append({"action": key, "mass": mass, "score_gap": parent_score - score,
                                   "same_immediate_summary": same_summary,
                                   "same_immediate_vector": same_vector,
                                   "standard_shanten": shape["standard_shanten"],
                                   "seven_shanten": shape["seven_shanten"],
                                   "standard_support": shape["standard"],
                                   "combined_support": shape["combined"]})
            if not candidates:
                continue
            best = min(candidates,
                       key=lambda candidate: (-(candidate["mass"] - parent_mass),
                                              candidate["score_gap"], candidate["action"]))
            parent_capacity = parent_shape["combined"][0]
            any_higher_value_per_support = (
                parent_capacity > 0 and any(
                    candidate["combined_support"][0] > 0 and
                    candidate["mass"] * parent_capacity >
                    parent_mass * candidate["combined_support"][0]
                    for candidate in candidates
                )
            )
            key = (game_id, context.get("round_no"), context.get("trigger_seq"))
            labels = ["higher_one_draw_mass"]
            if best["score_gap"] <= 0:
                labels.append("higher_mass_score_tie")
            if best["score_gap"] <= 6:
                labels.append("higher_mass_score_gap_le_6")
            if best["same_immediate_summary"]:
                labels.append("same_immediate_summary")
            if best["same_immediate_vector"]:
                labels.append("same_immediate_vector")
            if any_higher_value_per_support:
                labels.append("any_higher_conditional_value_per_support")
            alternative_capacity = best["combined_support"][0]
            if parent_capacity > 0 and alternative_capacity > 0:
                # 精确整数交叉相乘，不以浮点除法混淆番值与进张容量。
                comparison = best["mass"] * parent_capacity - parent_mass * alternative_capacity
                if comparison > 0:
                    labels.append("higher_conditional_value_per_support")
                elif comparison == 0:
                    labels.append("same_conditional_value_per_support")
                else:
                    labels.append("lower_conditional_value_per_support")
            if best["action"] != old_g10.get(key) and best["action"] != old_g11.get(key):
                labels.append("not_old_g10_g11_action")
            for label in labels:
                counts[label] += 1
                scopes[label].add(game_id)
            rows.append({"room_id": room["room_id"], "game_id": game_id,
                         "round_no": key[1], "trigger_seq": key[2],
                         "parent_action": parent_key, "alternative": best,
                         "parent_mass": parent_mass,
                         "parent_shape": parent_shape,
                         "parent_score": parent_score,
                         "parent_white_after": parent_after["白"],
                         "positive_alternatives": len(candidates),
                         "any_higher_conditional_value_per_support": any_higher_value_per_support,
                         "g10_old_action": old_g10.get(key),
                         "g11_old_action": old_g11.get(key)})
    if counts["parent_keeps_white"] != 23_165:
        raise ValueError("G17 持白母体与 G14/G16 对账不一致")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with ROWS.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as stream:
            for row in rows:
                stream.write((json.dumps(row, ensure_ascii=False, sort_keys=True,
                                         separators=(",", ":")) + "\n").encode("utf-8"))
    result = {"schema": "g17-one-draw-value-gap/1", "outcome_blind": True,
              "script_sha256": _sha(Path(__file__)),
              "source_frozen_rooms_sha256": _sha(atlas.FROZEN),
              "source_complete_ids_sha256": _sha(atlas.TRAIN_ROWS),
              "parent_source_sha256": frozen["parent_source_sha256"],
              "old_g10_sha256": _sha(G10), "old_g11_sha256": _sha(G11),
              "complete_official_tables": len(complete),
              "counts": dict(sorted(counts.items())),
              "table_coverage": {name: len(ids) for name, ids in sorted(scopes.items())},
              "rows_count": len(rows), "rows_sha256": _sha(ROWS),
              "boundary": "生产条件结算只到下一次本人自摸；公开未见容量非墙内概率；不含对手先胡或未来响应，不是净分或候选。"}
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"counts": result["counts"], "table_coverage": result["table_coverage"]},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
