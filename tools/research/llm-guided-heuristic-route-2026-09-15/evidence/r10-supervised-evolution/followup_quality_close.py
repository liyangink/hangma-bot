"""只读复核后继原型完整阶段结果并按预登记作开发裁定；不追加评测。"""

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
from statistics import mean, stdev

import followup_quality_panel as run

b = run.b
OUT = run.OUT


def close():
    """核对完整清单、双臂身份、逐窗审计和独立根均值；不是发布显著性确认。"""
    plan = b.read(OUT / "evaluation-plan.json")
    run.verify_inputs(plan)
    process = b.read(OUT / "effect-process.json")
    assert process["returncode"] == 0 and not process["timed_out"] and not process["group_still_alive"]
    assert not (OUT / "development-decision.json").exists()
    samples = b.read(OUT / "effect-samples.json")
    assert len(samples) == 64
    expected = {(mix, root, seat) for mix in ("H", "M") for root in range(1, 9) for seat in range(4)}
    assert {(s["opponent_mix"], s["root_index"], s["focal_anchor_seat"]) for s in samples} == expected
    contract = b.read(b.Path(plan["contract"]))
    prototype, runtime = Counter(), Counter()
    rows = []
    references = {mix: b.read(b.Path(ref["path"])) for mix, ref in plan["reference_panels"].items()}
    for sample in samples:
        mix, root, seat = sample["opponent_mix"], sample["root_index"], sample["focal_anchor_seat"]
        plans = run.natural.build_seat_stage_plans(contract=contract, opponent=mix, root_index=root,
            focal_seat=seat, panel_seed=plan["panel_seed"])
        reference = next(s for s in references[mix]["samples"] if s["root_index"] == root and s["focal_anchor_seat"] == seat)
        assert sample["root_content_digest"] == reference["root_content_digest"]
        assert sample["table_ids"] == [p.table_id for p in plans] and sample["table_seeds"] == [p.seed for p in plans]
        assert sample["candidate_id"] == plan["candidate_id"]
        assert sample["raw_arms"]["baseline"] == reference["raw_arms"]["baseline"]
        for arm in ("baseline", "candidate"):
            raw = sample["raw_arms"][arm]
            checked = run.verify_stage(raw, plans, contract, plan, arm)
            assert all(raw[key] == sample["arms"][arm][key] for key in ("u", "u_low", "u_high", "focal_stage_score", "stage_totals_by_participant", "status", "usable", "error"))
            if arm == "candidate":
                prototype.update(checked["prototype_counts"])
                runtime.update(checked["runtime_counts"])
                rows.extend(r for t in raw["tables"] for r in t["prototype_audit"])
    statistics = run.natural.paired_stage_statistics(samples, min_roots=8)
    assert statistics == b.read(OUT / "effect-statistics.json")
    block = statistics["by_candidate"][plan["candidate_id"]]["panels"]["normal"]
    measures = {}
    for mix in ("H", "M"):
        group = block["panels"][mix]
        assert group["n_roots"] == 8 and group["manifest_complete"] and group["status"] == "ok"
        low, high = [], []
        for root in range(1, 9):
            root_samples = [s for s in samples if s["opponent_mix"] == mix and s["root_index"] == root]
            assert len(root_samples) == 4
            low.append(mean(s["arms"]["candidate"]["u_low"] - s["arms"]["baseline"]["u_high"] for s in root_samples))
            high.append(mean(s["arms"]["candidate"]["u_high"] - s["arms"]["baseline"]["u_low"] for s in root_samples))
        assert mean(low) == group["delta_bounds"]["mean_delta_low"]
        assert mean(high) == group["delta_bounds"]["mean_delta_high"]
        assert abs(stdev(low) / (8 ** 0.5) - group["delta_bounds"]["standard_error_low"]) < 1e-12
        measures[mix] = {"mean_delta": group["mean_delta"], "mean_delta_low": mean(low), "mean_delta_high": mean(high),
            "root_deltas_low": low, "root_deltas_high": high, "standard_error": group["standard_error"],
            "sampling_interval_95_normal_approx": group["interval_95"]}
    summary = b.read(OUT / "effect-summary.json")
    assert summary["prototype_decisions"] == len(rows)
    assert summary["first_changes"] == prototype["first_changed"]
    assert summary["runtime_counts"] == dict(runtime)
    statuses = Counter(r["status"] for r in rows)
    assert summary["prototype_statuses"] == dict(statuses)
    positive = all(m["mean_delta_low"] > 0 for m in measures.values())
    clean = not any(statuses[k] for k in ("ERROR_FALLBACK", "FACT_FALLBACK", "COST_FALLBACK"))
    reliable = not any(runtime[k] for k in ("illegal_choices", "fallbacks", "timeouts", "audit_missing", "auto_actions"))
    latency = sorted(r["elapsed_seconds"] for r in rows if r["status"] == "EVALUATED")
    def percentile(q):
        """实测增强调用的最近秩分位数，秒；不是最大并发全链预算。"""
        from math import ceil
        return latency[max(0, ceil(q * len(latency)) - 1)] if latency else None
    result = {"status": "CONTINUE_SECOND_SEEN_DEVELOPMENT" if positive and clean and reliable else "NOT_PROMOTED_AFTER_CORE",
        "candidate_id": plan["candidate_id"], "versus_v2": measures,
        "declared_mix": block["declared_mix"], "effect_condition_passed": positive,
        "clean_prototype_execution": clean, "driver_reliable_in_logical_time": reliable,
        "continue_second_seen_panel": positive and clean and reliable,
        "effect_signal_requires_execution_review": positive and not (clean and reliable),
        "prototype_counts": dict(prototype), "enhancement_timing_seconds": {
            "p50": percentile(0.5), "p95": percentile(0.95), "p99": percentile(0.99), "max": max(latency, default=None)},
        "full_candidate_tables_verified": 128, "full_reused_baseline_tables_verified": 128,
        "new_baseline_control_tables": 4, "new_full_tables": 132,
        "interpretation": "H/M各8来源根、根内4座位配置平均；识别界不等于抽样区间，已反复曝光核心不能用于发布显著性结论",
        "performance_interpretation": "增强时延为本机逻辑时钟模拟中的同步分析片段，不含完整生产链与最大并发；底层已使用C数学，后续提速需单独测量",
        "model_calls": 0, "confirmation_roots": 0, "release_eligible": False,
        "analysis_source_sha256": b.digest(b.Path(__file__).read_bytes()),
    }
    b.write(OUT / "development-decision.json", result)
    print(result)


if __name__ == "__main__":
    close()
