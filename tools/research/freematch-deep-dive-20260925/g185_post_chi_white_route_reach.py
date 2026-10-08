#!/usr/bin/env python3
"""G185：官方冻结 R18 审计里，结果盲普查吃后可弃白的规则事实。"""

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
PLAN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G185-POST-CHI-WHITE-ROUTE-REACH-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g185-post-chi-white-route-reach-20260928/result.json')


def sha(path: Path) -> str:
    """把官方来源清单、事前判据与分析代码绑定到结果。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def white_branch(item: dict) -> dict | None:
    """仅取规则已算的吃后弃白分支，不在策略侧重做吃牌数学。"""

    facts = item.get("facts") or {}
    branches = facts.get("followup_branches")
    if not isinstance(branches, list):
        return None
    matching = [branch for branch in branches
                if branch.get("followup_discard") == "白"]
    if len(matching) > 1:
        raise ValueError("同一吃候选出现重复白后继")
    return matching[0] if matching else None


def response_hand(observation: dict) -> list[str]:
    """吃牌响应前本人没有新摸牌，暗手应有 13−3×本人副露数张。"""

    seat = observation.get("seat")
    melds = observation.get("melds") or []
    if type(seat) is not int or not (0 <= seat < len(melds)):
        raise ValueError("响应窗本人座位或副露缺失")
    hand = list(observation.get("my_hand") or [])
    if observation.get("drawn_tile") is not None:
        raise ValueError("响应窗不应有本人新摸牌")
    if len(hand) != 13 - 3 * len(melds[seat]):
        raise ValueError("响应窗暗手张数不符")
    if any(hand.count(code) > 4 for code in set(hand)):
        raise ValueError("暗手中的物理牌张数超过四")
    return hand


def main() -> None:
    """只报告触达和事实缺口；不读取结算、不调整评分常数。"""

    if OUT.exists():
        raise FileExistsError("G185 已有结果，拒绝覆盖")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    complete_ids = atlas._complete_ids()
    counts = Counter()
    scopes = defaultdict(set)
    rows = []
    for room in frozen["rooms"]:
        audit = atlas.source.ROOT / room["audit_dir"]
        path = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if path.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结房决策文件长度漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("冻结房 R18 源码摘要漂移")
        accepted = atlas.source._accepted(path)
        for context, raw, plan in atlas.source.screen._iter_decisions(audit):
            game_id = context.get("game_id")
            if game_id not in complete_ids:
                continue
            if (raw.get("window_key") or {}).get("phase") != "response_chi":
                continue
            counts["all_confirmed_table_response_chi_windows"] += 1
            ranked = sorted(plan.get("candidates") or [],
                            key=lambda item: item.get("rank", 10**9))
            if not ranked:
                counts["missing_plan"] += 1
                continue
            parent = ranked[0].get("action_key")
            if accepted.get(context.get("decision_id")) != parent:
                counts["parent_not_confirmed"] += 1
                continue
            counts["accepted_parent_response_chi_windows"] += 1
            scopes["all"].add(game_id)
            observation = raw["observation"]
            if (observation.get("rule_state") or {}).get("baotou") is not True:
                continue
            counts["already_baotou"] += 1
            try:
                hand = response_hand(observation)
            except ValueError:
                counts["response_hand_not_reconstructed"] += 1
                continue
            whites = hand.count("白")
            if whites < 1:
                continue
            counts["already_baotou_with_white"] += 1
            legal = raw.get("rules") or {}
            candidates = legal.get("legal_candidates") or []
            if len({item.get("action_key") for item in candidates}) != len(candidates):
                raise ValueError("同一窗口规则合法候选动作键重复")
            eligible = []
            for item in candidates:
                key = item.get("action_key") or ""
                if not key.startswith("chi:"):
                    continue
                counts["legal_chi_candidates_in_baotou_white_windows"] += 1
                branch = white_branch(item)
                if branch is None:
                    continue
                counts["legal_chi_white_followup_branches"] += 1
                facts = item.get("facts") or {}
                if branch.get("combined_shanten") != 0 or facts.get("baotou_after") is not True:
                    continue
                eligible.append((item, branch))
            if not eligible:
                continue
            counts["possible_chi_then_white_windows"] += 1
            scopes["possible"].add(game_id)
            if parent == "pass":
                counts["parent_pass_possible_chi_then_white"] += 1
                scopes["parent_pass"].add(game_id)
            score_map = {item.get("action_key"): item.get("total_score")
                         for item in ranked}
            choices = []
            for item, branch in eligible:
                key = item["action_key"]
                facts = item["facts"]
                best_code = facts.get("best_followup_discard")
                best_branch = next((entry for entry in facts.get("followup_branches") or []
                                    if entry.get("followup_discard") == best_code), None)
                same_shape = (best_branch is not None
                              and (branch.get("combined_shanten"),
                                   branch.get("support_remaining")) ==
                                  (best_branch.get("combined_shanten"),
                                   best_branch.get("support_remaining")))
                if same_shape:
                    counts["white_same_best_shanten_and_support"] += 1
                choices.append({
                    "action_key": key,
                    "best_followup_discard": best_code,
                    "white_branch_shanten": branch["combined_shanten"],
                    "white_branch_public_support": branch.get("support_remaining"),
                    "white_same_best_shanten_and_support": same_shape,
                    "r18_score_gap_parent_minus_chi": (
                        score_map[parent] - score_map[key]
                        if isinstance(score_map.get(parent), (int, float))
                        and isinstance(score_map.get(key), (int, float)) else None),
                })
            rows.append({
                "room_id": room["room_id"], "game_id": game_id,
                "round_no": context["round_no"],
                "trigger_seq": context["trigger_seq"],
                "seat": observation.get("seat"),
                "white_held": whites,
                "chain_count": (observation.get("rule_state") or {}).get("chain_count"),
                "wall_remaining": observation.get("remaining_tile_count"),
                "parent_action": parent, "choices": choices,
            })
    result = {
        "schema": "g185-post-chi-white-route-reach/1",
        "frozen_rooms_sha256": sha(atlas.FROZEN),
        "prereg_sha256": sha(PLAN), "script_sha256": sha(Path(__file__)),
        "parent_source_sha256": frozen["parent_source_sha256"],
        "complete_official_tables": len(complete_ids),
        "counts": dict(sorted(counts.items())),
        "scopes": {name: {
            "complete_tables": len(ids),
            "conditional_gain_for_plus2_all_tables": (
                2 * len(complete_ids) / len(ids) if ids else None),
        } for name, ids in sorted(scopes.items())},
        "rows": rows,
        "boundary": "候选级爆头不等于白后继分支爆头；结果盲触达不是策略收益。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False,
                              sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "rows"},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
