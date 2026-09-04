"""唯一杭麻规则实现必须满足的公开契约。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

from hangma_bot.kernel.actions import Action, CANONICAL_TILE_CODES
from hangma_bot.kernel.observation import PlayerObservation, ScoreVector


class RuleCompleteness(str, Enum):
    """规则分析是否完整；降级表示至少一个动作族分析失败。"""

    COMPLETE = "complete"
    DEGRADED = "degraded"


class CandidateFactKind(str, Enum):
    """候选牌效事实的结果分类；不适用或失败的候选不得伪造数值。

    2026-09-04 集成阶段契约收口：向听与有效牌数学只允许存在于
    ``hangma``；``policy`` 只消费本分类引导的加权，不得重新推演。
    """

    HAND_PROGRESS = "hand_progress"  # 动作后等待状态已按规则引擎口径估计
    WIN = "win"                      # 胡牌候选：动作后即成牌，shanten_after=-1
    NOT_APPLICABLE = "not_applicable"  # 该动作无动作后等待语义（如过）
    ANALYSIS_FAILED = "analysis_failed"  # 分析异常；数值字段不可信，全部为空


@dataclass(frozen=True)
class UsefulTileFact:
    """一种有效牌及其基于当前公开信息的估计剩余张数。

    ``remaining_estimate``：从本人视角按 4 张物理上限扣除本人手牌与
    全部公开可见牌（四家牌河与副露）后的剩余张数估计，取值 0—4；
    不包含对其他玩家手牌的推测，未来牌墙不可见。
    """

    code: str
    remaining_estimate: int

    def __post_init__(self) -> None:
        if self.code not in CANONICAL_TILE_CODES:
            raise ValueError("UsefulTileFact.code 必须是规范牌值")
        if (
            isinstance(self.remaining_estimate, bool)
            or not isinstance(self.remaining_estimate, int)
            or not 0 <= self.remaining_estimate <= 4
        ):
            raise ValueError(
                "UsefulTileFact.remaining_estimate 必须是 0-4 的整数，得到 {0!r}".format(
                    self.remaining_estimate
                )
            )


@dataclass(frozen=True)
class CandidateFacts:
    """一个候选动作的"动作后牌效事实"；由规则模块生产，策略只消费加权。

    契约不变量（2026-09-04 集成阶段裁定）：

    - 事实与 ``RuleCandidate.action_key`` 一一对应，随候选一起传递；
    - ``fact_kind`` 为 ``WIN``/``NOT_APPLICABLE``/``ANALYSIS_FAILED`` 时
      数值字段必须为空或哨兵值，不得伪造向听或有效牌；
    - 吃/碰候选必须给出采用最佳合法后续弃牌后的最佳等待状态，
      ``best_followup_discard`` 即该弃牌的规范牌值；
    - 杠候选 ``replacement_draw_unknown=True``：杠上补牌未知，
      ``shanten_after`` 是补牌前余牌口径，不得假设具体未来摸牌；
    - ``completeness=DEGRADED`` 时 ``note`` 必须给出降级原因或证据。
    """

    fact_kind: CandidateFactKind
    shanten_after: Optional[int]  # 动作后向听；WIN 为 -1，不适用/失败为 None
    useful_tiles: Tuple[UsefulTileFact, ...] = ()  # 最佳等待状态的有效牌；按规范牌序
    best_followup_discard: Optional[str] = None  # 吃/碰后的最佳后续弃牌牌值
    replacement_draw_unknown: bool = False  # 杠后补牌未知时为 True
    completeness: RuleCompleteness = RuleCompleteness.COMPLETE
    note: Optional[str] = None  # 降级原因或证据说明；可审计、人可读

    def __post_init__(self) -> None:
        _require_tuple = isinstance(self.useful_tiles, tuple)
        if not _require_tuple:
            raise ValueError("CandidateFacts.useful_tiles 必须是 tuple")
        if self.best_followup_discard is not None and self.best_followup_discard not in CANONICAL_TILE_CODES:
            raise ValueError("CandidateFacts.best_followup_discard 必须是规范牌值或空")
        non_numeric_kinds = (
            CandidateFactKind.NOT_APPLICABLE,
            CandidateFactKind.ANALYSIS_FAILED,
        )
        if self.fact_kind in non_numeric_kinds:
            if self.shanten_after is not None or self.useful_tiles or self.best_followup_discard:
                raise ValueError(
                    "fact_kind={0} 不得携带向听、有效牌或后续弃牌数值".format(
                        self.fact_kind.value
                    )
                )
        if self.fact_kind is CandidateFactKind.WIN and self.shanten_after != -1:
            raise ValueError("WIN 候选的 shanten_after 必须为 -1（已成牌）")
        if (
            self.completeness is RuleCompleteness.DEGRADED
            and self.fact_kind is CandidateFactKind.ANALYSIS_FAILED
            and not self.note
        ):
            raise ValueError("ANALYSIS_FAILED 必须在 note 中给出失败原因")


@dataclass(frozen=True)
class RuleCandidate:
    """规则引擎确认合法的一个动作及其证据。

    ``facts``：该候选的动作后牌效事实；``None`` 表示未生产（紧急路径
    按设计不运行复杂分析，或实现尚未覆盖该动作族），消费方必须按
    未知处理，不得据此推断向听或有效牌数值。
    """

    action: Action
    action_key: str
    evidence: Tuple[str, ...]
    facts: Optional[CandidateFacts] = None


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


