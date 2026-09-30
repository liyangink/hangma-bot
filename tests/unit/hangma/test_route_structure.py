"""用途结构距离的守恒金例及独立目标枚举，不调用待测距离作 oracle。"""

from dataclasses import FrozenInstanceError
from functools import lru_cache
from itertools import product
import json
from pathlib import Path
import random
import subprocess
import sys

import pytest

from hangma_bot.hangma.hand_analysis import analyse_counts_progress
from hangma_bot.hangma.route_structure import (
    ROUTE_STRUCTURE_SCHEMA_VERSION,
    analyze_route_structure,
)
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER


def counts(*codes):
    return tuple(codes.count(code) for code in CANONICAL_TILE_ORDER)


def target(facts, family, retained):
    return next(
        item for item in facts.targets
        if item.family == family and item.retained_whites == retained
    )


def _block_options(indices):
    """独立枚举单块各槽自然/白分配；保留白数和自然实体稀疏向量。"""

    found = set()
    for is_white in product((False, True), repeat=len(indices)):
        natural = [0] * 33
        for index, white in zip(indices, is_white):
            if not white:
                natural[index] += 1
        found.add((sum(is_white), tuple(natural)))
    return found


@lru_cache(maxsize=None)
def _one_set_targets(pair_needed, exact_whites):
    """穷举全 33 码一面子（可加将）目标，直接检查实体四张上限。"""

    sets = set()
    for index in range(33):
        sets.update(_block_options((index,) * 3))
    for suit in (0, 9, 18):
        for offset in range(7):
            start = suit + offset
            sets.update(_block_options((start, start + 1, start + 2)))
    pairs = {(0, (0,) * 33)}
    if pair_needed:
        pairs = set()
        for index in range(33):
            pairs.update(_block_options((index,) * 2))
    result = set()
    for set_whites, set_natural in sets:
        for pair_whites, pair_natural in pairs:
            if set_whites + pair_whites != exact_whites:
                continue
            combined = tuple(a + b for a, b in zip(set_natural, pair_natural))
            if max(combined) <= 4:
                result.add(tuple((i, value) for i, value in enumerate(combined) if value))
    return tuple(sorted(result))


def _enumerated_one_set_need(natural, pair_needed, exact_whites):
    """以目标实体向量计算缺口，与标准分组求解实现结构无关。"""

    return min(
        sum(max(value - natural[index], 0) for index, value in desired)
        for desired in _one_set_targets(pair_needed, exact_whites)
    )


def _enumerated_pairs_need(natural, pairs, exact_whites):
    """独立逐码目标枚举；每码0-4自然实体，奇数需一白，余白可自对。

    这里使用目标向量的动态规划，而待测实现使用已持自然对/单张的
    闭式槽位公式。最后恰用白；不调用 hand_analysis 或被测距离函数。
    """

    state = {(0, 0): 0}
    for held in natural:
        following = {}
        for (made_pairs, used_white), cost in state.items():
            for desired in range(5):
                next_pairs = made_pairs + (desired + 1) // 2
                next_white = used_white + desired % 2
                if next_pairs > pairs or next_white > exact_whites:
                    continue
                key = next_pairs, next_white
                value = cost + max(desired - held, 0)
                following[key] = min(value, following.get(key, 99))
        state = following
    return min(
        cost for (made_pairs, used_white), cost in state.items()
        if exact_whites - used_white == 2 * (pairs - made_pairs)
    )


def _random_waiting(rng, melds, whites):
    natural = [0] * 33
    for _ in range(13 - 3 * melds - whites):
        index = rng.choice([i for i, value in enumerate(natural) if value < 4])
        natural[index] += 1
    return tuple(natural) + (whites,)


def test_retained_white_example_and_zero_need_is_not_hu():
    facts = analyze_route_structure(
        counts(*"1w 2w 3w 1t 2t 3t 1b 2b 3b 7w 8w 白 白".split()), 0
    )
    one = target(facts, "standard", 1)
    two = target(facts, "standard", 2)
    complete = target(facts, "standard", 0)
    assert (one.white_used, one.target_natural_size, one.natural_need) == (1, 11, 0)
    assert one.requires_terminal_draw and one.target_stage == "waiting_predecessor"
    assert one.conditional_need_improvement_codes == ()
    assert one.witness is None and one.witness_status == "distance_only"
    assert (two.white_used, two.target_natural_size, two.natural_need) == (0, 12, 1)
    assert two.conditional_need_improvement_codes == ("6w", "9w")
    assert two.target_white_discard_lower_bound == 1
    assert two.target_natural_discard_lower_bound == 0
    assert complete.natural_need == 1 and not complete.requires_terminal_draw
    # D0前驱的推进空集合没有删除当次完成出口，且两种目标不会混为胡速度。
    assert len(complete.conditional_need_improvement_codes) == 33


def test_four_natural_pairs_three_singles_two_whites_are_not_hard_gated():
    hand = counts(*"1w 1w 3w 3w 5b 5b 7t 7t 东 南 西 白 白".split())
    facts = analyze_route_structure(hand, 0)
    assert facts.natural_pair_count == 4
    assert facts.seven_pairs_shanten == 0
    assert target(facts, "seven_pairs", 0).natural_need == 1
    assert target(facts, "seven_pairs", 1).natural_need == 1
    assert target(facts, "seven_pairs", 2).natural_need == 2
    assert target(facts, "seven_pairs", 0).conditional_need_improvement_codes == ("东", "南", "西")


def test_middle_single_has_more_standard_structural_progress_than_isolated_honor():
    middle = analyze_route_structure(counts("5w", "白", "白", "白"), 3)
    honor = analyze_route_structure(counts("东", "白", "白", "白"), 3)
    middle_target = target(middle, "standard", 3)
    honor_target = target(honor, "standard", 3)
    assert middle_target.natural_need == honor_target.natural_need == 2
    assert middle_target.conditional_need_improvement_codes == ("3w", "4w", "5w", "6w", "7w")
    assert honor_target.conditional_need_improvement_codes == ("东",)


def test_white_is_not_prebound_and_the_fifth_natural_entity_is_never_listed():
    hand = counts("东", "东", "东", "东")
    facts = analyze_route_structure(hand, 3)
    complete = target(facts, "standard", 0)
    assert complete.natural_need == 2  # 五张东不能作为刻子+将目标。
    assert "东" not in complete.conditional_need_improvement_codes
    assert complete.conditional_need_improvement_codes == tuple(code for code in CANONICAL_TILE_ORDER[:33] if code != "东")
    # 原权威回归中的四东并不把一白锁死为“补第五东”。
    white = analyze_route_structure(counts("1w", "2w", "东", "东", "东", "东", "白"), 2)
    assert white.standard_shanten == 0
    assert "3w" in target(white, "standard", 0).conditional_need_improvement_codes


def test_natural_quad_is_two_pairs_and_overlap_stays_as_labeled_sets():
    hand = counts(*"1w 1w 1w 1w 2w 2w 3w 3w 4w 4w 5w 5w 白".split())
    facts = analyze_route_structure(hand, 0)
    assert facts.natural_pair_count == 6
    assert facts.natural_quad_codes == ("1w",)
    assert target(facts, "seven_pairs", 1).natural_need == 0
    plain = set(target(facts, "standard", 0).conditional_need_improvement_codes)
    seven = set(target(facts, "seven_pairs", 0).conditional_need_improvement_codes)
    assert plain & seven
    assert len(plain | seven) < len(plain) + len(seven)
    assert [item.family for item in facts.targets] == ["standard", "standard", "seven_pairs", "seven_pairs"]


@pytest.mark.parametrize("melds", range(5))
def test_all_feasible_white_inventories_and_meld_counts_obey_conservation(melds):
    rng = random.Random(901 + melds)
    for whites in range(min(4, 13 - 3 * melds) + 1):
        hand = _random_waiting(rng, melds, whites)
        facts = analyze_route_structure(hand, melds)
        true_progress = analyse_counts_progress(hand, melds)
        assert facts.standard_shanten == true_progress.standard_shanten
        assert facts.seven_pairs_shanten == true_progress.chiitoi_shanten
        expected_families = 2 if melds == 0 else 1
        assert len(facts.targets) == expected_families * (whites + 1)
        if melds:
            assert facts.seven_pairs_shanten is None
        else:
            assert facts.seven_pairs_shanten is not None
        for item in facts.targets:
            k = item.retained_whites
            assert item.white_used + k == whites
            assert item.target_natural_draw_lower_bound == item.natural_need
            if k:
                assert item.natural_need >= k - 1
                assert item.target_white_discard_lower_bound == k - 1
                final_natural = sum(hand[:33]) + item.natural_need - item.target_natural_discard_lower_bound
                assert final_natural == item.target_natural_size
                assert final_natural + item.white_used + 1 == 13 - 3 * melds
            else:
                assert item.natural_need >= 1
                assert item.target_natural_discard_lower_bound == item.natural_need - 1
                assert item.target_natural_size + item.white_used == 14 - 3 * melds
            assert "白" not in item.conditional_need_improvement_codes
            assert item.conditional_need_improvement_codes == tuple(
                code for code in CANONICAL_TILE_ORDER[:33] if code in item.conditional_need_improvement_codes
            )
        expected_evaluations = len(facts.targets) * (1 + sum(value < 4 for value in hand[:33]))
        assert facts.target_distance_evaluation_count == expected_evaluations


def test_standard_exact_used_distance_and_progress_against_full_one_set_target_enumeration():
    rng = random.Random(3401)
    hands = [counts("东", "东", "东", "东")]
    for whites in range(5):
        hands.extend(_random_waiting(rng, 3, whites) for _ in range(8))
    for hand in hands:
        facts = analyze_route_structure(hand, 3)
        for item in facts.targets:
            pair_needed = item.retained_whites == 0
            oracle = _enumerated_one_set_need(hand[:33], pair_needed, item.white_used)
            assert item.natural_need == oracle
            expected = []
            for index, held in enumerate(hand[:33]):
                if held == 4:
                    continue
                drawn = hand[:index] + (held + 1,) + hand[index + 1 :33]
                if _enumerated_one_set_need(drawn, pair_needed, item.white_used) < oracle:
                    expected.append(CANONICAL_TILE_ORDER[index])
            assert item.conditional_need_improvement_codes == tuple(expected)


def test_seven_pair_distance_against_independent_exact_target_vector_enumeration():
    rng = random.Random(7601)
    for whites in range(5):
        for _ in range(12):
            hand = _random_waiting(rng, 0, whites)
            facts = analyze_route_structure(hand, 0)
            for item in (entry for entry in facts.targets if entry.family == "seven_pairs"):
                pair_count = 7 if item.retained_whites == 0 else 6
                oracle = _enumerated_pairs_need(hand[:33], pair_count, item.white_used)
                assert item.natural_need == oracle


def test_seven_pair_conditional_progress_against_independent_target_vector_enumeration():
    rng = random.Random(7602)
    for whites in range(5):
        hand = _random_waiting(rng, 0, whites)
        facts = analyze_route_structure(hand, 0)
        for item in (entry for entry in facts.targets if entry.family == "seven_pairs"):
            pair_count = 7 if item.retained_whites == 0 else 6
            before = _enumerated_pairs_need(hand[:33], pair_count, item.white_used)
            expected = []
            for index, held in enumerate(hand[:33]):
                if held == 4:
                    continue
                drawn = hand[:index] + (held + 1,) + hand[index + 1 :33]
                if _enumerated_pairs_need(drawn, pair_count, item.white_used) < before:
                    expected.append(CANONICAL_TILE_ORDER[index])
            assert item.conditional_need_improvement_codes == tuple(expected)


def test_counts_domain_and_waiting_stage_are_enforced_even_after_cache_hit():
    valid = counts("东")
    analyze_route_structure(valid, 4)
    with pytest.raises(FrozenInstanceError):
        analyze_route_structure(valid, 4).whites_held = 4
    assert ROUTE_STRUCTURE_SCHEMA_VERSION == "vip-route-structure/1"
    for invalid in (counts("东", "东"), counts(), counts("东")[:-1]):
        with pytest.raises(ValueError):
            analyze_route_structure(invalid, 4)
    with pytest.raises(ValueError):
        analyze_route_structure(counts(*(["东"] * 5 + ["白"] * 2)), 2)
    with pytest.raises(ValueError):
        analyze_route_structure(valid, 5)
    with pytest.raises(TypeError):
        analyze_route_structure(list(valid), 4)
    with pytest.raises(TypeError):
        analyze_route_structure(tuple(True if value else value for value in valid), 4)
    with pytest.raises(TypeError):
        analyze_route_structure(counts("东", "东", "东", "白"), True)


def test_missing_native_backend_preserves_route_distance_and_progress():
    """隔离解释器禁用原生加载，验证结构入口继承现有 Python 退路。"""

    source = Path(__file__).resolve().parents[3] / "src"
    script = r'''
import json, sys
sys.path.insert(0, sys.argv[1])
sys.modules["hangma_bot.hangma._grouped_native"] = None
from hangma_bot.hangma.hand_analysis import math_backend_info
from hangma_bot.hangma.route_structure import analyze_route_structure
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER
codes = "1w 2w 3w 1t 2t 3t 1b 2b 3b 7w 8w 白 白".split()
hand = tuple(codes.count(code) for code in CANONICAL_TILE_ORDER)
facts = analyze_route_structure(hand, 0)
assert math_backend_info()["implementation"] == "python_grouped"
print(json.dumps([(item.retained_whites, item.natural_need,
                  item.conditional_need_improvement_codes)
                 for item in facts.targets if item.family == "standard"]))
'''
    result = subprocess.run(
        [sys.executable, "-I", "-c", script, str(source)],
        capture_output=True, text=True, check=True, timeout=15,
    )
    entries = json.loads(result.stdout)
    assert entries[1] == [1, 0, []]
    assert entries[2] == [2, 1, ["6w", "9w"]]
