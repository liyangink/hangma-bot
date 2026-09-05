"""完整世界 → 指定座位 PlayerObservation 的纯投影（信息权限边界）。

只把依法可见事实放进观察：本人暗牌与刚摸牌、四家牌河、四家副露、
四家手牌张数、最近弃牌、牌墙剩余张数、四家积分、本人规则状态与公开事件
历史（他人摸牌事件不出现——官方事件流只含自己的摸牌）。替换他家手牌或
未来牌墙不会改变本座位观察（tests/simulation/test_info_permission.py）。

手牌形态固定使用契约形态：my_hand 不含独立 drawn_tile，保持获得顺序。
"""

from __future__ import annotations

from typing import Optional, Tuple

from hangma_bot.hangma.progression import MeldRecord
from hangma_bot.kernel.actions import Tile, WindowKey, WindowPhase
from hangma_bot.kernel.observation import (
    PlayerObservation,
    PublicDiscard,
    PublicEvent,
    PublicMeld,
    RulePublicState,
)

from .state import WorldState

_WEALTH_GOD = Tile("白")

_RESPONSE_WINDOWS = ("response_peng", "response_chi")


def _public_meld(meld: MeldRecord, seat: int) -> PublicMeld:
    """推进副露 → 观察副露；kind 直接透传（chi/peng/gang）。"""
    return PublicMeld(seat=seat, kind=meld.kind, tiles=meld.tiles, from_seat=meld.from_seat)


def public_history_for(events: Tuple[object, ...], seat: int) -> Tuple[PublicEvent, ...]:
    """事件 → 该座位公开历史：他人 tile_drawn 不入史（官方私有信息）。"""
    out = []
    for event in events:
        kind = event.kind
        if kind == "tile_drawn" and event.seat != seat:
            continue  # 他人摸牌是私有信息，绝不进入观察
        event_seat = event.seat
        if event_seat is not None and not 0 <= event_seat <= 3:
            event_seat = None  # round_ended 流局 seat=-1 等官方形态 → 空
        out.append(PublicEvent(
            seq=event.seq,
            kind=kind,
            seat=event_seat,
            tiles=(event.tile,) if event.tile is not None else (),
        ))
    return tuple(out)


def observation(world: WorldState, seat: int) -> PlayerObservation:
    """投影指定座位在当前决策边界的全部依法可见事实。

    抓打圈（打出财神那一圈，官方 v15 1.1）的 catch_play 按窗口阶段投影：
    圈主在本人摸牌窗口 true（出牌只能打刚摸到的牌）；圈内响应窗口的
    响应者 true（不能吃/碰/明杠，仅过）；圈内其他座位的摸牌窗口 false
    （可正常出牌）。v14 夹具实测：弃白后不开响应窗口，圈内普通弃牌仍开
    窗口且全员过（timeout/pass 事件）。"""
    state = world.progression
    s = state.seats[seat]
    phase = state.window
    last_discard: Optional[PublicDiscard] = None
    if phase in _RESPONSE_WINDOWS:
        last_discard = state.last_discard
    hand_counts = tuple(
        len(x.hand) + (1 if x.drawn is not None else 0) for x in state.seats
    )
    circle_active = any(x.catch_play for x in state.seats)
    in_response = phase in _RESPONSE_WINDOWS and seat in state.responding
    catch_play = s.catch_play or (circle_active and in_response)
    return PlayerObservation(
        game_id=world.match_id,
        seat=seat,
        round_no=state.round_no,
        snapshot_seq=state.seq,
        phase=phase,
        dealer_seat=state.dealer_seat,
        turn_seat=state.turn_seat if state.turn_seat is not None else 0,
        responding_seats=state.responding,
        my_hand=s.hand,
        drawn_tile=s.drawn,
        discards=tuple(tuple(x.discards) for x in state.seats),
        melds=tuple(
            tuple(_public_meld(meld, seat_no) for meld in x.melds)
            for seat_no, x in enumerate(state.seats)
        ),
        hand_counts=hand_counts,
        last_discard=last_discard,
        remaining_tile_count=state.wall_total,
        scores=state.scores,
        rule_state=RulePublicState(
            wealth_god=_WEALTH_GOD,
            baotou=s.baotou,
            chain_count=s.chain_count,
            catch_play=catch_play,
        ),
        public_history=public_history_for(world.events, seat),
    )


def window_key(world: WorldState, seat: int) -> WindowKey:
    """当前决策边界的动作窗口键；碰窗口与随后吃窗口必为不同键。"""
    state = world.progression
    phase = WindowPhase(state.window)
    return WindowKey(
        game_id=world.match_id,
        round_no=state.round_no,
        trigger_seq=state.trigger_seq,
        phase=phase,
        seat=seat,
    )


def timeout_for(world: WorldState, phase: str) -> float:
    """窗口阶段 → 官方配置的窗口持续秒数（评估器建立本地预算的基准）。"""
    if phase == "response_peng":
        return world.timing.peng_timeout_sec
    if phase == "response_chi":
        return world.timing.chi_timeout_sec
    return world.timing.discard_timeout_sec
