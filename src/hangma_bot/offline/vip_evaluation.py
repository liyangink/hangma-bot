"""VIP 路线策略的自然完整桌评测核验。

只消费冻结抽样框与既有 MatchResult，不读取完整世界，也不推进规则。
抽中一个牌山根后必须补齐四座 A/C 八行；任何未完成都会使整批自然
积分估计不可确认，不能对幸存桌求均值。
"""

from __future__ import annotations

from dataclasses import dataclass
from math import prod
from typing import Mapping, Optional, Sequence, Tuple

from .evaluation_results import (
    SIMULATION_SOURCE_NAMESPACE,
    MatchResult,
    check_complete_consistency,
)
from .evaluation_statistics import table_score_delta


SeatPermutation = Tuple[int, int, int, int]


@dataclass(frozen=True)
class FrozenRoot:
    """结果盲抽样框中的一个牌山根，含四个焦点座位映射。

    strata、draws 与 permutations 按同一映射顺序排列。strata 仅能由各
    映射焦点座位的首个单局起手可见事实生成；draws 是筛选用的固定均匀
    随机数，不是未来牌墙或对局结果。root_id 对应 MatchResult.scenario_id。
    """

    root_id: str
    permutations: Tuple[SeatPermutation, SeatPermutation, SeatPermutation, SeatPermutation]
    strata: Tuple[str, str, str, str]
    draws: Tuple[float, float, float, float]

    def __post_init__(self) -> None:
        if not self.root_id:
            raise ValueError("root_id 不能为空")
        if len(self.permutations) != 4 or len(set(self.permutations)) != 4:
            raise ValueError("一个牌山根必须有四个不同座位映射")
        for permutation in self.permutations:
            if tuple(sorted(permutation)) != (0, 1, 2, 3):
                raise ValueError("座位映射必须是 0—3 的排列")
        if {permutation[0] for permutation in self.permutations} != {0, 1, 2, 3}:
            raise ValueError("四个映射必须覆盖焦点身份的四个实际座位")
        if len(self.strata) != 4 or not all(self.strata):
            raise ValueError("每个映射必须有结果盲层标签")
        if len(self.draws) != 4 or any(
            not isinstance(draw, (int, float)) or isinstance(draw, bool)
            or not 0 <= draw < 1 for draw in self.draws
        ):
            raise ValueError("筛选随机数必须在 [0,1) 内")


@dataclass(frozen=True)
class RootAudit:
    """一根的完整性与四个焦点桌内积分配对差；缺失时差值为空。"""

    root_id: str
    selected: bool
    inclusion_probability: float
    issues: Tuple[str, ...]
    deltas: Optional[Tuple[float, float, float, float]]


@dataclass(frozen=True)
class VipBatchAudit:
    """批次核验结果；自然估计只有全部抽中根完整时可用。

    estimate 单位为每个焦点完整桌赛的净积分差，按冻结抽样框四座自然
    平均和牌山根包含概率还原；不是阶段晋级概率或奖金金额。
    """

    roots: Tuple[RootAudit, ...]
    frame_root_count: int
    selected_root_count: int
    complete_root_count: int
    frame_stratum_counts: Tuple[Tuple[str, int], ...]
    confirmable: bool
    natural_score_delta: Optional[float]
    stratum_contributions: Tuple[Tuple[str, float], ...]


def audit_vip_batch(
    frame: Sequence[FrozenRoot],
    selection_probabilities: Mapping[str, float],
    results: Sequence[MatchResult],
    *,
    baseline_policy_id: str,
    challenger_policy_id: str,
) -> VipBatchAudit:
    """核验预登记抽样框及 A/C 八行，并计算设计加权自然积分差。

    输入必须是同一冻结实验的完整结果行，不能预先过滤异常行。错误的
    抽样框或多余/重复行直接报错；运行缺失与机械缺口保留为不可确认原因。
    """

    if not frame or not baseline_policy_id or not challenger_policy_id:
        raise ValueError("抽样框与 A/C 策略身份不能为空")
    if baseline_policy_id == challenger_policy_id:
        raise ValueError("A/C 策略身份必须不同")
    root_ids = [root.root_id for root in frame]
    if len(root_ids) != len(set(root_ids)):
        raise ValueError("抽样框牌山根身份重复")
    used_strata = {stratum for root in frame for stratum in root.strata}
    if set(selection_probabilities) != used_strata:
        raise ValueError("筛选概率必须恰好覆盖抽样框层标签")
    for stratum, probability in selection_probabilities.items():
        if isinstance(probability, bool) or not isinstance(probability, (int, float)) or not 0 < probability <= 1:
            raise ValueError(f"层 {stratum} 的筛选概率必须在 (0,1] 内")

    indexed: dict[tuple[str, SeatPermutation, str], MatchResult] = {}
    expected_keys = {
        (root.root_id, permutation, policy_id)
        for root in frame
        for permutation in root.permutations
        for policy_id in (baseline_policy_id, challenger_policy_id)
    }
    for result in results:
        if result.scenario_id not in root_ids:
            raise ValueError(f"结果行来自抽样框外牌山根: {result.result_id}")
        seat = result.seat_permutation[0]
        policy_id = result.policy_ids_by_seat[seat]
        if policy_id not in (baseline_policy_id, challenger_policy_id):
            raise ValueError(f"结果行焦点策略身份不属 A/C: {result.result_id}")
        key = (result.scenario_id, result.seat_permutation, policy_id)
        if key not in expected_keys:
            raise ValueError(f"结果行座位映射不属于冻结抽样框: {result.result_id}")
        if key in indexed:
            raise ValueError(f"同一牌山根/映射/策略存在重复结果行: {key}")
        indexed[key] = result

    audits = []
    contributions = {stratum: 0.0 for stratum in used_strata}
    batch_versions: Optional[Tuple[str, str, str]] = None
    batch_opponents: Optional[Tuple[str, str, str]] = None
    stratum_counts = {
        stratum: sum(label == stratum for root in frame for label in root.strata)
        for stratum in used_strata
    }
    for root in frame:
        probabilities = tuple(selection_probabilities[label] for label in root.strata)
        selected = any(draw < probability for draw, probability in zip(root.draws, probabilities))
        rho = 1.0 - prod(1.0 - probability for probability in probabilities)
        issues: list[str] = []
        deltas: list[float] = []
        for index, permutation in enumerate(root.permutations):
            mapping_issues: list[str] = []
            pair = [indexed.get((root.root_id, permutation, policy_id)) for policy_id in
                    (baseline_policy_id, challenger_policy_id)]
            if not selected:
                if any(row is not None for row in pair):
                    raise ValueError(f"未抽中根却存在运行结果: {root.root_id}")
                continue
            if any(row is None for row in pair):
                issues.append(f"映射 {index} 缺少 A 或 C 结果行")
                continue
            baseline, challenger = pair
            assert baseline is not None and challenger is not None
            if baseline.source_kind != "simulation" or challenger.source_kind != "simulation":
                mapping_issues.append(f"映射 {index} 来源不是生产模拟器")
            expected_pair_id = f"{root.root_id}:{''.join(map(str, permutation))}"
            if baseline.pair_id != expected_pair_id or challenger.pair_id != expected_pair_id:
                mapping_issues.append(f"映射 {index} 配对身份未绑定根和座位映射")
            if baseline.config is None or challenger.config is None:
                mapping_issues.append(f"映射 {index} 缺少赛事配置")
            elif baseline.config != challenger.config:
                mapping_issues.append(f"映射 {index} 赛事配置不一致")
            if baseline.scores_before is None or challenger.scores_before is None:
                mapping_issues.append(f"映射 {index} 缺少初始积分")
            elif baseline.scores_before != challenger.scores_before:
                mapping_issues.append(f"映射 {index} 初始积分不一致")
            if baseline.game_key is None or challenger.game_key is None:
                mapping_issues.append(f"映射 {index} 缺少来源场次身份")
            elif (baseline.game_key.source_namespace != SIMULATION_SOURCE_NAMESPACE
                  or challenger.game_key.source_namespace != SIMULATION_SOURCE_NAMESPACE
                  or baseline.game_key.tournament_id != root.root_id
                  or challenger.game_key.tournament_id != root.root_id):
                mapping_issues.append(f"映射 {index} 来源场次未绑定牌山根")
            a_versions, c_versions = dict(baseline.versions), dict(challenger.versions)
            required_versions: list[str] = []
            for version_key in ("rules_hash", "ruleset_version", "simulation_version"):
                a_version, c_version = a_versions.get(version_key), c_versions.get(version_key)
                if not isinstance(a_version, str) or not a_version or not isinstance(c_version, str) or not c_version:
                    mapping_issues.append(f"映射 {index} 缺少 {version_key}")
                elif a_version != c_version:
                    mapping_issues.append(f"映射 {index} {version_key} 不一致")
                else:
                    required_versions.append(a_version)
            if len(required_versions) == 3:
                version_tuple = tuple(required_versions)
                if batch_versions is None:
                    batch_versions = version_tuple
                elif batch_versions != version_tuple:
                    mapping_issues.append(f"映射 {index} 与同批规则/模拟版本不一致")
            if baseline.config is not None:
                rule_version = a_versions.get("ruleset_version")
                if rule_version != baseline.config.rules.ruleset_version:
                    mapping_issues.append(f"映射 {index} 规则版本与赛事配置不一致")
            opponent_ids = tuple(baseline.policy_ids_by_seat[permutation[logical]] for logical in (1, 2, 3))
            if any(policy_id is None for policy_id in opponent_ids):
                mapping_issues.append(f"映射 {index} 缺少对手策略身份")
            elif batch_opponents is None:
                batch_opponents = opponent_ids
            elif batch_opponents != opponent_ids:
                mapping_issues.append(f"映射 {index} 对手池身份与同批不一致")
            for seat in range(4):
                if seat != permutation[0] and baseline.policy_ids_by_seat[seat] != challenger.policy_ids_by_seat[seat]:
                    mapping_issues.append(f"映射 {index} 对手策略不一致")
            for arm, row in (("A", baseline), ("C", challenger)):
                consistency = check_complete_consistency(row)
                if (row.status != "complete" or consistency
                    or row.expected_hands is None
                    or row.completed_hands != row.expected_hands):
                    mapping_issues.append(f"映射 {index} {arm} 未完成: {row.status} {','.join(row.invalid_reasons)} {consistency}")
                if row.expected_hands is None or row.expected_hands <= 0:
                    mapping_issues.append(f"映射 {index} {arm} 缺少计划单局数")
                elif row.config is not None and row.expected_hands != row.config.rounds_per_game:
                    mapping_issues.append(f"映射 {index} {arm} 计划单局数与赛事配置不一致")
            c_counts = challenger.runtime_counts
            if c_counts is None or c_counts.fallbacks is None:
                mapping_issues.append(f"映射 {index} C 缺少回退审计计数")
            elif c_counts.fallbacks:
                mapping_issues.append(f"映射 {index} C 发生 {c_counts.fallbacks} 次回退")
            if c_counts is None or c_counts.illegal_choices is None:
                mapping_issues.append(f"映射 {index} C 缺少非法选择审计计数")
            elif c_counts.illegal_choices:
                mapping_issues.append(f"映射 {index} C 发生 {c_counts.illegal_choices} 次非法选择")
            if c_counts is None or c_counts.timeouts is None:
                mapping_issues.append(f"映射 {index} C 缺少超时审计计数")
            elif c_counts.timeouts:
                mapping_issues.append(f"映射 {index} C 发生 {c_counts.timeouts} 次超时")
            if not mapping_issues:
                a_score = table_score_delta(baseline, baseline_policy_id)
                c_score = table_score_delta(challenger, challenger_policy_id)
                if a_score is None or c_score is None:
                    mapping_issues.append(f"映射 {index} 缺少确认积分")
                else:
                    deltas.append(c_score - a_score)
            issues.extend(mapping_issues)
        complete_deltas = tuple(deltas) if selected and not issues and len(deltas) == 4 else None
        if complete_deltas is not None:
            for index, delta in enumerate(complete_deltas):
                contributions[root.strata[index]] += delta / (4 * len(frame) * rho)
        audits.append(RootAudit(root.root_id, selected, rho, tuple(issues), complete_deltas))

    confirmable = any(root.selected for root in audits) and all(
        not root.selected or root.deltas is not None for root in audits
    )
    counts = dict(
        frame_root_count=len(frame),
        selected_root_count=sum(root.selected for root in audits),
        complete_root_count=sum(root.deltas is not None for root in audits),
        frame_stratum_counts=tuple(sorted(stratum_counts.items())),
    )
    if not confirmable:
        return VipBatchAudit(tuple(audits), **counts, confirmable=False,
                             natural_score_delta=None, stratum_contributions=())
    return VipBatchAudit(
        tuple(audits), **counts, confirmable=True,
        natural_score_delta=sum(contributions.values()),
        stratum_contributions=tuple(sorted(contributions.items())),
    )
