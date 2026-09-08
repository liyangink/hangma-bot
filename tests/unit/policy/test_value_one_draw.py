"""一次摸牌分值候选的公开 choose 行为与真实可见观察回归。"""

import asyncio
import json
from dataclasses import replace
from pathlib import Path

import pytest

from hangma_bot.application.audit_codec import decision_request_from_json
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import (
    CandidateFactKind, CandidateFacts, CandidateValueFacts, RuleCandidate,
    RuleCompleteness, RuleIssue, Settlement, UsefulTileFact, ValueAnalysisLimits,
    ValueConditions, ValueCoverage, ValueRoute,
)
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER, Chi, Discard, Gang, GangKind, Hu, Pass, Peng, Tile, action_key
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.policy.errors import PolicyTimeoutError
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
from hangma_bot.policy.value_one_draw import OneDrawValuePolicy
from hangma_bot.policy.weights_v1 import DEFAULT_WEIGHTS_V1

from .support import make_budget, make_observation, make_request, make_rules, rejected


def progress(shanten=0, unseen=4, **kwargs):
    """只构造输入契约，不在策略测试中复刻规则牌型数学。"""

    useful = tuple(UsefulTileFact(code, min(4, unseen - index * 4))
                   for index, code in enumerate(CANONICAL_TILE_ORDER) if unseen > index * 4)
    return CandidateFacts(CandidateFactKind.HAND_PROGRESS, shanten, useful, **kwargs)


def route(unseen=4, score=10, *, followup=None, seat=0, start=0, draw_kind="normal"):
    """造一个带座位顺序净分向量的条件见证，实际牌型由规则测试覆盖。"""

    useful = tuple(UsefulTileFact(code, min(4, unseen - index * 4))
                   for index, code in enumerate(CANONICAL_TILE_ORDER[start:]) if unseen > index * 4)
    scores = [0, 0, 0, 0]
    scores[seat] = score
    scores[(seat + 1) % 4] = -score
    melds = 1 if followup is not None else 0
    return ValueRoute(
        conditional_settlement=Settlement(tuple(scores), 1, ("受控条件见证",)),
        shanten=0,
        useful_tiles=useful,
        followup_discard=followup,
        conditions=ValueConditions(draw_kind, CANONICAL_TILE_ORDER[:13 - 3 * melds], melds, 0, 0, False),
    )


def value(*routes):
    return CandidateValueFacts(routes=routes, coverage=ValueCoverage.COMPLETE)


def candidate(action, *, unseen=4, shanten=0, score=10, facts=None, value_facts=None):
    return RuleCandidate(
        action, action_key(action), (),
        progress(shanten, unseen) if facts is None else facts,
        value(route(unseen, score)) if value_facts is None else value_facts,
    )


def request_for(candidates, *, observation=None, emergency=None, rejected_attempts=()):
    return make_request(
        observation or make_observation(), make_rules(candidates, emergency), rejected=rejected_attempts,
    )


def choose(request, *, value_weight=1, weights=DEFAULT_WEIGHTS_V1, clock=lambda: 0):
    return asyncio.run(OneDrawValuePolicy(weights, clock, value_weight=value_weight).choose(request, make_budget()))


def baseline(request, *, weights=DEFAULT_WEIGHTS_V1, clock=lambda: 0):
    return asyncio.run(ComparableHeuristicPolicyV2(weights, clock).choose(request, make_budget()))


def test_same_shanten_uses_score_and_outs_instead_of_largest_fan_or_most_outs_alone():
    ordinary = candidate(Discard(Tile("1w")), unseen=8, score=10)
    valuable = candidate(Discard(Tile("2w")), unseen=4, score=30)
    largest = candidate(Discard(Tile("3w")), unseen=1, score=80)
    request = request_for([ordinary, valuable, largest], emergency=ordinary)
    old = baseline(request)
    new = choose(request)
    assert old.candidates[0].action_key == ordinary.action_key
    assert [item.action_key for item in new.candidates] == [valuable.action_key, ordinary.action_key, largest.action_key]
    assert [item.total_score for item in new.candidates] == [120, 80, 80]
    for item in new.candidates:
        previous = next(c for c in old.candidates if c.action_key == item.action_key)
        assert item.score_parts[:len(previous.score_parts)] == previous.score_parts
        assert item.total_score == sum(part.value for part in item.score_parts)
        assert "不是成胡概率或整单局期望" in " ".join(item.reasons)
        assert item.is_emergency == previous.is_emergency
    assert new == choose(request)


def test_scores_use_our_seat_instead_of_assuming_seat_zero_or_dealer():
    first = candidate(Discard(Tile("1w")), value_facts=value(route(4, 20, seat=2)))
    second = candidate(Discard(Tile("2w")), value_facts=value(route(4, 30, seat=2)))
    plan = choose(request_for([first, second], observation=make_observation(seat=2, dealer_seat=1)))
    assert plan.candidates[0].action_key == second.action_key
    assert plan.candidates[0].total_score == 120


@pytest.mark.parametrize("weight", [0, 0.0])
def test_zero_weight_is_the_exact_v2_ablation(weight):
    request = request_for([
        candidate(Discard(Tile("1w")), unseen=8),
        candidate(Discard(Tile("2w")), unseen=4, score=80),
    ])
    assert choose(request, value_weight=weight) == baseline(request)


@pytest.mark.parametrize("weight", [True, -1, 0.5, 2, float("nan"), float("inf"), "1"])
def test_interpolation_and_invalid_weights_are_rejected(weight):
    with pytest.raises(ValueError, match="只允许 0 或 1"):
        OneDrawValuePolicy(value_weight=weight)


@pytest.mark.parametrize("missing", [
    None,
    CandidateValueFacts(coverage=ValueCoverage.PARTIAL, issues=(RuleIssue("value", "达到工作量上限"),)),
    CandidateValueFacts(coverage=ValueCoverage.UNAVAILABLE, issues=(RuleIssue("value", "缺少规则见证"),)),
])
def test_missing_or_partial_value_facts_keep_the_entire_v2_plan(missing):
    first = candidate(Discard(Tile("1w")), unseen=8)
    second = replace(candidate(Discard(Tile("2w")), score=80), value_facts=missing)
    request = request_for([first, second], emergency=first)
    assert choose(request) == baseline(request)


def test_complete_empty_routes_are_zero_in_scope_and_all_zero_keeps_baseline():
    dead = candidate(Discard(Tile("1w")), unseen=8, value_facts=value())
    live = candidate(Discard(Tile("2w")), unseen=4)
    request = request_for([dead, live])
    assert baseline(request).candidates[0].action_key == dead.action_key
    assert choose(request).candidates[0].action_key == live.action_key
    empty = replace(live, value_facts=value())
    all_empty = request_for([dead, empty])
    assert choose(all_empty) == baseline(all_empty)


@pytest.mark.parametrize("action", [Peng(Tile("5w")), Chi((Tile("1w"), Tile("2w"), Tile("3w")))])
def test_claim_followups_take_one_maximum_and_never_sum_incompatible_discards(action):
    wait = candidate(Pass(), unseen=6, score=10)
    claim = candidate(action, unseen=20, value_facts=value(
        route(4, 10, followup="2w"), route(4, 10, followup="1w"),
    ))
    request = request_for([wait, claim], emergency=wait)
    assert baseline(request).candidates[0].action_key == claim.action_key
    plan = choose(request)
    assert plan.candidates[0].action_key == "pass"
    ranked_claim = next(item for item in plan.candidates if item.action_key == claim.action_key)
    assert ranked_claim.total_score == 40
    assert "先弃1w" in " ".join(ranked_claim.reasons)

    # 下一窗口采用同一标尺和动作键平局规则，执行估值时选定的方案。
    followups = request_for([candidate(Discard(Tile("2w"))), candidate(Discard(Tile("1w")))])
    assert choose(followups).candidates[0].action_key == "discard:1w"


def test_disjoint_tiles_for_one_followup_are_added_but_duplicate_witnesses_keep_v2():
    first = candidate(Discard(Tile("1w")), unseen=8, score=10)
    second = candidate(Discard(Tile("2w")), value_facts=value(route(4, 10), route(4, 20, start=1)))
    request = request_for([first, second])
    assert choose(request).candidates[0].total_score == 120
    duplicate = replace(second, value_facts=value(route(4, 10), route(4, 20)))
    malformed = request_for([first, duplicate])
    degraded = choose(malformed)
    assert degraded.candidates == baseline(malformed).candidates
    assert "重复计数" in " ".join(degraded.degraded_reasons)


def test_immediate_hu_is_always_the_unchanged_v2_plan():
    hu = RuleCandidate(Hu(), "hu", ())
    huge = candidate(Discard(Tile("1w")), unseen=4, score=100000)
    request = request_for([hu, huge])
    weights = replace(DEFAULT_WEIGHTS_V1, win_now=-10000)
    assert choose(request, weights=weights) == baseline(request, weights=weights)
    assert choose(request, weights=weights).candidates[0].action_key == "hu"


def test_non_ready_v2_first_choice_is_not_overridden_by_a_large_conditional_route():
    progress_first = candidate(Discard(Tile("1w")), shanten=1, unseen=80)
    ready_white = candidate(Discard(Tile("白")), unseen=4, score=10000)
    request = request_for([progress_first, ready_white])
    assert baseline(request).candidates[0].action_key == progress_first.action_key
    assert choose(request) == baseline(request)


def test_gang_first_keeps_baseline_and_normal_groups_do_not_cross_a_gang():
    first = candidate(Discard(Tile("1w")), unseen=12)
    gang = candidate(Gang(Tile("5w"), GangKind.CONCEALED), unseen=4)
    last = candidate(Discard(Tile("2w")), unseen=4, score=80)
    request = request_for([first, gang, last])
    assert baseline(request).candidates[0].action_key == gang.action_key
    assert choose(request) == baseline(request)
    weights = replace(DEFAULT_WEIGHTS_V1, gang_bonus=4)
    old = baseline(request, weights=weights)
    new = choose(request, weights=weights)
    assert [item.action_key for item in old.candidates] == [first.action_key, gang.action_key, last.action_key]
    assert [item.action_key for item in new.candidates] == [item.action_key for item in old.candidates]
    assert new.candidates[1] == old.candidates[1]


def test_replacement_routes_are_not_mixed_into_normal_waiting_scores():
    first = candidate(Discard(Tile("1w")), unseen=8)
    second = candidate(Discard(Tile("2w")), value_facts=value(route(4, 80, draw_kind="replacement")))
    request = request_for([first, second])
    assert choose(request) == baseline(request)


def test_v2_intake_filters_and_emergency_candidate_survive_value_sorting():
    first = candidate(Discard(Tile("1w")), unseen=8)
    second = candidate(Discard(Tile("2w")), unseen=4, score=40)
    refused = candidate(Discard(Tile("3w")), score=10000)
    unknown = RuleCandidate(Discard(Tile("9b")), "discard:9b", ())
    bad_key = replace(candidate(Discard(Tile("9w"))), action_key=second.action_key)
    duplicate = replace(second, value_facts=None)
    request = request_for(
        [first, bad_key, second, duplicate, refused, unknown],
        emergency=unknown, rejected_attempts=(rejected(refused.action_key),),
    )
    new = choose(request)
    old = baseline(request)
    assert [item.action_key for item in new.candidates] == [second.action_key, first.action_key, unknown.action_key]
    assert new.candidates[-1] == old.candidates[-1]
    assert new.candidates[-1].is_emergency
    assert new.revision == 2
    assert new.degraded_reasons == old.degraded_reasons


def test_missing_first_duplicate_is_not_replaced_with_a_later_complete_duplicate():
    first = candidate(Discard(Tile("1w")), unseen=8)
    duplicate = candidate(Discard(Tile("2w")), score=80)
    request = request_for([first, replace(duplicate, value_facts=None), duplicate])
    assert choose(request) == baseline(request)


@pytest.mark.parametrize("items,refused", [([], ()), ([RuleCandidate(Pass(), "pass", ())], ()), ([candidate(Discard(Tile("1w")))], (rejected("discard:1w"),))])
def test_empty_unknown_and_exhausted_requests_preserve_v2(items, refused):
    request = request_for(items, rejected_attempts=refused, emergency=items[0] if items else None)
    assert choose(request) == baseline(request)


def test_expired_value_phase_keeps_v2_while_baseline_timeout_and_cancellation_propagate():
    request = request_for([candidate(Discard(Tile("1w"))), candidate(Discard(Tile("2w")), score=80)])
    calls = []
    baseline(request, clock=lambda: calls.append(0) or 0)
    baseline_clock_calls = len(calls)
    calls.clear()
    def expires_after_baseline():
        calls.append(0)
        return 0 if len(calls) <= baseline_clock_calls else 101
    degraded = choose(request, clock=expires_after_baseline)
    assert degraded.candidates == baseline(request).candidates
    assert "一次摸牌分值计算超过增强截止时间" in " ".join(degraded.degraded_reasons)
    with pytest.raises(PolicyTimeoutError):
        choose(request, clock=lambda: 999)
    async def cancel():
        task = asyncio.create_task(OneDrawValuePolicy(monotonic=lambda: 0).choose(request, make_budget()))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(cancel())
    async def cancel_during_enhancement():
        entered = asyncio.Event()
        ticks = []
        def clock():
            ticks.append(0)
            if len(ticks) > baseline_clock_calls:
                entered.set()
            return 0
        task = asyncio.create_task(OneDrawValuePolicy(monotonic=clock).choose(request, make_budget()))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(cancel_during_enhancement())


@pytest.mark.parametrize("score", [float("inf"), float("nan"), -1, 0])
def test_invalid_winner_score_keeps_v2_and_records_the_failure(score):
    request = request_for([
        candidate(Discard(Tile("1w"))),
        candidate(Discard(Tile("2w")), value_facts=value(route(4, score))),
    ])
    degraded = choose(request)
    assert degraded.candidates == baseline(request).candidates
    assert "正的有限数值" in " ".join(degraded.degraded_reasons)


def test_malformed_enhancement_payload_does_not_discard_a_completed_v2_plan():
    first = candidate(Discard(Tile("1w")), unseen=8)
    second = candidate(Discard(Tile("2w")), value_facts=value(object()))
    request = request_for([first, second], emergency=second)
    degraded = choose(request)
    old = baseline(request)
    assert degraded.candidates == old.candidates
    assert degraded.candidates[0].action_key == first.action_key
    assert "一次摸牌增强失败" in " ".join(degraded.degraded_reasons)
    assert degraded.decision_id == old.decision_id
    assert degraded.window_key == old.window_key
    assert degraded.based_on_authoritative_seq == old.based_on_authoritative_seq
    assert degraded.revision == old.revision


def recorded_request(case_id):
    """仅读取历史玩家可见请求，所有规则事实按当前规则重新生产。"""

    path = Path(__file__).parents[2] / "fixtures" / "policy" / "one-draw-value" / (case_id + ".json")
    row = json.loads(path.read_text(encoding="utf-8"))
    request = decision_request_from_json(row["request_event"]["payload"]["request"])
    rules = HangmaRules(RuleConfig("policy-one-draw-test", 1, False))
    return replace(request, rules=rules.analyze(request.observation, value_limits=ValueAnalysisLimits()))


@pytest.mark.parametrize("case_id,old_action,new_action", [
    ("B", "discard:1b", "discard:3b"),
    ("C", "discard:6w", "discard:5w"),
    ("D", "peng:发", "pass"),
    ("G", "peng:南", "peng:南"),
])
def test_real_same_shanten_examples_use_conditional_value_and_keep_profitable_claims(case_id, old_action, new_action):
    request = recorded_request(case_id)
    old = baseline(request)
    new = choose(request)
    assert request.rules.completeness is RuleCompleteness.COMPLETE
    assert old.candidates[0].action_key == old_action
    assert new.candidates[0].action_key == new_action
    assert {item.action_key for item in new.candidates} == {item.action_key for item in old.candidates}
    assert "不是成胡概率或整单局期望" in " ".join(new.candidates[0].reasons)


@pytest.mark.parametrize("case_id", ["A", "F"])
def test_real_available_hu_is_preserved_without_declining_for_a_bigger_hand(case_id):
    request = recorded_request(case_id)
    assert choose(request) == baseline(request)
    assert choose(request).candidates[0].action_key == "hu"


def test_real_gang_example_exposes_higher_value_routes_without_changing_gang_tradeoff():
    request = recorded_request("E")
    assert isinstance(baseline(request).candidates[0].action, Gang)
    assert choose(request) == baseline(request)
    discard = next(candidate for candidate in request.rules.legal_candidates if candidate.action_key == "discard:中")
    assert discard.value_facts.coverage is ValueCoverage.COMPLETE
    assert any(route.conditional_settlement.fan >= 4 for route in discard.value_facts.routes)
