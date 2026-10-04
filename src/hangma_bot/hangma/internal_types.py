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


# 原函数体产生内建34项整数元组；仅供同模块群的缓存准入证明。
# 紧邻定义保存对象和代码，避免先换计数函数、后导入手牌模块被误认可。
# 私有证明不改变原计数的非法牌码/第五张行为，也不新增公共契约。
_COUNTS_FROM_TILES_CANONICAL_FUNCTION = counts_from_tiles
_COUNTS_FROM_TILES_CANONICAL_CODE = counts_from_tiles.__code__


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
class HandWinEvidence:
    """只判定当前暗牌是否成胡的规则事实，不承诺向听或后续进张。

    用于仅需胡资格的条件见证；由同一手牌分解器产出，避免以未计算
    的向听和有效牌字段拼装完整 ``HandSummary``。
    """

    is_win: bool  # 当前完整暗牌能否成胡；不含动作窗口或有财必靠门禁
    evidence: Tuple[str, ...]  # 同一确定性胡牌分解器给出的人读证据


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
    standard_useful_tiles: Optional[Tuple[UsefulTile, ...]] = None  # 普通型独立推进牌；未枚举为空，已枚举空集合为 ()
    seven_pairs_useful_tiles: Optional[Tuple[UsefulTile, ...]] = None  # 七对独立推进牌；有副露或未枚举为空


@dataclass(frozen=True)
class HandProgressSummary:
    """公开后继批量分析使用的轻量手牌数学投影。

    与 ``HandSummary`` 共用 ``hand_analysis`` 的同一核心计算，只省略
    分牌型有效牌对象和人读证据；不得在消费模块重算向听或有效牌。
    """

    is_win: bool
    standard_shanten: int
    chiitoi_shanten: Optional[int]
    shanten: int
    useful_codes: Tuple[str, ...]
    evidence: Tuple[str, ...] = ()  # 兼容动作族胡候选的证据拼接；轻量入口固定为空


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
    """一个动作窗口内生成候选所需的机械事实。

    ``conditional_discard`` 只给离线条件分支使用：它携带响应触发者和
    牌值，不含官方事件序号；正式观察始终使用 ``last_discard``。
    两种来源不能同时填写，避免给假设事件制造官方身份。
    """

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
    conditional_discard: Optional[Tuple[int, Tile]] = None  # 离线给定触发弃牌；无官方 seq

    def __post_init__(self) -> None:
        if self.last_discard is not None and self.conditional_discard is not None:
            raise ValueError("官方触发弃牌与条件触发弃牌不能同时填写")
        if self.conditional_discard is not None:
            seat, tile = self.conditional_discard
            if (self.phase not in ("response_peng", "response_chi")
                    or seat not in range(4) or seat != self.turn_seat
                    or not isinstance(tile, Tile)):
                raise ValueError("条件触发弃牌必须匹配响应窗口、弃牌座位与牌值")

    def response_trigger(self) -> Optional[Tuple[int, Tile]]:
        """读取响应触发的座位与牌值，不把条件假设转成官方弃牌。"""

        if self.last_discard is not None:
            return self.last_discard.seat, self.last_discard.tile
        return self.conditional_discard

    def full_hand(self) -> Tuple[Tile, ...]:
        """暗牌全集 = 手牌 + 刚摸牌（若在本窗口）；保留官方顺序，摸牌置尾。"""

        if self.drawn_tile is None:
            return self.hand_tiles
        return self.hand_tiles + (self.drawn_tile,)
