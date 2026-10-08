#!/usr/bin/env python3
"""G55 官方结果盲弃牌：生产爆头真值 False→True 的动作空间。"""

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
import g11_longitudinal_route_audit as hands
import g48_cross_layer_natural_gap_reach as g48


HERE = Path(__file__).resolve().parent
G49 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g49-official-behavior-20260927/result.json')
G11 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g11-shape-risk-behavior-20260927/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g55-baotou-entry-reach-20260927/result.json')
LEVELS = ("transition", "no_hu", "shape_guard", "same_combined",
          "near_score", "near_score_capacity")


def sha(path: Path) -> str:
    """返回冻结输入和程序的 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def integer(value) -> int | None:
    """规则整数不得由布尔冒充。"""

    return value if type(value) is int else None


def shape_guard(parent: dict, alt: dict, white_parent: int, white_alt: int) -> bool:
    """综合／普通／可用七对向听及实持白板均不退；缺事实不猜。"""

    for field in ("shanten_after", "standard_shanten_after"):
        p, a = integer(parent.get(field)), integer(alt.get(field))
        if p is None or a is None or a > p:
            return False
    p7, a7 = parent.get("seven_pairs_shanten_after"), alt.get("seven_pairs_shanten_after")
    if p7 is not None:
        if integer(p7) is None or integer(a7) is None or a7 > p7:
            return False
    elif a7 is not None:
        return False
    return white_alt >= white_parent


def main() -> None:
    """完整读取冻结官方父代决策；不读任何后续事件或桌分。"""

    if OUT.exists():
        raise SystemExit("G55 结果已存在，拒绝覆盖")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    complete = atlas._complete_ids()
    g49 = json.loads(G49.read_text(encoding="utf-8"))
    g11 = json.loads(G11.read_text(encoding="utf-8"))
    if (len(complete) != 909 or g49.get("outcome_blind") is not True or
            g11.get("outcome_blind") is not True or
            g49.get("parent_source_sha256") != frozen["parent_source_sha256"] or
            g11.get("parent_source_sha256") != frozen["parent_source_sha256"]):
        raise ValueError("G55 冻结父代、完整桌或旧动作身份漂移")
    key = lambda row: (row["game_id"], row["round_no"], row["trigger_seq"])
    old49 = {key(row): row["candidate_action"] for row in g49["changed"]}
    old11 = {key(row): row["candidate_action"] for row in g11["changed"]}
    counts = Counter()
    tables: dict[str, set[str]] = defaultdict(set)
    rooms: dict[str, set[str]] = defaultdict(set)
    rows = []
    for room in frozen["rooms"]:
        audit = atlas.source.ROOT / room["audit_dir"]
        decisions = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decisions.stat().st_size != room["decision_bytes"]:
            raise ValueError("G55 冻结动作审计字节数漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("G55 房间父代源码漂移")
        accepted = atlas.source._accepted(decisions)
        for context, raw, plan in atlas.source.screen._iter_decisions(audit):
            game_id = context.get("game_id")
            if game_id not in complete or (raw.get("window_key") or {}).get("phase") != "draw":
                continue
            ranked = sorted(plan.get("candidates") or [],
                            key=lambda item: item.get("rank", 10**9))
            if not ranked or not (ranked[0].get("action_key") or "").startswith("discard:"):
                continue
            parent_action = ranked[0]["action_key"]
            if accepted.get(context.get("decision_id")) != parent_action:
                continue
            parsed = hands._hand(raw["observation"])
            if parsed is None:
                counts["unreconstructable_accepted_discard"] += 1
                continue
            counts["accepted_normal_draw_discards"] += 1
            legal_list = (raw.get("rules") or {}).get("legal_candidates") or []
            legal = {item.get("action_key"): item.get("facts") or {} for item in legal_list}
            if len(legal) != len(legal_list) or parent_action not in legal:
                raise ValueError("G55 合法候选重复或缺父代弃牌")
            parent = legal[parent_action]
            p_baotou = parent.get("baotou_after")
            if type(p_baotou) is not bool:
                counts["parent_baotou_unknown"] += 1
                continue
            if p_baotou:
                counts["parent_already_baotou"] += 1
                continue
            full, _, _melds = parsed
            parent_hand = hands._after_discard(full, parent_action)
            if parent_hand is None:
                raise ValueError("G55 父代已接受弃牌不在本人手牌")
            white_parent = parent_hand["白"]
            has_hu = any((action or "").startswith("hu:") or action == "hu"
                         for action in legal)
            scores = {item["action_key"]: item.get("total_score") for item in ranked}
            parent_capacity = g48.useful_count(parent, "useful_tiles")
            alternatives = []
            for action, fact in legal.items():
                if action == parent_action or not isinstance(action, str) or not action.startswith("discard:"):
                    continue
                baotou = fact.get("baotou_after")
                if type(baotou) is not bool:
                    counts["alternative_baotou_unknown"] += 1
                    continue
                if not baotou:
                    continue
                counts["transition_pairs"] += 1
                alt_hand = hands._after_discard(full, action)
                if alt_hand is None:
                    raise ValueError("G55 生产合法弃牌不在本人手牌")
                white_alt = alt_hand["白"]
                alt_capacity = g48.useful_count(fact, "useful_tiles")
                p_score, a_score = scores.get(parent_action), scores.get(action)
                score_gap = (p_score - a_score if type(p_score) in (int, float) and
                             type(a_score) in (int, float) else None)
                guard = shape_guard(parent, fact, white_parent, white_alt)
                same = (guard and integer(fact.get("shanten_after")) ==
                        integer(parent.get("shanten_after")))
                near = (guard and score_gap is not None and 0 <= score_gap <= 10)
                capacity = (near and parent_capacity is not None and
                            alt_capacity is not None and alt_capacity >= parent_capacity)
                alternatives.append({"action": action,
                                     "combined_shanten_after": fact.get("shanten_after"),
                                     "standard_shanten_after": fact.get("standard_shanten_after"),
                                     "seven_pairs_shanten_after": fact.get("seven_pairs_shanten_after"),
                                     "whites_held": white_alt,
                                     "combined_useful_capacity": alt_capacity,
                                     "parent_score_gap": score_gap,
                                     "shape_guard": guard, "same_combined": same,
                                     "near_score": near, "near_score_capacity": capacity})
            if not alternatives:
                continue
            row_key = (game_id, context.get("round_no"), context.get("trigger_seq"))
            flags = {"transition": True,
                     "no_hu": not has_hu,
                     "shape_guard": not has_hu and any(a["shape_guard"] for a in alternatives),
                     "same_combined": not has_hu and any(a["same_combined"] for a in alternatives),
                     "near_score": not has_hu and any(a["near_score"] for a in alternatives),
                     "near_score_capacity": not has_hu and any(a["near_score_capacity"]
                                                                 for a in alternatives)}
            for level, present in flags.items():
                if present:
                    counts[level + "_windows"] += 1
                    tables[level].add(game_id)
                    rooms[level].add(room["room_id"])
            strict = [a for a in alternatives if a["near_score_capacity"]] if not has_hu else []
            best = min(strict, key=lambda a: (a["parent_score_gap"],
                                               -a["combined_useful_capacity"], a["action"])) if strict else None
            if best is not None:
                counts["strict_same_combined"] += int(best["same_combined"])
                counts["strict_same_g49"] += int(old49.get(row_key) == best["action"])
                counts["strict_same_g11"] += int(old11.get(row_key) == best["action"])
            rows.append({"room_id": room["room_id"], "game_id": game_id,
                         "round_no": context.get("round_no"),
                         "trigger_seq": context.get("trigger_seq"),
                         "parent_action": parent_action,
                         "parent_combined_shanten_after": parent.get("shanten_after"),
                         "parent_standard_shanten_after": parent.get("standard_shanten_after"),
                         "parent_seven_pairs_shanten_after": parent.get("seven_pairs_shanten_after"),
                         "parent_whites_held": white_parent,
                         "parent_combined_useful_capacity": parent_capacity,
                         "legal_hu_available": has_hu,
                         "alternatives": alternatives,
                         "strict_best": best,
                         "strict_same_g49": best is not None and old49.get(row_key) == best["action"],
                         "strict_same_g11": best is not None and old11.get(row_key) == best["action"]})
    if (counts["accepted_normal_draw_discards"] != 55170 or
            counts["unreconstructable_accepted_discard"] != 7805):
        raise ValueError("G55 接受弃牌、正常本人摸牌母体与 G14/G45 不一致")
    if len({(row["game_id"], row["round_no"], row["trigger_seq"]) for row in rows}) != len(rows):
        raise ValueError("G55 爆头真值差窗口重复")
    output = {"schema": "g55-baotou-entry-reach/1", "outcome_blind": True,
              "frozen_rooms_sha256": sha(atlas.FROZEN),
              "g49_result_sha256": sha(G49), "g11_result_sha256": sha(G11),
              "parent_source_sha256": frozen["parent_source_sha256"],
              "script_sha256": sha(Path(__file__)), "complete_tables": len(complete),
              "counts": dict(sorted(counts.items())),
              "table_coverage": {name: len(tables[name]) for name in LEVELS},
              "room_coverage": {name: len(rooms[name]) for name in LEVELS},
              "rows": rows,
              "boundary": "仅父代动作前生产合法事实，爆头是真任意听；未读未来墙、对手暗手或桌分，触达不等于收益。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"counts": output["counts"], "table_coverage": output["table_coverage"],
                      "room_coverage": output["room_coverage"]},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
