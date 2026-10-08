"""R17 P0：34 摸牌批处理与惰性前沿的等价性能探针。

本探针不改生产代码，不删除任何公开容量边或合法叶。它把相同最终暗牌的
``HandSummary`` 从“最终公开计数”中分离并跨根共享；弃牌叶只物化冻结
reducer 需要的六个标量，不构造完整 ``CandidateFacts``。公开支持随后按
同一 ``candidate_facts._remaining`` 公式批量计算。胡与杠仍单列，杠事实
继续交给 ``candidate_facts``。完整逐边结果只计算 canonical digest。
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
from dataclasses import dataclass
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
from hangma_bot.hangma.candidate_facts import FactsAnalysisError, _remaining, _remove_codes  # noqa: E402
from hangma_bot.hangma.engine import _build_context, _public_counts  # noqa: E402
from hangma_bot.hangma.hand_analysis import _need_std, _validate_melds  # noqa: E402
from hangma_bot.hangma.internal_types import TILE_INDEX, TILE_ORDER, counts_from_tiles  # noqa: E402
from hangma_bot.kernel.actions import Discard, Tile  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r17-public-successor-performance-03-20260921')
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


@dataclass(frozen=True)
class _SlimSummary:
    """冻结 reducer 实际消费的 HandSummary 投影；不物化证据和分型有效牌。"""

    is_win: bool
    standard_shanten: int
    chiitoi_shanten: int | None
    shanten: int
    useful_codes: tuple[str, ...]


def _fast_analyse_hand(codes: tuple[str, ...], meld_count: int) -> _SlimSummary:
    """对 reducer 读取字段等价 analyse_hand；七对进张用 O(1) 增量更新。"""

    _validate_melds(meld_count)
    mutable = [0] * 34
    for code in codes:
        mutable[TILE_INDEX[code]] += 1
    counts34 = tuple(mutable)
    counts = counts34[:33]
    whites = counts34[33]
    sets_needed = 4 - meld_count
    standard_shanten = _need_std(counts, whites, sets_needed, True) - 1
    natural_pairs = 0
    singles = 0
    for value in counts:
        natural_pairs += value // 2
        singles += value % 2
    if meld_count == 0:
        paired = whites if whites < singles else singles
        pair_total = natural_pairs + paired + (whites - paired) // 2
        chiitoi_shanten = 6 - (7 if pair_total > 7 else pair_total)
    else:
        chiitoi_shanten = None
    shanten = standard_shanten if chiitoi_shanten is None else min(
        standard_shanten, chiitoi_shanten
    )
    is_win = shanten == -1

    useful_codes: tuple[str, ...] = ()
    if not is_win:
        entries = []
        for index in range(34):
            held = counts34[index]
            if held >= 4:
                continue
            if index < 33:
                drawn_counts = counts[:index] + (held + 1,) + counts[index + 1:]
                drawn_whites = whites
                # 偶数加一增加一个单张；奇数加一把该单张并成一对。
                drawn_pairs = natural_pairs + (held % 2)
                drawn_singles = singles + (1 if held % 2 == 0 else -1)
            else:
                drawn_counts = counts
                drawn_whites = whites + 1
                drawn_pairs = natural_pairs
                drawn_singles = singles
            after_standard = _need_std(
                drawn_counts, drawn_whites, sets_needed, True
            ) - 1
            after = after_standard
            if meld_count == 0:
                drawn_paired = drawn_whites if drawn_whites < drawn_singles else drawn_singles
                drawn_total = (
                    drawn_pairs + drawn_paired + (drawn_whites - drawn_paired) // 2
                )
                after_seven = 6 - (7 if drawn_total > 7 else drawn_total)
                after = min(after, after_seven)
            if after < shanten:
                entries.append(TILE_ORDER[index])
        if whites < 4 and "白" not in entries:
            entries.append("白")
        useful_codes = tuple(entries)

    return _SlimSummary(
        is_win=is_win,
        standard_shanten=standard_shanten,
        chiitoi_shanten=chiitoi_shanten,
        shanten=shanten,
        useful_codes=useful_codes,
    )


def _pareto(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """与 raw._pareto 同序同支配式，去掉生成器/闭包开销。"""

    kept = []
    for index, row in enumerate(rows):
        dominated = False
        row_seven = row["seven_pairs_shanten"]
        for other_index, other in enumerate(rows):
            if other_index == index:
                continue
            if other["shanten"] > row["shanten"]:
                continue
            if other["standard_shanten"] > row["standard_shanten"]:
                continue
            strict = (
                other["shanten"] < row["shanten"]
                or other["standard_shanten"] < row["standard_shanten"]
            )
            if row_seven is not None:
                if other["seven_pairs_shanten"] > row_seven:
                    continue
                strict = strict or other["seven_pairs_shanten"] < row_seven
            if other["support_remaining"] < row["support_remaining"]:
                continue
            if strict or other["support_remaining"] > row["support_remaining"]:
                dominated = True
                break
        if not dominated:
            kept.append(row)
    return kept


def _summary(
    codes: tuple[str, ...], meld_count: int,
    cache: dict[tuple[Any, ...], Any], performance: Counter[str],
) -> Any:
    """暗牌数学只依赖规范牌计数与副露数，不依赖公开支持计数。"""

    key = (tuple(sorted(codes, key=TILE_INDEX.get)), meld_count)
    value = cache.get(key)
    if value is None:
        value = _fast_analyse_hand(key[0], meld_count)
        cache[key] = value
        performance["hand_summary_cache_misses"] += 1
    else:
        performance["hand_summary_cache_hits"] += 1
    return value


def _leaf_scalar(
    context: Any,
    public_after_root: tuple[Any, ...],
    meld_count: int,
    discard_code: str,
    summary_cache: dict[tuple[Any, ...], Any],
    scalar_cache: dict[tuple[Any, ...], dict[str, Any]],
    performance: Counter[str],
) -> dict[str, Any]:
    """只生产冻结 Pareto reducer 读取的标量；等价式见结果报告。"""

    full_codes = tuple(tile.code for tile in context.full_hand())
    after_codes = _remove_codes(full_codes, {discard_code: 1})
    final_public = raw._adjust_public_counts(public_after_root, {discard_code: 1})
    hand_key = tuple(sorted(after_codes, key=TILE_INDEX.get))
    scalar_key = (hand_key, final_public, meld_count)
    scalar = scalar_cache.get(scalar_key)
    if scalar is None:
        summary = _summary(after_codes, meld_count, summary_cache, performance)
        hand_counts = counts_from_tiles(tuple(Tile(code) for code in hand_key))
        support = 0
        for code in summary.useful_codes:
            remaining = final_public[TILE_INDEX[code]]
            if remaining is None:
                raise FactsAnalysisError("最终公开计数未知，无法保持原 CandidateFacts 语义")
            support += max(0, 4 - hand_counts[TILE_INDEX[code]] - remaining)
        scalar = {
            "fact_kind": "hand_progress",
            "shanten": summary.shanten,
            "standard_shanten": summary.standard_shanten,
            "seven_pairs_shanten": summary.chiitoi_shanten,
            "support_remaining": support,
            "useful_tile_count": len(summary.useful_codes),
            "replacement_draw_unknown": False,
        }
        scalar_cache[scalar_key] = scalar
        performance["leaf_scalar_cache_misses"] += 1
    else:
        performance["leaf_scalar_cache_hits"] += 1
    performance["logical_discard_leaf_requests"] += 1
    return {"action_key": "discard:" + discard_code, **scalar}


def _edge_leaf(
    root: Any,
    current: Any,
    public_after_root: tuple[Any, ...],
    drawn_code: str,
    summary_cache: dict[tuple[Any, ...], Any],
    scalar_cache: dict[tuple[Any, ...], dict[str, Any]],
    performance: Counter[str],
) -> tuple[dict[str, Any], Counter[str], list[str]]:
    """批量展开同一摸牌的两个抓打包络；不构造未来观察。"""

    contexts = {
        "unrestricted": raw._future_context(current, root, drawn_code, catch_play=False),
        "drawn_only": raw._future_context(current, root, drawn_code, catch_play=True),
    }
    drawn_codes = tuple(tile.code for tile in contexts["unrestricted"].full_hand())
    drawn_summary = _summary(drawn_codes, root.meld_count, summary_cache, performance)

    # generate_candidates 的 draw 窗口语义：YouCaiBiKao=false 时胡恰等于
    # drawn_summary.is_win；不受限弃全部暗牌值，受限只摸切。杠形仍调用
    # action_families，保留墙余量、抓打圈、明/暗/补杠规则边界。
    discard_codes = {
        "unrestricted": tuple(sorted(set(drawn_codes), key=TILE_INDEX.get)),
        "drawn_only": (drawn_code,),
    }
    gangs = {}
    issues = []
    union_gangs: dict[str, Any] = {}
    for regime, context in contexts.items():
        outcome = action_families.gang_candidates(context)
        gangs[regime] = tuple(candidate.action_key for candidate in outcome.candidates)
        union_gangs.update((candidate.action_key, candidate) for candidate in outcome.candidates)
        issues.extend(regime + ":" + issue.area + ":" + issue.reason for issue in outcome.issues)
    attached, fact_issues = candidate_facts.attach_facts(
        contexts["unrestricted"], public_after_root, root.meld_count,
        tuple(union_gangs.values()),
    )
    issues.extend("facts:" + issue.area + ":" + issue.reason for issue in fact_issues)
    gang_map = {candidate.action_key: candidate for candidate in attached}

    counts: Counter[str] = Counter()
    regimes = {}
    for regime in ("unrestricted", "drawn_only"):
        gang = [raw._facts_mapping(gang_map[key]) for key in gangs[regime]]
        discards = [
            _leaf_scalar(
                contexts[regime], public_after_root, root.meld_count, code,
                summary_cache, scalar_cache, performance,
            )
            for code in discard_codes[regime]
        ]
        pareto = _pareto(discards)
        counts[regime + "_hu"] += int(drawn_summary.is_win)
        counts[regime + "_gang"] += len(gang)
        counts[regime + "_discard"] += len(discards)
        counts[regime + "_discard_pareto"] += len(pareto)
        regimes[regime] = {
            "hu": drawn_summary.is_win,
            "gang": gang,
            "discard_pareto": pareto,
        }
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
        summary_cache: dict[tuple[Any, ...], Any] = {}
        scalar_cache: dict[tuple[Any, ...], dict[str, Any]] = {}
        phase = request.observation.phase
        if phase != "draw":
            global_counts["response_fallback_windows"] += 1
            local["response_fallback_windows"] += 1
            response_ids.append(window_id)
            window_rows.append({
                "window_id": window_id, "origins": origins, "phase": phase,
                "elapsed_ms": (time.perf_counter() - started) * 1000.0,
                "counts": dict(sorted(local.items())), "performance_counts": {},
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
                    summary_cache, scalar_cache, local_performance,
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
        raise SystemExit("R17 批量性能复核目录已存在；拒绝覆盖")
    OUT.mkdir(parents=True)
    raw_result = json.loads(RAW_RESULT.read_text(encoding="utf-8"))
    expected = raw_result["semantic_digest"]
    windows = raw.r16.load_windows()
    first_edges, first_windows, first = evaluate_once(windows)
    second_edges, second_windows, second = evaluate_once(windows)
    cold_latency = _latency(first_windows)
    warm_latency = _latency(second_windows)
    equivalent = first["semantic_digest"] == expected and second["semantic_digest"] == expected
    deterministic = first["semantic_digest"] == second["semantic_digest"]
    performance_pass = (
        warm_latency["p99_ms"] <= raw.RESEARCH_P99_MS_MAX
        and warm_latency["max_ms"] <= raw.RESEARCH_WINDOW_MS_MAX
    )
    result = {
        "schema": "r17-public-successor-batch-performance-result/1",
        "status": (
            "PASS_P0_PERFORMANCE_GATE"
            if equivalent and deterministic and performance_pass
            else (
                "FAIL_PERFORMANCE_AFTER_BATCH_EQUIVALENT_OPTIMIZATION"
                if equivalent and deterministic else "FAIL_SEMANTIC_EQUIVALENCE"
            )
        ),
        "windows": len(windows), "tables": 0, "model_calls": 0,
        "strength_claim": False, "selection_eligible": False,
        "semantic_equivalence": {
            "passed": equivalent, "raw_digest": expected,
            "cold_digest": first["semantic_digest"], "warm_digest": second["semantic_digest"],
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
        "equivalence_proof": {
            "hand_summary_key": "analyse_hand 只读取最终暗牌计数与 meld_count；公开计数不参与向听/有效牌集合",
            "support_formula": "对 summary.useful_tiles 逐牌求 max(0,4-最终暗牌计数-最终公开计数)，与 _waiting_facts(public_after_root,newly_hidden=次弃牌) 代数相同",
            "discard_legality": "you_cai_bi_kao=false 的本人 draw 窗口：不受限时每个暗牌值可弃，受限时仅摸切；顺序均按 TILE_ORDER",
            "no_pruning": "所有合法弃牌叶都计算标量；只在随后执行原冻结 Pareto reducer 时不物化被支配叶的 CandidateFacts 对象",
        },
        "stop_if_failed": "若冻结性能门仍失败，停止P0、不生成候选；下一步必须复盘搜索深度或把批量规则接口下沉到hangma生产边界",
    }
    raw.write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    raw.write_json(_project_file(_PROJECT_ROOT, OUT / "per-window.json"), {
        "schema": "r17-public-successor-batch-performance-per-window/1",
        "cold": first_windows, "warm": second_windows,
    })
    raw.write_json(_project_file(_PROJECT_ROOT, OUT / "frontier-sample.json"), raw.frontier_sample(first_edges, 12))
    raw.write_json(_project_file(_PROJECT_ROOT, OUT / "issues.json"), {
        "schema": "r17-public-successor-batch-performance-issues/1",
        "route": first["route_issues"], "projection": first["projection_issues"],
    })
    runner = Path(__file__)
    raw.write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r17-public-successor-batch-performance-manifest/1",
        "runner": {"path": str(runner), "sha256": hashlib.sha256(runner.read_bytes()).hexdigest()},
        "raw_result": {"path": str(RAW_RESULT), "sha256": hashlib.sha256(RAW_RESULT.read_bytes()).hexdigest()},
        "optimization": "跨根共享HandSummary；批量公开支持；惰性标量前沿，不构造弃牌CandidateFacts",
        "forbidden_changes": ["删除容量边", "删除合法叶", "合并抓打包络", "改变冻结阈值"],
        "outputs": ["result.json", "per-window.json", "frontier-sample.json", "issues.json"],
    })
    print(json.dumps({
        "status": result["status"], "equivalent": equivalent,
        "latency": result["latency"], "performance_counts": first["performance_counts"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
