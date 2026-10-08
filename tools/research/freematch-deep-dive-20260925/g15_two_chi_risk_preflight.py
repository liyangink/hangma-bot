#!/usr/bin/env python3
"""G15 结果盲预检：下家两吃后，旧近副露扣分可让出多少留白自然牌形动作。"""

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
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g15-two-chi-risk-preflight-20260927/result.json')


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _number(value: object) -> float | None:
    if type(value) not in (int, float):
        return None
    number = float(value)
    return number if number - number == 0 else None


def _capacity(facts: dict, field: str) -> tuple[int, int] | None:
    items = facts.get(field)
    if not isinstance(items, list):
        return None
    values = [item.get("remaining_estimate") for item in items]
    if any(type(value) is not int or value < 0 for value in values):
        return None
    return sum(values), sum(value > 0 for value in values)


def _near(tile: str, melds: list[dict]) -> bool:
    """逐字重现父代数牌邻近副露谓词；它本身不等于实际鸣牌机会。"""

    if len(tile) < 2 or tile[0] not in "123456789" or tile[-1] not in "wbt":
        return False
    for meld in melds:
        for other in meld.get("tiles") or []:
            if (len(other) >= 2 and other[0] in "123456789"
                    and other[-1] == tile[-1]
                    and abs(int(other[0]) - int(tile[0])) <= 2):
                return True
    return False


def _overlay_active(detail: dict) -> bool:
    """避免把父代专项覆盖之后的总分误当基础近副露项。"""

    for key, value in detail.items():
        if key in ("r18_opportunity_overlay", "r18_gang_dominance_overlay",
                   "r18_seven_pairs_value_overlay", "two_wealth_piao_keeps_baotou_cf",
                   "hu_vs_nonwealth_baotou_cf"):
            if isinstance(value, dict) and value.get("triggered") is True:
                return True
    return False


def _suit_only(facts: dict, parent: dict) -> bool:
    """自然牌形保护：三向听不退，旧容量不退，普通型须有实际新进张。"""

    for field in ("shanten_after", "standard_shanten_after", "seven_pairs_shanten_after"):
        if (type(facts.get(field)) is not int or type(parent.get(field)) is not int
                or facts[field] > parent[field]):
            return False
    for field in ("useful_tiles", "standard_useful_tiles", "seven_pairs_useful_tiles"):
        a, b = _capacity(facts, field), _capacity(parent, field)
        if a is None or b is None or a[0] < b[0]:
            return False
    ordinary, old = _capacity(facts, "standard_useful_tiles"), _capacity(parent, "standard_useful_tiles")
    return ordinary[0] > old[0] or ordinary[1] > old[1]


def main() -> None:
    """审计只读父代动作前观察、规则事实与评分；不读后续牌墙或成绩。"""

    if OUT.exists():
        raise SystemExit("G15 两吃预检已有结果，拒绝覆盖")
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    complete_ids = atlas._complete_ids()
    counts = Counter()
    scopes: dict[str, set[str]] = defaultdict(set)
    rows = []
    for room in frozen["rooms"]:
        audit = atlas.source.ROOT / room["audit_dir"]
        decisions = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decisions.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结父代动作审计大小漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("冻结父代源码摘要漂移")
        accepted = atlas.source._accepted(decisions)
        for context, request, plan in atlas.source.screen._iter_decisions(audit):
            if (context.get("game_id") not in complete_ids
                    or (request.get("window_key") or {}).get("phase") != "draw"):
                continue
            ranked = sorted(plan.get("candidates") or [], key=lambda item: item.get("rank", 10**9))
            if not ranked:
                continue
            parent = ranked[0]["action_key"]
            if not parent.startswith("discard:") or accepted.get(context.get("decision_id")) != parent:
                continue
            observation = request["observation"]
            seat = observation["seat"]
            next_seat = (seat + 1) % 4
            next_melds = observation["melds"][next_seat]
            if sum(meld.get("kind") == "chi" for meld in next_melds) < 2:
                continue
            counts["accepted_draw_windows_with_next_two_chi"] += 1
            scopes["two_chi"].add(context["game_id"])
            if any(row["action_key"] == "hu" for row in ranked):
                counts["hu_present_abstain"] += 1
                continue
            legal = {item["action_key"]: item.get("facts") or {} for item in
                     (request.get("rules") or {}).get("legal_candidates") or []}
            if len(legal) != len((request.get("rules") or {}).get("legal_candidates") or []):
                raise ValueError("合法动作键重复")
            original = []
            counterfactual = []
            for row in ranked:
                key = row["action_key"]
                if not key.startswith("discard:"):
                    continue
                score = _number(row.get("total_score"))
                detail = (row.get("score_trace") or {}).get("detail") or {}
                if score is None or _overlay_active(detail):
                    original = []
                    break
                tile = key.split(":", 1)[1]
                familiar = any(
                    seat_of_river != seat and tile in river
                    for seat_of_river, river in enumerate(observation["discards"])
                )
                risk = _number(detail.get("risk_units"))
                can_remove = (
                    _near(tile, next_melds)
                    and not familiar
                    and risk is not None and risk >= 1.0
                    and detail.get("basis") == "direct_v2"
                )
                original.append((score, key))
                counterfactual.append((score + (6.0 if can_remove else 0.0), key, can_remove))
            if not original:
                counts["unknown_or_overlay_abstain"] += 1
                continue
            if min(original, key=lambda pair: (-pair[0], pair[1]))[1] != parent:
                counts["parent_score_reconstruction_mismatch"] += 1
                continue
            counts["base_score_reconstructed"] += 1
            best = min(counterfactual, key=lambda item: (-item[0], item[1]))
            if best[1] == parent or not best[2]:
                continue
            counts["raw_reorder"] += 1
            scopes["raw_reorder"].add(context["game_id"])
            parent_facts, next_facts = legal[parent], legal[best[1]]
            shape_safe = _suit_only(next_facts, parent_facts)
            whites = observation["my_hand"].count("白")
            if observation.get("drawn_tile") == "白" and len(observation["my_hand"]) % 3 == 1:
                whites += 1
            if shape_safe:
                counts["shape_safe_reorder"] += 1
                scopes["shape_safe_reorder"].add(context["game_id"])
                if whites > 0 and parent != "discard:白" and best[1] != "discard:白":
                    counts["shape_safe_white_reorder"] += 1
                    scopes["shape_safe_white_reorder"].add(context["game_id"])
            rows.append({"room_id": room["room_id"], "game_id": context["game_id"],
                         "round_no": context["round_no"], "trigger_seq": context["trigger_seq"],
                         "parent_action": parent, "alternate_action": best[1],
                         "parent_score": next(score for score, key in original if key == parent),
                         "alternate_old_score": next(score for score, key in original if key == best[1]),
                         "alternate_revised_score": best[0], "white_count": whites,
                         "shape_safe": shape_safe,
                         "parent_standard_support": _capacity(parent_facts, "standard_useful_tiles"),
                         "alternate_standard_support": _capacity(next_facts, "standard_useful_tiles")})
    result = {"schema": "g15-two-chi-risk-preflight/1", "outcome_blind": True,
              "source_frozen_sha256": _sha(FROZEN),
              "parent_source_sha256": frozen["parent_source_sha256"],
              "complete_official_tables": len(complete_ids),
              "counts": dict(sorted(counts.items())),
              "touched_complete_tables": {name: len(value) for name, value in sorted(scopes.items())},
              "rows": rows,
              "limitation": "只按现成最终分机械加回明确下家邻近项；两吃禁止再吃不等于弃牌安全，且本审计未生成候选源码、未跑完整桌收益。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "rows"}, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
