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


class RouteStatus(str, Enum):
    """路线证据状态；与进展五态 ProgressKind 不混（v4 §5.1）。

    回答"该路线当前有什么证据"，不回答"动作使它变好还是变坏"；
    `UNANALYZED` 不等于关闭，也不等于零机会。
    """

    WITNESSED = "witnessed"          # 已有条件见证（如 ValueRoute 一次摸牌成胡见证）
    OPEN_UNCERTAIN = "open_uncertain"  # 合法可达但兑现未知；不得因未枚举写成零机会
    CLOSED_PROVEN = "closed_proven"    # 已证关闭（如七对路线存在副露）
    UNANALYZED = "unanalyzed"          # 未分析；不等于关闭或零机会


class FamilyId(str, Enum):
    """规则价值来源的四个专长家族（v4 §7.3 场景矩阵；进展载荷按声明序排列）。"""

    BRANCH = "branch"        # 普通型/七对分支
    CHAIN = "chain"          # 动作链（连续飘/杠）
    FOUR_WHITE = "four_white"  # 四白等值
    BAOTOU = "baotou"        # 爆头


class ProgressKind(str, Enum):
    """动作相对变化（前后对比）；缺证据/未分析时用 UNKNOWN，不得用数值冒充。"""

    ADVANCE = "advance"
    SAME = "same"
    RETREAT = "retreat"
    CLOSE = "close"
    UNKNOWN = "unknown"      # 缺证据/未分析时用，不得用数值冒充


@dataclass(frozen=True)
class FollowupBranchFacts:
    """吃/碰候选动作后一种合法弃牌分支的机械事实。

    v4 §3.1/§4.2：新入口保留吃碰后全部已分析合法弃牌分支，不只读已选
    最佳分支；吃碰后不同弃牌不得预合并成一个牌效最佳分支。计数未知时
    `useful_tiles` 为空且 `support_remaining=None`（all-or-nothing 口径），
    不得写 0 冒充已知空缺。
    """

    followup_key: str            # 分支键："<action_key>#<followup_discard>"，稳定排序用
    followup_discard: str        # 该分支先弃的牌（规范牌值）
    combined_shanten: Optional[int]      # 该分支等待态已知分牌型向听的最小值；两分牌型都未知为 None
    standard_shanten_after: Optional[int]   # 同一等待手牌普通型向听；未分析 None
    seven_pairs_shanten_after: Optional[int] # 七对向听；有副露或未分析 None
    useful_tiles: Tuple[UsefulTileFact, ...] = ()  # 该分支等待态的一步推进有效牌
    support_remaining: Optional[int] = None  # 一步推进有效牌的未见枚数总和（牌码去重后求和）；计数未知 None，不得写 0 冒充

    def __post_init__(self) -> None:
        if self.followup_discard not in CANONICAL_TILE_CODES:
            raise ValueError("FollowupBranchFacts.followup_discard 必须是规范牌值")
        if (
            not isinstance(self.followup_key, str)
            or not self.followup_key.endswith("#" + self.followup_discard)
        ):
            raise ValueError(
                "FollowupBranchFacts.followup_key 必须形如 <action_key>#<followup_discard>"
            )
        for name in ("combined_shanten", "standard_shanten_after", "seven_pairs_shanten_after"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < -1):
                raise ValueError("FollowupBranchFacts." + name + " 必须是至少 -1 的整数或空")
        if not isinstance(self.useful_tiles, tuple) or any(
            not isinstance(tile, UsefulTileFact) for tile in self.useful_tiles
        ):
            raise ValueError("FollowupBranchFacts.useful_tiles 必须是 UsefulTileFact 元组")
        if self.support_remaining is not None and (
            type(self.support_remaining) is not int or self.support_remaining < 0
        ):
            raise ValueError("FollowupBranchFacts.support_remaining 必须是非负整数或空")


@dataclass(frozen=True)
class FamilyProgress:
    """一个候选动作对一个规则家族的相对进展与证据状态（v4 §7.3 谓词输入）。"""

    family: FamilyId
    progress: ProgressKind       # 动作相对变化（前后对比）
    route_status: RouteStatus    # 证据状态
    basis: str                   # 确定性依据一句话（引用规则数学/观察事实；不得调用任何策略）

    def __post_init__(self) -> None:
        if not isinstance(self.family, FamilyId):
            raise ValueError("FamilyProgress.family 必须是 FamilyId")
        if not isinstance(self.progress, ProgressKind):
            raise ValueError("FamilyProgress.progress 必须是 ProgressKind")
        if not isinstance(self.route_status, RouteStatus):
            raise ValueError("FamilyProgress.route_status 必须是 RouteStatus")
        if not isinstance(self.basis, str) or not self.basis:
            raise ValueError("FamilyProgress.basis 必须是非空字符串")


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
    standard_shanten_after: Optional[int] = None  # 同一动作后等待手牌的普通型向听；未分析为空
    seven_pairs_shanten_after: Optional[int] = None  # 同一等待手牌的七对向听；有副露或未分析为空
    standard_useful_tiles: Optional[Tuple[UsefulTileFact, ...]] = None  # 普通型推进牌及可见未见张数；未分析或计数未知为空
    seven_pairs_useful_tiles: Optional[Tuple[UsefulTileFact, ...]] = None  # 七对推进牌；未分析、不适用或计数未知为空；() 表示已知空集合
    pattern_progress_note: Optional[str] = None  # 新增分牌型计数的局部缺证据原因，不降低原综合事实完整性
    # B3 编解码升级后载荷参与相等性（audit_codec 已携带两键，往返保持相等）；
    # compare=False 临时兼容随编解码升级移除，旧消费者按"开关 value 分析产生
    # 不同载荷即不同事实"的新契约比较。
    followup_branches: Optional[Tuple[FollowupBranchFacts, ...]] = None  # 吃/碰候选：全部已分析合法弃牌分支，按 followup_discard 规范牌序；None=未分析或不适用；旧 best_followup_discard 保留原语义（=其中牌效最佳分支的弃牌）
    family_progress: Tuple[FamilyProgress, ...] = ()  # 空元组=未分析，不冒充无进展；按 FamilyId 声明序

    def __post_init__(self) -> None:
        for name in ("standard_useful_tiles", "seven_pairs_useful_tiles"):
            value = getattr(self, name)
            if value is not None:
                if self.fact_kind is not CandidateFactKind.HAND_PROGRESS:
                    raise ValueError("分牌型有效牌只属于 HAND_PROGRESS 等待事实")
                if not isinstance(value, tuple) or any(not isinstance(t, UsefulTileFact) for t in value):
                    raise ValueError("CandidateFacts." + name + " 必须是 UsefulTileFact 元组或空")
        if self.pattern_progress_note is not None and not isinstance(self.pattern_progress_note, str):
            raise ValueError("CandidateFacts.pattern_progress_note 必须是字符串或空")
        for name in ("standard_shanten_after", "seven_pairs_shanten_after"):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < -1):
                raise ValueError("CandidateFacts." + name + " 必须是至少 -1 的整数或空")
            if value is not None and self.fact_kind is not CandidateFactKind.HAND_PROGRESS:
                raise ValueError("分牌型向听只属于 HAND_PROGRESS 等待事实")
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
        if self.followup_branches is not None:
            # 适用口径与 best_followup_discard 一致：只有吃/碰类 HAND_PROGRESS
            # 候选携带（由生产端保证动作类别；此处校验事实形状一致性）。
            if self.fact_kind is not CandidateFactKind.HAND_PROGRESS:
                raise ValueError("followup_branches 只属于 HAND_PROGRESS 吃/碰候选")
            if not isinstance(self.followup_branches, tuple) or any(
                not isinstance(branch, FollowupBranchFacts)
                for branch in self.followup_branches
            ):
                raise ValueError("CandidateFacts.followup_branches 必须是 FollowupBranchFacts 元组")
            if self.best_followup_discard is None:
                raise ValueError(
                    "followup_branches 需要 best_followup_discard（吃/碰适用口径）"
                )
            branch_discards = tuple(
                branch.followup_discard for branch in self.followup_branches
            )
            if len(set(branch_discards)) != len(branch_discards):
                raise ValueError("followup_branches.followup_discard 不得重复")
            if self.best_followup_discard not in branch_discards:
                raise ValueError("best_followup_discard 必须属于 followup_branches")
        if not isinstance(self.family_progress, tuple) or any(
            not isinstance(entry, FamilyProgress) for entry in self.family_progress
        ):
            raise ValueError("CandidateFacts.family_progress 必须是 FamilyProgress 元组")
        if len({entry.family for entry in self.family_progress}) != len(self.family_progress):
            raise ValueError("family_progress.family 不得重复")


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
