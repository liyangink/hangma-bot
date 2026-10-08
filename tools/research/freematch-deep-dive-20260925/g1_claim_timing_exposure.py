#!/usr/bin/env python3
"""结果盲统计 R18 v2 鸣/过窗口的当前自摸机会与成形取舍。

只读取已结算房的发布身份、决策输入和父代排序；不读取官方牌谱、
后续动作、房分或终局结果。统计单位是去重后的真实动作窗口。
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
from pathlib import Path

from g1_route_exposure import LEDGER, ME, RELEASE_ID, ROOT, VERSION, _percentiles


def _support(candidate: dict) -> int | None:
    tiles = ((candidate.get("facts") or {}).get("useful_tiles") or [])
    estimates = [tile.get("remaining_estimate") for tile in tiles]
    if any(type(value) is not int or value < 0 for value in estimates):
        return None
    return sum(estimates)


def _shanten(candidate: dict) -> int | None:
    value = (candidate.get("facts") or {}).get("shanten_after")
    return value if type(value) is int else None


def _timing_bucket(pass_shanten: int, claim_shanten: int) -> str:
    if pass_shanten == 0 and claim_shanten == 0:
        return "pass_tenpai_claim_tenpai"
    if pass_shanten == 1 and claim_shanten == 0:
        return "pass_one_away_claim_tenpai"
    if claim_shanten < pass_shanten:
        return "claim_improves_other"
    if claim_shanten == pass_shanten:
        return "same_shanten_other"
    return "claim_worsens"


def audit_room(audit_dir: Path) -> dict:
    """核验冻结身份后，按动作窗口去重计算可见事实和父代排序。"""

    manifest = json.loads((audit_dir / "manifest.json").read_text(encoding="utf-8"))
    identity = manifest.get("payload") or {}
    release = (identity.get("policy_release") or {}).get("release_package_id")
    if identity.get("policy_version") != VERSION or release != RELEASE_ID:
        raise ValueError(f"发布身份不符：{audit_dir}")
    decisions = audit_dir / "participants" / ME / "decisions.jsonl"
    inputs: dict[str, dict] = {}
    plans: dict[str, dict] = {}
    duplicates = Counter()
    for line in decisions.open(encoding="utf-8"):
        record = json.loads(line)
        payload = record.get("payload") or {}
        if record.get("kind") == "decision_input":
            request = payload.get("request") or {}
            key = request.get("decision_id")
            if not key:
                raise ValueError(f"输入缺决策 ID：{decisions}")
            if key in inputs:
                duplicates["input"] += 1
            else:
                inputs[key] = request
        elif record.get("kind") == "decision_planned":
            plan = payload.get("returned_plan") or {}
            key = plan.get("decision_id")
            if not key:
                raise ValueError(f"计划缺决策 ID：{decisions}")
            if key in plans:
                duplicates["plan"] += 1
            else:
                plans[key] = plan

    counts = Counter()
    margin_by_bucket: dict[str, list[float]] = {}
    seen: set[tuple] = set()
    for decision_id, request in inputs.items():
        window = request.get("window_key") or {}
        phase = window.get("phase")
        if phase not in ("response_peng", "response_chi"):
            continue
        window_key = tuple(window.get(key) for key in
                           ("game_id", "round_no", "trigger_seq", "phase", "seat"))
        if any(value is None for value in window_key):
            raise ValueError(f"窗口键不完整：{decision_id}")
        if window_key in seen:
            counts["revised_window"] += 1
            continue
        seen.add(window_key)
        counts[f"response_window:{phase}"] += 1
        legal = (request.get("rules") or {}).get("legal_candidates") or []
        claims = [candidate for candidate in legal
                  if (candidate.get("action") or {}).get("kind") ==
                  ("chi" if phase == "response_chi" else "peng")]
        if not claims:
            continue
        counts["claim_window"] += 1
        counts[f"claim_window:{phase}"] += 1
        observation = request.get("observation") or {}
        seat = observation.get("seat")
        discarder = (observation.get("last_discard") or {}).get("seat")
        if (type(seat) is not int or type(discarder) is not int
                or not 0 <= seat < 4 or not 0 <= discarder < 4
                or observation.get("turn_seat") != discarder
                or observation.get("phase") != phase):
            raise ValueError(f"鸣牌位置事实不一致：{decision_id}")
        distance = (seat - discarder) % 4
        if distance not in (1, 2, 3) or (phase == "response_chi" and distance != 1):
            raise ValueError(f"鸣牌相对座位不一致：{decision_id}")
        counts[f"claim_distance:{phase}:d{distance}"] += 1
        passes = [candidate for candidate in legal
                  if (candidate.get("action") or {}).get("kind") == "pass"]
        if len(passes) != 1:
            counts["missing_unique_pass"] += 1
            continue
        pass_candidate = passes[0]
        pass_shanten = _shanten(pass_candidate)
        claim_shantens = [_shanten(candidate) for candidate in claims]
        if pass_shanten is None or any(value is None for value in claim_shantens):
            counts["missing_shanten_comparison"] += 1
            continue
        best_shanten = min(claim_shantens)
        bucket = _timing_bucket(pass_shanten, best_shanten)
        counts[f"opportunity:{bucket}"] += 1
        counts[f"opportunity:{phase}:{bucket}"] += 1
        counts[f"opportunity:d{distance}:{bucket}"] += 1
        if type(observation.get("remaining_tile_count")) is not int:
            counts["missing_wall_count"] += 1
        else:
            wall = observation["remaining_tile_count"]
            counts[f"wall:{'late' if wall <= 40 else 'middle' if wall <= 65 else 'early'}"] += 1
        if any((candidate.get("facts") or {}).get("best_followup_discard") is None
               for candidate in claims):
            counts["missing_claim_followup_discard"] += 1
        if pass_shanten == 0:
            pass_support = _support(pass_candidate)
            if pass_support is None:
                counts["missing_pass_support"] += 1
            elif pass_support > 0:
                counts["pass_tenpai_with_positive_support"] += 1
        support_relation = None
        if pass_shanten == 0 and best_shanten == 0:
            pass_support = _support(pass_candidate)
            claim_supports = [_support(candidate) for candidate in claims
                              if _shanten(candidate) == 0]
            if pass_support is not None and all(value is not None
                                                for value in claim_supports):
                best_support = max(claim_supports)
                support_relation = ("more" if best_support > pass_support else
                                    "equal" if best_support == pass_support else "less")
                counts[f"tenpai_support:{support_relation}"] += 1
        if (pass_candidate.get("value_facts") or {}).get("routes") or any(
                (candidate.get("value_facts") or {}).get("routes") for candidate in claims):
            counts["conditional_route_fact_present"] += 1
            counts[f"conditional_route_fact_present:{bucket}"] += 1

        plan = plans.get(decision_id)
        if plan is None:
            counts["missing_plan"] += 1
            continue
        ranked = plan.get("candidates") or []
        if not ranked:
            counts["empty_plan"] += 1
            continue
        top = min(ranked, key=lambda candidate: candidate.get("rank", 10**9))
        top_key = top.get("action_key")
        claim_keys = {candidate.get("action_key") for candidate in claims}
        choice = "claim" if top_key in claim_keys else "pass" if top_key == "pass" else "other"
        counts[f"parent_choice:{choice}"] += 1
        counts[f"parent_choice:{bucket}:{choice}"] += 1
        if support_relation is not None:
            counts[f"tenpai_support_parent:{support_relation}:{choice}"] += 1
        if bucket == "pass_tenpai_claim_tenpai" and choice == "claim":
            counts[f"tenpai_claim_by_distance:d{distance}"] += 1
            pass_support = _support(pass_candidate)
            chosen_claim = next(candidate for candidate in claims
                                if candidate.get("action_key") == top_key)
            chosen_support = _support(chosen_claim)
            if pass_support is not None and pass_support > 0:
                counts["tenpai_claim_skips_positive_support_draw"] += 1
            if pass_support is not None and chosen_support is not None:
                relation = ("more" if chosen_support > pass_support else
                            "equal" if chosen_support == pass_support else "less")
                counts[f"chosen_tenpai_support:{relation}"] += 1
                counts[f"chosen_tenpai_support_gain:{chosen_support - pass_support}"] += 1
        scores = {candidate.get("action_key"): candidate.get("total_score")
                  for candidate in ranked}
        pass_score = scores.get("pass")
        claim_scores = [scores.get(key) for key in claim_keys]
        if type(pass_score) in (int, float) and claim_scores and all(
                type(score) in (int, float) for score in claim_scores):
            margin_by_bucket.setdefault(bucket, []).append(
                max(float(score) for score in claim_scores) - float(pass_score))
        else:
            counts["missing_score_comparison"] += 1
    return {
        "room_id": (manifest.get("context") or {}).get("tournament_id"),
        "audit_dir": str(audit_dir.relative_to(ROOT)),
        "counts": dict(sorted(counts.items())),
        "claim_minus_pass_parent_score": {
            key: _percentiles(values) for key, values in sorted(margin_by_bucket.items())},
        "duplicate_records": dict(duplicates),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--last-rooms", type=int, default=10)
    parser.add_argument("--room-id", action="append", default=[],
                        help="按给定房号固定来源；可重复传入，优先于 --last-rooms")
    args = parser.parse_args()
    if args.last_rooms < 1:
        parser.error("--last-rooms 必须为正数")
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    selected: list[Path] = []
    if args.room_id:
        if len(args.room_id) != len(set(args.room_id)):
            parser.error("--room-id 不可重复")
        by_id = {room["room_id"]: room for room in ledger.get("rooms") or []}
        missing = [room_id for room_id in args.room_id if room_id not in by_id]
        if missing:
            parser.error(f"账本缺少指定已结算房：{missing}")
        selected = [_project_file(_PROJECT_ROOT, ROOT / by_id[room_id]["audit_dir"]) for room_id in args.room_id]
    else:
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
        # 房级分位数不能合并为总体分位数；只输出各房分布，避免伪精度。
    print(json.dumps({
        "scope": "completed R18 v2 rooms; decision facts and parent plan only",
        "requested_rooms": args.room_id if args.room_id else args.last_rooms,
        "actual_rooms": len(reports),
        "total_counts": dict(sorted(total.items())),
        "rooms": reports,
    }, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
