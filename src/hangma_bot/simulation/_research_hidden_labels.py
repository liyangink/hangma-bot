"""仅供离线测量的完整世界标签；策略和正式评估器不得导入。

本模块属于 simulation：只有它读取 WorldState 私有字段。调用方只能拿到
34 牌码的计数标签，用于赛后误差审计；不能传给 BotPolicy.choose。
"""

from __future__ import annotations

from collections import Counter

from hangma_bot.hangma.internal_types import TILE_ORDER

from .state import WorldState


def hidden_partition_counts(world: WorldState, *, focal_seat: int) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """返回三家暗手与墙余总牌的逐码张数，牌码顺序为生产 TILE_ORDER。

    墙余包括可摸区和保留区，与 PlayerObservation.remaining_tile_count
    的口径一致。只接受模拟器创建的决策边界世界；不导出未来牌墙顺序。
    """

    if not isinstance(world, WorldState):
        raise ValueError("隐藏标签仅接受模拟完整世界")
    if type(focal_seat) is not int or not 0 <= focal_seat < 4:
        raise ValueError("焦点座位必须是 0..3")
    if world.blocked_reason is not None or world.progression.window not in (
        "draw", "response_peng", "response_chi"
    ):
        raise ValueError("隐藏标签仅在非阻塞决策边界可取")
    hand = Counter(
        tile.code
        for seat, state in enumerate(world.progression.seats)
        if seat != focal_seat
        for tile in (state.hand + (() if state.drawn is None else (state.drawn,)))
    )
    # 补牌从可摸区尾端移走；wall_back..round_start_wall_back 之间是已经摸走
    # 的补牌，虽然仍在不可变底层牌墙元组里，却不属于墙余。保留区始终为
    # 原始末端 20 张，两段相加才与 progression.wall_total 同口径。
    remaining = (world.wall[world.wall_front:world.wall_back]
                 + world.wall[world.round_start_wall_back:])
    wall = Counter(tile.code for tile in remaining)
    if sum(wall.values()) != world.progression.wall_total:
        raise ValueError("墙余总数与模拟进展状态不符")
    if set(hand).difference(TILE_ORDER) or set(wall).difference(TILE_ORDER):
        raise ValueError("完整世界存在未知牌码")
    return (tuple(hand[code] for code in TILE_ORDER),
            tuple(wall[code] for code in TILE_ORDER))
