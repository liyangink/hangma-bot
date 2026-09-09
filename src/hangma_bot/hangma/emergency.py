"""独立紧急路径：不依赖任何复杂分析分支的最终兜底动作。

依据（RULES_EVIDENCE §9、模块 AGENTS.md）：
- 本模块禁止调用向听、有效牌、分解或结算；
- 响应窗口 → 过；抓打圈内非圈主或归属未知 → 打刚摸牌；圈主及普通出牌 → 从右优先非财神；
- 普通出牌保财是本地保底偏好（2026-09-08），不改变官方合法动作；
- 无动作权或观察不完整时返回 None，不伪造动作。

性能约束：本文件不得分配大对象、不得做牌型搜索；目标是 P99 远低于 1 秒窗口预算。
"""

from __future__ import annotations

from typing import Optional

from hangma_bot.kernel.actions import Action, Discard, Pass, Tile, action_key
from hangma_bot.kernel.observation import PlayerObservation

from .interface import RuleCandidate
from .catch_play import analyze_catch_play

_RESPONSE_PHASES = ("response_peng", "response_chi")


def emergency_action(observation: PlayerObservation) -> Optional[RuleCandidate]:
    """以最小依赖路径返回过、抓打牌或从右优先非财神的弃牌。

    无动作权时返回 None。活跃圈用可见事件后缀或权威牌河的弃白对账确认归属；
    副露数量仅用于识别单列摸牌，不运行牌型、向听或结算分析。
    """

    circle = analyze_catch_play(observation)
    forced_draw = circle.restricts(observation.seat)
    action = _decide(observation, forced_draw)
    if action is None:
        return None
    if isinstance(action, Pass):
        evidence = ("emergency:response-pass",)
    elif isinstance(action, Discard):
        if forced_draw:
            evidence = ("emergency:catch-play-drawn",)
        elif action.tile != observation.rule_state.wealth_god:
            evidence = ("emergency:rightmost-nonwealth-discard",)
        else:
            evidence = ("emergency:only-wealth-discard",)
    else:  # pragma: no cover - 当前决策不可能产生其他动作类型
        return None
    if circle.active and circle.owner_seat is not None:
        evidence += ("抓打圈:圈主={0},开圈seq={1},依据={2}".format(circle.owner_seat, circle.started_seq, circle.source),)
    return RuleCandidate(
        action=action,
        action_key=action_key(action),
        evidence=evidence,
    )


def _decide(observation: PlayerObservation, forced_draw: bool) -> Optional[Action]:
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
        if forced_draw:
            # 非圈主/圈主未知时只能打刚摸牌；缺失时不能猜最右牌就是摸牌。
            if observation.drawn_tile is not None:
                return Discard(observation.drawn_tile)
            return None
        tile = _ordinary_discard(observation)
        return Discard(tile) if tile is not None else None
    # deal / settled / finished 等阶段无动作权。
    return None


def _ordinary_discard(observation: PlayerObservation) -> Optional[Tile]:
    """线性扫描优先保财；全是财神时仍保留可提交的弃牌，不计算飘。"""

    hand = observation.my_hand
    drawn = observation.drawn_tile
    wealth = observation.rule_state.wealth_god
    # 模拟器的 13−3×副露数 + 单列摸牌，与官方已含摸牌的形态等价。
    # 只在前一种形态把摸牌看作右端；后一种保留官方实际牌序。
    if (
        drawn is not None
        and drawn != wealth
        and len(hand) == 13 - 3 * len(observation.melds[observation.seat])
    ):
        return drawn
    for tile in reversed(hand):
        if tile != wealth:
            return tile
    if drawn is not None:
        return drawn
    return hand[-1] if hand else None
