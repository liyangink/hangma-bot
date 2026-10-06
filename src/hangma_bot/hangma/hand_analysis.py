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

from dataclasses import replace
from typing import Optional, Tuple
from builtins import int as _builtin_int, len as _builtin_len, tuple as _builtin_tuple, type as _builtin_type
from functools import lru_cache
from types import FunctionType

from hangma_bot.kernel.actions import Tile

from ._standard import backend_info as math_backend_info, need as _need_std
from .internal_types import (
    _COUNTS_FROM_TILES_CANONICAL_FUNCTION,
    _COUNTS_FROM_TILES_CANONICAL_CODE,
    TILE_ORDER,
    WEALTH_CODE,
    Counts34,
    HandProgressSummary,
    HandSummary,
    HandWinEvidence,
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


def _analyse_progress_math(
    hand_tiles: Tuple[Tile, ...],
    meld_set_count: int,
    *,
    collect_pattern_useful: bool,
):
    """共享的向听/进张核心；详细与轻量入口不得各写一套数学。"""

    counts34 = counts_from_tiles(hand_tiles)
    return _analyse_counts_progress_math(
        counts34,
        meld_set_count,
        collect_pattern_useful=collect_pattern_useful,
    )


def _analyse_counts_progress_math(
    counts34: Counts34,
    meld_set_count: int,
    *,
    collect_pattern_useful: bool,
):
    """34 维计数版共享数学；供规则模块的有界批量接口复用。"""

    _validate_melds(meld_set_count)
    if len(counts34) != 34:
        raise ValueError("counts34 必须包含 34 个规范牌值计数")
    counts, whites = _split_counts(counts34)
    sets_needed = 4 - meld_set_count

    standard_shanten = _need_std(counts, whites, sets_needed, True) - 1
    if meld_set_count == 0:
        # 七对基础统计只做一次。后续逐牌进张按该牌原计数奇偶 O(1)
        # 更新，避免在 34 次枚举中反复扫描 33 维自然牌；公式与
        # _chiitoi_pairs 完全相同（R17 P0 六遍摘要对账验证）。
        natural_pairs = sum(value // 2 for value in counts)
        natural_singles = sum(value % 2 for value in counts)
        paired_with_white = min(whites, natural_singles)
        pair_total = (
            natural_pairs + paired_with_white
            + (whites - paired_with_white) // 2
        )
        chiitoi_shanten = 6 - min(7, pair_total)
    else:
        natural_pairs = 0
        natural_singles = 0
        chiitoi_shanten = None
    shanten = (
        standard_shanten
        if chiitoi_shanten is None
        else min(standard_shanten, chiitoi_shanten)
    )
    is_win = shanten == -1

    entries = []
    standard_entries = [] if collect_pattern_useful else None
    seven_pairs_entries = [] if collect_pattern_useful else None
    if not is_win:
        for index in range(34):
            if counts34[index] >= 4:
                continue
            drawn = list(counts34)
            drawn[index] += 1
            d_counts, d_whites = _split_counts(tuple(drawn))
            after_standard = _need_std(
                d_counts, d_whites, sets_needed, True
            ) - 1
            after = after_standard
            if (
                standard_entries is not None
                and after_standard < standard_shanten
            ):
                standard_entries.append((TILE_ORDER[index], after_standard))
            if meld_set_count == 0:
                if index < 33:
                    held = counts34[index]
                    drawn_pairs = natural_pairs + (held % 2)
                    drawn_singles = natural_singles + (
                        1 if held % 2 == 0 else -1
                    )
                else:
                    drawn_pairs = natural_pairs
                    drawn_singles = natural_singles
                drawn_paired_with_white = min(d_whites, drawn_singles)
                drawn_pair_total = (
                    drawn_pairs + drawn_paired_with_white
                    + (d_whites - drawn_paired_with_white) // 2
                )
                after_seven_pairs = 6 - min(7, drawn_pair_total)
                after = min(after, after_seven_pairs)
                if (
                    seven_pairs_entries is not None
                    and after_seven_pairs < chiitoi_shanten
                ):
                    seven_pairs_entries.append(
                        (TILE_ORDER[index], after_seven_pairs)
                    )
            if after < shanten:
                entries.append((TILE_ORDER[index], after))
        if whites < 4 and not any(code == _WHITE_CODE for code, _ in entries):
            entries.append((_WHITE_CODE, shanten - 1))
    return (
        standard_shanten,
        chiitoi_shanten,
        shanten,
        is_win,
        whites,
        tuple(entries),
        None if standard_entries is None else tuple(standard_entries),
        None if seven_pairs_entries is None else tuple(seven_pairs_entries),
    )


def analyse_hand_win(hand_tiles: Tuple[Tile, ...], meld_set_count: int) -> HandWinEvidence:
    """只判当前完整暗牌是否成胡，不展开向听或下一摸有效牌。

    输入只含本人已知牌和固定副露数；副露数非法时抛 ``ValueError``。
    复用完整手牌分析的同一成胡判定，不能据此绕过动作资格或结算。
    本函数不访问外部状态，也不伪造未计算的完整分析字段。
    """

    _validate_melds(meld_set_count)
    is_win = _is_win_counts(counts_from_tiles(hand_tiles), meld_set_count)
    return HandWinEvidence(is_win, ("仅胡资格数学:同源标准型或七对成胡判定",))


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
    两组分牌型有效牌复用同一次进张枚举，分别对比各自当前向听；已胡
    不再枚举，返回 None；七对有副露时也为 None，已枚举空集合为 ()。
    """

    (
        standard_shanten,
        chiitoi_shanten,
        shanten,
        is_win,
        whites,
        entries,
        standard_entries,
        seven_pairs_entries,
    ) = _analyse_progress_math(
        hand_tiles, meld_set_count, collect_pattern_useful=True
    )
    useful_tiles = tuple(UsefulTile(code, after) for code, after in entries)
    standard_useful_tiles = (
        None
        if is_win
        else tuple(UsefulTile(code, after) for code, after in standard_entries)
    )
    seven_pairs_useful_tiles = (
        None
        if is_win or meld_set_count > 0
        else tuple(UsefulTile(code, after) for code, after in seven_pairs_entries)
    )

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
        standard_useful_tiles=standard_useful_tiles,
        seven_pairs_useful_tiles=seven_pairs_useful_tiles,
    )


def analyse_hand_progress(
    hand_tiles: Tuple[Tile, ...], meld_set_count: int
) -> HandProgressSummary:
    """返回公开后继 reducer 所需的轻量规则数学摘要。

    本入口与 ``analyse_hand`` 调用同一个 ``_analyse_progress_math``；只省略
    分牌型有效牌对象、白板计数和人读证据，不改变向听、成牌或综合有效
    牌集合。它是 ``hangma`` 内部批量接口，不是策略侧重算入口。
    """

    (
        standard_shanten,
        chiitoi_shanten,
        shanten,
        is_win,
        _,
        entries,
        _,
        _,
    ) = _analyse_progress_math(
        hand_tiles, meld_set_count, collect_pattern_useful=False
    )
    return HandProgressSummary(
        is_win=is_win,
        standard_shanten=standard_shanten,
        chiitoi_shanten=chiitoi_shanten,
        shanten=shanten,
        useful_codes=tuple(code for code, _ in entries),
    )


def analyse_counts_progress(
    counts34: Counts34, meld_set_count: int
) -> HandProgressSummary:
    """按 34 维规范计数返回轻量进张摘要。

    这是 ``hangma`` 内部批量入口。调用方必须从同模块规则状态构造计数；
    数学与 ``analyse_hand``、``analyse_hand_progress`` 共用
    ``_analyse_counts_progress_math``，不会形成第二套向听或有效牌实现。
    """

    (
        standard_shanten,
        chiitoi_shanten,
        shanten,
        is_win,
        _,
        entries,
        _,
        _,
    ) = _analyse_counts_progress_math(
        counts34, meld_set_count, collect_pattern_useful=False
    )
    return HandProgressSummary(
        is_win=is_win,
        standard_shanten=standard_shanten,
        chiitoi_shanten=chiitoi_shanten,
        shanten=shanten,
        useful_codes=tuple(code for code, _ in entries),
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
    豪华组数（仅七对）：四张自然同牌按两对计 1 组；4 张真白板仅在
    其余牌全为自然对、未用于补落单时计 1 组（官方 v23 §1.3，
    2026-09-08 抓取及 fan-calc 对拍）；平胡分支恒 0。

    any_tile_tenpai 说明：本函数收到的 hand_tiles 是暗牌全集（14 张口径），
    "摸牌前 13 张 + 任意一张都胡"无法在此口径下判定，故恒填 False 占位；
    调用方（engine/test）应使用 any_tile_win(摸牌前 13 张, meld_set_count)
    判定后以 dataclasses.replace 覆盖该字段。
    """

    _validate_melds(meld_set_count)
    counts34 = counts_from_tiles(hand_tiles)
    # 先执行原公共校验和原计数；未知/子类输入不新增访问或拒绝。
    # 原计数的0初始化与逐牌+1证明结果为0..14的内建整数，不逐34项重扫。
    if (
        _builtin_type(hand_tiles) is _builtin_tuple
        and _builtin_len(hand_tiles) <= 14
        and _builtin_type(meld_set_count) is _builtin_int
        and 0 <= meld_set_count <= 4
        and _builtin_type(counts34) is _builtin_tuple
        and _win_split_cache_dependencies_unchanged()
    ):
        result = _win_split_counts_cached(counts34, meld_set_count)
        if result is None:
            return None
        # 缓存不把结果对象借给调用方；每次仍是原WinSplit类型的新实例。
        return WinSplit(result.branch, result.luxury_pairs, result.whites_held,
                        result.any_tile_tenpai, result.evidence)
    return _win_split_counts(counts34, meld_set_count)


def _win_split_counts(counts34: Counts34, meld_set_count: int) -> Optional[WinSplit]:
    """已构造计数的原分解主体；顺序、七对优先和全部证据逐句保持。

    仅由先完成原副露校验、原牌值计数的入口调用。研究装配可在此
    复用同计数结果，不缓存输入校验、不混用不同副露数。
    """

    counts, whites = _split_counts(counts34)

    if meld_set_count == 0:
        if _chiitoi_pairs(counts, whites) == 7:
            singles = [i for i, value in enumerate(counts) if value % 2 == 1]
            # 豪华只数自然四张：三张同牌加白可补成两个对子，不能算豪华。
            # v23：补落单的白板已参与其他对子，不能再把四真白重复计豪华。
            luxury = sum(1 for value in counts if value == 4) + (
                1 if whites == 4 and not singles else 0
            )
            pair_labels: list = []
            for i, value in enumerate(counts):
                # 每两张自然牌一对；四张同牌即两对（其中一对计入豪华）。
                for _ in range(value // 2):
                    pair_labels.append(_block_label("对", (TILE_ORDER[i],) * 2))
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

    【官方】v23 指南 1.2 / RULES_EVIDENCE §5（2026-09-08 核验）：
    静态爆头按本判定，四白同样适用；已有爆头的连续动作状态由调用方处理。
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


def qualify_seven_pairs_baotou(
    win: WinSplit, pre_draw_hand: Tuple[Tile, ...], meld_set_count: int,
) -> WinSplit:
    """补充当前七对分支的爆头支付资格；不修改全局爆头旗或合法动作。

    官方 v35、2026-10-06 纯计算器同14张不同draw对照（SYN01/SYN02）
    确认：平胡任意听产生的全局 baotou 不给非任意听七对再乘2。
    输入必须是准确摸前13张，不能从最终14张任意移除一张来猜测。
    七对的白板先补自然落单；任意新增自然牌的最坏情形是新增落单，
    因此白板数必须大于自然奇数张种类数。13张最多占13种牌，必有
    未持有种类，此最坏情形确实存在；满足它也覆盖摸白与补已有单张。
    这是 _chiitoi_pairs 的闭式任意听条件，只扫一次计数，不重复34次分解。
    """

    _validate_melds(meld_set_count)
    if win.branch != _BRANCH_CHIITOI:
        return win
    if meld_set_count != 0 or len(pre_draw_hand) != 13:
        raise ValueError("七对爆头支付资格需要无副露的准确摸前13张手牌")
    counts34 = counts_from_tiles(pre_draw_hand)
    if any(value > 4 for value in counts34):
        raise ValueError("七对爆头支付资格的摸前手牌不能含第五张同种牌")
    counts, whites = _split_counts(counts34)
    eligible = whites > sum(value % 2 for value in counts)
    return replace(win, seven_pairs_baotou=eligible)


# 仅完整确定性分解复用：每解释器最多1024条，不缓存布尔判胡或递归后缀。
# 内建LRU不存异常；值/键只含本手牌计数与副露数，不含座位、世界或时间。
_WIN_SPLIT_CACHE_LIMIT = 1024
_win_split_counts_cached = lru_cache(maxsize=_WIN_SPLIT_CACHE_LIMIT, typed=True)(_win_split_counts)
_WIN_SPLIT_NAMESPACE = globals()
_WIN_SPLIT_BUILTINS = win_split.__builtins__
_WIN_SPLIT_COUNT_GLOBALS = _COUNTS_FROM_TILES_CANONICAL_FUNCTION.__globals__
_WIN_SPLIT_COUNT_BUILTINS = _COUNTS_FROM_TILES_CANONICAL_FUNCTION.__builtins__
_WIN_SPLIT_FUNCTION_NAMES = (
    "_need_std", "_chiitoi_pairs", "_split_counts", "_dec", "_block_label",
    "_split_std_evidence", "_validate_melds", "_win_split_counts",
)
_WIN_SPLIT_VALUE_NAMES = (
    "TILE_ORDER", "WinSplit", "_BRANCH_PLAIN", "_BRANCH_CHIITOI",
    # 只绑定原数学主体实际使用的builtin；不扫描全部模块或计数元素。
    "sum", "min", "max", "range", "enumerate", "tuple", "list", "sorted",
)


def _win_split_global(name):
    if name in _WIN_SPLIT_NAMESPACE:
        return _WIN_SPLIT_NAMESPACE[name]
    return _WIN_SPLIT_BUILTINS.get(name)


def _win_split_code(value):
    return value.__code__ if _builtin_type(value) is FunctionType else None


_WIN_SPLIT_FUNCTION_DEPENDENCIES = tuple(
    (name, _win_split_global(name), _win_split_code(_win_split_global(name)))
    for name in _WIN_SPLIT_FUNCTION_NAMES
)
_WIN_SPLIT_VALUE_DEPENDENCIES = tuple(
    (name, _win_split_global(name)) for name in _WIN_SPLIT_VALUE_NAMES
)
_WIN_SPLIT_RESULT_TYPE = WinSplit
_WIN_SPLIT_RESULT_METHODS = tuple(
    (name, getattr(WinSplit, name), _win_split_code(getattr(WinSplit, name)))
    for name in ("__new__", "__init__", "__getattribute__")
)


def _win_split_cache_dependencies_unchanged():
    """只认可原同源依赖；热漂移原算，不为未知替代函数重新授缓存证明。"""

    if (counts_from_tiles is not _COUNTS_FROM_TILES_CANONICAL_FUNCTION
            or counts_from_tiles.__code__ is not _COUNTS_FROM_TILES_CANONICAL_CODE):
        return False
    # counts_from_tiles的tuple是另一模块实际解析的全局/builtin绑定。
    # builtins字典可原地改写，不能只捕获字典对象后跳过逐次值校验。
    constructor = (
        _WIN_SPLIT_COUNT_GLOBALS["tuple"] if "tuple" in _WIN_SPLIT_COUNT_GLOBALS
        else _WIN_SPLIT_COUNT_BUILTINS.get("tuple")
    )
    if constructor is not _builtin_tuple:
        return False
    for name, expected, code in _WIN_SPLIT_FUNCTION_DEPENDENCIES:
        current = _win_split_global(name)
        if current is not expected or _win_split_code(current) is not code:
            return False
    for name, expected in _WIN_SPLIT_VALUE_DEPENDENCIES:
        if _win_split_global(name) is not expected:
            return False
    for name, expected, code in _WIN_SPLIT_RESULT_METHODS:
        current = getattr(_WIN_SPLIT_RESULT_TYPE, name)
        if current is not expected or _win_split_code(current) is not code:
            return False
    return True


# 仅提供原数学缓存的回归/诊断属性；choose与规则受控接口不增加参数。
# clear后释放全部键/值，进程/解释器退出同样回收；调用不读文件或时钟。
win_split.cache_info = _win_split_counts_cached.cache_info
win_split.cache_clear = _win_split_counts_cached.cache_clear
