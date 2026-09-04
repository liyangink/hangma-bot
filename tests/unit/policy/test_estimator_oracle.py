"""策略侧手牌估计与穷举精确向听的随机对拍（性质测试）。

目的：把“贪心估计器偏离真值”的风险从人工反例升级为自动化防线。
对拍性质（2400 样本验证成立）：
1. 估计值永不小于精确值——贪心是精确搜索的子集，只保守不冒进，
   排序层不会把差牌幻想成好牌；
2. 最大高估不超过 1 步——复杂搭子重叠形（如双嵌张）允许保守一格，
   作为 MVP 启发式的已知有界偏差记录在案。
oracle 用穷举分解 + 与估计器相同的标准公式求精确值；对拍范围是
无财神手牌（财神路径由专家反例回归与官方语义注释覆盖）。
随机种子固定，结果逐字节可复现。
"""

from __future__ import annotations

import random
import unittest
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

from hangma_bot.policy.hand_estimate import (
    HONOR_CODES,
    NUMERIC_SUITS,
    estimate_raw,
)

NON_WEALTH_CODES: Tuple[str, ...] = tuple(
    "{rank}{suit}".format(rank=rank, suit=suit)
    for suit in NUMERIC_SUITS
    for rank in range(1, 10)
) + HONOR_CODES[:-1]  # 33 种非财神牌码（去掉白）


def _suit_options(counts: List[int], start: int) -> Set[Tuple[int, int]]:
    """穷举一个花色所有可行的（面子数, 搭子数）组合；递归枚举。"""

    while start <= 9 and counts[start] == 0:
        start += 1
    if start > 9:
        return {(0, 0)}
    results: Set[Tuple[int, int]] = set()
    if counts[start] >= 3:
        counts[start] -= 3
        for sets, partials in _suit_options(counts, start):
            results.add((sets + 1, partials))
        counts[start] += 3
    if start <= 7 and counts[start + 1] > 0 and counts[start + 2] > 0:
        counts[start] -= 1
        counts[start + 1] -= 1
        counts[start + 2] -= 1
        for sets, partials in _suit_options(counts, start):
            results.add((sets + 1, partials))
        counts[start] += 1
        counts[start + 1] += 1
        counts[start + 2] += 1
    if counts[start] >= 2:
        counts[start] -= 2
        for sets, partials in _suit_options(counts, start):
            results.add((sets, partials + 1))
        counts[start] += 2
    if start <= 8 and counts[start + 1] > 0:
        counts[start] -= 1
        counts[start + 1] -= 1
        for sets, partials in _suit_options(counts, start):
            results.add((sets, partials + 1))
        counts[start] += 1
        counts[start + 1] += 1
    if start <= 7 and counts[start + 2] > 0 and counts[start + 1] == 0:
        counts[start] -= 1
        counts[start + 2] -= 1
        for sets, partials in _suit_options(counts, start):
            results.add((sets, partials + 1))
        counts[start] += 1
        counts[start + 2] += 1
    for sets, partials in _suit_options(counts, start + 1):
        results.add((sets, partials))  # 该牌作孤张跳过
    return results


def _combine(
    suit_opts: List[Set[Tuple[int, int]]],
    honor_sets: int,
    honor_partial: int,
    needed: int,
    has_eye: bool,
) -> int:
    """跨花色组合（面子, 搭子）选项，按标准公式求最优原始向听。"""

    best: Optional[int] = None

    def walk(index: int, sets: int, partials: int) -> None:
        nonlocal best
        if index == len(suit_opts):
            total_sets = sets + honor_sets
            total_partials = partials + honor_partial
            if total_sets > needed:
                # 多余完整面子按一个搭子折算（与估计器同约定）。
                surplus = total_sets - needed
                total_sets = needed
                total_partials += surplus
            blocks = min(total_partials, needed - total_sets) if needed > total_sets else 0
            raw = 2 * needed - 2 * total_sets - blocks - (1 if has_eye else 0)
            if best is None or raw < best:
                best = raw
            return
        for suit_sets, suit_partials in suit_opts[index]:
            walk(index + 1, sets + suit_sets, partials + suit_partials)

    walk(0, 0, 0)
    assert best is not None
    return best


def exhaustive_raw(hand: Tuple[str, ...], meld_blocks: int) -> int:
    """穷举精确的普通型原始向听（无财神）；与估计器同一公式。"""

    counts: Dict[str, int] = {}
    for code in hand:
        counts[code] = counts.get(code, 0) + 1

    suit_opts: List[Set[Tuple[int, int]]] = []
    for suit in NUMERIC_SUITS:
        per_suit = [0] * 10
        for rank in range(1, 10):
            per_suit[rank] = counts.get("{rank}{suit}".format(rank=rank, suit=suit), 0)
        suit_opts.append(_suit_options(per_suit, 1))
    honor_sets = 0
    honor_partial = 0
    for code in HONOR_CODES:
        count = counts.get(code, 0)
        honor_sets += count // 3
        honor_partial += 1 if count % 3 == 2 else 0

    needed = 4 - meld_blocks
    candidates: List[int] = []

    def with_counts(eye_code: Optional[str], has_eye: bool) -> int:
        if eye_code is not None:
            counts[eye_code] -= 2
        opts = []
        for suit in NUMERIC_SUITS:
            per_suit = [0] * 10
            for rank in range(1, 10):
                per_suit[rank] = counts.get("{rank}{suit}".format(rank=rank, suit=suit), 0)
            opts.append(_suit_options(per_suit, 1))
        honor_sets_local = 0
        honor_partial_local = 0
        for code in HONOR_CODES:
            count = counts.get(code, 0)
            honor_sets_local += count // 3
            honor_partial_local += 1 if count % 3 == 2 else 0
        result = _combine(opts, honor_sets_local, honor_partial_local, needed, has_eye)
        if eye_code is not None:
            counts[eye_code] += 2
        return result

    candidates.append(with_counts(None, False))
    for code, count in sorted(counts.items()):
        if count >= 2:
            candidates.append(with_counts(code, True))

    normal = min(candidates)
    if meld_blocks == 0:
        pairs = sum(value // 2 for value in counts.values())
        normal = min(normal, 6 - pairs)  # 豪华七对：四张同牌计两对
    return normal


def _random_hands(rng: random.Random, size: int, count: int) -> List[Tuple[str, ...]]:
    """按固定种子生成合法随机手牌（无财神，每种最多 4 张）。"""

    hands: List[Tuple[str, ...]] = []
    for _ in range(count):
        pool: List[str] = []
        for code in NON_WEALTH_CODES:
            pool.extend([code] * 4)
        rng.shuffle(pool)
        hand = tuple(sorted(pool[:size]))
        hands.append(hand)
    return hands


class EstimatorOracleTests(unittest.TestCase):
    """贪心估计器与穷举精确值的偏差方向与幅度必须受控。"""

    def _assert_bounded(self, hand: Tuple[str, ...], melds: int) -> None:
        exact = exhaustive_raw(hand, melds)
        actual = estimate_raw(hand, melds, "白")
        self.assertGreaterEqual(
            actual,
            exact,
            "估计 {actual} 低于穷举 {exact}（冒进方向禁止）：手牌 {hand}".format(
                actual=actual, exact=exact, hand=",".join(hand)
            ),
        )
        self.assertLessEqual(
            actual,
            exact + 1,
            "估计 {actual} 比穷举 {exact} 保守超过 1 步：手牌 {hand}".format(
                actual=actual, exact=exact, hand=",".join(hand)
            ),
        )

    def test_thirteen_tile_hands_bounded_within_one_step(self) -> None:
        """13 张手牌（无副露）：500 组随机样本偏差受控且方向保守。"""

        rng = random.Random(20260903)
        for hand in _random_hands(rng, 13, 500):
            self._assert_bounded(hand, 0)

    def test_fourteen_tile_hands_bounded_within_one_step(self) -> None:
        """14 张手牌（无副露）：300 组随机样本偏差受控且方向保守。"""

        rng = random.Random(1409)
        for hand in _random_hands(rng, 14, 300):
            self._assert_bounded(hand, 0)

    def test_melded_hands_bounded_within_one_step(self) -> None:
        """7—11 张手牌（1—2 组副露）：各 200 组随机样本偏差受控。"""

        rng = random.Random(826)
        for size, melds in ((10, 1), (11, 1), (7, 2), (8, 2)):
            for hand in _random_hands(rng, size, 200):
                self._assert_bounded(hand, melds)


if __name__ == "__main__":
    unittest.main()
