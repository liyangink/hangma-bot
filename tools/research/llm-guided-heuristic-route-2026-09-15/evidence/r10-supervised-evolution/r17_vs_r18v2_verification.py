"""P28 补充核验：冻结未漂移、配对红线、逐桌基线身份、窗口账。

与主脚本分开写，是因为主脚本的字节摘要在 prepare 时已进冻结清单；本脚本只读
既有产物并另写一份 verification.json，不改动任何已冻结内容。
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
import time
from collections import Counter, defaultdict
from pathlib import Path

import r17_vs_r18v2_evaluation as p28


def phase_split_choose_cost(arm: str, source_row: dict) -> dict:
    """单来源探针：按窗口阶段拆开焦点策略 choose 的墙钟耗时。

    主脚本的 t_focal_choose_ms 没有带阶段标签，p50 落在 0.25 ms 上不好解释；
    这里在**同一个 execute_stage 装配路径**上再包一层计时，按
    request.observation.phase 分桶。只跑 2 张桌，单进程无并发。
    """

    samples: list[tuple[str, float]] = []
    original = p28.natural.arm_logical_policies

    class _Probe:
        def __init__(self, inner):
            self.inner = inner
            self.policy_id = inner.policy_id
            self.max_operations = getattr(inner, "max_operations", None)

        async def choose(self, request, budget):
            started = time.perf_counter()
            try:
                return await self.inner.choose(request, budget)
            finally:
                samples.append(
                    (
                        str(request.observation.phase),
                        (time.perf_counter() - started) * 1000.0,
                    )
                )

    def wrapper(**kwargs):
        policies = original(**kwargs)
        focal = policies[p28.natural.FOCAL_PARTICIPANT]
        policies[p28.natural.FOCAL_PARTICIPANT] = _Probe(focal)
        return policies

    p28.natural.arm_logical_policies = wrapper
    try:
        row = p28.execute_stage(arm, source_row, p28.passing_candidates())
    finally:
        p28.natural.arm_logical_policies = original
    by_phase = defaultdict(list)
    for phase, elapsed in samples:
        by_phase[phase].append(elapsed)
    return {
        "arm": arm,
        "source": source_row["source_id"],
        "tables": len(row["stage"]["tables"]),
        "status": row["stage"]["status"],
        "focal_policy_ids": [
            item["policy_id"] for item in row["stage"]["focal_policy_ids_by_table"]
        ],
        "by_phase": {
            phase: {
                "samples": len(values),
                "p50_ms": round(p28.percentile(values, 0.50), 3),
                "p90_ms": round(p28.percentile(values, 0.90), 3),
                "p99_ms": round(p28.percentile(values, 0.99), 3),
                "max_ms": round(max(values), 3),
                "mean_ms": round(statistics.fmean(values), 3),
            }
            for phase, values in sorted(by_phase.items())
        },
        "all": {
            "samples": len(samples),
            "p50_ms": round(p28.percentile([v for _, v in samples], 0.50), 3),
            "p99_ms": round(p28.percentile([v for _, v in samples], 0.99), 3),
            "max_ms": round(max(v for _, v in samples), 3),
        },
    }


def sign_test(rows, key):
    """配对标号检验（精确二项，双侧）。**诊断量**：预登记判定不读它。"""

    wins = sum(1 for row in rows if float(row[key]) > 0)
    losses = sum(1 for row in rows if float(row[key]) < 0)
    ties = len(rows) - wins - losses
    n = wins + losses
    if n == 0:
        return {"wins": wins, "losses": losses, "ties": ties, "p_two_sided": None}
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / float(2 ** n)
    return {
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "p_two_sided": round(min(1.0, 2.0 * tail), 6),
        "note": "精确二项符号检验，忽略并列；只作诊断，不参与预登记判定",
    }


def paired_rows(candidate_arm, baseline_arm="baseline"):
    rows = []
    for source_row in p28.sources():
        source_id = str(source_row["source_id"])
        base = json.loads(
            p28._stage_path(baseline_arm, source_row).read_text(encoding="utf-8")
        )["stage"]
        cand = json.loads(
            p28._stage_path(candidate_arm, source_row).read_text(encoding="utf-8")
        )["stage"]
        rows.append(
            {
                "source_id": source_id,
                "mix": source_row["mix"],
                "root_index": source_row["root_index"],
                "focal_seat": source_row["focal_seat"],
                "u_delta_low": cand["u_low"] - base["u_high"],
                "stage_score_delta": cand["focal_stage_score"] - base["focal_stage_score"],
                "candidate_u_low": cand["u_low"],
                "candidate_u_high": cand["u_high"],
                "baseline_u_low": base["u_low"],
                "baseline_u_high": base["u_high"],
                "candidate_unresolved": cand["unresolved"],
                "baseline_unresolved": base["unresolved"],
            }
        )
    return rows


def norm_table(table):
    return {
        "table_id": table["table_id"],
        "seed": table["seed"],
        "participants_by_seat": table["stage_situation"]["participant_ids_by_seat"],
    }


def main() -> None:
    manifest = p28.verify_manifest()
    result = json.loads((p28.OUT / "result.json").read_text(encoding="utf-8"))

    schedule_mismatches = []
    identity_by_arm = defaultdict(Counter)
    window_totals = defaultdict(Counter)
    stage_elapsed = defaultdict(list)
    for source_row in p28.sources():
        source_id = str(source_row["source_id"])
        per_arm = {}
        for arm in manifest["arms"]:
            row = json.loads(p28._stage_path(arm, source_row).read_text(encoding="utf-8"))
            stage_row = row["stage"]
            per_arm[arm] = stage_row
            stage_elapsed[arm].append(float(stage_row["elapsed_ms"]))
            for item in stage_row.get("focal_policy_ids_by_table") or ():
                identity_by_arm[arm][str(item["policy_id"])] += 1
            if stage_row.get("p28_live"):
                live = stage_row["p28_live"]
                window_totals[arm]["eligible_draw_windows"] += live["eligible_draw_windows"]
                window_totals[arm]["provider_failures"] += live["provider_failures"]
                window_totals[arm]["incomplete_reductions"] += live["incomplete_reductions"]
                window_totals[arm]["changed_discard_orders"] += live["changed_discard_orders"]
                window_totals[arm]["t_analysis_samples"] += len(live["t_analysis_ms"])
            if stage_row.get("p28_windows"):
                windows = stage_row["p28_windows"]
                window_totals[arm]["focal_decisions"] += windows["focal_decisions"]
                window_totals[arm]["draw_windows"] += windows["draw_windows"]
                window_totals[arm]["response_windows"] += windows[
                    "response_windows_exact_fallback"
                ]
        reference = [norm_table(item) for item in per_arm["baseline"]["tables"]]
        for arm in manifest["arms"]:
            if arm == "baseline":
                continue
            other = [norm_table(item) for item in per_arm[arm]["tables"]]
            if other != reference:
                schedule_mismatches.append(
                    {"source_id": source_id, "arm": arm, "detail": "排程/牌山不逐字相同"}
                )

    baseline_id = manifest["baseline"]["strategy"]
    expected_by_arm = {
        "baseline": {p28.BASELINE_POLICY_ID},
        "reference:v2": {"ComparableHeuristicPolicyV2"},
        "candidate:A": {
            "r17-public-successor:" + manifest["candidates"]["A"]["identity"][:12]
        },
        "candidate:B": {
            "r17-public-successor:" + manifest["candidates"]["B"]["identity"][:12]
        },
    }
    identity_ok = {
        arm: set(identity_by_arm[arm]) == expected
        for arm, expected in expected_by_arm.items()
    }

    candidate_source_freeze = {
        candidate_id: {
            "path": item["path"],
            "manifest_sha256": item["sha256"],
            "current_sha256": p28.digest(Path(item["path"])),
            "unchanged_after_batch": p28.digest(Path(item["path"])) == item["sha256"],
        }
        for candidate_id, item in manifest["candidates"].items()
    }

    # analyze 里的参考臂分支因字典键类型写错而为 null（键是 (arm, source) 元组，
    # 不是字符串）。主脚本在 prepare 时已进冻结清单，**不改主脚本**；参考臂在这里
    # 独立复算，写进 verification.json。这不影响任何判定口径。
    reference_rows = paired_rows("reference:v2")
    reference = {
        "arm": "reference:v2",
        "note": "旧基线（稳定 V2）减 R18 v2（ref.u_low - base.u_high）；不参与预登记判定",
        "overall": {
            "u_delta_low_mean": sum(r["u_delta_low"] for r in reference_rows) / len(reference_rows),
            "stage_score_delta_mean": (
                sum(r["stage_score_delta"] for r in reference_rows) / len(reference_rows)
            ),
            "positive_units": sum(1 for r in reference_rows if r["u_delta_low"] > 0),
            "negative_units": sum(1 for r in reference_rows if r["u_delta_low"] < 0),
        },
        "by_mix": {},
        "sign_test_u": sign_test(reference_rows, "u_delta_low"),
        "sign_test_stage_score": sign_test(reference_rows, "stage_score_delta"),
        "recomputed_by": Path(__file__).name,
    }
    for mix in p28.MIXES:
        subset = [r for r in reference_rows if r["mix"] == mix]
        reference["by_mix"][mix] = {
            "u_delta_low_mean": sum(r["u_delta_low"] for r in subset) / len(subset),
            "stage_score_delta_mean": (
                sum(r["stage_score_delta"] for r in subset) / len(subset)
            ),
        }

    candidate_diagnostics = {}
    for arm, label in (("candidate:A", "A"), ("candidate:B", "B")):
        rows = paired_rows(arm)
        candidate_diagnostics[label] = {
            "sign_test_u": sign_test(rows, "u_delta_low"),
            "sign_test_stage_score": sign_test(rows, "stage_score_delta"),
            "units_with_u_interval": [
                {
                    "source_id": row["source_id"],
                    "candidate_u": [row["candidate_u_low"], row["candidate_u_high"]],
                    "baseline_u": [row["baseline_u_low"], row["baseline_u_high"]],
                }
                for row in rows
                if row["candidate_u_low"] != row["candidate_u_high"]
            ],
            "stage_score_delta_quantiles": p28.quantiles(
                [float(row["stage_score_delta"]) for row in rows]
            ),
        }

    # 审计口径说明：候选臂的「歧义诊断」是 rebase 产物，不是执行失败。
    audit = result["simulation_execution_audit"]
    candidate_focal_decisions = sum(
        result["candidates"][arm]["window_counts"]["focal_decisions"]
        for arm in result["candidates"]
    )
    audit_classification = {
        "ambiguous_diagnostics": audit["recorded_counts"]["ambiguous_diagnostics"],
        "candidate_focal_decisions_sum": candidate_focal_decisions,
        "equal": (
            audit["recorded_counts"]["ambiguous_diagnostics"] == candidate_focal_decisions
        ),
        "action_value_failed": audit["recorded_counts"]["action_value_failed"],
        "failure_kinds": audit["recorded_failure_kinds"],
        "explanation": (
            "候选焦点策略 id 是 r17-public-successor:<identity12>，不在 "
            "sitin_execution_audit.SCORING_POLICY_PREFIXES 白名单内；而 rebase 后它"
            "包住的基线是 ActionValue（R18 v2），其计划带 action_value 评分完成说明，"
            "于是被判为 (scored and not is_scoring) => ambiguous。失败种类全 0、"
            "action_value_failed=0，因此这不是执行失败，是审计分类口径的产物。"
            "原 R17 批次基线是 V2（非 ActionValue），故当时为 0。"
        ),
    }

    cost = {}
    for arm in manifest["arms"]:
        rows = [
            json.loads(p28._stage_path(arm, source_row).read_text(encoding="utf-8"))["stage"]
            for source_row in p28.sources()
        ]
        cost[arm] = p28.collect_live(rows)

    report = {
        "schema": "p28-r17-vs-r18v2-verification/1",
        "manifest_sha256": p28.digest(p28.OUT / "manifest.json"),
        "result_sha256": p28.digest(p28.OUT / "result.json"),
        "runtime_identity_verified": True,
        "baseline_strategy_expected": baseline_id,
        "focal_policy_identity_by_arm": {
            arm: dict(counter) for arm, counter in identity_by_arm.items()
        },
        "focal_policy_identity_matches_expected": identity_ok,
        "schedule_mismatch_count": len(schedule_mismatches),
        "schedule_mismatches": schedule_mismatches[:5],
        "candidate_source_freeze": candidate_source_freeze,
        "window_bookkeeping": {arm: dict(counter) for arm, counter in window_totals.items()},
        "stage_elapsed_ms": {
            arm: {
                "stages": len(values),
                "mean_ms": round(sum(values) / len(values), 1),
                "max_ms": round(max(values), 1),
            }
            for arm, values in stage_elapsed.items()
        },
        "live_cost_and_counts": cost,
        "reference_arm_recomputed": reference,
        "candidate_diagnostics": candidate_diagnostics,
        "audit_classification_note": audit_classification,
        "sign_frame": result["sign_frame"],
    }
    probe_row = {"mix": "H", "root_index": 1, "focal_seat": 0, "source_id": "H:r01:s0"}
    report["phase_split_choose_cost"] = {
        arm: phase_split_choose_cost(arm, probe_row)
        for arm in ("baseline", "candidate:A", "candidate:B")
    }

    report["all_checks_pass"] = (
        not schedule_mismatches
        and all(identity_ok.values())
        and all(item["unchanged_after_batch"] for item in candidate_source_freeze.values())
    )
    p28.write_json(p28.OUT / "verification.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2)[:6000])


if __name__ == "__main__":
    main()
