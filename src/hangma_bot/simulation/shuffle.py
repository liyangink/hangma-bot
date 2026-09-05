"""确定性发牌与每局独立牌墙（simulation 所有，规则边界在 hangma）。

算法版本 deal-v1（入产物 deal_algorithm 字段）：

- 每局牌墙由 (scenario_id, seed, round_no) 独立派生：
  ["simulation-v1:deal-v1", scenario_id, seed, round_no] 按契约 §4.1 编码
  （ensure_ascii=False、separators=(comma,colon)、allow_nan=False）取
  SHA-256，前 8 字节作 random.Random 种子，shuffle 136 张牌；
- 发牌顺序：庄家起每圈每家 4 张 × 3 圈，再每家 1 张，最后庄家 1 张直抽
  （官方 v10：庄家第 14 张为发牌直抽、无摸牌事件）；
- 策略调用次数与吃碰次数不消耗后续单局发牌随机源（每局独立派生）；
- random.Random 的梅森旋转算法跨进程稳定；换 Python 实现版本需登记并
  升级 deal 版本（不能仅说“同一个 seed”却使用不同版本洗牌）。
"""

from __future__ import annotations

import hashlib
import json
import random
from typing import List, Tuple

from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER, Tile

DEAL_ALGORITHM = "simulation-v1:deal-v1"
"""发牌算法版本标识，写入每个 world_payload 与产物 manifest。"""

RESERVE_TILES = 20
"""牌墙保留不摸的张数（最后 10 墩，官方指南 1.1 v15）。"""

_FULL_POOL: Tuple[str, ...] = tuple(
    code for code in CANONICAL_TILE_ORDER for _ in range(4)
)
"""136 张全牌池（每种 4 张，规范牌序展开）。"""


def _round_seed(scenario_id: str, seed: int, round_no: int) -> int:
    """每局独立派生种子；算法版本参与哈希，换版本自动换牌墙。"""
    value = [DEAL_ALGORITHM, scenario_id, seed, round_no]
    payload = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def wall_for_round(scenario_id: str, seed: int, round_no: int) -> Tuple[Tile, ...]:
    """该局完整 136 张牌墙（物理顺序）；随后由 deal_hands 切分。"""
    rng = random.Random(_round_seed(scenario_id, seed, round_no))
    pool = list(_FULL_POOL)
    rng.shuffle(pool)
    return tuple(Tile(code) for code in pool)


def deal_hands(
    shuffled: Tuple[Tile, ...], dealer_seat: int
) -> Tuple[Tuple[Tuple[Tile, ...], ...], Tile, Tuple[Tile, ...]]:
    """切分牌墙：四家 13 张起手、庄家直抽、剩余牌墙（含保留区）。

    返回 (hands13, dealer_drawn_tile, wall)；wall 前段为可摸区
    （83-20=63 张），末 20 张为保留区（RESERVE_TILES），补牌从可摸区尾端取。
    """
    if len(shuffled) != 136:
        raise ValueError("牌墙必须恰为 136 张，得到 {0} 张".format(len(shuffled)))
    hands: List[List[Tile]] = [[] for _ in range(4)]
    cursor = 0
    for _ in range(3):
        for offset in range(4):
            seat = (dealer_seat + offset) % 4
            hands[seat].extend(shuffled[cursor : cursor + 4])
            cursor += 4
    for offset in range(4):
        seat = (dealer_seat + offset) % 4
        hands[seat].append(shuffled[cursor])
        cursor += 1
    dealer_drawn = shuffled[cursor]
    cursor += 1
    wall = shuffled[cursor:]  # 83 张：63 可摸 + 20 保留
    return (
        tuple(tuple(hand) for hand in hands),
        dealer_drawn,
        tuple(wall),
    )
