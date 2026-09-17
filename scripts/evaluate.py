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
from hangma_bot.offline.scoring_sources import (  # noqa: E402
    candidate_identity_digest,
    scoring_source_snapshot,
    write_code_snapshot,
)
from hangma_bot.policy import heuristics  # noqa: E402
from hangma_bot.policy.heuristic_adapter import HeuristicAdjustmentPolicy  # noqa: E402
from hangma_bot.policy.heuristic_v1 import ReliableHeuristicPolicyV1  # noqa: E402
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2  # noqa: E402
from hangma_bot.policy.white_discard_guard import WhiteDiscardGuardPolicy  # noqa: E402
from hangma_bot.policy.safe_fallback import SafeFallbackPolicy  # noqa: E402
from hangma_bot.policy.weights import HeuristicWeights  # noqa: E402
from hangma_bot.policy.weights_v1 import HeuristicWeightsV1  # noqa: E402
from hangma_bot.policy.legacy_pass import LegacyWeightedHeuristicPolicy  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# 显式装配（组合根钩子缺失时的最小回退；不建注册表）
# ---------------------------------------------------------------------------


def _candidate_source_fingerprint(name: str) -> str:
    """候选**执行依赖闭包**的 sha256 前 16 位（不是入口文件的指纹）。

    **在这里算而不是在 policy 包内**：policy 模块禁止任何文件副作用
    （`tests/unit/policy/test_policy_timeout_and_purity.py` 静态扫描
    `Path(` / `open(` / `read_text`）。指纹是**装载期的溯源信息**，
    装载方持有 IO 权限；契约测试比对声明与实际源码，防止漂移。

    **REVIEW-8 S8-1**：初版只对入口文件取哈希。候选之间会互相 import
    （`meld_waiting_conditional` 用 `meld_opportunity_cost.natural_draw_value`），
    只改被依赖的文件时身份不变，于是"在某份代码上过了门禁"可以被另一份代码沿用。
    现在与门禁侧 `candidate_identity` 共用同一个闭包摘要，两侧必然一致。
    """

    return candidate_identity_digest(name)


def _build_registered_candidate(
    declaration: PolicyDeclaration, monotonic: Callable[[], float]
) -> Optional[Any]:
    """尝试把声明装配成**已注册的候选启发式**；未注册返回 None。

    候选注册表在 `hangma_bot.policy.heuristics` 内（静态字面量，非插件系统）。
    这里只做一次委托，新增候选不需要修改本文件。
    """

    if not heuristics.is_candidate(declaration.name):
        return None
    candidate = heuristics.build_candidate(
        declaration.name,
        weights=dict(declaration.weights),
        monotonic=monotonic,
        source_fingerprint_value=_candidate_source_fingerprint(declaration.name),
    )
    candidate.policy_id = declaration.policy_id  # 诊断标识，不进评分
    return candidate


def build_policy(declaration: PolicyDeclaration, monotonic: Callable[[], float]) -> Any:
    """按声明装配第一阶段两个真实策略；未知名称立即失败。"""
    if declaration.name == "weighted_heuristic":
        weights = HeuristicWeights(**dict(declaration.weights))
        policy = LegacyWeightedHeuristicPolicy(weights=weights, monotonic=monotonic)
        policy.policy_id = declaration.policy_id  # 诊断标识，不进评分
        return policy
    if declaration.name == "safe_fallback":
        policy = SafeFallbackPolicy()
        policy.policy_id = declaration.policy_id
        return policy
    if declaration.name.startswith("action_value:"):
        # B3 可选注入：action_value:<seed> 经离线驱动工厂用受限执行器装载；
        # 不改变默认装配，cmd_matches 会为这类声明启用统一 value_limits。
        from hangma_bot.offline.evaluate import build_action_value_offline_policy

        policy = build_action_value_offline_policy(declaration.name.split(":", 1)[1])
        policy.policy_id = declaration.policy_id
        return policy
    if declaration.name in ("weighted_heuristic_v1", "weighted_heuristic_v2", "weighted_heuristic_v2_white_guard"):
        # 与 V0 使用同一实验时钟；逻辑预算不能与主机单调时钟比较。
        weights = HeuristicWeightsV1(**dict(declaration.weights))
        policy_type = ReliableHeuristicPolicyV1 if declaration.name == "weighted_heuristic_v1" else ComparableHeuristicPolicyV2
        policy = policy_type(weights=weights, monotonic=monotonic)
        if declaration.name == "weighted_heuristic_v2_white_guard":
            policy = WhiteDiscardGuardPolicy(policy)
        policy.policy_id = declaration.policy_id
        return policy
    # 候选启发式接缝（README §17 2.2）：注册表在 policy 包内，**新增候选不必再改本文件**。
    # 这是打通接缝的**唯一一次**生产改动；之后加候选只改 policy/heuristics/__init__.py 一行。
    # 候选模块是 hangma_bot 包成员，因此这里的 import 不破坏模块边界
    # （这正是候选放在 review/ 下做不到的一点）。
    policy = _build_registered_candidate(declaration, monotonic)
    if policy is not None:
        return policy
    raise ValueError(
        "未知策略名 {0!r}；本脚本只装配 weighted_heuristic / safe_fallback / "
        "weighted_heuristic_v1 / weighted_heuristic_v2 / weighted_heuristic_v2_white_guard，"
        "action_value:<seed>（B3 可选注入），"
        "以及 policy.heuristics 已注册的候选：{1}".format(
            declaration.name, ", ".join(heuristics.candidate_names()))
    )


def _value_limits_for_declarations(declarations) -> Optional[object]:
    """声明含 action_value 策略时返回统一分析配置；默认 None（旧行为零变化）。

    action_value 策略依赖 B1 载荷（followup_branches/family_progress/routes），
    与线上组合根同口径启用 ValueAnalysisLimits；其它策略保持 None。
    """
    from hangma_bot.hangma.interface import ValueAnalysisLimits

    if any(str(item.name).startswith("action_value:") for item in declarations):
        return ValueAnalysisLimits()
    return None


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


#: 装饰器链最大解包层数；防止自引用把快照函数变成死循环。
_MAX_POLICY_UNWRAP = 8

#: 脏工作区里最多记录多少条变更路径；超出只截断**列表**，不截断该布尔标志。
_DIRTY_PATHS_MAX = 200


def _unwrap_scoring_policy(policy: Any) -> Any:
    """剥掉只做重排/追加分项的装饰器，取到**持权重的内核**。

    为什么必须解包：V2 之后新增了两层装饰器（白板保护、候选适配器）。
    初版只认 `WhiteDiscardGuardPolicy`，于是候选适配器解不出来，
    manifest 写成 `effective_weights=null`；而 **null 与"该策略确实没有权重"
    在产物里长得一样**，事后无法区分（REVIEW-7 S7-2 实测）。

    用 `base_policy` **约定**而不是 isinstance 白名单：新增装饰器不必再改本函数。
    仓库内实现该约定的装饰器都把 `base_policy` 指向被包装策略
    （`white_discard_guard.py` / `catch_play_probe.py` / `heuristic_adapter.py`）。
    """

    current = policy
    for _ in range(_MAX_POLICY_UNWRAP):
        inner = getattr(current, "base_policy", None)
        if inner is None or inner is current:
            break
        current = inner
    return current


def _effective_weights_snapshot(policy: Any) -> Optional[dict]:
    """策略生效权重快照（类声明字段的当前值）；无权重参数的策略返回 None。

    声明权重为空时实际生效的是类默认权重，manifest 必须记录生效值
    才能事后复现（E3 诊断教训 2026-09-06）。
    """

    weights = getattr(_unwrap_scoring_policy(policy), "_weights", None)
    if weights is None:
        return None
    cls = type(weights)
    return {
        name: getattr(weights, name)
        for name, value in vars(cls).items()
        if not name.startswith("_") and not callable(value)
    }


def _source_digest(relative_path: str) -> Optional[dict]:
    """一份源码文件的字节指纹；文件不存在时返回 None（**不冒充已记录**）。"""

    import hashlib

    path = _REPO_ROOT / relative_path
    if not path.is_file():
        return None
    data = path.read_bytes()
    return {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


def _candidate_module_path(name: str) -> str:
    """已注册候选模块相对仓库根的路径；未注册由注册表抛错（不静默回退）。"""

    module = heuristics.candidate_module(name)
    return str(Path(module.__file__).resolve().relative_to(_REPO_ROOT))


def _scoring_source_snapshot(candidate_names: Tuple[str, ...]) -> dict:
    """本次比较依赖的评分源码 → 字节指纹（**import 依赖闭包**，不是固定清单）。

    这是 `dirty=true` 之外的**可验证指纹**：拿到产物的人可按"路径 → sha256"
    逐份复核当时实际装载的源码，即使那些源码从未提交。

    **REVIEW-8 S8-1**：初版是一份**硬编码文件清单**，它漏了正在使用的
    `evaluation_v2.py`，也不覆盖候选之间的相互 import。现在与门禁身份
    共用 `offline/scoring_sources.py` 的闭包实现——一处定义，三处引用
    （准入身份、实验清单、源码归档），不会再出现"清单各写一遍、各自漏项"。
    """

    return scoring_source_snapshot(tuple(candidate_names))


def _worktree_snapshot() -> dict:
    """工作区身份：提交号、是否脏、**脏在哪些路径**（REVIEW-7 S7-2）。

    与 `scoring_source` 的分工：这里回答"仓库整体是否与父提交一致"，
    `scoring_source` 回答"评分源码的字节是什么"。两者都落盘，
    既不依赖 `dirty=true` 这个布尔值，也不依赖父提交。
    """

    commit, dirty = _git_state()
    paths: list = []
    truncated = False
    try:
        status = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
        for line in status.splitlines():
            if line.strip():
                # porcelain 前两列是状态码，其后是路径。
                paths.append(line[3:].strip() if len(line) > 3 else line.strip())
    except (OSError, subprocess.SubprocessError):
        paths = []
        truncated = True
    if len(paths) > _DIRTY_PATHS_MAX:
        paths = paths[:_DIRTY_PATHS_MAX]
        truncated = True
    return {
        "commit": commit,
        "dirty": dirty,
        "dirty_paths": paths,
        "dirty_paths_truncated": truncated,
    }


def _write_code_snapshot(out_dir: Path, scoring_source: Mapping) -> Optional[str]:
    """把本次实际装载的评分源码落到产物目录，返回快照子目录名。

    REVIEW-7 S7-2 的处置是"保存实际代码快照**或**可验证指纹"；这里两件都做，
    因为用途不同：指纹用于**核对**，快照用于**在没有该提交的环境里重建**。
    代价有界——清单是**依赖闭包**（十几到几十个小文件），不是整仓快照。
    """

    return write_code_snapshot(out_dir, scoring_source)


def _candidate_names_in(declarations) -> Tuple[str, ...]:
    """声明序列里**已注册候选**的名字；其余策略名不进评分源码指纹清单。"""

    return tuple(item.name for item in declarations if heuristics.is_candidate(item.name))


def _policy_artifact_fields(declaration: PolicyDeclaration, policy: Any) -> dict:
    """manifest 里每个评分者一条的**候选身份字段**（REVIEW-7 S7-2）。

    初版只写 `effective_weights`，且候选适配器解包不出来 ⇒ 候选那条是 null。
    现在写四样：生效基础权重、生效调整参数、候选身份串、候选源码指纹。
    四者缺一，产物就回答不了"跑的是哪一份候选代码 + 哪一组参数"。
    """

    params, _base = heuristics.split_declaration_params(dict(declaration.weights))
    fields = {
        "effective_weights": _effective_weights_snapshot(policy),
        "effective_adjustment_params": params or None,
        "candidate_identity": None,
        "candidate_spec": None,
        "candidate_source": None,
    }
    if not isinstance(policy, HeuristicAdjustmentPolicy):
        return fields
    spec = policy.adjustment.spec
    relative_path = _candidate_module_path(declaration.name)
    fields["candidate_identity"] = policy.identity()
    fields["candidate_spec"] = {
        "name": spec.name,
        "version": spec.version,
        "trigger": spec.trigger,
        "scope": list(spec.scope),
        "bound": spec.bound,
    }
    # 依赖闭包摘要：与门禁 `bound_identity` 里的 src 段**同一个值**，
    # 两处产物因此可以互核（REVIEW-8 S8-1）。
    fields["dependency_digest"] = candidate_identity_digest(declaration.name)
    fields["candidate_source"] = dict(
        _source_digest(relative_path) or {}, path=relative_path)
    return fields


def _manifest_versions(
    *,
    experiment: Any,
    baseline: PolicyDeclaration,
    challenger: PolicyDeclaration,
    opponents: Tuple[PolicyDeclaration, ...] = (),
    policy_artifacts_by_id: Optional[Mapping] = None,
    scoring_source: Optional[Mapping] = None,
    worktree: Optional[Mapping] = None,
) -> list:
    """manifest 的 versions 段。

    `policy_artifacts_by_id` 取代初版的 `effective_weights_by_id`：每条评分者
    除生效权重外还要写候选身份、生效调整参数与候选源码指纹（REVIEW-7 S7-2）。
    `policy_id` 不在映射里时该条写 null——**与"算不出权重"用同一个可读形态**，
    并同时把缺项写进 `missing_fields`（由调用方核对）。
    """

    scoring_entries = {
        "baseline": baseline.to_json(),
        "challenger": challenger.to_json(),
        "opponent_pool": [item.to_json() for item in opponents],
    }
    artifacts = policy_artifacts_by_id or {}
    for entry in (
        [scoring_entries["baseline"], scoring_entries["challenger"]]
        + scoring_entries["opponent_pool"]
    ):
        fields = artifacts.get(entry["policy_id"])
        entry["effective_weights"] = (
            fields.get("effective_weights") if fields is not None else None
        )
        entry["effective_adjustment_params"] = (
            fields.get("effective_adjustment_params") if fields is not None else None
        )
        entry["candidate_identity"] = (
            fields.get("candidate_identity") if fields is not None else None
        )
        entry["candidate_spec"] = (
            fields.get("candidate_spec") if fields is not None else None
        )
        entry["candidate_source"] = (
            fields.get("candidate_source") if fields is not None else None
        )
        entry["dependency_digest"] = (
            fields.get("dependency_digest") if fields is not None else None
        )
    versions = {
        "experiment_kind": experiment.kind,
        "clock_mode": experiment.clock_mode,
        "scoring_policies": scoring_entries,
    }
    # 评分源码指纹与工作区身份（REVIEW-7 S7-2）：只写 dirty=true 说明不了差在哪。
    versions["scoring_source"] = dict(scoring_source or {})
    versions["worktree"] = dict(worktree or {})
    # 单独记录实际原生制品；规则源哈希不受 Python/C 装配选择影响。
    from hangma_bot.simulation.artifacts import hand_math_runtime_metadata
    versions["hand_math"] = hand_math_runtime_metadata()
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
    declarations = (experiment.baseline, experiment.challenger)
    scoring_source = _scoring_source_snapshot(_candidate_names_in(declarations))
    worktree = _worktree_snapshot()
    worktree["code_snapshot"] = _write_code_snapshot(out_dir, scoring_source)
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
            policy_artifacts_by_id={
                experiment.baseline.policy_id: _policy_artifact_fields(
                    experiment.baseline, baseline_policy),
                experiment.challenger.policy_id: _policy_artifact_fields(
                    experiment.challenger, challenger_policy),
            },
            scoring_source=scoring_source,
            worktree=worktree,
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
    declarations_all = (
        (experiment.baseline, experiment.challenger) + experiment.opponents
    )
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
            # T08 统一分析配置：action_value 声明启用，其余默认 None（零变化）。
            value_limits=_value_limits_for_declarations(declarations_all),
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
    declarations = declarations_all
    scoring_source = _scoring_source_snapshot(_candidate_names_in(declarations))
    worktree = _worktree_snapshot()
    worktree["code_snapshot"] = _write_code_snapshot(out_dir, scoring_source)
    manifest = _build_manifest(
        experiment=experiment,
        inputs=(),
        versions=_manifest_versions(
            experiment=experiment,
            baseline=experiment.baseline,
            challenger=experiment.challenger,
            opponents=experiment.opponents,
            policy_artifacts_by_id={
                declaration.policy_id: _policy_artifact_fields(
                    declaration, policies_by_id[declaration.policy_id])
                for declaration in declarations
                if declaration.policy_id in policies_by_id
            },
            scoring_source=scoring_source,
            worktree=worktree,
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
