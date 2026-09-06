"""固定决策集比较与完整桌赛驱动（评估线 parallel-v1）。

两个实验能力（evaluation-start §2-§3）：
1. 固定决策集比较：读统一牌谱 decisions.jsonl，在相同历史候选与事实下
   换策略/权重（recorded_request）或重算规则（recomputed_rules），输出
   旧/新动作键、完整评分、合法性、保底/错误与耗时；两种模式分开归因，
   不混合统计。
2. 完整桌赛驱动：只调用 SimulationEngine 的公开方法（start/frame/advance/
   export_hand/from_replay），按 frame 的全部窗口先准备紧急动作再请求
   策略、复核选择后一次性 advance；blocked/异常/步数上限都不是 complete。

依赖纪律（parallel-contracts §2/§6）：
- 不读取 WorldState 字段；engine/spec 只做结构访问。SimulationEngine、
  MatchSpec 由模拟线在 simulation/interface.py 交付（当前 C0 尚未存在），
  驱动通过注入的 choice_factory/spec_factory 构造对应对象，真实类型由
  组合根在 S/E 集成时传入，本模块不定义同名类型、不新增 SimulationPort。
- 决策行 request/budget 的解码属于审计 codec（C1）；本模块只定义注入
  接缝（decode_request/decode_budget），不复制生产 codec，也不把测试
  fixture 当生产解码器。
- 预算构造复用 application.deadline 的公开逻辑；clock_mode=logical 的
  实验不产生耗时结论（elapsed_ms 为 null），不能证明 1 秒窗口性能。
- 异常/超预算按与线上相同的保底规则降级（规则紧急候选）并计数；
  不能把选择不到动作静默换成 Pass。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, List, Mapping, Optional, Sequence, Tuple, Union

from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.actions import Action, WindowKey, action_key
from hangma_bot.kernel.config import RuleConfig, TournamentConfig
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.kernel.serialization import window_key_to_json
from hangma_bot.policy.interface import (
    BotPolicy,
    DecisionBudget,
    DecisionPlan,
    DecisionRequest,
)
from hangma_bot.policy.errors import PolicyTimeoutError

from .evaluation_results import (
    EVALUATION_SCHEMA_VERSION,
    SIMULATION_SOURCE_NAMESPACE,
    GameKey,
    MatchResult,
    RuntimeCounts,
    render_report_md,
)

# 实验配置线格式版本；破坏性变更必须递增并保留旧版本读取说明。
EXPERIMENT_SCHEMA_VERSION = 1
# 决策实验两种模式；报告不能混合归因。
DECISION_MODES = ("recorded_request", "recomputed_rules")
# 时钟模式：逻辑时钟只做可重复排序实验；耗时结论只来自 real。
CLOCK_MODES = ("logical", "real")
# 桌赛驱动终态；blocked/error 都不是 complete。
MATCH_OUTCOME_STATUSES = ("complete", "blocked", "error")

# 决策比较结果行格式版本（本模块输出 decisions.jsonl 的行）。
DECISION_ROW_SCHEMA_VERSION = 1

# 组合根钩子：bootstrap.py 提供的评估运行装配入口（主审集成项）。
# 存在时优先使用；缺失时 decisions 模式退回脚本内置显式装配，
# matches 模式必须等待模拟线交付（E3）。
BOOTSTRAP_RUNTIME_HOOK = "build_evaluation_runtime"
BOOTSTRAP_CODEC_HOOK = "build_decision_codec"


def _require_str(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("{0} 必须是非空字符串，得到 {1!r}".format(field_name, value))
    return value


def _require_non_negative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("{0} 必须是非负整数，得到 {1!r}".format(field_name, value))
    return value


# ---------------------------------------------------------------------------
# 实验配置
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PolicyDeclaration:
    """实验 JSON 中的策略声明：policy_id 加名称与完整权重（契约 §5）。"""

    policy_id: str  # 版本化标识；用户身份不冒充策略版本
    name: str  # weighted_heuristic / safe_fallback；由入口脚本装配
    weights: Tuple[Tuple[str, float], ...] = ()  # 完整权重；进 manifest

    def to_json(self) -> dict:
        return {
            "policy_id": self.policy_id,
            "name": self.name,
            "weights": dict(self.weights),
        }

    @classmethod
    def from_mapping(cls, data: object, field_name: str) -> "PolicyDeclaration":
        if not isinstance(data, Mapping):
            raise ValueError("{0} 必须是 JSON 对象".format(field_name))
        weights_raw = data.get("weights", {})
        if not isinstance(weights_raw, Mapping):
            raise ValueError("{0}.weights 必须是 JSON 对象".format(field_name))
        weights = tuple(
            sorted((str(key), float(value)) for key, value in weights_raw.items())
        )
        return cls(
            policy_id=_require_str(data.get("policy_id"), field_name + ".policy_id"),
            name=_require_str(data.get("name"), field_name + ".name"),
            weights=weights,
        )


def _rules_config_from_mapping(data: object, field_name: str) -> RuleConfig:
    if not isinstance(data, Mapping):
        raise ValueError("{0} 必须是 JSON 对象".format(field_name))
    return RuleConfig(
        ruleset_version=_require_str(data.get("ruleset_version"), field_name + ".ruleset_version"),
        base_score=data.get("base_score", 1),
        you_cai_bi_kao=bool(data.get("you_cai_bi_kao", False)),
    )


@dataclass(frozen=True)
class DecisionExperiment:
    """decisions 模式实验配置；从 EXPERIMENT_JSON 读取并校验。"""

    kind: str  # decisions
    decision_mode: str  # recorded_request / recomputed_rules
    clock_mode: str  # logical / real
    baseline: PolicyDeclaration
    challenger: PolicyDeclaration
    input_sha256: Optional[str]
    source_namespace: Optional[str]
    rules_config: Optional[RuleConfig]  # recomputed_rules 必填；重算用
    tournament_config: Optional[TournamentConfig]
    exclusions: Tuple[str, ...] = ()  # 声明排除的 hand_id/decision_id

    def __post_init__(self) -> None:
        if self.kind != "decisions":
            raise ValueError("DecisionExperiment.kind 必须是 decisions")
        if self.decision_mode not in DECISION_MODES:
            raise ValueError("decision_mode 必须是 {0} 之一".format(DECISION_MODES))
        if self.clock_mode not in CLOCK_MODES:
            raise ValueError("clock_mode 必须是 {0} 之一".format(CLOCK_MODES))
        if self.decision_mode == "recomputed_rules" and self.rules_config is None:
            raise ValueError("recomputed_rules 模式必须声明 rules_config（重算规则版本）")
        if self.baseline.policy_id == self.challenger.policy_id:
            raise ValueError("baseline 与 challenger 的 policy_id 必须不同")


@dataclass(frozen=True)
class MatchSeedSpec:
    """matches 模式的一个牌山根组：seed 与 scenario_id 一一对应。"""

    seed: int
    scenario_id: str

    def __post_init__(self) -> None:
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise ValueError("seed 必须是整数，得到 {0!r}".format(self.seed))
        _require_str(self.scenario_id, "scenario_id")


@dataclass(frozen=True)
class MatchExperiment:
    """matches 模式实验配置；换座与配对由本模块按声明执行。"""

    kind: str  # matches
    clock_mode: str
    baseline: PolicyDeclaration  # 测试座位的稳定版本
    challenger: PolicyDeclaration  # 测试座位的候选版本
    opponents: Tuple[PolicyDeclaration, ...]  # 对手池：逻辑座位 1—3
    tournament_config: TournamentConfig
    seeds: Tuple[MatchSeedSpec, ...]
    seat_permutations: Tuple[Tuple[int, int, int, int], ...]
    initial_dealer: int  # 逻辑座位（换座实验同步映射到实际座位）
    initial_scores: Tuple[int, int, int, int]  # 逻辑座位口径桌内积分
    step_limit: int = 100000
    match_id_prefix: str = "sim-eval"
    primary_metric: str = "table_score_delta"
    tie_method: str = "strict"
    n_resamples: int = 10000
    resample_seed: int = 0
    simulation_version: Optional[str] = None  # 模拟线版本；进 versions
    input_sha256: Optional[str] = None
    source_namespace: Optional[str] = None

    def __post_init__(self) -> None:
        if self.kind != "matches":
            raise ValueError("MatchExperiment.kind 必须是 matches")
        if self.clock_mode not in CLOCK_MODES:
            raise ValueError("clock_mode 必须是 {0} 之一".format(CLOCK_MODES))
        if len(self.opponents) != 3:
            raise ValueError("对手池必须恰好 3 个逻辑座位（1—3）")
        if not self.seeds:
            raise ValueError("seeds 不能为空")
        for permutation in self.seat_permutations:
            if tuple(sorted(permutation)) != (0, 1, 2, 3):
                raise ValueError("seat_permutations 元素必须是 0—3 的排列，得到 {0!r}".format(permutation))
        if isinstance(self.initial_dealer, bool) or not isinstance(self.initial_dealer, int) or not 0 <= self.initial_dealer < 4:
            raise ValueError("initial_dealer 必须是 0—3 的逻辑座位")
        if not isinstance(self.initial_scores, tuple) or len(self.initial_scores) != 4:
            raise ValueError("initial_scores 必须是长度为 4 的逻辑座位向量")
        if self.baseline.policy_id == self.challenger.policy_id:
            raise ValueError("baseline 与 challenger 的 policy_id 必须不同")


def load_experiment(path: Path) -> Union[DecisionExperiment, MatchExperiment]:
    """读取 EXPERIMENT_JSON 并按 kind 分派到对应配置类；格式错误立即失败。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("实验配置不是合法 JSON: {0}".format(error)) from error
    if not isinstance(data, Mapping):
        raise ValueError("实验配置必须是 JSON 对象")
    version = data.get("experiment_schema_version")
    if version != EXPERIMENT_SCHEMA_VERSION:
        raise ValueError(
            "experiment_schema_version 必须是 {0}，得到 {1!r}".format(EXPERIMENT_SCHEMA_VERSION, version)
        )
    kind = data.get("kind")
    if kind == "decisions":
        return DecisionExperiment(
            kind="decisions",
            decision_mode=_require_str(data.get("decision_mode"), "decision_mode"),
            clock_mode=_require_str(data.get("clock_mode", "logical"), "clock_mode"),
            baseline=PolicyDeclaration.from_mapping(data.get("baseline_policy"), "baseline_policy"),
            challenger=PolicyDeclaration.from_mapping(data.get("challenger_policy"), "challenger_policy"),
            input_sha256=data.get("input_sha256"),
            source_namespace=data.get("source_namespace"),
            rules_config=(
                None
                if data.get("rules_config") is None
                else _rules_config_from_mapping(data["rules_config"], "rules_config")
            ),
            tournament_config=(
                None
                if data.get("tournament_config") is None
                else _tournament_config_from_mapping(data["tournament_config"])
            ),
            exclusions=tuple(
                str(item) for item in data.get("exclusions", [])
                if isinstance(data.get("exclusions"), list)
            ),
        )
    if kind == "matches":
        from hangma_bot.kernel.serialization import tournament_config_from_json

        config_raw = data.get("tournament_config")
        if not isinstance(config_raw, Mapping):
            raise ValueError("matches 模式必须声明 tournament_config")
        tournament_config = tournament_config_from_json(config_raw)
        seeds_raw = data.get("seeds")
        if not isinstance(seeds_raw, list) or not seeds_raw:
            raise ValueError("seeds 必须是非空数组")
        seeds = tuple(
            MatchSeedSpec(
                seed=item["seed"] if isinstance(item, Mapping) else None,
                scenario_id=item["scenario_id"] if isinstance(item, Mapping) else None,
            )
            for item in seeds_raw
        )
        permutations_raw = data.get("seat_permutations")
        if not isinstance(permutations_raw, list) or not permutations_raw:
            raise ValueError("seat_permutations 必须是非空数组")
        permutations = tuple(tuple(item) for item in permutations_raw)
        initial_scores_raw = data.get("initial_scores", [0, 0, 0, 0])
        if not isinstance(initial_scores_raw, list) or len(initial_scores_raw) != 4:
            raise ValueError("initial_scores 必须是长度为 4 的数组")
        opponents = tuple(
            PolicyDeclaration.from_mapping(item, "opponent_pool[{0}]".format(index))
            for index, item in enumerate(data.get("opponent_pool", []))
        )
        return MatchExperiment(
            kind="matches",
            clock_mode=_require_str(data.get("clock_mode", "logical"), "clock_mode"),
            baseline=PolicyDeclaration.from_mapping(data.get("baseline_policy"), "baseline_policy"),
            challenger=PolicyDeclaration.from_mapping(data.get("challenger_policy"), "challenger_policy"),
            opponents=opponents,
            tournament_config=tournament_config,
            seeds=seeds,
            seat_permutations=permutations,
            initial_dealer=data.get("initial_dealer", 0),
            initial_scores=(initial_scores_raw[0], initial_scores_raw[1], initial_scores_raw[2], initial_scores_raw[3]),
            step_limit=data.get("step_limit", 100000),
            match_id_prefix=_require_str(data.get("match_id_prefix", "sim-eval"), "match_id_prefix"),
            primary_metric=_require_str(data.get("primary_metric", "table_score_delta"), "primary_metric"),
            tie_method=data.get("tie_method", "strict"),
            n_resamples=data.get("n_resamples", 10000),
            resample_seed=data.get("resample_seed", 0),
            simulation_version=data.get("simulation_version"),
            input_sha256=data.get("input_sha256"),
            source_namespace=data.get("source_namespace"),
        )
    raise ValueError("kind 必须是 decisions 或 matches，得到 {0!r}".format(kind))


def _tournament_config_from_mapping(data: object) -> TournamentConfig:
    from hangma_bot.kernel.serialization import tournament_config_from_json

    return tournament_config_from_json(data)


# ---------------------------------------------------------------------------
# 预算平移（契约 §3.3 与 contract-vectors budget_translation）
# ---------------------------------------------------------------------------


def translate_budget(
    budget: DecisionBudget, old_origin_monotonic: float, new_origin_monotonic: float
) -> DecisionBudget:
    """把记录的预算平移到新逻辑时钟基准，保持三个截止时间的间距不变。

    新截止 = 新基准 + (旧截止 − 旧基准)；跨进程单调时钟不得直接相减。
    三段顺序由 DecisionBudget 构造校验。
    """
    return DecisionBudget(
        enhancement_deadline_monotonic=new_origin_monotonic
        + (budget.enhancement_deadline_monotonic - old_origin_monotonic),
        fallback_deadline_monotonic=new_origin_monotonic
        + (budget.fallback_deadline_monotonic - old_origin_monotonic),
        latest_send_at_monotonic=new_origin_monotonic
        + (budget.latest_send_at_monotonic - old_origin_monotonic),
    )


# ---------------------------------------------------------------------------
# 固定决策集比较
# ---------------------------------------------------------------------------


def _candidate_keys(request: DecisionRequest) -> Tuple[str, ...]:
    return tuple(
        sorted(candidate.action_key for candidate in request.rules.legal_candidates)
    )


@dataclass(frozen=True)
class PolicyRunOutcome:
    """一次策略运行的结果与复核事实；JSON 序列化用 to_json。"""

    policy_id: str
    action_key: Optional[str]  # 生效动作；策略与紧急候选都不可得时为 None
    rank: Optional[int]  # 计划内排名（1 起）；紧急保底为空
    total_score: Optional[float]
    score_parts: Tuple[Tuple[str, float], ...]
    reasons: Tuple[str, ...]
    is_emergency: bool
    legal: Optional[bool]  # 相对本次实验所用 RuleAnalysis 的复核结果
    legality_reason: Optional[str]
    fallback_reason: Optional[str]  # timeout/error/empty_plan/无紧急候选
    plan_revision: Optional[int]
    degraded_reasons: Tuple[str, ...]
    elapsed_ms: Optional[float]  # 只有 clock_mode=real 才有值
    error: Optional[str]

    def to_json(self) -> dict:
        return {
            "policy_id": self.policy_id,
            "action_key": self.action_key,
            "rank": self.rank,
            "total_score": self.total_score,
            "score_parts": [list(item) for item in self.score_parts],
            "reasons": list(self.reasons),
            "is_emergency": self.is_emergency,
            "legal": self.legal,
            "legality_reason": self.legality_reason,
            "fallback_reason": self.fallback_reason,
            "plan_revision": self.plan_revision,
            "degraded_reasons": list(self.degraded_reasons),
            "elapsed_ms": self.elapsed_ms,
            "error": self.error,
        }


async def _run_policy_on_request(
    policy: BotPolicy,
    policy_id: str,
    request: DecisionRequest,
    budget: DecisionBudget,
    *,
    now_monotonic: Callable[[], float],
    wall_clock: Optional[Callable[[], float]],
) -> PolicyRunOutcome:
    """在指定预算内运行策略并复核选择；异常/超时按紧急保底降级并计数。

    保底规则与线上一致：优先用计划第一候选，计划为空或策略失败时用
    规则紧急候选；都不存在时 action_key 为 None（绝不静默换成 Pass）。
    """
    legal_keys = frozenset(_candidate_keys(request))
    started = None if wall_clock is None else wall_clock()

    plan: Optional[DecisionPlan] = None
    fallback_reason: Optional[str] = None
    error: Optional[str] = None
    try:
        remaining = max(0.0, budget.fallback_deadline_monotonic - now_monotonic())
        plan = await asyncio.wait_for(policy.choose(request, budget), timeout=remaining)
    except (asyncio.TimeoutError, PolicyTimeoutError):
        fallback_reason = "timeout"
    except Exception as exc:  # 故障边界：策略异常不得崩溃整批比较
        fallback_reason = "error"
        error = "{0}: {1}".format(type(exc).__name__, exc)

    elapsed_ms = None
    if wall_clock is not None and started is not None:
        elapsed_ms = (wall_clock() - started) * 1000.0

    chosen = None if plan is None or not plan.candidates else plan.candidates[0]
    is_emergency = False
    if chosen is not None:
        action = chosen.action
        rank = chosen.rank
        total_score = chosen.total_score
        score_parts = tuple((item.name, item.value) for item in chosen.score_parts)
        reasons = tuple(chosen.reasons)
        plan_revision = plan.revision
        degraded = tuple(plan.degraded_reasons)
        emergency_flag = chosen.is_emergency
    else:
        # 保底规则：计划为空或策略失败时使用规则紧急候选（同线上）。
        fallback_reason = fallback_reason or "empty_plan"
        emergency = request.rules.emergency_candidate
        if emergency is None:
            return PolicyRunOutcome(
                policy_id=policy_id,
                action_key=None,
                rank=None,
                total_score=None,
                score_parts=(),
                reasons=(),
                is_emergency=False,
                legal=None,
                legality_reason="无紧急候选，无法确定保底动作（不静默换成 Pass）",
                fallback_reason=fallback_reason or "empty_plan",
                plan_revision=None,
                degraded_reasons=(),
                elapsed_ms=elapsed_ms,
                error=error,
            )
        action = emergency.action
        rank = None
        total_score = None
        score_parts = ()
        reasons = tuple(emergency.evidence)
        plan_revision = None
        degraded = ()
        emergency_flag = True
        is_emergency = True

    key = action_key(action)
    if key in legal_keys:
        legal = True
        legality_reason = None
    else:
        legal = False
        legality_reason = "动作 {0} 不在本实验所用 RuleAnalysis 合法候选中".format(key)

    return PolicyRunOutcome(
        policy_id=policy_id,
        action_key=key,
        rank=rank,
        total_score=total_score,
        score_parts=score_parts,
        reasons=reasons,
        is_emergency=is_emergency or emergency_flag,
        legal=legal,
        legality_reason=legality_reason,
        fallback_reason=fallback_reason,
        plan_revision=plan_revision,
        degraded_reasons=degraded,
        elapsed_ms=elapsed_ms,
        error=error,
    )


@dataclass(frozen=True)
class RulesDiff:
    """recorded_request 下只有旧口径；recomputed_rules 下记录旧/新差异。"""

    recomputed: bool
    old_ruleset_version: Optional[str]
    new_ruleset_version: Optional[str]
    old_candidate_keys: Tuple[str, ...]
    new_candidate_keys: Tuple[str, ...]
    old_completeness: Optional[str]
    new_completeness: Optional[str]

    def to_json(self) -> dict:
        return {
            "recomputed": self.recomputed,
            "old_ruleset_version": self.old_ruleset_version,
            "new_ruleset_version": self.new_ruleset_version,
            "old_candidate_keys": list(self.old_candidate_keys),
            "new_candidate_keys": list(self.new_candidate_keys),
            "old_completeness": self.old_completeness,
            "new_completeness": self.new_completeness,
        }


@dataclass(frozen=True)
class DecisionComparisonRow:
    """decisions.jsonl 的一行：一次固定决策比较的完整事实。"""

    evaluation_schema_version: int
    mode: str
    clock_mode: str
    hand_id: str
    split_group_id: Optional[str]
    decision_id: str
    run_id: Optional[str]
    participant_id: Optional[str]
    recorded_plan_revision: Optional[int]
    seat: int
    window_key: Mapping  # kernel window_key_to_json 口径
    budget: Mapping  # 平移后的三段截止与新旧基准
    rules: RulesDiff
    baseline: PolicyRunOutcome
    challenger: PolicyRunOutcome
    end_reason: Optional[str]
    decision_complete: Optional[bool]
    source_refs: Tuple[Mapping, ...]

    def to_json(self) -> dict:
        return {
            "evaluation_schema_version": self.evaluation_schema_version,
            "mode": self.mode,
            "clock_mode": self.clock_mode,
            "hand_id": self.hand_id,
            "split_group_id": self.split_group_id,
            "decision_id": self.decision_id,
            "run_id": self.run_id,
            "participant_id": self.participant_id,
            "recorded_plan_revision": self.recorded_plan_revision,
            "seat": self.seat,
            "window_key": dict(self.window_key),
            "budget": dict(self.budget),
            "rules": self.rules.to_json(),
            "baseline": self.baseline.to_json(),
            "challenger": self.challenger.to_json(),
            "end_reason": self.end_reason,
            "decision_complete": self.decision_complete,
            "source_refs": [dict(item) for item in self.source_refs],
        }


def _validate_decision_source_row(row: Mapping, line_no: int) -> List[str]:
    """按契约 §5.1 检查决策行本模块需要的字段；问题列表返回。"""
    problems: List[str] = []
    version = row.get("replay_schema_version")
    if version != 1:
        problems.append("replay_schema_version 必须为 1，得到 {0!r}".format(version))
    for key in ("hand_id", "decision_id", "request", "budget", "budget_origin_monotonic"):
        if key not in row:
            problems.append("缺少必填键 {0}".format(key))
    return problems


async def compare_decision_row(
    row: Mapping,
    *,
    experiment: DecisionExperiment,
    baseline_policy: BotPolicy,
    challenger_policy: BotPolicy,
    decode_request: Callable[[Mapping], DecisionRequest],
    decode_budget: Callable[[Mapping, float], DecisionBudget],
    recompute_rules: Optional[HangmaRules],
    now_monotonic: Callable[[], float],
    wall_clock: Optional[Callable[[], float]],
) -> DecisionComparisonRow:
    """对一行决策记录执行固定决策比较；缺完整 request 时抛 ValueError。

    - recorded_request：保留原 request.rules，只换策略/权重并平移预算；
    - recomputed_rules：用同一 observation 重新调用指定版本 HangmaRules，
      两个策略都在新规则上运行，旧/新规则差异单列，不混合归因。
    """
    request = decode_request(row["request"])
    recorded_budget = decode_budget(row["budget"], row["budget_origin_monotonic"])
    new_origin = now_monotonic()
    budget = translate_budget(recorded_budget, row["budget_origin_monotonic"], new_origin)

    old_rules = request.rules
    if experiment.decision_mode == "recomputed_rules":
        if recompute_rules is None:
            raise ValueError("recomputed_rules 模式缺少注入的规则重算实例")
        new_analysis = recompute_rules.analyze(request.observation)
        rules_diff = RulesDiff(
            recomputed=True,
            old_ruleset_version=old_rules.ruleset_version,
            new_ruleset_version=new_analysis.ruleset_version,
            old_candidate_keys=tuple(
                sorted(candidate.action_key for candidate in old_rules.legal_candidates)
            ),
            new_candidate_keys=tuple(
                sorted(candidate.action_key for candidate in new_analysis.legal_candidates)
            ),
            old_completeness=old_rules.completeness.value,
            new_completeness=new_analysis.completeness.value,
        )
        effective_rules = new_analysis
    else:
        rules_diff = RulesDiff(
            recomputed=False,
            old_ruleset_version=old_rules.ruleset_version,
            new_ruleset_version=old_rules.ruleset_version,
            old_candidate_keys=tuple(
                sorted(candidate.action_key for candidate in old_rules.legal_candidates)
            ),
            new_candidate_keys=tuple(
                sorted(candidate.action_key for candidate in old_rules.legal_candidates)
            ),
            old_completeness=old_rules.completeness.value,
            new_completeness=old_rules.completeness.value,
        )
        effective_rules = old_rules

    from dataclasses import replace

    effective_request = replace(request, rules=effective_rules)
    baseline = await _run_policy_on_request(
        baseline_policy,
        experiment.baseline.policy_id,
        effective_request,
        budget,
        now_monotonic=now_monotonic,
        wall_clock=wall_clock,
    )
    challenger = await _run_policy_on_request(
        challenger_policy,
        experiment.challenger.policy_id,
        effective_request,
        budget,
        now_monotonic=now_monotonic,
        wall_clock=wall_clock,
    )

    seat = effective_request.observation.seat
    if seat != effective_request.window_key.seat:
        raise ValueError(
            "观察座位 {0} 与窗口座位 {1} 不一致".format(seat, effective_request.window_key.seat)
        )

    end_reason = row.get("end_reason")
    decision_complete = row.get("decision_complete")
    return DecisionComparisonRow(
        evaluation_schema_version=DECISION_ROW_SCHEMA_VERSION,
        mode=experiment.decision_mode,
        clock_mode=experiment.clock_mode,
        hand_id=row["hand_id"],
        split_group_id=row.get("split_group_id"),
        decision_id=row["decision_id"],
        run_id=row.get("run_id"),
        participant_id=row.get("participant_id"),
        recorded_plan_revision=row.get("plan_revision"),
        seat=seat,
        window_key=window_key_to_json(effective_request.window_key),
        budget={
            "old_origin_monotonic": row["budget_origin_monotonic"],
            "new_origin_monotonic": new_origin,
            "enhancement_deadline_monotonic": budget.enhancement_deadline_monotonic,
            "fallback_deadline_monotonic": budget.fallback_deadline_monotonic,
            "latest_send_at_monotonic": budget.latest_send_at_monotonic,
        },
        rules=rules_diff,
        baseline=baseline,
        challenger=challenger,
        end_reason=end_reason if isinstance(end_reason, str) else None,
        decision_complete=decision_complete if isinstance(decision_complete, bool) else None,
        source_refs=tuple(
            {"file": str(item.get("file")), "line_no": item.get("line_no")}
            for item in row.get("source_refs", [])
            if isinstance(item, Mapping)
        ),
    )


@dataclass(frozen=True)
class DecisionsOutcome:
    """一次 decisions 实验的产出与排除清单。"""

    rows: Tuple[DecisionComparisonRow, ...]
    excluded: Tuple[str, ...]  # 每项含行号与原因；不静默删除
    input_sha256: Optional[str]


def write_decision_rows(path: Path, rows: Sequence[DecisionComparisonRow]) -> None:
    """按稳定键序写出 decisions.jsonl；同输入输出逐字节一致。"""
    lines = [
        json.dumps(row.to_json(), ensure_ascii=False, sort_keys=True) + "\n"
        for row in rows
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(lines), encoding="utf-8")


def read_decision_rows(path: Path) -> Tuple[List[Mapping], List[str]]:
    """读取本模块产出的 decisions.jsonl；结构错误进问题列表不整体崩溃。"""
    rows: List[Mapping] = []
    problems: List[str] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as error:
            problems.append("第 {0} 行不是合法 JSON: {1}".format(line_no, error))
            continue
        if not isinstance(payload, Mapping):
            problems.append("第 {0} 行不是 JSON 对象".format(line_no))
            continue
        if payload.get("evaluation_schema_version") != DECISION_ROW_SCHEMA_VERSION:
            problems.append(
                "第 {0} 行 evaluation_schema_version 未知: {1!r}".format(
                    line_no, payload.get("evaluation_schema_version")
                )
            )
            continue
        rows.append(payload)
    return rows, problems


async def run_decisions_comparison(
    dataset_dir: Path,
    experiment: DecisionExperiment,
    *,
    baseline_policy: BotPolicy,
    challenger_policy: BotPolicy,
    decode_request: Callable[[Mapping], DecisionRequest],
    decode_budget: Callable[[Mapping, float], DecisionBudget],
    recompute_rules: Optional[HangmaRules] = None,
    now_monotonic: Callable[[], float],
    wall_clock: Optional[Callable[[], float]],
) -> DecisionsOutcome:
    """读取统一牌谱 decisions.jsonl 并逐行比较；排除项带原因返回。

    - 缺完整 request 的旧记录排除并计数，不从修复后的算法补算后仍标
      recorded_request（evaluation-start §2）；
    - 行级异常不崩溃整批：进入 excluded 并继续；
    - accepted 不当作执行标签；本函数不输出最优动作准确率或遗憾值。
    """
    decisions_path = dataset_dir / "decisions.jsonl"
    if not decisions_path.is_file():
        raise FileNotFoundError("统一牌谱缺少 decisions.jsonl: {0}".format(decisions_path))
    input_sha256 = hashlib.sha256(decisions_path.read_bytes()).hexdigest()

    rows: List[DecisionComparisonRow] = []
    excluded: List[str] = []
    for line_no, line in enumerate(
        decisions_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as error:
            excluded.append("第 {0} 行：非法 JSON（{1}）".format(line_no, error))
            continue
        if not isinstance(payload, Mapping):
            excluded.append("第 {0} 行：不是 JSON 对象".format(line_no))
            continue
        problems = _validate_decision_source_row(payload, line_no)
        if problems:
            excluded.append("第 {0} 行：{1}".format(line_no, "; ".join(problems)))
            continue
        hand_id = str(payload["hand_id"])
        decision_id = str(payload["decision_id"])
        if hand_id in experiment.exclusions or decision_id in experiment.exclusions:
            excluded.append("第 {0} 行：{1}/{2} 在实验排除清单中".format(line_no, hand_id, decision_id))
            continue
        try:
            row = await compare_decision_row(
                payload,
                experiment=experiment,
                baseline_policy=baseline_policy,
                challenger_policy=challenger_policy,
                decode_request=decode_request,
                decode_budget=decode_budget,
                recompute_rules=recompute_rules,
                now_monotonic=now_monotonic,
                wall_clock=wall_clock,
            )
        except ValueError as error:
            excluded.append("第 {0} 行：{1}".format(line_no, error))
            continue
        except Exception as error:  # 单行故障隔离
            excluded.append(
                "第 {0} 行：未预期异常 {1}: {2}".format(line_no, type(error).__name__, error)
            )
            continue
        rows.append(row)
    return DecisionsOutcome(rows=tuple(rows), excluded=tuple(excluded), input_sha256=input_sha256)


def build_decision_report(
    outcome: DecisionsOutcome, experiment: DecisionExperiment
) -> dict:
    """生成 decisions 实验的结构化报告；只描述差异，不下强度结论。"""
    rows = outcome.rows
    changed = [
        row
        for row in rows
        if row.baseline.action_key != row.challenger.action_key
    ]
    baseline_illegal = [row for row in rows if row.baseline.legal is False]
    challenger_illegal = [row for row in rows if row.challenger.legal is False]
    baseline_fallback = [row for row in rows if row.baseline.fallback_reason is not None]
    challenger_fallback = [row for row in rows if row.challenger.fallback_reason is not None]
    both_none = [row for row in rows if row.baseline.action_key is None or row.challenger.action_key is None]

    matrix: dict = {}
    for row in changed:
        key = (row.baseline.action_key, row.challenger.action_key)
        matrix[key] = matrix.get(key, 0) + 1
    matrix_rows = [
        [baseline_key, challenger_key, count]
        for (baseline_key, challenger_key), count in sorted(matrix.items())
    ]

    sections = [
        {
            "heading": "样本与排除",
            "table": {
                "columns": ["指标", "数值"],
                "rows": [
                    ["输入决策行（比较成功）", len(rows)],
                    ["排除行", len(outcome.excluded)],
                    ["mode", experiment.decision_mode],
                    ["clock_mode", experiment.clock_mode],
                    ["基线 policy_id", experiment.baseline.policy_id],
                    ["候选 policy_id", experiment.challenger.policy_id],
                ],
            },
        },
        {
            "heading": "决策差异（相同历史候选与事实下的排序变化）",
            "table": {
                "columns": ["指标", "数值"],
                "rows": [
                    ["第一名动作键不同", len(changed)],
                    ["基线动作不在合法候选", len(baseline_illegal)],
                    ["候选动作不在合法候选", len(challenger_illegal)],
                    ["基线使用保底", len(baseline_fallback)],
                    ["候选使用保底", len(challenger_fallback)],
                    ["任一侧无可用动作", len(both_none)],
                ],
            },
        },
        {
            "heading": "第一名动作变化矩阵",
            "table": {
                "columns": ["基线动作键", "候选动作键", "行数"],
                "rows": matrix_rows,
            },
        },
    ]
    if outcome.excluded:
        sections.append(
            {"heading": "排除明细", "paragraphs": list(outcome.excluded)}
        )
    if experiment.clock_mode == "logical":
        sections.append(
            {
                "heading": "耗时说明",
                "paragraphs": [
                    "clock_mode=logical：本实验不产生耗时结论（elapsed_ms 为 null），"
                    "不能证明 1 秒窗口性能；硬件耗时基准另跑 real 时钟。"
                ],
            }
        )
    elif rows:
        baseline_ms = [row.baseline.elapsed_ms for row in rows if row.baseline.elapsed_ms is not None]
        challenger_ms = [row.challenger.elapsed_ms for row in rows if row.challenger.elapsed_ms is not None]
        sections.append(
            {
                "heading": "耗时（wall-clock，仅本机参考）",
                "table": {
                    "columns": ["策略", "均值 ms", "最大 ms", "样本"],
                    "rows": [
                        [
                            "基线",
                            _safe_mean(baseline_ms),
                            max(baseline_ms) if baseline_ms else None,
                            len(baseline_ms),
                        ],
                        [
                            "候选",
                            _safe_mean(challenger_ms),
                            max(challenger_ms) if challenger_ms else None,
                            len(challenger_ms),
                        ],
                    ],
                },
            }
        )

    return {
        "title": "固定决策集比较报告",
        "intro": [
            "统计单位：单次决策（仅诊断与差异归因，不是强度结论的统计单位）。",
            "归因纪律：recorded_request 与 recomputed_rules 分开报告，"
            "不混合归因；accepted 不当执行标签，不输出最优动作准确率或遗憾值。",
        ],
        "sections": sections,
    }


def _safe_mean(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return sum(values) / len(values)


# ---------------------------------------------------------------------------
# 完整桌赛驱动（只调用 SimulationEngine 公开方法）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MatchDriverConfig:
    """桌赛驱动的确定性输入；不含策略、网络或真实时钟。"""

    clock_mode: str  # logical / real
    step_limit: int  # 步数上限；到顶是 error，不是 complete/合成流局
    budget_policy: BudgetPolicy  # deadline.py 公开预算比例
    competition_tournament_id: str  # 可见事实：模拟实验标识，不伪造海选晋级线

    def __post_init__(self) -> None:
        if self.clock_mode not in CLOCK_MODES:
            raise ValueError("clock_mode 必须是 {0} 之一".format(CLOCK_MODES))
        if self.step_limit <= 0:
            raise ValueError("step_limit 必须是正整数")


@dataclass(frozen=True)
class MatchDecisionRecord:
    """驱动内一次窗口决策的审计事实；供诊断指标与 runtime_counts。

    decision_id 必须同帧多窗口唯一（含座位成分）：碰窗口三家同帧的
    关联链路按 AGENTS.md §8 用 decision_id 串联，不得共享同一标识。
    """

    decision_id: str
    seat: int
    policy_id: Optional[str]
    window_key: Mapping
    action_key: Optional[str]
    legal: Optional[bool]
    is_emergency: bool
    fallback_reason: Optional[str]
    plan_revision: Optional[int]
    degraded_reasons: Tuple[str, ...]
    elapsed_ms: Optional[float]

    def to_json(self) -> dict:
        return {
            "decision_id": self.decision_id,
            "seat": self.seat,
            "policy_id": self.policy_id,
            "window_key": dict(self.window_key),
            "action_key": self.action_key,
            "legal": self.legal,
            "is_emergency": self.is_emergency,
            "fallback_reason": self.fallback_reason,
            "plan_revision": self.plan_revision,
            "degraded_reasons": list(self.degraded_reasons),
            "elapsed_ms": self.elapsed_ms,
        }


@dataclass(frozen=True)
class MatchRunOutcome:
    """一次完整桌赛运行的结果；只有 complete 可进强度统计。"""

    status: str  # complete / blocked / error
    completed_hands: int
    final_scores: Optional[Tuple[int, int, int, int]]
    blocked_reason: Optional[str]
    error_reason: Optional[str]
    steps: int
    decisions: Tuple[MatchDecisionRecord, ...]
    runtime_counts: RuntimeCounts

    def to_json(self) -> dict:
        return {
            "status": self.status,
            "completed_hands": self.completed_hands,
            "final_scores": None if self.final_scores is None else list(self.final_scores),
            "blocked_reason": self.blocked_reason,
            "error_reason": self.error_reason,
            "steps": self.steps,
            "decisions": [item.to_json() for item in self.decisions],
            "runtime_counts": {
                "timeouts": self.runtime_counts.timeouts,
                "illegal_choices": self.runtime_counts.illegal_choices,
                "fallbacks": self.runtime_counts.fallbacks,
                "auto_actions": self.runtime_counts.auto_actions,
                "audit_missing": self.runtime_counts.audit_missing,
            },
        }


def seat_policies_from(
    policies_by_id: Mapping[str, BotPolicy],
    permutation: Sequence[int],
    logical_ids: Sequence[str],
) -> Tuple[BotPolicy, BotPolicy, BotPolicy, BotPolicy]:
    """把逻辑身份策略映射到实际座位：permutation[i] = 逻辑身份 i 的实际座位。"""
    if tuple(sorted(permutation)) != (0, 1, 2, 3):
        raise ValueError("permutation 必须是 0—3 的排列")
    if len(logical_ids) != 4:
        raise ValueError("logical_ids 必须长度为 4")
    by_seat: List[BotPolicy] = [None, None, None, None]  # type: ignore[list-item]
    for logical, seat in enumerate(permutation):
        by_seat[seat] = policies_by_id[logical_ids[logical]]
    return (by_seat[0], by_seat[1], by_seat[2], by_seat[3])  # type: ignore[return-value]


def policy_ids_by_seat_from(
    permutation: Sequence[int], logical_ids: Sequence[Optional[str]]
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """同上，返回 policy_id 而非策略对象；供 MatchResult.policy_ids_by_seat。"""
    if tuple(sorted(permutation)) != (0, 1, 2, 3):
        raise ValueError("permutation 必须是 0—3 的排列")
    if len(logical_ids) != 4:
        raise ValueError("logical_ids 必须长度为 4")
    by_seat: List[Optional[str]] = [None, None, None, None]
    for logical, seat in enumerate(permutation):
        by_seat[seat] = logical_ids[logical]
    return (by_seat[0], by_seat[1], by_seat[2], by_seat[3])


async def drive_match(
    *,
    engine: Any,
    spec: Any,
    policies_by_seat: Tuple[BotPolicy, BotPolicy, BotPolicy, BotPolicy],
    rules: HangmaRules,
    choice_factory: Callable[[WindowKey, Action], Any],
    config: MatchDriverConfig,
    now_monotonic: Callable[[], float],
    wall_clock: Optional[Callable[[], float]],
) -> MatchRunOutcome:
    """完整桌赛驱动循环（simulation-v1 公开方法的唯一调用方）。

    - engine 必须是模拟线的 SimulationEngine（start/frame/advance）；spec
      是 MatchSpec；二者均来自组合根，本模块不读取 WorldState 字段。
    - 每帧先对每个窗口调用 rules.analyze 准备紧急动作，再构造
      DecisionRequest/DecisionBudget 请求对应座位策略；复核选择后把
      全部窗口一次性 advance。
    - 策略异常/超时按紧急候选保底并计数；复核非法同样转紧急候选；
      任何窗口都拿不到动作时整场以 error 结束，不合成流局。
    - advance 抛 ValueError（旧 revision/缺窗/非法动作）按 error 结束。
    """
    timeouts = 0
    illegal_choices = 0
    fallbacks = 0
    decisions: List[MatchDecisionRecord] = []
    world = engine.start(spec)
    steps = 0
    while steps < config.step_limit:
        steps += 1
        frame = engine.frame(world)
        if frame.blocked_reason is not None:
            return MatchRunOutcome(
                status="blocked",
                completed_hands=frame.completed_hands,
                final_scores=None,
                blocked_reason=frame.blocked_reason,
                error_reason=None,
                steps=steps,
                decisions=tuple(decisions),
                runtime_counts=RuntimeCounts(
                    timeouts=timeouts,
                    illegal_choices=illegal_choices,
                    fallbacks=fallbacks,
                    auto_actions=0,
                    audit_missing=0,
                ),
            )
        if frame.final_scores is not None:
            return MatchRunOutcome(
                status="complete",
                completed_hands=frame.completed_hands,
                final_scores=tuple(frame.final_scores),
                blocked_reason=None,
                error_reason=None,
                steps=steps,
                decisions=tuple(decisions),
                runtime_counts=RuntimeCounts(
                    timeouts=timeouts,
                    illegal_choices=illegal_choices,
                    fallbacks=fallbacks,
                    auto_actions=0,
                    audit_missing=0,
                ),
            )
        if not frame.decisions:
            # 契约：帧必须是「有决策且两终态为空」三类之一；空决策非终态
            # 会让评估器忙循环，按 error 结束并给出原因。
            return MatchRunOutcome(
                status="error",
                completed_hands=frame.completed_hands,
                final_scores=None,
                blocked_reason=None,
                error_reason="空决策非终态帧（revision={0}）".format(frame.revision),
                steps=steps,
                decisions=tuple(decisions),
                runtime_counts=RuntimeCounts(
                    timeouts=timeouts,
                    illegal_choices=illegal_choices,
                    fallbacks=fallbacks,
                    auto_actions=0,
                    audit_missing=0,
                ),
            )

        choices = []
        for decision in frame.decisions:
            record, choice, action_available = await _resolve_window(
                decision=decision,
                match_id=spec.match_id,
                policies_by_seat=policies_by_seat,
                rules=rules,
                choice_factory=choice_factory,
                config=config,
                now_monotonic=now_monotonic,
                wall_clock=wall_clock,
            )
            decisions.append(record)
            if record.fallback_reason == "timeout":
                timeouts += 1
            elif record.fallback_reason == "illegal_choice":
                illegal_choices += 1
            elif record.fallback_reason is not None:
                fallbacks += 1
            if not action_available:
                return MatchRunOutcome(
                    status="error",
                    completed_hands=frame.completed_hands,
                    final_scores=None,
                    blocked_reason=None,
                    error_reason="窗口无可用动作（策略与紧急候选都不可得），不静默换成 Pass",
                    steps=steps,
                    decisions=tuple(decisions),
                    runtime_counts=RuntimeCounts(
                        timeouts=timeouts,
                        illegal_choices=illegal_choices,
                        fallbacks=fallbacks,
                        auto_actions=0,
                        audit_missing=0,
                    ),
                )
            choices.append(choice)

        try:
            world = engine.advance(world, frame.revision, tuple(choices))
        except ValueError as error:
            return MatchRunOutcome(
                status="error",
                completed_hands=frame.completed_hands,
                final_scores=None,
                blocked_reason=None,
                error_reason="advance 拒绝本帧选择（旧 revision/缺窗/非法动作）: {0}".format(error),
                steps=steps,
                decisions=tuple(decisions),
                runtime_counts=RuntimeCounts(
                    timeouts=timeouts,
                    illegal_choices=illegal_choices,
                    fallbacks=fallbacks,
                    auto_actions=0,
                    audit_missing=0,
                ),
            )
        except Exception as error:  # 引擎异常不得伪装成 complete
            return MatchRunOutcome(
                status="error",
                completed_hands=frame.completed_hands,
                final_scores=None,
                blocked_reason=None,
                error_reason="引擎 advance 异常: {0}: {1}".format(type(error).__name__, error),
                steps=steps,
                decisions=tuple(decisions),
                runtime_counts=RuntimeCounts(
                    timeouts=timeouts,
                    illegal_choices=illegal_choices,
                    fallbacks=fallbacks,
                    auto_actions=0,
                    audit_missing=0,
                ),
            )
    return MatchRunOutcome(
        status="error",
        completed_hands=0,
        final_scores=None,
        blocked_reason=None,
        error_reason="超过步数上限 {0}，不是 complete，不合成流局".format(config.step_limit),
        steps=steps,
        decisions=tuple(decisions),
        runtime_counts=RuntimeCounts(
            timeouts=timeouts,
            illegal_choices=illegal_choices,
            fallbacks=fallbacks,
            auto_actions=0,
            audit_missing=0,
        ),
    )


async def _resolve_window(
    *,
    decision: Any,
    match_id: str,
    policies_by_seat: Tuple[BotPolicy, BotPolicy, BotPolicy, BotPolicy],
    rules: HangmaRules,
    choice_factory: Callable[[WindowKey, Action], Any],
    config: MatchDriverConfig,
    now_monotonic: Callable[[], float],
    wall_clock: Optional[Callable[[], float]],
) -> Tuple[MatchDecisionRecord, Any, bool]:
    """解析一个模拟窗口：规则分析 → 预算 → 策略 → 复核 → SimulationChoice。"""
    observation = decision.observation
    window_key: WindowKey = decision.window_key
    seat = window_key.seat
    if not 0 <= seat < 4:
        raise ValueError("窗口座位越界: {0!r}".format(seat))
    analysis = rules.analyze(observation)

    competition = CompetitionContext(
        tournament_id=config.competition_tournament_id,
        stage_no=None,
        stage_role=None,
        stage_total=None,
        participant_rank=None,
        ranking=(),
        observed_at_unix_ms=0,
    )
    budget = config.budget_policy.build(now_monotonic(), decision.timeout_seconds)
    # 决策标识含座位成分：同帧多窗口（如三家碰响应）必须 decision_id 唯一，
    # 关联链路（AGENTS.md §8）不得共享同一标识。
    decision_id = "{0}:{1}:{2}:{3}:{4}:seat{5}".format(
        match_id,
        window_key.game_id,
        window_key.round_no,
        window_key.trigger_seq,
        window_key.phase.value,
        seat,
    )
    request = DecisionRequest(
        observation=observation,
        competition=competition,
        rules=analysis,
        decision_id=decision_id,
        trigger_seq=window_key.trigger_seq,
        window_key=window_key,
        rejected_attempts=(),
    )

    policy = policies_by_seat[seat]
    started = None if wall_clock is None else wall_clock()
    plan: Optional[DecisionPlan] = None
    fallback_reason: Optional[str] = None
    policy_error: Optional[str] = None
    try:
        remaining = max(0.0, budget.fallback_deadline_monotonic - now_monotonic())
        plan = await asyncio.wait_for(policy.choose(request, budget), timeout=remaining)
    except (asyncio.TimeoutError, PolicyTimeoutError):
        fallback_reason = "timeout"
    except Exception as exc:
        fallback_reason = "policy_error"
        policy_error = "{0}: {1}".format(type(exc).__name__, exc)

    elapsed_ms = None
    if wall_clock is not None and started is not None:
        elapsed_ms = (wall_clock() - started) * 1000.0

    legal_keys = frozenset(candidate.action_key for candidate in analysis.legal_candidates)
    emergency = analysis.emergency_candidate

    chosen = None if plan is None or not plan.candidates else plan.candidates[0]
    is_emergency = False
    if chosen is not None:
        action = chosen.action
        plan_revision = plan.revision
        degraded = tuple(plan.degraded_reasons)
        is_emergency = bool(chosen.is_emergency)
    else:
        fallback_reason = fallback_reason or "empty_plan"
        if emergency is None:
            record = MatchDecisionRecord(
                decision_id=decision_id,
                seat=seat,
                policy_id=None,
                window_key=window_key_to_json(window_key),
                action_key=None,
                legal=None,
                is_emergency=False,
                fallback_reason=fallback_reason,
                plan_revision=None,
                degraded_reasons=(),
                elapsed_ms=elapsed_ms,
            )
            return record, None, False
        action = emergency.action
        plan_revision = None
        degraded = ()
        is_emergency = True

    key = action_key(action)
    legal = key in legal_keys
    if not legal:
        # 复核非法：按相同保底规则转紧急候选（计数），不把非法动作送进 advance。
        if emergency is None or emergency.action_key not in legal_keys:
            record = MatchDecisionRecord(
                decision_id=decision_id,
                seat=seat,
                policy_id=None,
                window_key=window_key_to_json(window_key),
                action_key=key,
                legal=False,
                is_emergency=is_emergency,
                fallback_reason=fallback_reason or "illegal_choice",
                plan_revision=plan_revision,
                degraded_reasons=degraded,
                elapsed_ms=elapsed_ms,
            )
            return record, None, False
        action = emergency.action
        key = action_key(action)
        legal = True
        is_emergency = True
        fallback_reason = fallback_reason or "illegal_choice"

    record = MatchDecisionRecord(
        decision_id=decision_id,
        seat=seat,
        policy_id=_policy_id_from_policy(policy),
        window_key=window_key_to_json(window_key),
        action_key=key,
        legal=legal,
        is_emergency=is_emergency,
        fallback_reason=fallback_reason,
        plan_revision=plan_revision,
        degraded_reasons=degraded,
        elapsed_ms=elapsed_ms,
    )
    return record, choice_factory(window_key, action), True


def _policy_id_from_policy(policy: Any) -> Optional[str]:
    """从策略对象尽力取 policy_id；缺失返回 None（不进强度统计的身份）。"""
    return getattr(policy, "policy_id", None)


def build_match_result(
    *,
    match_id: str,
    scenario_id: str,
    pair_id: str,
    config: TournamentConfig,
    policy_ids_by_seat: Tuple[Optional[str], Optional[str], Optional[str], Optional[str]],
    seat_permutation: Tuple[int, int, int, int],
    initial_scores_physical: Tuple[int, int, int, int],
    outcome: MatchRunOutcome,
    versions: Tuple[Tuple[str, object], ...],
    source_refs: Tuple[Mapping, ...] = (),
    result_id: str,
    source_kind: str = "simulation",
) -> MatchResult:
    """把 MatchRunOutcome 转成契约 §7 的 MatchResult 行。

    - source_kind 必须显式声明：真实 SimulationEngine 驱动才传 simulation；
      Fake 引擎的编排验证（E2）必须传 mock，绝不冒充强度证据
      （evaluation-start §6）。
    - blocked/error 不是 complete：完成过单局的记 partial，否则 error，
      invalid_reasons 保留原由；不合成流局。
    - official_ranks 恒为 null：本地分数排序另标方法，不生成官方名次分。
    """
    if outcome.status == "complete":
        status = "complete"
        invalid_reasons: Tuple[str, ...] = ()
    elif outcome.completed_hands > 0:
        status = "partial"
        if outcome.status == "blocked":
            invalid_reasons = ("blocked: {0}".format(outcome.blocked_reason),)
        else:
            invalid_reasons = (outcome.error_reason or "运行未完成",)
    else:
        status = "error"
        if outcome.status == "blocked":
            invalid_reasons = ("blocked: {0}".format(outcome.blocked_reason),)
        else:
            invalid_reasons = (outcome.error_reason or "运行未完成",)

    return MatchResult(
        evaluation_schema_version=EVALUATION_SCHEMA_VERSION,
        result_id=result_id,
        source_kind=source_kind,
        scenario_id=scenario_id,
        pair_id=pair_id,
        game_key=GameKey(
            source_namespace=SIMULATION_SOURCE_NAMESPACE,
            tournament_id=scenario_id,
            game_id=match_id,
        ),
        config=config,
        policy_ids_by_seat=policy_ids_by_seat,
        seat_permutation=seat_permutation,
        expected_hands=config.rounds_per_game,
        completed_hands=outcome.completed_hands,
        scores_before=initial_scores_physical,
        scores_after=outcome.final_scores,
        official_ranks=None,
        status=status,
        invalid_reasons=invalid_reasons,
        runtime_counts=outcome.runtime_counts,
        versions=versions,
        source_refs=source_refs,
    )


@dataclass(frozen=True)
class MatchExperimentOutcome:
    """matches 实验的产物；强度统计在 summarize 阶段进行。"""

    results: Tuple[MatchResult, ...]
    excluded: Tuple[str, ...]
    match_records: Tuple[Tuple[str, MatchRunOutcome], ...]  # (match_id, 运行结果)


async def run_match_experiment(
    experiment: MatchExperiment,
    *,
    engine: Any,
    spec_factory: Callable[..., Any],
    choice_factory: Callable[[WindowKey, Action], Any],
    policies_by_id: Mapping[str, BotPolicy],
    rules: HangmaRules,
    rules_hash: Optional[str],
    now_monotonic: Callable[[], float],
    wall_clock: Optional[Callable[[], float]],
    budget_policy: BudgetPolicy,
    source_kind: str = "simulation",
) -> MatchExperimentOutcome:
    """按声明执行完整同牌山复式实验：seed × 换座 × 稳定/候选。

    - source_kind 显式声明来源：真实 SimulationEngine 传 simulation；
      Fake 引擎编排验证（E2）必须传 mock，mock 永不进入强度结论。
    - 每轮 run：match_id 唯一（含测试策略），pair_id 相同；scenario_id 相同；
    - 换座用 seat_permutation 把逻辑身份映射到实际座位，初始庄家与积分
      同步映射；
    - 单场异常记录后继续其余场次，不崩溃整批；blocked/error 行照常落盘
      （status 非 complete），供汇总排除计数。
    """
    results: List[MatchResult] = []
    excluded: List[str] = []
    records: List[Tuple[str, MatchRunOutcome]] = []

    opponent_logical_ids = [opponent.policy_id for opponent in experiment.opponents]
    for seed_spec in experiment.seeds:
        for permutation in experiment.seat_permutations:
            perm_label = "".join(str(seat) for seat in permutation)
            for test_role, test_policy in (
                ("baseline", experiment.baseline),
                ("challenger", experiment.challenger),
            ):
                logical_ids = [test_policy.policy_id] + opponent_logical_ids
                try:
                    policies_by_seat = seat_policies_from(
                        policies_by_id, permutation, logical_ids
                    )
                    ids_by_seat = policy_ids_by_seat_from(permutation, logical_ids)
                    dealer_physical = permutation[experiment.initial_dealer]
                    # 初始积分声明为逻辑座位口径；换座后按逆映射落到实际座位：
                    # inverse[s] = 实际座位 s 上的逻辑身份。
                    inverse = [permutation.index(seat) for seat in range(4)]
                    scores_physical = tuple(
                        experiment.initial_scores[inverse[seat]] for seat in range(4)
                    )
                except (KeyError, ValueError) as error:
                    excluded.append(
                        "seed={0} perm={1} role={2}：{3}".format(
                            seed_spec.seed, perm_label, test_role, error
                        )
                    )
                    continue

                match_id = "{0}:{1}:{2}:{3}".format(
                    experiment.match_id_prefix,
                    seed_spec.scenario_id,
                    perm_label,
                    test_policy.policy_id,
                )
                pair_id = "{0}:{1}".format(seed_spec.scenario_id, perm_label)
                try:
                    spec = spec_factory(
                        match_id=match_id,
                        scenario_id=seed_spec.scenario_id,
                        config=experiment.tournament_config,
                        seed=seed_spec.seed,
                        initial_dealer=dealer_physical,
                        initial_scores=scores_physical,
                    )
                except Exception as error:
                    excluded.append(
                        "match_id={0}：MatchSpec 构造失败 {1}: {2}".format(
                            match_id, type(error).__name__, error
                        )
                    )
                    continue
                driver_config = MatchDriverConfig(
                    clock_mode=experiment.clock_mode,
                    step_limit=experiment.step_limit,
                    budget_policy=budget_policy,
                    competition_tournament_id=seed_spec.scenario_id,
                )
                try:
                    outcome = await drive_match(
                        engine=engine,
                        spec=spec,
                        policies_by_seat=policies_by_seat,
                        rules=rules,
                        choice_factory=choice_factory,
                        config=driver_config,
                        now_monotonic=now_monotonic,
                        wall_clock=wall_clock,
                    )
                except Exception as error:
                    excluded.append(
                        "match_id={0}：驱动异常 {1}: {2}".format(
                            match_id, type(error).__name__, error
                        )
                    )
                    continue
                records.append((match_id, outcome))
                versions = tuple(
                    sorted(
                        [
                            ("contract_id", "parallel-v1"),
                            ("rules_hash", rules_hash),
                            (
                                "ruleset_version",
                                getattr(getattr(rules, "config", None), "ruleset_version", None),
                            ),
                            ("policy_ids", sorted(logical_ids)),
                            ("simulation_version", experiment.simulation_version),
                            ("driver", "offline.evaluate drive_match (evaluation-v1)"),
                        ],
                        key=lambda item: item[0],
                    )
                )
                try:
                    result = build_match_result(
                        match_id=match_id,
                        scenario_id=seed_spec.scenario_id,
                        pair_id=pair_id,
                        config=experiment.tournament_config,
                        policy_ids_by_seat=ids_by_seat,
                        seat_permutation=permutation,
                        initial_scores_physical=scores_physical,
                        outcome=outcome,
                        versions=versions,
                        source_refs=(
                            {
                                "note": source_kind,
                                "producer": "offline.evaluate.run_match_experiment",
                            },
                        ),
                        result_id="r-{0}".format(match_id),
                        source_kind=source_kind,
                    )
                except ValueError as error:
                    excluded.append(
                        "match_id={0}：结果行构造失败 {1}".format(match_id, error)
                    )
                    continue
                results.append(result)

    return MatchExperimentOutcome(
        results=tuple(results),
        excluded=tuple(excluded),
        match_records=tuple(records),
    )


def write_report_files(out_dir: Path, report: Mapping) -> None:
    """写出 report.json 与 report.md；键序稳定。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (out_dir / "report.md").write_text(render_report_md(report), encoding="utf-8")
