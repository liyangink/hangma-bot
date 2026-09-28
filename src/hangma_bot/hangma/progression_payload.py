"""分支进展载荷（family_progress）的规则计算（v4 §4.2/§5.1/§7.3 B1）。

四个规则家族的相对进展与证据状态只来自规则数学与可见观察：

- branch：动作前后已知分牌型（普通/七对）最优向听比较（hand_analysis
  已有数学）；开门副露使七对路线规则性关闭记 CLOSE/CLOSED_PROVEN；
  豪华七对是结算级细分（由 ValueRoute 条件结算携带），不参与向听比较，
  不会因此产生 UNKNOWN。
- chain：已知规则转移后的链次数相对动作前（progression.chain_after_action
  对照 observation.rule_state.chain_count 权威值）；不预测未来杠或飘。
- four_white：距四白等值条件距离 4−(手留白+链内飘白)（progression.
  wealth_after_action 与链转移的飘白）；链内飘白归因未知时 UNKNOWN；
  等值条件非单调量，任何单纯弃白都不写 CLOSE。
- baotou：observation.rule_state.baotou 权威值与 progression.
  baotou_after_action 同源推导的转移对比；无确定转移（终局等）UNKNOWN。

route_status：有 ValueRoute 条件见证 → WITNESSED；合法可达未见证 →
OPEN_UNCERTAIN；规则证明关闭（七对有副露）→ CLOSED_PROVEN；进展分析
未进入或超限 → UNANALYZED（由调用方以空 family_progress/UNKNOWN 条目
表达）。

红线（模块规范）：不调用任何策略/评分器/LLM；不读取未来牌墙；每候选
计算受 ValueAnalysisLimits 共享预算约束（由 value_analysis 计费并截获
超限），超限输出 UNKNOWN+UNANALYZED 并携带 RuleIssue，不截断冒充完整。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional, Tuple

from hangma_bot.kernel.actions import Action, Chi, Discard, Gang, GangKind, Peng, Tile
from hangma_bot.kernel.observation import PlayerObservation

from . import hand_analysis, progression, special_rules
from .interface import (
    CandidateFactKind,
    CandidateFacts,
    CandidateValueFacts,
    FamilyId,
    FamilyProgress,
    ProgressKind,
    RuleIssue,
    RouteStatus,
    ValueRoute,
)
from .internal_types import WEALTH_CODE, WindowContext

class ProgressionPayloadError(Exception):
    """进展载荷计算意外失败；engine 据此独立降级（DEGRADED）而不影响
    可选分值分析的非降级口径（分值失败只收敛到 value_facts.issues）。"""


_FAMILY_ORDER: Tuple[FamilyId, ...] = (
    FamilyId.BRANCH,
    FamilyId.CHAIN,
    FamilyId.FOUR_WHITE,
    FamilyId.BAOTOU,
)
"""载荷输出顺序 = FamilyId 声明序（CandidateFacts.family_progress 契约）。"""

_PAYLOAD_KINDS = (CandidateFactKind.HAND_PROGRESS, CandidateFactKind.WIN)
"""携带进展载荷的事实种类；NOT_APPLICABLE/ANALYSIS_FAILED/未生产不携带。"""


class BeforeState:
    """一次请求共享的动作前事实；全部来自当前观察与手牌数学（纯计算）。

    同一 analyze 请求的全部候选共用同一动作前状态；构造消耗一次手牌
    分析（由调用方计入共享预算），失败按模块故障边界向上传播。
    """

    def __init__(
        self, observation: PlayerObservation, context: WindowContext, meld_count: int
    ) -> None:
        self.hand = context.full_hand()
        self.meld_count = meld_count
        self.summary = hand_analysis.analyse_hand(self.hand, meld_count)
        self.chain_count = observation.rule_state.chain_count
        self.chain_piao = observation.chain_piao
        self.baotou = observation.rule_state.baotou


@dataclass(frozen=True)
class _Witnesses:
    """从候选 ValueRoute 条件见证推出的四家族见证布尔；无路线则全 False。"""

    branch: bool
    chain: bool
    four_white: bool
    baotou: bool


def _witnesses(routes: Tuple[ValueRoute, ...]) -> _Witnesses:
    """ValueRoute 条件见证扫描；只读已计算路线，不触发任何新分析。

    branch：任一一次摸牌成胡路线即等待路线见证；chain：路线条件链次数
    >0（条件结算含链倍率）；four_white：路线成胡时手留白+链内飘白恰为 4
    （special_rules.four_white_indicator，白摸入计入手留白）；baotou：
    路线条件爆头为真。
    """

    branch = chain = four_white = baotou = False
    for route in routes:
        branch = True
        conditions = route.conditions
        if conditions.chain_count > 0:
            chain = True
        if conditions.baotou:
            baotou = True
        pre_whites = sum(1 for code in conditions.pre_draw_hand if code == WEALTH_CODE)
        for tile in route.useful_tiles:
            win_whites = pre_whites + (1 if tile.code == WEALTH_CODE else 0)
            if special_rules.four_white_indicator(win_whites, conditions.chain_piao) is True:
                four_white = True
    return _Witnesses(
        branch=branch, chain=chain, four_white=four_white, baotou=baotou
    )


def _after_melds(action: Action, meld_count: int) -> int:
    """动作后的折算副露数；补杠不新增面子块（与 _gang_basis 同口径）。"""

    if isinstance(action, (Chi, Peng)):
        return meld_count + 1
    if isinstance(action, Gang):
        return meld_count + (0 if action.kind is GangKind.ADDED else 1)
    return meld_count


def _status(witnessed: bool) -> RouteStatus:
    """可达路线的证据状态：有见证 WITNESSED，否则合法可达未见证。"""

    return RouteStatus.WITNESSED if witnessed else RouteStatus.OPEN_UNCERTAIN


def _branch_entry(
    state: BeforeState, facts: CandidateFacts, after_melds: int, witnessed: bool
) -> FamilyProgress:
    """branch：开门关闭七对记 CLOSE/CLOSED_PROVEN；否则比较已知分牌型
    最优向听（动作前 hand_analysis 数学 vs 动作后该弃牌/该分支结果）。"""

    before = state.summary.shanten
    if state.meld_count == 0 and after_melds > 0:
        return FamilyProgress(
            family=FamilyId.BRANCH,
            progress=ProgressKind.CLOSE,
            route_status=RouteStatus.CLOSED_PROVEN,
            basis=(
                "动作使副露 0→{0}，七对路线规则性关闭（七对仅门清成立）；"
                "普通型向听比较见 standard_shanten_after 与 followup_branches"
                .format(after_melds)
            ),
        )
    after = facts.shanten_after  # HAND_PROGRESS 综合向听；WIN 为 -1
    if after is None:
        return FamilyProgress(
            family=FamilyId.BRANCH,
            progress=ProgressKind.UNKNOWN,
            route_status=RouteStatus.UNANALYZED,
            basis="动作后已知分牌型向听缺失，无法与动作前 {0} 比较".format(before),
        )
    if after < before:
        kind = ProgressKind.ADVANCE
    elif after > before:
        kind = ProgressKind.RETREAT
    else:
        kind = ProgressKind.SAME
    return FamilyProgress(
        family=FamilyId.BRANCH,
        progress=kind,
        route_status=_status(witnessed),
        basis=(
            "动作前后已知分牌型最优向听 {0}→{1}（hand_analysis 数学；"
            "七对有副露时已关闭不计入；豪华细分属条件结算不参与比较）".format(
                before, after
            )
        ),
    )


def _chain_entry(
    state: BeforeState, chain_after: int, witnessed: bool
) -> FamilyProgress:
    """chain：已知规则转移链次数相对动作前；不预测未来杠或飘。"""

    before = state.chain_count
    if chain_after > before:
        kind = ProgressKind.ADVANCE
    elif chain_after < before:
        kind = ProgressKind.RETREAT
    else:
        kind = ProgressKind.SAME
    return FamilyProgress(
        family=FamilyId.CHAIN,
        progress=kind,
        route_status=_status(witnessed),
        basis=(
            "已知规则转移链次数 {0}→{1}（progression.chain_after_action 对照"
            " observation.rule_state.chain_count；杠 +1、飘 +1、非飘弃牌断链清零、"
            "吃碰过不变；不预测未来杠或飘）".format(before, chain_after)
        ),
    )


def _four_white_entry(
    state: BeforeState, action: Action, piao_after: Optional[int], witnessed: bool
) -> FamilyProgress:
    """four_white：距四白等值条件距离 4−(手留白+链内飘白) 的前后比较。"""

    whites_before = state.summary.whites_held
    whites_after = progression.wealth_after_action(whites_before, action)
    status = _status(witnessed)
    if state.chain_piao is None or piao_after is None:
        return FamilyProgress(
            family=FamilyId.FOUR_WHITE,
            progress=ProgressKind.UNKNOWN,
            route_status=status,
            basis=(
                "链内飘白归因未知（动作前 chain_piao={0}、动作后 {1}），"
                "四白距离 4−(手留白+链内飘白) 不可比；不写数值冒充".format(
                    state.chain_piao, piao_after
                )
            ),
        )
    distance_before = 4 - (whites_before + state.chain_piao)
    distance_after = 4 - (whites_after + piao_after)
    if distance_after < distance_before:
        kind = ProgressKind.ADVANCE
    elif distance_after > distance_before:
        kind = ProgressKind.RETREAT
    else:
        kind = ProgressKind.SAME
    return FamilyProgress(
        family=FamilyId.FOUR_WHITE,
        progress=kind,
        route_status=status,
        basis=(
            "距四白等值条件距离 4−(手留白+链内飘白)：{0}→{1}"
            "（手留白 {2}→{3}，链内飘白 {4}→{5}；等值条件非单调量，"
            "不因单纯弃白写 CLOSE）".format(
                distance_before, distance_after,
                whites_before, whites_after,
                state.chain_piao, piao_after,
            )
        ),
    )


def _baotou_entry(
    state: BeforeState, after: Optional[bool], witnessed: bool
) -> FamilyProgress:
    """baotou：权威状态与同源推导的动作后状态对比；无确定转移 UNKNOWN。"""

    before = state.baotou
    status = _status(witnessed)
    if after is None:
        return FamilyProgress(
            family=FamilyId.BAOTOU,
            progress=ProgressKind.UNKNOWN,
            route_status=status,
            basis=(
                "动作后爆头状态无确定转移（progression.baotou_after_action "
                "返回未知：终局或动作形状未定），未知转移不得猜测"
            ),
        )
    if after and not before:
        kind = ProgressKind.ADVANCE
    elif before and not after:
        kind = ProgressKind.RETREAT
    else:
        kind = ProgressKind.SAME
    return FamilyProgress(
        family=FamilyId.BAOTOU,
        progress=kind,
        route_status=status,
        basis=(
            "权威爆头 {0}→{1}（observation.rule_state.baotou 与 progression."
            "baotou_after_action 同源推导：弃牌按弃后暗牌任意听重判，"
            "吃碰杠过继承）".format(before, after)
        ),
    )


def _build_payload(
    state: BeforeState, action: Action, facts: CandidateFacts,
    value_facts: CandidateValueFacts,
) -> Tuple[Tuple[FamilyProgress, ...], Optional[bool]]:
    """一次同源计算四家族进展和动作后爆头事实。"""

    witnesses = _witnesses(value_facts.routes)
    after_melds = _after_melds(action, state.meld_count)
    chain_after, piao_after = progression.chain_after_action(
        state.chain_count, state.chain_piao, state.baotou, action
    )
    baotou_after = progression.baotou_after_action(
        state.baotou, action, state.hand, state.meld_count
    )
    entries = (
        _branch_entry(state, facts, after_melds, witnesses.branch),
        _chain_entry(state, chain_after, witnesses.chain),
        _four_white_entry(state, action, piao_after, witnesses.four_white),
        _baotou_entry(state, baotou_after, witnesses.baotou),
    )
    return entries, baotou_after


def build_family_progress(
    state: BeforeState, action: Action, facts: CandidateFacts,
    value_facts: CandidateValueFacts,
) -> Tuple[FamilyProgress, ...]:
    """构建一个候选的四家族进展条目（FamilyId 声明序，恰好四条）。"""

    return _build_payload(state, action, facts, value_facts)[0]


def _append_issue(
    value_facts: CandidateValueFacts, issue: RuleIssue
) -> CandidateValueFacts:
    """把载荷 RuleIssue 追加到该候选的 value_facts.issues（不改动路线）。"""

    return replace(value_facts, issues=value_facts.issues + (issue,))


def attach_payload(
    state: BeforeState, candidate, value_facts: CandidateValueFacts
) -> Tuple[CandidateValueFacts, CandidateFacts]:
    """给单个候选附加 family_progress；返回 (value_facts, facts)。

    适用口径：facts 已生产且 fact_kind ∈ {HAND_PROGRESS, WIN}；其余保持
    原样（family_progress 空元组=未分析）。计算异常向上传播，由
    engine 故障边界收敛为整批 value_facts 失败 + DEGRADED。
    """

    facts = candidate.facts
    if facts is None or facts.fact_kind not in _PAYLOAD_KINDS:
        return value_facts, facts
    entries, baotou_after = _build_payload(
        state, candidate.action, facts, value_facts
    )
    if isinstance(candidate.action, (Chi, Peng)) and facts.followup_branches is not None:
        if baotou_after is None:
            raise ProgressionPayloadError("鸣牌后爆头暂态未知，不能计算后继弃牌链状态")
        chain, piao = progression.chain_after_action(
            state.chain_count, state.chain_piao, state.baotou, candidate.action
        )
        whites = sum(tile.code == WEALTH_CODE for tile in state.hand)
        branches = []
        for branch in facts.followup_branches:
            discard = Discard(Tile(branch.followup_discard))
            branch_chain, branch_piao = progression.chain_after_action(
                chain, piao, baotou_after, discard
            )
            remaining_whites = progression.wealth_after_action(whites, discard)
            four_white = special_rules.four_white_indicator(
                remaining_whites, branch_piao
            )
            branches.append(replace(
                branch, chain_count_after=branch_chain,
                chain_piao_after=branch_piao,
                four_white_qualified_after=four_white,
            ))
        facts = replace(facts, followup_branches=tuple(branches))
    return value_facts, replace(
        facts, family_progress=entries, baotou_after=baotou_after
    )


def attach_unknown_payload(
    candidate, value_facts: CandidateValueFacts, reason: str
) -> Tuple[CandidateValueFacts, CandidateFacts]:
    """预算超限时的降级载荷：UNKNOWN 进展 + UNANALYZED 证据 + RuleIssue。

    只追加 RuleIssue（value_analysis.limit 已记录截断原因时按原样保留），
    不删除已证明的路线，不产出任何数值进展冒充完整。
    """

    facts = candidate.facts
    issue = RuleIssue(
        "progression_payload.limit",
        "候选 {key} 进展载荷未完成：{reason}".format(
            key=candidate.action_key, reason=reason
        ),
    )
    value_facts = _append_issue(value_facts, issue)
    if facts is None or facts.fact_kind not in _PAYLOAD_KINDS:
        return value_facts, facts
    entries = tuple(
        FamilyProgress(
            family=family,
            progress=ProgressKind.UNKNOWN,
            route_status=RouteStatus.UNANALYZED,
            basis=(
                "进展分析超工作量上限未进入（{reason}）；"
                "不产出数值进展".format(reason=reason)
            ),
        )
        for family in _FAMILY_ORDER
    )
    return value_facts, replace(facts, family_progress=entries)
