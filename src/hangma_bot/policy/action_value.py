"""action_value_v1 独立策略评分接缝：ScoringView/ScoreBatch 类型与固定骨架。

权威材料：review/llm-guided-heuristic-route-2026-09-15/contracts/action-value-v1.json
（机器合同）与同目录 SEARCH-SPACE-REDESIGN-2026-09-16.md §4.1/§5。本模块只定义
类型、完整性验证与 RankedCandidate 适配；受限执行在 action_value_executor.py，
种子在 action_value_seeds.py。骨架不拼任何 weighted_heuristic_v2 分数。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from hangma_bot.hangma.interface import Settlement
from hangma_bot.kernel.actions import Action, action_key as kernel_action_key
from hangma_bot.kernel.observation import PlayerObservation

from .interface import RankedCandidate, ScorePart

if False:  # pragma: no cover - 仅为类型检查保留；载荷运行期按 B1 实类型透传
    from hangma_bot.hangma.interface import FollowupBranchFacts, ValueRoute  # noqa: F401

# —— 合同常量（scoring_view.schema_version / route_states / progress_states）——

#: 结构版本。/1 = 阶段账未进入候选视图的冻结版；/2 = 新增 competition_bases
#: 口径（stage_scores 座位序账 / table_scores 本桌进行中 / freshness_masks 闭集），
#: R7 P11 投影 + P11b 升位；/3 = R8 E3（M1）：新增第三概念 current_stage_scores
#: （已完成账 + 当前桌账 = 当前阶段合计，逐座位相加）与合同 residual_gaps
#: （剩余赛程未投影的显式登记）；/4 = R18：新增规则同源动作后爆头事实。
#: 结构面变化必须先登记再升版本（守卫见
#: tests/unit/policy/test_action_value_policy.py::TestScoringViewVersionGuard）。
SCORING_VIEW_SCHEMA_VERSION = "sitin-scoring-view/4"
CANDIDATE_KIND = "action_value_v1"

ROUTE_STATES: Tuple[str, ...] = (
    "WITNESSED",
    "OPEN_UNCERTAIN",
    "CLOSED_PROVEN",
    "UNANALYZED",
)
PROGRESS_STATES: Tuple[str, ...] = ("ADVANCE", "SAME", "RETREAT", "CLOSE", "UNKNOWN")

STATUS_SCORED = "SCORED"
STATUS_ABSTAIN = "ABSTAIN"
STATUS_VALUES: Tuple[str, ...] = (STATUS_SCORED, STATUS_ABSTAIN)

# trace 序列化字节上限（合同 limits.candidate.max_trace_bytes；执行器再导出对账）。
MAX_TRACE_BYTES = 32768

# R2/S5：RankedCandidate.score_trace 的线格式版本（完整有界结构化解释；
# 变更解释结构时递增，审计旧记录缺键还原 None）。
SCORE_TRACE_SCHEMA_VERSION = "sitin-action-score-trace/1"

# trace 允许的最大嵌套深度（dict 嵌套层数 ≤3）。
MAX_TRACE_DEPTH = 3

# 单个 trace 字符串值的长度上限，防止靠超长字符串在深度限制内撑爆体积。
MAX_TRACE_STRING_CHARS = 4096


@dataclass(frozen=True)
class ReferenceFeature:
    """有版本的参考代理值；与规则事实分开存储，候选可不用。

    信息权限：只承载 policy 侧代理，不含规则确定事实；无校准证据时不得
    标注为真实概率或严格下界（docstring 与 unit 字段共同表达假设）。
    """

    name: str  # 代理名，稳定标识
    value: float  # 代理值；单位见 unit，可空条件：missing_reason 为空时才有信息量
    version: str  # 代理语义版本
    unit: str  # 单位说明（如“近似每百局次数”）；不是积分
    missing_reason: Optional[str] = None  # 缺失原因；非空时 value 仅是无信息占位 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("ReferenceFeature.name 必须是非空字符串")
        if not isinstance(self.version, str) or not self.version:
            raise ValueError("ReferenceFeature.version 必须是非空字符串")
        if not isinstance(self.unit, str) or not self.unit:
            raise ValueError("ReferenceFeature.unit 必须是非空字符串")
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
            raise ValueError("ReferenceFeature.value 必须是数值，不允许布尔冒充")
        if not float(self.value) == float(self.value) or float(self.value) in (
            float("inf"),
            float("-inf"),
        ):
            raise ValueError("ReferenceFeature.value 必须是有限数")
        if self.missing_reason is not None and (
            not isinstance(self.missing_reason, str) or not self.missing_reason
        ):
            raise ValueError("ReferenceFeature.missing_reason 必须是非空字符串或空")


@dataclass(frozen=True)
class AnalysisProfileView:
    """规则分析语义版本与固定工作量上限快照。

    信息权限：只是上限与版本的不可变快照；不含计时器、可变缓存句柄或
    预算剩余量（候选不得据此做时间投机）。
    """

    semantics_version: str  # 分析语义版本；变更即候选身份变化
    max_expansions: int  # 整次请求规则分析扩展节点上限（ValueAnalysisLimits 同源）
    max_routes_per_candidate: int  # 每动作条件路线分组上限
    truncation_note: str  # 截断范围说明；PARTIAL 时描述未覆盖的路线范围
    ruleset_version: str = ""  # 规则语义版本；未提供时为空字符串

    def __post_init__(self) -> None:
        if not isinstance(self.semantics_version, str) or not self.semantics_version:
            raise ValueError("AnalysisProfileView.semantics_version 必须是非空字符串")
        for name in ("max_expansions", "max_routes_per_candidate"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError("AnalysisProfileView.{0} 必须是正整数".format(name))
        if not isinstance(self.truncation_note, str):
            raise ValueError("AnalysisProfileView.truncation_note 必须是字符串")
        if not isinstance(self.ruleset_version, str):
            raise ValueError("AnalysisProfileView.ruleset_version 必须是字符串")


@dataclass(frozen=True)
class CompetitionView:
    """可见赛事上下文与可用/陈旧掩码；积分基准按本阶段/本桌分别命名。

    信息权限：全部字段可空——无权获知或陈旧时为 None；不投影其他进行中
    桌赛的未来结果。座位向量固定按座位 0—3。
    """

    stage_scores: Optional[Tuple[int, int, int, int]] = None  # 已完成账；陈旧/无权为空
    table_scores: Optional[Tuple[int, int, int, int]] = None  # 当前桌账；陈旧/无权为空
    freshness_masks: Optional[Tuple[str, ...]] = None  # 各基准的可用/陈旧说明；未提供为空
    # 当前阶段合计（已完成账 + 当前桌账，逐座位）；stage_scores 为空时它也为空。
    # 位置序固定 [stage_scores, table_scores]，本字段的可用性与 stage_scores 同掩码。
    current_stage_scores: Optional[Tuple[int, int, int, int]] = None

    def __post_init__(self) -> None:
        for name in ("stage_scores", "table_scores", "current_stage_scores"):
            value = getattr(self, name)
            if value is None:
                continue
            if len(value) != 4 or any(
                isinstance(item, bool) or not isinstance(item, int) for item in value
            ):
                raise ValueError(
                    "CompetitionView.{0} 必须是按座位 0—3 的整数四元组或空".format(name)
                )
        # 三概念的机器不变量：只要同时给出两账与合计，合计必须等于逐座位之和
        # （把本桌账算两次、或换一个基准合成，都在构造期失败而不是被候选照抄）。
        if (
            self.stage_scores is not None
            and self.table_scores is not None
            and self.current_stage_scores is not None
        ):
            expected = tuple(
                int(completed) + int(live)
                for completed, live in zip(self.stage_scores, self.table_scores)
            )
            if tuple(self.current_stage_scores) != expected:
                raise ValueError(
                    "CompetitionView.current_stage_scores 必须等于 stage_scores + "
                    "table_scores（逐座位；重复累计本桌账或换基准都非法）：期望 {0}，"
                    "得到 {1}".format(expected, tuple(self.current_stage_scores))
                )
        if self.freshness_masks is not None:
            if any(
                not isinstance(item, str) or not item for item in self.freshness_masks
            ):
                raise ValueError("CompetitionView.freshness_masks 元素必须是非空字符串")


@dataclass(frozen=True)
class ActionView:
    """不可变动作表条目：一个合法动作在同一窗口内的只读事实。

    信息权限：动作集合只来自 RuleAnalysis，本视图不重新判定合法性；
    followup_branches 透传 B1 的分支事实对象，本包不校验其内部结构。
    """

    action_key: str  # 稳定动作键（kernel.actions.action_key 同源）
    action: Action  # 规则动作值对象；仅供 B3 适配 RankedCandidate，不进入受限映射
    action_type: str  # 规则动作类型：discard/chi/peng/gang/hu/pass
    is_legal: bool  # 合法身份，来自 RuleAnalysis；仅作事实透传
    followup_branches: Optional[Tuple[Any, ...]] = None  # B1 FollowupBranchFacts 元组；None=未分析/不适用（B3 起透传 None，不与已知空集合混淆）
    immediate_settlement: Optional[Settlement] = None  # 立即结算；非立即结算动作为空
    family_progress: str = "UNKNOWN"  # 本动作相对进展（全家族显著性摘要），取值见 PROGRESS_STATES
    routes: Tuple[Any, ...] = ()  # B1 ValueRoute 条件见证摘要（B3 投影）；空=无路线分析
    # —— R2/S2：显式动作牌效事实（普通弃牌/过牌等的 CandidateFacts 直投影；
    # 不重新实现规则数学，缺省 None/() 表示未生产或未分析，不冒充零）——
    fact_kind: Optional[str] = None  # hand_progress/win/not_applicable/analysis_failed；None=未生产 facts
    shanten_after: Optional[int] = None  # 动作后综合向听；WIN 为 -1；未分析 None
    useful_tiles: Tuple[Any, ...] = ()  # 动作后等待态一步推进有效牌（UsefulTileFact 透传）
    replacement_draw_unknown: Optional[bool] = None  # 杠上补牌未知标记（杠候选）；None=未携带
    best_followup_discard: Optional[str] = None  # 吃/碰后的最佳后续弃牌（旧语义保留）
    standard_shanten_after: Optional[int] = None  # 普通型向听；未分析 None
    seven_pairs_shanten_after: Optional[int] = None  # 七对向听；未分析 None
    standard_useful_tiles: Optional[Tuple[Any, ...]] = None  # 普通型推进牌；None=未分析，() =已知空
    seven_pairs_useful_tiles: Optional[Tuple[Any, ...]] = None  # 七对推进牌；None=未分析，() =已知空
    pattern_progress_note: Optional[str] = None  # 分牌型计数的局部缺证据原因
    family_progress_entries: Tuple[Any, ...] = ()  # 完整 FamilyProgress 明细（R2/S5 前折叠为单串，现两口径并存）
    value_coverage: Optional[str] = None  # value_facts.coverage：complete/partial/unavailable；None=未跑分值分析
    value_issues: Tuple[Any, ...] = ()  # value_facts.issues（缺证据/截断/失败原因）
    baotou_after: Optional[bool] = None  # hangma 生产的动作后爆头状态；None=终局/未知/未分析

    def __post_init__(self) -> None:
        if not isinstance(self.action_key, str) or not self.action_key:
            raise ValueError("ActionView.action_key 必须是非空字符串")
        if self.action_type not in ("discard", "chi", "peng", "gang", "hu", "pass"):
            raise ValueError("ActionView.action_type 必须是已知规则动作类型")
        if not isinstance(self.is_legal, bool):
            raise ValueError("ActionView.is_legal 必须是布尔值")
        if self.family_progress not in PROGRESS_STATES:
            raise ValueError(
                "ActionView.family_progress 必须是 {0} 之一".format(PROGRESS_STATES)
            )
        if self.followup_branches is not None and not isinstance(
            self.followup_branches, tuple
        ):
            raise ValueError("ActionView.followup_branches 必须是 tuple 或 None")
        if not isinstance(self.routes, tuple):
            raise ValueError("ActionView.routes 必须是 tuple")
        for name in ("useful_tiles", "family_progress_entries", "value_issues"):
            if not isinstance(getattr(self, name), tuple):
                raise ValueError("ActionView.{0} 必须是 tuple".format(name))
        for name in (
            "standard_useful_tiles", "seven_pairs_useful_tiles",
        ):
            value = getattr(self, name)
            if value is not None and not isinstance(value, tuple):
                raise ValueError("ActionView.{0} 必须是 tuple 或 None".format(name))
        if self.baotou_after is not None and not isinstance(self.baotou_after, bool):
            raise ValueError("ActionView.baotou_after 必须是 bool 或 None")
        for name in (
            "shanten_after", "standard_shanten_after", "seven_pairs_shanten_after",
        ):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < -1):
                raise ValueError("ActionView.{0} 必须是至少 -1 的整数或 None".format(name))
        if self.fact_kind is not None and self.fact_kind not in (
            "hand_progress", "win", "not_applicable", "analysis_failed",
        ):
            raise ValueError("ActionView.fact_kind 必须是已知候选事实类别或 None")
        if self.replacement_draw_unknown is not None and not isinstance(
            self.replacement_draw_unknown, bool
        ):
            raise ValueError("ActionView.replacement_draw_unknown 必须是布尔或 None")
        if self.value_coverage is not None and self.value_coverage not in (
            "complete", "partial", "unavailable",
        ):
            raise ValueError("ActionView.value_coverage 必须是 complete/partial/unavailable 或 None")
        derived = kernel_action_key(self.action)
        if derived != self.action_key:
            raise ValueError(
                "ActionView.action_key 与动作值对象不一致：{0} != {1}".format(
                    self.action_key, derived
                )
            )


def _guard_trace_serialized_size(value: Any, where: str) -> int:
    """序列化前的**有界**体积预判：返回字节下界；超过 MAX_TRACE_BYTES 即拒绝。

    R9/S1b：候选返回值（trace）此前在「递归校验 → json.dumps → 比上限」之后
    才被拒绝，两步都在候选计费之外：24 operations 的候选可让整批序列化
    201 MB / 峰值 406 MB。本函数在**进入递归校验与序列化之前**用显式栈做
    有界预判：

    - 字符串按字符数、数值/None/bool 按 1 字节、容器按 1 字节括号计入下界；
    - 共享引用按**出现次数**展开（json.dumps 与递归校验都按次展开，不去重）；
    - 访问节点数超过 MAX_TRACE_BYTES 即拒绝：任何节点在 JSON 里至少占 1 字节，
      因此节点数超过上限的 trace 必然超过字节上限（下界足以判定）；
    - 无递归、无记忆化，工作与内存都以 MAX_TRACE_BYTES 为界（实测 ≤ 数毫秒）。

    保留下游原有的精确检查（序列化后逐字节比较）作为最终口径——本函数只
    提前拒绝「无论如何都会超限」的输入，不放过任何原本会被拒绝的形状。
    """
    limit = MAX_TRACE_BYTES
    total = 0
    nodes = 0
    stack: List[Any] = [value]
    while stack:
        node = stack.pop()
        nodes += 1
        if nodes > limit:
            raise ValueError(
                "{0} 展开节点超过 {1} 上限：拒绝序列化前的大体积 trace".format(
                    where, limit
                )
            )
        if isinstance(node, str):
            total += len(node)
        elif node is None or isinstance(node, (bool, int, float)):
            total += 1
        elif isinstance(node, (list, tuple)):
            total += 1
            stack.extend(node)
        elif isinstance(node, dict):
            total += 1
            for key, item in node.items():
                stack.append(key)
                stack.append(item)
        else:
            # 其余类型由 _validate_trace_value 报错；这里只按最小字节计入下界。
            total += 1
        if total > limit:
            raise ValueError(
                "{0} 序列化规模超过 {1} 字节上限（序列化前预判拒绝）".format(
                    where, limit
                )
            )
    return total


def _validate_trace_value(value: Any, remaining_depth: int, where: str) -> None:
    """校验 trace 标量/容器：深度 ≤3、只含原始类型、字符串有界。"""
    if value is None or isinstance(value, bool) or isinstance(value, int):
        if isinstance(value, int) and abs(value) > 2**63 - 1:
            raise ValueError("{0} 含超过 63 位界限的整数".format(where))
        return
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("{0} 含非有限浮点".format(where))
        return
    if isinstance(value, str):
        if len(value) > MAX_TRACE_STRING_CHARS:
            raise ValueError("{0} 含超过 {1} 字符的字符串".format(where, MAX_TRACE_STRING_CHARS))
        return
    if isinstance(value, (list, tuple)):
        if remaining_depth <= 0:
            raise ValueError("{0} 嵌套深度超过 {1}".format(where, MAX_TRACE_DEPTH))
        for item in value:
            _validate_trace_value(item, remaining_depth - 1, where)
        return
    if isinstance(value, dict):
        if remaining_depth <= 0:
            raise ValueError("{0} 嵌套深度超过 {1}".format(where, MAX_TRACE_DEPTH))
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("{0} 的字典键必须是字符串".format(where))
            _validate_trace_value(item, remaining_depth - 1, where)
        return
    raise ValueError(
        "{0} 含不允许的 trace 类型 {1}".format(where, type(value).__name__)
    )


@dataclass(frozen=True)
class ActionScore:
    """单个动作的评分点与有界结构化解释。

    score 是有限浮点评分点，越大越优先；不跨候选比较绝对量级，也不当
    实际积分。trace 是有界结构化解释（深度 ≤3，整批序列化 ≤32KiB），
    非线性机制明细放 trace，不拆成虚假可加贡献。
    """

    action_key: str  # 动作键，必须属于输入动作表
    score: float  # 有限浮点；布尔冒充数在构造期拒绝
    trace: Dict[str, Any]  # 结构化解释：分支选择、所用事实键、分项与组合方式

    def __post_init__(self) -> None:
        if not isinstance(self.action_key, str) or not self.action_key:
            raise ValueError("ActionScore.action_key 必须是非空字符串")
        if isinstance(self.score, bool) or not isinstance(self.score, (int, float)):
            raise ValueError(
                "ActionScore.score 必须是数值，得到 {0!r}（布尔冒充数整批失败）".format(
                    self.score
                )
            )
        score = float(self.score)
        if score != score or score in (float("inf"), float("-inf")):
            raise ValueError("ActionScore.score 必须是有限数")
        object.__setattr__(self, "score", score)
        if not isinstance(self.trace, dict):
            raise ValueError("ActionScore.trace 必须是 dict")
        # R9/S1b：先做有界体积预判，再进入递归校验（单条 trace 超过整批上限
        # 即必然超限，故用同一上限即可判定，且不会放过原本合法的 trace）。
        _guard_trace_serialized_size(self.trace, "ActionScore.trace")
        _validate_trace_value(self.trace, MAX_TRACE_DEPTH, "ActionScore.trace")
        object.__setattr__(self, "trace", dict(self.trace))


def _serialized_trace_bytes(entries: Tuple[ActionScore, ...]) -> int:
    """把整批 trace 序列化成 UTF-8 文本并返回字节数；超限即整批失败。"""
    payload = [
        {"action_key": entry.action_key, "score": entry.score, "trace": entry.trace}
        for entry in entries
    ]
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return len(text.encode("utf-8"))


@dataclass(frozen=True)
class ScoreBatch:
    """一个动作窗口的完整评分结果；不能部分成功后用 0 补齐。

    status 只取 SCORED/ABSTAIN：SCORED 时 entries 对输入动作恰好各一项；
    ABSTAIN 时 entries 为空且必须给出 reason。任何构造期校验失败都以
    ValueError 使整批失效，由调用方降级到已备紧急计划。
    """

    status: str  # SCORED 或 ABSTAIN
    entries: Tuple[ActionScore, ...] = ()  # SCORED 时恰好每输入动作一项
    reason: Optional[str] = None  # ABSTAIN/降级原因；SCORED 时可为空

    def __post_init__(self) -> None:
        if self.status not in STATUS_VALUES:
            raise ValueError(
                "ScoreBatch.status 必须是 {0} 之一，得到 {1!r}".format(STATUS_VALUES, self.status)
            )
        if not isinstance(self.entries, tuple):
            raise ValueError("ScoreBatch.entries 必须是 tuple")
        for entry in self.entries:
            if not isinstance(entry, ActionScore):
                raise ValueError("ScoreBatch.entries 元素必须是 ActionScore")
        if self.reason is not None and (not isinstance(self.reason, str) or not self.reason):
            raise ValueError("ScoreBatch.reason 必须是非空字符串或空")
        if self.status == STATUS_ABSTAIN:
            if self.entries:
                raise ValueError("ABSTAIN 批不得携带评分条目")
            if self.reason is None:
                raise ValueError("ABSTAIN 批必须给出原因，不得用特殊数值表示未知")
            return
        if not self.entries:
            raise ValueError("SCORED 批必须至少包含一个评分条目")
        keys = [entry.action_key for entry in self.entries]
        if len(set(keys)) != len(keys):
            raise ValueError("SCORED 批存在重复动作键，整批失效")
        # R9/S1b：整批序列化前的有界预判（共享 trace 按出现次数展开），
        # 避免先把超限 trace 序列化成几十/上百 MB 再比上限。
        _guard_trace_serialized_size(
            [
                {"action_key": entry.action_key, "score": entry.score,
                 "trace": entry.trace}
                for entry in self.entries
            ],
            "ScoreBatch.trace",
        )
        trace_bytes = _serialized_trace_bytes(self.entries)
        if trace_bytes > MAX_TRACE_BYTES:
            raise ValueError(
                "整批 trace 序列化 {0} 字节，超过 {1} 字节上限".format(
                    trace_bytes, MAX_TRACE_BYTES
                )
            )


def _settlement_mapping(settlement: Settlement, seat: int) -> Dict[str, Any]:
    """把 Settlement 转成受限候选可见的原始值映射；座位 0—3 语义不变。"""
    delta = tuple(settlement.score_delta)
    return {
        "fan": settlement.fan,
        "score_delta": delta,
        "self_delta": delta[seat] if seat < len(delta) else None,
        "details": tuple(settlement.details),
    }


def _plain_value(value: Any, depth: int = 0) -> Any:
    """把分支事实中的值对象降为原始值；未知对象跳过而不是猜结构。"""
    if value is None or isinstance(value, (bool, int, float, str)):
        if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
            return 0.0
        return value
    if isinstance(value, tuple) or isinstance(value, list):
        if depth >= 2:
            return tuple()
        return tuple(_plain_value(item, depth + 1) for item in value)
    if isinstance(value, Settlement):
        return _settlement_mapping(value, 0)
    tiles = getattr(value, "code", None)
    if isinstance(tiles, str):
        return tiles
    if hasattr(value, "value") and isinstance(value.value, (bool, int, float, str)):
        return value.value
    return None


# 分支事实的别名键：B1 定稿前以宽容映射支持多种命名，键集合稳定。
_BRANCH_KEY_ALIASES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("followup_key", ("followup_key", "discard_key", "branch_key")),
    ("combined_shanten", ("combined_shanten", "shanten", "shanten_after")),
    ("support_remaining", ("support_remaining", "useful_remaining", "support")),
    ("progress", ("progress", "family_progress", "pattern_progress")),
    ("route_state", ("route_state", "route_status", "evidence_state")),
    ("fan", ("fan", "settlement_fan", "route_fan")),
    ("draw_kind", ("draw_kind",)),
    ("hand_codes", ("hand_codes", "visible_hand")),
)


def _branch_mapping(branch: Any) -> Any:
    """把 B1 分支事实（或测试用 dict）透传为受限候选可读映射。

    B1 的 FollowupBranchFacts 尚未合入 hangma.interface：对象分支按别名键
    提取公共字段，其余原始字段原样透传；dict 分支浅拷贝直接使用。本函数
    不校验分支内部语义（合法性由规则侧负责）。
    """
    if isinstance(branch, dict):
        return dict(branch)
    mapping: Dict[str, Any] = {}
    for canonical, aliases in _BRANCH_KEY_ALIASES:
        for alias in aliases:
            if alias in mapping:
                continue
            value = getattr(branch, alias, None)
            if value is not None:
                mapping[canonical] = _plain_value(value)
                break
    namespace = getattr(branch, "__dict__", None)
    if namespace:
        for name, value in namespace.items():
            if name.startswith("_") or name in mapping:
                continue
            plain = _plain_value(value)
            if plain is not None:
                mapping.setdefault(name, plain)
    return mapping


def _route_mapping(route: Any, seat: int) -> Dict[str, Any]:
    """把 B1 ValueRoute 条件见证投影为受限候选可读的原始值映射。

    只透传路线已证事实（条件结算、有效牌未见枚数、条件结构），不补未来
    摸牌值；候选不得把 useful_tiles 的未见枚数当概率（合同 §4.2 路线行）。
    测试用 dict 路线浅拷贝直通（与 _branch_mapping 同口径）。
    """
    if isinstance(route, dict):
        return dict(route)
    settlement = getattr(route, "conditional_settlement", None)
    conditions = getattr(route, "conditions", None)
    useful = getattr(route, "useful_tiles", None) or ()
    return {
        "followup_discard": getattr(route, "followup_discard", None),
        "shanten": getattr(route, "shanten", None),
        "useful_tiles": tuple(
            {"code": tile.code, "remaining_estimate": tile.remaining_estimate}
            for tile in useful
        ),
        "conditional_settlement": (
            None if settlement is None else _settlement_mapping(settlement, seat)
        ),
        "conditions": {
            "draw_kind": getattr(conditions, "draw_kind", None),
            "pre_draw_hand": tuple(getattr(conditions, "pre_draw_hand", None) or ()),
            "meld_count": getattr(conditions, "meld_count", None),
            "chain_count": getattr(conditions, "chain_count", None),
            "chain_piao": getattr(conditions, "chain_piao", None),
            "baotou": getattr(conditions, "baotou", None),
        },
        "support": getattr(route, "support", None),
    }


def _useful_tiles_mapping(tiles: Any) -> Any:
    """UsefulTileFact 元组的原始值投影；None 保持 None（未分析口径）。"""
    if tiles is None:
        return None
    return tuple(
        {"code": tile.code, "remaining_estimate": tile.remaining_estimate}
        for tile in tiles
    )


def _family_entries_mapping(entries: Any) -> Tuple[Dict[str, Any], ...]:
    """FamilyProgress 明细的原始值投影（family/progress/route_status 用 .value 字符串）。"""
    result = []
    for entry in entries:
        family = getattr(entry, "family", None)
        progress = getattr(entry, "progress", None)
        status = getattr(entry, "route_status", None)
        result.append({
            "family": getattr(family, "value", family),
            "progress": getattr(progress, "value", progress),
            "route_status": getattr(status, "value", status),
            "basis": getattr(entry, "basis", None),
        })
    return tuple(result)


def _rule_issues_mapping(issues: Any) -> Tuple[Dict[str, Any], ...]:
    """RuleIssue（缺证据/截断/失败原因）的原始值投影。"""
    return tuple(
        {"area": getattr(issue, "area", None), "reason": getattr(issue, "reason", None)}
        for issue in issues
    )


def _action_mapping(view: ActionView, seat: int) -> Dict[str, Any]:
    """单个动作的受限映射：只含原始值，不携带 Action 值对象。"""
    settlement = None
    if view.immediate_settlement is not None:
        settlement = _settlement_mapping(view.immediate_settlement, seat)
    return {
        "action_key": view.action_key,
        "action_type": view.action_type,
        "is_legal": view.is_legal,
        "family_progress": view.family_progress,
        "immediate_settlement": settlement,
        # None 透传：候选按"未分析"显式处理，不与已知空分支集合混淆。
        "followup_branches": (
            None
            if view.followup_branches is None
            else tuple(_branch_mapping(b) for b in view.followup_branches)
        ),
        "routes": tuple(_route_mapping(r, seat) for r in view.routes),
        # —— R2/S2：显式动作牌效事实直投影（普通弃牌/过牌不再只剩分支口径）——
        "fact_kind": view.fact_kind,
        "shanten_after": view.shanten_after,
        "useful_tiles": _useful_tiles_mapping(view.useful_tiles),
        "replacement_draw_unknown": view.replacement_draw_unknown,
        "best_followup_discard": view.best_followup_discard,
        "standard_shanten_after": view.standard_shanten_after,
        "seven_pairs_shanten_after": view.seven_pairs_shanten_after,
        "standard_useful_tiles": _useful_tiles_mapping(view.standard_useful_tiles),
        "seven_pairs_useful_tiles": _useful_tiles_mapping(view.seven_pairs_useful_tiles),
        "pattern_progress_note": view.pattern_progress_note,
        "family_progress_entries": _family_entries_mapping(
            view.family_progress_entries
        ),
        "value_coverage": view.value_coverage,
        "value_issues": _rule_issues_mapping(view.value_issues),
        "baotou_after": view.baotou_after,
    }


def _observation_mapping(observation: PlayerObservation) -> Dict[str, Any]:
    """PlayerObservation 的白名单只读投影（合同 scoring_view.visible_state）。

    只保留：自己牌、公开副露与牌河、当前窗口事实、庄闲、公开规则状态与
    墙余量；game_id 等运行关联键与观察诊断字符串不进入受限映射。
    """
    rule_state = observation.rule_state
    last_discard = observation.last_discard
    return {
        "seat": observation.seat,
        "phase": observation.phase,
        "round_no": observation.round_no,
        "snapshot_seq": observation.snapshot_seq,
        "dealer_seat": observation.dealer_seat,
        "turn_seat": observation.turn_seat,
        "responding_seats": tuple(observation.responding_seats),
        "my_hand": tuple(tile.code for tile in observation.my_hand),
        "drawn_tile": observation.drawn_tile.code if observation.drawn_tile else None,
        "discards": tuple(
            tuple(tile.code for tile in river) for river in observation.discards
        ),
        "melds": tuple(
            tuple(
                {
                    "seat": meld.seat,
                    "kind": meld.kind,
                    "tiles": tuple(tile.code for tile in meld.tiles),
                    "from_seat": meld.from_seat,
                }
                for meld in seat_melds
            )
            for seat_melds in observation.melds
        ),
        "hand_counts": tuple(observation.hand_counts),
        "last_discard": (
            {
                "seat": last_discard.seat,
                "tile": last_discard.tile.code,
                "seq": last_discard.seq,
            }
            if last_discard
            else None
        ),
        "remaining_tile_count": observation.remaining_tile_count,
        "table_scores": tuple(observation.scores),
        "rule_state": {
            "wealth_god": rule_state.wealth_god.code,
            "baotou": rule_state.baotou,
            "chain_count": rule_state.chain_count,
            "catch_play": rule_state.catch_play,
            "catch_play_owner_seat": rule_state.catch_play_owner_seat,
        },
        "chain_piao": observation.chain_piao,
        "gang_draw": observation.gang_draw,
    }


@dataclass(frozen=True)
class ScoringView:
    """一个动作窗口内候选代码可见的全部只读事实（sitin-scoring-view/4）。

    信息权限：visible_state 直接持有 PlayerObservation 引用并只提供白名单
    只读访问器（不复制可变状态，PlayerObservation 本身冻结）；不含 WorldState、
    研究标签、实验种子、token、评估分组身份或赛后结果；decision_id 等
    运行关联键不入视图。受限候选经 candidate_view() 得到纯原始值映射。
    """

    schema_version: str  # 固定 sitin-scoring-view/4；结构面/语义不兼容变更升版本并登记
    visible_state: PlayerObservation  # 白名单只读观察（信息权限见各访问器）
    actions: Tuple[ActionView, ...]  # 按 action_key 严格升序的不可变动作表
    analysis_profile: AnalysisProfileView  # 语义版本与工作量上限快照
    competition: Optional[CompetitionView] = None  # 可见赛事上下文；无权/陈旧为空
    reference_features: Tuple[ReferenceFeature, ...] = ()  # 参考代理；可为空

    def __post_init__(self) -> None:
        if self.schema_version != SCORING_VIEW_SCHEMA_VERSION:
            raise ValueError(
                "ScoringView.schema_version 必须是 {0!r}".format(
                    SCORING_VIEW_SCHEMA_VERSION
                )
            )
        if not isinstance(self.visible_state, PlayerObservation):
            raise ValueError("ScoringView.visible_state 必须是 PlayerObservation")
        keys = [item.action_key for item in self.actions]
        if keys != sorted(keys) or len(set(keys)) != len(keys):
            raise ValueError("ScoringView.actions 必须按 action_key 严格升序且无重复")

    # —— 第一方只读访问器：白名单字段的稳定投影，不含运行关联键 ——

    def hand_codes(self) -> Tuple[str, ...]:
        """本人手牌牌码，保留官方顺序；紧急“最右一张”语义依赖该顺序。"""
        return tuple(tile.code for tile in self.visible_state.my_hand)

    def drawn_tile_code(self) -> Optional[str]:
        """刚摸到的牌码；非摸牌窗口为空。"""
        tile = self.visible_state.drawn_tile
        return tile.code if tile else None

    def discards_codes(self) -> Tuple[Tuple[str, ...], ...]:
        """四家牌河牌码，外层固定按座位 0—3。"""
        return tuple(
            tuple(tile.code for tile in river) for river in self.visible_state.discards
        )

    def hand_counts(self) -> Tuple[int, ...]:
        """四家剩余手牌张数，按座位 0—3。"""
        return tuple(self.visible_state.hand_counts)

    def table_scores(self) -> Tuple[int, ...]:
        """当前桌内积分，按座位 0—3（另一基准 competition.stage_scores 可为空）。"""
        return tuple(self.visible_state.scores)

    def wall_remaining(self) -> Optional[int]:
        """官方墙余量；官方未提供时为空（不得自行补零）。"""
        return self.visible_state.remaining_tile_count

    def phase(self) -> str:
        """官方阶段字符串原样透传。"""
        return self.visible_state.phase

    def seat_index(self) -> int:
        """本人座位，0—3。"""
        return self.visible_state.seat

    def expected_action_keys(self) -> Tuple[str, ...]:
        """输入动作表的全部键，升序；完整性验证以此为基准。"""
        return tuple(item.action_key for item in self.actions)

    def candidate_view(self) -> Dict[str, Any]:
        """受限候选可见的纯原始值映射（五个合同字段 + schema_version）。

        值只含 dict/tuple/str/int/float/bool/None；不携带任何值对象引用，
        候选无法借此触达 PlayerObservation 以外的对象或修改输入。
        """
        actions = tuple(_action_mapping(item, self.visible_state.seat) for item in self.actions)
        competition = None
        if self.competition is not None:
            competition = {
                "stage_scores": self.competition.stage_scores,
                "table_scores": self.competition.table_scores,
                "current_stage_scores": self.competition.current_stage_scores,
                "freshness_masks": self.competition.freshness_masks,
            }
        profile = {
            "semantics_version": self.analysis_profile.semantics_version,
            "max_expansions": self.analysis_profile.max_expansions,
            "max_routes_per_candidate": self.analysis_profile.max_routes_per_candidate,
            "truncation_note": self.analysis_profile.truncation_note,
            "ruleset_version": self.analysis_profile.ruleset_version,
        }
        references = tuple(
            {
                "name": item.name,
                "value": item.value,
                "version": item.version,
                "unit": item.unit,
                "missing_reason": item.missing_reason,
            }
            for item in self.reference_features
        )
        return {
            "schema_version": self.schema_version,
            "visible_state": _observation_mapping(self.visible_state),
            "competition": competition,
            "actions": actions,
            "analysis_profile": profile,
            "reference_features": references,
        }


def _entry_from_mapping(raw: Any, index: int) -> ActionScore:
    """把候选返回的单条映射转成 ActionScore；形状错误整批 ValueError。"""
    where = "entries[{0}]".format(index)
    if not isinstance(raw, dict):
        raise ValueError("{0} 必须是映射".format(where))
    if "action_key" not in raw or "score" not in raw or "trace" not in raw:
        raise ValueError(
            "{0} 必须同时包含 action_key/score/trace 三个字段".format(where)
        )
    try:
        return ActionScore(
            action_key=raw["action_key"],
            score=raw["score"],
            trace=raw["trace"],
        )
    except ValueError as exc:
        raise ValueError("{0}: {1}".format(where, exc)) from exc


def run_scoring_skeleton(
    view: ScoringView,
    candidate_fn: Callable[[Mapping[str, Any]], Mapping[str, Any]],
) -> ScoreBatch:
    """固定骨架运行顺序（§4.1 第 4—5 步）：调用候选并验证完整返回。

    candidate_fn 收到 view.candidate_view() 的只读映射，返回
    {"status": "SCORED", "entries": [...]} 或 {"status": "ABSTAIN", "reason": ...}。
    完整性验证：SCORED 时全部输入动作恰好一项、键合法、分数有限且非布尔、
    trace 有界；任何验证失败抛 ValueError，由调用方降级到已备紧急计划，
    绝不部分补零、不拼 V2 分数。候选自身异常转换为 ValueError；
    WorkloadExceeded 等 BaseException 原样上抛（执行器终止信号）。
    """
    if not isinstance(view, ScoringView):
        raise ValueError("run_scoring_skeleton 需要 ScoringView 输入")
    expected = view.expected_action_keys()
    if not expected:
        raise ValueError("输入动作表为空，窗口必须先备好合法紧急计划")
    try:
        raw = candidate_fn(view.candidate_view())
    except Exception as exc:  # noqa: BLE001 - 候选任意异常都使整批失效
        raise ValueError(
            "候选执行失败: {0}: {1}".format(type(exc).__name__, exc)
        ) from exc
    if not isinstance(raw, dict):
        raise ValueError("候选必须返回映射，得到 {0}".format(type(raw).__name__))
    status = raw.get("status")
    if status == STATUS_ABSTAIN:
        reason = raw.get("reason")
        if not isinstance(reason, str) or not reason:
            raise ValueError("ABSTAIN 必须给出非空 reason，不得用特殊数值表示未知")
        carried = raw.get("entries")
        if carried not in (None, (), []):
            raise ValueError("ABSTAIN 批不得携带评分条目（不能部分成功后用 0 补齐）")
        return ScoreBatch(status=STATUS_ABSTAIN, entries=(), reason=reason)
    if status != STATUS_SCORED:
        raise ValueError("status 必须是 {0} 之一，得到 {1!r}".format(STATUS_VALUES, status))
    entries_raw = raw.get("entries")
    if not isinstance(entries_raw, (list, tuple)):
        raise ValueError("SCORED 的 entries 必须是列表或元组")
    entries = tuple(
        _entry_from_mapping(item, index) for index, item in enumerate(entries_raw)
    )
    got = [entry.action_key for entry in entries]
    expected_set = set(expected)
    got_set = set(got)
    if len(got_set) != len(got):
        raise ValueError("评分存在重复动作键：{0}".format(sorted(got)))
    missing = sorted(expected_set - got_set)
    if missing:
        raise ValueError("评分遗漏动作键：{0}".format(missing))
    extra = sorted(got_set - expected_set)
    if extra:
        raise ValueError("评分包含越界动作键：{0}".format(extra))
    reason = raw.get("reason")
    if reason is not None and (not isinstance(reason, str) or not reason):
        raise ValueError("SCORED 的 reason 必须是非空字符串或空")
    return ScoreBatch(status=STATUS_SCORED, entries=entries, reason=reason)


def _trace_reasons(trace: Mapping[str, Any]) -> Tuple[str, ...]:
    """从 trace 提取稳定、有界的 reasons 摘要；键排序保证确定性。"""
    reasons: List[str] = []
    for key in sorted(trace):
        value = trace[key]
        if isinstance(value, (bool, int, float, str)):
            reasons.append("{0}={1}".format(key, value))
        if len(reasons) >= 6:
            break
    return tuple(reasons) if reasons else (CANDIDATE_KIND,)


def batch_to_ranked_candidates(
    batch: ScoreBatch,
    actions: Sequence[ActionView],
) -> Tuple[RankedCandidate, ...]:
    """把 SCORED 批适配为 RankedCandidate 列表（合同 entry_point.rank_contract）。

    - 新总分放单个 ScorePart，精确保持 total_score == sum(score_parts)；
      非线性机制明细留在有版本 trace，不拆成虚假可加贡献。
    - 排序按分数降序、action_key 升序稳定排列；rank 从 1 开始连续。
    - R2/S5：完整有界结构化解释不再在适配时丢弃——entry.trace 原样挂到
      RankedCandidate.score_trace（带 trace_schema 版本键，深度≤3、单串
      ≤4096、整批 ≤32KiB 已在 ScoreBatch 构造期验证）；reasons 仍是有界
      人读摘要。
    - ABSTAIN 批返回空元组：调用方沿用已备紧急计划，本函数不拼任何分数。
    """
    if not isinstance(batch, ScoreBatch):
        raise ValueError("batch_to_ranked_candidates 需要 ScoreBatch 输入")
    if batch.status != STATUS_SCORED or not batch.entries:
        return ()
    by_key = {item.action_key: item for item in actions}
    ordered = sorted(batch.entries, key=lambda entry: (-entry.score, entry.action_key))
    candidates: List[RankedCandidate] = []
    for rank, entry in enumerate(ordered, start=1):
        action_view = by_key[entry.action_key]
        part = ScorePart(name=CANDIDATE_KIND, value=entry.score)
        candidates.append(
            RankedCandidate(
                action=action_view.action,
                action_key=entry.action_key,
                rank=rank,
                total_score=entry.score,
                score_parts=(part,),
                reasons=_trace_reasons(entry.trace),
                score_trace={
                    "trace_schema": SCORE_TRACE_SCHEMA_VERSION,
                    "detail": dict(entry.trace),
                },
            )
        )
    return tuple(candidates)
