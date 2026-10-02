"""自然面子准备的公开行为测试，独立目标枚举不调用被测距离作oracle。"""

from dataclasses import FrozenInstanceError
from functools import lru_cache
from itertools import combinations_with_replacement
import json
from pathlib import Path
import random
import subprocess
import sys

import pytest

from hangma_bot.hangma.natural_preparation import (
    NATURAL_PREPARATION_SEMANTICS_VERSION,
    analyze_natural_set_preparation,
)
from hangma_bot.hangma.route_structure import analyze_route_structure
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER


def counts(*codes):
    """测试用规范实体计数，不绑定任何副露、摸牌或胡牌资格。"""

    return tuple(codes.count(code) for code in CANONICAL_TILE_ORDER)


@lru_cache(maxsize=2)
def _natural_group_targets(sets_left):
    """独立枚举一/两面子所有自然实体目标，并拒绝目标的第五张。

    33种刻子和三种花色各7种顺子，按组合枚举一/两组。该oracle
    只覆盖目标一/两组的有限域，不调用标准型距离或被测实现。
    """

    blocks = [(index,) * 3 for index in range(33)]
    blocks += [
        (suit + offset, suit + offset + 1, suit + offset + 2)
        for suit in (0, 9, 18)
        for offset in range(7)
    ]
    targets = set()
    for selected in combinations_with_replacement(blocks, sets_left):
        desired = [0] * 33
        for block in selected:
            for index in block:
                desired[index] += 1
        if max(desired) <= 4:
            targets.add(tuple((i, value) for i, value in enumerate(desired) if value))
    return tuple(targets)


def _enumerated_natural_need(natural, sets_left):
    """直接按目标向量的缺张总数取最小值，与分组求解步骤无关。"""

    return min(
        sum(max(value - natural[index], 0) for index, value in desired)
        for desired in _natural_group_targets(sets_left)
    )


def _random_waiting(rng, melds, whites):
    natural = [0] * 33
    for _ in range(13 - 3 * melds - whites):
        index = rng.choice([i for i, value in enumerate(natural) if value < 4])
        natural[index] += 1
    return tuple(natural) + (whites,)


def test_zero_white_counterexample_distinguishes_natural_preparation_without_changing_shanten():
    """T38共同零白已听牌形：拆五条刻子比保刻子多缺一张自然牌。"""

    discard_five = counts(*"2w 3w 4w 4b 6b 9b 9b 9b 5t 5t 7t 8t 9t".split())
    discard_six = counts(*"2w 3w 4w 4b 9b 9b 9b 5t 5t 5t 7t 8t 9t".split())
    old_five = analyze_route_structure(discard_five, 0)
    old_six = analyze_route_structure(discard_six, 0)
    assert old_five.standard_shanten == old_six.standard_shanten == 0
    assert old_five.seven_pairs_shanten == old_six.seven_pairs_shanten == 4
    five = analyze_natural_set_preparation(discard_five, 0)
    six = analyze_natural_set_preparation(discard_six, 0)
    assert five.whites_held == six.whites_held == 0
    assert five.sets_left == six.sets_left == 4
    assert five.target_natural_size == six.target_natural_size == 12
    assert five.natural_draw_lower_bound == 1
    assert six.natural_draw_lower_bound == 0
    assert five.natural_discard_lower_bound == 2
    assert six.natural_discard_lower_bound == 1
    assert five.natural_need_improvement_codes == ("5b", "5t")
    assert six.natural_need_improvement_codes == ()
    # 新事实没有回写旧事实，也没有把未来白板补进真实库存。
    assert analyze_route_structure(discard_five, 0) == old_five
    assert analyze_route_structure(discard_six, 0) == old_six
    assert five.natural_counts33 + (five.whites_held,) == discard_five
    assert six.natural_counts33 + (six.whites_held,) == discard_six


def test_natural_gap_has_width_without_binding_white_to_isolated_honor():
    middle = analyze_natural_set_preparation(counts("5w", "白", "白", "白"), 3)
    honor = analyze_natural_set_preparation(counts("东", "白", "白", "白"), 3)
    assert middle.natural_draw_lower_bound == honor.natural_draw_lower_bound == 2
    assert middle.natural_need_improvement_codes == ("3w", "4w", "5w", "6w", "7w")
    assert honor.natural_need_improvement_codes == ("东",)
    assert middle.whites_held == honor.whites_held == 3
    assert middle.natural_discard_lower_bound == honor.natural_discard_lower_bound == 0


def test_four_whites_are_real_inventory_and_do_not_fill_natural_target():
    facts = analyze_natural_set_preparation(counts("白", "白", "白", "白"), 3)
    assert facts.whites_held == 4
    assert facts.natural_counts33 == (0,) * 33
    assert facts.target_natural_size == facts.natural_draw_lower_bound == 3
    assert facts.natural_discard_lower_bound == 0
    assert facts.natural_need_improvement_codes == CANONICAL_TILE_ORDER[:33]
    assert "白" not in facts.natural_need_improvement_codes


def test_natural_fourth_entity_does_not_admit_a_fifth_and_melds_are_folded_as_sets():
    hand = counts("东", "东", "东", "东", "2w", "4w", "白")
    facts = analyze_natural_set_preparation(hand, 2)
    assert facts.sets_left == 2
    assert facts.target_natural_size == 6
    assert facts.natural_draw_lower_bound == 1
    assert facts.natural_discard_lower_bound == 1
    assert facts.natural_need_improvement_codes == ("3w",)
    assert "东" not in facts.natural_need_improvement_codes
    assert facts.target_distance_evaluation_count == 33


@pytest.mark.parametrize("code", ("东", "白"))
def test_four_melds_need_no_more_natural_sets_but_zero_is_not_a_hu_qualification(code):
    facts = analyze_natural_set_preparation(counts(code), 4)
    assert facts.sets_left == facts.target_natural_size == facts.natural_draw_lower_bound == 0
    assert facts.natural_discard_lower_bound == int(code != "白")
    assert facts.natural_need_improvement_codes == ()


@pytest.mark.parametrize("melds", range(5))
def test_all_white_inventories_preserve_counts_and_match_existing_all_white_retained_target(melds):
    rng = random.Random(4600 + melds)
    for whites in range(min(4, 13 - 3 * melds) + 1):
        for _ in range(5):
            hand = _random_waiting(rng, melds, whites)
            facts = analyze_natural_set_preparation(hand, melds)
            assert facts.natural_counts33 + (facts.whites_held,) == hand
            assert facts.natural_discard_lower_bound >= 0
            assert sum(hand[:33]) + facts.natural_draw_lower_bound - facts.natural_discard_lower_bound == facts.target_natural_size
            assert facts.target_distance_evaluation_count == 1 + sum(value < 4 for value in hand[:33])
            assert "白" not in facts.natural_need_improvement_codes
            assert facts.natural_need_improvement_codes == tuple(
                code for code in CANONICAL_TILE_ORDER[:33] if code in facts.natural_need_improvement_codes
            )
            if whites:
                old = analyze_route_structure(hand, melds)
                retained = next(
                    target for target in old.targets
                    if target.family == "standard" and target.retained_whites == whites
                )
                assert retained.white_used == 0
                assert facts.natural_draw_lower_bound == retained.natural_need
                assert facts.natural_discard_lower_bound == retained.target_natural_discard_lower_bound
                assert facts.target_natural_size == retained.target_natural_size
                assert facts.natural_need_improvement_codes == retained.conditional_need_improvement_codes


@pytest.mark.parametrize("melds", (2, 3))
def test_one_and_two_set_distances_and_improvement_codes_against_independent_targets(melds):
    rng = random.Random(4610 + melds)
    for whites in range(5):
        for _ in range(5):
            hand = _random_waiting(rng, melds, whites)
            facts = analyze_natural_set_preparation(hand, melds)
            oracle = _enumerated_natural_need(hand[:33], 4 - melds)
            assert facts.natural_draw_lower_bound == oracle
            expected = []
            for index, held in enumerate(hand[:33]):
                if held == 4:
                    continue
                drawn = hand[:index] + (held + 1,) + hand[index + 1 :33]
                if _enumerated_natural_need(drawn, 4 - melds) < oracle:
                    expected.append(CANONICAL_TILE_ORDER[index])
            assert facts.natural_need_improvement_codes == tuple(expected)


def test_input_domain_checked_before_cache_and_facts_remain_immutable():
    valid = counts("东")
    facts = analyze_natural_set_preparation(valid, 4)
    assert analyze_natural_set_preparation(valid, 4) == facts
    assert NATURAL_PREPARATION_SEMANTICS_VERSION == "vip-natural-set-preparation/1"
    with pytest.raises(FrozenInstanceError):
        facts.whites_held = 4
    for invalid in (counts(), counts("东", "东"), valid[:-1]):
        with pytest.raises(ValueError):
            analyze_natural_set_preparation(invalid, 4)
    for invalid_count in (-1, 5):
        bad = (invalid_count,) + (0,) * 33
        with pytest.raises(ValueError):
            analyze_natural_set_preparation(bad, 4)
    for bad_melds in (-1, 5):
        with pytest.raises(ValueError):
            analyze_natural_set_preparation(valid, bad_melds)
    with pytest.raises(TypeError):
        analyze_natural_set_preparation(list(valid), 4)
    # 先用对应整数填充缓存，随后bool/int相等也必须拒绝。
    with pytest.raises(TypeError):
        analyze_natural_set_preparation(tuple(bool(v) if v else v for v in valid), 4)
    with pytest.raises(TypeError):
        analyze_natural_set_preparation(counts("东", "东", "东", "白"), True)
    with pytest.raises(TypeError):
        analyze_natural_set_preparation(valid[:27] + (1.0,) + valid[28:], 4)


def test_missing_native_backend_preserves_natural_preparation_public_result():
    """隔离解释器选现有Python退路，不在被测进程修改缓存或私有状态。"""

    source = Path(__file__).resolve().parents[3] / "src"
    script = r'''
import json, sys
sys.path.insert(0, sys.argv[1])
sys.modules["hangma_bot.hangma._grouped_native"] = None
from hangma_bot.hangma._standard import backend_info
from hangma_bot.hangma.natural_preparation import analyze_natural_set_preparation
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER
codes = "2w 3w 4w 4b 6b 9b 9b 9b 5t 5t 7t 8t 9t".split()
hand = tuple(codes.count(code) for code in CANONICAL_TILE_ORDER)
facts = analyze_natural_set_preparation(hand, 0)
assert backend_info()["implementation"] == "python_grouped"
print(json.dumps([facts.whites_held, facts.natural_draw_lower_bound,
                  facts.natural_discard_lower_bound, facts.natural_need_improvement_codes]))
'''
    result = subprocess.run(
        [sys.executable, "-I", "-c", script, str(source)],
        capture_output=True, text=True, check=True, timeout=15,
    )
    assert json.loads(result.stdout) == [0, 1, 2, ["5b", "5t"]]
