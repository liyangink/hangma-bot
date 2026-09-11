"""候选结果与赛事目标的共享值对象；只表达数据，不实现规则或评分。

outcome-v1 的终点固定为当前单局结束，积分从候选首动作执行前计算。
所有四家向量按物理座位 0—3；不包含后续单局、阶段名次或赛事效用。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

OUTCOME_SCHEMA_VERSION = 1
MAX_OUTCOME_ATOMS = 256  # 单候选联合支持集上限，限制窗口内计算和审计载荷
MAX_OUTCOME_CANDIDATES = 128  # 整批载荷上限；仍必须覆盖本次全部未拒合法候选
SeatFloatVector = tuple[float, float, float, float]


def _text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(name + " 必须是非空字符串")


def _finite(value: object, name: str) -> None:
    try:
        valid = not isinstance(value, bool) and isinstance(value, (float, int)) and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(name + " 必须是有限数值")


def _vector(value: object) -> None:
    if not isinstance(value, tuple) or len(value) != 4:
        raise ValueError("积分向量必须是按座位 0—3 的四元组")
    for item in value:
        _finite(item, "score_delta")
    try:
        conserved = math.isclose(math.fsum(value), 0.0, rel_tol=0.0, abs_tol=1e-7)
    except OverflowError:
        conserved = False
    if not conserved:
        raise ValueError("四家积分变化必须守恒")


@dataclass(frozen=True)
class OutcomeModelVersion:
    """模型适用条件；运行组合根与制品必须逐项匹配，不能只核对模型名。"""

    model_id: str  # 不可变模型制品标识，正式权重应使用其内容摘要
    ruleset_version: str  # 本地规则语义版本，须与 RuleAnalysis 一致
    rules_hash: str  # rules_context_key：规则源码摘要与有效底分/规则开关的联合摘要
    feature_schema_version: str  # 训练和推理共享的可见特征编码版本
    action_schema_version: str  # 候选动作编码版本
    training_data_id: str  # 可追溯数据 manifest 标识
    continuation_policy_id: str  # 首动作之后的我方续打策略组合
    opponent_pool_id: str  # 续打对手及其权重的冻结标识
    sampler_version: str  # 世界/窗口/候选采样规则版本
    calibration_version: str  # 未校准时明确记为 uncalibrated
    engine_commit: str  # 生成标签所用生产代码提交或内容摘要
    guide_api_version: str  # 标签所依据的官方指南/API 版本

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            _text(getattr(self, name), name)


@dataclass(frozen=True)
class MeanOutcome:
    """四家条件积分均值；不携带或暗示尾部概率。"""

    score_delta: SeatFloatVector  # 单位为桌内积分，顺序为物理座位 0—3

    def __post_init__(self) -> None:
        _vector(self.score_delta)


@dataclass(frozen=True)
class OutcomeAtom:
    """联合分布中的一项四家积分结果；四家相关性在同一项中保留。"""

    score_delta: SeatFloatVector  # 当前单局剩余积分变化，物理座位 0—3
    probability: float  # 无单位，严格大于 0 且不大于 1

    def __post_init__(self) -> None:
        _vector(self.score_delta)
        _finite(self.probability, "probability")
        if not 0 < self.probability <= 1:
            raise ValueError("probability 必须在 (0, 1] 内")


@dataclass(frozen=True)
class JointOutcome:
    """有限支持的四家联合分布；不会对错误概率静默归一化。"""

    atoms: tuple[OutcomeAtom, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.atoms, tuple) or not self.atoms:
            raise ValueError("联合分布必须有非空不可变支持集")
        if len(self.atoms) > MAX_OUTCOME_ATOMS:
            raise ValueError("联合支持集超过工作量上限")
        if any(not isinstance(atom, OutcomeAtom) for atom in self.atoms):
            raise ValueError("atoms 必须全部为 OutcomeAtom")
        if not math.isclose(math.fsum(a.probability for a in self.atoms), 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("联合分布的概率和必须为 1")


@dataclass(frozen=True)
class CandidateOutcome:
    """与规范动作键绑定的结果；不包含合法性或启发式评分。"""

    action_key: str
    estimate: MeanOutcome | JointOutcome

    def __post_init__(self) -> None:
        _text(self.action_key, "action_key")
        if not isinstance(self.estimate, (MeanOutcome, JointOutcome)):
            raise ValueError("estimate 必须明确为均值或联合分布")


@dataclass(frozen=True)
class OutcomeBatch:
    """同一观察的候选结果；缺候选表示未覆盖，消费方不得填零。"""

    observation_key: str  # 完整可见观察的稳定摘要，只用于绑定，不是模型特征
    version: OutcomeModelVersion
    candidates: tuple[CandidateOutcome, ...]

    def __post_init__(self) -> None:
        _text(self.observation_key, "observation_key")
        if not isinstance(self.version, OutcomeModelVersion):
            raise ValueError("version 必须为 OutcomeModelVersion")
        if not isinstance(self.candidates, tuple) or any(not isinstance(c, CandidateOutcome) for c in self.candidates):
            raise ValueError("candidates 必须是 CandidateOutcome 元组")
        if len(self.candidates) > MAX_OUTCOME_CANDIDATES:
            raise ValueError("候选结果超过工作量上限")
        keys = [c.action_key for c in self.candidates]
        if len(set(keys)) != len(keys):
            raise ValueError("候选结果不能包含重复动作键")


class HandObjectiveKind(str, Enum):
    """首批单局目标；达到积分门槛不等于赛事晋级。"""

    EXPECTED_SCORE = "expected_score"
    TARGET_PROBABILITY = "target_probability"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class HandOutcomeObjective:
    """赛事线交给结果消费方的单局目标；未知时必须完整恢复基线。"""

    kind: HandObjectiveKind
    seat: int  # 被评估者物理座位，0—3
    source: str  # 目标来源/配置版本；人工实验须明示，不是官方事实
    target_score_delta: float | None = None  # 同一预测终点下的净增积分门槛，仅门槛目标提供
    reason: str | None = None  # 未知/不适用原因；UNAVAILABLE 必填

    def __post_init__(self) -> None:
        if not isinstance(self.kind, HandObjectiveKind):
            raise ValueError("kind 必须为 HandObjectiveKind")
        if isinstance(self.seat, bool) or not isinstance(self.seat, int) or self.seat not in range(4):
            raise ValueError("seat 必须为物理座位 0—3")
        _text(self.source, "source")
        if self.kind is HandObjectiveKind.TARGET_PROBABILITY:
            _finite(self.target_score_delta, "target_score_delta")
        elif self.target_score_delta is not None:
            raise ValueError("只有门槛目标可以提供 target_score_delta")
        if self.kind is HandObjectiveKind.UNAVAILABLE:
            _text(self.reason, "reason")
        elif self.reason is not None:
            raise ValueError("只有未知目标提供 reason")


@dataclass(frozen=True)
class OutcomeDecisionTrace:
    """随决策计划记录的结果接入证据；旧计划没有该载荷。"""

    status: str  # applied / bypassed / fallback
    reason: str  # 稳定机器原因，不记录模型异常原文或敏感标识
    expected_version: OutcomeModelVersion
    objective: HandOutcomeObjective | None  # 目标生产失败时为空
    batch: OutcomeBatch | None = None  # 尚未收到或未采用有效结果时可空

    def __post_init__(self) -> None:
        if self.status not in ("applied", "bypassed", "fallback"):
            raise ValueError("未知结果接入状态")
        _text(self.reason, "reason")
        if not isinstance(self.expected_version, OutcomeModelVersion):
            raise ValueError("expected_version 类型错误")
        if self.objective is not None and not isinstance(self.objective, HandOutcomeObjective):
            raise ValueError("objective 类型错误")
        if self.batch is not None and not isinstance(self.batch, OutcomeBatch):
            raise ValueError("batch 类型错误")
        if self.status == "applied" and (self.batch is None or self.objective is None):
            raise ValueError("已应用结果必须保存目标及结果批次")
