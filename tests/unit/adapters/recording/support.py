"""3.6d 记录层测试夹具：只通过公开契约类型构造观察与事件。

夹具不复制任何链规则：链状态由测试显式声明（``chain_count``/``chain_piao``），
牌面事实（牌河、暗牌、副露、事件流）按真实记录形态构造，
推导与核对逻辑一律由被测模块与 ``hangma`` 单一规则来源提供。
"""

from __future__ import annotations

from typing import Optional, Sequence, Tuple

from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.observation import (
    PlayerObservation,
    PublicEvent,
    PublicMeld,
    RulePublicState,
)

WEALTH_CODE = "白"


def make_observation(**overrides) -> PlayerObservation:
    """构造默认玩家观察；未给字段使用安全的最小默认值。"""

    defaults = dict(
        game_id="g1",
        seat=0,
        round_no=1,
        snapshot_seq=0,  # 消费水位的下界；测试按需给 consumed_seq
        phase="draw",
        dealer_seat=0,
        turn_seat=0,
        responding_seats=(),
        my_hand=(),
        drawn_tile=None,
        discards=((), (), (), ()),
        melds=((), (), (), ()),
        hand_counts=(13, 13, 13, 13),
        last_discard=None,
        remaining_tile_count=60,
        scores=(0, 0, 0, 0),
        rule_state=RulePublicState(
            wealth_god=Tile(WEALTH_CODE), baotou=False, chain_count=0, catch_play=False
        ),
        public_history=(),
    )
    defaults.update(overrides)
    return PlayerObservation(**defaults)


def discard_event(seq: int, seat: int, code: str) -> PublicEvent:
    """一条公开弃牌事件（牌河与历史同源）。"""

    return PublicEvent(seq=seq, kind="tile_discarded", seat=seat, tiles=(Tile(code),))


def gang_event(seq: int, seat: int, code: str) -> PublicEvent:
    """一条公开杠事件；``detail_kind`` 取官方公开的杠种类。"""

    return PublicEvent(
        seq=seq, kind="gang", seat=seat, tiles=(Tile(code),), detail_kind="an"
    )


def draw_event(seq: int, seat: int, code: str) -> PublicEvent:
    """一条公开摸牌事件。"""

    return PublicEvent(seq=seq, kind="tile_drawn", seat=seat, tiles=(Tile(code),))


def meld(seat: int, kind: str, codes: Sequence[str]) -> PublicMeld:
    """一副公开副露（座位置于对象内，与官方投影一致）。"""

    return PublicMeld(
        seat=seat, kind=kind, tiles=tuple(Tile(code) for code in codes), from_seat=None
    )


def history(*events: PublicEvent) -> Tuple[PublicEvent, ...]:
    """按给定顺序组装公开历史（调用方负责序号连续）。"""

    return tuple(events)


def observation_with_river(
    seat: int, river: Sequence[str], **overrides
) -> PlayerObservation:
    """把本人牌河替换为给定牌码序列，其余座位保持为空。"""

    rows = [[], [], [], []]
    rows[seat] = [Tile(code) for code in river]
    return make_observation(seat=seat, discards=tuple(tuple(row) for row in rows), **overrides)
