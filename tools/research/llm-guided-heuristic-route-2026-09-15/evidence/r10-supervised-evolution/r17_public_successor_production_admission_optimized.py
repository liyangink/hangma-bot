"""R17 P0 生产公开后继接口：226 窗语义、性能与内存准入复核。

性能段固定六遍、保持 Python 循环 GC 开启，单窗计时包含
``HangmaRules.analyze`` 与公开后继投影。raw 大图只在临时文件中逐边写入
canonical JSON 片段以复算旧摘要，运行结束删除；Git 证据只保存摘要、
每窗统计和有限样本。tracemalloc 与对象增长另跑，不混入性能数据。
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
import gc
import hashlib
import json
import math
from pathlib import Path
import resource
import sys
import tempfile
import time
import tracemalloc
from typing import Any


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import r17_public_successor_pilot as raw  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.hangma.interface import PublicSuccessorCoverage  # noqa: E402
from hangma_bot.kernel.actions import Discard  # noqa: E402
from hangma_bot.kernel.config import RuleConfig  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r17-public-successor-production-admission-08-20260921')
RAW_RESULT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r17-public-successor-pilot-01-20260921/result.json')
EXPECTED_RAW_DIGEST = "5db94acf10972588e47ae2b05f6c3c644f039fbc7837a434ecb20f8e164b6a12"
PASSES = 6
P99_MS_MAX = 200.0
WINDOW_MS_MAX = 500.0
SAMPLE_LIMIT = 12


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


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


def _leaf_mapping(leaf: Any) -> dict[str, Any]:
    return {
        "action_key": leaf.action_key,
        "fact_kind": "hand_progress",
        "shanten": leaf.shanten_after,
        "standard_shanten": leaf.standard_shanten_after,
        "seven_pairs_shanten": leaf.seven_pairs_shanten_after,
        "support_remaining": leaf.support_remaining,
        "useful_tile_count": leaf.useful_tile_count,
        "replacement_draw_unknown": leaf.replacement_draw_unknown,
    }


def _packed_leaf_problem(leaf: Any) -> str | None:
    """复核紧凑有效牌身份/容量可逆且总容量一致。"""

    support = 0
    for index in range(34):
        remaining = leaf.useful_remaining(index)
        marked = bool(leaf.useful_mask & (1 << index))
        if remaining > 4:
            return "第 {0} 维容量越过四张上限: {1}".format(index, remaining)
        if not marked and remaining:
            return "第 {0} 维未标有效却携带容量: {1}".format(index, remaining)
        support += remaining
    if support != leaf.support_remaining:
        return "打包容量和 {0} != support_remaining {1}".format(
            support, leaf.support_remaining
        )
    return None


def _regime_mapping(envelope: Any) -> dict[str, Any]:
    return {
        "hu": envelope.hu_available,
        "gang": [_leaf_mapping(item) for item in envelope.gang_leaves],
        "discard_pareto": [
            _leaf_mapping(item) for item in envelope.discard_frontier
        ],
    }


def _edge_mapping(window_id: str, root: Any, edge: Any) -> dict[str, Any]:
    return {
        "window_id": window_id,
        "root_action_key": root.action_key,
        "root_shanten": root.shanten_after,
        "draw_tile": edge.draw_tile.code,
        "remaining_capacity": edge.draw_tile.remaining_estimate,
        "edge_class": "useful" if edge.is_currently_useful else "non_useful",
        "regimes": {
            "unrestricted": _regime_mapping(edge.unrestricted),
            "drawn_only": _regime_mapping(edge.restricted),
        },
    }


def _sample(samples: dict[str, list[dict[str, Any]]], edge: dict[str, Any]) -> None:
    edge_class = edge["edge_class"]
    if len(samples[edge_class]) < SAMPLE_LIMIT:
        samples[edge_class].append(edge)
    regimes = edge["regimes"].values()
    if any(item["hu"] for item in regimes) and len(samples["hu"]) < SAMPLE_LIMIT:
        samples["hu"].append(edge)
    regimes = edge["regimes"].values()
    if any(item["gang"] for item in regimes) and len(samples["gang"]) < SAMPLE_LIMIT:
        samples["gang"].append(edge)


def _semantic_digest(
    spool_path: Path,
    counts: dict[str, int],
    response_ids: list[str],
    semantic_windows: list[dict[str, Any]],
) -> str:
    digest = hashlib.sha256()
    digest.update(b'{"counts":')
    digest.update(_canonical_bytes(counts))
    digest.update(b',"edges":[')
    with spool_path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    digest.update(b'],"response_ids":')
    digest.update(_canonical_bytes(response_ids))
    digest.update(b',"windows":')
    digest.update(_canonical_bytes(semantic_windows))
    digest.update(b"}")
    return digest.hexdigest()


def _rules_for(request: Any, cache: dict[str, HangmaRules]) -> HangmaRules:
    version = request.rules.ruleset_version
    rules = cache.get(version)
    if rules is None:
        rules = HangmaRules(RuleConfig(version, 1, False))
        cache[version] = rules
    return rules


def evaluate_once(
    windows: list[tuple[str, Any, list[str]]], *, keep_samples: bool
) -> dict[str, Any]:
    """默认 GC 下评测一遍；只将旧摘要边写入临时文件。"""

    if not gc.isenabled():
        raise RuntimeError("生产性能复核要求 Python 循环 GC 保持开启")
    rules_cache: dict[str, HangmaRules] = {}
    global_counts: Counter[str] = Counter()
    response_ids: list[str] = []
    window_rows: list[dict[str, Any]] = []
    semantic_windows: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    route_issues: list[dict[str, Any]] = []
    samples = {"useful": [], "non_useful": [], "hu": [], "gang": []}
    maxima: Counter[str] = Counter()
    spool = tempfile.NamedTemporaryFile(prefix="r17-production-", suffix=".json", delete=False)
    spool_path = Path(spool.name)
    first_edge = True
    try:
        for window_id, request, origins in windows:
            local: Counter[str] = Counter()
            rules = _rules_for(request, rules_cache)
            started = time.perf_counter()
            result = rules.analyze_public_self_draw_successors(request.observation)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            phase = request.observation.phase

            if phase != "draw":
                global_counts["response_fallback_windows"] += 1
                local["response_fallback_windows"] += 1
                response_ids.append(window_id)
                if result.coverage is not PublicSuccessorCoverage.UNAVAILABLE:
                    issues.append({
                        "window_id": window_id,
                        "kind": "response_not_unavailable",
                    })
            else:
                global_counts["draw_windows"] += 1
                local["draw_windows"] += 1
                if result.coverage is not PublicSuccessorCoverage.COMPLETE:
                    issues.append({
                        "window_id": window_id,
                        "kind": "draw_projection_incomplete",
                        "coverage": result.coverage.value,
                        "issues": [item.reason for item in result.issues],
                    })

                recorded_candidates = {
                    candidate.action_key: candidate
                    for candidate in request.rules.legal_candidates
                    if isinstance(candidate.action, Discard)
                }
                maxima["roots"] = max(maxima["roots"], len(result.roots))
                maxima["edges"] = max(
                    maxima["edges"], sum(len(root.edges) for root in result.roots)
                )
                maxima["frontier_leaf_objects"] = max(
                    maxima["frontier_leaf_objects"],
                    sum(
                        len(edge.restricted.discard_frontier)
                        + len(edge.unrestricted.discard_frontier)
                        + len(edge.restricted.gang_leaves)
                        + len(edge.unrestricted.gang_leaves)
                        for root in result.roots
                        for edge in root.edges
                    ),
                )
                for root in result.roots:
                    global_counts["discard_roots"] += 1
                    local["discard_roots"] += 1
                    if root.coverage is not PublicSuccessorCoverage.COMPLETE:
                        global_counts["discard_roots_failed"] += 1
                        local["discard_roots_failed"] += 1
                        continue
                    global_counts["discard_roots_covered"] += 1
                    local["discard_roots_covered"] += 1
                    recorded = recorded_candidates.get(root.action_key)
                    if recorded is None:
                        issues.append({
                            "window_id": window_id,
                            "kind": "root_not_in_recorded_rule_analysis",
                            "action_key": root.action_key,
                        })
                    else:
                        try:
                            context = raw._build_context(request.observation)
                            raw_root = raw._discard_root(
                                recorded,
                                context,
                                len(request.observation.melds[request.observation.seat]),
                            )
                            capacities = {
                                edge.draw_tile.code: edge.draw_tile.remaining_estimate
                                for edge in root.edges
                            }
                            route_groups, route_edges, problems = raw._route_check(
                                window_id, recorded, raw_root, capacities
                            )
                            global_counts["value_route_groups"] += route_groups
                            global_counts["value_route_edges"] += route_edges
                            local["value_route_groups"] += route_groups
                            local["value_route_edges"] += route_edges
                            route_issues.extend(problems)
                        except Exception as exc:
                            issues.append({
                                "window_id": window_id,
                                "kind": "route_adapter_failed",
                                "action_key": root.action_key,
                                "error": type(exc).__name__ + ": " + str(exc),
                            })

                    for edge in root.edges:
                        global_counts["all_capacity_edges"] += 1
                        local["all_capacity_edges"] += 1
                        edge_class = (
                            "useful_edges" if edge.is_currently_useful else "non_useful_edges"
                        )
                        global_counts[edge_class] += 1
                        local[edge_class] += 1
                        for prefix, envelope in (
                            ("unrestricted", edge.unrestricted),
                            ("drawn_only", edge.restricted),
                        ):
                            global_counts[prefix + "_hu"] += int(envelope.hu_available)
                            global_counts[prefix + "_gang"] += len(envelope.gang_leaves)
                            global_counts[prefix + "_discard"] += envelope.legal_discard_count
                            global_counts[prefix + "_discard_pareto"] += len(
                                envelope.discard_frontier
                            )
                            local[prefix + "_hu"] += int(envelope.hu_available)
                            local[prefix + "_gang"] += len(envelope.gang_leaves)
                            local[prefix + "_discard"] += envelope.legal_discard_count
                            local[prefix + "_discard_pareto"] += len(
                                envelope.discard_frontier
                            )
                            for leaf in (
                                envelope.gang_leaves
                                + envelope.discard_frontier
                            ):
                                problem = _packed_leaf_problem(leaf)
                                if problem is not None:
                                    issues.append({
                                        "window_id": window_id,
                                        "kind": "packed_leaf_invalid",
                                        "action_key": leaf.action_key,
                                        "problem": problem,
                                    })
                        mapped = _edge_mapping(window_id, root, edge)
                        if first_edge:
                            first_edge = False
                        else:
                            spool.write(b",")
                        spool.write(_canonical_bytes(mapped))
                        if keep_samples:
                            _sample(samples, mapped)

            semantic = {
                "window_id": window_id,
                "origins": origins,
                "phase": phase,
                "counts": dict(sorted(local.items())),
            }
            semantic_windows.append(semantic)
            window_rows.append({**semantic, "elapsed_ms": elapsed_ms})
        spool.close()
        counts = dict(sorted(global_counts.items()))
        digest = _semantic_digest(spool_path, counts, response_ids, semantic_windows)
        return {
            "semantic_digest": digest,
            "counts": counts,
            "response_ids": response_ids,
            "window_rows": window_rows,
            "issues": issues,
            "route_issues": route_issues,
            "samples": samples,
            "maxima": dict(sorted(maxima.items())),
        }
    finally:
        if not spool.closed:
            spool.close()
        spool_path.unlink(missing_ok=True)


def memory_probe(windows: list[tuple[str, Any, list[str]]]) -> dict[str, Any]:
    """独立全窗对象/内存检查；数值不得进入性能门。"""

    rules_cache: dict[str, HangmaRules] = {}
    gc.collect()
    objects_before = len(gc.get_objects())
    tracemalloc.start()
    try:
        baseline_current, _ = tracemalloc.get_traced_memory()
        for _, request, _ in windows:
            result = _rules_for(request, rules_cache).analyze_public_self_draw_successors(
                request.observation
            )
            del result
        gc.collect()
        final_current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    objects_after = len(gc.get_objects())
    return {
        "scope": "独立于性能门的226窗全遍；每窗结果立即删除后强制collect",
        "tracemalloc_current_before_bytes": baseline_current,
        "tracemalloc_current_after_bytes": final_current,
        "tracemalloc_retained_delta_bytes": final_current - baseline_current,
        "tracemalloc_peak_bytes": peak,
        "gc_tracked_objects_before": objects_before,
        "gc_tracked_objects_after": objects_after,
        "gc_tracked_objects_delta": objects_after - objects_before,
        "process_ru_maxrss_platform_units": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    if OUT.exists():
        raise SystemExit("生产准入证据目录已存在；拒绝覆盖")
    OUT.mkdir(parents=True)
    raw_result = json.loads(RAW_RESULT.read_text(encoding="utf-8"))
    if raw_result["semantic_digest"] != EXPECTED_RAW_DIGEST:
        raise RuntimeError("冻结 raw digest 与脚本常量不一致")
    windows = raw.r16.load_windows()
    passes = []
    for index in range(PASSES):
        gc.collect()
        evaluated = evaluate_once(windows, keep_samples=index == 0)
        evaluated["pass_index"] = index + 1
        evaluated["latency"] = _latency(evaluated["window_rows"])
        passes.append(evaluated)
    memory = memory_probe(windows)

    digests = [item["semantic_digest"] for item in passes]
    deterministic = len(set(digests)) == 1
    raw_equivalent = all(item == EXPECTED_RAW_DIGEST for item in digests)
    no_issues = all(
        not item["issues"] and not item["route_issues"] for item in passes
    )
    performance_pass = all(
        item["latency"]["p99_ms"] <= P99_MS_MAX
        and item["latency"]["max_ms"] <= WINDOW_MS_MAX
        for item in passes
    )
    memory_pass = (
        memory["tracemalloc_retained_delta_bytes"] < 1024 * 1024
        and memory["gc_tracked_objects_delta"] < 1000
    )
    admitted = (
        deterministic
        and raw_equivalent
        and no_issues
        and performance_pass
        and memory_pass
    )
    result = {
        "schema": "r17-public-successor-production-admission-result/1",
        "status": (
            "PASS_R17_P0_PRODUCTION_ADMISSION"
            if admitted
            else "FAIL_R17_P0_PRODUCTION_ADMISSION"
        ),
        "windows": len(windows),
        "performance_protocol": {
            "passes": PASSES,
            "gc_enabled": True,
            "timed_scope": "HangmaRules.analyze + analyze_public_self_draw_successors；包含同源合法动作分析",
            "tracemalloc_mixed_into_timing": False,
        },
        "semantic_equivalence": {
            "passed": raw_equivalent,
            "raw_digest": EXPECTED_RAW_DIGEST,
            "pass_digests": digests,
            "deterministic": deterministic,
        },
        "coverage": {
            "passed": no_issues,
            "counts": passes[0]["counts"],
            "issue_count_per_pass": [len(item["issues"]) for item in passes],
            "route_issue_count_per_pass": [len(item["route_issues"]) for item in passes],
        },
        "bounded_return_objects_per_window_max": passes[0]["maxima"],
        "latency_passes": [item["latency"] for item in passes],
        "gate": {
            "passed": performance_pass,
            "p99_ms_max": P99_MS_MAX,
            "window_max_ms": WINDOW_MS_MAX,
        },
        "memory": {"passed": memory_pass, **memory},
        "rules": {
            "response": "UNAVAILABLE，策略回退稳定V2",
            "you_cai_bi_kao": "未来爆头资格未知时整项UNAVAILABLE",
            "gang": "当前wall=21时下一普通摸后不可能>20；仅当前>21保留未来wall>20条件叶",
            "capacity": "枚举全34牌码中公开容量>0的边，包含非useful边；容量不是概率",
        },
        "selection_eligible": admitted,
        "strength_claim": False,
    }
    _write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    _write_json(
        _project_file(_PROJECT_ROOT, OUT / "per-window.json"),
        {
            "schema": "r17-public-successor-production-per-window/1",
            "passes": [
                {
                    "pass_index": item["pass_index"],
                    "rows": item["window_rows"],
                }
                for item in passes
            ],
        },
    )
    _write_json(
        _project_file(_PROJECT_ROOT, OUT / "frontier-sample.json"),
        {
            "schema": "r17-public-successor-production-frontier-sample/1",
            "per_bucket_limit": SAMPLE_LIMIT,
            "buckets": passes[0]["samples"],
            "scope": "有限审计样本；完整逐边内容仅临时流式用于旧摘要对账，未落Git证据",
        },
    )
    _write_json(
        _project_file(_PROJECT_ROOT, OUT / "issues.json"),
        {
            "schema": "r17-public-successor-production-issues/1",
            "passes": [
                {
                    "pass_index": item["pass_index"],
                    "projection": item["issues"],
                    "route": item["route_issues"],
                }
                for item in passes
            ],
        },
    )
    (_project_file(_PROJECT_ROOT, OUT / "VERDICT.md")).write_text(
        "# R17 P0 生产接口准入裁决\n\n"
        + (
            "**PASS**：语义、覆盖、默认 GC 性能和独立内存门均通过；"
            "只准入后续候选生成研究，不构成强度或发布结论。\n"
            if admitted
            else "**FAIL**：至少一项冻结门未通过；不得进入候选生成。\n"
        ),
        encoding="utf-8",
    )
    runner = Path(__file__)
    files = ["result.json", "per-window.json", "frontier-sample.json", "issues.json"]
    _write_json(
        _project_file(_PROJECT_ROOT, OUT / "manifest.json"),
        {
            "schema": "r17-public-successor-production-admission-manifest/1",
            "runner": {
                "path": str(runner),
                "sha256": hashlib.sha256(runner.read_bytes()).hexdigest(),
            },
            "raw_result": {
                "path": str(RAW_RESULT),
                "sha256": hashlib.sha256(RAW_RESULT.read_bytes()).hexdigest(),
            },
            "panels": [
                {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                for path in raw.r16.PANELS
            ],
            "temporary_full_edge_spool_deleted": True,
            "outputs": files + ["manifest.json", "VERDICT.md"],
        },
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
