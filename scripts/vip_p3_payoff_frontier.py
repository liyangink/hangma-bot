"""VIP 条件胡支付前沿：保留规则真值，绝不把容量当概率。

只重组 HangmaRules 同次合法候选的 CandidateValueFacts。每条路线
必须先满足动作生效、指定跟打以及本人确实摸到指定牌；吃碰明杠
还须获完整响应裁决。不同跟打选择互斥，不得累加。
"""

from __future__ import annotations

from dataclasses import dataclass

from hangma_bot.hangma.interface import RuleCandidate, ValueConditions, ValueCoverage
from hangma_bot.hangma.route_transition import ConditionalPhase, ConditionalRoot
from hangma_bot.kernel.actions import CANONICAL_TILE_INDEX, Discard, Hu

from scripts.vip_p3_afterstate_contract import AfterstateStatus, project_afterstate


@dataclass(frozen=True)
class PayoffCell:
    """摸到一个给定牌码并立即胡的同源结算；分数为本座净积分。"""

    draw_code: str
    public_unseen_count: int  # 规则见证的公开未见张数；不是牌墙概率
    fan: int
    own_net: int
    score_delta: tuple[int, int, int, int]  # 按官方座位 0—3
    details: tuple[str, ...]
    capacity_exact_after_effect: bool  # 只在已生效后态且逐码证据 exact 时为真


@dataclass(frozen=True)
class PayoffPath:
    """一个独立跟打选择及摸牌来源；不同 path 是互斥决策分支。"""

    followup_discard: str | None  # 吃碰获裁决后的本人跟打；其他动作为空
    conditions: ValueConditions  # 已执行动作、未被截尾且下一次摸牌的限定
    cells: tuple[PayoffCell, ...]  # 不同摸牌码互斥，按规范牌序排列

    @property
    def public_capacity_sum(self) -> int:
        """本路径条件胡的公开未见张数总和；不能解释为牌墙成功率。"""

        return sum(cell.public_unseen_count for cell in self.cells)

    @property
    def capacity_weighted_net(self) -> int:
        """仅用于支付规模比较的张数×积分和；不是预期积分。"""

        return sum(cell.public_unseen_count * cell.own_net for cell in self.cells)


@dataclass(frozen=True)
class PayoffFrontier:
    """一条合法根的可核支付见证；未来兑现概率完全留给价值模型。"""

    action_key: str
    afterstate_status: AfterstateStatus
    immediate_hu_net: int | None  # 仅当前合法胡填值
    paths: tuple[PayoffPath, ...]


@dataclass(frozen=True)
class OneDrawPayoffComponent:
    """若下一次本人普通摸牌确实发生，交换性近似下的直接胡支付部分。

    不含活到下一摸的概率、摸后不胡的续打价值、他家抢先胡与流局损益；
    因此不是整手动作的预期积分，也不是线上发布评分。
    """

    total_public_unseen: int  # 所有规范牌码的公开未见物理张数
    direct_hu_capacity: int  # 下一摸可直接胡的公开未见物理张数
    capacity_weighted_own_net: int  # 张数×本座净分之和，未除分母
    conditional_exchangeable_direct_hu_net: float  # 上式÷总未见；只在交换性近似下解释


def extract_payoff_frontier(
    candidate: RuleCandidate, root: ConditionalRoot, seat: int,
) -> PayoffFrontier:
    """核同次规则结算、路径互斥与后态公开容量证据。"""

    after = project_afterstate(candidate, root, seat)
    facts = candidate.value_facts
    if facts is None or facts.coverage is not ValueCoverage.COMPLETE:
        raise ValueError("条件支付见证不完整或被工作量截断")
    if isinstance(candidate.action, Hu):
        if (facts.immediate_settlement is None or root.settlement != facts.immediate_settlement
                or facts.routes):
            raise ValueError("当前胡条件支付与同源结算不一致")
        return PayoffFrontier(candidate.action_key, after.status,
                              after.exact_current_hu_net, ())
    if facts.immediate_settlement is not None:
        raise ValueError("非胡动作不能携即时结算")
    grouped: dict[tuple[str | None, str], tuple[ValueConditions, dict[str, PayoffCell]]] = {}
    effective = after.status is AfterstateStatus.EFFECTIVE_PENDING_EVENT
    state = root.branches[0].state if effective else None
    for route in facts.routes:
        if route.conditional_settlement.fan < 1 or sum(route.conditional_settlement.score_delta) != 0:
            raise ValueError("条件胡结算积分不守恒")
        key = (route.followup_discard, route.conditions.draw_kind)
        if key not in grouped:
            grouped[key] = (route.conditions, {})
        conditions, cells = grouped[key]
        if conditions != route.conditions:
            raise ValueError("同一跟打和摸牌来源出现矛盾的条件前缀")
        for tile in route.useful_tiles:
            if tile.code in cells or tile.remaining_estimate <= 0:
                raise ValueError("同一路径摸牌码重复或公开未见容量无效")
            exact = False
            if effective and state.unseen_capacities is not None and state.unseen_evidence is not None:
                index = CANONICAL_TILE_INDEX[tile.code]
                if state.unseen_evidence[index] == "exact":
                    if state.unseen_capacities[index] != tile.remaining_estimate:
                        raise ValueError("已生效后态容量与规则支付见证不同")
                    exact = True
            result = route.conditional_settlement
            cells[tile.code] = PayoffCell(
                draw_code=tile.code, public_unseen_count=tile.remaining_estimate,
                fan=result.fan, own_net=result.score_delta[seat],
                score_delta=result.score_delta, details=result.details,
                capacity_exact_after_effect=exact,
            )
    paths = tuple(PayoffPath(followup, conditions, tuple(
        cells[code] for code in sorted(cells, key=CANONICAL_TILE_INDEX.get)
    )) for (followup, _), (conditions, cells) in sorted(
        grouped.items(), key=lambda item: (item[0][0] or "", item[0][1])
    ))
    return PayoffFrontier(candidate.action_key, after.status, None, paths)


def ordinary_discard_one_draw_component(
    candidate: RuleCandidate, root: ConditionalRoot, seat: int,
) -> OneDrawPayoffComponent:
    """仅对已生效普通弃牌求条件支付部分；缺逐码精确证据即拒绝。"""

    if not isinstance(candidate.action, Discard):
        raise ValueError("一次普通摸牌支付分量仅支持弃牌根")
    front = extract_payoff_frontier(candidate, root, seat)
    if (front.afterstate_status is not AfterstateStatus.EFFECTIVE_PENDING_EVENT
            or len(root.branches) != 1
            or root.branches[0].state.phase not in (
                ConditionalPhase.RESPONSE_RESOLUTION, ConditionalPhase.PUBLIC_WAIT)
            or len(front.paths) > 1
            or any(path.conditions.draw_kind != "normal"
                   or path.followup_discard is not None for path in front.paths)):
        raise ValueError("弃牌根缺独立的下一次普通摸牌条件路径")
    state = root.branches[0].state
    if (state.unseen_capacities is None or state.unseen_evidence is None
            or any(status != "exact" for status in state.unseen_evidence)
            or any(value is None for value in state.unseen_capacities)):
        raise ValueError("下一摸交换性近似缺完整精确公开未见容量")
    total = sum(state.unseen_capacities)
    if total <= 0:
        raise ValueError("下一摸交换性近似没有未见物理牌")
    path = front.paths[0] if front.paths else None
    direct = path.public_capacity_sum if path is not None else 0
    weighted = path.capacity_weighted_net if path is not None else 0
    if direct > total or (path is not None and any(
        not cell.capacity_exact_after_effect for cell in path.cells
    )):
        raise ValueError("条件胡容量超过总未见或证据未达精确")
    return OneDrawPayoffComponent(total, direct, weighted, weighted / total)
