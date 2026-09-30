"""VIP 用途约束的纯手牌结构事实，不授予胡牌或动作资格。

输入始终是含全部保留白的 ``13 - 3*m`` 张弃后等待态。真实向听复用
现有手牌数学；自然缺口另以目标块数、用白数和目标阶段定义，不能跨
目标当作成胡速度比较。摸后多一张的状态必须先由规则枚举合法弃牌。

标准型距离复用权威分组求解器。其白资源是使用上限，但本模块的距离
也等于恰用白的最优值：任意少用白的目标，都可把目标自然实体换成白
直到用满，块形不变、自然缺口不增、自然实体配额只减不增；反向由
恰用目标是上限目标的子集得到等值。该证明要求白不超过目标槽位。
这里返回精确距离，不生成分解见证；``witness=None`` 明确标明此范围。

规则来源是 ``hand_analysis``、``_standard`` 和 ``RULES_EVIDENCE.md``。
本模块不读取完整世界、公开容量、文件、网络或时钟；当前合法胡及
合法续行仍由现有规则分支提供。本批没有新增官方规则确认。
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER

from ._standard import need as _standard_need
from .hand_analysis import _chiitoi_pairs

ROUTE_STRUCTURE_SCHEMA_VERSION = "vip-route-structure/1"
"""用途结构事实的语义版本；与真实向听及旧候选契约分别绑定。"""

_Family = Literal["standard", "seven_pairs"]
_Stage = Literal["complete_structure", "waiting_predecessor"]


@dataclass(frozen=True)
class RouteStructureTarget:
    """一个固定牌型、白用途与阶段下的自然缺口，单位均为张或动作次。

    这些是理想自然补张到指定目标的条件下界，不包含新增白、鸣牌转换、
    他家截断或规则资格。进张代码仅表示补张后同一目标距离降低，尚未
    验证实际弃牌过程；空集合不代表当次合法胡集合为空。
    """

    family: _Family  # 普通型或七对；普通与七对共有进张不可相加计宽度。
    retained_whites: int  # k；前驱保留一白，其余 k-1 白待合法弃出。
    white_used: int  # 块内恰用的实体白张数，恒为原库存 w-k。
    target_stage: _Stage  # 完成结构或等待前驱；结构不等于合法胡。
    target_natural_size: int  # 目标块中所需自然实体总张数，不含保留白。
    natural_need: int  # D=min sum(max(目标自然计数-当前自然计数,0))。
    target_natural_draw_lower_bound: int  # 达到该固定目标至少补 D 张自然牌。
    target_natural_discard_lower_bound: int  # 达到目标的自然弃牌次数，未验资格。
    target_white_discard_lower_bound: int  # 前驱待弃白次数 k-1，完成目标为 0。
    requires_terminal_draw: bool  # 前驱成形后仍需下一合法摸牌/补牌才可能胡。
    conditional_need_improvement_codes: tuple[str, ...]  # 规范顺序、去重且排白。
    witness: tuple[str, ...] | None = None  # 本版本不生成分解见证，恒为 None。
    witness_status: Literal["distance_only"] = "distance_only"  # 距离已算，分解见证未生成。


@dataclass(frozen=True)
class RouteStructureFacts:
    """来自真实全手的不可变结构事实，不含隐藏牌、容量或赛事压力。"""

    natural_counts33: tuple[int, ...]  # 规范 34 牌序前 33 位，每码 0-4 张。
    whites_held: int  # 真实白库存 w，包含全部保留白。
    meld_set_count: int  # 吃、碰、杠各折算一组；杠实体第四张不进此手牌。
    standard_shanten: int  # 原权威普通型向听，未删白、未改语义。
    seven_pairs_shanten: int | None  # 原七对向听；有副露时为 None（不适用）。
    natural_pair_count: int  # 自然实体对子数；四张同码按两对计。
    natural_quad_codes: tuple[str, ...]  # 自然四张的规范牌码；不推断豪华胡资格。
    targets: tuple[RouteStructureTarget, ...]  # 逐牌型及 k=0..w，不合并不同目标。
    target_distance_evaluation_count: int  # 本次目标距离请求次数；不等于后端节点数。


def _validate_waiting_counts(counts34: tuple[int, ...], meld_set_count: int) -> None:
    """校验纯手牌实体域与等待态守恒；不判断当前窗口或副露合法性。"""

    if type(counts34) is not tuple:
        raise TypeError("counts34 必须是规范牌序的 tuple")
    if len(counts34) != 34:
        raise ValueError("counts34 必须包含 34 个规范牌值计数")
    if type(meld_set_count) is not int:
        raise TypeError("meld_set_count 必须是整数")
    if not 0 <= meld_set_count <= 4:
        raise ValueError("meld_set_count 必须在 0-4 范围内")
    for value in counts34:
        if type(value) is not int:
            raise TypeError("每种牌计数必须是整数，不能是布尔值")
        if not 0 <= value <= 4:
            raise ValueError("每种牌实体计数必须在 0-4 范围内")
    if sum(counts34) != 13 - 3 * meld_set_count:
        raise ValueError("只支持 13-3m 张等待态；动作态请先枚举合法弃牌")


def _seven_pairs_need(counts33: tuple[int, ...], whites: int, pairs: int) -> int:
    """把原七对补对规则推广到指定 6/7 对目标，返回理想自然补张数。

    先保留最多 pairs 个已成自然对；四张同码是两对。其余 r 对至多
    使用 r 个自然单张，每个单张和可用白各填一个槽位，缺槽即需自然
    补张。最多 7 对、33 个自然牌码足以放置新增纯自然对；已有奇数
    牌码只需补一张且不会超过四张。与真实向听分别输出。
    """

    natural_pairs = sum(value // 2 for value in counts33)
    singles = sum(value % 2 for value in counts33)
    remaining_pairs = max(0, pairs - natural_pairs)
    return max(0, 2 * remaining_pairs - min(singles, remaining_pairs) - whites)


def _target_need(
    counts33: tuple[int, ...], whites: int, sets_left: int, family: _Family, k: int
) -> int:
    """固定目标距离；k 仅区分完成/前驱，不在摸牌后更换白用途。"""

    if family == "standard":
        return _standard_need(counts33, whites, sets_left, k == 0)
    return _seven_pairs_need(counts33, whites, 7 if k == 0 else 6)


def analyze_route_structure(
    counts34: tuple[int, ...], meld_set_count: int
) -> RouteStructureFacts:
    """分析完整等待手牌的分牌型向听和逐白用途自然缺口。

    输入计数按 ``CANONICAL_TILE_ORDER``（白在最后），只接受每码 0-4
    且总张数为 ``13-3m`` 的 tuple；非法类型抛 TypeError，非法数量
    抛 ValueError。结果仅是手牌数学，无动作、胡资格或副作用。缓存
    最多保存 2048 个不可变结果，不读取系统时间。

    ``k=0`` 为剩余面子+将/七对的完成目标；``k>=1`` 为剩余面子/
    六对+一白的等待前驱。块内恰用 ``w-k`` 白，其余白仍在真实库存中。
    进张枚举只补自然实体、保持同目标，排除已有四张的物理第五张。
    调用方负责公开容量、给定摸牌后的合法续行和终点胡集合。
    """

    _validate_waiting_counts(counts34, meld_set_count)
    return _analyze_validated_counts(counts34, meld_set_count)


@lru_cache(maxsize=2048)
def _analyze_validated_counts(
    counts34: tuple[int, ...], meld_set_count: int
) -> RouteStructureFacts:
    """仅缓存已校验的实体计数，避免 bool/int 相等绕过边界校验。"""

    natural = counts34[:33]
    whites = counts34[33]
    sets_left = 4 - meld_set_count
    standard_shanten = _standard_need(natural, whites, sets_left, True) - 1
    seven_pairs_shanten = (
        6 - _chiitoi_pairs(natural, whites) if meld_set_count == 0 else None
    )
    natural_pairs = sum(value // 2 for value in natural)
    targets = []
    evaluations = 0
    families: tuple[_Family, ...] = (
        ("standard", "seven_pairs") if meld_set_count == 0 else ("standard",)
    )
    for family in families:
        for retained in range(whites + 1):
            used = whites - retained
            predecessor = retained > 0
            slots = (
                3 * sets_left + (0 if predecessor else 2)
                if family == "standard"
                else (12 if predecessor else 14)
            )
            need = _target_need(natural, used, sets_left, family, retained)
            evaluations += 1
            # 等待态库存与目标自然总量的差，限定需弃牌数量；距离不能
            # 偷用保留白，也不能以删白后的残缺手牌冒充真实向听。
            natural_discards = need - (retained - 1) if predecessor else need - 1
            if used > slots or natural_discards < 0:
                raise RuntimeError("用途结构距离违反等待态数量守恒")
            improving = []
            for index, held in enumerate(natural):
                if held == 4:
                    continue
                drawn = natural[:index] + (held + 1,) + natural[index + 1 :]
                after_need = _target_need(drawn, used, sets_left, family, retained)
                evaluations += 1
                if after_need < need:
                    improving.append(CANONICAL_TILE_ORDER[index])
            targets.append(
                RouteStructureTarget(
                    family=family,
                    retained_whites=retained,
                    white_used=used,
                    target_stage="waiting_predecessor" if predecessor else "complete_structure",
                    target_natural_size=slots - used,
                    natural_need=need,
                    target_natural_draw_lower_bound=need,
                    target_natural_discard_lower_bound=natural_discards,
                    target_white_discard_lower_bound=retained - 1 if predecessor else 0,
                    requires_terminal_draw=predecessor,
                    conditional_need_improvement_codes=tuple(improving),
                )
            )
    return RouteStructureFacts(
        natural_counts33=natural,
        whites_held=whites,
        meld_set_count=meld_set_count,
        standard_shanten=standard_shanten,
        seven_pairs_shanten=seven_pairs_shanten,
        natural_pair_count=natural_pairs,
        natural_quad_codes=tuple(
            CANONICAL_TILE_ORDER[index] for index, count in enumerate(natural) if count == 4
        ),
        targets=tuple(targets),
        target_distance_evaluation_count=evaluations,
    )
