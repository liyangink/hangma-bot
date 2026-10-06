"""合法弃后的一次局部胡资格见证；不展开弃牌、进张或未来事件。

前置与 ``analyze_waiting_draw_witness`` 相同。只判胡数学、动作族门禁、
爆头更新和结算继续复用唯一规则源；结果不伪装为完整动作分析或可推进
的后态。被摸码的容量仅作已验证精确库存的实体增量，不重扫公开历史。
"""

from dataclasses import dataclass, field
from typing import Optional, Tuple

from hangma_bot.kernel.actions import Hu, Tile
from hangma_bot.kernel.config import RuleConfig

from . import action_families, hand_analysis, progression, settlement
from .interface import RuleIssue, Settlement
from .internal_types import TILE_INDEX, WindowContext
from .route_transition import ConditionalPhase, ConditionalRouteState


ROUTE_HU_WITNESS_SCHEMA_VERSION = "vip-local-hu-witness/1"


@dataclass(frozen=True)
class WaitingHuWitness:
    """给定普通摸牌条件下的窄事实；不是完整合法动作表或未来必达资格。

    ``legal_hu`` 与结算分开：数学成胡但链证据或分解缺失时，合法胡仍为
    真，结算为空并附问题。未分析的弃牌、进张和其他动作族没有填充字段。
    仅返回所摸牌码的精确容量变化，不表示完整公开库存已被重新投影。
    """

    tile: Tile  # 本次明示的本人摸牌码，不是从未来牌墙取得
    catch_restricted: bool  # 调用方给定的抓打限制包络
    wall_remaining_before_draw: int  # 含20张保留区的摸前墙余，单位张
    wall_remaining_after_draw: int  # 仅此局部本人摸牌扣一张，单位张
    ruleset_version: str  # 同源条件根绑定的本地规则版本
    legal_hu: bool
    immediate_settlement: Optional[Settlement]  # 四座净积分顺序0—3；非胡/缺证据为空
    issues: Tuple[RuleIssue, ...]  # 仅胡族及其结算的问题，不冒充其他动作族覆盖
    baotou_after_draw: bool  # 同源生命周期更新；普通摸不盲继承旧爆头
    draw_capacity_before: int  # 所摸码已验证精确公开未见张数，含他家暗牌
    draw_capacity_after: int  # 所摸码容量扣一张；不是墙内概率
    local_witness_only: bool = field(default=True, init=False)
    scope: str = field(default="local_given_normal_draw_hu_only", init=False)

    def __post_init__(self) -> None:
        if type(self.legal_hu) is not bool or type(self.catch_restricted) is not bool:
            raise ValueError("局部胡见证的胡真假及限制须为布尔值")
        if self.immediate_settlement is not None and not self.legal_hu:
            raise ValueError("非胡局部见证不能携带胡结算")
        if not isinstance(self.issues, tuple):
            raise ValueError("局部胡见证问题须为不可变元组")
        if (not 1 <= self.draw_capacity_before <= 4
                or self.draw_capacity_after != self.draw_capacity_before - 1
                or self.wall_remaining_after_draw != self.wall_remaining_before_draw - 1):
            raise ValueError("局部摸牌只允许一张实体容量与墙余增量")


def analyze_waiting_hu_witness(
    state: ConditionalRouteState, tile: Tile, *,
    wall_remaining_before_draw: int, catch_restricted: bool, config: RuleConfig,
) -> WaitingHuWitness:
    """只计算合法弃后一次局部普通摸牌的胡真假、实际结算及胡相关问题。

    输入须与完整见证一样有规则身份、座位、公开视图和 ``13-3m`` 等待
    手牌。未裁决结构、末墙不可摸、非精确/零容量或不符配置抛 ValueError。
    公开相容不证明墙内存在，也不证明途中响应全过或他家未先胡。无副作用，
    不产生官方观察、水位或可续行状态；输入规模固定为最多13张及34码容量。
    """

    if state.structural_only:
        raise ValueError("未裁决的结构预列分支不能建立等待摸牌见证")
    if state.phase not in (ConditionalPhase.RESPONSE_RESOLUTION, ConditionalPhase.PUBLIC_WAIT):
        raise ValueError("局部摸牌见证只接受本人合法弃后等待状态")
    if (state.seat is None or state.dealer_seat is None or state.identity is None
            or state.public_view is None):
        raise ValueError("局部摸牌见证缺本人、庄家、规则身份或公开视图")
    if type(state.seat) is not int or state.seat not in range(4):
        raise ValueError("本人座位须在 0—3")
    if type(state.dealer_seat) is not int or state.dealer_seat not in range(4):
        raise ValueError("庄家座位须在 0—3")
    if (state.drawn_tile is not None or state.expected_discard_seat is not None
            or state.expected_replacement_draw
            or len(state.concealed) != 13 - 3 * state.meld_count
            or state.public_view.hand_counts[state.seat] != len(state.concealed)):
        raise ValueError("局部摸牌见证不是本人13-3m张合法弃后等待手牌")
    if type(wall_remaining_before_draw) is not int or wall_remaining_before_draw < 0:
        raise ValueError("局部摸牌见证的墙余必须是非负整数张数")
    if type(catch_restricted) is not bool:
        raise ValueError("局部摸牌见证的抓打限制必须是布尔值")
    if (config.base_score != 1 or config.you_cai_bi_kao
            or state.identity.ruleset_version != config.ruleset_version):
        raise ValueError("局部摸牌见证的规则配置与条件根不一致")
    if wall_remaining_before_draw <= action_families.WALL_RESERVE_TILES:
        raise ValueError("已进入保留区，不能假定继续摸牌")
    if state.unseen_capacities is None:
        raise ValueError("给定摸牌缺公开未见容量证据")
    index = TILE_INDEX[tile.code]
    if state.unseen_evidence is None or state.unseen_evidence[index] != "exact":
        raise ValueError("给定摸牌的公开未见容量证据不精确")
    capacity = state.unseen_capacities[index]
    if capacity is None:
        raise ValueError("给定摸牌的公开未见容量不确定")
    if capacity <= 0:
        raise ValueError("给定摸牌码公开未见容量为零，不可条件摸入")

    baotou = progression.baotou_after_draw(
        state.baotou, state.concealed, state.meld_count, tile, replacement=False)
    context = WindowContext(
        seat=state.seat, phase="draw", turn_seat=state.seat, responding_seats=(),
        hand_tiles=state.concealed, drawn_tile=tile,
        my_chi_count=state.my_chi_count, my_peng_codes=state.my_peng_codes,
        last_discard=None, catch_play=catch_restricted,
        remaining_tile_count=wall_remaining_before_draw - 1,
    )
    full_hand = state.concealed + (tile,)
    hand = hand_analysis.analyse_hand_win(full_hand, state.meld_count)
    try:
        outcome = action_families.hu_candidates(context, hand)
        legal_hu = any(isinstance(candidate.action, Hu) for candidate in outcome.candidates)
        issues = outcome.issues
    except Exception as exc:
        # 与六族组合器的胡族异常边界一致，不能把资格故障冒充精确非胡。
        legal_hu = False
        issues = (RuleIssue("action_families.hu", "动作族 hu 分析异常: {0}: {1}".format(
            type(exc).__name__, exc)),)
    immediate = None
    if legal_hu:
        if state.chain_piao is None:
            issues += (RuleIssue("route_transition.input_evidence",
                                 "链内飘白次数未知，不能结算给定补牌胡"),)
        else:
            split = hand_analysis.win_split(full_hand, state.meld_count)
            if split is None:
                issues += (RuleIssue("route_transition.mechanical",
                                     "胡候选无法还原同源成胡分解"),)
            else:
                immediate = settlement.settle_win(
                    split, state.chain_count, state.chain_piao, baotou,
                    config.base_score, state.seat, state.dealer_seat,
                    pre_draw_hand=state.concealed, meld_set_count=state.meld_count)
    return WaitingHuWitness(
        tile, catch_restricted, wall_remaining_before_draw, wall_remaining_before_draw - 1,
        config.ruleset_version, legal_hu, immediate, issues, baotou, capacity, capacity - 1,
    )
