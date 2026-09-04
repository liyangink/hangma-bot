"""杭麻手牌数学：胡牌判定、向听数、有效牌、任意听与确定性分解。

本文件属于「手牌数学」子模块，是通用牌型分解的唯一实现：action_families /
special_rules / settlement 复用本文件产出的 HandSummary / WinSplit，
不得另建第二套分解。全部函数为纯函数：只依赖 kernel 值对象与
internal_types 内部契约，不访问网络、文件、时钟、随机源或应用状态。

核心算法（前任原型验证过的骨架）：把暗牌转成 34 维计数向量后，
白板（财神）单独抽出作为可任意垫牌的资源；标准型按
「枚举将 → 取最低非空位 i → 刻子 / 顺子窗口 s∈{i-2,i-1,i} / 纯白刻」
递归分解。白可垫顺子任意位置（含起始位，如 白+8w+9w=789w）、
可垫刻子、可作将眼；白白可自将对、白白白可自刻；4 白在手可胡。

向听口径：need = 凑成完整牌型还差的张数（白垫计 0、虚牌计 1），
未胡 shanten = need - 1（0=听牌），已胡 shanten = -1；该恒等式对
13/14 张暗牌与任意副露折算统一成立（多余暗牌视为可弃）。
虚牌施加每种 4 张上限（手牌原计数 + 该种虚牌 ≤ 4），杜绝
"第 5 张东"式不可能进张把向听算低（评审回归例 123w456w789w+东×4）。

缓存：_need_std 使用有界 lru_cache——单 Token 长驻进程跑整赛事时，
无界缓存的实测增长约 1300 条/手（GB 级风险）；有界化后偶发冷算
（毫秒级）不影响动作窗口预算。

规则依据与证据级别：RULES_EVIDENCE.md §1/§2/§5
（官方指南 v9，2026-09-03 抓取；金例夹具 tests/fixtures/official/v9）。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional, Tuple

from hangma_bot.kernel.actions import Tile

from .internal_types import (
    TILE_ORDER,
    WEALTH_CODE,
    Counts34,
    HandSummary,
    UsefulTile,
    WinSplit,
    counts_from_tiles,
)

_INF = 99  # 哨兵上界：单手牌型 need 不可能超过 8

_BRANCH_PLAIN = "平胡"
_BRANCH_CHIITOI = "七对"
_WHITE_CODE = WEALTH_CODE


def _dec(counts: Tuple[int, ...], index: int, n: int) -> Tuple[int, ...]:
    """返回 counts[index] 减少 n 后的新元组（计数向量的不可变更新）。"""

    return counts[:index] + (counts[index] - n,) + counts[index + 1 :]


def _phantom_budget(counts: Tuple[int, ...]) -> Tuple[Tuple[int, int], ...]:
    """紧凑虚牌配额：只编码手牌原计数 ≥3 的种类（配额 4-计数 ≤ 1）。

    虚牌（假想进张）不能突破每种 4 张的物理上限。原计数 ≤2 的种类
    不进键：其同种虚牌用量在最小分解中不可能触顶（同种"虚对+虚刻"
    的 5 张组合恒被等价或更廉价的异种/自然/纯白方案取代，最小值不
    变），因此省略它们不损失精确性，却让键跨手牌稳定——评审
    d8-f4dadf：全维 33 元组键使跨手牌缓存全失效，长驻进程每手冷算
    p50≈100ms；紧凑键恢复毫秒级。
    """

    return tuple((i, 4 - c) for i, c in enumerate(counts) if c >= 3)


_BUDGET_FREE = 4  # 未编码种类的等效配额（恒不构成约束）


def _budget_left(budget: Tuple[Tuple[int, int], ...], index: int) -> int:
    """查询某牌种的剩余虚牌配额；未编码种类视为不受限。"""

    for i, value in budget:
        if i == index:
            return value
    return _BUDGET_FREE


def _budget_dec(
    budget: Tuple[Tuple[int, int], ...], index: int, n: int
) -> Tuple[Tuple[int, int], ...]:
    """扣减某牌种配额并保持元组紧凑（归零剔除；未编码种类不变）。"""

    entries = []
    for i, value in budget:
        if i == index:
            value -= n
            if value > 0:
                entries.append((i, value))
        else:
            entries.append((i, value))
    return tuple(entries)


@lru_cache(maxsize=65536)
def _need_std(
    counts: Tuple[int, ...],
    whites: int,
    sets_left: int,
    pair_needed: bool,
    budget: Tuple[Tuple[int, int], ...],
) -> int:
    """标准型最小成胡差距：还需多少张牌（白垫计 0、虚牌计 1）。

    缓存上界：lru_cache(maxsize=65536)——纯函数淘汰不损正确性；无界
    缓存实测 500 个随机手牌累积 65 万条目（评审 d4-4f5bf9），长驻单
    Token 进程有内存风险；上界后单局命中率不受影响。

    分解枚举（正确性关键，与向听恒等式 shanten=need-1 配合）：
    - 状态 (counts, whites, sets_left, pair_needed, budget)；counts 为
      33 维自然牌计数（白板抽出），whites 为白板池，budget 为紧凑
      编码的剩余虚牌配额（仅原计数 ≥3 的种类，见 _phantom_budget）；
    - 基态：面子与将都齐 → 0（剩余自然牌视为弃牌，不影响 need）；
    - 自然牌耗尽：剩余槽位（3/组面子 + 2/将）全部由白或虚牌填充
      （虚牌按"全新种类"计——手牌至多占 13 种，34 种牌下恒可分配
      满足 4 张上限），need = max(0, 槽位 - whites)；
    - 取最低非空位 i，枚举含 i 的块：将（自然对 / 自然+白 / 白白 /
      带虚牌变体）、刻子（自然优先、白垫补足）、顺子窗口 s∈{i-2,i-1,i}
      （空位白垫或虚牌——白可垫起始位是官方语义，最易错点）、
      纯白刻（白白白自刻）。消耗虚牌的分支必须校验并扣减 budget。
    """

    # 用 <= 0：将未定而面子已齐时，后续分支会继续把 sets_left 减为负数，
    # 此时只有将眼分支有意义（其余分支代价被自然抬高，不影响最优值）。
    if sets_left <= 0 and not pair_needed:
        return 0
    index = -1
    for i in range(33):
        if counts[i]:
            index = i
            break
    if index == -1:
        return max(0, 3 * sets_left + 2 * int(pair_needed) - whites)

    # 弃牌分支：need 按子集语义取最小。仅当该种虚牌配额为 0（在手
    # 满 4 张）时弃牌才可能占优——有配额的牌恒能以 ≤ 弃牌的代价并入
    # 某块（等价于替下一张虚牌，评审 d5-a0c5d8：东×4 手的将眼虚牌被
    # 堵死后须可弃掉余张）。限定触发条件避免子集枚举状态爆炸。
    # 残留近似：邻位四张耗尽导致顺子搭子全部受阻的极端牌型可能仍差
    # 一张，不进金例与实战牌谱范围。
    if _budget_left(budget, index) == 0:
        best = _need_std(
            _dec(counts, index, 1), whites, sets_left, pair_needed, budget
        )
    else:
        best = _INF

    if pair_needed:
        held = counts[index]
        # 将眼枚举：自然对 / 自然+白 / 白白，以及带虚牌的降级变体。
        if held >= 2:
            best = min(
                best,
                _need_std(
                    _dec(counts, index, 2), whites, sets_left, False, budget
                ),
            )
        if held >= 1 and whites >= 1:
            best = min(
                best,
                _need_std(
                    _dec(counts, index, 1), whites - 1, sets_left, False, budget
                ),
            )
        if held >= 1 and _budget_left(budget, index) >= 1:
            # 虚牌配对消耗该种 1 张配额（手牌原计数 + 1 虚牌 ≤ 4）。
            best = min(
                best,
                1 + _need_std(
                    _dec(counts, index, 1),
                    whites,
                    sets_left,
                    False,
                    _budget_dec(budget, index, 1),
                ),
            )
        if whites >= 2:
            best = min(
                best, _need_std(counts, whites - 2, sets_left, False, budget)
            )
        if whites >= 1:
            best = min(
                best, 1 + _need_std(counts, whites - 1, sets_left, False, budget)
            )
        # 纯虚牌将按"全新种类"计，不占现有种类配额。
        best = min(best, 2 + _need_std(counts, whites, sets_left, False, budget))
    if sets_left <= 0:
        # 面子已齐（或超发）：只剩将眼分支有意义，直接返回当前最优。
        return best
    # 刻子：自然张优先（自然牌永不吃亏），缺口由白垫 / 虚牌补。
    natural = min(counts[index], 3)
    pad_white = min(3 - natural, whites)
    phantom = 3 - natural - pad_white
    if phantom == 0 or _budget_left(budget, index) >= phantom:
        triplet_budget = (
            budget if phantom == 0 else _budget_dec(budget, index, phantom)
        )
        best = min(
            best,
            phantom
            + _need_std(
                _dec(counts, index, natural),
                whites - pad_white,
                sets_left - 1,
                pair_needed,
                triplet_budget,
            ),
        )
    # 纯白刻：白白白可自刻（不消耗自然牌，面子数减一保证递归前进）。
    white_trip = min(3, whites)
    best = min(
        best,
        (3 - white_trip)
        + _need_std(
            counts, whites - white_trip, sets_left - 1, pair_needed, budget
        ),
    )
    # 顺子窗口：s∈{i-2,i-1,i} 且同花色 1-9 内；空位白垫——含起始位垫白
    # （纯 8w9w + 白 = 789w 合法，官方指南 1.2 爆头反例锚点）。
    if index < 27:
        suit_start = (index // 9) * 9
        for start in range(max(index - 2, suit_start), min(index, suit_start + 6) + 1):
            remaining = list(counts)
            missing = 0
            for pos in (start, start + 1, start + 2):
                if remaining[pos]:
                    remaining[pos] -= 1
                else:
                    missing += 1
            fill_white = min(missing, whites)
            phantoms_needed = missing - fill_white
            # 白优先垫无配额位；虚牌位需该种配额 ≥1（确定性按窗口序）。
            # 未编码种类的扣减为空操作（_budget_dec），其配额恒不约束。
            whites_avail = fill_white
            phantom_slots: list = []
            feasible = True
            for pos in (start, start + 1, start + 2):
                if counts[pos]:
                    continue
                if _budget_left(budget, pos) == 0:
                    if whites_avail > 0:
                        whites_avail -= 1
                    else:
                        feasible = False
                        break
                else:
                    phantom_slots.append(pos)
            if feasible and len(phantom_slots) >= phantoms_needed:
                run_budget = budget
                for pos in phantom_slots[:phantoms_needed]:
                    run_budget = _budget_dec(run_budget, pos, 1)
                best = min(
                    best,
                    phantoms_needed
                    + _need_std(
                        tuple(remaining),
                        whites - fill_white,
                        sets_left - 1,
                        pair_needed,
                        run_budget,
                    ),
                )
    return best


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
        _need_std(counts, whites, 4 - meld_set_count, True, _phantom_budget(counts))
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
    4 张上限约束（见 _phantom_budget），有效牌不含不可能摸到的第 5
    张同种牌。
    """

    _validate_melds(meld_set_count)
    counts34 = counts_from_tiles(hand_tiles)
    counts, whites = _split_counts(counts34)
    sets_needed = 4 - meld_set_count
    budget = _phantom_budget(counts)

    standard_shanten = _need_std(counts, whites, sets_needed, True, budget) - 1
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
                d_counts, d_whites, sets_needed, True, _phantom_budget(d_counts)
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

    与 _need_std 同一分支骨架，但返回块描述而非代价；未胡返回 None。
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
        _need_std(counts, whites, 4 - meld_set_count, True, _phantom_budget(counts))
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
