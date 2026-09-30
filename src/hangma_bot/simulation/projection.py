"""完整世界 → 指定座位 PlayerObservation 的纯投影（信息权限边界）。

只把依法可见事实放进观察：本人暗牌与刚摸牌、四家牌河、四家副露、
四家手牌张数、最近弃牌、牌墙剩余张数、四家积分、本人规则状态与公开事件
历史（他人摸牌保留事件与序号，但不包含牌值）。替换他家手牌或
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
    """保留连续公开事件及弃牌后圈状态；他人摸牌隐藏牌值而不丢序号。"""
    out = []
    for event in events:
        kind = event.kind
        data = dict(event.data)
        hidden_draw = kind == "tile_drawn" and event.seat != seat
        event_seat = event.seat
        if event_seat is not None and not 0 <= event_seat <= 3:
            event_seat = None  # round_ended 流局 seat=-1 等官方形态 → 空
        out.append(PublicEvent(
            seq=event.seq,
            kind=kind,
            seat=event_seat,
            tiles=(tuple(Tile(code) for code in data.get("tiles", ())) if kind == "chi"
                   else (event.tile,) if event.tile is not None and not hidden_draw else ()),
            detail_kind=data.get("kind"),
            catch_play=data.get("catch_play") if kind == "tile_discarded" else None,
            result_draw=data.get("draw") if kind == "round_ended" else None,
            result_fan=data.get("fan") if kind == "round_ended" else None,
            result_details=(tuple(data["detail"])
                            if kind == "round_ended" and "detail" in data else None),
            result_scores=(tuple(data["scores"])
                           if kind == "round_ended" and "scores" in data else None),
            final_scores=(tuple(data["final_scores"])
                          if kind == "game_ended" and "final_scores" in data else None),
            claimed_tile=event.tile if kind == "chi" else None,
        ))
    return tuple(out)


def observation(world: WorldState, seat: int) -> PlayerObservation:
    """投影指定座位在当前决策边界的全部依法可见事实。

    官方 god.catch_play 表示全局圈存在，四家投影相同值，不等同本人须
    摸切。规则从连续公开弃牌恢复最近圈主，另行判断当前座位的动作限制。
    v26已确认圈主响应；公开圈主身份按v26快照语义投影，不泄漏暗牌。
    """
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
            catch_play=circle_active,
            catch_play_owner_seat=next((i for i, s in enumerate(state.seats) if s.catch_play), None),
        ),
        public_history=public_history_for(world.events, seat),
        consumed_seq=state.seq,
        history_complete=True,  # 模拟器从本单局起点持有全部可见事件
        chain_piao=s.chain_piao,  # 本人链内飘数；不读取他家暗牌
        gang_draw=(phase == "draw" and state.turn_seat == seat and len(world.events) >= 2
                   and world.events[-1].kind == "tile_drawn" and world.events[-1].seat == seat
                   and world.events[-2].kind == "gang" and world.events[-2].seat == seat),
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
