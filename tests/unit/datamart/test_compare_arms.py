"""通过公开函数验证多臂对比口径：名次份额、庄家连庄、比例区间与配对检验。

比较器是出结论的工具，口径错了会给出错误的强弱判断，所以这些不变量必须钉死：
位次份额合计等于单局数、同一单局四个座位得分和为 0、完全相同两臂的配对差恒为零。
"""

import importlib.util
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _load():
    spec = importlib.util.spec_from_file_location("compare_arms", ROOT / "datamart" / "compare_arms.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["compare_arms"] = module
    spec.loader.exec_module(module)
    return module


compare = _load()


def row(hand, game, round_no, seat, strategy, delta, *, dealer_seat=0, local_first=0, god=0):
    """构造一行与 SQL 同形状的座位事实；只填比较器真正读取的字段。"""

    return {
        "hand_key": hand, "game_id": game, "round_no": round_no,
        "dealer_seat": dealer_seat, "winner_seat": dealer_seat, "is_draw": 0,
        "fan": 1, "fan_detail": "[\"平胡\"]", "played_date": "2026-09-14",
        "seat": seat, "strategy_key": strategy,
        "is_winner": 1 if seat == dealer_seat else 0,
        "is_local_first": local_first,
        "is_dealer": 1 if seat == dealer_seat else 0,
        "god_count": god, "score_delta": delta,
    }


def test_rank_shares_split_ties_and_sum_to_seat_count():
    ranks = compare.rank_within_hand({0: 10, 1: -1, 2: -1, 3: -8})

    assert ranks[0] == (1.0, {1: 1.0})
    assert ranks[1] == (2.5, {2: 0.5, 3: 0.5})
    assert ranks[2] == (2.5, {2: 0.5, 3: 0.5})
    assert ranks[3] == (4.0, {4: 1.0})
    total = sum(share for _, shares in ranks.values() for share in shares.values())
    assert math.isclose(total, 4.0)


def test_four_way_tie_splits_every_position():
    ranks = compare.rank_within_hand({0: 0, 1: 0, 2: 0, 3: 0})

    for seat in range(4):
        average, shares = ranks[seat]
        assert average == 2.5
        assert shares == {1: 0.25, 2: 0.25, 3: 0.25, 4: 0.25}


def test_rank_within_hand_requires_exactly_four_seats():
    assert compare.rank_within_hand({0: 1, 1: 2}) == {}
    assert compare.rank_within_hand({}) == {}


def test_wilson_interval_brackets_the_proportion():
    low, high = compare.wilson_ci(0, 10)
    assert math.isclose(low, 0.0, abs_tol=1e-9) and 20 < high < 35
    low, high = compare.wilson_ci(10, 10)
    assert 65 < low < 80 and math.isclose(high, 100.0, abs_tol=1e-9)
    assert compare.wilson_ci(0, 0) == (0.0, 0.0)


def test_sign_test_matches_exact_binomial():
    assert compare.sign_test_p(0, 0) == 1.0
    assert math.isclose(compare.sign_test_p(10, 0), 2 * 0.5 ** 10, rel_tol=1e-9)
    assert math.isclose(compare.sign_test_p(0, 10), compare.sign_test_p(10, 0), rel_tol=1e-12)
    assert compare.sign_test_p(5, 5) > 0.9


def test_percentile_interpolates_linearly():
    assert compare.percentile([4, 1, 3, 2], 0.5) == 2.5
    assert compare.percentile([1, 2, 3, 4], 1.0) == 4
    assert compare.percentile([], 0.5) == 0.0


def test_cluster_bootstrap_needs_two_games_and_keeps_constant_difference():
    rng = random.Random(1)
    assert compare.cluster_bootstrap_ci({"g1": [1.0, 2.0]}, rng) is None
    interval = compare.cluster_bootstrap_ci({"g1": [3.0], "g2": [3.0], "g3": [3.0]}, rng)
    assert interval == (3.0, 3.0)


def _two_arm_rows():
    """每单局四座恒为 +10 / -5 / -5 / 0（和为零）；arm_a 局局坐庄、局局胡。

    其中 arm_b 与 arm_other 取值完全相同，专门用来验证「同一批数据的两条臂
    配对差恒为零」这条比较器必须满足的性质。
    """

    rows = []
    for game_index in range(2):
        game = "t_demo_r1_b%d_t0" % game_index
        for index in range(4):
            hand = "hand-%d-%d" % (game_index, index)
            rows.append(row(hand, game, index + 1, 0, "arm_a", 10, dealer_seat=0, local_first=1, god=1))
            rows.append(row(hand, game, index + 1, 1, "arm_b", -5, dealer_seat=0))
            rows.append(row(hand, game, index + 1, 2, "arm_other", -5, dealer_seat=0))
            rows.append(row(hand, game, index + 1, 3, "arm_fourth", 0, dealer_seat=0))
    return rows


def test_aggregate_reports_chains_ranks_and_zero_sum():
    stats = compare.aggregate(_two_arm_rows())

    assert set(stats) == {"arm_a", "arm_b", "arm_other", "arm_fourth"}
    assert stats["arm_a"]["hands"] == 8 and stats["arm_a"]["games"] == 2
    assert stats["arm_a"]["net"] == 80 and stats["arm_a"]["net_per_hand"] == 10
    assert stats["arm_b"]["net"] == -40
    assert stats["arm_a"]["hu_rate"] == 100.0 and stats["arm_b"]["hu_rate"] == 0.0
    assert stats["arm_a"]["first_rate"] == 100.0
    # 每场四局连续坐庄：每场连庄机会 3 次全部命中，最长连庄 4
    assert stats["arm_a"]["dealer_chain_rate"] == 100.0
    assert stats["arm_a"]["dealer_chain_max"] == 4
    assert stats["arm_b"]["dealer_chain_max"] == 0
    counts = stats["arm_a"]["rank_counts"]
    assert math.isclose(sum(counts.values()), stats["arm_a"]["hands"])
    assert counts["1"] == 8 and stats["arm_a"]["rank_mean"] == 1.0


def test_paired_is_zero_for_identical_arms_and_detects_a_constant_advantage():
    stats = compare.aggregate(_two_arm_rows())
    rng = random.Random(7)

    same = compare.paired(stats, "arm_b", rng)["arm_other"]
    assert same["axes"]["net"]["mean"] == 0
    assert same["axes"]["net"]["ci95"] == (0.0, 0.0)
    assert same["axes"]["net"]["sign_p"] == 1.0
    assert not same["axes"]["net"]["significant"]

    against = compare.paired(stats, "arm_fourth", rng)["arm_a"]
    net = against["axes"]["net"]
    assert against["paired_hands"] == 8
    assert net["mean"] == 10 and net["ci95"] == (10.0, 10.0)
    assert net["positive"] == 8 and net["negative"] == 0
    assert net["significant"]
    hu = against["axes"]["hu"]
    assert hu["mean"] == 1.0 and hu["significant"]