"""hangma 模块内部共享的不可变类型、34 种牌编码与窗口上下文。

本文件是子模块（hand_analysis / action_families / special_rules / settlement）之间的
内部数据契约，由规则主 Agent 维护；不属于 `interface.py` 的受控公开契约，
调用方（policy / application）不得 import 本文件。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from hangma_bot.kernel.actions import (
    CANONICAL_TILE_INDEX,
    CANONICAL_TILE_ORDER,
    Tile,
)
from hangma_bot.kernel.observation import PublicDiscard

# ---------------------------------------------------------------------------
# 牌编码：34 种牌的规范顺序。权威定义在 kernel（CANONICAL_TILE_ORDER，
# 2026-09-04 集成阶段 kernel 裁决）；本模块只保留内部惯用别名，
# 不维护第二份数据。Counts34 的下标即此顺序；白板（财神）固定为最后一位。
# ---------------------------------------------------------------------------

TILE_ORDER: Tuple[str, ...] = CANONICAL_TILE_ORDER
"""34 种牌值的规范顺序（kernel 权威常量的别名）；计数向量与分解枚举都按此顺序。"""

TILE_INDEX: Dict[str, int] = CANONICAL_TILE_INDEX
"""牌值 → 计数向量下标（kernel 权威映射的别名）。"""

WEALTH_CODE: str = "白"
"""财神（万能牌）的牌值编码；白板共 4 张。"""

Counts34 = Tuple[int, ...]
"""长度 34 的牌计数向量；各下标含义见 TILE_ORDER，元素非负。"""


def is_wealth(tile: Tile) -> bool:
    """判断一张牌是否为财神（白板）。"""

    return tile.code == WEALTH_CODE


def is_wealth_code(code: str) -> bool:
    """按牌值编码判断财神。"""

    return code == WEALTH_CODE


def counts_from_tiles(tiles: Tuple[Tile, ...]) -> Counts34:
    """把牌元组转成 34 维计数向量；非法牌值抛 KeyError（调用方负责边界）。"""

    counts = [0] * 34
    for tile in tiles:
        counts[TILE_INDEX[tile.code]] += 1
    return tuple(counts)


def codes_from_counts(counts: Counts34) -> Tuple[str, ...]:
    """把计数向量还原为按规范顺序排列的牌值元组（每个 code 重复其张数）。"""

    codes: list[str] = []
    for idx, n in enumerate(counts):
        codes.extend([TILE_ORDER[idx]] * n)
    return tuple(codes)


# ---------------------------------------------------------------------------
# 手牌分析结果：hand_analysis 产出，engine / special_rules / settlement 消费。
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UsefulTile:
    """一张能推进听牌的牌；`shanten_after` 为摸入后的最优向听数。"""

    code: str
    shanten_after: int


@dataclass(frozen=True)
class HandSummary:
    """一次确定性手牌分析的完整结果（不含动作窗口合法性）。

    `hand_tiles` 语义：暗牌全集（含刚摸牌，若有）；副露不参与，只以
    `meld_set_count` 折算固定面子数。向听数约定：未胡时 ≥ 0（0 = 听牌），
    已胡时为 -1，同时 `is_win=True`。
    """

    is_win: bool
    standard_shanten: int  # 标准型向听；副露 > 0 时仍按剩余面子需求计算
    chiitoi_shanten: Optional[int]  # 七对向听；任一副露存在时为 None
    shanten: int  # 两型最优向听（chiitoi 为 None 时取标准型）
    useful_tiles: Tuple[UsefulTile, ...]  # 按规范顺序去重；含白板（万能恒有效）
    whites_held: int  # 被分析暗牌中的白板张数（0-4）
    evidence: Tuple[str, ...]  # 确定性分解证据（审计用，人可读）


@dataclass(frozen=True)
class WinSplit:
    """胡牌分解的规则元数据（结算与爆头判定输入）。

    `any_tile_tenpai` 按摸牌前 13 张暗牌判定（指南 1.2"听任意牌"）；
    运行时结算优先用 `observation.rule_state.baotou` 权威状态，
    本字段用于金例对拍、审计与 YouCaiBiKao 推断。
    """

    branch: str  # "平胡" 或 "七对"（与官方 detail 命名一致）
    luxury_pairs: int  # 豪华七对组数（四张同牌按两对计，4 张真白板算 1 组）；平胡分支恒 0
    whites_held: int  # 胡牌暗牌全集（含摸牌）中的白板张数
    any_tile_tenpai: bool  # 摸牌前 13 张暗牌 + 任意一张牌都胡（爆头静态判定）
    evidence: Tuple[str, ...]


# ---------------------------------------------------------------------------
# 动作窗口上下文：engine 从 PlayerObservation 提取的纯机械事实，
# 供 action_families 生成候选；不含结算专属状态（chain/baotou 在 observation.rule_state）。
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WindowContext:
    """一个动作窗口内生成候选所需的机械事实（信息权限与 PlayerObservation 相同）。"""

    seat: int
    phase: str  # 规范官方阶段：deal / draw / response_peng / response_chi / settled / finished
    turn_seat: int
    responding_seats: Tuple[int, ...]
    hand_tiles: Tuple[Tile, ...]  # 本人暗牌，保留官方返回顺序（紧急路径依赖最右一张）
    drawn_tile: Optional[Tile]  # 本人刚摸到的牌；非摸牌窗口为 None
    my_chi_count: int  # 本人已有吃副露数（吃上限 2 次）
    my_peng_codes: Tuple[str, ...]  # 本人已碰牌值（补杠判定；不含杠化副露）
    last_discard: Optional[PublicDiscard]  # 触发响应窗口的最近公开弃牌
    catch_play: bool  # 本座是否受抓打约束：活跃圈的非圈主或归属未知，不是原始全局标记
    remaining_tile_count: Optional[int]  # 官方牌墙剩余；未知为 None（最后 20 张内禁杠）

    def full_hand(self) -> Tuple[Tile, ...]:
        """暗牌全集 = 手牌 + 刚摸牌（若在本窗口）；保留官方顺序，摸牌置尾。"""

        if self.drawn_tile is None:
            return self.hand_tiles
        return self.hand_tiles + (self.drawn_tile,)
