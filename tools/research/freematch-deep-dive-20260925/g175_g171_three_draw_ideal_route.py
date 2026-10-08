#!/usr/bin/env python3
"""G175：对账重放 G171 实际改弃，计算同公开池三摸理想胡牌容量。"""

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
import concurrent.futures
import json
from pathlib import Path
import time

import g173_g171_route_facts as g173
import g171_pareto_width_development as g171
import g171_pareto_width_policy as candidate
import g7_three_self_draw_probe as g7
from hangma_bot.hangma.engine import _build_context
from hangma_bot.hangma.internal_types import counts_from_tiles
from hangma_bot.hangma.public_tile_counts import count_unseen_tiles
from hangma_bot.kernel.actions import Tile


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G175-G171-THREE-DRAW-IDEAL-ROUTE-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g175-g171-three-draw-ideal-route-20260928/result.json')
G173 = g173.OUT / "result.json"


def _evaluate(observation, parent: str, alternate: str) -> dict:
    """双臂共享当时公开未知池，缓存仅在同一窗内复用。"""
    wall = observation.remaining_tile_count
    if type(wall) is not int or wall <= 32:
        return {"status": "wall_boundary", "wall_remaining": wall}
    unknown = count_unseen_tiles(observation)
    if any(type(value) is not int or value < 0 for value in unknown):
        return {"status": "unknown_public_pool", "wall_remaining": wall}
    melds = len(observation.melds[observation.seat])
    full = _build_context(observation).full_hand()
    if len(full) != 14 - 3 * melds:
        return {"status": "invalid_hand_length", "wall_remaining": wall}
    if sum(unknown) < 3:
        return {"status": "unknown_pool_too_small", "wall_remaining": wall}
    arms = {}
    started = time.perf_counter()
    try:
        for name, action in (("parent", parent), ("alternate", alternate)):
            code = action.split(":", 1)[1]
            hand = list(full)
            hand.remove(Tile(code))
            counts = counts_from_tiles(tuple(hand))
            arms[name] = {
                "depth2": g7.favorable(counts, unknown, melds, 2),
                "depth3": g7.favorable(counts, unknown, melds, 3),
            }
    except (ValueError, IndexError) as exc:
        return {"status": "math_unavailable", "error": type(exc).__name__,
                "wall_remaining": wall}
    finally:
        g7.favorable.cache_clear()
        g7.summary.cache_clear()
    elapsed = (time.perf_counter() - started) * 1000.0
    return {
        "status": "complete", "wall_remaining": wall,
        "unknown_pool": sum(unknown), "meld_count": melds,
        "parent": arms["parent"], "alternate": arms["alternate"],
        "delta_depth2": arms["alternate"]["depth2"] - arms["parent"]["depth2"],
        "delta_depth3": arms["alternate"]["depth3"] - arms["parent"]["depth3"],
        "elapsed_ms": round(elapsed, 3),
    }


def run_one(unit: tuple[str, int, int, str, int], expected: dict) -> list[dict]:
    """同一模拟阶段对账后，才保留原改弃窗口的行动前理想容量。"""
    prior = json.loads(g171.panel.paired.unit_path(g171.OUT, unit).read_text(
        encoding="utf-8"))["stage"]
    captured = []
    original_select = candidate.select

    def traced(request, plan):
        key, evidence, consumed = original_select(request, plan)
        if key is not None:
            captured.append((request.decision_id, request.observation,
                             plan.candidates[0].action_key, key))
        return key, evidence, consumed

    candidate.select = traced
    try:
        replay = g171.run_unit(unit)["stage"]
    finally:
        candidate.select = original_select
    for field in ("focal_stage_score", "stage_totals_by_participant",
                  "status", "usable", "unresolved"):
        if prior[field] != replay[field]:
            raise ValueError("G175 阶段积分或运行漂移: " + str((unit, field)))
    if (g173._metrics_without_elapsed(prior["g171_metrics"])
            != g173._metrics_without_elapsed(replay["g171_metrics"])):
        raise ValueError("G175 改选轨迹漂移: " + str(unit))
    for old_table, new_table in zip(prior["tables"], replay["tables"], strict=True):
        for field in ("seed", "scores_by_seat", "hand_records", "hand_account",
                      "match_status", "policy_execution"):
            actual = json.loads(json.dumps(new_table[field], ensure_ascii=False))
            if old_table[field] != actual:
                raise ValueError("G175 双桌逐局对账漂移: " + str((unit, field)))
    if len(captured) != sum(row["status"] == "adopted"
                            for row in prior["g171_metrics"]):
        raise ValueError("G175 阶段改弃次数漂移")
    rows = []
    for decision_id, observation, parent, alternate in captured:
        identity = (unit[0], unit[1], unit[2], decision_id)
        source = expected.get(identity)
        if (source is None or source["parent_action"] != parent
                or source["alternate_action"] != alternate):
            raise ValueError("G175 与 G173 原改弃身份不一致")
        rows.append({"mix": unit[0], "root_index": unit[1],
                     "focal_seat": unit[2], "decision_id": decision_id,
                     "parent_action": parent, "alternate_action": alternate,
                     "parent_seven_competitive": (
                         source["parent_facts"]["seven_pairs_shanten_after"]
                         <= source["parent_facts"]["shanten_after"]),
                     **_evaluate(observation, parent, alternate)})
    return rows


def _summary(rows: list[dict]) -> dict:
    """所有 H/M 与七对路线层完整列正零负，不按窗口假设独立。"""
    out = {}
    for mix in g171.panel.MIXES:
        for seven in (False, True):
            subset = [row for row in rows if row["mix"] == mix
                      and row["parent_seven_competitive"] is seven]
            complete = [row for row in subset if row["status"] == "complete"]
            counts = Counter(row["status"] for row in subset)
            for row in complete:
                for depth in (2, 3):
                    delta = row[f"delta_depth{depth}"]
                    direction = "positive" if delta > 0 else "negative" if delta < 0 else "equal"
                    counts[f"depth{depth}_{direction}"] += 1
            elapsed = sorted(row["elapsed_ms"] for row in complete)
            out[f"{mix}/seven_competitive_{int(seven)}"] = {
                "windows": len(subset),
                "independent_roots": len({row["root_index"] for row in subset}),
                "counts": dict(sorted(counts.items())),
                "elapsed_ms": ({} if not elapsed else {
                    "p50": elapsed[len(elapsed)//2],
                    "p95": elapsed[int((len(elapsed)-1)*.95)],
                    "max": elapsed[-1]}),
            }
    return out


def main() -> None:
    """G173 身份固定且完整阶段重放，结果一次性不可覆盖。"""
    if OUT.exists():
        raise FileExistsError("G175 结果已存在，拒绝覆盖")
    source = json.loads(G173.read_text(encoding="utf-8"))
    if source["schema"] != "g173-g171-route-facts/1" or len(source["rows"]) != 112:
        raise ValueError("G175 G173 来源身份漂移")
    expected = {(r["mix"], r["root_index"], r["focal_seat"], r["decision_id"]): r
                for r in source["rows"]}
    if len(expected) != 112:
        raise ValueError("G175 G173 决策身份重复")
    units = sorted({(r["mix"], r["root_index"], r["focal_seat"],
                     g171.ARMS[1], g171.SEED) for r in source["rows"]})
    if len(units) != 92:
        raise ValueError("G175 原阶段数漂移")
    rows = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=2) as workers:
        futures = {workers.submit(run_one, unit, expected): unit for unit in units}
        for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
            rows.extend(future.result())
            if i % 16 == 0 or i == len(units):
                print(json.dumps({"replayed_stages": i,
                                  "planned_stages": len(units)}), flush=True)
    rows.sort(key=lambda r: (r["mix"], r["root_index"],
                             r["focal_seat"], r["decision_id"]))
    if len(rows) != 112 or {(
            r["mix"], r["root_index"], r["focal_seat"], r["decision_id"])
            for r in rows} != set(expected):
        raise ValueError("G175 已看改弃身份未全量对齐")
    payload = {
        "schema": "g175-g171-three-draw-ideal-route/1",
        "input_sha256": {name: g171.sha(path) for name, path in {
            "prereg": PREREG, "script": Path(__file__), "g173": G173,
            "g171_manifest": g171.OUT / "manifest.json",
            "g171_result": g171.OUT / "result.json",
            "g7_math": Path(g7.__file__),
        }.items()},
        "replayed_candidate_stages": len(units),
        "summary": _summary(rows), "rows": rows,
        "boundary": "G171 已看收益的无对手理想两/三摸机制诊断；非可执行线上候选或赛事价值。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                              indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"summary": payload["summary"]},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
