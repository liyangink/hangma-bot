"""策略侧确定性手牌结构估计（仅用于候选排序）。

边界声明（对应根 AGENTS.md 模块边界）：hangma 规则模块是向听、
有效牌等规则概念的唯一权威来源；本文件提供的同名估计值只是
策略内部的排序偏好信号——不用于合法性判断、胡牌判定或提交前
复核，也不得被其他模块当作规则结果消费。已知局限与采用的
工程假设在函数级注释中标明；长期正确路径是由总体架构评审后
让规则分析经受控契约直接提供这些信号，而不是本估计器。

估计器不访问网络、文件或时钟；全部计算确定性。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Tuple

# 数牌花色顺序与官方牌码一致：b=筒、t=条、w=万；1-9 为序数。
NUMERIC_SUITS: Tuple[str, str, str] = ("b", "t", "w")
# 字牌固定顺序，仅用于稳定枚举与排序，不承载规则含义。
HONOR_CODES: Tuple[str, ...] = ("东", "南", "西", "北", "中", "发", "白")

# 全部 34 种牌码的稳定枚举顺序（数牌按花色分组、字牌殿后）。
ALL_CODES: Tuple[str, ...] = tuple(
    "{rank}{suit}".format(rank=rank, suit=suit)
    for suit in NUMERIC_SUITS
    for rank in range(1, 10)
) + HONOR_CODES


def _is_numeric(code: str) -> bool:
    """判断牌码是否为数牌；仅接受形如 1b-9w 的两位编码。"""

    return len(code) == 2 and code[1] in NUMERIC_SUITS and code[0] in "123456789"


def tile_sort_key(code: str) -> Tuple[int, int, str]:
    """返回稳定排序键：数牌按花色+序数在前，字牌按固定顺序在后。"""

    if _is_numeric(code):
        return (0, NUMERIC_SUITS.index(code[1]) * 10 + int(code[0]), code)
    if code in HONOR_CODES:
        return (1, HONOR_CODES.index(code), code)
    return (2, 0, code)


@dataclass(frozen=True)
class HandEstimate:
    """一手牌（或动作后余牌）的结构估计；全部字段为确定性计算结果。

    信息权限：只依赖本人手牌与公开可见牌，不含他家手牌推测。
    """

    shanten: int  # 向听估计（0 表示听牌，越大越远离胡牌；截断后不为负）
    flexibility: int  # 搭子数 + 有靠张的孤张数，衡量手牌灵活度
    wildcard_count: int  # 手中财神（万能牌）张数
    set_count: int  # 分解出的完整面子数（含财神升级）
    partial_count: int  # 分解出的搭子/对子数（含财神折算）
    summary: str  # 中文结构摘要，用于审计原因


@dataclass(frozen=True)
class _Decomposition:
    """手牌贪心分解结果；只在本文件内部使用。"""

    set_count: int
    partial_codes: Tuple[Tuple[str, str], ...]  # 每个搭子用两个牌码表示
    pair_count: int  # 其中对子搭子的数量
    isolate_codes: Tuple[str, ...]


def _score_decomposition(result: _Decomposition) -> Tuple[int, int, int]:
    """分解质量键：(2*面子+搭子+对子加成, 面子数, 搭子数)；确定性比较用。"""

    return (
        2 * result.set_count + len(result.partial_codes) + result.pair_count,
        result.set_count,
        len(result.partial_codes),
    )


def _decompose_numeric(
    counts: List[int], suit: str, descending: bool, pairs_first: bool
) -> _Decomposition:
    """对一个花色的序数牌做确定性贪心分解。

    两个变体维度：顺子抽取方向（升/降）与对子抽取时机
    （对子优先 / 搭子优先）。四个全局变体由调用方逐一评分取最优，
    弥补单一贪心在顺子重叠（4t6t 与 6t7t8t）与拆对成双搭子
    （3b3b4b 优先作 13b+34b）上的盲区。这是排序启发式，
    不追求与规则模块的最优分解完全一致。
    """

    sets = 0
    partials: List[Tuple[str, str]] = []
    pairs = 0
    isolates: List[str] = []
    work = list(counts)
    ranks = range(1, 10)

    for rank in ranks:
        if work[rank] >= 3:
            sets += 1
            work[rank] -= 3
    run_starts = range(1, 8) if not descending else range(7, 0, -1)
    for rank in run_starts:
        while work[rank] > 0 and work[rank + 1] > 0 and work[rank + 2] > 0:
            sets += 1
            work[rank] -= 1
            work[rank + 1] -= 1
            work[rank + 2] -= 1

    def extract_pairs() -> None:
        nonlocal pairs
        for rank in ranks:
            if work[rank] == 2:
                code = "{rank}{suit}".format(rank=rank, suit=suit)
                partials.append((code, code))
                pairs += 1
                work[rank] = 0

    def extract_adjacent() -> None:
        for rank in range(1, 9):
            while work[rank] > 0 and work[rank + 1] > 0:
                low = "{rank}{suit}".format(rank=rank, suit=suit)
                high = "{next}{suit}".format(next=rank + 1, suit=suit)
                partials.append((low, high))
                work[rank] -= 1
                work[rank + 1] -= 1

    def extract_gaps() -> None:
        for rank in range(1, 8):
            while work[rank] > 0 and work[rank + 2] > 0 and work[rank + 1] == 0:
                low = "{rank}{suit}".format(rank=rank, suit=suit)
                high = "{next}{suit}".format(next=rank + 2, suit=suit)
                partials.append((low, high))
                work[rank] -= 1
                work[rank + 2] -= 1

    if pairs_first:
        extract_pairs()
        extract_adjacent()
        extract_gaps()
    else:
        extract_adjacent()
        extract_gaps()
        extract_pairs()
    for rank in ranks:
        if work[rank] == 1:
            isolates.append("{rank}{suit}".format(rank=rank, suit=suit))
            work[rank] = 0
    return _Decomposition(sets, tuple(partials), pairs, tuple(isolates))


# 四个确定性分解变体：(顺子降序?, 对子优先?)
_DECOMPOSE_VARIANTS = (
    (False, True),
    (True, True),
    (False, False),
    (True, False),
)


def _decompose(counts: Mapping[str, int], descending: bool, pairs_first: bool) -> _Decomposition:
    """按指定变体把手牌计数分解为面子、搭子和孤张；字牌只允许刻子与对子。"""

    total_sets = 0
    partials: List[Tuple[str, str]] = []
    pairs = 0
    isolates: List[str] = []

    for suit in NUMERIC_SUITS:
        per_suit = [0] * 10
        for rank in range(1, 10):
            per_suit[rank] = counts.get("{rank}{suit}".format(rank=rank, suit=suit), 0)
        result = _decompose_numeric(per_suit, suit, descending, pairs_first)
        total_sets += result.set_count
        partials.extend(result.partial_codes)
        pairs += result.pair_count
        isolates.extend(result.isolate_codes)

    for code in HONOR_CODES:
        count = counts.get(code, 0)
        total_sets += count // 3
        remainder = count % 3
        if remainder == 2:
            partials.append((code, code))
            pairs += 1
        elif remainder == 1:
            isolates.append(code)

    return _Decomposition(
        total_sets,
        tuple(partials),
        pairs,
        tuple(sorted(isolates, key=tile_sort_key)),
    )


def _isolate_adjacency(isolates: Tuple[str, ...], partials: Tuple[Tuple[str, str], ...]) -> int:
    """统计有靠张价值的孤张数：与任意搭子或同花色孤张距离不超过 2。"""

    if not isolates:
        return 0
    anchors: List[str] = []
    for pair in partials:
        anchors.extend(pair)
    anchors.extend(isolates)
    adjacent = 0
    for code in isolates:
        if not _is_numeric(code):
            continue
        rank = int(code[0])
        suit = code[1]
        for other in anchors:
            if other == code or not _is_numeric(other):
                continue
            if other[1] == suit and abs(int(other[0]) - rank) <= 2:
                adjacent += 1
                break
    return adjacent


def _raw_normal(
    decomposition: _Decomposition,
    meld_blocks: int,
    wildcard_count: int,
) -> Tuple[int, int, int]:
    """普通型原始向听（可为负，负值表示成牌或财神听牌态）。

    公式：raw = 2*needed - 2*S - k - e，其中 needed=4-副路面子数，
    S=手牌面子数，k=朝面子扩展的搭子数（上限 needed-S），e=1 当
    存在牌眼。同一对子不能同时充当牌眼与搭子（oracle 对拍发现的
    双重计数缺陷），因此按两个方案取优：
    方案一：用对子或财神作牌眼，该对子退出搭子池；
    方案二：不设牌眼，全部搭子（含对子、财神）冲面子。
    财神使用顺序：先把两面搭子升级为面子，再保留牌眼，余量作搭子。
    """

    needed_sets = max(0, 4 - meld_blocks)
    sets = decomposition.set_count
    proto_partials = [pair for pair in decomposition.partial_codes if pair[0] != pair[1]]
    pair_partials = [pair for pair in decomposition.partial_codes if pair[0] == pair[1]]
    if sets > needed_sets:
        # 多余完整面子按对子搭子折算，避免高估。
        surplus = sets - needed_sets
        sets -= surplus
        pair_partials.extend([("折算", "折算")] * surplus)

    remaining_wildcards = wildcard_count
    # 财神优先把两面搭子升级为面子（对子留给牌眼）。
    while remaining_wildcards > 0 and proto_partials and sets < needed_sets:
        proto_partials.pop(0)
        sets += 1
        remaining_wildcards -= 1
    # 对子富余（多于一个）时才用财神升级对子为面子。
    while remaining_wildcards > 0 and len(pair_partials) > 1 and sets < needed_sets:
        pair_partials.pop()
        sets += 1
        remaining_wildcards -= 1

    proto_count = len(proto_partials)
    pair_count = len(pair_partials)
    room = max(0, needed_sets - sets)

    # 方案一：牌眼来自对子或财神，来源退出搭子池。
    candidates = []
    if pair_count >= 1:
        blocks = min(proto_count + pair_count - 1 + remaining_wildcards, room)
        candidates.append(2 * needed_sets - 2 * sets - blocks - 1)
    elif remaining_wildcards >= 1:
        blocks = min(proto_count + remaining_wildcards - 1, room)
        candidates.append(2 * needed_sets - 2 * sets - blocks - 1)
    # 方案二：不设牌眼，全部搭子（含对子与财神）冲面子。
    blocks = min(proto_count + pair_count + remaining_wildcards, room)
    candidates.append(2 * needed_sets - 2 * sets - blocks)

    raw = min(candidates)
    partial_total = proto_count + pair_count + remaining_wildcards
    return raw, sets, partial_total


def _raw_chiitoi(counts: Mapping[str, int], wildcard_count: int) -> int:
    """七对型原始向听：6 - 有效对子数。

    四张同牌计两对（豪华七对）：官方指南 v8 快照（检查日期 2026-09-03，
    doc/references/official-guide-version-v8.json「七对×2×2^豪华组数」
    「七对形爆头听牌（如 3 组四张 + 1 白）」）确认豪华组语义；
    财神可与任一单张组成对子；不要求七种互异牌码。
    """

    pair_count = 0
    singles = 0
    for count in counts.values():
        pair_count += count // 2
        singles += count % 2
    pair_count += min(wildcard_count, singles)
    return 6 - pair_count


def estimate_raw(
    hand: Tuple[str, ...],
    meld_blocks: int,
    wealth_code: str,
) -> int:
    """返回未截断的向听估计（可为负）；专供有效牌判定使用。

    四个贪心分解变体逐一用 raw 公式评分取最优；估计值只会
    不低于真值（贪心是精确搜索的子集），oracle 对拍测试钉住偏差为零。
    """

    counts: Dict[str, int] = {}
    for code in hand:
        counts[code] = counts.get(code, 0) + 1
    wildcard_count = counts.pop(wealth_code, 0)

    best: Optional[int] = None
    for descending, pairs_first in _DECOMPOSE_VARIANTS:
        decomposition = _decompose(counts, descending, pairs_first)
        raw, _, _ = _raw_normal(decomposition, meld_blocks, wildcard_count)
        if best is None or raw < best:
            best = raw
    if meld_blocks == 0:
        best = min(best, _raw_chiitoi(counts, wildcard_count))
    assert best is not None
    return best


def estimate_hand(
    hand: Tuple[str, ...],
    meld_blocks: int,
    wealth_code: str,
) -> HandEstimate:
    """估计一手牌的结构；hand 为牌码元组，meld_blocks 为已副露面子数。

    补杠不增加面子数（碰升级为杠仍是 1 个面子），由调用方保证。
    与 estimate_raw 同样按四变体取 raw 最优，摘要取最优变体的分解。
    """

    counts: Dict[str, int] = {}
    for code in hand:
        counts[code] = counts.get(code, 0) + 1
    wildcard_count = counts.pop(wealth_code, 0)

    best: Optional[Tuple[int, _Decomposition, int, int]] = None
    for descending, pairs_first in _DECOMPOSE_VARIANTS:
        decomposition = _decompose(counts, descending, pairs_first)
        raw, sets, partials = _raw_normal(decomposition, meld_blocks, wildcard_count)
        if best is None or raw < best[0]:
            best = (raw, decomposition, sets, partials)
    raw, decomposition, sets, partials = best
    if meld_blocks == 0:
        chiitoi = _raw_chiitoi(counts, wildcard_count)
        if chiitoi < raw:
            raw = chiitoi
    shanten = max(0, raw)

    flexibility = partials + _isolate_adjacency(decomposition.isolate_codes, decomposition.partial_codes)
    summary = (
        "面子{sets}组、搭子{partials}组、孤张{isolates}张、财神{wildcards}张，向听估计{shanten}".format(
            sets=sets,
            partials=partials,
            isolates=len(decomposition.isolate_codes),
            wildcards=wildcard_count,
            shanten=shanten,
        )
    )
    return HandEstimate(
        shanten=shanten,
        flexibility=flexibility,
        wildcard_count=wildcard_count,
        set_count=sets,
        partial_count=partials,
        summary=summary,
    )


def effective_tiles(
    hand: Tuple[str, ...],
    meld_blocks: int,
    wealth_code: str,
    remaining_by_code: Mapping[str, int],
) -> Tuple[int, float, Tuple[str, ...]]:
    """计算能降低向听估计的有效牌：返回 (牌种数, 加权张数, 样例)。

    remaining_by_code 是按可见牌扣除后每种牌的剩余张数（上限 4）。
    财神在手的听牌态（含财神牌眼/财神搭子）按工程近似处理为
    “任意可摸牌都有效”：财神可与任意摸牌组成面子或牌眼，
    raw 增量在此形态下无法表达该事实。
    """

    counts: Dict[str, int] = {}
    for code in hand:
        counts[code] = counts.get(code, 0) + 1
    wildcard_count = counts.pop(wealth_code, 0)
    base = estimate_raw(hand, meld_blocks, wealth_code)

    all_effective = base < 0 or (base == 0 and wildcard_count > 0)
    kinds = 0
    weight = 0.0
    samples: List[str] = []
    for code in ALL_CODES:
        remaining = remaining_by_code.get(code, 0)
        if remaining <= 0:
            continue
        effective = all_effective
        if not effective:
            candidate = hand + (code,)
            effective = estimate_raw(candidate, meld_blocks, wealth_code) < base
        if effective:
            kinds += 1
            weight += remaining
            if len(samples) < 3:
                samples.append(code)
    return kinds, weight, tuple(samples)
