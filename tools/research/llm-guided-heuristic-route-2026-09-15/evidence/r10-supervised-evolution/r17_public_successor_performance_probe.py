"""R17 P0 单次等价性能修订：跨根缓存相同最终公开叶。

不删除任何公开容量边，不改变受限/不受限双包络。唯一优化是把弃牌叶
规范化为（最终暗牌、最终公开计数、副露数）键；对称的“根弃 A、次弃 B”
与“根弃 B、次弃 A”若落到同一公开状态，只调用一次 hand_analysis 和
CandidateFacts 规则数学。完整逐边结果只计算 canonical digest，不落盘。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

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
import math
from pathlib import Path
import sys
import time
from typing import Any


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import r17_public_successor_pilot as raw  # noqa: E402
from hangma_bot.hangma import action_families, candidate_facts, hand_analysis  # noqa: E402
from hangma_bot.hangma.candidate_facts import FactsAnalysisError, _remaining, _remove_codes, _waiting_facts  # noqa: E402
from hangma_bot.hangma.engine import _build_context, _public_counts  # noqa: E402
from hangma_bot.hangma.internal_types import TILE_INDEX, TILE_ORDER, counts_from_tiles  # noqa: E402
from hangma_bot.kernel.actions import Discard, Gang, Hu, Tile  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r17-public-successor-performance-02-20260921')
RAW_RESULT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r17-public-successor-pilot-01-20260921/result.json')


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1)]


def _latency(rows: list[dict[str, Any]]) -> dict[str, float]:
    values = [row["elapsed_ms"] for row in rows if row["phase"] == "draw"]
    return {
        "mean_ms": sum(values) / len(values),
        "p50_ms": _percentile(values, 0.50),
        "p90_ms": _percentile(values, 0.90),
        "p95_ms": _percentile(values, 0.95),
        "p99_ms": _percentile(values, 0.99),
        "max_ms": max(values),
    }


def _leaf_facts(
    context: Any,
    public_after_root: tuple[Any, ...],
    meld_count: int,
    discard_code: str,
    cache: dict[tuple[Any, ...], dict[str, Any]],
    performance: Counter[str],
) -> dict[str, Any]:
    """把同一最终公开状态的规则数学合并，动作键仍按本叶重新挂接。"""

    full_codes = tuple(tile.code for tile in context.full_hand())
    after_codes = _remove_codes(full_codes, {discard_code: 1})
    final_public = raw._adjust_public_counts(public_after_root, {discard_code: 1})
    key = (tuple(sorted(after_codes, key=TILE_INDEX.get)), final_public, meld_count)
    cached = cache.get(key)
    if cached is None:
        value = _waiting_facts(
            tuple(Tile(code) for code in after_codes),
            meld_count,
            final_public,
            {},
            followup=None,
            replacement_unknown=False,
        )
        cached = {
            "fact_kind": value.fact_kind.value,
            "shanten": value.shanten_after,
            "standard_shanten": value.standard_shanten_after,
            "seven_pairs_shanten": value.seven_pairs_shanten_after,
            "support_remaining": sum(tile.remaining_estimate for tile in value.useful_tiles),
            "useful_tile_count": len(value.useful_tiles),
            "replacement_draw_unknown": value.replacement_draw_unknown,
        }
        cache[key] = cached
        performance["leaf_cache_misses"] += 1
    else:
        performance["leaf_cache_hits"] += 1
    performance["logical_discard_leaf_requests"] += 1
    return {"action_key": "discard:" + discard_code, **cached}


def _edge_leaf(
    root: Any,
    current: Any,
    public_after_root: tuple[Any, ...],
    drawn_code: str,
    cache: dict[tuple[Any, ...], dict[str, Any]],
    performance: Counter[str],
) -> tuple[dict[str, Any], Counter[str], list[str]]:
    contexts = {
        "unrestricted": raw._future_context(current, root, drawn_code, catch_play=False),
        "drawn_only": raw._future_context(current, root, drawn_code, catch_play=True),
    }
    outcomes = {}
    union_gangs: dict[str, Any] = {}
    issues = []
    for regime, context in contexts.items():
        summary = hand_analysis.analyse_hand(context.full_hand(), root.meld_count)
        outcome = action_families.generate_candidates(context, summary)
        keys = []
        for candidate in outcome.candidates:
            if isinstance(candidate.action, (Hu, Gang, Discard)):
                keys.append(candidate.action_key)
                if isinstance(candidate.action, Gang):
                    union_gangs[candidate.action_key] = candidate
        outcomes[regime] = (tuple(keys), outcome.candidates)
        issues.extend(regime + ":" + issue.area + ":" + issue.reason for issue in outcome.issues)

    gangs, fact_issues = candidate_facts.attach_facts(
        contexts["unrestricted"], public_after_root, root.meld_count,
        tuple(union_gangs.values()),
    )
    issues.extend("facts:" + issue.area + ":" + issue.reason for issue in fact_issues)
    gang_map = {candidate.action_key: candidate for candidate in gangs}
    counts: Counter[str] = Counter()
    regimes = {}
    for regime, (keys, candidates) in outcomes.items():
        action_map = {candidate.action_key: candidate for candidate in candidates}
        hu = [key for key in keys if isinstance(action_map[key].action, Hu)]
        gang = [raw._facts_mapping(gang_map[key]) for key in keys if isinstance(action_map[key].action, Gang)]
        discards = [
            _leaf_facts(
                contexts[regime], public_after_root, root.meld_count,
                action_map[key].action.tile.code, cache, performance,
            )
            for key in keys
            if isinstance(action_map[key].action, Discard)
        ]
        pareto = raw._pareto(discards)
        counts[regime + "_hu"] += len(hu)
        counts[regime + "_gang"] += len(gang)
        counts[regime + "_discard"] += len(discards)
        counts[regime + "_discard_pareto"] += len(pareto)
        regimes[regime] = {"hu": bool(hu), "gang": gang, "discard_pareto": pareto}
    return regimes, counts, issues


def evaluate_once(
    windows: list[tuple[str, Any, list[str]]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    edge_rows = []
    window_rows = []
    global_counts: Counter[str] = Counter()
    global_performance: Counter[str] = Counter()
    route_issues = []
    projection_issues = []
    response_ids = []

    for window_id, request, origins in windows:
        started = time.perf_counter()
        local: Counter[str] = Counter()
        local_performance: Counter[str] = Counter()
        leaf_cache: dict[tuple[Any, ...], dict[str, Any]] = {}
        phase = request.observation.phase
        if phase != "draw":
            global_counts["response_fallback_windows"] += 1
            local["response_fallback_windows"] += 1
            response_ids.append(window_id)
            window_rows.append({
                "window_id": window_id, "origins": origins, "phase": phase,
                "elapsed_ms": (time.perf_counter() - started) * 1000.0,
                "counts": dict(sorted(local.items())),
                "performance_counts": {},
            })
            continue

        global_counts["draw_windows"] += 1
        local["draw_windows"] += 1
        context = _build_context(request.observation)
        public_counts = _public_counts(request.observation)
        meld_count = len(request.observation.melds[request.observation.seat])
        roots = [
            candidate for candidate in request.rules.legal_candidates
            if isinstance(candidate.action, Discard)
        ]
        for candidate in roots:
            global_counts["discard_roots"] += 1
            local["discard_roots"] += 1
            try:
                root = raw._discard_root(candidate, context, meld_count)
                counts34 = counts_from_tiles(root.hand)
                capacities = {}
                unknown = []
                for code in TILE_ORDER:
                    try:
                        capacity = _remaining(code, counts34, public_counts, root.newly_public)
                    except FactsAnalysisError:
                        unknown.append(code)
                        continue
                    if capacity > 0:
                        capacities[code] = capacity
                if unknown:
                    projection_issues.append({
                        "window_id": window_id, "action_key": candidate.action_key,
                        "kind": "public_capacity_unknown", "tile_codes": unknown,
                    })
                public_after_root = raw._adjust_public_counts(public_counts, root.newly_public)
            except Exception as exc:
                projection_issues.append({
                    "window_id": window_id, "action_key": candidate.action_key,
                    "kind": "discard_root_failed",
                    "error": type(exc).__name__ + ": " + str(exc),
                })
                global_counts["discard_roots_failed"] += 1
                local["discard_roots_failed"] += 1
                continue

            global_counts["discard_roots_covered"] += 1
            local["discard_roots_covered"] += 1
            route_groups, route_edges, problems = raw._route_check(
                window_id, candidate, root, capacities
            )
            global_counts["value_route_groups"] += route_groups
            global_counts["value_route_edges"] += route_edges
            local["value_route_groups"] += route_groups
            local["value_route_edges"] += route_edges
            route_issues.extend(problems)
            for drawn_code, capacity in capacities.items():
                global_counts["all_capacity_edges"] += 1
                local["all_capacity_edges"] += 1
                is_useful = drawn_code in root.useful_codes
                edge_key = "useful_edges" if is_useful else "non_useful_edges"
                global_counts[edge_key] += 1
                local[edge_key] += 1
                regimes, leaf_counts, issues = _edge_leaf(
                    root, context, public_after_root, drawn_code,
                    leaf_cache, local_performance,
                )
                global_counts.update(leaf_counts)
                local.update(leaf_counts)
                if issues:
                    projection_issues.append({
                        "window_id": window_id, "action_key": candidate.action_key,
                        "draw_tile": drawn_code, "kind": "future_leaf_rule_issues",
                        "issues": issues,
                    })
                edge_rows.append({
                    "window_id": window_id,
                    "root_action_key": candidate.action_key,
                    "root_shanten": root.shanten,
                    "draw_tile": drawn_code,
                    "remaining_capacity": capacity,
                    "edge_class": "useful" if is_useful else "non_useful",
                    "regimes": regimes,
                })

        global_performance.update(local_performance)
        window_rows.append({
            "window_id": window_id, "origins": origins, "phase": phase,
            "elapsed_ms": (time.perf_counter() - started) * 1000.0,
            "counts": dict(sorted(local.items())),
            "performance_counts": dict(sorted(local_performance.items())),
        })

    semantic_windows = [
        {key: value for key, value in row.items() if key not in ("elapsed_ms", "performance_counts")}
        for row in window_rows
    ]
    semantic = {
        "edges": edge_rows,
        "windows": semantic_windows,
        "counts": dict(sorted(global_counts.items())),
        "response_ids": response_ids,
    }
    return edge_rows, window_rows, {
        "counts": dict(sorted(global_counts.items())),
        "performance_counts": dict(sorted(global_performance.items())),
        "route_issues": route_issues,
        "projection_issues": projection_issues,
        "response_ids": response_ids,
        "semantic_digest": raw.canonical_digest(semantic),
    }


def main() -> None:
    if OUT.exists():
        raise SystemExit("R17 性能复核目录已存在；拒绝覆盖")
    OUT.mkdir(parents=True)
    raw_result = json.loads(RAW_RESULT.read_text(encoding="utf-8"))
    expected_digest = raw_result["semantic_digest"]
    windows = raw.r16.load_windows()
    first_edges, first_windows, first = evaluate_once(windows)
    second_edges, second_windows, second = evaluate_once(windows)
    cold_latency = _latency(first_windows)
    warm_latency = _latency(second_windows)
    equivalent = (
        first["semantic_digest"] == expected_digest
        and second["semantic_digest"] == expected_digest
    )
    deterministic = first["semantic_digest"] == second["semantic_digest"]
    performance_pass = (
        warm_latency["p99_ms"] <= raw.RESEARCH_P99_MS_MAX
        and warm_latency["max_ms"] <= raw.RESEARCH_WINDOW_MS_MAX
    )
    result = {
        "schema": "r17-public-successor-performance-result/1",
        "status": (
            "PASS_P0_PERFORMANCE_GATE"
            if equivalent and deterministic and performance_pass
            else (
                "FAIL_PERFORMANCE_AFTER_ONE_EQUIVALENT_OPTIMIZATION"
                if equivalent and deterministic else "FAIL_SEMANTIC_EQUIVALENCE"
            )
        ),
        "windows": len(windows),
        "tables": 0,
        "model_calls": 0,
        "strength_claim": False,
        "selection_eligible": False,
        "semantic_equivalence": {
            "passed": equivalent,
            "raw_digest": expected_digest,
            "cold_digest": first["semantic_digest"],
            "warm_digest": second["semantic_digest"],
        },
        "determinism": {"passed": deterministic},
        "counts": first["counts"],
        "performance_counts": first["performance_counts"],
        "latency": {"cold": cold_latency, "warm": warm_latency},
        "gate": {
            "passed": performance_pass,
            "p99_ms_max": raw.RESEARCH_P99_MS_MAX,
            "window_max_ms": raw.RESEARCH_WINDOW_MS_MAX,
            "observed_warm_p99_ms": warm_latency["p99_ms"],
            "observed_warm_max_ms": warm_latency["max_ms"],
        },
        "issues": {
            "route": len(first["route_issues"]),
            "projection": len(first["projection_issues"]),
        },
        "next_minimum_equivalent_optimization_if_failed": {
            "name": "BATCH_34_DRAW_TRANSITIONS_WITH_LAZY_FRONTIER",
            "scope": "在hangma一次传入根手牌，批量返回34种容量边共享的规范手牌分析；只在固定reducer实际读取时物化叶对象",
            "invariants": "全34容量边、双抓打包络、胡/杠单列、ValueRoute核对、canonical语义摘要全部不变",
            "stop_rule": "下一次优化仍不过冻结门则关闭当前深度骨架，先复盘规则投影与固定搜索深度，不生成候选",
        },
    }
    raw.write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    raw.write_json(_project_file(_PROJECT_ROOT, OUT / "per-window.json"), {
        "schema": "r17-public-successor-performance-per-window/1",
        "cold": first_windows, "warm": second_windows,
    })
    raw.write_json(_project_file(_PROJECT_ROOT, OUT / "frontier-sample.json"), raw.frontier_sample(first_edges, 12))
    raw.write_json(_project_file(_PROJECT_ROOT, OUT / "issues.json"), {
        "schema": "r17-public-successor-performance-issues/1",
        "route": first["route_issues"], "projection": first["projection_issues"],
    })
    runner = Path(__file__)
    raw.write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r17-public-successor-performance-manifest/1",
        "runner": {"path": str(runner), "sha256": hashlib.sha256(runner.read_bytes()).hexdigest()},
        "raw_result": {"path": str(RAW_RESULT), "sha256": hashlib.sha256(RAW_RESULT.read_bytes()).hexdigest()},
        "optimization": "跨根按最终暗牌+最终公开计数+meld_count缓存弃牌叶规则数学",
        "forbidden_changes": ["删除容量边", "删除不利叶", "合并抓打包络", "改变冻结阈值"],
        "outputs": ["result.json", "per-window.json", "frontier-sample.json", "issues.json"],
    })
    print(json.dumps({
        "status": result["status"], "equivalent": equivalent,
        "latency": result["latency"], "performance_counts": first["performance_counts"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
