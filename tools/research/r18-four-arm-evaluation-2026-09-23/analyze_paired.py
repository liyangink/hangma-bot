"""按对手组合×牌山根分析四臂桌赛；同根四座和两桌不当作独立样本。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/r18-four-arm-evaluation-2026-09-23'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import random
import statistics


COMPARISONS = (
    ("tier_a_minus_v2", "v2_hu_upgrade_v1", "weighted_heuristic_v2"),
    ("r18_v1_minus_v2", "r18_v1", "weighted_heuristic_v2"),
    ("r18_v2_minus_v2", "r18_v2", "weighted_heuristic_v2"),
    ("r18_v2_minus_v1", "r18_v2", "r18_v1"),
)
FAMILY_ALPHA = 0.05
POWER_FACTOR = 11.151  # 四项双侧检验各 α=0.0125、80% 功效的正态近似平方系数。


def percentile(sorted_values: list[float], probability: float) -> float:
    """返回线性插值分位数；输入已排序，概率在 0..1 之间。"""
    position = (len(sorted_values) - 1) * probability
    low = math.floor(position)
    high = math.ceil(position)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


def main() -> None:
    """复核完成率与执行故障，输出分层独立根重采样的配对效果摘要。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-dir", type=Path, required=True)
    parser.add_argument("--bootstrap-reps", type=int, default=20_000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260923)
    args = parser.parse_args()
    if args.bootstrap_reps < 1_000:
        parser.error("bootstrap 至少执行 1,000 次")

    manifest = json.loads((args.study_dir / "manifest.json").read_text(encoding="utf-8"))
    result = json.loads((args.study_dir / "result.json").read_text(encoding="utf-8"))
    roots = result["root_clusters"]
    expected = len(roots) * len(manifest["arms"]) * len(manifest["seats"])
    stage_paths = sorted((args.study_dir / "stages").glob("*.json"))
    if len(stage_paths) != expected or result["complete_tables"] != manifest["planned_complete_tables"]:
        raise SystemExit("阶段文件数或完整桌数与冻结清单不一致")

    runtime_counts: dict[str, Counter] = defaultdict(Counter)
    execution_counts: dict[str, Counter] = defaultdict(Counter)
    scoring_activity: dict[str, Counter] = defaultdict(Counter)
    table_outcomes: dict[str, Counter] = defaultdict(Counter)
    stage_outcomes: dict[str, Counter] = defaultdict(Counter)
    table_scores: dict[str, list[int]] = defaultdict(list)
    stage_status = Counter()
    for path in stage_paths:
        row = json.loads(path.read_text(encoding="utf-8"))
        arm, stage = row["arm"], row["stage"]
        review = stage["execution_review"]
        stage_status[(stage["status"], review["status"])] += 1
        if stage["status"] != "complete" or review["status"] != "complete":
            raise SystemExit("阶段或执行审计不完整：" + str(path))
        if len(stage["tables"]) != manifest["tables_per_stage"]:
            raise SystemExit("阶段桌数不完整：" + str(path))
        stage_totals = stage["stage_totals_by_participant"]
        focal_stage_score = stage_totals["focal"]
        stage_higher = sum(score > focal_stage_score for participant, score
                           in stage_totals.items() if participant != "focal")
        stage_outcomes[arm]["stages"] += 1
        stage_outcomes[arm]["strict_first"] += int(all(
            focal_stage_score > score for participant, score in stage_totals.items()
            if participant != "focal"))
        stage_outcomes[arm]["top_two_including_ties"] += int(stage_higher <= 1)
        for key, value in review["recorded_failure_kinds"].items():
            execution_counts[arm][key] += value
        for key in ("action_value_failed", "ambiguous_diagnostics", "unclassified_action_value"):
            execution_counts[arm][key] += review["recorded_counts"][key]
        for key in ("action_value_scored", "decision_count", "other_policy_decisions"):
            scoring_activity[arm][key] += review["recorded_counts"][key]
        for table in stage["tables"]:
            if table["result"]["status"] != "complete":
                raise SystemExit("桌赛未完成：" + str(path))
            for key, value in table["result"]["runtime_counts"].items():
                if isinstance(value, int):
                    runtime_counts[arm][key] += value
            scores = table["scores_by_seat"]
            focal = scores[row["focal_seat"]]
            table_scores[arm].append(focal)
            higher = sum(score > focal for score in scores)
            table_outcomes[arm]["tables"] += 1
            table_outcomes[arm]["strict_first"] += int(all(focal > score for i, score in enumerate(scores)
                                                            if i != row["focal_seat"]))
            table_outcomes[arm]["top_two_including_ties"] += int(higher <= 1)
    for arm in manifest["arms"]:
        if any(runtime_counts[arm][key] for key in ("timeouts", "illegal_choices", "fallbacks", "audit_missing")):
            raise SystemExit("策略运行故障非零：" + arm)
        if any(execution_counts[arm].values()):
            raise SystemExit("评分内部故障非零：" + arm)
        if arm.startswith("r18_") and scoring_activity[arm]["action_value_scored"] == 0:
            raise SystemExit("R18 未进入受限评分路径：" + arm)

    strata = {mix: [row for row in roots if row["mix"] == mix] for mix in manifest["mixes"]}
    if any(not rows for rows in strata.values()):
        raise SystemExit("对手组合层缺失")
    vectors = {
        mix: [[row["table_score_mean_by_arm"][a] - row["table_score_mean_by_arm"][b]
               for _name, a, b in COMPARISONS] for row in rows]
        for mix, rows in strata.items()
    }
    rng = random.Random(args.bootstrap_seed)
    bootstrap = [[] for _ in COMPARISONS]
    for _ in range(args.bootstrap_reps):
        totals = [0.0] * len(COMPARISONS)
        for rows in vectors.values():
            for _ in rows:
                sampled = rows[rng.randrange(len(rows))]
                for i, value in enumerate(sampled):
                    totals[i] += value
        for i, total in enumerate(totals):
            bootstrap[i].append(total / len(roots))

    comparisons = {}
    tail = FAMILY_ALPHA / (2 * len(COMPARISONS))
    for i, (name, a, b) in enumerate(COMPARISONS):
        values = [row["table_score_mean_by_arm"][a] - row["table_score_mean_by_arm"][b]
                  for row in roots]
        draws = sorted(bootstrap[i])
        sd = statistics.stdev(values)
        comparisons[name] = {
            "mean_delta_per_table": statistics.mean(values),
            "root_paired_sd_per_table": sd,
            "bonferroni_bootstrap_interval": [percentile(draws, tail), percentile(draws, 1 - tail)],
            "mean_by_opponent_mix": {
                mix: statistics.mean(row["table_score_mean_by_arm"][a]
                                     - row["table_score_mean_by_arm"][b] for row in rows)
                for mix, rows in strata.items()
            },
            "normal_approx_roots_for_delta_3": math.ceil(POWER_FACTOR * (sd / 3) ** 2),
            "normal_approx_roots_for_delta_5": math.ceil(POWER_FACTOR * (sd / 5) ** 2),
        }

    summary = {
        "schema": "r18-four-arm-paired-analysis/1",
        "study_manifest": str(args.study_dir / "manifest.json"),
        "complete_tables": result["complete_tables"],
        "independent_root_clusters": len(roots),
        "roots_by_opponent_mix": {mix: len(rows) for mix, rows in strata.items()},
        "stage_status_counts": {"/".join(key): value for key, value in stage_status.items()},
        "runtime_counts_by_arm": {arm: dict(runtime_counts[arm]) for arm in manifest["arms"]},
        "scoring_failure_counts_by_arm": {arm: dict(execution_counts[arm]) for arm in manifest["arms"]},
        "scoring_activity_by_arm": {arm: dict(scoring_activity[arm]) for arm in manifest["arms"]},
        "table_outcomes_by_arm": {arm: dict(table_outcomes[arm]) for arm in manifest["arms"]},
        "stage_outcomes_by_arm": {arm: dict(stage_outcomes[arm]) for arm in manifest["arms"]},
        "table_score_quantiles_by_arm": {
            arm: {"min": min(table_scores[arm]), "p10": percentile(sorted(table_scores[arm]), .10),
                  "median": percentile(sorted(table_scores[arm]), .50),
                  "p90": percentile(sorted(table_scores[arm]), .90), "max": max(table_scores[arm])}
            for arm in manifest["arms"]
        },
        "arm_mean_score_per_table": {
            arm: statistics.mean(row["table_score_mean_by_arm"][arm] for row in roots)
            for arm in manifest["arms"]
        },
        "comparisons": comparisons,
        "interval_method": {
            "family_alpha": FAMILY_ALPHA,
            "comparison_count": len(COMPARISONS),
            "per_comparison_two_sided_alpha": FAMILY_ALPHA / len(COMPARISONS),
            "cluster_unit": "opponent_mix × root_index",
            "resampling": "independent roots with replacement within H/M, same sampled roots across four contrasts",
            "bootstrap_reps": args.bootstrap_reps,
            "bootstrap_seed": args.bootstrap_seed,
            "tails": [tail, 1 - tail],
        },
    }
    target = args.study_dir / "analysis.json"
    target.write_text(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                      encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
