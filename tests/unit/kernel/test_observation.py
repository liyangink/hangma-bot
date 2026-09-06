"""kernel.observation 的单元测试：结构校验、手牌顺序与信息权限。"""

import unittest
from dataclasses import FrozenInstanceError, fields

from hangma_bot.kernel.observation import (
    CompetitionContext,
    PlayerObservation,
    PublicDiscard,
    PublicEvent,
    PublicMeld,
    RankingEntry,
    RulePublicState,
)
from hangma_bot.kernel.actions import Tile


def _rule_state(**overrides: object) -> RulePublicState:
    base = {
        "wealth_god": Tile("白"),
        "baotou": False,
        "chain_count": 0,
        "catch_play": False,
    }
    base.update(overrides)
    return RulePublicState(**base)  # type: ignore[arg-type]


def _observation(**overrides: object) -> PlayerObservation:
    base = {
        "game_id": "g1",
        "seat": 0,
        "round_no": 1,
        "snapshot_seq": 5,
        "phase": "draw",
        "dealer_seat": 0,
        "turn_seat": 0,
        "responding_seats": (),
        "my_hand": (Tile("1w"), Tile("2w"), Tile("3w")),
        "drawn_tile": Tile("3w"),
        "discards": ((), (), (), ()),
        "melds": ((), (), (), ()),
        "hand_counts": (13, 13, 13, 13),
        "last_discard": None,
        "remaining_tile_count": 70,
        "scores": (0, 0, 0, 0),
        "rule_state": _rule_state(),
        "public_history": (),
    }
    base.update(overrides)
    return PlayerObservation(**base)  # type: ignore[arg-type]


class StructuralValidationTests(unittest.TestCase):
    """座位范围与四家向量长度的廉价校验。"""

    def test_rejects_seat_out_of_range(self) -> None:
        """所有座位字段（含响应座位集合）都必须在 0—3。"""
        for field_name in ("seat", "dealer_seat", "turn_seat"):
            with self.assertRaises(ValueError):
                _observation(**{field_name: 4})
            with self.assertRaises(ValueError):
                _observation(**{field_name: -1})
        with self.assertRaises(ValueError):
            _observation(responding_seats=(5,))

    def test_rejects_wrong_four_seat_vector_lengths(self) -> None:
        """牌河、副露、手牌张数与积分都必须是按座位 0—3 的四元组。"""
        with self.assertRaises(ValueError):
            _observation(discards=((), (), ()))
        with self.assertRaises(ValueError):
            _observation(melds=((), (), (), (), ()))
        with self.assertRaises(ValueError):
            _observation(hand_counts=(13, 13, 13))
        with self.assertRaises(ValueError):
            _observation(scores=(0, 0, 0, 0, 0))

    def test_rejects_negative_counts_and_empty_identifiers(self) -> None:
        with self.assertRaises(ValueError):
            _observation(remaining_tile_count=-1)
        with self.assertRaises(ValueError):
            _observation(hand_counts=(13, 13, 13, -1))
        with self.assertRaises(ValueError):
            _observation(game_id="")
        with self.assertRaises(ValueError):
            _observation(game_id="   ")
        with self.assertRaises(ValueError):
            _observation(phase="")
        with self.assertRaises(ValueError):
            _observation(responding_seats=(1, 1))

    def test_accepts_minimal_and_boundary_values(self) -> None:
        """空响应集合、空历史、空牌河与 0 张数都是合法状态。"""
        observation = _observation(
            drawn_tile=None,
            remaining_tile_count=None,
            hand_counts=(0, 0, 0, 0),
        )
        self.assertIsNone(observation.drawn_tile)
        self.assertEqual(observation.hand_counts, (0, 0, 0, 0))


class NestedValueTests(unittest.TestCase):
    """嵌套公开值的结构校验。"""

    def test_public_meld_validates_seats_and_tiles(self) -> None:
        valid = PublicMeld(
            seat=2, kind="peng", tiles=(Tile("5w"), Tile("5w"), Tile("5w")), from_seat=1
        )
        self.assertEqual(valid.seat, 2)
        with self.assertRaises(ValueError):
            PublicMeld(seat=4, kind="peng", tiles=(), from_seat=None)
        with self.assertRaises(ValueError):
            PublicMeld(seat=0, kind="peng", tiles=(), from_seat=4)
        with self.assertRaises(ValueError):
            PublicMeld(seat=0, kind="", tiles=(), from_seat=None)
        with self.assertRaises(ValueError):
            PublicMeld(seat=0, kind="peng", tiles=("5w",), from_seat=None)

    def test_public_event_allows_unknown_kind_and_validates_seat(self) -> None:
        """未知官方事件类型必须可以透传保存，不能因此失败。"""
        event = PublicEvent(seq=7, kind="future_event", seat=None, tiles=(Tile("东"),), occurred_at_unix_sec=1756771200)
        self.assertEqual(event.kind, "future_event")
        with self.assertRaises(ValueError):
            PublicEvent(seq=7, kind="chi", seat=4)
        with self.assertRaises(ValueError):
            PublicEvent(seq=-1, kind="chi", seat=None)
        with self.assertRaises(ValueError):
            PublicEvent(seq=7, kind="chi", seat=None, tiles=("东",))

    def test_public_discard_and_rule_state_validation(self) -> None:
        discard = PublicDiscard(seat=3, tile=Tile("中"), seq=42)
        self.assertEqual(discard.seq, 42)
        with self.assertRaises(ValueError):
            PublicDiscard(seat=3, tile=Tile("中"), seq=-1)
        with self.assertRaises(ValueError):
            _rule_state(chain_count=-1)
        with self.assertRaises(ValueError):
            _rule_state(wealth_god="白")
        with self.assertRaises(ValueError):
            _rule_state(baotou=1)


class HandOrderTests(unittest.TestCase):
    """手牌必须保留官方顺序；紧急弃牌依赖最右一张。"""

    def test_hand_order_is_preserved_and_significant(self) -> None:
        hand = (Tile("8w"), Tile("1w"), Tile("3w"))
        observation = _observation(my_hand=hand)
        self.assertEqual(observation.my_hand, hand)  # 不排序、不去重
        self.assertEqual(observation.my_hand[-1].code, "3w")  # 紧急弃牌位
        swapped = _observation(my_hand=(hand[1], hand[0], hand[2]))
        self.assertNotEqual(observation, swapped)  # 顺序参与相等性

    def test_observation_is_immutable(self) -> None:
        observation = _observation()
        with self.assertRaises(FrozenInstanceError):
            observation.snapshot_seq = 6  # type: ignore[misc]

    def test_deterministic_equality_and_hash(self) -> None:
        self.assertEqual(_observation(), _observation())
        self.assertEqual(hash(_observation()), hash(_observation()))


class InformationPermissionTests(unittest.TestCase):
    """信息权限回归：改变隐藏牌不会改变同一 PlayerObservation。"""

    def test_hidden_information_has_no_field_to_flow_into(self) -> None:
        """他家手牌、未来牌墙与赛后结果在类型上没有承载字段。

        “改变隐藏牌不会改变同一 PlayerObservation”在 kernel 层的证明是
        结构性的：隐藏信息无法进入构造输入。本测试固定字段白名单，
        未来新增字段必须显式更新本清单并说明信息权限（AGENTS.md 第 5 节）。
        """
        expected_fields = {
            "game_id",
            "seat",
            "round_no",
            "snapshot_seq",
            "phase",
            "dealer_seat",
            "turn_seat",
            "responding_seats",
            "my_hand",
            "drawn_tile",
            "discards",
            "melds",
            "hand_counts",
            "last_discard",
            "remaining_tile_count",
            "scores",
            "rule_state",
            "public_history",
            "consumed_seq", "history_complete", "chain_piao", "gang_draw", "observation_issues",
        }
        self.assertEqual({field.name for field in fields(PlayerObservation)}, expected_fields)

    def test_same_visible_facts_produce_equal_observations(self) -> None:
        """同一可见事实构造的两个观察完全相等（确定性）。"""
        self.assertEqual(_observation(), _observation())


class CounterexampleRegressionTests(unittest.TestCase):
    """终裁反例回归：可变容器与整数不变量必须在构造期被拒绝。"""

    def test_all_container_fields_reject_mutable_lists(self) -> None:
        """反例回归：list 渗入会使身份漂移、不可哈希、往返断裂。

        拒绝式修复（RS-4 裁定）：所有声明 Tuple 的序列字段（含嵌套行）
        在构造期拒绝 list，错误暴露在调用方转换点。
        """
        cases = {
            "responding_seats": [0, 1],
            "my_hand": [Tile("1w")],
            "discards": [(), (), (), ()],
            "melds": [(), (), (), ()],
            "hand_counts": [13, 13, 13, 13],
            "scores": [0, 0, 0, 0],
            "public_history": [],
        }
        for field_name, bad_value in cases.items():
            with self.assertRaises(ValueError, msg=field_name):
                _observation(**{field_name: bad_value})
        # 嵌套行也必须拒绝 list。
        with self.assertRaises(ValueError):
            _observation(discards=((), (), (), [Tile("1w")]))
        with self.assertRaises(ValueError):
            _observation(melds=((), (), (), [PublicMeld(seat=0, kind="chi", tiles=(Tile("1t"), Tile("2t"), Tile("3t")), from_seat=1)]))
        # 嵌套公开值同样拒绝 list。
        with self.assertRaises(ValueError):
            PublicMeld(seat=0, kind="peng", tiles=[Tile("5w"), Tile("5w"), Tile("5w")], from_seat=None)
        with self.assertRaises(ValueError):
            PublicEvent(seq=1, kind="chi", seat=None, tiles=[Tile("东")])
        with self.assertRaises(ValueError):
            CompetitionContext(
                tournament_id="t1", stage_no=None, stage_role=None, stage_total=None,
                participant_rank=None, ranking=[], observed_at_unix_ms=0,
            )

    def test_scores_elements_must_be_plain_integers(self) -> None:
        """反例回归：积分元素拒绝 str/float/bool；负分（输分）必须放行。

        混合类型积分会构造成功却无法经序列化往返（能写出不能读回）。
        """
        for bad in (("10", 0, 0, 0), (1.5, 0, 0, 0), (True, 0, 0, 0), (None, 0, 0, 0)):
            with self.assertRaises(ValueError):
                _observation(scores=bad)
        self.assertEqual(_observation(scores=(-24, 0, 8, 0)).scores, (-24, 0, 8, 0))

    def test_round_no_and_stage_fields_reject_bad_values(self) -> None:
        """反例回归：局号与阶段字段必须是纯非负 int 或 None。"""
        for bad in (-2, "1", True, 1.5, None):
            with self.assertRaises(ValueError):
                _observation(round_no=bad)
        with self.assertRaises(ValueError):
            CompetitionContext(
                tournament_id="t1", stage_no=-2, stage_role=None, stage_total=None,
                participant_rank=None, ranking=(), observed_at_unix_ms=0,
            )
        with self.assertRaises(ValueError):
            CompetitionContext(
                tournament_id="t1", stage_no=None, stage_role=None, stage_total=None,
                participant_rank=-1, ranking=(), observed_at_unix_ms=0,
            )
        # None（官方未提供）与非负值合法。
        context = CompetitionContext(
            tournament_id="t1", stage_no=1, stage_role=None, stage_total=4,
            participant_rank=None, ranking=(), observed_at_unix_ms=0,
        )
        self.assertEqual(context.stage_total, 4)


class CompetitionContextTests(unittest.TestCase):
    """已观察赛事上下文只保存权威事实。"""

    def test_ranking_entry_validates_observed_facts(self) -> None:
        entry = RankingEntry(
            participant_id="p1",
            total_score=-12,  # 总分允许为负
            place_points=-3,  # 排名分允许为负
            god_count=2,
            games_played=0,
            rank=1,
        )
        self.assertEqual(entry.total_score, -12)
        base = {
            "participant_id": "p1",
            "total_score": 0,
            "place_points": 0,
            "god_count": 0,
            "games_played": 0,
            "rank": 1,
        }
        for field_name, bad_value in (
            ("rank", 0),
            ("rank", True),
            ("god_count", -1),
            ("games_played", -1),
            ("participant_id", ""),
            ("total_score", "1"),
        ):
            broken = dict(base)
            broken[field_name] = bad_value
            with self.assertRaises(ValueError):
                RankingEntry(**broken)  # type: ignore[arg-type]

    def test_competition_context_validates_identity_and_time(self) -> None:
        context = CompetitionContext(
            tournament_id="t1",
            stage_no=1,
            stage_role="finalist",
            stage_total=4,
            participant_rank=None,
            ranking=(),
            observed_at_unix_ms=1756771200000,
        )
        self.assertEqual(context.tournament_id, "t1")
        with self.assertRaises(ValueError):
            CompetitionContext(
                tournament_id="", stage_no=None, stage_role=None, stage_total=None,
                participant_rank=None, ranking=(), observed_at_unix_ms=0,
            )
        with self.assertRaises(ValueError):
            CompetitionContext(
                tournament_id="t1", stage_no="1", stage_role=None, stage_total=None,
                participant_rank=None, ranking=(), observed_at_unix_ms=0,
            )
        with self.assertRaises(ValueError):
            CompetitionContext(
                tournament_id="t1", stage_no=None, stage_role=None, stage_total=None,
                participant_rank=None, ranking=(), observed_at_unix_ms=-1,
            )


if __name__ == "__main__":
    unittest.main()
