#!/usr/bin/env python3
"""G221：从完整阶段证据复核根级积分与候选行为，不把决策当独立样本。"""

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
from hashlib import sha256
import json
from pathlib import Path
import random
import statistics


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g221-settlement-route-panel-20260929')
ARM = "g221_settlement_route_v1"
BOOTSTRAP_SEED = 20261229221
BOOTSTRAP_REPETITIONS = 100_000


def digest(path: Path) -> str:
    """对机读结论绑定原始完整桌汇总字节。"""
    return sha256(path.read_bytes()).hexdigest()


def percentile(values: list[float], fraction: float) -> float:
    """固定使用排序后的最近秩，不混用插值分位定义。"""
    return sorted(values)[min(len(values) - 1, int(fraction * len(values)))]


def analyze() -> dict:
    """按 H/M 根聚类；改弃的条件价值只解释选择器行为。"""
    result_path = _project_file(_PROJECT_ROOT, OUT / "result.json")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["complete_tables"] == 128
    assert result["independent_root_clusters"] == 8
    roots = {mix: [] for mix in ("H", "M")}
    components = {mix: Counter() for mix in roots}
    for row in result["root_clusters"]:
        mix = row["mix"]
        roots[mix].append(row["delta_vs_baseline_per_table"][ARM])
        components[mix].update(row["component_delta_vs_baseline_per_table"][ARM])
    assert all(len(values) == 4 for values in roots.values())
    assert abs(statistics.mean(map(statistics.mean, roots.values()))
               - result["descriptive_mean_delta_vs_baseline_per_table"][ARM]) < 1e-12

    rng = random.Random(BOOTSTRAP_SEED)
    draws = []
    for _ in range(BOOTSTRAP_REPETITIONS):
        draws.append(statistics.mean(
            statistics.mean(rng.choices(roots[mix], k=4)) for mix in roots))

    statuses = Counter()
    reasons = Counter()
    fallback_error_types = Counter()
    adopted_margins = []
    changed_tables = {mix: set() for mix in roots}
    changed_stage_units = {mix: set() for mix in roots}
    runtime_counts = Counter()
    stage_files = sorted((_project_file(_PROJECT_ROOT, OUT / "stages")).glob("*.json"))
    assert len(stage_files) == 64
    for path in stage_files:
        unit = json.loads(path.read_text(encoding="utf-8"))
        stage = unit["stage"]
        assert stage["status"] == "complete" and stage["error"] is None
        if unit["arm"] != ARM:
            continue
        review = stage["execution_review"]
        assert review["status"] == "complete" and review["zero_internal_failures_verified"]
        for group in ("recorded_counts", "recorded_failure_kinds"):
            for key, value in review[group].items():
                if key in ("action_value_failed", "ambiguous_diagnostics",
                           "unclassified_action_value", "abstain", "operation_limit",
                           "resource_or_numeric_limit", "scoring_error",
                           "unclassified_failure"):
                    runtime_counts[key] += value
        for row in stage["g221_metrics"]:
            statuses[row["status"]] += 1
            if row["status"] == "fallback":
                reasons[row["reason"]] += 1
                fallback_error_types[row.get("error_type", "unknown")] += 1
            if row["status"] == "adopted":
                adopted_margins.append(row["half_total_gain"])
                changed_tables[unit["mix"]].add(row["decision_id"].split(":")[1])
                changed_stage_units[unit["mix"]].add(
                    (unit["root_index"], unit["focal_seat"]))
    assert statuses["adopted"] == 148
    assert statuses["fallback"] == 26
    assert all(value == 0 for value in runtime_counts.values()), runtime_counts
    adopted_margins.sort()
    return {
        "schema": "g221-settlement-route-analysis/1",
        "source_result_sha256": digest(result_path),
        "source_manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "source_stage_count": len(stage_files),
        "independent_root_clusters": 8,
        "root_deltas_per_table": roots,
        "mean_delta_per_table_by_mix": {mix: statistics.mean(values)
                                        for mix, values in roots.items()},
        "component_delta_per_table_by_mix": {
            mix: {key: value / 4 for key, value in sorted(counter.items())}
            for mix, counter in components.items()},
        "stratified_root_bootstrap": {
            "seed": BOOTSTRAP_SEED,
            "repetitions": BOOTSTRAP_REPETITIONS,
            "method": "H/M 各自四根有放回抽四根，然后两池等权",
            "descriptive_95_interval": [percentile(draws, .025), percentile(draws, .975)],
        },
        "selector_statuses": dict(sorted(statuses.items())),
        "selector_fallback_reasons": dict(sorted(reasons.items())),
        "selector_fallback_error_types": dict(sorted(fallback_error_types.items())),
        "changed_stage_units_by_mix": {
            mix: len(values) for mix, values in changed_stage_units.items()},
        "changed_complete_tables_by_mix": {
            mix: len(values) for mix, values in changed_tables.items()},
        "adopted_half_total_gain": {
            "median": statistics.median(adopted_margins),
            "at_most_0_05": sum(value <= .05 for value in adopted_margins),
            "at_most_0_1": sum(value <= .1 for value in adopted_margins),
            "at_most_0_25": sum(value <= .25 for value in adopted_margins),
            "p95_nearest_rank": percentile(adopted_margins, .95),
            "max": max(adopted_margins),
        },
        "execution_review_integer_totals": dict(sorted(runtime_counts.items())),
        "boundary": "八个独立开发根的描述性区间；选择器条件分不是整桌因果收益。",
    }


def main() -> None:
    """只写新的派生分析，原始完整桌与预登记保持不变。"""
    destination = _project_file(_PROJECT_ROOT, OUT / "analysis.json")
    if destination.exists():
        raise FileExistsError(destination)
    destination.write_text(json.dumps(analyze(), ensure_ascii=False, sort_keys=True,
                                      indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
