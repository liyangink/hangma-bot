"""不可变 WorldState 与单局记录（simulation 所有；对外不透明）。

WorldState 是完整世界状态（四家手牌、牌墙与桌赛进度），只能由
SimulationEngine 构造；评估线与策略不得读其字段（契约 §6）。全部字段
不可变：advance 返回新对象，一个起点可被多个候选分叉而不互相污染。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from hangma_bot.hangma.progression import EventRecord, ProgressionState
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.config import TimingConfig
from hangma_bot.kernel.observation import ScoreVector


@dataclass(frozen=True)
class RoundRecord:
    """一个已完成单局的完整记录；导出与历史核对的原始事实。"""

    round_no: int
    dealer_seat: int
    scores_before: ScoreVector
    scores_after: ScoreVector
    score_delta: ScoreVector
    winner_seat: Optional[int]
    is_draw: bool
    fan: int
    details: Tuple[str, ...]
    initial_hands: Tuple[Tuple[Tile, ...], ...]  # 14/13/13/13（庄家直抽置尾）
    dealer_drawn_tile: Tile
    wall: Tuple[Tile, ...]  # 该局起点剩余牌墙（含保留区）
    wall_back: int  # 可摸区/保留区分界下标
    events: Tuple[EventRecord, ...]  # 全事件（含 round_ended；末局含 game_ended）


@dataclass(frozen=True)
class WorldState:
    """完整世界状态：四家手牌与牌墙、单局推进、桌赛进度、产物身份。"""

    match_id: str
    scenario_id: str
    seed: int
    initial_dealer: int
    timing: TimingConfig
    ruleset_version: str
    base_score: int
    you_cai_bi_kao: bool
    rules_hash: Optional[str]
    parent_hand_id: Optional[str]  # 反事实导出/from_replay 的父单局标识
    rounds_per_game: int
    round_no: int
    dealer_seat: int
    round_scores_before: ScoreVector  # 当前局起点积分（导出 scores_before）
    round_start_seq: int  # 当前局起点事件水位（上一局末 round_ended seq；首局 0）
    revision: int
    completed_hands: int
    progression: ProgressionState
    wall: Tuple[Tile, ...]  # 当前局剩余牌墙（含保留区，物理顺序）
    wall_front: int  # 普通摸牌端游标
    wall_back: int  # 补牌端游标；wall[wall_back:] 为保留区
    round_initial_hands: Tuple[Tuple[Tile, ...], ...]  # 当前局 4×13 起手
    round_dealer_drawn: Tile  # 当前局庄家直抽
    round_start_wall: Tuple[Tile, ...]  # 当前局起点牌墙（导出 world_payload）
    round_start_wall_back: int
    events: Tuple[EventRecord, ...]  # 当前局已发生事件
    round_records: Tuple[RoundRecord, ...]  # 已完成局
    blocked_reason: Optional[str]

    @property
    def scores(self) -> ScoreVector:
        """当前桌内积分（座位 0—3）；终局帧的 final_scores 即此值。"""
        return self.progression.scores

    @property
    def is_blocked(self) -> bool:
        return self.blocked_reason is not None

    @property
    def is_match_end(self) -> bool:
        return self.progression.window == "match_end"
