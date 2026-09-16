"""价值族④（期望实际积分：概率代理 × 番值 × 庄闲结算）的契约与行为测试。

四组断言：

  C 组（契约）：静态注册、参数往返进身份、bound 由声明域推导、未知键拒绝、
      适配器是唯一钳制点、纯函数与确定性；
  R 组（规则单一来源与量纲）：结算系数逐项等于 settlement.settle_scores、
      对照常量等于其座位平均、庄闲失明模式下与座位无关；
  P 组（路径进展三态）：七对被副露永久关闭是**规则已证**、四白等值条件与
      "需求超出可得即不可达"、爆头未成立时不填零、链越界/墙余量未知时**不评分**；
  D 组（消融与方向）：代价项可关、路径进展可关、动作标签无关、兑现代理单调。

**本文件不构成准入或效果证据**：只证明结构与接线（README §17.1 第 3 条）。
"""

import math
from dataclasses import replace

import pytest

from hangma_bot.hangma.interface import RuleCandidate
from hangma_bot.hangma.settlement import settle_scores
from hangma_bot.kernel.actions import (
    Chi,
    Discard,
    Hu,
    Pass,
    Peng,
    Tile,
    action_key,
)
from hangma_bot.policy.evaluation_v1 import ScoredCandidate, build_context
from hangma_bot.policy import heuristics
from hangma_bot.policy.heuristics import expected_score_path_value as es

from .support import WEALTH_CODE, make_observation, rules_from_engine

PARAMS = es.ExpectedScoreParams()

#: 合法 13 张手牌（每码 ≤ 4 张，物理可得）；测试夹具不用"13 张同码"这类非法输入。
LEGAL_WEALTH_HAND = ("白",) * 4 + ("1w",) * 3 + ("2b",) * 3 + ("3t",) * 3


def _cand(action, facts=None) -> RuleCandidate:
    return RuleCandidate(action=action, action_key=action_key(action),
                         evidence=(), facts=facts)


def _observation(codes, *, drawn=None, seat=0, dealer=0, wall=60, baotou=False,
                 chain=0, piao=None, **extra):
    return make_observation(
        my_hand=tuple(Tile(code) for code in codes),
        drawn_tile=None if drawn is None else Tile(drawn),
        seat=seat, dealer_seat=dealer, remaining_tile_count=wall,
        rule_state=replace(make_observation().rule_state, baotou=baotou,
                           chain_count=chain), **extra)


def _ctx(observation, **overrides):
    return replace(build_context(observation), **overrides)


def _discard_ctx(codes, tile_code, **overrides):
    observation = _observation(codes)
    analysis = rules_from_engine(observation)
    candidate = next(c for c in analysis.legal_candidates
                     if c.action_key == "discard:{0}".format(tile_code))
    return candidate, _ctx(observation, **overrides), analysis


# --- C 组：契约 -----------------------------------------------------------------


def test_candidate_is_registered_in_the_static_registry() -> None:
    assert heuristics.is_candidate("expected_score_path_value")


def test_declared_spec_is_complete() -> None:
    adjustment = es.build_adjustment()
    assert adjustment.spec.name
    assert adjustment.spec.trigger.strip()
    assert adjustment.spec.thought.strip()
    assert adjustment.spec.version == es.EXPECTED_SCORE_VERSION
    assert adjustment.spec.bound == PARAMS.derived_bound


def test_bound_is_derived_from_the_declared_domain() -> None:
    """bound 由声明域推导：pps × (fan_cap × 收益上界 + 他家番代理 × 支付上界)。"""

    gain_max = float(max(settle_scores(1, es.SETTLEMENT_BASE_SCORE, seat, seat)[seat]
                         for seat in range(4)))
    pay_max = float(max(-settle_scores(1, es.SETTLEMENT_BASE_SCORE, winner, dealer)[payer]
                        for winner in range(4) for dealer in range(4)
                        for payer in range(4) if payer != winner))
    assert gain_max == 24.0          # 庄家自摸：三家各付 ×8
    assert pay_max == 8.0            # 付方倍率上限
    expected = PARAMS.points_per_score * (
        PARAMS.fan_cap * gain_max + float(PARAMS.opp_fan_proxy) * pay_max)
    assert PARAMS.derived_bound == pytest.approx(expected)


def test_parameters_round_trip_through_the_identity() -> None:
    first = es.build_adjustment(es.ExpectedScoreParams(points_per_score=3.0))
    second = es.build_adjustment(es.ExpectedScoreParams(points_per_score=3.0))
    other = es.build_adjustment(es.ExpectedScoreParams(points_per_score=1.0))
    assert first.identity() == second.identity()
    assert first.identity() != other.identity()
    assert es.build_adjustment_from_params({"points_per_score": 3.0}).identity() == first.identity()


def test_dealer_mode_changes_the_identity() -> None:
    real = es.build_adjustment(es.ExpectedScoreParams(use_dealer_parity=1.0))
    blind = es.build_adjustment(es.ExpectedScoreParams(use_dealer_parity=0.0))
    assert real.identity() != blind.identity()


def test_unknown_parameter_key_is_rejected() -> None:
    with pytest.raises(ValueError):
        es.build_adjustment_from_params({"loss_absolute": 1.0})


def test_scope_covers_every_action_kind() -> None:
    adjustment = es.build_adjustment()
    for kind in ("chi", "peng", "gang", "discard", "pass", "hu"):
        assert adjustment.applies_to("{0}:x".format(kind))


def test_adapter_is_the_only_clamp_and_it_does_not_fire() -> None:
    candidate, ctx, _ = _discard_ctx(("1w", "1w", "2b", "3t", "4t", "5t", "6t",
                                     "7t", "8t", "9t", "2w", "3w", "4w"), "9t")
    adjustment = es.build_adjustment()
    item = ScoredCandidate(priority=1, candidate=candidate, action_key=candidate.action_key,
                           parts=(), reasons=(), total=0.0, shanten=None,
                           is_safe_discard=False)
    applied = adjustment.apply(item, ctx, (candidate,))
    assert adjustment.clamped_count == 0
    if applied.parts:
        assert abs(applied.parts[-1].value) <= adjustment.spec.bound


def test_delta_is_deterministic_and_does_not_mutate_inputs() -> None:
    candidate, ctx, _ = _discard_ctx(("1w", "1w", "2b", "3t", "4t", "5t", "6t",
                                     "7t", "8t", "9t", "2w", "3w", "4w"), "9t")
    first = es.expected_points(candidate, ctx, PARAMS)
    second = es.expected_points(candidate, ctx, PARAMS)
    assert first == second


# --- R 组：规则单一来源与量纲 ---------------------------------------------------


def test_settlement_factors_come_from_settle_scores() -> None:
    observation = _observation(("1w",) * 4 + ("2b",) * 4 + ("3t",) * 4 + ("5w",), seat=1, dealer=1)
    ctx = _ctx(observation)
    gain, pay = es.settlement_factors(ctx, PARAMS)
    assert gain == float(settle_scores(1, 1, 1, 1)[1]) == 24.0
    for seat in range(4):
        if seat == ctx.my_seat:
            assert pay[seat] == 0.0
        else:
            assert pay[seat] == float(-settle_scores(1, 1, seat, ctx.dealer_seat)[ctx.my_seat])


def test_non_dealer_pays_eight_to_the_dealer_and_one_to_others() -> None:
    ctx = _ctx(_observation(("1w",) * 4 + ("2b",) * 4 + ("3t",) * 4 + ("5w",), seat=2, dealer=0))
    gain, pay = es.settlement_factors(ctx, PARAMS)
    assert gain == 10.0
    assert pay[0] == 8.0     # 庄家胡：付 ×8
    assert pay[1] == 1.0     # 闲家胡：付 ×1
    assert pay[3] == 1.0
    assert pay[2] == 0.0     # 本人座位不付给自己


def test_dealer_seat_sees_every_opponent_at_eight() -> None:
    ctx = _ctx(_observation(("1w",) * 4 + ("2b",) * 4 + ("3t",) * 4 + ("5w",), seat=3, dealer=3))
    gain, pay = es.settlement_factors(ctx, PARAMS)
    assert gain == 24.0
    assert [pay[seat] for seat in (0, 1, 2)] == [8.0, 8.0, 8.0]


def test_blind_factor_is_the_seat_average_and_dealer_independent() -> None:
    gain_const, pay_const = es.blind_settlement_factors()
    gains = [settle_scores(1, 1, seat, dealer)[seat]
             for seat in range(4) for dealer in range(4)]
    assert gain_const == pytest.approx(sum(gains) / len(gains))
    legal = ("1w",) * 4 + ("2b",) * 4 + ("3t",) * 4 + ("5w",)
    dealer_ctx = _ctx(_observation(legal, seat=0, dealer=0))
    blind_ctx = _ctx(_observation(legal, seat=0, dealer=2))
    blind = es.ExpectedScoreParams(use_dealer_parity=0.0)
    assert es.settlement_factors(dealer_ctx, blind) == es.settlement_factors(blind_ctx, blind)


# --- P 组：路径进展三态 ---------------------------------------------------------


def test_chiitoi_path_closed_by_melds_is_rule_proven_not_unknown() -> None:
    ctx = _ctx(_observation(("1w",) * 2 + ("2b",) * 2 + ("3t",) * 2 + ("4w",) * 2
                            + ("5b",) * 2 + ("6t",) * 2 + ("7w",), seat=0, dealer=0))
    state = es.ActionState(branch_log2=0.0, chiitoi_alive=False, locked_groups=0,
                           chain_count=0, wealth_after=0, piao_after=0,
                           four_white=False, baotou=False)
    reach, label = es.chiitoi_reach(state, None, 60)
    assert reach == 0.0
    assert label == es.IMPOSSIBLE


def test_four_white_reach_is_closed_form_and_rule_proven() -> None:
    ctx = _ctx(_observation(LEGAL_WEALTH_HAND))
    reached = es.ActionState(branch_log2=1.0, chiitoi_alive=True, locked_groups=0,
                             chain_count=0, wealth_after=4, piao_after=0,
                             four_white=True, baotou=False)
    assert es.four_white_reach(reached, 60, ctx)[0] == 1.0
    # 手留 0 张、需要 4 张但只剩 4 张可得：可达（不是 0）
    distant = replace(reached, four_white=False, wealth_after=0, piao_after=0)
    assert 0.0 < es.four_white_reach(distant, 60, ctx)[0] < 1.0


def test_four_white_unknown_piao_uses_a_conservative_bound_not_zero() -> None:
    ctx = _ctx(_observation(("白",) * 2 + ("1w",) * 4 + ("2b",) * 4 + ("3t",) * 3, chain=3))
    state = es.ActionState(branch_log2=1.0, chiitoi_alive=True, locked_groups=0,
                           chain_count=3, wealth_after=2, piao_after=None,
                           four_white=None, baotou=True)
    value, note = es.four_white_reach(state, 60, ctx)
    assert value > 0.0
    assert note is not None and "保守下界" in note


def test_baotou_not_reached_is_registered_as_unappraised() -> None:
    candidate, ctx, _ = _discard_ctx(("1w", "1w", "2b", "3t", "4t", "5t", "6t",
                                     "7t", "8t", "9t", "2w", "3w", "4w"), "9t")
    appraisal = es.appraise(candidate, ctx, PARAMS)
    assert appraisal is not None
    assert any(item.startswith("baotou=") for item in appraisal.unappraised)


def test_out_of_domain_chain_is_not_appraised_rather_than_penalised() -> None:
    candidate, ctx, _ = _discard_ctx(("1w", "1w", "2b", "3t", "4t", "5t", "6t",
                                     "7t", "8t", "9t", "2w", "3w", "4w"), "9t")
    broken = replace(ctx, chain_count=es.MAX_CHAIN_COUNT + 1)
    assert es.appraise(candidate, broken, PARAMS) is None


def test_unknown_wall_is_not_appraised() -> None:
    candidate, ctx, _ = _discard_ctx(("1w", "1w", "2b", "3t", "4t", "5t", "6t",
                                     "7t", "8t", "9t", "2w", "3w", "4w"), "9t")
    assert es.appraise(candidate, replace(ctx, remaining_tile_count=None), PARAMS) is None


def test_missing_progress_facts_is_not_appraised() -> None:
    candidate, ctx, _ = _discard_ctx(("1w", "1w", "2b", "3t", "4t", "5t", "6t",
                                     "7t", "8t", "9t", "2w", "3w", "4w"), "9t")
    bare = _cand(candidate.action)
    assert es.appraise(bare, ctx, PARAMS) is None
    assert es.expected_points(bare, ctx, PARAMS) == 0.0


def test_win_is_terminal_and_not_appraised() -> None:
    ctx = _ctx(_observation(("1w",) * 4 + ("2b",) * 4 + ("3t",) * 4 + ("5w",)))
    assert es.appraise(_cand(Hu()), ctx, PARAMS) is None
    assert es.expected_points(_cand(Hu()), ctx, PARAMS) == 0.0


def test_discarding_the_wealth_tile_loses_the_four_white_reach() -> None:
    """四白是**等值条件**：打掉一张财神就从"已成立"掉到"还需要一张"。"""

    # 合法手牌（每码 ≤ 4 张）：手留 4 张财神 ⇒ 四白已成立。
    ctx = _ctx(_observation(LEGAL_WEALTH_HAND, seat=0), chain_piao=0)
    keep = _cand(Discard(Tile("9b")))
    drop = _cand(Discard(Tile(WEALTH_CODE)))
    kept = es.four_white_reach(es.action_state_after(keep, ctx), 60, ctx)[0]
    dropped = es.four_white_reach(es.action_state_after(drop, ctx), 60, ctx)[0]
    assert kept == 1.0
    assert dropped < kept


# --- D 组：消融与方向 -----------------------------------------------------------


def test_opponent_cost_can_be_ablated() -> None:
    candidate, ctx, _ = _discard_ctx(("1w", "1w", "2b", "3t", "4t", "5t", "6t",
                                     "7t", "8t", "9t", "2w", "3w", "4w"), "9t")
    with_cost = es.appraise(candidate, ctx, PARAMS)
    without = es.appraise(candidate, ctx, es.ExpectedScoreParams(use_opp_cost=0.0))
    assert with_cost is not None and without is not None
    assert without.cost is None
    assert without.net == pytest.approx(without.gain)


def test_path_progress_can_be_ablated() -> None:
    candidate, ctx, _ = _discard_ctx(("1w", "1w", "2b", "3t", "4t", "5t", "6t",
                                     "7t", "8t", "9t", "2w", "3w", "4w"), "9t")
    full = es.appraise(candidate, ctx, PARAMS)
    ablated = es.appraise(candidate, ctx, es.ExpectedScoreParams(use_path_progress=0.0))
    assert full is not None and ablated is not None
    assert ablated.fan_lower_bound <= full.fan_lower_bound


def test_action_labels_do_not_enter_the_value() -> None:
    """同状态同事实的两种鸣牌取值相同：取值只看动作后的规则事实，不看标签。"""

    ctx = _ctx(_observation(("1w", "1w", "2b", "2b", "2b", "3t", "4t", "5t", "6t",
                             "7t", "8t", "9t", "5b")))
    chi = _cand(Chi((Tile("1b"), Tile("2b"), Tile("3b"))))
    peng = _cand(Peng(Tile("2b")))
    assert es.expected_points(chi, ctx, PARAMS) == es.expected_points(peng, ctx, PARAMS)


def test_realisation_chance_is_monotone_in_tiles_and_distance() -> None:
    assert es.hit_once(0.1, 10) > es.hit_once(0.1, 5)
    assert es.path_reach(0.1, 10, 1) > es.path_reach(0.1, 10, 3)
    assert es.remaining_rounds(60) == 15
    assert es.remaining_rounds(None) is None


def test_points_are_finite_and_within_the_declared_bound() -> None:
    candidate, ctx, _ = _discard_ctx(("1w", "1w", "2b", "3t", "4t", "5t", "6t",
                                     "7t", "8t", "9t", "2w", "3w", "4w"), "9t")
    points = es.expected_points(candidate, ctx, PARAMS)
    assert math.isfinite(points)
    assert abs(points) <= PARAMS.derived_bound
