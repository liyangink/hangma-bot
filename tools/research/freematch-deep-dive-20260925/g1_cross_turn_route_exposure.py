#!/usr/bin/env python3
"""固定十房、结果盲统计放慢一档向听的合法弃牌路线入口。"""

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

from collections import Counter
import hashlib
import json
from pathlib import Path

import g1_route_exposure as prior


ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g1-cross-turn-route-exposure-01')
ROOM_IDS = (
    "a_b711a7c02a81", "a_9ee7874d4f99", "a_1b1218333c71",
    "a_aacdc2914766", "a_63b1b5d2ada6", "a_5f95901e0f28",
    "a_fa51c277a2d5", "a_d0c11d42d7ef", "a_d539acd906b5",
    "a_1efbcaa39ce9",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bucket_wall(value: object) -> str:
    if type(value) is not int:
        return "unknown"
    if value < 20:
        return "below_reserve"
    if value < 40:
        return "20_39"
    if value < 60:
        return "40_59"
    return "60_plus"


def family_vector(candidate: dict) -> tuple[int, int] | None:
    facts = candidate.get("facts") or {}
    standard = facts.get("standard_shanten_after")
    seven = facts.get("seven_pairs_shanten_after")
    if type(standard) is int and type(seven) is int:
        return standard, seven
    return None


def read_room(audit_dir: Path) -> tuple[Counter, list[dict], dict]:
    """只解析冻结策略输入/计划；不读取赛后桌分或未来事件。"""
    manifest_path = audit_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload = manifest.get("payload") or {}
    if payload.get("policy_version") != prior.VERSION:
        raise ValueError("发布策略版本不符：" + str(audit_dir))
    release = (payload.get("policy_release") or {}).get("release_package_id")
    if release != prior.RELEASE_ID:
        raise ValueError("冻结包 ID 不符：" + str(audit_dir))
    room_id = (manifest.get("context") or {}).get("tournament_id")
    decisions_path = audit_dir / "participants" / prior.ME / "decisions.jsonl"
    inputs = {}
    plans = {}
    counts = Counter()
    for line in decisions_path.open(encoding="utf-8"):
        record = json.loads(line)
        data = record.get("payload") or {}
        if record.get("kind") == "decision_input":
            request = data.get("request") or {}
            decision_id = request.get("decision_id")
            if decision_id in inputs:
                counts["duplicate_input"] += 1
            else:
                inputs[decision_id] = request
        elif record.get("kind") == "decision_planned":
            plan = data.get("returned_plan") or {}
            decision_id = plan.get("decision_id")
            if decision_id in plans:
                counts["duplicate_plan"] += 1
            else:
                plans[decision_id] = plan
    seen = set()
    windows = []
    for decision_id, request in inputs.items():
        observation = request.get("observation") or {}
        if observation.get("phase") != "draw":
            continue
        window_key = request.get("window_key") or {}
        key = tuple(window_key.get(name) for name in
                    ("game_id", "round_no", "trigger_seq", "phase", "seat"))
        if None in key:
            raise ValueError("不完整 WindowKey")
        if key in seen:
            counts["revised_window"] += 1
            continue
        seen.add(key)
        counts["draw_windows"] += 1
        plan = plans.get(decision_id)
        if plan is None:
            counts["missing_plan"] += 1
            continue
        ranked = plan.get("candidates") or []
        if not ranked:
            counts["empty_plan"] += 1
            continue
        top = min(ranked, key=lambda item: item.get("rank", 10**9))
        top_key = top.get("action_key")
        legal = ((request.get("rules") or {}).get("legal_candidates") or [])
        discards = {candidate.get("action_key"): candidate for candidate in legal
                    if (candidate.get("action") or {}).get("kind") == "discard"
                    and type((candidate.get("facts") or {}).get("shanten_after")) is int}
        if len(discards) < 2 or top_key not in discards:
            continue
        counts["parent_discard_multi_choice"] += 1
        parent = discards[top_key]
        s = parent["facts"]["shanten_after"]
        if s not in (0, 1, 2):
            continue
        counts["parent_s_0_2"] += 1
        alternatives = [candidate for candidate in discards.values()
                        if candidate["action_key"] != top_key
                        and candidate["facts"]["shanten_after"] == s + 1]
        if not alternatives:
            continue
        counts["has_s_plus_one_alternative"] += 1
        counts["parent_s:" + str(s)] += 1
        whites = sum(tile == "白" for tile in observation.get("my_hand") or [])
        white_bucket = "2_plus" if whites >= 2 else str(whites)
        dealer = observation.get("seat") == observation.get("dealer_seat")
        wall = bucket_wall(observation.get("remaining_tile_count"))
        counts["white:" + white_bucket] += 1
        counts["dealer:" + str(dealer).lower()] += 1
        counts["wall:" + wall] += 1
        parent_vector = family_vector(parent)
        parent_baotou = (parent.get("facts") or {}).get("baotou_after")
        scored = {item.get("action_key"): item.get("total_score") for item in ranked}
        top_score = scored.get(top_key)
        facts = Counter()
        gaps = []
        for candidate in alternatives:
            vector = family_vector(candidate)
            if vector is None:
                facts["family_vector_unknown"] += 1
            else:
                facts["family_vector_known"] += 1
                if parent_vector is not None and ((parent_vector[0] - vector[0])
                                                   * (parent_vector[1] - vector[1]) < 0):
                    facts["pareto_crossing"] += 1
            baotou = (candidate.get("facts") or {}).get("baotou_after")
            if parent_baotou is False and baotou is True:
                facts["baotou_false_to_true"] += 1
            entries = (candidate.get("facts") or {}).get("family_progress") or []
            if any(entry.get("route_status") == "witnessed"
                   and entry.get("progress") == "advance" for entry in entries):
                facts["witnessed_family_advance"] += 1
            if (candidate.get("value_facts") or {}).get("routes"):
                facts["direct_win_route"] += 1
            score = scored.get(candidate.get("action_key"))
            if type(top_score) in (int, float) and type(score) in (int, float):
                gaps.append(float(top_score) - float(score))
        counts["any_pareto_crossing"] += facts["pareto_crossing"] > 0
        counts["any_baotou_false_to_true"] += facts["baotou_false_to_true"] > 0
        counts["any_witnessed_family_advance"] += facts["witnessed_family_advance"] > 0
        counts["any_direct_win_route"] += facts["direct_win_route"] > 0
        counts["all_alternative_scores_known"] += len(gaps) == len(alternatives)
        windows.append({
            "game_id": key[0], "round_no": key[1], "trigger_seq": key[2],
            "seat": key[4], "parent_action": top_key,
            "parent_shanten": s, "parent_family_vector": parent_vector,
            "white_bucket": white_bucket, "dealer": dealer, "wall_bucket": wall,
            "alternative_count": len(alternatives),
            "fact_counts": dict(sorted(facts.items())),
            "best_sacrifice_score_gap": min(gaps) if gaps else None,
        })
    meta = {"room_id": room_id,
            "audit_dir": str(audit_dir.relative_to(ROOT)),
            "manifest_sha256": digest(manifest_path),
            "decisions_sha256": digest(decisions_path)}
    return counts, windows, meta


def main() -> None:
    """按冻结房号统计，不依赖后台续房后的滚动顺序。"""
    if OUT.exists():
        raise FileExistsError("筛查结果目录已存在，拒绝覆盖")
    ledger = json.loads(prior.LEDGER.read_text(encoding="utf-8"))
    by_id = {room.get("room_id"): _project_file(_PROJECT_ROOT, ROOT / room["audit_dir"])
             for room in ledger.get("rooms") or [] if room.get("room_id") in ROOM_IDS}
    if set(by_id) != set(ROOM_IDS):
        raise ValueError("冻结房号缺失于已结算账本")
    reports = []
    all_windows = []
    total = Counter()
    for room_id in ROOM_IDS:
        counts, windows, meta = read_room(by_id[room_id])
        if meta["room_id"] != room_id:
            raise ValueError("manifest 房号不符：" + room_id)
        reports.append({**meta, "counts": dict(sorted(counts.items()))})
        all_windows.extend({"room_id": room_id, **window} for window in windows)
        total.update(counts)
    gaps = [row["best_sacrifice_score_gap"] for row in all_windows
            if row["best_sacrifice_score_gap"] is not None]
    result = {"schema": "g1-cross-turn-route-exposure/1",
              "script_sha256": digest(Path(__file__)),
              "room_ids": list(ROOM_IDS), "rooms": reports,
              "total_counts": dict(sorted(total.items())),
              "score_gap_to_best_sacrifice": prior._percentiles(gaps),
              "windows_count": len(all_windows),
              "outcome_labels_opened": False}
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    (_project_file(_PROJECT_ROOT, OUT / "windows.json")).write_text(
        json.dumps({"schema": "g1-cross-turn-route-exposure-windows/1",
                    "windows": all_windows}, ensure_ascii=False,
                   sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"total_counts": result["total_counts"],
                      "score_gap_to_best_sacrifice": result["score_gap_to_best_sacrifice"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
