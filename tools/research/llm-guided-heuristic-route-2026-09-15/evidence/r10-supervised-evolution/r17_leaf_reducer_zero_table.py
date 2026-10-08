"""R17 LeafView/固定归约器：226 窗零桌覆盖、行为与性能探针。"""

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

import asyncio
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys
import time


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import r17_public_successor_pilot as raw  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.kernel.config import RuleConfig  # noqa: E402
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2  # noqa: E402
from hangma_bot.policy.interface import DecisionBudget  # noqa: E402
from hangma_bot.policy.public_successor_leaf_executor import (  # noqa: E402
    LeafProgramExecutor,
)
from hangma_bot.policy.public_successor_search import (  # noqa: E402
    order_discard_keys_by_fronts,
    reduce_public_successors,
)


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r17-leaf-reducer-zero-table-02-20260921')

LEAF_SOURCE = '''
def score_actions(view):
    root = view["root"]
    next_leaf = view["next"]
    draw = view["draw"]
    score = 0.35 * (root["shanten_after"] - next_leaf["shanten_after"])
    score -= 0.15 * next_leaf["shanten_after"]
    score += 0.015 * next_leaf["support_remaining"]
    score += 0.005 * next_leaf["useful_tile_count"]
    if next_leaf["replacement_draw_unknown"]:
        score -= 0.10
    return max(-1.0, min(1.0, score))
'''


def leaf_seed(view) -> float:
    """基础设施行为探针，不是效果候选或待发布算法。"""

    score = (
        0.35 * (view.root.shanten_after - view.shanten_after)
        - 0.15 * view.shanten_after
        + 0.015 * view.support_remaining
        + 0.005 * view.useful_tile_count
        - (0.10 if view.replacement_draw_unknown else 0.0)
    )
    return max(-1.0, min(1.0, score))


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1)]


def _latency(values: list[float]) -> dict:
    return {
        "mean_ms": sum(values) / len(values),
        "p50_ms": _percentile(values, 0.50),
        "p95_ms": _percentile(values, 0.95),
        "p99_ms": _percentile(values, 0.99),
        "max_ms": max(values),
    }


async def main() -> None:
    if OUT.exists():
        raise SystemExit("零桌证据目录已存在；拒绝覆盖")
    OUT.mkdir(parents=True)
    windows = raw.r16.load_windows()
    rules_cache = {}
    policy = ComparableHeuristicPolicyV2(monotonic=lambda: 0.0)
    executor = LeafProgramExecutor(LEAF_SOURCE, name="r17_zero_table_probe")
    budget = DecisionBudget(10.0, 20.0, 30.0)
    rows = []
    counts = Counter()
    changed_seats = set()
    changed_sources = set()
    latencies = []
    max_leaf_evaluations = 0
    max_candidate_operations = 0
    failures = []

    for window_id, request, origins in windows:
        version = request.rules.ruleset_version
        rules = rules_cache.setdefault(
            version, HangmaRules(RuleConfig(version, 1, False))
        )
        successors = rules.analyze_public_self_draw_successors(request.observation)
        baseline = await policy.choose(request, budget)
        baseline_discards = tuple(
            item.action_key
            for item in baseline.candidates
            if item.action_key.startswith("discard:")
        )
        scorer = executor.window_scorer()
        started = time.perf_counter()
        reduced = reduce_public_successors(request, successors, scorer)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        repeated = reduce_public_successors(
            request, successors, executor.window_scorer()
        )
        if repeated != reduced:
            failures.append({"window_id": window_id, "kind": "nondeterministic"})
        ordered = order_discard_keys_by_fronts(reduced, baseline_discards)
        changed = ordered != baseline_discards
        phase = request.observation.phase
        if phase == "draw":
            counts["draw_windows"] += 1
            latencies.append(elapsed_ms)
            if reduced.complete:
                counts["complete_reductions"] += 1
                used = sum(item.leaf_evaluations for item in reduced.roots)
                max_leaf_evaluations = max(max_leaf_evaluations, used)
                max_candidate_operations = max(
                    max_candidate_operations, scorer.operation_count
                )
            else:
                counts["failed_reductions"] += 1
                failures.append({
                    "window_id": window_id,
                    "kind": "draw_reduction_failed",
                    "reason": reduced.reason,
                })
            if changed:
                counts["changed_draw_windows"] += 1
                changed_seats.add(request.observation.seat)
                changed_sources.update(origins)
        else:
            counts["response_windows"] += 1
            if reduced.complete:
                failures.append({
                    "window_id": window_id,
                    "kind": "response_reduction_should_fallback",
                })
            else:
                counts["response_fallbacks"] += 1
        rows.append({
            "window_id": window_id,
            "origins": origins,
            "seat": request.observation.seat,
            "phase": phase,
            "complete": reduced.complete,
            "reason": reduced.reason,
            "baseline_discard_keys": baseline_discards,
            "reduced_discard_keys": ordered,
            "changed": changed,
            "leaf_evaluations": (
                0 if not reduced.complete
                else sum(item.leaf_evaluations for item in reduced.roots)
            ),
            "candidate_operations": scorer.operation_count,
            "elapsed_ms": elapsed_ms,
        })

    behavior_pass = len(changed_seats) >= 2 and len(changed_sources) >= 2
    coverage_pass = (
        counts["complete_reductions"] == counts["draw_windows"]
        and counts["response_fallbacks"] == counts["response_windows"]
        and not failures
    )
    result = {
        "schema": "r17-leaf-reducer-zero-table-result/1",
        "status": (
            "PASS_R17_LEAF_REDUCER_ZERO_TABLE"
            if coverage_pass and behavior_pass
            else "FAIL_R17_LEAF_REDUCER_ZERO_TABLE"
        ),
        "windows": len(windows),
        "counts": dict(sorted(counts.items())),
        "coverage_pass": coverage_pass,
        "behavior_pass": behavior_pass,
        "changed_seats": sorted(changed_seats),
        "changed_source_count": len(changed_sources),
        "changed_sources": sorted(changed_sources),
        "max_leaf_evaluations": max_leaf_evaluations,
        "max_candidate_operations": max_candidate_operations,
        "fixed_limit": 4096,
        "candidate_operation_limit": executor.max_operations_per_window,
        "reducer_latency": _latency(latencies),
        "failures": failures,
        "strength_claim": False,
        "seed_scope": "基础设施行为探针；不是效果候选或待发布算法",
    }
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (_project_file(_PROJECT_ROOT, OUT / "per-window.json")).write_text(
        json.dumps(
            {"schema": "r17-leaf-reducer-zero-table-windows/1", "rows": rows},
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    runner = Path(__file__)
    (_project_file(_PROJECT_ROOT, OUT / "manifest.json")).write_text(
        json.dumps(
            {
                "schema": "r17-leaf-reducer-zero-table-manifest/1",
                "runner": str(runner),
                "runner_sha256": hashlib.sha256(runner.read_bytes()).hexdigest(),
                "outputs": ["result.json", "per-window.json", "manifest.json"],
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
