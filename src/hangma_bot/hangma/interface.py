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
    NOT_APPLICABLE = "not_applicable"  # 无等待语义；旧版响应过牌事实仍可读取
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
    value_facts: Optional[CandidateValueFacts] = None  # 可选有限路线分析；缺失不代表无路线


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


class ValueCoverage(str, Enum):
    """仅相对“一次未来摸牌直接胡”的分析范围；不声称穷尽多步路线。"""

    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ValueAnalysisLimits:
    """可选规则分析的固定工作量上限；不依赖墙上时间或策略权重。"""

    max_expansions: int = 2048  # 整次请求的等待手牌与逐牌成胡检查节点上限
    max_routes_per_candidate: int = 128  # 每动作返回的条件结算分组数上限

    def __post_init__(self) -> None:
        for name in ("max_expansions", "max_routes_per_candidate"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(name + " 必须是正整数")


@dataclass(frozen=True)
class ValueConditions:
    """未来摸牌成胡的条件见证，不能当作已经发生的胡牌观察。

    必须先执行所属候选及 followup_discard，再在无人结束单局、本人没有
    其他吃碰杠/弃牌的条件下，摸到路线 useful_tiles 中的一张并立即胡。
    普通摸牌与杠补来源分开，不假设两者会摸到相同物理牌。
    """

    draw_kind: str  # normal / replacement；杠补不等候本人下一常规摸牌
    pre_draw_hand: Tuple[str, ...]  # 本人假定摸前暗牌，规范牌序，不含未来摸牌
    meld_count: int  # 吃碰杠每副计一组，仅用于本路线分解
    chain_count: int  # 条件成立时连续飘/杠动作数，非未来预估次数
    chain_piao: int  # 同一链中已飘出的白板张数
    baotou: bool  # 条件摸牌后的爆头，按同源生命周期推演

    def __post_init__(self) -> None:
        if self.draw_kind not in ("normal", "replacement"):
            raise ValueError("draw_kind 必须是 normal 或 replacement")
        if not isinstance(self.pre_draw_hand, tuple) or any(
            code not in CANONICAL_TILE_CODES for code in self.pre_draw_hand
        ):
            raise ValueError("pre_draw_hand 必须是规范牌值 tuple")
        if isinstance(self.meld_count, bool) or not isinstance(self.meld_count, int) or not 0 <= self.meld_count <= 4:
            raise ValueError("meld_count 必须是 0—4 的整数")
        if len(self.pre_draw_hand) != 13 - 3 * self.meld_count:
            raise ValueError("pre_draw_hand 必须是该副露数对应的摸前暗牌")
        if any(self.pre_draw_hand.count(code) > 4 for code in set(self.pre_draw_hand)):
            raise ValueError("pre_draw_hand 每种牌不能超过四张")
        for name in ("chain_count", "chain_piao"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(name + " 必须是非负整数")
        if self.chain_piao > self.chain_count or self.chain_piao + self.pre_draw_hand.count("白") > 4:
            raise ValueError("条件中的飘链或白板总数矛盾")
        if not isinstance(self.baotou, bool):
            raise ValueError("baotou 必须是 bool")


@dataclass(frozen=True)
class ValueRoute:
    """一次未来摸牌直接胡的路线；有效牌数是未见张数，不是成胡概率。"""

    conditional_settlement: Settlement  # 上述条件满足时的四家净变分，座位顺序 0—3
    shanten: int  # 首版只提供直接成胡见证，固定为 0
    useful_tiles: Tuple[UsefulTileFact, ...]  # 互斥的下一摸牌，同一后续弃牌内不能重复计数
    followup_discard: Optional[str]  # 吃碰后先弃的牌；不能把不同弃牌路线相加
    conditions: ValueConditions
    support: str = "conditional_witness"  # 已校验条件见证；不包含未来生存概率

    def __post_init__(self) -> None:
        if type(self.shanten) is not int or self.shanten != 0:
            raise ValueError("首版 ValueRoute 仅支持 shanten=0")
        if self.support != "conditional_witness":
            raise ValueError("首版 ValueRoute 仅支持条件见证")
        if not isinstance(self.useful_tiles, tuple) or not self.useful_tiles:
            raise ValueError("ValueRoute 必须携带非空有效牌 tuple")
        if len({tile.code for tile in self.useful_tiles}) != len(self.useful_tiles):
            raise ValueError("同一路线不能重复有效牌")
        if self.followup_discard is not None and self.followup_discard not in CANONICAL_TILE_CODES:
            raise ValueError("followup_discard 必须是规范牌值或空")
        if self.conditional_settlement.fan <= 0:
            raise ValueError("成胡路线必须有正番结算")


@dataclass(frozen=True)
class CandidateValueFacts:
    """候选的可选分值事实，随原观察、规则版本和动作键一起序列化。

    coverage 只描述首版一次摸牌范围。COMPLETE 加空 routes 表示此范围
    没有合法胡牌见证，不能解释为后续整单局不可能胡。
    """

    immediate_settlement: Optional[Settlement] = None  # 仅当前合法 Hu；未知不可填零
    routes: Tuple[ValueRoute, ...] = ()
    coverage: ValueCoverage = ValueCoverage.UNAVAILABLE
    issues: Tuple[RuleIssue, ...] = ()  # 缺证据、工作量截断或计算失败的稳定分类

    def __post_init__(self) -> None:
        if not isinstance(self.routes, tuple) or not isinstance(self.issues, tuple):
            raise ValueError("routes 和 issues 必须是 tuple")
        if self.coverage is not ValueCoverage.COMPLETE and not self.issues:
            raise ValueError("非完整分值分析必须说明原因")
