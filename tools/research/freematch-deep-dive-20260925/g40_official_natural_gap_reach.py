#!/usr/bin/env python3
"""G40：结果盲检查父代持白弃牌是否遗漏同向听、更小自然缺口的合法动作。"""

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
from hangma_bot.hangma._standard import backend_info, need
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g40-official-natural-gap-reach-20260927/result.json')
G39 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g39-quad-white-gap-stress-20260927/result.json')
PARENT_SHA = "a2d9b8af93beabdba75716fccae56b0668a6fd84f0bdce558d2ff3e569443618"
NATURAL = tuple(code for code in CANONICAL_TILE_ORDER if code != "白")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def gap(hand: Counter, melds: int) -> int:
    """生产标准型数学下，全部白板保留时所需最少自然进张。"""

    return need(tuple(hand[code] for code in NATURAL), 0, 4 - melds, True)


def standard(hand: Counter, melds: int) -> int:
    """同源生产数学：当前白板可充当百搭时的普通型向听。"""

    return need(tuple(hand[code] for code in NATURAL), hand["白"], 4 - melds, True) - 1


def _same_stratum(parent: dict, alternative: dict) -> bool:
    """只比较生产规则事实已知的同普通型、七对及综合向听动作。"""

    for field in ("standard_shanten_after", "shanten_after"):
        if type(parent.get(field)) is not int or type(alternative.get(field)) is not int:
            return False
        if alternative[field] != parent[field]:
            return False
    seven_p = parent.get("seven_pairs_shanten_after")
    seven_a = alternative.get("seven_pairs_shanten_after")
    if seven_p is not None and type(seven_p) is not int:
        return False
    if seven_a is not None and type(seven_a) is not int:
        return False
    return seven_a == seven_p


def main() -> None:
    """固定官方完整桌和已接受父代动作，保存全量低缺口触达而不读取成绩。"""

    if OUT.exists():
        raise SystemExit("G40 已有结果，拒绝覆盖")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    complete = atlas._complete_ids()
    if len(complete) != 909 or frozen.get("parent_source_sha256") != PARENT_SHA:
        raise ValueError("G40 冻结父代或完整桌清单漂移")
    g39 = json.loads(G39.read_text(encoding="utf-8"))
    if g39.get("schema") != "g39-quad-white-gap-stress/1":
        raise ValueError("G39 压力结果身份缺失")
    counts = Counter()
    tables = defaultdict(set)
    rows = []
    for room in frozen["rooms"]:
        audit = atlas.source.ROOT / room["audit_dir"]
        decisions = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decisions.stat().st_size != room["decision_bytes"]:
            raise ValueError("G40 冻结官方审计字节数漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != PARENT_SHA:
            raise ValueError("G40 房间父代源码漂移")
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
            full, _seat, melds = parsed
            p_hand = hands._after_discard(full, parent_key)
            if p_hand is None:
                raise ValueError("已接受弃牌不在动作前手牌")
            counts["reconstructable_accepted_discards"] += 1
            if p_hand["白"] == 0:
                continue
            counts["parent_keeps_white"] += 1
            legal = {item["action_key"]: item.get("facts") or {}
                     for item in (raw.get("rules") or {}).get("legal_candidates") or []}
            if parent_key not in legal:
                raise ValueError("合法候选缺少已接受父代动作")
            p_fact = legal[parent_key]
            p_gap = gap(p_hand, melds)
            if standard(p_hand, melds) != p_fact.get("standard_shanten_after"):
                raise ValueError("G40 父代普通型数学与规则事实不一致")
            candidates = []
            for key, fact in legal.items():
                if key == parent_key or key == "discard:白" or not key.startswith("discard:"):
                    continue
                if not _same_stratum(p_fact, fact):
                    continue
                a_hand = hands._after_discard(full, key)
                if a_hand is None or a_hand["白"] != p_hand["白"]:
                    continue
                if standard(a_hand, melds) != fact["standard_shanten_after"]:
                    raise ValueError("G40 备选普通型数学与规则事实不一致")
                a_gap = gap(a_hand, melds)
                counts["same_stratum_pairs"] += 1
                if a_gap < p_gap:
                    direction = "lower"
                elif a_gap > p_gap:
                    direction = "higher"
                else:
                    direction = "equal"
                counts[direction + "_gap_pairs"] += 1
                if direction != "equal":
                    candidates.append((key, direction, a_gap))
            if not candidates:
                continue
            score = {item["action_key"]: item.get("total_score") for item in ranked}
            for direction in ("lower", "higher"):
                options = [item for item in candidates if item[1] == direction]
                if not options:
                    continue
                counts[direction + "_gap_windows"] += 1
                tables[direction].add(game_id)
                best = min(options, key=lambda item: (item[2], item[0])) if direction == "lower" else max(
                    options, key=lambda item: (item[2], item[0]))
                value_gap = (score[parent_key] - score[best[0]]
                             if type(score.get(parent_key)) in (int, float) and
                             type(score.get(best[0])) in (int, float) else None)
                counts[f"{direction}_white_{p_hand['白']}_windows"] += 1
                counts[f"{direction}_quads_{sum(n == 4 for n in p_hand.values())}_windows"] += 1
                counts[f"{direction}_standard_{p_fact['standard_shanten_after']}_windows"] += 1
                rows.append({"room_id": room["room_id"], "game_id": game_id,
                             "round_no": context["round_no"], "trigger_seq": context["trigger_seq"],
                             "direction": direction, "parent_action": parent_key,
                             "alternative_action": best[0], "parent_natural_need": p_gap,
                             "alternative_natural_need": best[2],
                             "standard_shanten": p_fact["standard_shanten_after"],
                             "seven_pairs_shanten": p_fact.get("seven_pairs_shanten_after"),
                             "white_count": p_hand["白"], "parent_score_gap": value_gap})
    result = {"schema": "g40-official-natural-gap-reach/1", "outcome_blind": True,
              "frozen_rooms_sha256": sha(atlas.FROZEN),
              "g39_result_sha256": sha(G39), "script_sha256": sha(Path(__file__)),
              "parent_source_sha256": PARENT_SHA, "complete_tables": len(complete),
              "math_backend": backend_info(), "counts": dict(sorted(counts.items())),
              "touched_complete_tables": {name: len(ids) for name, ids in sorted(tables.items())},
              "rows": rows,
              "boundary": "冻结官方父代已接受弃牌的可见规则数学与合法动作；无赛后摸牌、收益或候选代码。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"counts": result["counts"], "tables": result["touched_complete_tables"]},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
