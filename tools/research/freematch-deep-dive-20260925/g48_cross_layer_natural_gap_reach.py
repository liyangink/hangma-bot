#!/usr/bin/env python3
"""G48：结果盲枚举持白弃牌跨向听层的全留白自然缺口改进。"""

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
import g40_official_natural_gap_reach as g40


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g48-cross-layer-natural-gap-reach-20260927/result.json')
PARENT_SHA = g40.PARENT_SHA


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def integer(value) -> int | None:
    """布尔值不能冒充规则向听。"""

    return value if type(value) is int else None


def useful_count(facts: dict, field: str) -> int | None:
    entries = facts.get(field)
    if not isinstance(entries, list):
        return None
    amounts = [item.get("remaining_estimate") for item in entries]
    return sum(amounts) if all(type(value) is int and value >= 0 for value in amounts) else None


def main() -> None:
    """只读父代动作前观察与生产合法事实，不读取官方后续牌墙或结算。"""

    if OUT.exists():
        raise SystemExit("G48 结果已存在，拒绝覆盖")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    complete = atlas._complete_ids()
    if len(complete) != 909 or frozen.get("parent_source_sha256") != PARENT_SHA:
        raise ValueError("冻结父代或完整桌清单漂移")
    counts = Counter()
    tables = defaultdict(set)
    rows = []
    for room in frozen["rooms"]:
        audit = atlas.source.ROOT / room["audit_dir"]
        decisions = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decisions.stat().st_size != room["decision_bytes"]:
            raise ValueError("G48 冻结官方审计字节数漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != PARENT_SHA:
            raise ValueError("G48 房间父代源码漂移")
        accepted = atlas.source._accepted(decisions)
        for context, raw, plan in atlas.source.screen._iter_decisions(audit):
            game_id = context.get("game_id")
            if game_id not in complete or (raw.get("window_key") or {}).get("phase") != "draw":
                continue
            ranked = sorted(plan.get("candidates") or [], key=lambda row: row.get("rank", 10**9))
            if not ranked or not (ranked[0].get("action_key") or "").startswith("discard:"):
                continue
            parent_key = ranked[0]["action_key"]
            if accepted.get(context.get("decision_id")) != parent_key:
                continue
            parsed = hands._hand(raw["observation"])
            if parsed is None:
                counts["unreconstructable_accepted_discard"] += 1
                continue
            full, _before, melds = parsed
            parent_hand = hands._after_discard(full, parent_key)
            if parent_hand is None:
                raise ValueError("G48 已接受弃牌不在动作前手牌")
            counts["reconstructable_accepted_discard"] += 1
            if parent_hand["白"] == 0:
                continue
            counts["parent_keeps_white"] += 1
            legal = {item["action_key"]: item.get("facts") or {}
                     for item in (raw.get("rules") or {}).get("legal_candidates") or []}
            if len(legal) != len((raw.get("rules") or {}).get("legal_candidates") or []):
                raise ValueError("合法动作键重复")
            if parent_key not in legal:
                raise ValueError("已接受弃牌不在合法候选")
            parent_fact = legal[parent_key]
            parent_gap = g40.gap(parent_hand, melds)
            parent_std = integer(parent_fact.get("standard_shanten_after"))
            parent_combined = integer(parent_fact.get("shanten_after"))
            if parent_std is None or parent_combined is None or g40.standard(parent_hand, melds) != parent_std:
                raise ValueError("G48 父代生产规则数学错配")
            parent_seven = parent_fact.get("seven_pairs_shanten_after")
            if parent_seven is not None and integer(parent_seven) is None:
                raise ValueError("父代七对向听类型错误")
            parent_width = useful_count(parent_fact, "standard_useful_tiles")
            parent_combined_width = useful_count(parent_fact, "useful_tiles")
            scores = {item["action_key"]: item.get("total_score") for item in ranked}
            eligible = []
            for key, fact in legal.items():
                if key == parent_key or not key.startswith("discard:") or key == "discard:白":
                    continue
                after = hands._after_discard(full, key)
                if after is None or after["白"] != parent_hand["白"]:
                    continue
                alt_std = integer(fact.get("standard_shanten_after"))
                alt_combined = integer(fact.get("shanten_after"))
                if alt_std is None or alt_combined is None or g40.standard(after, melds) != alt_std:
                    raise ValueError("G48 备选生产规则数学错配")
                alt_seven = fact.get("seven_pairs_shanten_after")
                if alt_seven is not None and integer(alt_seven) is None:
                    raise ValueError("备选七对向听类型错误")
                gap = g40.gap(after, melds)
                counts["compared_nonwhite_legal_pair"] += 1
                if gap >= parent_gap:
                    continue
                counts["lower_gap_pair"] += 1
                delta_combined = alt_combined - parent_combined
                delta_std = alt_std - parent_std
                delta_seven = (alt_seven - parent_seven if type(alt_seven) is int
                               and type(parent_seven) is int else None)
                width = useful_count(fact, "standard_useful_tiles")
                combined_width = useful_count(fact, "useful_tiles")
                score_gap = (scores[parent_key] - scores[key]
                             if type(scores.get(parent_key)) in (int, float)
                             and type(scores.get(key)) in (int, float) else None)
                eligible.append({"action": key, "natural_need": gap,
                                 "delta_combined_shanten": delta_combined,
                                 "delta_standard_shanten": delta_std,
                                 "delta_seven_pairs_shanten": delta_seven,
                                 "delta_standard_useful_count": (width - parent_width
                                                                 if width is not None and parent_width is not None
                                                                 else None),
                                 "delta_combined_useful_count": (combined_width - parent_combined_width
                                                                 if combined_width is not None
                                                                 and parent_combined_width is not None else None),
                                 "parent_score_gap": score_gap})
                counts[f"lower_gap_pair|combined_delta|{delta_combined}"] += 1
                counts[f"lower_gap_pair|standard_delta|{delta_std}"] += 1
                counts[f"lower_gap_pair|white_count|{after['白']}"] += 1
            if not eligible:
                continue
            counts["lower_gap_window"] += 1
            tables["all"].add(game_id)
            for item in eligible:
                if item["delta_combined_shanten"] <= 0:
                    tables["combined_not_worse"].add(game_id)
                elif item["delta_combined_shanten"] == 1:
                    tables["combined_plus_one"].add(game_id)
            best = min(eligible, key=lambda item: (item["natural_need"],
                                                   item["delta_combined_shanten"],
                                                   item["delta_standard_shanten"],
                                                   item["action"]))
            counts[f"best|combined_delta|{best['delta_combined_shanten']}"] += 1
            counts[f"best|white_count|{parent_hand['白']}"] += 1
            rows.append({"room_id": room["room_id"], "game_id": game_id,
                         "round_no": context["round_no"], "trigger_seq": context["trigger_seq"],
                         "parent_action": parent_key,
                         "parent_natural_need": parent_gap,
                         "parent_standard_shanten": parent_std,
                         "parent_combined_shanten": parent_combined,
                         "parent_seven_pairs_shanten": parent_seven,
                         "parent_standard_useful_count": parent_width,
                         "parent_combined_useful_count": parent_combined_width,
                         "white_count": parent_hand["白"],
                         "wall_remaining": raw["observation"].get("remaining_tile_count"),
                         "alternatives": eligible, "best_lower_gap": best})
    result = {"schema": "g48-cross-layer-natural-gap-reach/1", "outcome_blind": True,
              "frozen_rooms_sha256": sha(atlas.FROZEN),
              "parent_source_sha256": PARENT_SHA, "script_sha256": sha(Path(__file__)),
              "complete_tables": len(complete),
              "counts": dict(sorted(counts.items())),
              "touched_complete_tables": {name: len(ids) for name, ids in sorted(tables.items())},
              "rows": rows,
              "boundary": "只查官方父代已接受弃牌的动作前可见信息与生产规则数学；公开未见牌不是牌墙概率，缺口下降不等于净分增益。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("complete_tables", "counts", "touched_complete_tables")},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
