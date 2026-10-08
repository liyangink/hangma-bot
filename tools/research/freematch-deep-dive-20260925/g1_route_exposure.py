#!/usr/bin/env python3
"""结果盲统计 R18 v2 的弃牌路线分歧与当前候选事实覆盖。

只读取已结算房的发布身份、决策输入和父代排序；不读取官方牌谱、
终局分、后续动作或账本小计。统计单位为真实动作窗口，重复修订按
``decision_id`` 去重。输出只描述可达机会，不推断收益。
"""

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

import argparse
import json
from collections import Counter
from itertools import combinations
from pathlib import Path

ROOT = _PROJECT_ROOT
LEDGER = _project_file(_PROJECT_ROOT, ROOT / "runs/auto-match-watchdog/auto-match-watchdog-state.json")
ME = "u_13495c3d79c8"
VERSION = "r18_integrated_positive_v2"
RELEASE_ID = "e82f904c2c1fb70beea3f195110c8b2db0648971ed3eaa9bfcbed1b6543de486"


def _family_vector(candidate: dict) -> tuple[int, int] | None:
    facts = candidate.get("facts") or {}
    standard = facts.get("standard_shanten_after")
    seven = facts.get("seven_pairs_shanten_after")
    if type(standard) is int and type(seven) is int:
        return standard, seven
    return None


def _percentiles(values: list[float]) -> dict:
    """报告父代分差分布；数值只是描述，不充当通过阈值。"""

    if not values:
        return {"n": 0}
    ordered = sorted(values)
    return {
        "n": len(ordered),
        "min": ordered[0],
        "p25": ordered[int((len(ordered) - 1) * 0.25)],
        "p50": ordered[int((len(ordered) - 1) * 0.50)],
        "p75": ordered[int((len(ordered) - 1) * 0.75)],
        "p95": ordered[int((len(ordered) - 1) * 0.95)],
        "max": ordered[-1],
    }


def audit_room(audit_dir: Path) -> dict:
    """一房仅解析真实决策输入与父代计划，不加载赛后结果。"""

    manifest = json.loads((audit_dir / "manifest.json").read_text(encoding="utf-8"))
    version = (manifest.get("payload") or {}).get("policy_version")
    if version != VERSION:
        raise ValueError(f"房间 {audit_dir} 的策略为 {version}，不是 {VERSION}")
    release = (((manifest.get("payload") or {}).get("policy_release") or {})
               .get("release_package_id"))
    if release != RELEASE_ID:
        raise ValueError(f"房间 {audit_dir} 的冻结包 ID 不符：{release}")
    decisions = audit_dir / "participants" / ME / "decisions.jsonl"
    inputs: dict[str, dict] = {}
    plans: dict[str, dict] = {}
    duplicates = Counter()
    for line in decisions.open(encoding="utf-8"):
        record = json.loads(line)
        payload = record.get("payload") or {}
        if record.get("kind") == "decision_input":
            request = payload.get("request") or {}
            decision_id = request.get("decision_id")
            if not decision_id:
                raise ValueError(f"决策输入缺 decision_id：{decisions}")
            if decision_id in inputs:
                duplicates["input"] += 1
            else:
                inputs[decision_id] = request
        elif record.get("kind") == "decision_planned":
            plan = payload.get("returned_plan") or {}
            decision_id = plan.get("decision_id")
            if not decision_id:
                raise ValueError(f"决策计划缺 decision_id：{decisions}")
            if decision_id in plans:
                duplicates["plan"] += 1
            else:
                plans[decision_id] = plan

    counts = Counter()
    margins: list[float] = []
    crossing_margins: list[float] = []
    seen_windows: set[tuple] = set()
    for decision_id, request in inputs.items():
        window = request.get("window_key") or {}
        window_key = tuple(window.get(key) for key in
                           ("game_id", "round_no", "trigger_seq", "phase", "seat"))
        if any(value is None for value in window_key):
            raise ValueError(f"决策窗口键不完整：{decision_id}")
        if window_key in seen_windows:
            counts["revised_window"] += 1
            continue
        seen_windows.add(window_key)
        counts["windows"] += 1
        counts[f"phase:{window.get('phase')}"] += 1
        plan = plans.get(decision_id)
        if plan is None:
            counts["missing_plan"] += 1
            continue
        legal = ((request.get("rules") or {}).get("legal_candidates") or [])
        discards = [candidate for candidate in legal
                    if (candidate.get("action") or {}).get("kind") == "discard"
                    and type((candidate.get("facts") or {}).get("shanten_after")) is int]
        if len(discards) < 2:
            continue
        counts["multi_discard_window"] += 1
        best_shanten = min(candidate["facts"]["shanten_after"] for candidate in discards)
        best = [candidate for candidate in discards
                if candidate["facts"]["shanten_after"] == best_shanten]
        if best_shanten <= 2:
            counts["near_shanten_window"] += 1
        if len(best) < 2:
            continue
        counts["min_shanten_tie"] += 1
        if best_shanten <= 2:
            counts["near_min_shanten_tie"] += 1
        valid = [candidate for candidate in best if _family_vector(candidate) is not None]
        if len(valid) < 2:
            continue
        counts["family_facts_tie"] += 1
        vectors = {_family_vector(candidate) for candidate in valid}
        if len(vectors) < 2:
            continue
        counts["family_diverse_tie"] += 1
        if best_shanten > 2:
            continue
        counts["near_family_diverse_tie"] += 1
        if any((candidate.get("value_facts") or {}).get("routes") for candidate in valid):
            counts["near_diverse_with_route"] += 1
        if min(vector[0] for vector in vectors) <= 2 and min(vector[1] for vector in vectors) <= 2:
            counts["near_both_branches_plausible"] += 1
        crossing = any((left[0] - right[0]) * (left[1] - right[1]) < 0
                       for left, right in combinations(vectors, 2))
        if crossing:
            counts["near_pareto_crossing"] += 1
            if any((candidate.get("value_facts") or {}).get("routes") for candidate in valid):
                counts["near_pareto_with_route"] += 1

        ranked = (plan.get("candidates") or [])
        if not ranked:
            counts["near_diverse_missing_rank"] += 1
            continue
        top = min(ranked, key=lambda candidate: candidate.get("rank", 10**9))
        by_key = {candidate.get("action_key"): candidate for candidate in valid}
        top_key = top.get("action_key")
        if top_key not in by_key:
            counts["near_diverse_parent_outside_min"] += 1
            continue
        top_vector = _family_vector(by_key[top_key])
        alternatives = [candidate for candidate in valid
                        if _family_vector(candidate) != top_vector]
        if not alternatives:
            continue
        counts["near_diverse_parent_has_alternative"] += 1
        scores = {candidate.get("action_key"): candidate.get("total_score")
                  for candidate in ranked}
        top_score = scores.get(top_key)
        alt_scores = [scores.get(candidate.get("action_key")) for candidate in alternatives]
        if type(top_score) in (int, float) and all(type(score) in (int, float)
                                                   for score in alt_scores):
            margins.append(float(top_score) - max(float(score) for score in alt_scores))
            if crossing:
                crossing_alternatives = [candidate for candidate in alternatives
                                         if (top_vector[0] - _family_vector(candidate)[0])
                                         * (top_vector[1] - _family_vector(candidate)[1]) < 0]
                if crossing_alternatives:
                    crossing_margins.append(float(top_score) - max(
                        float(scores[candidate["action_key"]])
                        for candidate in crossing_alternatives))
        else:
            counts["near_diverse_missing_score"] += 1
    return {
        "room_id": (manifest.get("context") or {}).get("tournament_id"),
        "audit_dir": str(audit_dir.relative_to(ROOT)),
        "counts": dict(sorted(counts.items())),
        "parent_margin_to_best_other_family": _percentiles(margins),
        "parent_margin_to_pareto_crossing": _percentiles(crossing_margins),
        "duplicate_records": dict(duplicates),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--last-rooms", type=int, default=10,
                        help="从已结算账本取最近几房 R18 v2；不读取房分")
    args = parser.parse_args()
    if args.last_rooms < 1:
        parser.error("--last-rooms 必须为正数")
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    selected: list[Path] = []
    for room in reversed(ledger.get("rooms") or []):
        audit_dir = _project_file(_PROJECT_ROOT, ROOT / room["audit_dir"])
        manifest = json.loads((audit_dir / "manifest.json").read_text(encoding="utf-8"))
        if (manifest.get("payload") or {}).get("policy_version") == VERSION:
            selected.append(audit_dir)
        if len(selected) == args.last_rooms:
            break
    selected.reverse()
    reports = [audit_room(path) for path in selected]
    total = Counter()
    for report in reports:
        total.update(report["counts"])
    print(json.dumps({"scope": "completed R18 v2 rooms, decision facts only",
                      "requested_rooms": args.last_rooms,
                      "actual_rooms": len(reports),
                      "total_counts": dict(sorted(total.items())),
                      "rooms": reports}, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
