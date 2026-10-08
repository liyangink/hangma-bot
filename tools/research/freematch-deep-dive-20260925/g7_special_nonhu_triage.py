#!/usr/bin/env python3
"""三白板未胡自然窗：先锁结果盲样本，再读既有一次摸牌番值见证。"""

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
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import g7_special_opportunity_screen as opportunity  # noqa: E402
import natural_shape_loss_screen as screen  # noqa: E402

OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g7-special-nonhu-triage-20260927')
LOCK = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g7-special-nonhu-triage-20260927/selection-lock.json')
RESULT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g7-special-nonhu-triage-20260927/result.json')
SCREEN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g7-special-nonhu-triage-20260927/exploratory-full-screen.json')
EXCLUDE = "a_0525f4514164_r1_b1_t0"


def _digest(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _collect():
    """只按可见观察与合法动作筛选；不读取番值路线或桌赛结局。"""
    by_group = defaultdict(list)
    seen = set()
    counters = Counter()
    for group, rooms in opportunity.GROUPS.items():
        for room in rooms:
            for run in sorted((screen.ROOT / "artifacts/sessions" / room / "audit/runs").glob("*")):
                manifest = run / "manifest.json"
                if not manifest.is_file():
                    continue
                release = ((json.loads(manifest.read_text(encoding="utf-8")).get("payload") or {})
                           .get("policy_release") or {})
                if release.get("candidate_source_sha256") != screen.PARENT_SHA256:
                    continue
                for context, request, plan in screen._iter_decisions(run):
                    key = (context.get("game_id"), context.get("round_no"),
                           context.get("trigger_seq"))
                    if key in seen:
                        continue
                    seen.add(key)
                    if key[0] == EXCLUDE:
                        continue
                    try:
                        row = opportunity._classify(request, plan)
                    except ValueError:
                        counters[group + "_invalid_shape"] += 1
                        continue
                    if (row is None or row["whites"] < 3 or row["top_type"] != "discard"
                            or row["discards"] < 2):
                        continue
                    actions = {action.get("action_key") for action in
                               (request.get("rules") or {}).get("legal_candidates") or []}
                    if row["top"] not in actions:
                        counters[group + "_parent_not_legal"] += 1
                        continue
                    by_group[group].append({"group": group, "room": room,
                                            "game_id": key[0], "round_no": key[1],
                                            "trigger_seq": key[2],
                                            "hash": hashlib.sha256("|".join(map(str, key)).encode()).hexdigest(),
                                            "parent": row["top"], "whites": row["whites"],
                                            "request_sha256": _digest(request),
                                            "request": request, "plan": plan})
                    counters[group + "_eligible_windows"] += 1
    return by_group, counters


def _select(by_group):
    selected = []
    for group in opportunity.GROUPS:
        by_game = {}
        for row in by_group[group]:
            game = row["game_id"]
            if game not in by_game or row["hash"] < by_game[game]["hash"]:
                by_game[game] = row
        selected.extend(sorted(by_game.values(), key=lambda row: row["hash"])[:12])
    return selected


def _capacity(action: dict, seat: int):
    """仅完整的一次摸牌互斥路线；未知显式返回 None。"""
    value = action.get("value_facts") or {}
    if value.get("coverage") != "complete":
        return None
    total = 0
    witness = []
    seen_tiles = set()
    for route in value.get("routes") or []:
        if route.get("followup_discard") is not None:
            return None
        conditions = route.get("conditions") or {}
        if conditions.get("draw_kind") != "normal":
            return None
        settlement = route.get("conditional_settlement") or {}
        delta = settlement.get("score_delta")
        fan = settlement.get("fan")
        if (type(fan) is not int or not isinstance(delta, list) or len(delta) != 4
                or type(delta[seat]) is not int):
            return None
        capacity = 0
        for tile in route.get("useful_tiles") or []:
            code = tile.get("code")
            remaining = tile.get("remaining_estimate")
            if (not isinstance(code, str) or code in seen_tiles
                    or type(remaining) is not int or remaining < 0):
                return None
            seen_tiles.add(code)
            capacity += remaining
        total += capacity * delta[seat]
        witness.append({"fan": fan, "capacity": capacity,
                        "self_delta": delta[seat],
                        "details": settlement.get("details"),
                        "baotou": conditions.get("baotou")})
    return {"weighted_self_delta": total, "routes": witness}


def _score(row):
    obs = row["request"]["observation"]
    seat = obs.get("seat")
    if type(seat) is not int or not 0 <= seat < 4:
        raise ValueError("缺少本人座位")
    actions = {action.get("action_key"): action for action in
               row["request"]["rules"]["legal_candidates"]}
    discards = {key: _capacity(action, seat) for key, action in actions.items()
                if isinstance(key, str) and key.startswith("discard:")}
    parent = row["parent"]
    known = {key: value for key, value in discards.items() if value is not None}
    best = (max(known, key=lambda key: (known[key]["weighted_self_delta"], key))
            if known else None)
    scores = {item.get("action_key"): item.get("total_score") for item in
              (row["plan"].get("candidates") or [])}
    return {key: row[key] for key in ("group", "room", "game_id", "round_no",
                                      "trigger_seq", "hash", "parent", "whites",
                                      "request_sha256")} | {
        "parent_score": scores.get(parent), "white_score": scores.get("discard:白"),
        "parent_one_draw": discards.get(parent),
        "white_one_draw": discards.get("discard:白"),
        "best_one_draw_key": best, "best_one_draw": known.get(best),
        "legal_discards": len(discards), "complete_one_draw": len(known),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("lock", "score", "screen"))
    args = parser.parse_args()
    by_group, counters = _collect()
    selected = _select(by_group)
    OUT.mkdir(parents=True, exist_ok=True)
    if args.mode == "screen":
        groups = {}
        for group, rows in by_group.items():
            by_game = {}
            for row in rows:
                game = row["game_id"]
                if game not in by_game or row["hash"] < by_game[game]["hash"]:
                    by_game[game] = row
            scored = [_score(row) for row in by_game.values()]
            gaps = [row for row in scored if row["parent_one_draw"] is not None
                    and row["best_one_draw"] is not None
                    and row["best_one_draw"]["weighted_self_delta"]
                    > row["parent_one_draw"]["weighted_self_delta"]]
            groups[group] = {"eligible_windows": len(rows), "official_games": len(scored),
                             "strict_one_draw_gaps": len(gaps),
                             "gap_keys": [{"game_id": row["game_id"],
                                           "round_no": row["round_no"],
                                           "trigger_seq": row["trigger_seq"],
                                           "parent": row["parent"],
                                           "best_one_draw_key": row["best_one_draw_key"]}
                                          for row in gaps]}
        payload = {"schema": "g7-special-nonhu-full-screen/1",
                   "parent_source_sha256": screen.PARENT_SHA256,
                   "groups": groups, "selection_counters": dict(counters),
                   "note": "结果盲但未事前锁定的动态探索频数；不是独立确认或收益样本"}
        SCREEN.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
        print(json.dumps(groups, ensure_ascii=False))
        return 0
    if args.mode == "lock":
        if LOCK.exists():
            raise SystemExit("选样锁已存在，不覆盖")
        locked = [{key: row[key] for key in ("group", "room", "game_id", "round_no",
                                             "trigger_seq", "hash", "parent", "whites",
                                             "request_sha256")} for row in selected]
        payload = {"schema": "g7-special-nonhu-lock/1",
                   "parent_source_sha256": screen.PARENT_SHA256, "windows": locked,
                   "selection_counters": dict(counters)}
        LOCK.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        print("locked", len(locked), "groups", dict(Counter(r["group"] for r in locked)),
              "sha256", hashlib.sha256(LOCK.read_bytes()).hexdigest())
        return 0
    if not LOCK.is_file():
        raise SystemExit("必须先执行 lock")
    locked = json.loads(LOCK.read_text(encoding="utf-8"))
    if locked.get("parent_source_sha256") != screen.PARENT_SHA256:
        raise SystemExit("选样锁父代身份不符")
    available = {(row["game_id"], row["round_no"], row["trigger_seq"]): row
                 for group in by_group.values() for row in group}
    scored = []
    for fixed in locked["windows"]:
        key = (fixed["game_id"], fixed["round_no"], fixed["trigger_seq"])
        row = available.get(key)
        if row is None or any(row.get(field) != fixed[field] for field in
                              ("group", "room", "hash", "parent", "whites", "request_sha256")):
            raise SystemExit("锁定窗口丢失或事实漂移：" + str(key))
        scored.append(_score(row))
    output = {"schema": "g7-special-nonhu-triage/1",
              "selection_lock_sha256": hashlib.sha256(LOCK.read_bytes()).hexdigest(),
              "rows": scored,
              "note": "仅已知下一次本人普通摸牌条件结算容量；不是实际概率或积分"}
    RESULT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print("scored", len(scored), "parent_complete",
          sum(row["parent_one_draw"] is not None for row in scored),
          "parent_one_draw_best", sum(row["best_one_draw_key"] == row["parent"]
                                      for row in scored))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
