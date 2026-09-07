"""标准型手牌数学的纯 Python 后端：分组成本表与严格虚牌配额。

自然牌按万、筒、条、字分组，白板单独作为可分配的财神资源。
每组允许舍牌，并完整枚举财神与未来自然牌的分配；全局只合并面子、
将和财神数量。数学结果不包含胡牌行动资格、七对或结算。

缓存由每个求解器实例独立持有且有容量上限，不依赖网络、文件或时钟。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Protocol, cast

SEMANTICS_VERSION = "hangma-standard-grouped-v1"

# 计数/配额向量：完整自然牌为33维，局部花色为9维，字牌为6维。
_Vector = tuple[int, ...]
_CacheInfo = dict[str, dict[str, int | None]]

_INF = 99
_WHOLE_CAPACITY = 8192
_TABLE_CAPACITY = 4096
_LOCAL_CAPACITY = 65536
_EMPTY_CAPACITY = 16384


class _Solver(Protocol):
    """标准型后端的内部调用与缓存诊断接口。"""

    def __call__(
        self,
        counts33: tuple[int, ...],
        whites: int,
        sets_left: int,
        pair_needed: bool,
    ) -> int:
        """接收完整自然牌计数，返回最少未来自然牌张数。"""
        ...

    def cache_clear(self) -> None:
        """清空此实例的全部缓存，不改变数学语义。"""
        ...

    def cache_info(self) -> _CacheInfo:
        """返回各层缓存的条目容量与命中、未命中次数。"""
        ...


def _sub(values: _Vector, index: int, amount: int) -> _Vector:
    """不可变扣减；调用方保证不会产生负计数。"""
    return values[:index] + (values[index] - amount,) + values[index + 1 :]


def build_solver() -> _Solver:
    """创建独立的标准型求解器，输入完整自然牌计数和当前财神资源。

    返回函数只接受正常顶层计数，虚牌配额统一初始化为每种4减持有张数；
    不接收旧搜索的部分配额状态。输出为最少未来自然牌张数，99表示在
    给定资源下无解。输入类型错误抛出TypeError，长度或数值越界抛出ValueError。
    cache_clear/cache_info仅清理或读取本实例缓存，不改变数学语义。
    """

    @lru_cache(maxsize=_EMPTY_CAPACITY)
    def empty_fill(
        quota: _Vector,
        whites: int,
        sets_left: int,
        pair_needed: bool,
        suited: bool,
    ) -> int:
        """自然牌耗尽后，精确填入纯白/虚牌块，不假定配额永远够用。"""
        if sets_left == 0 and not pair_needed:
            return 0
        slots = 3 * sets_left + 2 * int(pair_needed)
        lower = max(0, slots - whites)
        if sum(quota) + whites < slots:
            return _INF
        best = _INF
        size = 2 if pair_needed else 3
        next_sets = sets_left if pair_needed else sets_left - 1
        for virtual in range(max(0, size - whites), size + 1):
            white_used = size - virtual
            if virtual == 0:
                best = min(
                    best, empty_fill(quota, whites - size, next_sets, False, suited)
                )
                if best == lower:
                    return best
                continue
            for index in range(len(quota)):
                if quota[index] < virtual:
                    continue
                child = empty_fill(
                    _sub(quota, index, virtual),
                    whites - white_used,
                    next_sets,
                    False,
                    suited,
                )
                best = min(best, virtual + child)
                if best == lower:
                    return best
        # 将可以交换到所有面子之前；无将时再枚举纯虚/白顺子。
        if suited and not pair_needed:
            for start in range(7):
                for mask in range(8):
                    virtual = mask.bit_count()
                    white_used = 3 - virtual
                    if white_used > whites or virtual >= best:
                        continue
                    remaining = list(quota)
                    for offset in range(3):
                        if mask & (1 << offset):
                            if remaining[start + offset] == 0:
                                break
                            remaining[start + offset] -= 1
                    else:
                        child = empty_fill(
                            tuple(remaining),
                            whites - white_used,
                            sets_left - 1,
                            False,
                            suited,
                        )
                        best = min(best, virtual + child)
                        if best == lower:
                            return best
        return best

    @lru_cache(maxsize=_LOCAL_CAPACITY)
    def local_need(
        counts: _Vector,
        quota: _Vector,
        whites: int,
        sets_left: int,
        pair_needed: bool,
        suited: bool,
    ) -> int:
        """组内精确搜索；自然牌块先处理，纯白/虚牌块延后到空牌基态。

        同种自然牌与其他块中的白/虚牌可交换，故每个选定块优先用满
        自然牌不损最优解；白却必须枚举使用量，才能留给受配额限制的块。
        纯白/虚牌块的资源扣减可交换到末尾，因此空牌后统一补全。
        """
        if sets_left == 0 and not pair_needed:
            return 0
        index = next((i for i, count in enumerate(counts) if count), -1)
        if index < 0:
            return empty_fill(quota, whites, sets_left, pair_needed, suited)
        lower = max(0, 3 * sets_left + 2 * int(pair_needed) - sum(counts) - whites)
        best = _INF
        if pair_needed:
            natural = min(2, counts[index])
            missing = 2 - natural
            remaining = _sub(counts, index, natural)
            for white_used in range(min(missing, whites), -1, -1):
                virtual = missing - white_used
                if virtual > quota[index] or virtual >= best:
                    continue
                child = local_need(
                    remaining,
                    _sub(quota, index, virtual),
                    whites - white_used,
                    sets_left,
                    False,
                    suited,
                )
                best = min(best, virtual + child)
                if best == lower:
                    return best
        if sets_left:
            natural = min(3, counts[index])
            missing = 3 - natural
            remaining = _sub(counts, index, natural)
            for white_used in range(min(missing, whites), -1, -1):
                virtual = missing - white_used
                if virtual > quota[index] or virtual >= best:
                    continue
                child = local_need(
                    remaining,
                    _sub(quota, index, virtual),
                    whites - white_used,
                    sets_left - 1,
                    pair_needed,
                    suited,
                )
                best = min(best, virtual + child)
                if best == lower:
                    return best
            if suited:
                for start in range(max(0, index - 2), min(index, 6) + 1):
                    run_remaining = list(counts)
                    missing_positions = []
                    for pos in range(start, start + 3):
                        if run_remaining[pos]:
                            run_remaining[pos] -= 1
                        else:
                            missing_positions.append(pos)
                    missing = len(missing_positions)
                    remaining_counts = tuple(run_remaining)
                    # 每一缺位分别选白或自然虚牌，预算不同也不会丢失分配。
                    for mask in range(1 << missing):
                        virtual = mask.bit_count()
                        white_used = missing - virtual
                        if white_used > whites or virtual >= best:
                            continue
                        remaining_quota = list(quota)
                        for offset, pos in enumerate(missing_positions):
                            if mask & (1 << offset):
                                if remaining_quota[pos] == 0:
                                    break
                                remaining_quota[pos] -= 1
                        else:
                            child = local_need(
                                remaining_counts,
                                tuple(remaining_quota),
                                whites - white_used,
                                sets_left - 1,
                                pair_needed,
                                suited,
                            )
                            best = min(best, virtual + child)
                            if best == lower:
                                return best
        # 舍牌不可省：当前最低自然牌可能不属于最优完整牌型。
        return min(
            best,
            local_need(
                _sub(counts, index, 1),
                quota,
                whites,
                sets_left,
                pair_needed,
                suited,
            ),
        )

    @lru_cache(maxsize=_TABLE_CAPACITY)
    def local_table(
        counts: _Vector,
        quota: _Vector,
        max_sets: int,
        max_pair: int,
        max_whites: int,
        suited: bool,
    ) -> tuple[int, ...]:
        """资源表扁平顺序为面子数、将标志、分配白数；只算当前所需上限。"""
        return tuple(
            local_need(counts, quota, whites, sets_left, bool(pair), suited)
            for sets_left in range(max_sets + 1)
            for pair in range(max_pair + 1)
            for whites in range(max_whites + 1)
        )

    @lru_cache(maxsize=_WHOLE_CAPACITY)
    def whole_need(
        counts: _Vector,
        quota: _Vector,
        whites: int,
        sets_left: int,
        pair_needed: bool,
    ) -> int:
        """四组min-plus合并，严格分配总面子、将和白；局部可以不用满白。"""
        if sets_left == 0 and not pair_needed:
            return 0
        max_pair = int(pair_needed)
        white_span = whites + 1
        meld_span = (max_pair + 1) * white_span
        tables = [
            local_table(
                counts[start:end],
                quota[start:end],
                sets_left,
                max_pair,
                whites,
                group < 3,
            )
            for group, (start, end) in enumerate(((0, 9), (9, 18), (18, 27), (27, 33)))
        ]
        current: tuple[int, ...] | list[int] = tables[0]
        for table in tables[1:]:
            following = [_INF] * len(table)
            for old_m in range(sets_left + 1):
                for old_p in range(max_pair + 1):
                    old_base = old_m * meld_span + old_p * white_span
                    for old_w in range(whites + 1):
                        prior = current[old_base + old_w]
                        if prior >= _INF:
                            continue
                        for add_m in range(sets_left - old_m + 1):
                            for add_p in range(max_pair - old_p + 1):
                                add_base = add_m * meld_span + add_p * white_span
                                total_base = (
                                    (old_m + add_m) * meld_span
                                    + (old_p + add_p) * white_span
                                    + old_w
                                )
                                for add_w in range(whites - old_w + 1):
                                    value = prior + table[add_base + add_w]
                                    total_index = total_base + add_w
                                    if value < following[total_index]:
                                        following[total_index] = value
            current = following
        return current[sets_left * meld_span + max_pair * white_span + whites]

    def need(
        counts33: tuple[int, ...],
        whites: int,
        sets_left: int,
        pair_needed: bool,
    ) -> int:
        """求标准型最少进张；自然牌按万、筒、条、东南西北中发排列。

        counts33不含白板，每种计数必须为整数0—4；whites为当前白板张数
        0—4，sets_left为剩余面子数0—4，pair_needed表示是否还需要将。
        多余实牌和财神允许不用；不会假想摸到物理上不存在的第五张牌。
        """
        if type(counts33) is not tuple:
            raise TypeError("自然牌计数必须为tuple")
        if len(counts33) != 33:
            raise ValueError("自然牌计数必须为33维")
        for value in counts33:
            if type(value) is not int:
                raise TypeError("每种自然牌计数必须为int")
            if not 0 <= value <= 4:
                raise ValueError("每种自然牌计数必须在0—4范围内")
        if type(whites) is not int:
            raise TypeError("财神张数必须为int")
        if not 0 <= whites <= 4:
            raise ValueError("财神张数必须在0—4范围内")
        if type(sets_left) is not int:
            raise TypeError("剩余面子数必须为int")
        if not 0 <= sets_left <= 4:
            raise ValueError("剩余面子数必须在0—4范围内")
        if type(pair_needed) is not bool:
            raise TypeError("将标志必须为bool")
        quota = tuple(4 - value for value in counts33)
        return whole_need(counts33, quota, whites, sets_left, pair_needed)

    def cache_clear() -> None:
        """同时清空本实例的全部懒加载缓存，用于冷启动性能测量。"""
        whole_need.cache_clear()
        local_table.cache_clear()
        local_need.cache_clear()
        empty_fill.cache_clear()

    def cache_info() -> _CacheInfo:
        """分别报告缓存上限、命中和实际状态数，不合并成误导性命中率。"""
        return {
            "whole": whole_need.cache_info()._asdict(),
            "local_tables": local_table.cache_info()._asdict(),
            "local_recursive": local_need.cache_info()._asdict(),
            "empty_fill": empty_fill.cache_info()._asdict(),
        }

    # 增补函数的诊断方法后再收束为协议类型，避免把普通函数误标为带属性接口。
    setattr(need, "cache_clear", cache_clear)
    setattr(need, "cache_info", cache_info)
    return cast(_Solver, need)
