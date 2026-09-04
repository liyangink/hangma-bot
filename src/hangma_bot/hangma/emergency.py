"""独立紧急路径：不依赖任何复杂分析分支的最终兜底动作。

依据（RULES_EVIDENCE §9、模块 AGENTS.md）：
- 本模块禁止调用向听、有效牌、分解或结算；
- 响应窗口 → 过；抓打圈 → 打刚摸牌；普通出牌 → 打官方顺序最右一张；
- 无动作权或观察不完整时返回 None，不伪造动作。

性能约束：本文件不得分配大对象、不得做任何搜索；目标是 P99 远低于 1 秒窗口预算。
"""

from __future__ import annotations

from typing import Optional

from hangma_bot.kernel.actions import Action, Discard, Pass, Tile, action_key
from hangma_bot.kernel.observation import PlayerObservation

from .interface import RuleCandidate

_RESPONSE_PHASES = ("response_peng", "response_chi")


def emergency_action(observation: PlayerObservation) -> Optional[RuleCandidate]:
    """以最小依赖路径返回过、抓打牌或最右弃牌；无动作权时返回 None。

    判定只读取观察的阶段、座位关系、手牌顺序和抓打圈标志；
    不读取牌河、副露、公共历史，也不调用任何分析函数。
    """

    action = _decide(observation)
    if action is None:
        return None
    if isinstance(action, Pass):
        evidence = ("emergency:response-pass",)
    elif isinstance(action, Discard):
        if observation.rule_state.catch_play:
            evidence = ("emergency:catch-play-drawn",)
        else:
            evidence = ("emergency:rightmost-discard",)
    else:  # pragma: no cover - 当前决策不可能产生其他动作类型
        return None
    return RuleCandidate(
        action=action,
        action_key=action_key(action),
        evidence=evidence,
    )


def _decide(observation: PlayerObservation) -> Optional[Action]:
    """按阶段机械决策；返回 None 表示本窗口无动作权或信息不完整。"""

    phase = observation.phase
    seat = observation.seat
    if phase in _RESPONSE_PHASES:
        # 响应窗口：有响应权才过；无响应权不得伪造动作。
        if seat in tuple(observation.responding_seats):
            return Pass()
        return None
    if phase == "draw":
        # 出牌窗口：必须轮到本人。
        if observation.turn_seat != seat:
            return None
        if observation.rule_state.catch_play:
            # 抓打圈：只能打刚摸牌；缺失时保守退回最右一张。
            if observation.drawn_tile is not None:
                return Discard(observation.drawn_tile)
            if observation.my_hand:
                return Discard(_rightmost(observation.my_hand))
            return None
        # 普通出牌：打官方顺序最右一张；手牌为空但存在刚摸牌时打摸牌。
        if observation.my_hand:
            return Discard(_rightmost(observation.my_hand))
        if observation.drawn_tile is not None:
            return Discard(observation.drawn_tile)
        return None
    # deal / settled / finished 等阶段无动作权。
    return None


def _rightmost(hand: tuple[Tile, ...]) -> Tile:
    """官方返回顺序的最右一张（最后元素）；与官方超时兜底行为一致。"""

    return hand[-1]
