"""R17 零桌原型：全公开容量边的有界自摸后继叶。

正式投影只接管 ``phase=draw`` 的合法弃牌根；响应窗口不生成后继信号，
要求策略精确回退稳定 V2。每个弃牌根完成后，按当前公开事实计算 34 种
牌码的剩余容量，枚举全部容量大于零的下一次普通摸牌，包含当前牌效事实
未列为 ``useful_tiles`` 的中性/退化边，避免重演 R16-B 的好边过滤偏差。

下一摸牌叶不构造未来 ``PlayerObservation``，而是以显式条件化的
``WindowContext`` 调用 ``hangma.action_families``，并用
``hangma.candidate_facts`` / ``hangma.hand_analysis`` 生产胡、杠、弃牌事实：

* ``unrestricted``：下一窗口不受抓打圈约束；
* ``drawn_only``：下一窗口受抓打圈约束，只能摸切（仍可暗杠/自摸胡）；
* 杠只在当前剩余牌数已经大于 20 时列为“未来仍 >20”条件叶。

未见张数是公开容量，不是摸牌概率；不模拟对手，不生成未来观察。
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
from typing import Any, Iterable


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import r16_goal_first_preflight_02 as r16  # noqa: E402
from hangma_bot.hangma import action_families, candidate_facts, hand_analysis  # noqa: E402
from hangma_bot.hangma.candidate_facts import (  # noqa: E402
    FactsAnalysisError,
    _remaining,
    _remove_codes,
)
from hangma_bot.hangma.engine import _build_context, _public_counts  # noqa: E402
from hangma_bot.hangma.internal_types import (  # noqa: E402
    TILE_INDEX,
    TILE_ORDER,
    WindowContext,
    counts_from_tiles,
)
from hangma_bot.kernel.actions import Discard, Gang, Hu, Tile  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r17-public-successor-pilot-01-20260921')
RULE_CONFIG_EVIDENCE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/cross-specialist-01-20260921/manifest.json')
RESEARCH_P99_MS_MAX = 200.0
RESEARCH_WINDOW_MS_MAX = 500.0


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _sorted_codes(tiles: Iterable[Tile]) -> tuple[str, ...]:
    return tuple(sorted((tile.code for tile in tiles), key=TILE_INDEX.get))


def _adjust_public_counts(public_counts: Any, newly_public: dict[str, int]) -> tuple[Any, ...]:
    adjusted = list(public_counts)
    for code, amount in newly_public.items():
        index = TILE_INDEX[code]
        if adjusted[index] is not None:
            adjusted[index] += amount
    return tuple(adjusted)


@dataclass(frozen=True)
class DiscardRoot:
    """当前合法弃牌完成后的摸前暗牌。"""

    hand: tuple[Tile, ...]
    meld_count: int
    newly_public: dict[str, int]
    shanten: int
    useful_codes: frozenset[str]


def _discard_root(candidate: Any, context: WindowContext, meld_count: int) -> DiscardRoot:
    if not isinstance(candidate.action, Discard):
        raise FactsAnalysisError("R17 首版只接受合法弃牌根")
    facts = candidate.facts
    if facts is None or facts.fact_kind.value != "hand_progress" or facts.shanten_after is None:
        raise FactsAnalysisError("弃牌根缺少完整 hand_progress 事实")
    code = candidate.action.tile.code
    full = tuple(tile.code for tile in context.full_hand())
    if code not in full:
        raise FactsAnalysisError("弃牌不在当前暗牌全集")
    hand = tuple(Tile(item) for item in _remove_codes(full, {code: 1}))
    return DiscardRoot(
        hand=hand,
        meld_count=meld_count,
        newly_public={code: 1},
        shanten=facts.shanten_after,
        useful_codes=frozenset(tile.code for tile in facts.useful_tiles),
    )


def _future_context(
    current: WindowContext,
    root: DiscardRoot,
    drawn_code: str,
    *,
    catch_play: bool,
) -> WindowContext:
    """构造显式条件 WindowContext；不冒充未来官方观察。"""

    # 牌墙只会减少：当前已 <=20 时未来必禁杠；当前 >20 只能条件化为
    # “未来仍 >20”。给 action_families 的 21 是条件哨兵，不是未来墙估计。
    wall = current.remaining_tile_count
    conditional_wall = None if wall is None else (21 if wall > 20 else 20)
    return WindowContext(
        seat=current.seat,
        phase="draw",
        turn_seat=current.seat,
        responding_seats=(),
        hand_tiles=root.hand,
        drawn_tile=Tile(drawn_code),
        my_chi_count=current.my_chi_count,
        my_peng_codes=current.my_peng_codes,
        last_discard=None,
        catch_play=catch_play,
        remaining_tile_count=conditional_wall,
    )


def _facts_mapping(candidate: Any) -> dict[str, Any]:
    facts = candidate.facts
    result: dict[str, Any] = {"action_key": candidate.action_key}
    if facts is None:
        result["fact_kind"] = None
        return result
    result.update({
        "fact_kind": facts.fact_kind.value,
        "shanten": facts.shanten_after,
        "standard_shanten": facts.standard_shanten_after,
        "seven_pairs_shanten": facts.seven_pairs_shanten_after,
        "support_remaining": sum(tile.remaining_estimate for tile in facts.useful_tiles),
        "useful_tile_count": len(facts.useful_tiles),
        "replacement_draw_unknown": facts.replacement_draw_unknown,
    })
    return result


def _dominates(left: dict[str, Any], right: dict[str, Any]) -> bool:
    """弃牌叶的保守 Pareto 支配：低向听、高公开支持。"""

    names = ("shanten", "standard_shanten")
    if left["seven_pairs_shanten"] is not None:
        names += ("seven_pairs_shanten",)
    if any(left[name] > right[name] for name in names):
        return False
    strict = any(left[name] < right[name] for name in names)
    if left["support_remaining"] < right["support_remaining"]:
        return False
    return strict or left["support_remaining"] > right["support_remaining"]


def _pareto(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for index, row in enumerate(rows)
        if not any(
            other_index != index and _dominates(other, row)
            for other_index, other in enumerate(rows)
        )
    ]


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1)]


def _route_check(
    window_id: str,
    candidate: Any,
    root: DiscardRoot,
    capacities: dict[str, int],
) -> tuple[int, int, list[dict[str, Any]]]:
    """核验现有 ValueRoute 是全容量边中的可成胡子集。"""

    routes = () if candidate.value_facts is None else candidate.value_facts.routes
    edge_count = 0
    issues = []
    expected_hand = _sorted_codes(root.hand)
    for route_index, route in enumerate(routes):
        conditions = route.conditions
        if (
            route.followup_discard is not None
            or conditions.draw_kind != "normal"
            or conditions.pre_draw_hand != expected_hand
            or conditions.meld_count != root.meld_count
        ):
            issues.append({
                "window_id": window_id,
                "action_key": candidate.action_key,
                "route_index": route_index,
                "kind": "route_waiting_basis_mismatch",
            })
            continue
        for tile in route.useful_tiles:
            edge_count += 1
            if capacities.get(tile.code) != tile.remaining_estimate:
                issues.append({
                    "window_id": window_id,
                    "action_key": candidate.action_key,
                    "route_index": route_index,
                    "tile": tile.code,
                    "kind": "route_capacity_mismatch",
                    "route": tile.remaining_estimate,
                    "all_edge": capacities.get(tile.code),
                })
            if hand_analysis.win_split(root.hand + (Tile(tile.code),), root.meld_count) is None:
                issues.append({
                    "window_id": window_id,
                    "action_key": candidate.action_key,
                    "route_index": route_index,
                    "tile": tile.code,
                    "kind": "route_not_hand_analysis_win",
                })
    return len(routes), edge_count, issues


def _edge_leaf(
    root: DiscardRoot,
    current: WindowContext,
    public_after_root: tuple[Any, ...],
    drawn_code: str,
) -> tuple[dict[str, Any], Counter[str], list[str]]:
    """用规则动作族生成两个抓打条件下的胡/杠/弃牌叶。"""

    contexts = {
        "unrestricted": _future_context(current, root, drawn_code, catch_play=False),
        "drawn_only": _future_context(current, root, drawn_code, catch_play=True),
    }
    outcomes = {}
    issues = []
    union: dict[str, Any] = {}
    for regime, context in contexts.items():
        summary = hand_analysis.analyse_hand(context.full_hand(), root.meld_count)
        outcome = action_families.generate_candidates(context, summary)
        keys = []
        for candidate in outcome.candidates:
            if isinstance(candidate.action, (Hu, Gang, Discard)):
                union[candidate.action_key] = candidate
                keys.append(candidate.action_key)
        outcomes[regime] = tuple(keys)
        issues.extend(regime + ":" + issue.area + ":" + issue.reason for issue in outcome.issues)

    attached, fact_issues = candidate_facts.attach_facts(
        contexts["unrestricted"], public_after_root, root.meld_count, tuple(union.values())
    )
    issues.extend("facts:" + issue.area + ":" + issue.reason for issue in fact_issues)
    mapped = {candidate.action_key: candidate for candidate in attached}

    counts: Counter[str] = Counter()
    regimes = {}
    for regime, keys in outcomes.items():
        hu = [key for key in keys if isinstance(mapped[key].action, Hu)]
        gang = [_facts_mapping(mapped[key]) for key in keys if isinstance(mapped[key].action, Gang)]
        discards = [
            _facts_mapping(mapped[key]) for key in keys if isinstance(mapped[key].action, Discard)
        ]
        pareto = _pareto(discards)
        counts[regime + "_hu"] += len(hu)
        counts[regime + "_gang"] += len(gang)
        counts[regime + "_discard"] += len(discards)
        counts[regime + "_discard_pareto"] += len(pareto)
        regimes[regime] = {
            "hu": bool(hu),
            "gang": gang,
            "discard_pareto": pareto,
        }
    return regimes, counts, issues


def evaluate_once(
    windows: list[tuple[str, Any, list[str]]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    edge_rows: list[dict[str, Any]] = []
    window_rows: list[dict[str, Any]] = []
    global_counts: Counter[str] = Counter()
    route_issues: list[dict[str, Any]] = []
    fact_issues: list[dict[str, Any]] = []
    response_ids = []

    for window_id, request, origins in windows:
        started = time.perf_counter()
        local: Counter[str] = Counter()
        phase = request.observation.phase
        if phase != "draw":
            global_counts["response_fallback_windows"] += 1
            local["response_fallback_windows"] += 1
            response_ids.append(window_id)
            window_rows.append({
                "window_id": window_id,
                "origins": origins,
                "phase": phase,
                "elapsed_ms": (time.perf_counter() - started) * 1000.0,
                "counts": dict(sorted(local.items())),
            })
            continue

        global_counts["draw_windows"] += 1
        local["draw_windows"] += 1
        context = _build_context(request.observation)
        public_counts = _public_counts(request.observation)
        meld_count = len(request.observation.melds[request.observation.seat])
        discard_candidates = [
            candidate
            for candidate in request.rules.legal_candidates
            if isinstance(candidate.action, Discard)
        ]
        for candidate in discard_candidates:
            global_counts["discard_roots"] += 1
            local["discard_roots"] += 1
            try:
                root = _discard_root(candidate, context, meld_count)
                counts34 = counts_from_tiles(root.hand)
                capacities = {}
                unknown_codes = []
                for code in TILE_ORDER:
                    try:
                        capacity = _remaining(code, counts34, public_counts, root.newly_public)
                    except FactsAnalysisError:
                        unknown_codes.append(code)
                        continue
                    if capacity > 0:
                        capacities[code] = capacity
                if unknown_codes:
                    fact_issues.append({
                        "window_id": window_id,
                        "action_key": candidate.action_key,
                        "kind": "public_capacity_unknown",
                        "tile_codes": unknown_codes,
                    })
                public_after_root = _adjust_public_counts(public_counts, root.newly_public)
            except Exception as exc:
                fact_issues.append({
                    "window_id": window_id,
                    "action_key": candidate.action_key,
                    "kind": "discard_root_failed",
                    "error": type(exc).__name__ + ": " + str(exc),
                })
                global_counts["discard_roots_failed"] += 1
                local["discard_roots_failed"] += 1
                continue

            global_counts["discard_roots_covered"] += 1
            local["discard_roots_covered"] += 1
            route_groups, route_edges, problems = _route_check(
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
                regimes, leaf_counts, leaf_problems = _edge_leaf(
                    root, context, public_after_root, drawn_code
                )
                global_counts.update(leaf_counts)
                local.update(leaf_counts)
                if leaf_problems:
                    fact_issues.append({
                        "window_id": window_id,
                        "action_key": candidate.action_key,
                        "draw_tile": drawn_code,
                        "kind": "future_leaf_rule_issues",
                        "issues": leaf_problems,
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

        window_rows.append({
            "window_id": window_id,
            "origins": origins,
            "phase": phase,
            "elapsed_ms": (time.perf_counter() - started) * 1000.0,
            "counts": dict(sorted(local.items())),
        })

    semantic_windows = [
        {key: value for key, value in row.items() if key != "elapsed_ms"}
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
        "route_issues": route_issues,
        "fact_issues": fact_issues,
        "response_ids": response_ids,
        "semantic_digest": canonical_digest(semantic),
    }


def latency_summary(rows: list[dict[str, Any]], phase: str) -> dict[str, float]:
    values = [row["elapsed_ms"] for row in rows if row["phase"] == phase]
    return {
        "mean_ms": sum(values) / len(values),
        "p50_ms": _percentile(values, 0.50),
        "p90_ms": _percentile(values, 0.90),
        "p95_ms": _percentile(values, 0.95),
        "p99_ms": _percentile(values, 0.99),
        "max_ms": max(values),
    }


def frontier_sample(rows: list[dict[str, Any]], per_bucket: int = 24) -> dict[str, Any]:
    """保留有限可读样本；完整语义由 canonical digest 与每窗计数固定。"""

    buckets: dict[str, list[dict[str, Any]]] = {
        "useful": [], "non_useful": [], "hu": [], "gang": [],
    }
    for row in rows:
        edge_class = row["edge_class"]
        if len(buckets[edge_class]) < per_bucket:
            buckets[edge_class].append(row)
        regimes = row["regimes"]
        if any(value["hu"] for value in regimes.values()) and len(buckets["hu"]) < per_bucket:
            buckets["hu"].append(row)
        if any(value["gang"] for value in regimes.values()) and len(buckets["gang"]) < per_bucket:
            buckets["gang"].append(row)
    return {
        "schema": "r17-public-successor-frontier-sample/1",
        "per_bucket_limit": per_bucket,
        "buckets": buckets,
        "scope": "有限审计样本；完整逐边内容不作为 Git 必要证据",
    }


def main() -> None:
    if OUT.exists():
        raise SystemExit("R17 后继叶证据目录已存在；拒绝覆盖")
    OUT.mkdir(parents=True)
    windows = r16.load_windows()
    first_edges, first_windows, first = evaluate_once(windows)
    second_edges, second_windows, second = evaluate_once(windows)
    deterministic = first["semantic_digest"] == second["semantic_digest"]

    write_json(_project_file(_PROJECT_ROOT, OUT / "frontier-sample.json"), frontier_sample(first_edges))
    write_json(_project_file(_PROJECT_ROOT, OUT / "per-window.json"), {
        "schema": "r17-public-successor-per-window/2",
        "cold_pass": first_windows,
        "warm_pass": second_windows,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "route-consistency-issues.json"), {
        "schema": "r17-route-consistency-issues/2",
        "issues": first["route_issues"],
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "projection-issues.json"), {
        "schema": "r17-public-successor-projection-issues/2",
        "issues": first["fact_issues"],
    })

    counts = first["counts"]
    draw_work = [
        row["counts"].get("all_capacity_edges", 0)
        for row in first_windows
        if row["phase"] == "draw"
    ]
    cold_latency = latency_summary(first_windows, "draw")
    warm_latency = latency_summary(second_windows, "draw")
    math_pass = deterministic and not first["route_issues"] and not first["fact_issues"]
    performance_pass = (
        warm_latency["p99_ms"] <= RESEARCH_P99_MS_MAX
        and warm_latency["max_ms"] <= RESEARCH_WINDOW_MS_MAX
    )
    result = {
        "schema": "r17-public-successor-pilot-result/2",
        "status": (
            "PASS_P0_ZERO_TABLE_GATE"
            if math_pass and performance_pass
            else (
                "PASS_MATH_FAIL_PERFORMANCE_P0_NOT_ADMITTED"
                if math_pass else "FAIL_ZERO_TABLE_MATH_OR_CONTRACT"
            )
        ),
        "windows": len(windows),
        "tables": 0,
        "model_calls": 0,
        "strength_claim": False,
        "selection_eligible": False,
        "semantic_digest": first["semantic_digest"],
        "full_frontier_rows": len(first_edges),
        "full_frontier_materialized_in_git": False,
        "counts": counts,
        "coverage": {
            "discard_roots": {
                "covered": counts.get("discard_roots_covered", 0),
                "total": counts.get("discard_roots", 0),
            },
            "all_capacity_edges": counts.get("all_capacity_edges", 0),
            "useful_edges": counts.get("useful_edges", 0),
            "non_useful_edges": counts.get("non_useful_edges", 0),
            "non_useful_share": counts.get("non_useful_edges", 0)
            / counts.get("all_capacity_edges", 1),
        },
        "response_fallback": {
            "mode": "EXACT_STABLE_V2_NO_R17_OVERRIDE_REQUIRED",
            "windows": counts.get("response_fallback_windows", 0),
            "window_ids_digest": canonical_digest(first["response_ids"]),
        },
        "determinism": {
            "passed": deterministic,
            "cold_semantic_digest": first["semantic_digest"],
            "warm_semantic_digest": second["semantic_digest"],
        },
        "value_route_consistency": {
            "passed": not first["route_issues"],
            "route_groups_checked": counts.get("value_route_groups", 0),
            "route_edges_checked": counts.get("value_route_edges", 0),
            "issue_count": len(first["route_issues"]),
            "scope": "核验路线摸前暗牌、普通摸牌类型、公开容量与 hand_analysis 成胡；不重复结算数学",
        },
        "projection_issues": {
            "passed": not first["fact_issues"],
            "issue_count": len(first["fact_issues"]),
        },
        "latency": {
            "cold_draw_windows": cold_latency,
            "warm_draw_windows": warm_latency,
        },
        "research_performance_gate": {
            "passed": performance_pass,
            "p99_ms_max": RESEARCH_P99_MS_MAX,
            "window_max_ms": RESEARCH_WINDOW_MS_MAX,
            "observed_warm_p99_ms": warm_latency["p99_ms"],
            "observed_warm_max_ms": warm_latency["max_ms"],
        },
        "workload": {
            "capacity_edges_total": sum(draw_work),
            "capacity_edges_per_draw_window_max": max(draw_work),
            "capacity_edges_per_draw_window_p95": _percentile(
                [float(value) for value in draw_work], 0.95
            ),
        },
        "conditional_legality": {
            "unrestricted": "下一摸牌窗口不受抓打约束时，由 action_families 生成的合法胡/杠/弃牌集合",
            "drawn_only": "下一摸牌窗口受抓打约束时，由 action_families 生成的合法自摸胡/暗杠/摸切集合",
            "gang": "仅当前 wall_remaining>20 时保留，并继续要求未来实际窗口 wall_remaining>20；未把哨兵 21 当未来事实",
            "policy_requirement": "候选不得在当前观察中猜测未来属于哪一抓打/牌墙条件；消费时须对两条件分支做鲁棒聚合或回退 V2",
        },
        "one_allowed_equivalent_optimization": {
            "name": "CANONICAL_LEAF_MEMOIZATION_AND_LAZY_PARETO",
            "required_equivalence": "键必须覆盖规范暗牌计数、副露数、根弃牌新增公开计数、下一弃牌和抓打包络；命中必须逐字段等于当前规则输出",
            "work": "同一窗口先按规范后继手牌键批量分析全部34摸牌，再惰性物化Pareto保留叶；胡/杠单列，不得删非useful边",
            "current_logical_upper_bound": "每窗根弃牌数×至多34摸牌×至多14弃牌；本面板最大476条根-摸边，实际642562个unrestricted弃牌叶",
            "stop_rule": "优化后仍不满足p99≤200ms且max≤500ms则P0继续关闭，回查固定深度/等价批量规则接口，不调用叶程序作者",
        },
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r17-public-successor-pilot-manifest/2",
        "runner": {"path": str(Path(__file__)), "sha256": sha256_file(Path(__file__))},
        "panels": [{"path": str(path), "sha256": sha256_file(path)} for path in r16.PANELS],
        "rule_config_evidence": {
            "path": str(RULE_CONFIG_EVIDENCE),
            "sha256": sha256_file(RULE_CONFIG_EVIDENCE),
            "ruleset_version": "hangma-mvp-v10-public-counts",
            "you_cai_bi_kao": False,
        },
        "deduplicated_windows": len(windows),
        "semantics": {
            "root": "只处理 phase=draw 的 RuleCandidate 合法弃牌；响应窗口不覆盖稳定 V2",
            "draw_edges": "34 牌码中按 _remaining 得到公开容量>0的全部牌；包含非 useful 边",
            "capacity": "remaining_estimate 是公开未见张数，不是概率",
            "leaf": "action_families 生成条件化胡/杠/弃牌，candidate_facts 附加向听与公开支持",
            "pareto": "弃牌叶最小化综合/普通/七对向听并最大化公开支持；胡与 replacement_draw_unknown 杠不强塞入同一序关系",
            "opponents": "不模拟",
            "future_observation": "不构造",
        },
        "outputs": [
            "result.json", "per-window.json", "frontier-sample.json",
            "route-consistency-issues.json", "projection-issues.json",
            "VERDICT.md",
        ],
    })
    print(json.dumps({
        "status": result["status"],
        "windows": len(windows),
        "counts": counts,
        "latency": result["latency"],
        "deterministic": deterministic,
        "route_issues": len(first["route_issues"]),
        "projection_issues": len(first["fact_issues"]),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
