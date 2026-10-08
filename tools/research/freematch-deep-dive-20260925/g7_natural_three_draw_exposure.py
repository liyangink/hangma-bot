#!/usr/bin/env python3
"""G7a 预登记自然样本：仅用玩家可见状态算两/三次本人摸牌的胡牌容量。"""

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
import sys
from time import perf_counter

ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import g7_three_self_draw_probe as draw_math  # noqa: E402
import natural_shape_loss_screen as screen  # noqa: E402
from hangma_bot.application.audit_codec import decision_request_from_json  # noqa: E402
from hangma_bot.hangma.internal_types import counts_from_tiles  # noqa: E402
from hangma_bot.hangma.public_tile_counts import count_unseen_tiles  # noqa: E402
from hangma_bot.kernel.actions import Tile  # noqa: E402

GROUPS = {
    "pm": screen.ROOMS[:6],
    "recent": ("r18-sse-freematch-campaign-20260925b",),
    "historical": ("r18-auto-match-campaign-20260923",),
}
EXCLUDE_DISCOVERY = "a_0525f4514164_r1_b1_t0"
LOCK = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g7-three-draw-exposure-20260927/selection-lock.json')


def _eligible(request: dict, plan: dict):
    """按预登记可见条件取 A 与动作键最小的 B；缺字段直接弃权。"""
    obs = request.get("observation") or {}
    planned = plan.get("candidates") or []
    if obs.get("phase") != "draw" or not planned:
        return None
    a_key = planned[0].get("action_key")
    if not isinstance(a_key, str) or not a_key.startswith("discard:") or a_key[-1] not in "wbt":
        return None
    actions = {row.get("action_key"): row for row in
               (request.get("rules") or {}).get("legal_candidates") or []}
    a = (actions.get(a_key) or {}).get("facts") or {}
    shanten = a.get("shanten_after")
    if type(shanten) is not int or not 0 <= shanten <= 2:
        return None
    a_u = screen._useful_capacity(a, "useful_tiles")
    if a_u is None:
        return None
    if any(type(a.get(field)) is not int for field in
           ("standard_shanten_after", "seven_pairs_shanten_after")):
        return None
    scores = {entry.get("action_key"): entry.get("total_score") for entry in planned}
    a_score = scores.get(a_key)
    if type(a_score) not in (int, float):
        return None
    hand = list(obs.get("my_hand") or [])
    if len(hand) == 13 and obs.get("drawn_tile") is not None:
        hand.append(obs["drawn_tile"])
    wealth = (obs.get("rule_state") or {}).get("wealth_god")
    eligible = []
    for b_key, action in actions.items():
        if not isinstance(b_key, str) or b_key[:8] != "discard:":
            continue
        tile = b_key[8:]
        if tile not in screen.SINGLE_HONORS or tile == wealth or hand.count(tile) != 1:
            continue
        b = action.get("facts") or {}
        if b.get("shanten_after") != shanten:
            continue
        if screen._useful_capacity(b, "useful_tiles") != a_u:
            continue
        if any(type(b.get(field)) is not int or b[field] > a[field] for field in
               ("standard_shanten_after", "seven_pairs_shanten_after")):
            continue
        if type(scores.get(b_key)) not in (int, float) or scores[b_key] != a_score:
            continue
        eligible.append(b_key)
    return (a_key, min(eligible), shanten, hand.count("白")) if eligible else None


def _digest(key):
    raw = "|".join(str(part) for part in key)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _sample(rows):
    """每场先保留哈希最小窗口；每组按白板/向听槽位选 8+8+8。"""
    by_game = {}
    for row in rows:
        game = row["game_id"]
        if game not in by_game or row["hash"] < by_game[game]["hash"]:
            by_game[game] = row
    candidates = list(by_game.values())
    buckets = {
        "two_white": [row for row in candidates if row["whites"] >= 2],
        "near_low_white": [row for row in candidates if row["whites"] < 2 and row["shanten"] <= 1],
        "rest": [row for row in candidates if row["whites"] < 2 and row["shanten"] == 2],
    }
    selected = []
    for bucket in ("two_white", "near_low_white", "rest"):
        selected.extend(sorted(buckets[bucket], key=lambda row: row["hash"])[:8])
    if len(selected) < 24:
        taken = {row["game_id"] for row in selected}
        selected.extend(sorted((row for row in candidates if row["game_id"] not in taken),
                               key=lambda row: row["hash"])[:24-len(selected)])
    return sorted(selected, key=lambda row: row["hash"])


def _evaluate(row):
    """算 A/B 的两/三摸容量；显式保留未知和异常，绝不填零。"""
    request = decision_request_from_json(row["request"])
    obs = request.observation
    unseen = count_unseen_tiles(obs)
    if any(value is None for value in unseen):
        raise ValueError("公开未知容量不完整")
    melds = len(obs.melds[obs.seat])
    expected = 14 - 3*melds
    hand = list(obs.my_hand)
    if len(hand) == expected-1 and obs.drawn_tile is not None:
        hand.append(obs.drawn_tile)
    if len(hand) != expected:
        raise ValueError("摸牌后暗手长度不合法")
    values = {}
    started = perf_counter()
    for key in (row["a"], row["b"]):
        tile = Tile(key[8:])
        after = list(hand)
        after.remove(tile)
        counts = counts_from_tiles(tuple(after))
        values[key] = {str(depth): draw_math.favorable(counts, unseen, melds, depth)
                       for depth in (2, 3)}
    elapsed_ms = round((perf_counter()-started)*1000, 3)
    draw_math.favorable.cache_clear()
    draw_math.summary.cache_clear()
    output = {key: row[key] for key in ("group", "room", "game_id", "round_no",
                                          "trigger_seq", "hash", "a", "b", "shanten", "whites")}
    output.update({"unknown_pool": sum(unseen), "capacity": values, "elapsed_ms": elapsed_ms,
                   "delta_2": values[row["b"]]["2"]-values[row["a"]]["2"],
                   "delta_3": values[row["b"]]["3"]-values[row["a"]]["3"]})
    return output


def main() -> int:
    all_rows = defaultdict(list)
    seen = set()
    counters = Counter()
    for group, rooms in GROUPS.items():
        for room in rooms:
            audit = _project_file(_PROJECT_ROOT, ROOT / "artifacts/sessions" / room / "audit/runs")
            for run in sorted(audit.glob("*")):
                manifest = run / "manifest.json"
                if not manifest.is_file():
                    continue
                release = ((json.loads(manifest.read_text(encoding="utf-8")).get("payload") or {})
                           .get("policy_release") or {})
                if release.get("candidate_source_sha256") != screen.PARENT_SHA256:
                    continue
                for context, request, plan in screen._iter_decisions(run):
                    key = (context.get("game_id"), context.get("round_no"), context.get("trigger_seq"))
                    if key in seen:
                        counters["duplicate"] += 1
                        continue
                    seen.add(key)
                    pair = _eligible(request, plan)
                    if pair is None:
                        continue
                    counters[group + "_eligible_windows"] += 1
                    a, b, shanten, whites = pair
                    all_rows[group].append({"group": group, "room": room, "game_id": key[0],
                                            "round_no": key[1], "trigger_seq": key[2],
                                            "hash": _digest(key), "a": a, "b": b,
                                            "shanten": shanten, "whites": whites,
                                            "request": request})
    results = []
    locked = None
    if LOCK.is_file():
        locked = json.loads(LOCK.read_text(encoding="utf-8"))
        if locked.get("parent_source_sha256") != screen.PARENT_SHA256:
            raise SystemExit("选样锁与冻结父代摘要不符")
    for group in GROUPS:
        if locked is None:
            selected = _sample(all_rows[group])
        else:
            available = {(row["game_id"], row["round_no"], row["trigger_seq"]): row
                         for row in all_rows[group]}
            selected = []
            for fixed in locked["windows"]:
                if fixed["group"] != group:
                    continue
                key = (fixed["game_id"], fixed["round_no"], fixed["trigger_seq"])
                row = available.get(key)
                if row is None or any(row.get(field) != fixed[field] for field in
                                      ("room", "hash", "a", "b", "shanten", "whites")):
                    raise SystemExit("冻结选样窗口缺失或可见事实漂移：" + str(key))
                selected.append(row)
        counters[group + "_selected"] = len(selected)
        for row in selected:
            if row["game_id"] == EXCLUDE_DISCOVERY:
                counters["discovery_excluded"] += 1
                continue
            try:
                results.append(_evaluate(row))
            except (ValueError, KeyError) as error:
                counters[group + "_invalid"] += 1
                print("跳过不可判窗口", row["group"], row["game_id"], str(error), file=sys.stderr)
    aggregate = {}
    for group in GROUPS:
        subset = [row for row in results if row["group"] == group]
        data = {}
        for depth in (2, 3):
            field = f"delta_{depth}"
            data[field] = {"positive": sum(row[field] > 0 for row in subset),
                           "zero": sum(row[field] == 0 for row in subset),
                           "negative": sum(row[field] < 0 for row in subset)}
        data["new_three_only"] = sum(row["delta_2"] == 0 and row["delta_3"] != 0
                                      for row in subset)
        data["windows"] = len(subset)
        data["runtime_ms_max"] = max((row["elapsed_ms"] for row in subset), default=None)
        aggregate[group] = data
    output = {"schema": "g7-natural-three-draw-exposure/1", "counters": dict(counters),
              "aggregate": aggregate, "selected": results,
              "selection_lock_sha256": (hashlib.sha256(LOCK.read_bytes()).hexdigest()
                                        if locked is not None else None),
              "note": "赛前可见未知池均匀代理；不是实际胡率、番值或净积分"}
    out = _project_file(_PROJECT_ROOT, HERE / "evidence/g7-three-draw-exposure-20260927/result.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"counters": output["counters"], "aggregate": aggregate,
                      "output": str(out)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
