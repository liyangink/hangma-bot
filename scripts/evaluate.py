"""评估线命令行入口：decisions / matches / summarize 三个子命令。

职责边界（scripts/AGENTS.md）：本脚本只做参数解析、实验配置读取与显式
装配，业务逻辑全部在 hangma_bot.offline.*；不实现规则、HTTP、策略或
生命周期。Token 不出现在本脚本任何路径或输出中。

装配优先级：
- 组合根（bootstrap.py）提供 build_evaluation_runtime(kind, experiment)
  与 build_decision_codec() 时优先使用（主审集成项，见
  doc/implementation/handoffs/evaluation.md）；
- 缺失时 decisions 模式退回本脚本内的显式装配（只覆盖第一阶段两个
  真实策略：weighted_heuristic / safe_fallback）；
- matches 模式需要模拟线交付 SimulationEngine 与 MatchSpec 后才能运行
  （E3），组合根钩子缺失时给出明确错误而不是伪造引擎。

命令：
  python scripts/evaluate.py decisions DATASET --experiment EXP --out DIR
  python scripts/evaluate.py matches --experiment EXP --out DIR
  python scripts/evaluate.py summarize RESULTS_JSONL --out DIR [--baseline ID --challenger ID]
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Tuple

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from hangma_bot.application.deadline import BudgetPolicy, ManualClock  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.offline.evaluate import (  # noqa: E402
    BOOTSTRAP_CODEC_HOOK,
    BOOTSTRAP_RUNTIME_HOOK,
    DecisionExperiment,
    MatchExperiment,
    PolicyDeclaration,
    build_decision_report,
    load_experiment,
    run_decisions_comparison,
    run_match_experiment,
    write_decision_rows,
    write_report_files,
)
from hangma_bot.offline.evaluation_results import (  # noqa: E402
    SIMULATION_SOURCE_NAMESPACE,
    EvaluationManifest,
    ManifestInput,
    compute_rules_hash,
    new_evaluation_manifest,
    read_results_jsonl,
    write_manifest,
    write_results_jsonl,
)
from hangma_bot.offline.evaluation_statistics import summarize_results  # noqa: E402
from hangma_bot.policy.safe_fallback import SafeFallbackPolicy  # noqa: E402
from hangma_bot.policy.weighted_heuristic import WeightedHeuristicPolicy  # noqa: E402
from hangma_bot.policy.weights import HeuristicWeights  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# 显式装配（组合根钩子缺失时的最小回退；不建注册表）
# ---------------------------------------------------------------------------


def build_policy(declaration: PolicyDeclaration, monotonic: Callable[[], float]) -> Any:
    """按声明装配第一阶段两个真实策略；未知名称立即失败。"""
    if declaration.name == "weighted_heuristic":
        weights = HeuristicWeights(**dict(declaration.weights))
        policy = WeightedHeuristicPolicy(weights=weights, monotonic=monotonic)
        policy.policy_id = declaration.policy_id  # 诊断标识，不进评分
        return policy
    if declaration.name == "safe_fallback":
        policy = SafeFallbackPolicy()
        policy.policy_id = declaration.policy_id
        return policy
    raise ValueError(
        "未知策略名 {0!r}；本脚本只装配 weighted_heuristic / safe_fallback".format(
            declaration.name
        )
    )


def _clock_callables(clock_mode: str) -> Tuple[Callable[[], float], Optional[Callable[[], float]]]:
    """按 clock_mode 返回 (now_monotonic, wall_clock)。"""
    if clock_mode == "logical":
        clock = ManualClock(start_monotonic=800.0, wait_scale=1.0)
        return clock.now, None
    return time.monotonic, time.monotonic


def _bootstrap_runtime(kind: str, experiment: Any) -> Optional[Mapping]:
    """组合根钩子：优先使用主审装配的运行时；缺失返回 None。"""
    try:
        from hangma_bot import bootstrap
    except ImportError:
        return None
    builder = getattr(bootstrap, BOOTSTRAP_RUNTIME_HOOK, None)
    if builder is None:
        return None
    runtime = builder(kind, experiment)
    if runtime is None:
        return None
    if isinstance(runtime, Mapping):
        return runtime
    raise TypeError(
        "组合根 {0} 必须返回 dict 或 None，得到 {1!r}".format(BOOTSTRAP_RUNTIME_HOOK, type(runtime))
    )


def _bootstrap_decision_codec() -> Optional[Mapping]:
    """组合根钩子：审计 codec 的解码入口（C1 集成后可用）。"""
    try:
        from hangma_bot import bootstrap
    except ImportError:
        return None
    builder = getattr(bootstrap, BOOTSTRAP_CODEC_HOOK, None)
    if builder is None:
        return None
    codec = builder()
    if codec is None:
        return None
    if isinstance(codec, Mapping):
        return codec
    return {"decode_request": codec.decode_request, "decode_budget": codec.decode_budget}


def _git_state() -> Tuple[Optional[str], Optional[bool]]:
    """取 producer_commit 与 dirty；取不到时为空（不冒充已提交代码）。"""
    try:
        commit = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        commit = ""
    try:
        status = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
        dirty = bool(status.strip())
    except (OSError, subprocess.TimeoutExpired):
        dirty = None
    return (commit or None), dirty


def _manifest_versions(
    *,
    experiment: Any,
    baseline: PolicyDeclaration,
    challenger: PolicyDeclaration,
    opponents: Tuple[PolicyDeclaration, ...] = (),
) -> list:
    versions = {
        "experiment_kind": experiment.kind,
        "clock_mode": experiment.clock_mode,
        "scoring_policies": {
            "baseline": baseline.to_json(),
            "challenger": challenger.to_json(),
            "opponent_pool": [item.to_json() for item in opponents],
        },
    }
    if isinstance(experiment, DecisionExperiment):
        versions["decision_mode"] = experiment.decision_mode
        if experiment.rules_config is not None:
            versions["rules_config"] = {
                "ruleset_version": experiment.rules_config.ruleset_version,
                "base_score": experiment.rules_config.base_score,
                "you_cai_bi_kao": experiment.rules_config.you_cai_bi_kao,
            }
    else:
        versions["seeds"] = [
            {"seed": item.seed, "scenario_id": item.scenario_id} for item in experiment.seeds
        ]
        versions["seat_permutations"] = [list(item) for item in experiment.seat_permutations]
        versions["primary_metric"] = experiment.primary_metric
        versions["tie_method"] = experiment.tie_method
        versions["n_resamples"] = experiment.n_resamples
        versions["resample_seed"] = experiment.resample_seed
        versions["simulation_version"] = experiment.simulation_version
    return versions


def _build_manifest(
    *,
    experiment: Any,
    inputs: Tuple[ManifestInput, ...],
    versions: Mapping,
) -> EvaluationManifest:
    commit, dirty = _git_state()
    if isinstance(experiment, DecisionExperiment):
        source_namespace = experiment.source_namespace
        config = experiment.tournament_config
    else:
        source_namespace = experiment.source_namespace or SIMULATION_SOURCE_NAMESPACE
        config = experiment.tournament_config
    # 契约 §4.2：未知指南/配置/代码 hash 等字段允许为 null，但必须进入
    # missing_fields 说明，不能静默写 null。guide_version/guide_captured_at
    # 当前无来源；config 在 decisions 实验可未声明；producer_commit/dirty
    # 在 git 不可用时为空。
    missing: list = []
    if experiment.input_sha256 is None:
        missing.append("input_sha256")
    for field_name, value in (
        ("guide_version", None),
        ("guide_captured_at", None),
        ("config", config),
        ("producer_commit", commit),
        ("dirty", dirty),
    ):
        if value is None:
            missing.append(field_name)
    return new_evaluation_manifest(
        source_namespace=source_namespace,
        producer_commit=commit,
        dirty=dirty,
        inputs=inputs,
        rules_hash=compute_rules_hash(_REPO_ROOT),
        guide_version=None,
        guide_captured_at=None,
        config=config,
        missing_fields=tuple(missing),
        versions=tuple(sorted(versions.items())),
    )


# ---------------------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------------------


def cmd_decisions(args: argparse.Namespace) -> int:
    dataset = Path(args.dataset)
    out_dir = Path(args.out)
    experiment = load_experiment(Path(args.experiment))
    if not isinstance(experiment, DecisionExperiment):
        raise SystemExit("decisions 子命令要求 kind=decisions 的实验配置")
    if experiment.input_sha256 is not None:
        decisions_path = dataset / "decisions.jsonl"
        import hashlib

        actual = hashlib.sha256(decisions_path.read_bytes()).hexdigest()
        if actual != experiment.input_sha256:
            raise SystemExit(
                "input_sha256 不一致：声明 {0}，实际 {1}".format(experiment.input_sha256, actual)
            )

    now_monotonic, wall_clock = _clock_callables(experiment.clock_mode)
    runtime = _bootstrap_runtime("decisions", experiment)
    if runtime is not None:
        baseline_policy = runtime["baseline_policy"]
        challenger_policy = runtime["challenger_policy"]
    else:
        baseline_policy = build_policy(experiment.baseline, now_monotonic)
        challenger_policy = build_policy(experiment.challenger, now_monotonic)

    codec = _bootstrap_decision_codec()
    if codec is None:
        raise SystemExit(
            "决策行解码需要审计 codec（C1 交付）：组合根未提供 build_decision_codec()；"
            "当前版本不能把测试 fixture 当生产解码器。见 doc/implementation/handoffs/evaluation.md"
        )
    decode_request = codec["decode_request"]
    decode_budget = codec["decode_budget"]

    recompute_rules = None
    if experiment.decision_mode == "recomputed_rules":
        recompute_rules = HangmaRules(experiment.rules_config)

    outcome = asyncio.run(
        run_decisions_comparison(
            dataset,
            experiment,
            baseline_policy=baseline_policy,
            challenger_policy=challenger_policy,
            decode_request=decode_request,
            decode_budget=decode_budget,
            recompute_rules=recompute_rules,
            now_monotonic=now_monotonic,
            wall_clock=wall_clock,
        )
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    write_decision_rows(out_dir / "decisions.jsonl", outcome.rows)
    report = build_decision_report(outcome, experiment)
    write_report_files(out_dir, report)
    decisions_input = dataset / "decisions.jsonl"
    manifest = _build_manifest(
        experiment=experiment,
        inputs=(
            ManifestInput(
                path=decisions_input.name,
                sha256=outcome.input_sha256 or _sha256_of(decisions_input),
            ),
        ),
        versions=_manifest_versions(
            experiment=experiment,
            baseline=experiment.baseline,
            challenger=experiment.challenger,
        ),
    )
    write_manifest(out_dir / "manifest.json", manifest)
    print(
        "decisions 完成：比较 {0} 行，排除 {1} 行；产物目录 {2}".format(
            len(outcome.rows), len(outcome.excluded), out_dir
        )
    )
    return 0


def _sha256_of(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def cmd_matches(args: argparse.Namespace) -> int:
    out_dir = Path(args.out)
    experiment = load_experiment(Path(args.experiment))
    if not isinstance(experiment, MatchExperiment):
        raise SystemExit("matches 子命令要求 kind=matches 的实验配置")

    runtime = _bootstrap_runtime("matches", experiment)
    if runtime is None:
        raise SystemExit(
            "matches 需要模拟线交付 SimulationEngine/MatchSpec 并由组合根装配"
            "（build_evaluation_runtime，E3）；当前契约基线（C0）不伪造引擎。"
            "见 doc/implementation/handoffs/evaluation.md"
        )
    engine = runtime["engine"]
    spec_factory = runtime["spec_factory"]
    choice_factory = runtime["choice_factory"]

    now_monotonic, wall_clock = _clock_callables(experiment.clock_mode)
    if "policies_by_id" in runtime:
        policies_by_id = runtime["policies_by_id"]
    else:
        policies_by_id = {}
        for declaration in (
            (experiment.baseline, experiment.challenger)
            + experiment.opponents
        ):
            policies_by_id[declaration.policy_id] = build_policy(declaration, now_monotonic)

    rules = HangmaRules(experiment.tournament_config.rules)
    outcome = asyncio.run(
        run_match_experiment(
            experiment,
            engine=engine,
            spec_factory=spec_factory,
            choice_factory=choice_factory,
            policies_by_id=policies_by_id,
            rules=rules,
            rules_hash=compute_rules_hash(_REPO_ROOT),
            now_monotonic=now_monotonic,
            wall_clock=wall_clock,
            budget_policy=BudgetPolicy(),
        )
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    write_results_jsonl(out_dir / "results.jsonl", list(outcome.results))
    report = summarize_results(
        outcome.results,
        baseline_policy_id=experiment.baseline.policy_id,
        challenger_policy_id=experiment.challenger.policy_id,
        primary_metric=experiment.primary_metric,
        tie_method=experiment.tie_method,
        n_resamples=experiment.n_resamples,
        resample_seed=experiment.resample_seed,
    )
    if outcome.excluded:
        report["sections"].append(
            {"heading": "运行排除明细", "paragraphs": list(outcome.excluded)}
        )
    write_report_files(out_dir, report)
    manifest = _build_manifest(
        experiment=experiment,
        inputs=(),
        versions=_manifest_versions(
            experiment=experiment,
            baseline=experiment.baseline,
            challenger=experiment.challenger,
            opponents=experiment.opponents,
        ),
    )
    write_manifest(out_dir / "manifest.json", manifest)
    print(
        "matches 完成：结果 {0} 行，运行排除 {1} 项；产物目录 {2}".format(
            len(outcome.results), len(outcome.excluded), out_dir
        )
    )
    return 0


def cmd_summarize(args: argparse.Namespace) -> int:
    out_dir = Path(args.out)
    results = read_results_jsonl(Path(args.results_jsonl))
    report = summarize_results(
        results,
        baseline_policy_id=args.baseline,
        challenger_policy_id=args.challenger,
        primary_metric=args.metric,
        tie_method=args.tie_method,
        n_resamples=args.n_resamples,
        resample_seed=args.seed,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    write_report_files(out_dir, report)
    print(
        "summarize 完成：输入 {0} 行；产物目录 {1}".format(len(results), out_dir)
    )
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evaluate.py",
        description="评估线入口：固定决策比较 / 完整桌赛驱动 / 结果汇总",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    decisions = subparsers.add_parser("decisions", help="固定决策集比较")
    decisions.add_argument("dataset", help="统一牌谱目录（含 decisions.jsonl）")
    decisions.add_argument("--experiment", required=True, help="EXPERIMENT_JSON 路径")
    decisions.add_argument("--out", required=True, help="产物目录")
    decisions.set_defaults(func=cmd_decisions)

    matches = subparsers.add_parser("matches", help="完整桌赛复式实验（E3，需模拟线）")
    matches.add_argument("--experiment", required=True, help="EXPERIMENT_JSON 路径")
    matches.add_argument("--out", required=True, help="产物目录")
    matches.set_defaults(func=cmd_matches)

    summarize = subparsers.add_parser("summarize", help="汇总 results.jsonl")
    summarize.add_argument("results_jsonl", help="results.jsonl 路径")
    summarize.add_argument("--out", required=True, help="产物目录")
    summarize.add_argument("--baseline", default=None, help="稳定版本 policy_id")
    summarize.add_argument("--challenger", default=None, help="候选版本 policy_id")
    summarize.add_argument("--metric", default="table_score_delta", help="主指标")
    summarize.add_argument("--tie-method", default="strict", choices=("strict", "inclusive"))
    summarize.add_argument("--n-resamples", type=int, default=10000)
    summarize.add_argument("--seed", type=int, default=0)
    summarize.set_defaults(func=cmd_summarize)
    return parser


def main(argv: Optional[list] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
