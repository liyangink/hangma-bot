"""计算真实等待手牌的自然面子准备事实，不授予未来白板或胡牌资格。

普通型目标只要求剩余自然面子，不要求将，也不使用白板百搭。距离
复用唯一标准型数学 ``_standard.need``；这补充了零白手牌的有限准备
事实，不修改含全部白板的真实向听，也不是另一个爆头判定器。

规则依据见 ``RULES_EVIDENCE.md`` 的牌系统和标准型条款。这里没有
新增官方规则确认：给定目标的缺张、弃牌下界和推进码是数学事实。
它们不包含他家暗牌、未来牌墙、公开剩余容量或等待成功概率。
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER

from ._standard import need as _standard_need

NATURAL_PREPARATION_SEMANTICS_VERSION = "vip-natural-set-preparation/1"
"""自然面子准备的独立语义版本；不替换真实向听或旧路线目标版本。"""


@dataclass(frozen=True)
class NaturalSetPreparationFacts:
    """指定自然面子目标的不可变事实，数量字段单位均为张或组。

    所有真实白板仍在库存中，只是不允许在这个目标内充当百搭。
    补张下界按实体张数计，不是需要再摸几次；固定副露组数，不含
    吃碰转换。缺张为零仅说明暗牌已包含所需自然面子，尚未证明有白板、已经
    进入爆头或能通过合法动作达到该状态。改善码是同一目标的数学
    推进，不证明牌山有该牌，更不表示当前直接胡牌集合。
    """

    natural_counts33: tuple[int, ...]  # 规范牌序前33位的真实暗牌，每码0-4。
    whites_held: int  # 真实白库存0-4；没有假设将来已摸到白板。
    meld_set_count: int  # 吃、碰、杠各折算一组；不读副露内牌值。
    sets_left: int  # 自然面子目标组数，恒为4-meld_set_count，不含将。
    target_natural_size: int  # 目标自然实体数，恒为3*sets_left。
    natural_draw_lower_bound: int  # D=min sum(max(目标计数-当前自然计数,0))。
    natural_discard_lower_bound: int  # sum(natural)+D-target_natural_size。
    natural_need_improvement_codes: tuple[str, ...]  # 自然补张使同目标D下降的规范码。
    target_distance_evaluation_count: int  # 首次构造该结果的距离请求数；缓存命中不新增。


def analyze_natural_set_preparation(
    counts34: tuple[int, ...], meld_set_count: int
) -> NaturalSetPreparationFacts:
    """分析真实 ``13-3m`` 等待手牌的自然面子准备程度。

    ``counts34`` 必须按 ``CANONICAL_TILE_ORDER``（白板最后）给出34维
    tuple，每码为整数0-4；``meld_set_count`` 为整数0-4。布尔值不算
    整数；非法类型抛 TypeError，数量或等待态守恒不符抛 ValueError。

    全部白板保留在结果中，目标计算仅使用前33种自然牌。函数不判断
    当前动作合法性、胡牌、爆头或番数，没有网络、时间、文件副作用。
    缓存最多保存2048个不可变结果；先校验再查缓存，避免bool/int相等
    绕过校验。调用方另外按公开容量判断改善码是否还有可见支持。
    """

    if type(counts34) is not tuple:
        raise TypeError("counts34 必须是规范牌序的 tuple")
    if len(counts34) != 34:
        raise ValueError("counts34 必须包含34个规范牌值计数")
    if type(meld_set_count) is not int:
        raise TypeError("meld_set_count 必须是整数，不能是布尔值")
    if not 0 <= meld_set_count <= 4:
        raise ValueError("meld_set_count 必须在0-4范围内")
    for value in counts34:
        if type(value) is not int:
            raise TypeError("每种牌计数必须是整数，不能是布尔值")
        if not 0 <= value <= 4:
            raise ValueError("每种牌实体计数必须在0-4范围内")
    if sum(counts34) != 13 - 3 * meld_set_count:
        raise ValueError("只支持13-3m张真实等待态；动作态须先枚举合法弃牌")
    return _analyze_validated_counts(counts34, meld_set_count)


@lru_cache(maxsize=2048)
def _analyze_validated_counts(
    counts34: tuple[int, ...], meld_set_count: int
) -> NaturalSetPreparationFacts:
    """复用权威标准型求解器；不复制分组算法或构造假想白板库存。"""

    natural = counts34[:33]
    sets_left = 4 - meld_set_count
    target_size = 3 * sets_left
    missing = _standard_need(natural, 0, sets_left, False)
    natural_discards = sum(natural) + missing - target_size
    if natural_discards < 0:
        raise RuntimeError("自然面子准备距离违反目标实体数量守恒")
    improving = []
    evaluations = 1
    for index, held in enumerate(natural):
        # 自然目标不准借白，也不能补本人暗牌已经持满的第五张实体。
        if held == 4:
            continue
        drawn = natural[:index] + (held + 1,) + natural[index + 1 :]
        after_missing = _standard_need(drawn, 0, sets_left, False)
        evaluations += 1
        if after_missing < missing:
            improving.append(CANONICAL_TILE_ORDER[index])
    return NaturalSetPreparationFacts(
        natural_counts33=natural,
        whites_held=counts34[33],
        meld_set_count=meld_set_count,
        sets_left=sets_left,
        target_natural_size=target_size,
        natural_draw_lower_bound=missing,
        natural_discard_lower_bound=natural_discards,
        natural_need_improvement_codes=tuple(improving),
        target_distance_evaluation_count=evaluations,
    )
