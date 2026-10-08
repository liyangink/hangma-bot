#!/usr/bin/env python3
"""结果盲固定 G10 分路线向听帕累托备选及独立房/场覆盖。"""

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

import g8_public_response_training_rows as source
import g9_action_space_atlas as atlas


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
FROZEN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-two-white-next-draw-20260927/frozen_rooms.json')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G10-ROUTE-OPTION-ACTION-VALUE-PREREG-2026-09-27.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g10-route-option-screen-20260927/result.json')
HONORS = set("东南西北中发")


def _strict_int(facts: dict, field: str) -> int | None:
    """规则缺失或布尔值都视为未知，不补默认向听。"""

    value = facts.get(field)
    return value if type(value) is int else None


def _capacity(facts: dict, field: str) -> int | None:
    """仅汇总规则模块已提供的公开剩余张数。"""

    entries = facts.get(field)
    if not isinstance(entries, list):
        return None
    values = [item.get("remaining_estimate") for item in entries]
    return sum(values) if all(type(value) is int for value in values) else None


def _hand(observation: dict) -> list[str]:
    """本次摸牌可单列；只用于统计白板和 G6 表面重合。"""

    hand = list(observation.get("my_hand") or [])
    drawn = observation.get("drawn_tile")
    if drawn is not None and len(hand) % 3 == 1:
        hand.append(drawn)
    return hand


def _route_values(facts: dict) -> tuple[int, int, int, int] | None:
    """返回综合/普通型/七对向听和合并有效张公开容量。"""

    values = tuple(_strict_int(facts, name) for name in
                   ("shanten_after", "standard_shanten_after", "seven_pairs_shanten_after"))
    support = atlas._support(facts)
    if any(value is None for value in values) or support is None:
        return None
    return (*values, support)


def _g6_surface(parent_action: str, alternate_action: str, parent_score: float,
                alternate_score: float, parent: dict, alternate: dict, hand: list[str]) -> bool:
    """仅统计 G6 公开条件的重合上界，不重算其特殊覆盖与正式候选。"""

    a_tile = parent_action.split(":", 1)[1]
    b_tile = alternate_action.split(":", 1)[1]
    if (a_tile[-1:] not in ("w", "b", "t") or b_tile not in HONORS or hand.count(b_tile) != 1
            or parent_score != alternate_score):
        return False
    a_standard = _capacity(parent, "standard_useful_tiles")
    b_standard = _capacity(alternate, "standard_useful_tiles")
    a_seven = _capacity(parent, "seven_pairs_useful_tiles")
    b_seven = _capacity(alternate, "seven_pairs_useful_tiles")
    return (None not in (a_standard, b_standard, a_seven, b_seven)
            and b_standard > a_standard and b_seven >= a_seven)


def main() -> None:
    """不看官方牌谱/结算；父代首选必须是明确已接受的真实弃牌。"""

    if OUT.exists():
        raise SystemExit("G10 结果盲筛查已有结果，拒绝覆盖")
    frozen_bytes = FROZEN.read_bytes()
    frozen = json.loads(frozen_bytes)
    totals = Counter()
    by_room = {}
    rows = []
    for room in frozen["rooms"]:
        audit = _project_file(_PROJECT_ROOT, ROOT / room["audit_dir"])
        decisions = audit / "participants" / source.ACTOR / "decisions.jsonl"
        if decisions.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结房动作审计字节数漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("父代源码身份漂移")
        accepted = source._accepted(decisions)
        counts = Counter()
        seen = set()
        for context, request, plan in source.screen._iter_decisions(audit):
            if (request.get("window_key") or {}).get("phase") != "draw":
                continue
            key = (context.get("game_id"), context.get("round_no"), context.get("trigger_seq"))
            if key in seen:
                raise ValueError("同一摸牌动作窗口重复")
            seen.add(key)
            ranked = sorted(plan.get("candidates") or [], key=lambda item: item.get("rank", 10**9))
            if not ranked or not ranked[0]["action_key"].startswith("discard:"):
                continue
            counts["parent_planned_discard_windows"] += 1
            parent_action = ranked[0]["action_key"]
            if accepted.get(context.get("decision_id")) != parent_action:
                counts["parent_not_accepted_as_planned"] += 1
                continue
            counts["parent_accepted_discard_windows"] += 1
            legal = {item["action_key"]: item.get("facts") or {} for item in
                     (request.get("rules") or {}).get("legal_candidates") or []}
            parent = legal.get(parent_action)
            if parent is None:
                raise ValueError("父代已执行弃牌不在规则合法候选")
            values = _route_values(parent)
            score_a = ranked[0].get("total_score")
            if values is None or type(score_a) not in (int, float):
                counts["parent_facts_missing"] += 1
                continue
            combined, standard, seven, support = values
            options = []
            for item in ranked[1:]:
                action = item.get("action_key")
                if not isinstance(action, str) or not action.startswith("discard:"):
                    continue
                alternate = legal.get(action)
                if alternate is None:
                    raise ValueError("评分备选不在规则合法候选")
                values_b = _route_values(alternate)
                score_b = item.get("total_score")
                if values_b is None or type(score_b) not in (int, float):
                    continue
                c, s, q, u = values_b
                if c != combined or s > standard or q > seven or (s == standard and q == seven) or u < support:
                    continue
                options.append((-(standard - s + seven - q), -float(score_b), -u, action,
                                values_b, alternate, float(score_b)))
            if not options:
                continue
            _gain_key, _score_key, _support_key, action_b, b_values, b_facts, score_b = min(options)
            c, s, q, u = b_values
            hand = _hand(request["observation"])
            kinds = (["standard"] if s < standard else []) + (["seven_pairs"] if q < seven else [])
            row = {"room_id": room["room_id"], "game_id": key[0], "round_no": key[1],
                   "trigger_seq": key[2], "parent_action": parent_action,
                   "alternate_action": action_b, "parent_score": float(score_a),
                   "alternate_score": score_b, "parent_route_shanten": [combined, standard, seven],
                   "alternate_route_shanten": [c, s, q], "parent_support": support,
                   "alternate_support": u, "white_count": hand.count("白"),
                   "wall_remaining": request["observation"].get("remaining_tile_count"),
                   "route_improvements": kinds, "eligible_alternatives": len(options),
                   "g6_surface_overlap": _g6_surface(parent_action, action_b, float(score_a),
                                                    score_b, parent, b_facts, hand)}
            rows.append(row)
            counts["selected_windows"] += 1
            counts["eligible_alternatives"] += len(options)
            for kind in kinds:
                counts[f"selected_{kind}"] += 1
            if row["g6_surface_overlap"]:
                counts["g6_surface_overlap"] += 1
        totals.update(counts)
        by_room[room["room_id"]] = dict(sorted(counts.items()))
    game_ids = {row["game_id"] for row in rows}
    score_gap = Counter()
    for row in rows:
        gap = row["parent_score"] - row["alternate_score"]
        score_gap["zero" if gap == 0 else "le10" if 0 < gap <= 10 else
                  "gt10" if gap > 10 else "negative"] += 1
    result = {"schema": "g10-route-option-outcome-blind-screen/1",
              "outcome_blind": True, "source_rooms": len(frozen["rooms"]),
              "source_frozen_rooms_sha256": hashlib.sha256(frozen_bytes).hexdigest(),
              "source_parent_sha256": frozen["parent_source_sha256"],
              "prereg_sha256": hashlib.sha256(PREREG.read_bytes()).hexdigest(),
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "counts": dict(sorted(totals.items())), "score_gap": dict(sorted(score_gap.items())),
              "selected_game_ids": len(game_ids),
              "selected_rooms": len({row["room_id"] for row in rows}),
              "by_route": {kind: {"windows": sum(kind in row["route_improvements"] for row in rows),
                                  "game_ids": len({row["game_id"] for row in rows
                                                   if kind in row["route_improvements"]})}
                           for kind in ("standard", "seven_pairs")},
              "exposure_gate_passed": len(game_ids) >= 150 and len({row["room_id"] for row in rows}) >= 50,
              "rows": rows, "by_room": by_room,
              "boundary": "仅动作前事实与已接受父代动作；不读取终局和他家暗手，不能作为收益或发布证据"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key not in ("rows", "by_room")},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
