"""内部动作与动作窗口的稳定值类型。

本文件是第一阶段共享接口基线：实施 Agent 不得单方面改名、删除字段或
改变语义；确需变更时先提出契约变更，并同步
`doc/implementation/interface-contracts.md`、统一术语表与所有消费模块
的契约测试。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import FrozenSet, Tuple, Union

# 固定座位数；四家向量与所有座位下标的合法范围（0—3）由它决定。
SEAT_COUNT = 4

# 规范牌值全集（34 张）：1w-9w 万、1b-9b 筒、1t-9t 条与东南西北中发白。
# 依据官方指南 v8 “牌码”表（doc/official-platform-api-v2.md，检查日期
# 2026-09-03）；“白”是财神。官方扩充牌码时必须先更新本集合与契约测试，
# 再调整适配器映射，禁止未映射的官方字符串直接流入业务模块。
CANONICAL_TILE_CODES: FrozenSet[str] = frozenset(
    ["{0}w".format(number) for number in range(1, 10)]
    + ["{0}b".format(number) for number in range(1, 10)]
    + ["{0}t".format(number) for number in range(1, 10)]
    + ["东", "南", "西", "北", "中", "发", "白"]
)


@dataclass(frozen=True, order=True)
class Tile:
    """规范牌值；`code` 使用项目内部编码，不直接等同于官方 DTO。

    合法取值即 `CANONICAL_TILE_CODES`：万 1w-9w、筒 1b-9b、条 1t-9t、
    风牌元牌“东南西北中发白”，其中“白”为财神。非法牌值在构造时立即
    失败，防止官方字符串未经显式映射就进入规则或策略模块；牌的等价、
    分解与合法性判断属于 `hangma` 规则模块，不在本类中实现。
    """

    code: str

    def __post_init__(self) -> None:
        # 只做值域与类型校验，属于廉价结构校验，不是业务规则判断。
        if not isinstance(self.code, str) or self.code not in CANONICAL_TILE_CODES:
            raise ValueError(
                "非法规范牌值 {0!r}；合法取值见 CANONICAL_TILE_CODES".format(self.code)
            )


def _validate_seat(seat: object, field_name: str) -> None:
    """座位下标必须位于 0—3；越界只可能是上游映射错误，必须立刻失败。

    本函数与 `_validate_tile` 是 kernel 包内共享的私有校验助手，
    不属于对外接口基线。
    """
    if isinstance(seat, bool) or not isinstance(seat, int) or not 0 <= seat < SEAT_COUNT:
        raise ValueError(
            "{0} 必须是 0-{1} 的座位下标，得到 {2!r}".format(field_name, SEAT_COUNT - 1, seat)
        )


def _validate_tile(tile: object, field_name: str) -> None:
    """动作参数位置的牌值必须是规范 `Tile`，防止裸字符串混入业务模块。"""
    if not isinstance(tile, Tile):
        raise ValueError(
            "{0} 必须是 Tile 值对象，得到 {1!r}；官方牌码由适配器显式映射".format(field_name, tile)
        )


def _require_non_empty_str(value: object, field_name: str) -> None:
    """非空且非纯空白字符串校验；空白标识只可能是装配错误。"""
    if not isinstance(value, str) or not value or not value.strip():
        raise ValueError("{0} 必须是非空白字符串".format(field_name))


def _require_non_negative_int(value: object, field_name: str) -> None:
    """非负整数校验；序号、局号与计数不允许负数或 bool 混入。

    `trigger_seq=0` 必须放行：官方协议用 seq=0 请求全量快照（API §2.3）。
    `round_no` 按非负校验（官方局号惯例从 1 起，但 1 起语义未文档化确认，
    收紧为 >=1 属契约变更，须待官方样本证实后再调整）。
    """
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("{0} 必须是非负整数，得到 {1!r}".format(field_name, value))


def _require_tuple(value: object, field_name: str) -> None:
    """序列字段必须是 tuple；list 等可变容器在构造期拒绝（fail-fast）。

    拒绝而非拷贝规范化：可变容器会使冻结值对象的身份在构造后漂移
    （action_key/哈希/审计关联随之变化），让错误暴露在调用方转换点
    而不是被静默吸收；官方快照热路径也无需为每字段付拷贝成本。
    """
    if not isinstance(value, tuple):
        raise ValueError(
            "{0} 必须是 tuple（可变序列请先在调用方 tuple(...) 转换），得到 {1}".format(
                field_name, type(value).__name__
            )
        )


class GangKind(str, Enum):
    """杠的种类；适配器负责把官方 `data.kind`（an/ming/bu）映射到本枚举。"""

    CONCEALED = "concealed"  # 暗杠（an）
    EXPOSED = "exposed"      # 明杠（ming）
    ADDED = "added"          # 补杠（bu）


@dataclass(frozen=True)
class Discard:
    """打出一张牌。"""

    tile: Tile

    def __post_init__(self) -> None:
        _validate_tile(self.tile, "Discard.tile")


@dataclass(frozen=True)
class Chi:
    """使用三张牌组成顺子；`tiles` 按牌值顺序保存且包含被吃牌。

    顺序约定由构造方（规则/适配器）保证；本类只校验张数与类型，
    是否构成合法顺子由 `hangma` 规则模块判断。
    """

    tiles: Tuple[Tile, Tile, Tile]

    def __post_init__(self) -> None:
        _require_tuple(self.tiles, "Chi.tiles")
        if len(self.tiles) != 3:
            raise ValueError(
                "Chi.tiles 必须恰好 3 张（含被吃牌），得到 {0} 张".format(len(self.tiles))
            )
        for tile in self.tiles:
            _validate_tile(tile, "Chi.tiles")


@dataclass(frozen=True)
class Peng:
    """碰指定牌值。"""

    tile: Tile

    def __post_init__(self) -> None:
        _validate_tile(self.tile, "Peng.tile")


@dataclass(frozen=True)
class Gang:
    """按指定类型杠牌。"""

    tile: Tile
    kind: GangKind

    def __post_init__(self) -> None:
        _validate_tile(self.tile, "Gang.tile")
        if not isinstance(self.kind, GangKind):
            raise ValueError(
                "Gang.kind 必须是 GangKind 枚举，得到 {0!r}；官方杠种由适配器映射".format(self.kind)
            )


@dataclass(frozen=True)
class Hu:
    """声明胡牌。"""


@dataclass(frozen=True)
class Pass:
    """放弃当前响应机会。"""


# 封闭动作联合：覆盖出牌、吃、碰、杠（暗/明/补）、胡、过的全部动作族；
# 禁止用携带大量可空字段的通用字典替代（kernel/AGENTS.md 验收标准）。
Action = Union[Discard, Chi, Peng, Gang, Hu, Pass]


class WindowPhase(str, Enum):
    """需要我方在限时窗口内作出动作的规范阶段。

    官方快照 `phase` 的完整取值为 deal/draw/response_peng/response_chi/
    settled/finished（指南 v8，检查日期 2026-09-03）；其中需要我方限时
    行动的只有本枚举三个值，deal/settled/finished 不产生动作窗口。
    """

    DRAW = "draw"  # 本人回合摸牌后：出牌、自摸胡、杠
    RESPONSE_PENG = "response_peng"  # 他人弃牌后的碰/明杠响应窗口（1 秒）
    RESPONSE_CHI = "response_chi"  # 随后轮转的吃响应窗口（1 秒）


@dataclass(frozen=True)
class WindowKey:
    """动作窗口唯一键；碰窗口与随后吃窗口必须是不同键。"""

    game_id: str  # 官方场次标识，原样保存
    round_no: int  # 官方当前局号
    trigger_seq: int  # 触发本窗口的官方事件序号
    phase: WindowPhase  # 需要我方行动的规范阶段
    seat: int  # 我方座位，固定 0—3

    def __post_init__(self) -> None:
        # 廉价结构校验：非空白场次标识、阶段枚举类型、座位范围与序号值域。
        _require_non_empty_str(self.game_id, "WindowKey.game_id")
        if not isinstance(self.phase, WindowPhase):
            raise ValueError(
                "WindowKey.phase 必须是 WindowPhase 枚举，得到 {0!r}".format(self.phase)
            )
        _validate_seat(self.seat, "WindowKey.seat")
        _require_non_negative_int(self.round_no, "WindowKey.round_no")
        _require_non_negative_int(self.trigger_seq, "WindowKey.trigger_seq")


def action_key(action: Action) -> str:
    """返回稳定动作键，用于排序、排除已拒绝动作和审计关联。

    键只由动作种类和牌值决定：同一规范动作在全生命周期保持一致，
    不包含 Token、时间或进程随机值；杠按“杠种:牌值”区分三类。
    未知类型抛 `TypeError`：这是跨模块契约——`hangma` 验证与
    `policy` 候选过滤依赖捕获 `TypeError` 做故障隔离，不得改为
    `ValueError`（终裁第 3 轮推翻 RS-3 统一提案的集成事实依据）。
    """
    if isinstance(action, Discard):
        return "discard:{}".format(action.tile.code)
    if isinstance(action, Chi):
        return "chi:{}".format(",".join(tile.code for tile in action.tiles))
    if isinstance(action, Peng):
        return "peng:{}".format(action.tile.code)
    if isinstance(action, Gang):
        return "gang:{}:{}".format(action.kind.value, action.tile.code)
    if isinstance(action, Hu):
        return "hu"
    if isinstance(action, Pass):
        return "pass"
    raise TypeError("未知内部动作类型: {!r}".format(type(action)))
