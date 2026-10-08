"""汇总路线冠军在正/零/负效果根上的同观察改选特征。

本工具只分析已经消费的诊断轨迹，不产生效果样本，也不把事后相关性解释为因果。
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

import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path


HERE = Path(__file__).resolve().parent
BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/route-microfunction-contrastive-01-20260921')
SOURCE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/route-microfunction-contrastive-01-20260921/outcome-diagnostic-01/disagreements.jsonl')
TARGET = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/route-microfunction-contrastive-01-20260921/outcome-diagnostic-01/outcome-feature-analysis.json')


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def quantiles(values: list[float]) -> dict:
    """返回不依赖第三方库的描述统计；空集合显式保留。"""
    if not values:
        return {"count": 0, "min": None, "q25": None, "median": None,
                "q75": None, "max": None, "mean": None}
    ordered = sorted(values)

    def percentile(ratio: float) -> float:
        position = ratio * (len(ordered) - 1)
        low = math.floor(position)
        high = math.ceil(position)
        if low == high:
            return ordered[low]
        weight = position - low
        return ordered[low] * (1.0 - weight) + ordered[high] * weight

    return {
        "count": len(ordered),
        "min": ordered[0],
        "q25": percentile(0.25),
        "median": statistics.median(ordered),
        "q75": percentile(0.75),
        "max": ordered[-1],
        "mean": statistics.fmean(ordered),
    }


def preferred_trace(record: dict, side: str) -> dict:
    preferred = record[side]["preferred"]
    return record[side]["traces"][preferred]


def action_family(action_key: str | None) -> str:
    return "none" if action_key is None else action_key.split(":", 1)[0]


def stage_position(record: dict) -> tuple[float, int]:
    visible = record["candidate_view"]["visible_state"]
    seat = int(visible["seat"])
    scores = record["candidate_view"].get("competition", {}).get("current_stage_scores")
    if scores is None or len(scores) != 4:
        scores = visible["table_scores"]
    own = float(scores[seat])
    rank = 1 + sum(float(value) > own for value in scores)
    return own, rank


def extract(record: dict) -> dict:
    parent_preferred = record["parent"]["preferred"]
    child_preferred = record["child"]["preferred"]
    parent_trace = preferred_trace(record, "parent")
    child_trace = preferred_trace(record, "child")
    parent_score = float(record["parent"]["scores"][parent_preferred])
    child_base_score = float(record["parent"]["scores"][child_preferred])
    own_stage_score, stage_rank = stage_position(record)
    route_raw = child_trace.get("route_raw")
    route_low = child_trace.get("route_low")
    route_high = child_trace.get("route_high")
    route_span = None
    if route_low is not None and route_high is not None:
        route_span = float(route_high) - float(route_low)
    return {
        "root_id": record["context"]["root_id"],
        "view_sha256": record["view_sha256"],
        "outcome_class": record["context"]["outcome_class"],
        "mix": record["context"]["mix"],
        "transition": action_family(parent_preferred) + "->" + action_family(child_preferred),
        "child_family": action_family(child_preferred),
        "phase": record["observation"]["phase"],
        "route_delta": float(child_trace.get("route_delta", 0.0)),
        "route_raw": None if route_raw is None else float(route_raw),
        "route_span": route_span,
        "base_score_gap": parent_score - child_base_score,
        "wall_remaining": float(record["candidate_view"]["visible_state"]["remaining_tile_count"]),
        "own_stage_score": own_stage_score,
        "stage_rank": stage_rank,
    }


def describe(rows: list[dict]) -> dict:
    counters = {
        "transitions": Counter(row["transition"] for row in rows),
        "child_families": Counter(row["child_family"] for row in rows),
        "phases": Counter(row["phase"] for row in rows),
        "mixes": Counter(row["mix"] for row in rows),
    }
    metrics = {}
    for key in ("route_delta", "route_raw", "route_span", "base_score_gap",
                "wall_remaining", "own_stage_score", "stage_rank"):
        metrics[key] = quantiles([
            float(row[key]) for row in rows if row[key] is not None
        ])
    return {
        "observations": len(rows),
        **{key: dict(value.most_common()) for key, value in counters.items()},
        "metrics": metrics,
    }


def pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 3:
        return None
    left_mean = statistics.fmean(left)
    right_mean = statistics.fmean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    denominator = math.sqrt(
        sum((x - left_mean) ** 2 for x in left)
        * sum((y - right_mean) ** 2 for y in right)
    )
    return None if denominator == 0.0 else numerator / denominator


def main() -> None:
    raw = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines()]
    deduplicated = {}
    duplicates = 0
    for record in raw:
        key = (record["context"]["root_id"], record["view_sha256"])
        current = deduplicated.get(key)
        if current is None:
            deduplicated[key] = record
            continue
        duplicates += 1
        if record["context"]["active"] == "child":
            deduplicated[key] = record
    rows = [extract(record) for _, record in sorted(deduplicated.items())]
    by_class = {
        label: describe([row for row in rows if row["outcome_class"] == label])
        for label in ("positive_extreme", "zero", "negative_extreme")
    }
    by_transition = {
        label: describe([row for row in rows if row["transition"] == label])
        for label in sorted({row["transition"] for row in rows})
    }
    root_rows = []
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["root_id"]].append(row)
    original_by_root = {}
    for record in raw:
        original_by_root[record["context"]["root_id"]] = record["context"]
    for root_id, items in sorted(grouped.items()):
        context = original_by_root[root_id]
        root_rows.append({
            "root_id": root_id,
            "outcome_class": context["outcome_class"],
            "mix": context["mix"],
            "d_low": float(context["d_low"]),
            "changed_observations": len(items),
            "claim_changes": sum(row["child_family"] in ("chi", "peng") for row in items),
            "discard_changes": sum(row["child_family"] == "discard" for row in items),
        })
    fixed_deltas = sorted({row["route_delta"] for row in rows})
    result = {
        "schema": "r10-route-microfunction-outcome-feature-analysis/1",
        "source_records": len(raw),
        "deduplicated_observations": len(rows),
        "duplicate_trajectory_records": duplicates,
        "deduplication_key": "root_id + view_sha256；重复时优先保留 child 活动轨迹",
        "all_changed_bonuses_equal": len(fixed_deltas) == 1,
        "changed_bonus_values": fixed_deltas,
        "mathematical_finding": (
            "best_only 对同窗 route_high 使用 (route_raw-route_low)/(route_high-route_low)，"
            "其值恒为1；因此所有被改变的首选动作均获完整 RMF_SCALE，原始优势幅度被丢弃。"
        ),
        "overall": describe(rows),
        "by_outcome_class": by_class,
        "by_transition": by_transition,
        "root_rows": root_rows,
        "posthoc_root_correlations": {
            "changed_observations_vs_d_low": pearson(
                [float(row["changed_observations"]) for row in root_rows],
                [row["d_low"] for row in root_rows],
            ),
            "claim_changes_vs_d_low": pearson(
                [float(row["claim_changes"]) for row in root_rows],
                [row["d_low"] for row in root_rows],
            ),
            "discard_changes_vs_d_low": pearson(
                [float(row["discard_changes"]) for row in root_rows],
                [row["d_low"] for row in root_rows],
            ),
        },
        "interpretation_boundary": (
            "本分析从按效果极值抽取的12个已消费根产生，只能提出下一批结构假设；"
            "不得作为新候选效果、显著性、因果或发布证据。"
        ),
        "selection_eligible": False,
        "confirmation_eligible": False,
        "release_eligible": False,
        "next_search_axes": [
            "保留 route_raw 或相对第二名的幅度，禁止同窗第一名无条件映射为固定满额奖励",
            "把 discard 与 chi/peng 的加分门分开，避免一次结构同时改变留牌和副露承诺",
            "零效应稳定V2与当前固定+8冠军必须作为显式控制父代",
        ],
    }
    write_json(TARGET, result)
    print(json.dumps({
        "status": "COMPLETE",
        "source_records": len(raw),
        "deduplicated_observations": len(rows),
        "changed_bonus_values": fixed_deltas,
        "correlations": result["posthoc_root_correlations"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
