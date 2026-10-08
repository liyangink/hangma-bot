#!/usr/bin/env python3
"""结果盲盘点冻结父代的合法动作取舍，不读取官方后续事件或得分。"""

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


HERE = Path(__file__).resolve().parent
FROZEN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-two-white-next-draw-20260927/frozen_rooms.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g9-action-space-atlas-20260927/result.json')
KINDS = ("standard_faster", "seven_pairs_faster", "baotou_gain", "chain_advance")


def _support(facts: dict) -> int | None:
    """返回规则模块给出的即时公开剩余估计张数，未知时不补零。"""

    entries = facts.get("useful_tiles")
    if not isinstance(entries, list):
        return None
    amounts = [entry.get("remaining_estimate") for entry in entries]
    if any(type(amount) is not int for amount in amounts):
        return None
    return sum(amounts)


def _lower(alt: object, top: object) -> bool:
    """只比较两个明确整数的规则向听，不把布尔值当整数。"""

    return type(alt) is int and type(top) is int and alt < top


def _chain_advance(facts: dict) -> bool:
    """规则族进展中的飘杠链推进事实，不预测未来链成功。"""

    return any(item.get("family") == "chain" and item.get("progress") == "advance"
               for item in facts.get("family_progress") or [])


def main() -> None:
    """按独立官方房汇总动作前冲突窗口及父代放弃的路线事实。"""

    if OUT.exists():
        raise SystemExit("G9 动作图谱已冻结，拒绝覆盖")
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    totals = Counter()
    by_room = {}
    examples = defaultdict(list)
    tradeoff = Counter()
    for room in frozen["rooms"]:
        audit = source.ROOT / room["audit_dir"]
        decisions = audit / "participants" / source.ACTOR / "decisions.jsonl"
        if decisions.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结房动作审计字节数漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("冻结父代源码摘要漂移")
        counts = Counter()
        seen = set()
        for context, request, plan in source.screen._iter_decisions(audit):
            phase = (request.get("window_key") or {}).get("phase")
            key = (context.get("game_id"), context.get("round_no"),
                   context.get("trigger_seq"), phase)
            if key in seen:
                counts["duplicate_window"] += 1
                continue
            seen.add(key)
            ranked = sorted(plan.get("candidates") or [],
                            key=lambda item: item.get("rank", 10**9))
            if not ranked:
                counts["no_ranked_candidates"] += 1
                continue
            counts[f"phase_{phase}"] += 1
            legal = {item["action_key"]: item for item in
                     (request.get("rules") or {}).get("legal_candidates") or []}
            if len(legal) != len((request.get("rules") or {}).get("legal_candidates") or []):
                raise ValueError("规则候选动作键重复")
            top_key = ranked[0]["action_key"]
            if top_key not in legal:
                raise ValueError("父代首选不在合法候选")
            if phase != "draw" or not top_key.startswith("discard:"):
                continue
            top = legal[top_key].get("facts") or {}
            top_shanten = top.get("shanten_after")
            top_support = _support(top)
            top_score = ranked[0].get("total_score")
            if type(top_shanten) is not int or top_support is None or type(top_score) not in (int, float):
                counts["draw_top_facts_unknown"] += 1
                continue
            counts["draw_discard_scored"] += 1
            window_kinds = set()
            for alternative in ranked[1:]:
                alt_key = alternative["action_key"]
                if not alt_key.startswith("discard:"):
                    continue
                if alt_key not in legal:
                    raise ValueError("父代备选不在合法候选")
                alt = legal[alt_key].get("facts") or {}
                if alt.get("shanten_after") != top_shanten:
                    continue
                alt_support = _support(alt)
                alt_score = alternative.get("total_score")
                if alt_support is None or type(alt_score) not in (int, float):
                    counts["same_shanten_alt_facts_unknown"] += 1
                    continue
                counts["same_shanten_alternatives"] += 1
                observed = set()
                if _lower(alt.get("standard_shanten_after"), top.get("standard_shanten_after")):
                    observed.add("standard_faster")
                if _lower(alt.get("seven_pairs_shanten_after"), top.get("seven_pairs_shanten_after")):
                    observed.add("seven_pairs_faster")
                if alt.get("baotou_after") is True and top.get("baotou_after") is False:
                    observed.add("baotou_gain")
                if _chain_advance(alt) and not _chain_advance(top):
                    observed.add("chain_advance")
                for kind in observed:
                    counts[f"alternative_{kind}"] += 1
                    window_kinds.add(kind)
                    support_delta = alt_support - top_support
                    score_gap = float(top_score - alt_score)
                    tradeoff[f"{kind}_support_" + (
                        "higher" if support_delta > 0 else
                        "equal" if support_delta == 0 else "lower")] += 1
                    tradeoff[f"{kind}_score_gap_" + (
                        "zero" if score_gap == 0 else
                        "le_10" if 0 < score_gap <= 10 else
                        "gt_10" if score_gap > 10 else "negative")] += 1
                    if support_delta >= 0 and score_gap <= 10:
                        tradeoff[f"{kind}_support_not_lower_and_score_gap_le_10"] += 1
                    if len(examples[kind]) < 20:
                        examples[kind].append({
                            "room_id": room["room_id"], "game_id": key[0],
                            "round_no": key[1], "trigger_seq": key[2],
                            "parent_action": top_key, "alternative_action": alt_key,
                            "shanten_after": top_shanten,
                            "parent_support": top_support, "alternative_support": alt_support,
                            "parent_score_gap": float(top_score - alt_score),
                            "wall_remaining": request["observation"].get("remaining_tile_count"),
                            "parent_standard_shanten": top.get("standard_shanten_after"),
                            "alternative_standard_shanten": alt.get("standard_shanten_after"),
                            "parent_seven_pairs_shanten": top.get("seven_pairs_shanten_after"),
                            "alternative_seven_pairs_shanten": alt.get("seven_pairs_shanten_after")})
            for kind in window_kinds:
                counts[f"window_{kind}"] += 1
        if counts["duplicate_window"]:
            raise ValueError("冻结房存在重复窗口，图谱不能去重后继续")
        by_room[room["room_id"]] = dict(sorted(counts.items()))
        totals.update(counts)
    result = {
        "schema": "g9-action-space-atlas/1",
        "source_rooms": len(by_room),
        "source_frozen_rooms_sha256": hashlib.sha256(FROZEN.read_bytes()).hexdigest(),
        "source_parent_sha256": frozen["parent_source_sha256"],
        "script_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "outcome_blind": True,
        "totals": dict(sorted(totals.items())),
        "alternative_tradeoff": dict(sorted(tradeoff.items())),
        "rooms_with_window": {kind: sum(row.get(f"window_{kind}", 0) > 0
                                        for row in by_room.values()) for kind in KINDS},
        "by_room": by_room,
        "first_examples": dict(examples),
        "boundary": "仅证实父代取舍与规则可见事实；不表示备选行动更优或整桌收益为正"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ("by_room", "first_examples")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
