"""唯一杭麻规则实现必须满足的公开契约。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

from hangma_bot.kernel.actions import Action
from hangma_bot.kernel.observation import PlayerObservation, ScoreVector


class RuleCompleteness(str, Enum):
    """规则分析是否完整；降级表示至少一个动作族分析失败。"""

    COMPLETE = "complete"
    DEGRADED = "degraded"


@dataclass(frozen=True)
class RuleCandidate:
    """规则引擎确认合法的一个动作及其证据。"""

    action: Action
    action_key: str
    evidence: Tuple[str, ...]


@dataclass(frozen=True)
class RuleIssue:
    """某个规则分支失败或进入保守降级的可审计说明。"""

    area: str
    reason: str


@dataclass(frozen=True)
class RuleAnalysis:
    """一个动作窗口的合法候选、紧急动作和规则降级信息。"""

    legal_candidates: Tuple[RuleCandidate, ...]
    emergency_candidate: Optional[RuleCandidate]
    completeness: RuleCompleteness
    ruleset_version: str
    issues: Tuple[RuleIssue, ...]


@dataclass(frozen=True)
class ActionValidation:
    """提交前本地复核结果；失败原因必须可写入审计。"""

    legal: bool
    reason: Optional[str]


@dataclass(frozen=True)
class WinDescription:
    """计分所需的已确认胡牌事实，不包含推测字段。"""

    observation: PlayerObservation
    winner_seat: int


@dataclass(frozen=True)
class Settlement:
    """规则结算结果；``score_delta`` 固定按座位 0—3。"""

    score_delta: ScoreVector
    fan: int
    details: Tuple[str, ...]


