"""2026-09-04 集成阶段契约收口的跨模块契约固化。

覆盖四项裁定（主技术方案集成阶段）：
1. `SubmitRejectedNoRefresh` 封闭结果类型（contract-change-request 方案 A）；
2. 吃牌组合的规范牌序与 `action_key` 一致性（kernel 唯一权威牌序）；
3. 候选牌效事实 `CandidateFacts` 的不可变与不伪造数值不变量；
4. kernel 裁决：`PlayerObservation.phase` 开放字符串、`WindowKey.phase`
   封闭枚举、`round_no` 非负不假设从 1 起、`my_hand` 不含单列摸牌。
"""

import unittest
from typing import get_args

from hangma_bot.adapters.recording.schema import canonical_outcome
from hangma_bot.application.contracts import (
    SubmitOutcome,
    SubmitRejectedNoRefresh,
)
from hangma_bot.hangma.interface import (
    CandidateFactKind,
    CandidateFacts,
    RuleCandidate,
    RuleCompleteness,
    UsefulTileFact,
)
from hangma_bot.kernel.actions import (
    CANONICAL_TILE_CODES,
    CANONICAL_TILE_INDEX,
    CANONICAL_TILE_ORDER,
    Chi,
    Pass,
    Tile,
    WindowKey,
    WindowPhase,
    action_key,
)


class SubmitRejectedNoRefreshContracts(unittest.TestCase):
    """"已发出 + 官方明确未执行 + 无权威刷新"的诚实结果类型。"""

    def test_type_is_part_of_closed_union(self) -> None:
        """新类型必须进入 SubmitOutcome 封闭联合。"""

        self.assertIn(SubmitRejectedNoRefresh, get_args(SubmitOutcome))

    def test_carries_required_fields(self) -> None:
        outcome = SubmitRejectedNoRefresh(
            official_code="RATE_LIMITED",
            rejected_action_key="discard:1w",
            latest_local_seq=42,
            reason="official_rate_limited",
        )
        self.assertEqual(outcome.official_code, "RATE_LIMITED")
        self.assertEqual(outcome.rejected_action_key, "discard:1w")
        self.assertEqual(outcome.latest_local_seq, 42)
        self.assertEqual(outcome.reason, "official_rate_limited")

    def test_audit_vocabulary_maps_new_type(self) -> None:
        """recording 规范结果词表必须认识新类型的两种形态。"""

        self.assertEqual(canonical_outcome("SubmitRejectedNoRefresh"), "rejected_no_refresh")
        self.assertEqual(canonical_outcome("rejected_no_refresh"), "rejected_no_refresh")


class CanonicalChiOrderContracts(unittest.TestCase):
    """吃牌组合使用全仓唯一规范牌序；相同组合产生相同 action_key。"""

    def test_canonical_order_accepted(self) -> None:
        chi = Chi((Tile("1w"), Tile("2w"), Tile("3w")))
        self.assertEqual(action_key(chi), "chi:1w,2w,3w")

    def test_non_canonical_order_rejected_at_construction(self) -> None:
        """构造边界拒绝非规范顺序，不在 action_key 中静默排序。"""

        with self.assertRaises(ValueError):
            Chi((Tile("3w"), Tile("1w"), Tile("2w")))
        with self.assertRaises(ValueError):
            Chi((Tile("2w"), Tile("1w"), Tile("3w")))

    def test_same_combination_same_key(self) -> None:
        first = Chi((Tile("4b"), Tile("5b"), Tile("6b")))
        second = Chi((Tile("4b"), Tile("5b"), Tile("6b")))
        self.assertEqual(action_key(first), action_key(second))

    def test_kernel_is_single_tile_order_authority(self) -> None:
        """hangma 内部牌序必须是 kernel 权威常量的引用，不是平行数据。"""

        from hangma_bot.hangma import internal_types

        self.assertIs(internal_types.TILE_ORDER, CANONICAL_TILE_ORDER)
        self.assertIs(internal_types.TILE_INDEX, CANONICAL_TILE_INDEX)

    def test_tile_order_covers_all_codes_exactly_once(self) -> None:
        self.assertEqual(len(CANONICAL_TILE_ORDER), 34)
        self.assertEqual(set(CANONICAL_TILE_ORDER), CANONICAL_TILE_CODES)
        self.assertEqual(len(set(CANONICAL_TILE_ORDER)), 34)
        # 财神（白）固定为最后一位，计数向量下标 33。
        self.assertEqual(CANONICAL_TILE_ORDER[-1], "白")


class CandidateFactsContracts(unittest.TestCase):
    """候选牌效事实：不可变、不伪造数值、与 action_key 关联。"""

    def test_facts_default_none_on_rule_candidate(self) -> None:
        candidate = RuleCandidate(action=Pass(), action_key="pass", evidence=())
        self.assertIsNone(candidate.facts)

    def test_facts_attach_to_candidate(self) -> None:
        facts = CandidateFacts(
            fact_kind=CandidateFactKind.HAND_PROGRESS,
            shanten_after=1,
            useful_tiles=(UsefulTileFact(code="5w", remaining_estimate=3),),
        )
        candidate = RuleCandidate(
            action=Pass(), action_key="pass", evidence=(), facts=facts
        )
        self.assertIs(candidate.facts, facts)

    def test_win_uses_minus_one_sentinel(self) -> None:
        facts = CandidateFacts(fact_kind=CandidateFactKind.WIN, shanten_after=-1)
        self.assertEqual(facts.shanten_after, -1)
        with self.assertRaises(ValueError):
            CandidateFacts(fact_kind=CandidateFactKind.WIN, shanten_after=0)

    def test_not_applicable_must_not_carry_numbers(self) -> None:
        with self.assertRaises(ValueError):
            CandidateFacts(
                fact_kind=CandidateFactKind.NOT_APPLICABLE,
                shanten_after=2,
            )
        with self.assertRaises(ValueError):
            CandidateFacts(
                fact_kind=CandidateFactKind.NOT_APPLICABLE,
                shanten_after=None,
                useful_tiles=(UsefulTileFact(code="5w", remaining_estimate=1),),
            )

    def test_analysis_failed_requires_note(self) -> None:
        with self.assertRaises(ValueError):
            CandidateFacts(
                fact_kind=CandidateFactKind.ANALYSIS_FAILED,
                shanten_after=None,
                completeness=RuleCompleteness.DEGRADED,
                note=None,
            )
        facts = CandidateFacts(
            fact_kind=CandidateFactKind.ANALYSIS_FAILED,
            shanten_after=None,
            completeness=RuleCompleteness.DEGRADED,
            note="向听分支超时",
        )
        self.assertIsNone(facts.shanten_after)
        self.assertEqual(facts.useful_tiles, ())

    def test_useful_tile_fact_bounds(self) -> None:
        self.assertEqual(
            UsefulTileFact(code="5w", remaining_estimate=4).remaining_estimate, 4
        )
        with self.assertRaises(ValueError):
            UsefulTileFact(code="5w", remaining_estimate=5)
        with self.assertRaises(ValueError):
            UsefulTileFact(code="5w", remaining_estimate=-1)
        with self.assertRaises(ValueError):
            UsefulTileFact(code="XX", remaining_estimate=1)

    def test_gang_replacement_unknown_flag(self) -> None:
        facts = CandidateFacts(
            fact_kind=CandidateFactKind.HAND_PROGRESS,
            shanten_after=1,
            replacement_draw_unknown=True,
            note="杠后补牌未知，向听为补牌前余牌口径",
        )
        self.assertTrue(facts.replacement_draw_unknown)


class KernelRulingContracts(unittest.TestCase):
    """2026-09-04 kernel 裁决的结构性固化。"""

    def test_observation_phase_stays_open_string(self) -> None:
        """PlayerObservation.phase 保持开放字符串以兼容官方新增阶段。"""

        from hangma_bot.kernel.observation import PlayerObservation, RulePublicState

        observation = PlayerObservation(
            game_id="g-ruling",
            seat=0,
            round_no=1,
            snapshot_seq=1,
            phase="some_future_phase",  # 未知官方阶段必须能承载
            dealer_seat=0,
            turn_seat=0,
            responding_seats=(),
            my_hand=(Tile("1w"),),
            drawn_tile=Tile("2w"),  # 摸牌单列，不并入 my_hand
            discards=((), (), (), ()),
            melds=((), (), (), ()),
            hand_counts=(2, 13, 13, 13),
            last_discard=None,
            remaining_tile_count=None,
            scores=(0, 0, 0, 0),
            rule_state=RulePublicState(
                wealth_god=Tile("白"), baotou=False, chain_count=0, catch_play=False
            ),
            public_history=(),
        )
        self.assertEqual(observation.phase, "some_future_phase")
        # my_hand 不包含单列的 drawn_tile：官方 DTO 形态差异由适配器归一化。
        self.assertNotIn(observation.drawn_tile, observation.my_hand)

    def test_window_key_phase_is_closed_enum(self) -> None:
        key = WindowKey(
            game_id="g-ruling",
            round_no=0,  # round_no 不假设从 1 起；只作官方关联标识
            trigger_seq=0,
            phase=WindowPhase.DRAW,
            seat=0,
        )
        self.assertIsInstance(key.phase, WindowPhase)
        with self.assertRaises(ValueError):
            WindowKey(
                game_id="g-ruling",
                round_no=1,
                trigger_seq=1,
                phase="draw",  # 裸字符串不得替代封闭枚举
                seat=0,
            )

    def test_public_event_has_no_raw_data_dict(self) -> None:
        """PublicEvent 不携带官方任意 data 字典；原始数据留在协议审计。"""

        import inspect

        from hangma_bot.kernel import observation as observation_module

        fields = {
            name for name, _ in inspect.get_annotations(observation_module.PublicEvent).items()
        }
        self.assertNotIn("data", fields)


if __name__ == "__main__":
    unittest.main()
