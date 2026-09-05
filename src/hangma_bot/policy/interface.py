"""线上唯一决策接缝。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Tuple

from hangma_bot.hangma.interface import RuleAnalysis
from hangma_bot.kernel.actions import Action, WindowKey
from hangma_bot.kernel.observation import CompetitionContext, PlayerObservation


@dataclass(frozen=True)
class RejectedAttempt:
    """官方已明确确认未执行的历史动作；模糊提交绝不能出现在这里。"""

    action_key: str
    official_code: str
    attempt_no: int
    based_on_authoritative_seq: int


@dataclass(frozen=True)
class DecisionBudget:
    """单调时钟上的三段预算；同一窗口刷新后必须复用原值。"""

    enhancement_deadline_monotonic: float  # 到点取消模型或复杂分析
    fallback_deadline_monotonic: float  # 到点必须选择已经准备好的保底候选
    latest_send_at_monotonic: float  # 到点后适配器不得再发出动作 POST

    def __post_init__(self) -> None:
        if not (
            self.enhancement_deadline_monotonic
            <= self.fallback_deadline_monotonic
            <= self.latest_send_at_monotonic
        ):
            raise ValueError("决策预算必须按增强、保底、最晚发送的顺序递增")


@dataclass(frozen=True)
class DecisionRequest:
    """策略在一个动作窗口内能够读取的全部不可变输入。"""

    observation: PlayerObservation
    competition: CompetitionContext
    rules: RuleAnalysis
    decision_id: str  # 同一 ``WindowKey`` 的重新规划保持不变
    trigger_seq: int
    window_key: WindowKey
    rejected_attempts: Tuple[RejectedAttempt, ...]


@dataclass(frozen=True)
class ScorePart:
    """一个稳定、可排序的候选评分分项。"""

    name: str
    value: float


@dataclass(frozen=True)
class RankedCandidate:
    """经过策略评分的本地合法候选。"""

    action: Action
    action_key: str
    rank: int  # 从 1 开始的执行顺序；策略层内同分按 action_key，全部未知可优先紧急候选
    total_score: float  # 数值评分分项之和；跨优先层不能用此字段重新排序
    score_parts: Tuple[ScorePart, ...]
    reasons: Tuple[str, ...]
    is_emergency: bool = False


@dataclass(frozen=True)
class DecisionPlan:
    """同一次规划产生的完整候选顺序；不执行网络提交。"""

    decision_id: str
    window_key: WindowKey
    based_on_authoritative_seq: int
    revision: int
    candidates: Tuple[RankedCandidate, ...]
    degraded_reasons: Tuple[str, ...]


class BotPolicy(Protocol):
    """按时间预算给规则候选排序的唯一线上决策接口。"""

    async def choose(
        self,
        request: DecisionRequest,
        budget: DecisionBudget,
    ) -> DecisionPlan:
        """返回完整有序计划；不得提交 HTTP、写文件或读取完整世界状态。"""

        ...
