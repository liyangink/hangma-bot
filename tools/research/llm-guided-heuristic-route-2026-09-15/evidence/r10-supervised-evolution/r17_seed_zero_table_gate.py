"""R17 单叶种子的静态、全窗覆盖、确定性与行为门。

本脚本不运行效果桌。候选只有通过本门，才可以消耗新来源完整阶段样本。
输出目录不可覆盖；候选身份绑定源码、冻结合同和第一方语义闭包。
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

import argparse
import asyncio
from collections import Counter
from dataclasses import replace
import hashlib
import importlib.util
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
from hangma_bot.hangma.interface import (  # noqa: E402
    PublicSuccessorAnalysis,
    PublicSuccessorCoverage,
    RuleIssue,
)
from hangma_bot.kernel.config import RuleConfig  # noqa: E402
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2  # noqa: E402
from hangma_bot.policy.interface import DecisionBudget  # noqa: E402
from hangma_bot.policy.public_successor_leaf_executor import (  # noqa: E402
    LEAF_FIRST_PARTY_DIGEST_MODULES,
    LeafProgramExecutor,
    compute_leaf_candidate_identity,
    compute_leaf_deps_digest,
)
from hangma_bot.policy.public_successor_search import (  # noqa: E402
    MAX_LEAF_EVALUATIONS,
    order_discard_keys_by_fronts,
    reduce_public_successors,
)


CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/r17-public-successor-leaf-v1.json')
SOURCE_BYTE_LIMIT = 65_536


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1)]


def _latency(values: list[float]) -> dict:
    if not values:
        return {}
    return {
        "mean_ms": sum(values) / len(values),
        "p50_ms": _percentile(values, 0.50),
        "p95_ms": _percentile(values, 0.95),
        "p99_ms": _percentile(values, 0.99),
        "max_ms": max(values),
    }


def _dependency_contents() -> dict[str, str]:
    contents = {}
    for module_name in LEAF_FIRST_PARTY_DIGEST_MODULES:
        spec = importlib.util.find_spec(module_name)
        if spec is None or spec.origin is None:
            raise RuntimeError("找不到第一方依赖模块: " + module_name)
        path = Path(spec.origin)
        if not path.is_file() or path.suffix != ".py":
            raise RuntimeError("第一方依赖不是 Python 源文件: " + module_name)
        contents[module_name] = path.read_text(encoding="utf-8")
    return contents


def _reverse_graph(analysis: PublicSuccessorAnalysis) -> PublicSuccessorAnalysis:
    roots = []
    for root in reversed(analysis.roots):
        edges = []
        for edge in reversed(root.edges):
            edges.append(
                replace(
                    edge,
                    restricted=replace(
                        edge.restricted,
                        gang_leaves=tuple(reversed(edge.restricted.gang_leaves)),
                        discard_frontier=tuple(
                            reversed(edge.restricted.discard_frontier)
                        ),
                    ),
                    unrestricted=replace(
                        edge.unrestricted,
                        gang_leaves=tuple(reversed(edge.unrestricted.gang_leaves)),
                        discard_frontier=tuple(
                            reversed(edge.unrestricted.discard_frontier)
                        ),
                    ),
                )
            )
        roots.append(replace(root, edges=tuple(edges)))
    return replace(analysis, roots=tuple(roots))


def _erased_graph(analysis: PublicSuccessorAnalysis) -> PublicSuccessorAnalysis:
    return PublicSuccessorAnalysis(
        phase=analysis.phase,
        coverage=PublicSuccessorCoverage.UNAVAILABLE,
        roots=(),
        ruleset_version=analysis.ruleset_version,
        issues=(RuleIssue("public_successor", "测试抹去后继树"),),
    )


def _behavior_row(reduction, ordered_keys) -> dict:
    return {
        "ordered_keys": ordered_keys,
        "roots": [
            {
                "action_key": item.action_key,
                "lower": item.lower_support_score,
                "upper": item.upper_support_score,
                "hu_net_support": item.conditional_hu_net_support,
                "hu_capacity": item.conditional_hu_capacity,
                "capacity_total": item.capacity_total,
                "leaf_evaluations": item.leaf_evaluations,
            }
            for item in reduction.roots
        ],
    }


async def _run(candidate_dir: Path, output_dir: Path, candidate_label: str) -> dict:
    if output_dir.exists():
        raise SystemExit("证据目录已存在；拒绝覆盖: " + str(output_dir))
    candidate_file = candidate_dir / "candidate.py"
    source_bytes = candidate_file.read_bytes()
    if len(source_bytes) > SOURCE_BYTE_LIMIT:
        raise SystemExit("候选源码超过 65536 字节")
    source = source_bytes.decode("utf-8")
    contract_bytes = CONTRACT.read_bytes()
    contract = json.loads(contract_bytes)
    if (
        contract.get("limits", {}).get("max_leaf_evaluations_per_window")
        != MAX_LEAF_EVALUATIONS
    ):
        raise SystemExit("叶合同与生产归约的整窗叶数上限漂移")
    contract_sha256 = _sha256_bytes(contract_bytes)
    dependency_contents = _dependency_contents()
    deps_digest = compute_leaf_deps_digest(dependency_contents)
    identity = compute_leaf_candidate_identity(
        source, contract_sha256, deps_digest, {}
    )
    executor = LeafProgramExecutor(source, name=candidate_label)

    output_dir.mkdir(parents=True)
    windows = raw.r16.load_windows()
    rules_cache = {}
    baseline_policy = ComparableHeuristicPolicyV2(monotonic=lambda: 0.0)
    budget = DecisionBudget(10.0, 20.0, 30.0)
    counts = Counter()
    failures = []
    rows = []
    behavior_rows = []
    changed_seats = set()
    changed_sources = set()
    non_tie_changed_seats = set()
    non_tie_changed_sources = set()
    reducer_latencies = []
    graph_latencies = []
    max_leaf_evaluations = 0
    max_candidate_operations = 0
    deletion_guard_checked = False
    erased_fallback_checked = False

    for window_id, request, origins in windows:
        version = request.rules.ruleset_version
        rules = rules_cache.setdefault(
            version, HangmaRules(RuleConfig(version, 1, False))
        )
        graph_started = time.perf_counter()
        successors = rules.analyze_public_self_draw_successors(request.observation)
        graph_elapsed_ms = (time.perf_counter() - graph_started) * 1000.0
        baseline = await baseline_policy.choose(request, budget)
        baseline_keys = tuple(
            item.action_key
            for item in baseline.candidates
            if item.action_key.startswith("discard:")
        )

        recorded_scores = []
        scorer = executor.window_scorer()

        def recording_scorer(view):
            score = scorer(view)
            recorded_scores.append(score)
            return score

        started = time.perf_counter()
        reduction = reduce_public_successors(
            request, successors, recording_scorer
        )
        reducer_elapsed_ms = (time.perf_counter() - started) * 1000.0
        ordered_keys = order_discard_keys_by_fronts(reduction, baseline_keys)
        repeated = reduce_public_successors(
            request, successors, executor.window_scorer()
        )
        reversed_reduction = reduce_public_successors(
            request, _reverse_graph(successors), executor.window_scorer()
        )
        changed = ordered_keys != baseline_keys
        distinct_leaf_scores = len(set(recorded_scores))
        non_tie_changed = changed and distinct_leaf_scores >= 2

        if repeated != reduction:
            failures.append({"window_id": window_id, "kind": "nondeterministic"})
        if reversed_reduction != reduction:
            failures.append({"window_id": window_id, "kind": "reorder_variant"})

        phase = request.observation.phase
        if phase == "draw":
            counts["draw_windows"] += 1
            graph_latencies.append(graph_elapsed_ms)
            reducer_latencies.append(reducer_elapsed_ms)
            if reduction.complete:
                counts["complete_draw_reductions"] += 1
                max_leaf_evaluations = max(
                    max_leaf_evaluations,
                    sum(item.leaf_evaluations for item in reduction.roots),
                )
                max_candidate_operations = max(
                    max_candidate_operations, scorer.operation_count
                )
                behavior_rows.append(
                    {"window_id": window_id, **_behavior_row(reduction, ordered_keys)}
                )
            else:
                failures.append(
                    {
                        "window_id": window_id,
                        "kind": "draw_reduction_failed",
                        "reason": reduction.reason,
                    }
                )
            if changed:
                counts["changed_draw_windows"] += 1
                changed_seats.add(request.observation.seat)
                changed_sources.update(origins)
            if non_tie_changed:
                counts["non_tie_changed_draw_windows"] += 1
                non_tie_changed_seats.add(request.observation.seat)
                non_tie_changed_sources.update(origins)

            if not deletion_guard_checked and successors.roots:
                deletion_guard_checked = True
                root = successors.roots[0]
                try:
                    replace(root, edges=root.edges[:-1])
                except ValueError:
                    counts["positive_edge_deletion_rejected"] += 1
                else:
                    failures.append(
                        {"window_id": window_id, "kind": "edge_deletion_accepted"}
                    )

            if not erased_fallback_checked:
                erased_fallback_checked = True
                erased = reduce_public_successors(
                    request, _erased_graph(successors), executor.window_scorer()
                )
                erased_order = order_discard_keys_by_fronts(erased, baseline_keys)
                if erased.complete or erased_order != baseline_keys:
                    failures.append(
                        {"window_id": window_id, "kind": "erased_graph_not_exact_fallback"}
                    )
                else:
                    counts["erased_graph_exact_fallback"] += 1
        else:
            counts["response_windows"] += 1
            if reduction.complete or ordered_keys != baseline_keys:
                failures.append(
                    {"window_id": window_id, "kind": "response_not_exact_fallback"}
                )
            else:
                counts["response_exact_fallbacks"] += 1

        rows.append(
            {
                "window_id": window_id,
                "origins": origins,
                "seat": request.observation.seat,
                "phase": phase,
                "complete": reduction.complete,
                "reason": reduction.reason,
                "baseline_discard_keys": baseline_keys,
                "candidate_discard_keys": ordered_keys,
                "changed": changed,
                "distinct_leaf_scores": distinct_leaf_scores,
                "non_tie_changed": non_tie_changed,
                "leaf_evaluations": (
                    0
                    if not reduction.complete
                    else sum(item.leaf_evaluations for item in reduction.roots)
                ),
                "candidate_operations": scorer.operation_count,
                "graph_elapsed_ms": graph_elapsed_ms,
                "reducer_elapsed_ms": reducer_elapsed_ms,
            }
        )

    coverage_pass = (
        counts["complete_draw_reductions"] == counts["draw_windows"]
        and counts["response_exact_fallbacks"] == counts["response_windows"]
        and counts["positive_edge_deletion_rejected"] == 1
        and counts["erased_graph_exact_fallback"] == 1
    )
    behavior_pass = (
        len(non_tie_changed_seats) >= 2
        and len(non_tie_changed_sources) >= 2
    )
    pass_gate = coverage_pass and behavior_pass and not failures
    behavior_digest = _sha256_bytes(
        json.dumps(
            behavior_rows,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    result = {
        "schema": "r17-seed-zero-table-gate-result/1",
        "status": "PASS_R17_SEED_ZERO_TABLE" if pass_gate else "FAIL_R17_SEED_ZERO_TABLE",
        "candidate_label": candidate_label,
        "candidate_identity": identity,
        "candidate_source_sha256": _sha256_bytes(source_bytes),
        "candidate_source_bytes": len(source_bytes),
        "contract_sha256": contract_sha256,
        "deps_digest": deps_digest,
        "behavior_digest": behavior_digest,
        "windows": len(windows),
        "counts": dict(sorted(counts.items())),
        "coverage_pass": coverage_pass,
        "behavior_pass": behavior_pass,
        "non_tie_changed_seats": sorted(non_tie_changed_seats),
        "non_tie_changed_source_count": len(non_tie_changed_sources),
        "non_tie_changed_sources": sorted(non_tie_changed_sources),
        "changed_seats": sorted(changed_seats),
        "changed_source_count": len(changed_sources),
        "max_leaf_evaluations": max_leaf_evaluations,
        "max_candidate_operations": max_candidate_operations,
        "fixed_leaf_limit": MAX_LEAF_EVALUATIONS,
        "fixed_operation_limit": executor.max_operations_per_window,
        "graph_latency": _latency(graph_latencies),
        "reducer_latency": _latency(reducer_latencies),
        "failures": failures,
        "strength_claim": False,
        "next_gate": "new-source complete-stage development" if pass_gate else None,
    }
    (output_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "per-window.json").write_text(
        json.dumps(
            {"schema": "r17-seed-zero-table-windows/1", "rows": rows},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    runner = Path(__file__)
    author_files = {
        path.name: _sha256_bytes(path.read_bytes())
        for path in sorted(candidate_dir.iterdir())
        if path.is_file()
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema": "r17-seed-zero-table-gate-manifest/1",
                "runner": str(runner.relative_to(ROOT)),
                "runner_sha256": _sha256_bytes(runner.read_bytes()),
                "candidate_dir": str(candidate_dir.relative_to(ROOT)),
                "candidate_files": author_files,
                "outputs": ["result.json", "per-window.json", "manifest.json"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--candidate-label", required=True)
    args = parser.parse_args()
    candidate_dir = args.candidate_dir.resolve()
    output_dir = args.output_dir.resolve()
    if ROOT not in candidate_dir.parents or ROOT not in output_dir.parents:
        raise SystemExit("候选与输出目录必须位于仓库内")
    result = asyncio.run(
        _run(candidate_dir, output_dir, str(args.candidate_label))
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["status"].startswith("PASS_"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
