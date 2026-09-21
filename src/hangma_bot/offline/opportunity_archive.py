"""杭麻机会优先演化的 Pareto/Lexicase 研究档案。

档案只消费已经冻结的隐藏能力摘要和完整桌安全证据，不读取题面，也不调用
策略。每个机会分层保留为独立目标；成本、题数和自然触发频率不参与能力
排序，避免低频高收益专长再次被一个总均分淹没。
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Optional, Sequence, Tuple

from hangma_bot.offline.opportunity_capability import OPPORTUNITY_FAMILIES


OBJECTIVE_ADMISSION_STATUSES = (
    "BASELINE_ANCHOR",
    "MEASURED",
    "SPECIALIST_PASS",
    "FAIL",
)

TABLE_SAFETY_STATUSES = (
    "BASELINE_ANCHOR",
    "PASS_NONINFERIOR",
    "INCONCLUSIVE_NO_HARM_SIGNAL",
    "FAIL_MATERIAL_DEGRADATION",
    "NOT_EVALUATED",
)

_TABLE_ARCHIVE_ELIGIBLE = {
    "BASELINE_ANCHOR",
    "PASS_NONINFERIOR",
    "INCONCLUSIVE_NO_HARM_SIGNAL",
}


def _finite(name: str, value: float) -> None:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("{0} 必须是有限数".format(name))


@dataclass(frozen=True)
class OpportunityObjectiveScore:
    """候选在一个冻结机会分层上的隐藏集结果。

    ``conservative_gain`` 是相对稳定 V2 的保守 regret 改善量，越大越好。
    ``candidate_regret`` 另行保留绝对缺口，防止“相对 V2 无变化”被误写成
    已解决。一个候选必须覆盖本批全部活跃目标，缺测不会被当作零分。
    """

    objective_id: str
    family: str
    admission_status: str
    mean_gain: float
    conservative_gain: float
    candidate_regret: float
    scored_base_scenarios: int
    expected_base_scenarios: int
    regression_count: int
    paired_counterfactual_supported: bool
    evidence: str

    def __post_init__(self) -> None:
        if not isinstance(self.objective_id, str) or not self.objective_id:
            raise ValueError("objective_id 必须是非空字符串")
        if self.family not in OPPORTUNITY_FAMILIES:
            raise ValueError("未知机会家族: {0}".format(self.family))
        if not self.objective_id.startswith(self.family + "/"):
            raise ValueError("objective_id 必须以机会家族名为前缀")
        if self.admission_status not in OBJECTIVE_ADMISSION_STATUSES:
            raise ValueError("未知机会目标准入状态")
        _finite("mean_gain", self.mean_gain)
        _finite("conservative_gain", self.conservative_gain)
        _finite("candidate_regret", self.candidate_regret)
        if self.conservative_gain > self.mean_gain + 1e-12:
            raise ValueError("保守增益不能高于点估计增益")
        if self.candidate_regret < 0:
            raise ValueError("candidate_regret 不能为负")
        for name in (
            "scored_base_scenarios",
            "expected_base_scenarios",
            "regression_count",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("{0} 必须是非负整数".format(name))
        if self.scored_base_scenarios > self.expected_base_scenarios:
            raise ValueError("已计分基础场景数不能超过预期数")
        if not isinstance(self.paired_counterfactual_supported, bool):
            raise TypeError("paired_counterfactual_supported 必须是 bool")
        if not isinstance(self.evidence, str) or not self.evidence:
            raise ValueError("evidence 必须是非空字符串")

    @property
    def complete(self) -> bool:
        """该分层全部基础场景均有分数。"""

        return (
            self.expected_base_scenarios > 0
            and self.scored_base_scenarios == self.expected_base_scenarios
        )


@dataclass(frozen=True)
class TableSafetyEvidence:
    """候选相对稳定 V2 的完整桌安全证据。"""

    status: str
    source_units: int
    complete_tables: int
    paired_score_delta_mean: Optional[float]
    execution_failure_count: int
    evidence: str

    def __post_init__(self) -> None:
        if self.status not in TABLE_SAFETY_STATUSES:
            raise ValueError("未知完整桌安全状态")
        for name in ("source_units", "complete_tables", "execution_failure_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("{0} 必须是非负整数".format(name))
        if self.paired_score_delta_mean is not None:
            _finite("paired_score_delta_mean", self.paired_score_delta_mean)
        if self.status in {"PASS_NONINFERIOR", "INCONCLUSIVE_NO_HARM_SIGNAL"}:
            if self.source_units == 0 or self.complete_tables == 0:
                raise ValueError("候选完整桌安全状态必须有实际来源单元和完整桌")
            if self.paired_score_delta_mean is None:
                raise ValueError("候选完整桌安全状态必须有配对积分差")
        if not isinstance(self.evidence, str) or not self.evidence:
            raise ValueError("evidence 必须是非空字符串")


@dataclass(frozen=True)
class OpportunityArchiveCandidate:
    """一个候选进入机会档案所需的冻结摘要。"""

    candidate_id: str
    source_sha256: str
    objectives: Tuple[OpportunityObjectiveScore, ...]
    table_safety: TableSafetyEvidence
    author_cost_note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_id, str) or not self.candidate_id:
            raise ValueError("candidate_id 必须是非空字符串")
        if (
            not isinstance(self.source_sha256, str)
            or len(self.source_sha256) != 64
            or any(char not in "0123456789abcdef" for char in self.source_sha256)
        ):
            raise ValueError("source_sha256 必须是 64 位小写十六进制")
        if not isinstance(self.objectives, tuple):
            raise TypeError("objectives 必须是 tuple")
        ids = [item.objective_id for item in self.objectives]
        if len(ids) != len(set(ids)):
            raise ValueError("同一候选不能重复机会目标")
        if not isinstance(self.table_safety, TableSafetyEvidence):
            raise TypeError("table_safety 必须是 TableSafetyEvidence")
        if not isinstance(self.author_cost_note, str):
            raise TypeError("author_cost_note 必须是字符串")


@dataclass(frozen=True)
class ArchiveCandidateDecision:
    """一个候选的档案裁定。"""

    candidate_id: str
    eligible: bool
    exclusion_reasons: Tuple[str, ...]
    dominated_by: Tuple[str, ...]
    pareto_elite: bool
    lexicase_parent: bool


@dataclass(frozen=True)
class OpportunityArchiveResult:
    """一次冻结档案构建结果。"""

    active_objective_ids: Tuple[str, ...]
    baseline_candidate_id: str
    pareto_elite_ids: Tuple[str, ...]
    lexicase_parent_ids: Tuple[str, ...]
    decisions: Tuple[ArchiveCandidateDecision, ...]


def _objective_map(
    candidate: OpportunityArchiveCandidate,
) -> dict[str, OpportunityObjectiveScore]:
    return {item.objective_id: item for item in candidate.objectives}


def _eligibility_reasons(
    candidate: OpportunityArchiveCandidate,
    active_objective_ids: Sequence[str],
    *,
    baseline_candidate_id: str,
) -> Tuple[str, ...]:
    scores = _objective_map(candidate)
    reasons = []
    missing = [item for item in active_objective_ids if item not in scores]
    extra = sorted(set(scores) - set(active_objective_ids))
    if missing:
        reasons.append("MISSING_ACTIVE_OBJECTIVES:" + ",".join(missing))
    if extra:
        reasons.append("UNDECLARED_OBJECTIVES:" + ",".join(extra))
    for objective_id in active_objective_ids:
        score = scores.get(objective_id)
        if score is None:
            continue
        if not score.complete:
            reasons.append("INCOMPLETE_OBJECTIVE:" + objective_id)
        if score.admission_status == "FAIL":
            reasons.append("HIDDEN_OBJECTIVE_FAILED:" + objective_id)
        if (
            score.admission_status == "SPECIALIST_PASS"
            and not score.paired_counterfactual_supported
        ):
            reasons.append("SPECIALIST_WITHOUT_COUNTERFACTUAL_SUPPORT:" + objective_id)
        if (
            candidate.candidate_id != baseline_candidate_id
            and score.admission_status == "BASELINE_ANCHOR"
        ):
            reasons.append("NONBASELINE_USES_BASELINE_OBJECTIVE:" + objective_id)
    if candidate.table_safety.status not in _TABLE_ARCHIVE_ELIGIBLE:
        reasons.append("TABLE_SAFETY:" + candidate.table_safety.status)
    if (
        candidate.candidate_id != baseline_candidate_id
        and candidate.table_safety.status == "BASELINE_ANCHOR"
    ):
        reasons.append("NONBASELINE_USES_BASELINE_TABLE_STATUS")
    if candidate.table_safety.execution_failure_count:
        reasons.append("TABLE_EXECUTION_FAILURES")
    if candidate.candidate_id != baseline_candidate_id and not any(
        item.admission_status == "SPECIALIST_PASS" for item in candidate.objectives
    ):
        reasons.append("NO_HIDDEN_SPECIALIST_PASS")
    return tuple(reasons)


def dominates(
    left: OpportunityArchiveCandidate,
    right: OpportunityArchiveCandidate,
    active_objective_ids: Sequence[str],
) -> bool:
    """按逐目标保守增益判断 Pareto 支配；不计算跨目标总分。"""

    left_scores = _objective_map(left)
    right_scores = _objective_map(right)
    if any(item not in left_scores or item not in right_scores for item in active_objective_ids):
        raise ValueError("Pareto 比较要求双方覆盖全部活跃目标")
    weakly_better = all(
        left_scores[item].conservative_gain
        >= right_scores[item].conservative_gain
        for item in active_objective_ids
    )
    strictly_better = any(
        left_scores[item].conservative_gain
        > right_scores[item].conservative_gain
        for item in active_objective_ids
    )
    return weakly_better and strictly_better


def lexicase_survivors(
    candidates: Sequence[OpportunityArchiveCandidate],
    objective_order: Sequence[str],
    *,
    epsilon: float = 0.0,
) -> Tuple[str, ...]:
    """按给定目标顺序执行一次可审计的 epsilon-Lexicase 过滤。"""

    _finite("epsilon", epsilon)
    if epsilon < 0:
        raise ValueError("epsilon 不能为负")
    if len(objective_order) != len(set(objective_order)):
        raise ValueError("Lexicase 目标顺序不能重复")
    survivors = list(candidates)
    for objective_id in objective_order:
        if not survivors:
            break
        values = []
        for candidate in survivors:
            score = _objective_map(candidate).get(objective_id)
            if score is None:
                raise ValueError("Lexicase 候选缺少目标: {0}".format(objective_id))
            values.append(score.conservative_gain)
        best = max(values)
        survivors = [
            candidate for candidate in survivors
            if _objective_map(candidate)[objective_id].conservative_gain >= best - epsilon
        ]
    return tuple(sorted(candidate.candidate_id for candidate in survivors))


def _lexicase_parent_pool(
    candidates: Sequence[OpportunityArchiveCandidate],
    active_objective_ids: Sequence[str],
    *,
    epsilon: float,
) -> Tuple[str, ...]:
    """让每个目标各先出现一次，形成确定性的专长父代并集。"""

    pool = set()
    ordered = tuple(active_objective_ids)
    for index in range(len(ordered)):
        rotation = ordered[index:] + ordered[:index]
        pool.update(lexicase_survivors(candidates, rotation, epsilon=epsilon))
    return tuple(sorted(pool))


def build_opportunity_archive(
    candidates: Iterable[OpportunityArchiveCandidate],
    *,
    active_objective_ids: Sequence[str],
    baseline_candidate_id: str,
    lexicase_epsilon: float = 0.0,
) -> OpportunityArchiveResult:
    """构建研究档案；完整桌实质退化、缺测和隐藏失败先退出。"""

    candidate_rows = tuple(candidates)
    if not candidate_rows:
        raise ValueError("候选集合不能为空")
    objective_ids = tuple(active_objective_ids)
    if not objective_ids or len(objective_ids) != len(set(objective_ids)):
        raise ValueError("活跃目标必须非空且不重复")
    ids = [item.candidate_id for item in candidate_rows]
    if len(ids) != len(set(ids)):
        raise ValueError("candidate_id 不能重复")
    if baseline_candidate_id not in ids:
        raise ValueError("稳定基线必须在候选集合中")
    baseline = next(
        item for item in candidate_rows if item.candidate_id == baseline_candidate_id
    )
    if baseline.table_safety.status != "BASELINE_ANCHOR" or any(
        item.admission_status != "BASELINE_ANCHOR" for item in baseline.objectives
    ):
        raise ValueError("稳定基线必须使用 BASELINE_ANCHOR 证据状态")

    reasons_by_id = {
        item.candidate_id: _eligibility_reasons(
            item,
            objective_ids,
            baseline_candidate_id=baseline_candidate_id,
        )
        for item in candidate_rows
    }
    eligible = tuple(
        item for item in candidate_rows if not reasons_by_id[item.candidate_id]
    )
    dominated_by = {
        item.candidate_id: tuple(sorted(
            other.candidate_id
            for other in eligible
            if other.candidate_id != item.candidate_id
            and dominates(other, item, objective_ids)
        ))
        for item in eligible
    }
    pareto_ids = tuple(sorted(
        item.candidate_id for item in eligible if not dominated_by[item.candidate_id]
    ))
    pareto_candidates = tuple(
        item for item in eligible if item.candidate_id in pareto_ids
    )
    lexicase_ids = _lexicase_parent_pool(
        pareto_candidates,
        objective_ids,
        epsilon=lexicase_epsilon,
    ) if pareto_candidates else ()

    decisions = tuple(
        ArchiveCandidateDecision(
            candidate_id=item.candidate_id,
            eligible=not reasons_by_id[item.candidate_id],
            exclusion_reasons=reasons_by_id[item.candidate_id],
            dominated_by=dominated_by.get(item.candidate_id, ()),
            pareto_elite=item.candidate_id in pareto_ids,
            lexicase_parent=item.candidate_id in lexicase_ids,
        )
        for item in sorted(candidate_rows, key=lambda row: row.candidate_id)
    )
    return OpportunityArchiveResult(
        active_objective_ids=objective_ids,
        baseline_candidate_id=baseline_candidate_id,
        pareto_elite_ids=pareto_ids,
        lexicase_parent_ids=lexicase_ids,
        decisions=decisions,
    )


__all__ = [
    "OBJECTIVE_ADMISSION_STATUSES",
    "TABLE_SAFETY_STATUSES",
    "ArchiveCandidateDecision",
    "OpportunityArchiveCandidate",
    "OpportunityArchiveResult",
    "OpportunityObjectiveScore",
    "TableSafetyEvidence",
    "build_opportunity_archive",
    "dominates",
    "lexicase_survivors",
]
