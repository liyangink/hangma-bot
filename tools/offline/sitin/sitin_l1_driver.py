"""坐隐 1.7：出树驱动——把影子诊断接进完整桌赛，**零生产代码改动**。

为什么"出树"：`cmd_matches` 只在运行时含 `policies_by_id` 时才用外部策略，
而组合根不返回它，于是回退到只认 5 个注册名的 `build_policy`
（[SEAM-INVESTIGATION](../../evidence/1.7-diagnostics/SEAM-INVESTIGATION.md) §2.3）。
M4 是 review 下的非包模块，**不能**让生产评估脚本反向依赖它
（`AGENTS.md` §5 模块边界），因此改为在本脚本里显式装配策略对象，
复用公开形参 `run_match_experiment(policies_by_id=...)`。

**装配方式**（两臂各装一个影子包装器，行内同请求对照）：

    基线臂  driver=weighted_heuristic_v2   shadow=M4
    候选臂  driver=M4                      shadow=weighted_heuristic_v2

这样每一臂都产出"同一 request 的两套完整计划"，跨臂只在聚合层比较。

用法：

    .venv/bin/python review/llm-guided-heuristic-route-2026-09-15/tools/sitin_l1_driver.py \
        --experiment EXP.json --out runs/<实验>/L1-<β>/out --beta 20

产物：`results.jsonl`（与 CLI 同格式）、`diagnostics.jsonl`（逐窗口诊断）、
`diagnostic-summary.json`（漏斗聚合）、`diagnostics-manifest.json`（口径与指纹）。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/tools'

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
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

REPO = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, REPO / "src")))
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

from hangma_bot.application.deadline import BudgetPolicy  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.offline.evaluate import (  # noqa: E402
    BOOTSTRAP_RUNTIME_HOOK,
    MatchExperiment,
    load_experiment,
    run_match_experiment,
)
from hangma_bot.offline.evaluation_results import (  # noqa: E402
    compute_rules_hash,
    write_results_jsonl,
)
from hangma_bot.offline.evaluation_statistics import summarize_results  # noqa: E402
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2  # noqa: E402
from hangma_bot.policy.weights_v1 import DEFAULT_WEIGHTS_V1  # noqa: E402

import sitin_diagnostics as diag  # noqa: E402
import sitin_m4_policy as m4mod  # noqa: E402


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _project_file(_PROJECT_ROOT, _HERE / (name + ".py")))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


recompute = _load("sitin_m4_recompute")


def _runtime_for(experiment: Any) -> Mapping[str, Any]:
    """复用组合根装配的引擎与工厂；缺失时明确失败，不伪造引擎。"""

    from hangma_bot import bootstrap

    builder = getattr(bootstrap, BOOTSTRAP_RUNTIME_HOOK, None)
    runtime = builder("matches", experiment) if builder is not None else None
    if not isinstance(runtime, Mapping):
        raise SystemExit(
            "无法取得 matches 运行时（build_evaluation_runtime 未装配）；"
            "本驱动不伪造 SimulationEngine")
    return runtime


def build(experiment: MatchExperiment, *, beta: float, include_reasons: bool) -> Dict[str, Any]:
    """装配策略、包装器与 sink；返回传给 `run_match_experiment` 的实参。"""

    runtime = _runtime_for(experiment)
    now_monotonic = runtime.get("now_monotonic")
    if now_monotonic is None:
        import time
        now_monotonic = time.monotonic
    wall_clock = None  # logical 时钟下不需要墙钟；诊断不使用耗时结论

    baseline_id = experiment.baseline.policy_id
    challenger_id = experiment.challenger.policy_id

    params = m4mod.M4Params(beta=beta)
    m4_policy = m4mod.M4OpportunityCostPolicy(monotonic=now_monotonic, params=params)
    baseline_policy = ComparableHeuristicPolicyV2(monotonic=now_monotonic)

    seed_by_scenario = {spec.scenario_id: spec.seed for spec in experiment.seeds}
    rule_config = experiment.tournament_config.rules
    common = dict(
        baseline_identity="weighted_heuristic_v2",
        candidate_identity=m4_policy.candidate_identity(),
        ruleset_version=rule_config.ruleset_version,
        rule_config={"ruleset_version": rule_config.ruleset_version,
                     "base_score": rule_config.base_score,
                     "you_cai_bi_kao": rule_config.you_cai_bi_kao},
        rules_hash=compute_rules_hash(REPO),
        source_fingerprints=recompute.source_fingerprints(),
        seed_by_scenario=seed_by_scenario,
        funnel=diag.m4_funnel,
        natural_of=m4mod.natural_draw_value,
        include_reasons=include_reasons,
    )
    return {
        "runtime": runtime,
        "baseline_id": baseline_id,
        "challenger_id": challenger_id,
        "baseline_policy": baseline_policy,
        "m4_policy": m4_policy,
        "params": params,
        "common": common,
        "now_monotonic": now_monotonic,
        "wall_clock": wall_clock,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="坐隐 1.7 出树诊断驱动")
    ap.add_argument("--experiment", required=True, help="matches 实验配置 JSON")
    ap.add_argument("--out", required=True, help="产物目录")
    ap.add_argument("--beta", type=float, default=20.0, help="M4 候选参数 β")
    ap.add_argument("--no-reasons", action="store_true",
                    help="记录中省略逐候选 reasons（体积更小）")
    args = ap.parse_args(argv)

    experiment = load_experiment(Path(args.experiment))
    if not isinstance(experiment, MatchExperiment):
        raise SystemExit("本驱动要求 kind=matches 的实验配置")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    wiring = build(experiment, beta=args.beta, include_reasons=not args.no_reasons)

    sink = diag.DiagnosticSink(out_dir / "diagnostics.jsonl",
                              include_reasons=not args.no_reasons)
    baseline_wrapped = diag.ShadowPolicy(
        driver=wiring["baseline_policy"], shadow=wiring["m4_policy"], sink=sink,
        arm_role="baseline", driver_identity="weighted_heuristic_v2",
        shadow_identity=wiring["m4_policy"].candidate_identity(), **wiring["common"])
    candidate_wrapped = diag.ShadowPolicy(
        driver=wiring["m4_policy"], shadow=wiring["baseline_policy"], sink=sink,
        arm_role="challenger", driver_identity=wiring["m4_policy"].candidate_identity(),
        shadow_identity="weighted_heuristic_v2", **wiring["common"])

    policies_by_id: Dict[str, Any] = {
        wiring["baseline_id"]: baseline_wrapped,
        wiring["challenger_id"]: candidate_wrapped,
    }
    for opponent in experiment.opponents:
        policies_by_id[opponent.policy_id] = ComparableHeuristicPolicyV2(
            monotonic=wiring["now_monotonic"])

    rules = HangmaRules(experiment.tournament_config.rules)
    try:
        outcome = asyncio.run(run_match_experiment(
            experiment,
            engine=wiring["runtime"]["engine"],
            spec_factory=wiring["runtime"]["spec_factory"],
            choice_factory=wiring["runtime"]["choice_factory"],
            policies_by_id=policies_by_id,
            rules=rules,
            rules_hash=compute_rules_hash(REPO),
            now_monotonic=wiring["now_monotonic"],
            wall_clock=wiring["wall_clock"],
            budget_policy=BudgetPolicy(),
        ))
    finally:
        sink.close()

    write_results_jsonl(out_dir / "results.jsonl", list(outcome.results))
    report = summarize_results(
        outcome.results,
        baseline_policy_id=wiring["baseline_id"],
        challenger_policy_id=wiring["challenger_id"],
        primary_metric=experiment.primary_metric,
        tie_method=experiment.tie_method,
        n_resamples=experiment.n_resamples,
        resample_seed=experiment.resample_seed,
    )
    if outcome.excluded:
        report["sections"].append(
            {"heading": "运行排除明细", "paragraphs": list(outcome.excluded)})
    (out_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "schema": diag.DIAGNOSTIC_SCHEMA,
        "diagnostics": {"records": sink.count, "shadow_errors": sink.error_count,
                        "triggered": sink.triggered_count,
                        "file": "diagnostics.jsonl"},
        "funnel": dict(sink.stage_counts),
        "arms": {"baseline_policy_id": wiring["baseline_id"],
                 "challenger_policy_id": wiring["challenger_id"],
                 "baseline_identity": "weighted_heuristic_v2",
                 "candidate_identity": wiring["m4_policy"].candidate_identity()},
        "candidate_params": wiring["params"].to_json(),
        "candidate_effective_tile_multiplier": round(
            wiring["params"].effective_tile_multiplier(DEFAULT_WEIGHTS_V1.effective_tile), 4),
        "observation_digest_fields": list(diag.OBSERVATION_DIGEST_FIELDS),
        "source_fingerprints": recompute.source_fingerprints(),
        "results_rows": len(outcome.results),
        "excluded": list(outcome.excluded),
    }
    (out_dir / "diagnostic-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary["diagnostics"], ensure_ascii=False))
    print("漏斗:", json.dumps(summary["funnel"], ensure_ascii=False))
    print("桌赛结果 {0} 行；产物目录 {1}".format(len(outcome.results), out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
