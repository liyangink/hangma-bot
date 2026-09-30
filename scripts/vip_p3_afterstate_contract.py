"""VIP 研究量具：区分已生效动作后态与尚待响应裁决的条件牌形。

只消费同次规则分析给出的合法候选和条件根。这里不预测他家选择、
未来摸牌或牌墙，也不把吃碰的预列分支伪装成已经执行的公开状态。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from hangma_bot.hangma.hand_analysis import analyse_hand
from hangma_bot.hangma.interface import RuleCandidate
from hangma_bot.hangma.route_transition import (
    ConditionalPhase, ConditionalRoot, ConditionalRouteState,
)
from hangma_bot.kernel.actions import Chi, Discard, Gang, GangKind, Hu, Pass, Peng


class AfterstateStatus(str, Enum):
    """后态证据等级；条件牌形不能用于声称动作已获裁决。"""

    EXACT_TERMINAL = "exact_terminal"
    EFFECTIVE_PENDING_EVENT = "effective_pending_event"
    CONDITIONAL_AWARD = "conditional_award"
    UNRESOLVED_RESPONSE = "unresolved_response"


@dataclass(frozen=True)
class OwnHandShape:
    """本人可见牌形；仅在标明的生效或获裁决条件下成立。"""

    concealed_count: int  # 本座暗牌张数；不含副露
    meld_count: int  # 本座已固定面子数；吃、碰、杠各计一组
    whites_held: int  # 本座手留白板张数
    standard_shanten: int  # 标准型向听；-1 为已胡
    seven_pairs_shanten: int | None  # 七对向听；有副露时为空
    useful_code_count: int  # 有效牌种类数，不等于未见物理张数
    baotou: bool  # 条件机械状态中的爆头资格
    chain_count: int  # 当前动作链长度
    chain_piao: int | None  # 链内飘白数；证据缺失时为空
    wall_remaining: int | None  # 公开剩余牌墙张数；未知时为空


@dataclass(frozen=True)
class AfterstateFacts:
    """一条合法根的后态合同；终局净分仅在已结算胡根上有值。"""

    action_key: str
    status: AfterstateStatus
    phase: ConditionalPhase | None  # 下一待给定事件；即时终局为空
    own_shape: OwnHandShape | None  # 仅已生效后态或获裁决条件牌形可填
    exact_current_hu_net: int | None  # 本座净分；其他动作不得填零冒充结果
    public_after_effect_known: bool  # 真正已生效的条件公开视图是否存在


def _shape(state: ConditionalRouteState) -> OwnHandShape:
    """复用唯一规则数学来源，不在研究量具内重算向听。"""

    summary = analyse_hand(state.concealed, state.meld_count)
    return OwnHandShape(
        concealed_count=len(state.concealed), meld_count=state.meld_count,
        whites_held=summary.whites_held,
        standard_shanten=summary.standard_shanten,
        seven_pairs_shanten=summary.chiitoi_shanten,
        useful_code_count=len(summary.useful_tiles),
        baotou=state.baotou, chain_count=state.chain_count,
        chain_piao=state.chain_piao, wall_remaining=state.wall_remaining,
    )


def project_afterstate(candidate: RuleCandidate, root: ConditionalRoot, seat: int) -> AfterstateFacts:
    """按合法动作语义核条件根；机械缺口或矛盾状态直接报错。"""

    if seat not in range(4) or candidate.action_key != root.action_key or root.gap_kind is not None:
        raise ValueError("后态事实缺合法根身份、座位或机械完整性")
    action = candidate.action
    if isinstance(action, Hu):
        if (root.settlement is None or root.pending_condition is not None
                or len(root.branches) != 1
                or root.branches[0].state.phase is not ConditionalPhase.TERMINAL):
            raise ValueError("当前胡缺精确终局")
        return AfterstateFacts(root.action_key, AfterstateStatus.EXACT_TERMINAL,
                               None, None, root.settlement.score_delta[seat], False)
    if root.settlement is not None:
        raise ValueError("非胡动作混入即时结算")
    if isinstance(action, Pass):
        if (len(root.branches) != 1 or root.proposal_state is None
                or root.pending_condition is not ConditionalPhase.RESPONSE_RESOLUTION):
            raise ValueError("过牌缺待裁决响应")
        return AfterstateFacts(root.action_key, AfterstateStatus.UNRESOLVED_RESPONSE,
                               root.pending_condition, None, None, False)
    if isinstance(action, (Chi, Peng)) or (
        isinstance(action, Gang) and action.kind is GangKind.EXPOSED
    ):
        if (root.proposal_state is None
                or root.pending_condition is not ConditionalPhase.RESPONSE_RESOLUTION
                or not root.branches
                or not all(branch.state.structural_only for branch in root.branches)):
            raise ValueError("吃碰明杠的获裁决条件分支缺失")
        # 吃碰的 claim_state 只含“若获裁决”的本人局部牌形；公开副露、
        # 保留弃牌和未见容量仍待完整响应选择集合，不能在这里读取。
        state = root.claim_state if isinstance(action, (Chi, Peng)) else root.branches[0].state
        if state is None:
            raise ValueError("获裁决条件牌形缺失")
        return AfterstateFacts(root.action_key, AfterstateStatus.CONDITIONAL_AWARD,
                               root.pending_condition, _shape(state), None, False)
    if isinstance(action, (Discard, Gang)):
        if (len(root.branches) != 1 or root.proposal_state is not None
                or root.branches[0].state.structural_only
                or root.branches[0].state.public_view is None
                or root.pending_condition != root.branches[0].state.phase):
            raise ValueError("已生效动作缺完整条件公开后态")
        state = root.branches[0].state
        return AfterstateFacts(root.action_key, AfterstateStatus.EFFECTIVE_PENDING_EVENT,
                               state.phase, _shape(state), None, True)
    raise ValueError("未知合法动作族")
