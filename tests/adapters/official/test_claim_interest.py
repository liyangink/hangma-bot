"""鸣牌兴趣预过滤单元回归（2026-09-18 复盘修订的配套测试）。

只验证 adapters/official/claim_interest 的公开函数：保守超集方向
（假阳性安全、假阴性为零）与财神/字牌/上家约束。合法动作判定属于
hangma，不在此测试范围。
"""

from hangma_bot.adapters.official.claim_interest import chi_shape_superset, discard_interesting


class TestPengSuperset:
    def test_pair_anywhere_is_interesting(self):
        # 任何座位弃 5w、我持 5w×2 → 可能碰
        assert discard_interesting(my_seat=2, discarder_seat=0, tile_code="5w", hand_codes=("5w", "5w", "9t"))
        assert discard_interesting(my_seat=2, discarder_seat=3, tile_code="5w", hand_codes=("5w", "5w"))

    def test_triple_is_covered_by_pair_check(self):
        assert discard_interesting(my_seat=1, discarder_seat=2, tile_code="东", hand_codes=("东", "东", "东", "1w"))

    def test_wealth_god_never_claimable(self):
        # 财神不能被吃/碰/杠：即使持白×3 也无关
        assert not discard_interesting(my_seat=1, discarder_seat=0, tile_code="白", hand_codes=("白", "白", "白"))

    def test_unknown_inputs_default_to_interesting(self):
        assert discard_interesting(my_seat=None, discarder_seat=0, tile_code="1w", hand_codes=("1w",))
        assert discard_interesting(my_seat=1, discarder_seat=None, tile_code="1w", hand_codes=("1w",))
        assert discard_interesting(my_seat=1, discarder_seat=0, tile_code="1w", hand_codes=None)
        assert discard_interesting(my_seat=1, discarder_seat=0, tile_code="", hand_codes=("1w",))


class TestChiSuperset:
    def test_upper_house_same_suit_within_two(self):
        # 上家弃 6w，我持 4w/5w/8w 任一（距离≤2）→ 超集命中
        for held in ("4w", "5w", "7w", "8w"):
            assert discard_interesting(my_seat=2, discarder_seat=1, tile_code="6w", hand_codes=(held, "9t"))

    def test_non_upper_house_never_chi(self):
        # 非上家弃牌不可吃：即使搭子齐也只看碰（无对子 → 无关）
        assert not discard_interesting(my_seat=2, discarder_seat=0, tile_code="6w", hand_codes=("4w", "5w"))

    def test_distance_three_is_not_superset_hit(self):
        # 距离 3 的同花色牌不构成吃形超集（3w 与 6w）
        assert not chi_shape_superset("6w", ("3w", "9w"))
        assert not discard_interesting(my_seat=2, discarder_seat=1, tile_code="6w", hand_codes=("3w", "9w"))

    def test_honor_tiles_never_form_runs(self):
        assert not chi_shape_superset("东", ("东", "南", "西"))
        assert not discard_interesting(my_seat=2, discarder_seat=1, tile_code="发", hand_codes=("发", "白"))


class TestConservativeDirection:
    def test_stale_superset_overestimates_safely(self):
        # 超集不因本人弃牌收缩：已弃一张后仍按持有 2 张判定（多拉一次快照）
        hand_superset = ("5w", "5w", "9t")  # 真实暗牌可能只剩一张 5w
        assert discard_interesting(my_seat=2, discarder_seat=0, tile_code="5w", hand_codes=hand_superset)
