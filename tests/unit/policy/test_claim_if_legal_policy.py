"""ClaimIfLegalPolicy：合法鸣牌候选排序提升至过之前（官方测试房验收口径）。

策略契约：只对 WeightedHeuristicPolicy 的计划做一次稳定重排——peng/chi/
明杠（认领弃牌的鸣牌）移动到过之前，其余候选相对顺序不变；过永远保留
兜底（除非已被官方明确拒绝）；胡牌位置不变。不修改加权启发式默认行为。
"""
from __future__ import annotations

import unittest

from hangma_bot.kernel.actions import (
    Chi,
    Discard,
    Gang,
    GangKind,
    Hu,
    Pass,
    Peng,
    Tile,
    WindowPhase,
)
from hangma_bot.kernel.observation import PublicDiscard
from hangma_bot.policy import ClaimIfLegalPolicy, WeightedHeuristicPolicy
from hangma_bot.policy.legacy_pass import LegacyClaimIfLegalPolicy, LegacyWeightedHeuristicPolicy

from .support import (
    candidates_for,
    keep_keys,
    make_budget,
    make_observation,
    make_request,
    make_rules,
    ranks_by_key,
    rejected,
    rules_from_engine,
    run_choose,
)


def _policy() -> ClaimIfLegalPolicy:
    """与组合根使用相同旧过牌兼容视图，注入固定时钟。"""

    return LegacyClaimIfLegalPolicy(monotonic=lambda: 0.0)


def _weighted() -> WeightedHeuristicPolicy:
    return LegacyWeightedHeuristicPolicy(monotonic=lambda: 0.0)


def _hand(codes) -> tuple:
    return tuple(Tile(code) for code in codes)


def _plan(observation, keys, phase):
    """真实规则引擎产生候选与事实，再走 claim_if_legal 排序。"""

    analysis = rules_from_engine(observation)
    request = make_request(observation, keep_keys(analysis, keys), phase=phase)
    return run_choose(_policy(), request, make_budget())


def _structural_plan(actions, phase, rejected_keys=()):
    observation = make_observation(
        phase="response_peng" if phase is WindowPhase.RESPONSE_PENG else "response_chi",
        responding_seats=(0,),
        last_discard=PublicDiscard(seat=3, tile=Tile("2w"), seq=9),
    )
    request = make_request(
        observation,
        make_rules(candidates_for(actions)),
        rejected=tuple(rejected(key) for key in rejected_keys),
        phase=phase,
    )
    return run_choose(_policy(), request, make_budget())


class ClaimPromotionTests(unittest.TestCase):
    """合法鸣牌候选排序高于过；其余口径沿用加权启发式。"""

    def test_peng_that_loses_to_pass_is_promoted(self):
        """碰反例（碰后仍离听牌，加权口径下过排在前）仍被提升到过之前。"""

        observation = make_observation(
            phase="response_peng",
            responding_seats=(0,),
            turn_seat=1,
            my_hand=_hand(
                ("5w", "5w", "9b", "8t", "4t", "6w", "北", "7b", "9t", "4b", "7t", "8t", "8b")
            ),
            last_discard=PublicDiscard(seat=1, tile=Tile("5w"), seq=9),
        )
        # 原样本在完整舍牌计算后碰可直接听牌；改用碰后仍两向听的
        # 真实牌形，继续验证加权策略不愿碰时 claim_if_legal 的提升行为。
        # 对照：默认加权启发式在此输入下过排在碰之前
        analysis = rules_from_engine(observation)
        weighted_plan = run_choose(
            _weighted(),
            make_request(
                observation, keep_keys(analysis, ["peng:5w", "pass"]),
                phase=WindowPhase.RESPONSE_PENG,
            ),
            make_budget(),
        )
        weighted_ranks = ranks_by_key(weighted_plan)
        self.assertLess(weighted_ranks["pass"], weighted_ranks["peng:5w"])

        plan = _plan(observation, ["peng:5w", "pass"], WindowPhase.RESPONSE_PENG)
        ranks = ranks_by_key(plan)
        self.assertLess(ranks["peng:5w"], ranks["pass"])
        self.assertEqual(plan.candidates[0].action_key, "peng:5w")
        # 过兜底保留、排名升序、无重复
        self.assertEqual([item.rank for item in plan.candidates], [1, 2])

    def test_chi_that_loses_to_pass_is_promoted(self):
        """吃反例（吃后仍离听牌）仍被提升到过之前，过保留兜底。"""

        observation = make_observation(
            phase="response_chi",
            responding_seats=(0,),
            turn_seat=3,
            my_hand=_hand(
                ("1w", "2w", "1t", "2t", "3t", "4t", "5t", "6t", "7t", "8t", "东", "2b", "9b")
            ),
            last_discard=PublicDiscard(seat=3, tile=Tile("3w"), seq=9),
        )
        plan = _plan(observation, ["chi:1w,2w,3w", "pass"], WindowPhase.RESPONSE_CHI)
        ranks = ranks_by_key(plan)
        self.assertLess(ranks["chi:1w,2w,3w"], ranks["pass"])
        self.assertEqual(
            [item.action_key for item in plan.candidates], ["chi:1w,2w,3w", "pass"]
        )

    def test_hu_stays_above_claims(self):
        """胡牌候选位置不变：仍高于被提升的鸣牌候选。"""

        plan = _structural_plan(
            [Pass(), Peng(Tile("2w")), Hu()], WindowPhase.RESPONSE_PENG
        )
        self.assertEqual(
            [item.action_key for item in plan.candidates], ["hu", "peng:2w", "pass"]
        )

    def test_exposed_gang_is_claim_concealed_is_not(self):
        """明杠（认领弃牌）是鸣牌候选参与提升；暗杠不是，位置不动。"""

        plan = _structural_plan(
            [
                Pass(),
                Peng(Tile("2w")),
                Gang(Tile("6w"), GangKind.CONCEALED),
                Gang(Tile("6w"), GangKind.EXPOSED),
                Hu(),
            ],
            WindowPhase.RESPONSE_PENG,
        )
        self.assertEqual(
            [item.action_key for item in plan.candidates],
            [
                "hu",
                "gang:concealed:6w",
                "gang:exposed:6w",
                "peng:2w",
                "pass",
            ],
        )

    def test_claims_keep_relative_order_without_pass(self):
        """无过候选时鸣牌追加到末尾，鸣牌之间保持加权启发式相对顺序。"""

        plan = _structural_plan(
            [Chi((Tile("1w"), Tile("2w"), Tile("3w"))), Peng(Tile("2w"))],
            WindowPhase.RESPONSE_CHI,
        )
        keys = [item.action_key for item in plan.candidates]
        self.assertEqual(keys, ["peng:2w", "chi:1w,2w,3w"])  # 碰 -6 > 吃 -10
        self.assertEqual([item.rank for item in plan.candidates], [1, 2])


class PlanInvariantTests(unittest.TestCase):
    """计划不变量与默认行为隔离。"""

    def test_no_claims_identical_to_weighted_heuristic(self):
        """无鸣牌候选时与加权启发式输出完全一致（不改变默认行为口径）。"""

        actions = [Discard(Tile("1w")), Discard(Tile("2w")), Pass()]
        observation = make_observation(phase="draw", responding_seats=())
        request = make_request(
            observation, make_rules(candidates_for(actions)), phase=WindowPhase.DRAW
        )
        weighted = run_choose(_weighted(), request, make_budget())
        claim = run_choose(_policy(), request, make_budget())
        self.assertEqual(
            [item.action_key for item in weighted.candidates],
            [item.action_key for item in claim.candidates],
        )
        self.assertEqual(weighted.degraded_reasons, claim.degraded_reasons)

    def test_rejected_claim_filtered_and_pass_retained(self):
        """被官方明确拒绝的鸣牌照旧过滤，过兜底保留。"""

        plan = _structural_plan(
            [Peng(Tile("2w")), Pass()], WindowPhase.RESPONSE_PENG,
            rejected_keys=("peng:2w",),
        )
        self.assertEqual([item.action_key for item in plan.candidates], ["pass"])

    def test_rejected_pass_drops_pass_but_keeps_claim(self):
        """过被官方拒绝时不再保留；剩余鸣牌候选正常输出。"""

        plan = _structural_plan(
            [Peng(Tile("2w")), Pass()], WindowPhase.RESPONSE_PENG,
            rejected_keys=("pass",),
        )
        self.assertEqual([item.action_key for item in plan.candidates], ["peng:2w"])

    def test_emergency_flag_preserved_after_promotion(self):
        """紧急候选（过）被提升重排后仍保留在计划中且 is_emergency 不变。"""

        pass_candidate = next(
            iter(candidates_for([Pass()]))
        )
        peng_candidate = next(iter(candidates_for([Peng(Tile("2w"))])))
        observation = make_observation(
            phase="response_peng", responding_seats=(0,),
            last_discard=PublicDiscard(seat=3, tile=Tile("2w"), seq=9),
        )
        request = make_request(
            observation,
            make_rules([pass_candidate, peng_candidate], emergency=pass_candidate),
            phase=WindowPhase.RESPONSE_PENG,
        )
        plan = run_choose(_policy(), request, make_budget())
        pass_items = [item for item in plan.candidates if item.action_key == "pass"]
        self.assertEqual(len(pass_items), 1)
        self.assertTrue(pass_items[0].is_emergency)
        self.assertIn("peng:2w", [item.action_key for item in plan.candidates])

    def test_deterministic_same_input_same_plan(self):
        """同输入同配置输出逐字节一致。"""

        observation = make_observation(
            phase="response_peng",
            responding_seats=(0,),
            turn_seat=1,
            my_hand=_hand(
                ("5w", "5w", "1t", "2t", "3t", "4t", "5t", "6t", "1b", "2b", "8t", "9t", "东")
            ),
            last_discard=PublicDiscard(seat=1, tile=Tile("5w"), seq=9),
        )
        analysis = rules_from_engine(observation)
        request = make_request(
            observation, keep_keys(analysis, ["peng:5w", "pass"]),
            phase=WindowPhase.RESPONSE_PENG,
        )
        first = run_choose(_policy(), request, make_budget())
        second = run_choose(_policy(), request, make_budget())
        self.assertEqual(
            [item.action_key for item in first.candidates],
            [item.action_key for item in second.candidates],
        )
        self.assertEqual(first.degraded_reasons, second.degraded_reasons)


if __name__ == "__main__":
    unittest.main()
