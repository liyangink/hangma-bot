"""杭麻手牌数学：胡牌判定、向听、有效牌、任意听与确定性分解。

标准型由同语义的 Python/C 分组动态规划计算：万、筒、条、字牌分别
求局部面子／将／财神成本，再合成整手结果。缺位逐一枚举财神和
自然虚牌，完整维护每种自然牌的四张上限；不能贪心提前耗尽财神。
七对和确定性证据仍在本模块产生，动作族和结算继续复用这些结果。

need 表示最少额外自然进张数，标准型 shanten = need - 1；当前财神
补位成本为零，未来白板进张另由有效牌枚举处理。多余暗牌视为可弃。
原生库由安装期构建，导入时选择可用实现；不可用时使用修正后的
Python 分组算法。运行中不编译、不访问网络、文件或系统时钟。

规则依据：RULES_EVIDENCE.md；官方 v9 起的手牌金例与后续规则回归。
2026-09-07 数学修复和独立目标校验见 grouped-dp-integration 验收记录。
"""

from __future__ import annotations

from typing import Optional, Tuple

from hangma_bot.kernel.actions import Tile

from ._standard import backend_info as math_backend_info, need as _need_std
from .internal_types import (
    TILE_ORDER,
    WEALTH_CODE,
    Counts34,
    HandSummary,
    UsefulTile,
    WinSplit,
    counts_from_tiles,
)

_BRANCH_PLAIN = "平胡"
_BRANCH_CHIITOI = "七对"
_WHITE_CODE = WEALTH_CODE


def _dec(counts: Tuple[int, ...], index: int, n: int) -> Tuple[int, ...]:
    """返回 counts[index] 减少 n 后的新元组（计数向量的不可变更新）。"""

    return counts[:index] + (counts[index] - n,) + counts[index + 1 :]


def _chiitoi_pairs(counts: Tuple[int, ...], whites: int) -> int:
    """七对成型对数（财神补对；四张同牌按两对计，故无种类数约束）。

    白板最优用法：先与单张自然牌配对（1 白换 1 对），余白两两自对。
    """

    natural_pairs = sum(value // 2 for value in counts)
    singles = sum(value % 2 for value in counts)
    paired_with_white = min(whites, singles)
    leftover_whites = whites - paired_with_white
    return min(7, natural_pairs + paired_with_white + leftover_whites // 2)


def _split_counts(counts34: Counts34) -> Tuple[Tuple[int, ...], int]:
    """34 维计数 → (33 维自然牌计数, 白板张数)。"""

    return counts34[:33], counts34[33]


def _is_win_counts(counts34: Counts34, meld_set_count: int) -> bool:
    """按标准型 ∨ 七对判定计数向量是否成胡（纯函数，供任意听复用）。"""

    counts, whites = _split_counts(counts34)
    if (
        _need_std(counts, whites, 4 - meld_set_count, True)
        == 0
    ):
        return True
    return meld_set_count == 0 and _chiitoi_pairs(counts, whites) == 7


def _validate_melds(meld_set_count: int) -> None:
    """副露数廉价结构校验：吃/碰/杠副露各计 1，合法域 0-4。"""

    if (
        isinstance(meld_set_count, bool)
        or not isinstance(meld_set_count, int)
        or not 0 <= meld_set_count <= 4
    ):
        raise ValueError(
            "meld_set_count 必须是 0-4 的整数，得到 {0!r}".format(meld_set_count)
        )


def analyse_hand(hand_tiles: Tuple[Tile, ...], meld_set_count: int) -> HandSummary:
    """确定性手牌分析：胡牌、向听、有效牌与白板计数。

    参数：
      hand_tiles：暗牌全集（含刚摸牌，调用方已合并）；副露不参与，
        只以 meld_set_count 折算固定面子数；
      meld_set_count：吃/碰/杠副露各计 1（0-4）；七对仅门清有效。

    约定：未胡 shanten ≥ 0（0=听牌）；已胡 is_win=True 且 shanten=-1；
    chiitoi_shanten 在 meld_set_count>0 时为 None；useful_tiles 按规范
    顺序（TILE_ORDER）去重；手留白板 < 4 时白板恒有效（百搭严格
      不劣于任何有效牌），已持 4 张时第 5 张物理不可得、不列入；
    evidence 为人可读的确定性证据元组（审计用）。向听的虚牌受每种
    4 张上限约束（分组内持续扣减配额），有效牌不含不可能摸到的第 5
    张同种牌。
    """

    _validate_melds(meld_set_count)
    counts34 = counts_from_tiles(hand_tiles)
    counts, whites = _split_counts(counts34)
    sets_needed = 4 - meld_set_count

    standard_shanten = _need_std(counts, whites, sets_needed, True) - 1
    if meld_set_count == 0:
        chiitoi_shanten = 6 - _chiitoi_pairs(counts, whites)
    else:
        chiitoi_shanten = None
    shanten = (
        standard_shanten
        if chiitoi_shanten is None
        else min(standard_shanten, chiitoi_shanten)
    )
    is_win = shanten == -1

    useful_tiles: Tuple[UsefulTile, ...] = ()
    if not is_win:
        entries: list = []
        for index in range(34):
            if counts34[index] >= 4:
                # 全 4 张同种牌在手 → 第 5 张不可能摸到，不是有效牌
                #（评审 d5-a0c5d8：防止"第 5 张东"式幻影进张进入策略输入）。
                continue
            drawn = list(counts34)
            drawn[index] += 1
            d_counts, d_whites = _split_counts(tuple(drawn))
            after = _need_std(
                d_counts, d_whites, sets_needed, True
            ) - 1
            if meld_set_count == 0:
                after = min(after, 6 - _chiitoi_pairs(d_counts, d_whites))
            if after < shanten:
                entries.append(UsefulTile(code=TILE_ORDER[index], shanten_after=after))
        if whites < 4 and not any(entry.code == _WHITE_CODE for entry in entries):
            # 契约保险：百搭恒有效（数学上必然成立，此分支仅为防御）。
            # 已持 4 张白板时第 5 张物理不可得，不补入（评审 d8-f4dadf）。
            entries.append(UsefulTile(code=_WHITE_CODE, shanten_after=shanten - 1))
        useful_tiles = tuple(entries)

    evidence_parts = ["标准型向听 {0}".format(standard_shanten)]
    evidence_parts.append(
        "七对向听 {0}".format(
            chiitoi_shanten if chiitoi_shanten is not None else "N/A(有副露)"
        )
    )
    evidence_parts.append("最优向听 {0}{1}".format(shanten, "(已胡)" if is_win else ""))
    evidence_parts.append("手留白板 {0} 张".format(whites))
    return HandSummary(
        is_win=is_win,
        standard_shanten=standard_shanten,
        chiitoi_shanten=chiitoi_shanten,
        shanten=shanten,
        useful_tiles=useful_tiles,
        whites_held=whites,
        evidence=tuple(evidence_parts),
    )


def _block_label(kind: str, tiles) -> str:
    """块证据标签：如 刻子:1w1w白 / 顺子:白8w9w / 将:东东。"""

    return "{0}:{1}".format(kind, "".join(tiles))


def _split_std_evidence(
    counts: Tuple[int, ...], whites: int, sets_left: int, pair_needed: bool
) -> Optional[Tuple[str, ...]]:
    """标准型胡牌分解的确定性证据（首个找到的分解，枚举顺序固定）。

    只对缺牌数为零的手牌生成完整块证据，不枚举未来虚牌；未成牌返回 None。
    """

    if sets_left == 0 and not pair_needed:
        return ()
    index = -1
    for i in range(33):
        if counts[i]:
            index = i
            break
    if index == -1:
        # 自然牌耗尽：剩余块全部由白构成（仅成胡路径会到达且白必然够）。
        blocks: list = []
        w = whites
        if pair_needed:
            if w >= 2:
                blocks.append(_block_label("将", ("白", "白")))
                w -= 2
            else:
                return None
        for _ in range(sets_left):
            if w >= 3:
                blocks.append(_block_label("刻子", ("白", "白", "白")))
                w -= 3
            else:
                return None
        return tuple(blocks)

    code = TILE_ORDER[index]
    held = counts[index]
    result: Optional[Tuple[str, ...]]
    if pair_needed:
        # 将眼分支：自然对 / 自然+白 / 白白。
        if held >= 2:
            result = _split_std_evidence(
                _dec(counts, index, 2), whites, sets_left, False
            )
            if result is not None:
                return (_block_label("将", (code, code)),) + result
        if held >= 1 and whites >= 1:
            result = _split_std_evidence(
                _dec(counts, index, 1), whites - 1, sets_left, False
            )
            if result is not None:
                return (_block_label("将", (code, "白")),) + result
        if whites >= 2:
            result = _split_std_evidence(counts, whites - 2, sets_left, False)
            if result is not None:
                return (_block_label("将", ("白", "白")),) + result
    # 刻子（自然优先 + 白垫）。
    natural = min(held, 3)
    pad_white = min(3 - natural, whites)
    if natural + pad_white == 3:
        result = _split_std_evidence(
            _dec(counts, index, natural),
            whites - pad_white,
            sets_left - 1,
            pair_needed,
        )
        if result is not None:
            tiles = tuple([code] * natural + ["白"] * pad_white)
            return (_block_label("刻子", tiles),) + result
    # 纯白刻。
    if whites >= 3:
        result = _split_std_evidence(counts, whites - 3, sets_left - 1, pair_needed)
        if result is not None:
            return (_block_label("刻子", ("白", "白", "白")),) + result
    # 顺子窗口（空位白垫，含起始位）。
    if index < 27:
        suit_start = (index // 9) * 9
        for start in range(max(index - 2, suit_start), min(index, suit_start + 6) + 1):
            remaining = list(counts)
            tiles: list = []
            ok = True
            for pos in (start, start + 1, start + 2):
                if remaining[pos]:
                    remaining[pos] -= 1
                    tiles.append(TILE_ORDER[pos])
                elif tiles.count("白") < whites:
                    tiles.append("白")
                else:
                    ok = False
                    break
            if not ok:
                continue
            used_white = tiles.count("白")
            result = _split_std_evidence(
                tuple(remaining), whites - used_white, sets_left - 1, pair_needed
            )
            if result is not None:
                label_tiles = tuple(
                    sorted(tiles, key=lambda t: (t == "白", TILE_ORDER.index(t)))
                )
                return (_block_label("顺子", label_tiles),) + result
    return None


def win_split(hand_tiles: Tuple[Tile, ...], meld_set_count: int) -> Optional[WinSplit]:
    """胡牌分解元数据（分支 / 豪华组数 / 手留白板 / 证据）；未胡返回 None。

    分支选择：七对与平胡同时成立时取七对（分支因子 2×2^N 恒 ≥ 平胡 1，
    与官方 fan-calc 明细一致，金例 held3-no-white-pair 等核对）。
    豪华组数（仅七对）：四张同牌按两对计 1 组；4 张真白板也算 1 组
    （金例 chiitoi-held4）；平胡分支恒 0。

    any_tile_tenpai 说明：本函数收到的 hand_tiles 是暗牌全集（14 张口径），
    "摸牌前 13 张 + 任意一张都胡"无法在此口径下判定，故恒填 False 占位；
    调用方（engine/test）应使用 any_tile_win(摸牌前 13 张, meld_set_count)
    判定后以 dataclasses.replace 覆盖该字段。
    """

    _validate_melds(meld_set_count)
    counts34 = counts_from_tiles(hand_tiles)
    counts, whites = _split_counts(counts34)

    if meld_set_count == 0:
        if _chiitoi_pairs(counts, whites) == 7:
            luxury = sum(1 for value in counts if value == 4) + (
                1 if whites == 4 else 0
            )
            pair_labels: list = []
            for i, value in enumerate(counts):
                # 每两张自然牌一对；四张同牌即两对（其中一对计入豪华）。
                for _ in range(value // 2):
                    pair_labels.append(_block_label("对", (TILE_ORDER[i],) * 2))
            singles = [i for i, value in enumerate(counts) if value % 2 == 1]
            white_left = whites
            for i in singles:
                if white_left:
                    pair_labels.append(_block_label("对", (TILE_ORDER[i], "白")))
                    white_left -= 1
            while white_left >= 2:
                pair_labels.append(_block_label("对", ("白", "白")))
                white_left -= 2
            evidence = tuple(pair_labels[:7]) + (
                "豪华组数 {0}".format(luxury),
                "手留白板 {0} 张".format(whites),
            )
            return WinSplit(
                branch=_BRANCH_CHIITOI,
                luxury_pairs=luxury,
                whites_held=whites,
                any_tile_tenpai=False,
                evidence=evidence,
            )

    if (
        _need_std(counts, whites, 4 - meld_set_count, True)
        == 0
    ):
        blocks = _split_std_evidence(counts, whites, 4 - meld_set_count, True)
        evidence = (blocks or ()) + ("手留白板 {0} 张".format(whites),)
        return WinSplit(
            branch=_BRANCH_PLAIN,
            luxury_pairs=0,
            whites_held=whites,
            any_tile_tenpai=False,
            evidence=evidence,
        )
    return None


def any_tile_win(hand_tiles_13: Tuple[Tile, ...], meld_set_count: int) -> bool:
    """任意听判定：摸牌前 13 张暗牌 + 34 种任意一张牌都胡（爆头核心）。

    【官方】指南 1.2 / RULES_EVIDENCE §5：爆头 ⟺ 本判定 ∧ 胡牌时手留
    白板数 ≠ 4（"≠4"由调用方叠加，见 special_rules.static_baotou）。
    判定只看摸前 13 张（白作摸牌不影响）；白作百搭参与，可垫顺子任意
    位置（含起始位）、作将、白白自对、白白白自刻。副露折算：需
    (4-副露数) 组面子 + 将。内部复用记忆化的成胡判定（34 次判定毫秒级）。
    遍历种类时跳过在手已满 4 张的种类（第 5 张物理不可得）；该口径
    已被金例 chiitoi-3lux-white 类构型覆盖（评审 d8-f4dadf 核对）。
    """

    _validate_melds(meld_set_count)
    base = list(counts_from_tiles(hand_tiles_13))
    for index in range(34):
        if base[index] >= 4:
            continue  # 第 5 张同种牌不存在，不可能成为摸到的"任意一张"
        drawn = list(base)
        drawn[index] += 1
        if not _is_win_counts(tuple(drawn), meld_set_count):
            return False
    return True
