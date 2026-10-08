#!/usr/bin/env python3
"""按完整桌赛去重计数 G9 已见弃牌入口，估算达到目标所需影响量级。"""

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
import g8_public_response_train_model as fit
import g9_action_space_atlas as atlas
import g9_temporal_actionability as actionability


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g9-policy-impact-budget-20260927/result.json')
TARGET_POINTS_PER_TABLE = 2.0


def _group(value: float, cutoffs: list[float]) -> str:
    return "low" if value <= cutoffs[0] else "mid" if value <= cutoffs[1] else "high"


def main() -> None:
    """只按动作前规则事实筛入口；结算/未来墙不参与，量级不是收益估计。"""

    if OUT.exists():
        raise SystemExit("G9 影响量级结果已冻结，拒绝覆盖")
    probability, cutoffs = actionability._probabilities()
    source_meta = json.loads(fit.RESULT.read_text(encoding="utf-8"))
    frozen = json.loads(source.FROZEN.read_text(encoding="utf-8"))
    official_tables = source_meta["counts"]["official_games"]
    if official_tables != len({key[0] for key in probability}):
        raise ValueError("模型可评分完整桌数与官方训练牌谱不符")
    totals = Counter()
    games_by_group = defaultdict(set)
    windows_by_group = defaultdict(set)
    rooms_by_group = defaultdict(set)
    for room in frozen["rooms"]:
        audit = source.ROOT / room["audit_dir"]
        decision_file = audit / "participants" / source.ACTOR / "decisions.jsonl"
        if decision_file.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结房决策记录漂移")
        accepted = source._accepted(decision_file)
        for context, request, plan in source.screen._iter_decisions(audit):
            if (request.get("window_key") or {}).get("phase") != "draw":
                continue
            actual = accepted.get(context.get("decision_id"))
            if not actual or not actual.startswith("discard:"):
                continue
            key = (context["game_id"], context["round_no"], context["trigger_seq"] + 1)
            chance = probability.get(key)
            if chance is None:
                continue
            ranked = sorted(plan.get("candidates") or [], key=lambda item: item.get("rank", 10**9))
            if not ranked or ranked[0].get("action_key") != actual:
                totals["accepted_not_parent_first"] += 1
                continue
            group = _group(chance, cutoffs)
            legal = {candidate["action_key"]: candidate for candidate in
                     (request.get("rules") or {}).get("legal_candidates") or []}
            top = (legal.get(actual) or {}).get("facts") or {}
            top_shanten = top.get("shanten_after")
            top_support = atlas._support(top)
            top_score = ranked[0].get("total_score")
            if type(top_shanten) is not int or top_support is None or type(top_score) not in (int, float):
                totals["top_facts_unknown"] += 1
                continue
            totals[f"parent_first_{group}"] += 1
            for alternative in ranked[1:]:
                alt_key = alternative.get("action_key")
                if not isinstance(alt_key, str) or not alt_key.startswith("discard:"):
                    continue
                alt = (legal.get(alt_key) or {}).get("facts") or {}
                alt_support = atlas._support(alt)
                alt_score = alternative.get("total_score")
                if alt.get("shanten_after") != top_shanten or alt_support is None or type(alt_score) not in (int, float):
                    continue
                score_gap = float(top_score - alt_score)
                if score_gap < 0:
                    raise ValueError("父代排序与备选分数矛盾")
                for kind, field in (("standard", "standard_shanten_after"),
                                    ("seven_pairs", "seven_pairs_shanten_after")):
                    if not atlas._lower(alt.get(field), top.get(field)):
                        continue
                    scopes = [f"{kind}_same_shanten_{group}"]
                    if alt_support >= top_support:
                        scopes.append(f"{kind}_support_not_lower_{group}")
                        if score_gap <= 10:
                            scopes.append(f"{kind}_guarded_{group}")
                    for scope in scopes:
                        totals[f"alternatives_{scope}"] += 1
                        games_by_group[scope].add(key[0])
                        windows_by_group[scope].add(key)
                        rooms_by_group[scope].add(room["room_id"])
    scopes = {}
    for kind in ("standard", "seven_pairs"):
        for mode in ("same_shanten", "support_not_lower", "guarded"):
            for group in ("low", "mid", "high"):
                scope = f"{kind}_{mode}_{group}"
                games = len(games_by_group[scope])
                scopes[scope] = {
                    "official_tables_with_parent_trace_entry": games,
                    "action_windows": len(windows_by_group[scope]),
                    "official_rooms": len(rooms_by_group[scope]),
                    "required_net_gain_per_affected_table_for_plus2_overall":
                        None if games == 0 else TARGET_POINTS_PER_TABLE * official_tables / games,
                }
    result = {
        "schema": "g9-policy-impact-budget/1",
        "source_official_tables": official_tables,
        "source_rooms": len(frozen["rooms"]),
        "source_model_sha256": actionability.EXPECTED_MODEL_SHA256,
        "source_frozen_rooms_sha256": hashlib.sha256(source.FROZEN.read_bytes()).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "target_points_per_complete_table": TARGET_POINTS_PER_TABLE,
        "risk_tertile_cutoffs_for_exposure_only": cutoffs,
        "counts": dict(sorted(totals.items())),
        "scopes": scopes,
        "boundary": "父代自然轨迹的动作前覆盖与算术量级；非候选收益上界，改选可改变后续触发集合",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    summary = {key: value for key, value in scopes.items() if "_guarded_" in key}
    print(json.dumps({"source_official_tables": official_tables, "guarded": summary},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
