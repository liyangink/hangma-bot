"""杭麻机会能力离线评测接缝；只调用正式 ``BotPolicy.choose``。

本模块不生成题目、不计算规则或 oracle。题目生成器必须先由 ``hangma``
得到完整合法动作，再为每个动作附上同一口径的外部真值；任一动作缺值时，
本模块仍记录策略行为，但拒绝计算命中与 regret。
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from collections import Counter, defaultdict
from typing import Callable, Optional, Sequence, Tuple

from hangma_bot.policy.interface import (
    BotPolicy,
    DecisionBudget,
    DecisionRequest,
)


OPPORTUNITY_FAMILIES = (
    "multi_wealth_baotou",
    "hu_versus_continue",
    "gang_chain",
    "chain_keep_or_break",
    "catch_play",
    "seven_pairs_closed",
    "competition_situation",
)
"""R18 首版能力家族；报告必须逐项给出，不能按题数混成总分。"""

CASE_SPLITS = ("development", "hidden")

ORACLE_LEVELS = (
    "official_gold_or_rule_dominance",
    "bounded_exhaustive_expectation",
    "declared_conditional_proxy",
    "paired_counterfactual",
)


@dataclass(frozen=True)
class OracleActionValue:
    """一个合法动作在题目 oracle 下的确定值。

    ``value`` 的单位由题目的 ``oracle_version`` 定义；同一题内所有动作必须
    同单位。``error_bound`` 是同单位的双侧绝对误差界。它可以是官方结算、
    穷举期望、条件代理或配对反事实值，不能把不同等级的量直接相加。
    """

    action_key: str
    value: float
    error_bound: float
    oracle_level: str
    evidence: str

    def __post_init__(self) -> None:
        if not isinstance(self.action_key, str) or not self.action_key:
            raise ValueError("OracleActionValue.action_key 必须是非空字符串")
        if type(self.value) not in (int, float) or not math.isfinite(self.value):
            raise ValueError("OracleActionValue.value 必须是有限数")
        if (
            type(self.error_bound) not in (int, float)
            or not math.isfinite(self.error_bound)
            or self.error_bound < 0
        ):
            raise ValueError("OracleActionValue.error_bound 必须是非负有限数")
        if self.oracle_level not in ORACLE_LEVELS:
            raise ValueError("OracleActionValue.oracle_level 未登记")
        if not isinstance(self.evidence, str) or not self.evidence:
            raise ValueError("OracleActionValue.evidence 必须是非空字符串")


@dataclass(frozen=True)
class OpportunityCapabilityCase:
    """一个可分组、可回放的机会能力题。

    ``base_scenario_id`` 是统计单位：同一基础状态的财神数、链深、horizon、
    座位或赛事处境变体必须共享它，并进入同一 ``split``。哈希字段绑定生成器、
    请求和可达见证；具体产物由离线工具保存，本类只在运行时校验边界。
    """

    case_id: str
    base_scenario_id: str
    family: str
    split: str
    generator_seed: int
    rules_hash: str
    generator_sha256: str
    oracle_version: str
    oracle_level: str
    request_sha256: str
    reachability_witness_sha256: str
    request: DecisionRequest
    action_values: Tuple[OracleActionValue, ...]

    def __post_init__(self) -> None:
        for name in (
            "case_id",
            "base_scenario_id",
            "rules_hash",
            "generator_sha256",
            "oracle_version",
            "request_sha256",
            "reachability_witness_sha256",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError("OpportunityCapabilityCase.{0} 必须是非空字符串".format(name))
        if self.family not in OPPORTUNITY_FAMILIES:
            raise ValueError("未知机会家族: {0}".format(self.family))
        if self.split not in CASE_SPLITS:
            raise ValueError("split 必须是 development 或 hidden")
        if self.oracle_level not in ORACLE_LEVELS:
            raise ValueError("oracle_level 未登记")
        if isinstance(self.generator_seed, bool) or not isinstance(self.generator_seed, int):
            raise ValueError("generator_seed 必须是整数")
        if not isinstance(self.request, DecisionRequest):
            raise TypeError("request 必须是 DecisionRequest")
        if not isinstance(self.action_values, tuple):
            raise TypeError("action_values 必须是 tuple")
        keys = [item.action_key for item in self.action_values]
        if len(keys) != len(set(keys)):
            raise ValueError("action_values 不能包含重复动作键")
        legal = {item.action_key for item in self.request.rules.legal_candidates}
        extra = set(keys) - legal
        if extra:
            raise ValueError("oracle 包含题面非法动作: {0}".format(sorted(extra)))
        levels = {item.oracle_level for item in self.action_values}
        if levels and levels != {self.oracle_level}:
            raise ValueError("同题动作值必须与题目使用同一 oracle_level")

    @property
    def oracle_complete(self) -> bool:
        """全部合法动作恰有一个值时才允许计算 regret。"""

        legal = {item.action_key for item in self.request.rules.legal_candidates}
        valued = {item.action_key for item in self.action_values}
        return bool(legal) and valued == legal


@dataclass(frozen=True)
class CapabilityOutcome:
    """一个策略在一道题上的行为与计分；``regret=None`` 表示不可计分。"""

    case_id: str
    base_scenario_id: str
    family: str
    split: str
    status: str
    chosen_action_key: Optional[str]
    optimal_action_keys: Tuple[str, ...]
    regret: Optional[float]
    regret_lower: Optional[float]
    regret_upper: Optional[float]
    error: Optional[str] = None


@dataclass(frozen=True)
class PairedCapabilityOutcome:
    """候选与稳定 V2 在同一题上的配对结果。"""

    candidate: CapabilityOutcome
    baseline: CapabilityOutcome
    capability_gain: Optional[float]
    capability_gain_lower: Optional[float]
    capability_gain_upper: Optional[float]


@dataclass(frozen=True)
class FamilyCapabilitySummary:
    """按基础场景等权聚合的一个能力家族结果。

    一个基础场景可以展开多个财神数、链深或 horizon 变体；先在场景内取均值，
    再在场景间取均值，避免模板展开数量偷偷改变家族权重。
    """

    family: str
    split: str
    case_count: int
    base_scenario_count: int
    scored_case_count: int
    scored_base_scenario_count: int
    mean_candidate_regret: Optional[float]
    mean_baseline_regret: Optional[float]
    mean_capability_gain: Optional[float]
    conservative_capability_gain: Optional[float]
    optimistic_capability_gain: Optional[float]
    candidate_optimal_hit_rate: Optional[float]
    baseline_optimal_hit_rate: Optional[float]
    status_counts: Tuple[Tuple[str, int], ...]


def _optimal_keys(case: OpportunityCapabilityCase) -> Tuple[str, ...]:
    if not case.oracle_complete:
        return ()
    best = max(float(item.value) for item in case.action_values)
    return tuple(sorted(item.action_key for item in case.action_values if float(item.value) == best))


async def evaluate_case(
    policy: BotPolicy,
    case: OpportunityCapabilityCase,
    budget: DecisionBudget,
) -> CapabilityOutcome:
    """经正式策略接口评价一道题；异常转为证据，不让批次静默丢题。"""

    optimal = _optimal_keys(case)
    try:
        plan = await policy.choose(case.request, budget)
    except Exception as exc:  # noqa: BLE001 - 离线评测必须记录任意候选失败
        return CapabilityOutcome(
            case.case_id, case.base_scenario_id, case.family, case.split,
            "POLICY_ERROR", None, optimal, None, None, None,
            type(exc).__name__ + ": " + str(exc)[:240],
        )
    if not plan.candidates:
        return CapabilityOutcome(
            case.case_id, case.base_scenario_id, case.family, case.split,
            "EMPTY_PLAN", None, optimal, None, None, None, "策略返回空候选计划",
        )
    chosen = plan.candidates[0].action_key
    legal = {item.action_key for item in case.request.rules.legal_candidates}
    if chosen not in legal:
        return CapabilityOutcome(
            case.case_id, case.base_scenario_id, case.family, case.split,
            "ILLEGAL_TOP_ACTION", chosen, optimal, None, None, None,
            "首选动作不在规则合法集合",
        )
    if not case.oracle_complete:
        return CapabilityOutcome(
            case.case_id, case.base_scenario_id, case.family, case.split,
            "ORACLE_INCOMPLETE", chosen, (), None, None, None,
            "至少一个合法动作没有同口径 oracle 值",
        )
    values = {item.action_key: float(item.value) for item in case.action_values}
    errors = {item.action_key: float(item.error_bound) for item in case.action_values}
    regret = max(values.values()) - values[chosen]
    if regret < 0 and abs(regret) < 1e-12:
        regret = 0.0
    regret_lower = max(
        0.0,
        max(values[key] - errors[key] for key in values)
        - (values[chosen] + errors[chosen]),
    )
    regret_upper = max(
        0.0,
        max(values[key] + errors[key] for key in values)
        - (values[chosen] - errors[chosen]),
    )
    return CapabilityOutcome(
        case.case_id, case.base_scenario_id, case.family, case.split,
        "SCORED", chosen, optimal, regret, regret_lower, regret_upper,
    )


async def evaluate_pair(
    candidate: BotPolicy,
    baseline: BotPolicy,
    case: OpportunityCapabilityCase,
    budget_factory: Callable[[], DecisionBudget],
) -> PairedCapabilityOutcome:
    """在同一 ``DecisionRequest`` 上分别运行候选与 V2，返回 regret 改善量。"""

    candidate_outcome = await evaluate_case(candidate, case, budget_factory())
    baseline_outcome = await evaluate_case(baseline, case, budget_factory())
    gain = None
    gain_lower = None
    gain_upper = None
    if candidate_outcome.regret is not None and baseline_outcome.regret is not None:
        gain = baseline_outcome.regret - candidate_outcome.regret
        gain_lower = (
            baseline_outcome.regret_lower - candidate_outcome.regret_upper
            if baseline_outcome.regret_lower is not None
            and candidate_outcome.regret_upper is not None
            else None
        )
        gain_upper = (
            baseline_outcome.regret_upper - candidate_outcome.regret_lower
            if baseline_outcome.regret_upper is not None
            and candidate_outcome.regret_lower is not None
            else None
        )
    return PairedCapabilityOutcome(
        candidate_outcome, baseline_outcome, gain, gain_lower, gain_upper,
    )


def _mean(values: Sequence[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None


def _scenario_mean(rows: Sequence[PairedCapabilityOutcome], field: str) -> Optional[float]:
    """先按 ``base_scenario_id`` 均值，再给每个基础场景相同权重。"""

    grouped = defaultdict(list)
    for row in rows:
        value = getattr(row, field)
        if value is not None:
            grouped[row.candidate.base_scenario_id].append(float(value))
    scenario_values = [_mean(values) for values in grouped.values()]
    return _mean([value for value in scenario_values if value is not None])


def summarize_family(
    rows: Sequence[PairedCapabilityOutcome],
    *,
    family: str,
    split: str,
) -> FamilyCapabilitySummary:
    """形成可用于 Pareto/Lexicase 的家族向量分量，不跨家族混分。"""

    if family not in OPPORTUNITY_FAMILIES:
        raise ValueError("未知机会家族: {0}".format(family))
    if split not in CASE_SPLITS:
        raise ValueError("split 必须是 development 或 hidden")
    selected = [
        row for row in rows
        if row.candidate.family == family and row.candidate.split == split
    ]
    for row in selected:
        if (
            row.baseline.family != family
            or row.baseline.split != split
            or row.baseline.case_id != row.candidate.case_id
            or row.baseline.base_scenario_id != row.candidate.base_scenario_id
        ):
            raise ValueError("候选与基线的配对身份不一致")
    scored = [row for row in selected if row.capability_gain is not None]
    statuses = Counter()
    for row in selected:
        statuses["candidate:" + row.candidate.status] += 1
        statuses["baseline:" + row.baseline.status] += 1

    candidate_by_scenario = defaultdict(list)
    baseline_by_scenario = defaultdict(list)
    candidate_hits = defaultdict(list)
    baseline_hits = defaultdict(list)
    for row in scored:
        scenario = row.candidate.base_scenario_id
        candidate_by_scenario[scenario].append(float(row.candidate.regret))
        baseline_by_scenario[scenario].append(float(row.baseline.regret))
        candidate_hits[scenario].append(
            1.0 if row.candidate.chosen_action_key in row.candidate.optimal_action_keys else 0.0
        )
        baseline_hits[scenario].append(
            1.0 if row.baseline.chosen_action_key in row.baseline.optimal_action_keys else 0.0
        )

    return FamilyCapabilitySummary(
        family=family,
        split=split,
        case_count=len(selected),
        base_scenario_count=len({row.candidate.base_scenario_id for row in selected}),
        scored_case_count=len(scored),
        scored_base_scenario_count=len(candidate_by_scenario),
        mean_candidate_regret=_mean([
            value for values in candidate_by_scenario.values()
            if (value := _mean(values)) is not None
        ]),
        mean_baseline_regret=_mean([
            value for values in baseline_by_scenario.values()
            if (value := _mean(values)) is not None
        ]),
        mean_capability_gain=_scenario_mean(scored, "capability_gain"),
        conservative_capability_gain=_scenario_mean(scored, "capability_gain_lower"),
        optimistic_capability_gain=_scenario_mean(scored, "capability_gain_upper"),
        candidate_optimal_hit_rate=_mean([
            value for values in candidate_hits.values()
            if (value := _mean(values)) is not None
        ]),
        baseline_optimal_hit_rate=_mean([
            value for values in baseline_hits.values()
            if (value := _mean(values)) is not None
        ]),
        status_counts=tuple(sorted(statuses.items())),
    )


__all__ = [
    "CASE_SPLITS",
    "OPPORTUNITY_FAMILIES",
    "ORACLE_LEVELS",
    "CapabilityOutcome",
    "FamilyCapabilitySummary",
    "OpportunityCapabilityCase",
    "OracleActionValue",
    "PairedCapabilityOutcome",
    "evaluate_case",
    "evaluate_pair",
    "summarize_family",
]
