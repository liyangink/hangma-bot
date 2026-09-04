"""玩家依法可见的牌局信息与已观察赛事上下文。

本文件是第一阶段共享接口基线：不得单方面改名、删除字段或改变语义，
尤其不得扩大信息权限——他家手牌、未来牌墙和赛后结果不得进入
``PlayerObservation``。构造函数只做廉价结构校验（座位范围 0—3、
四家向量长度、动作参数和牌值域），昂贵业务校验属于规则模块。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

# 座位、牌值与序列校验是 kernel 包内共享的私有助手（见 actions.py）。
from .actions import (
    SEAT_COUNT,
    Tile,
    _require_non_empty_str,
    _require_non_negative_int,
    _require_tuple,
    _validate_seat,
    _validate_tile,
)

# 四家整型向量；固定按座位 0—3 排列，长度恒为 4。
SeatIntVector = Tuple[int, int, int, int]
# 当前桌内积分向量；固定按座位 0—3 排列，长度恒为 4。
ScoreVector = SeatIntVector


@dataclass(frozen=True)
class PublicMeld:
    """已经公开的副露；牌序使用内部规范顺序。"""

    seat: int  # 副露所有者座位，0—3
    kind: str  # 规范副露种类字符串（如 chi/peng/gang）；由适配器按官方字段映射
    tiles: Tuple[Tile, ...]  # 组成副露的牌，含被吃/碰/杠的那张牌
    from_seat: Optional[int]  # 供牌者座位；暗杠等无供牌来源时为空

    def __post_init__(self) -> None:
        _validate_seat(self.seat, "PublicMeld.seat")
        _require_non_empty_str(self.kind, "PublicMeld.kind")
        _require_tuple(self.tiles, "PublicMeld.tiles")
        for tile in self.tiles:
            _validate_tile(tile, "PublicMeld.tiles")
        if self.from_seat is not None:
            _validate_seat(self.from_seat, "PublicMeld.from_seat")


@dataclass(frozen=True)
class PublicEvent:
    """线上决策时已经公开的一条规范事件。"""

    seq: int  # 官方事件序号，非负且随事件流单调递增
    kind: str  # 官方事件 type 原样透传；未知事件必须允许并记录，不能因此崩溃
    seat: Optional[int]  # 动作发起座位，0—3；与座位无关的事件为空
    tiles: Tuple[Tile, ...] = ()  # 事件涉及的牌
    occurred_at_unix_sec: Optional[int] = None  # 官方 ``ts``；墙上时钟 Unix 秒

    def __post_init__(self) -> None:
        _require_non_negative_int(self.seq, "PublicEvent.seq")
        _require_non_empty_str(self.kind, "PublicEvent.kind")
        if self.seat is not None:
            _validate_seat(self.seat, "PublicEvent.seat")
        _require_tuple(self.tiles, "PublicEvent.tiles")
        for tile in self.tiles:
            _validate_tile(tile, "PublicEvent.tiles")
        if self.occurred_at_unix_sec is not None and (
            isinstance(self.occurred_at_unix_sec, bool)
            or not isinstance(self.occurred_at_unix_sec, int)
        ):
            raise ValueError("PublicEvent.occurred_at_unix_sec 必须是整数 Unix 秒或空")


@dataclass(frozen=True)
class PublicDiscard:
    """最近一张公开弃牌及其触发序号。"""

    seat: int  # 弃牌者座位，0—3
    tile: Tile
    seq: int  # 触发该弃牌的官方事件序号，非负

    def __post_init__(self) -> None:
        _validate_seat(self.seat, "PublicDiscard.seat")
        _validate_tile(self.tile, "PublicDiscard.tile")
        _require_non_negative_int(self.seq, "PublicDiscard.seq")


@dataclass(frozen=True)
class RulePublicState:
    """官方 ``god`` 中与本人动作相关的可见规则状态。"""

    wealth_god: Tile  # 财神牌；当前规则下为“白”，仍以字段传递避免硬编码
    baotou: bool  # 本人是否处于爆头状态
    chain_count: int  # 本人飘/杠动作链次数；断链后清零，非负
    catch_play: bool  # 本人是否处于抓打圈

    def __post_init__(self) -> None:
        _validate_tile(self.wealth_god, "RulePublicState.wealth_god")
        if not isinstance(self.baotou, bool):
            raise ValueError("RulePublicState.baotou 必须是布尔值")
        if not isinstance(self.catch_play, bool):
            raise ValueError("RulePublicState.catch_play 必须是布尔值")
        _require_non_negative_int(self.chain_count, "RulePublicState.chain_count")


@dataclass(frozen=True)
class PlayerObservation:
    """某座位在一个动作窗口内依法能够读取的全部牌局信息。

    信息权限：只含本人手牌与已公开事实；他家手牌、未来牌墙顺序和
    赛后结果在类型上没有承载字段。
    """

    game_id: str
    seat: int
    round_no: int
    snapshot_seq: int
    phase: str  # 官方阶段字符串原样透传（deal/draw/response_peng/response_chi/settled/finished；允许官方后续扩充未知值）；动作窗口阶段另由 ``WindowKey`` 强类型表达
    dealer_seat: int
    turn_seat: int
    responding_seats: Tuple[int, ...]
    my_hand: Tuple[Tile, ...]  # 保留官方返回顺序；紧急“最右一张”依赖该顺序
    drawn_tile: Optional[Tile]  # 非摸牌窗口可为空
    discards: Tuple[Tuple[Tile, ...], ...]  # 外层固定按座位 0—3
    melds: Tuple[Tuple[PublicMeld, ...], ...]  # 外层固定按座位 0—3
    hand_counts: SeatIntVector  # 四家剩余手牌张数，固定按座位 0—3
    last_discard: Optional[PublicDiscard]
    remaining_tile_count: Optional[int]  # 官方 ``wall_remaining``；官方未提供或无法可靠推出时为空
    scores: ScoreVector  # 当前桌内积分，固定按座位 0—3
    rule_state: RulePublicState
    public_history: Tuple[PublicEvent, ...]

    def __post_init__(self) -> None:
        # 以下均为 O(字段数+牌数) 的廉价结构校验，可在适配器热路径执行；
        # 是否构成合法动作等业务判断属于 hangma 规则模块。
        _require_non_empty_str(self.game_id, "PlayerObservation.game_id")
        _require_non_empty_str(self.phase, "PlayerObservation.phase")
        _require_non_negative_int(self.snapshot_seq, "PlayerObservation.snapshot_seq")
        _require_non_negative_int(self.round_no, "PlayerObservation.round_no")
        _validate_seat(self.seat, "PlayerObservation.seat")
        _validate_seat(self.dealer_seat, "PlayerObservation.dealer_seat")
        _validate_seat(self.turn_seat, "PlayerObservation.turn_seat")
        _require_tuple(self.responding_seats, "PlayerObservation.responding_seats")
        if len(set(self.responding_seats)) != len(self.responding_seats):
            # 一个座位在同一响应窗口只有一次响应权；重复座位无合法语义。
            raise ValueError("responding_seats 不得包含重复座位")
        for seat in self.responding_seats:
            _validate_seat(seat, "PlayerObservation.responding_seats")
        _require_tuple(self.my_hand, "PlayerObservation.my_hand")
        for tile in self.my_hand:
            _validate_tile(tile, "PlayerObservation.my_hand")
        if self.drawn_tile is not None:
            _validate_tile(self.drawn_tile, "PlayerObservation.drawn_tile")
        _require_tuple(self.discards, "PlayerObservation.discards")
        if len(self.discards) != SEAT_COUNT:
            raise ValueError("discards 必须是按座位 0—3 排列的四家牌河")
        for river in self.discards:
            _require_tuple(river, "PlayerObservation.discards 行")
            for tile in river:
                _validate_tile(tile, "PlayerObservation.discards")
        _require_tuple(self.melds, "PlayerObservation.melds")
        if len(self.melds) != SEAT_COUNT:
            raise ValueError("melds 必须是按座位 0—3 排列的四家副露")
        for seat_melds in self.melds:
            _require_tuple(seat_melds, "PlayerObservation.melds 行")
            for meld in seat_melds:
                if not isinstance(meld, PublicMeld):
                    raise ValueError(
                        "PlayerObservation.melds 的元素必须是 PublicMeld，得到 {0!r}".format(meld)
                    )
        _require_tuple(self.hand_counts, "PlayerObservation.hand_counts")
        if len(self.hand_counts) != SEAT_COUNT:
            raise ValueError("hand_counts 必须是按座位 0—3 的四元组")
        for count in self.hand_counts:
            _require_non_negative_int(count, "PlayerObservation.hand_counts 元素")
        _require_tuple(self.scores, "PlayerObservation.scores")
        if len(self.scores) != SEAT_COUNT:
            raise ValueError("scores 必须是按座位 0—3 的四元组")
        for score in self.scores:
            # 积分允许为负（输分）；但元素必须是 int 且不允许 bool 混入，
            # 否则观察对象能通过构造却无法经序列化往返（能写出不能读回）。
            if isinstance(score, bool) or not isinstance(score, int):
                raise ValueError(
                    "PlayerObservation.scores 元素必须是整数（允许负分），得到 {0!r}".format(score)
                )
        if self.last_discard is not None and not isinstance(self.last_discard, PublicDiscard):
            raise ValueError("PlayerObservation.last_discard 必须是 PublicDiscard 或空")
        if self.remaining_tile_count is not None:
            _require_non_negative_int(
                self.remaining_tile_count, "PlayerObservation.remaining_tile_count"
            )
        if not isinstance(self.rule_state, RulePublicState):
            raise ValueError("PlayerObservation.rule_state 必须是 RulePublicState 值对象")
        _require_tuple(self.public_history, "PlayerObservation.public_history")
        for event in self.public_history:
            if not isinstance(event, PublicEvent):
                raise ValueError(
                    "PlayerObservation.public_history 的元素必须是 PublicEvent，得到 {0!r}".format(event)
                )


@dataclass(frozen=True)
class RankingEntry:
    """平台观察到的一条权威排名；三个排序键不得相加。"""

    participant_id: str  # 已脱敏的参赛身份，不是 Token
    total_score: int  # 总分
    place_points: int  # 排名分；允许为负，不做符号校验
    god_count: int  # 财神次数，非负
    games_played: int  # 已完成单局数（每阶段清零），非负
    rank: int  # 名次，从 1 开始

    def __post_init__(self) -> None:
        _require_non_empty_str(self.participant_id, "RankingEntry.participant_id")
        for field_name in ("total_score", "place_points"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError("RankingEntry.{0} 必须是整数".format(field_name))
        _require_non_negative_int(self.god_count, "RankingEntry.god_count")
        _require_non_negative_int(self.games_played, "RankingEntry.games_played")
        if isinstance(self.rank, bool) or not isinstance(self.rank, int) or self.rank < 1:
            raise ValueError("RankingEntry.rank 必须是从 1 开始的名次，得到 {0!r}".format(self.rank))


@dataclass(frozen=True)
class CompetitionContext:
    """策略可读取的已观察赛事事实，不含客户端推测的未来赛制。"""

    tournament_id: str
    stage_no: Optional[int]
    stage_role: Optional[str]
    stage_total: Optional[int]
    participant_rank: Optional[int]
    ranking: Tuple[RankingEntry, ...]
    observed_at_unix_ms: int  # 墙上时钟，仅用于判断排名数据陈旧程度

    def __post_init__(self) -> None:
        _require_non_empty_str(self.tournament_id, "CompetitionContext.tournament_id")
        for field_name in ("stage_no", "stage_total"):
            value = getattr(self, field_name)
            if value is not None:
                # 阶段号与阶段总数不存在负值语义；None 表示官方未提供。
                _require_non_negative_int(
                    value, "CompetitionContext.{0}".format(field_name)
                )
        if self.participant_rank is not None:
            # 我方名次来自权威榜单，语义与 RankingEntry.rank 一致（从 1 起）。
            rank = self.participant_rank
            if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1:
                raise ValueError(
                    "CompetitionContext.participant_rank 必须是从 1 开始的名次或空，得到 {0!r}".format(rank)
                )
        if self.stage_role is not None and not isinstance(self.stage_role, str):
            raise ValueError("CompetitionContext.stage_role 必须是字符串或空")
        _require_non_negative_int(
            self.observed_at_unix_ms, "CompetitionContext.observed_at_unix_ms"
        )
        _require_tuple(self.ranking, "CompetitionContext.ranking")
        for entry in self.ranking:
            if not isinstance(entry, RankingEntry):
                raise ValueError(
                    "CompetitionContext.ranking 的元素必须是 RankingEntry，得到 {0!r}".format(entry)
                )
