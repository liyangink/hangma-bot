"""V2 可比等待评分、缺基线退路与冻结行为的公开接口验收。"""

import asyncio
from dataclasses import replace

import pytest

from hangma_bot.hangma.interface import CandidateFactKind as Kind, CandidateFacts, RuleCandidate, RuleCompleteness, UsefulTileFact
from hangma_bot.kernel.actions import CANONICAL_TILE_CODES, Chi, Hu, Pass, Peng, Tile, WindowPhase, action_key
from hangma_bot.kernel.observation import PublicDiscard
from hangma_bot.policy import ComparableHeuristicPolicyV2, ReliableHeuristicPolicyV1
from hangma_bot.policy.errors import PolicyTimeoutError
from hangma_bot.policy.weights_v1 import DEFAULT_WEIGHTS_V1
from .support import make_budget, make_observation, make_request, make_rules, rejected, rules_from_engine
from .test_v0_baseline import recorded_request, rows


def progress(shanten, remaining=0, **kwargs):
    """构造受控牌效事实；每牌种估计最多四张，不复刻规则手牌数学。"""
    useful = tuple(UsefulTileFact(code, min(4, remaining - i*4))
                   for i, code in enumerate(CANONICAL_TILE_CODES) if remaining - i*4 > 0)
    return CandidateFacts(Kind.HAND_PROGRESS, shanten, useful_tiles=useful, **kwargs)


def candidate(action, facts=None):
    return RuleCandidate(action, action_key(action), (), facts)


def choose(candidates, *, rejected_attempts=(), weights=DEFAULT_WEIGHTS_V1):
    rules = make_rules(candidates, next((c for c in candidates if isinstance(c.action, Pass)), None))
    request = replace(make_request(make_observation(), rules), rejected_attempts=tuple(rejected_attempts))
    return asyncio.run(ComparableHeuristicPolicyV2(weights, monotonic=lambda: 0).choose(request, make_budget()))


@pytest.mark.parametrize("action,risk", [(Peng(Tile("5w")),6), (Chi((Tile("1w"),Tile("2w"),Tile("3w"))),10)])
@pytest.mark.parametrize("waiting,claimed,prefer_claim", [((2,20),(1,15),True), ((1,15),(1,15),False), ((1,10),(1,25),True), ((0,0),(0,0),False), ((1,20),(2,30),False)])
def test_pass_and_claim_have_comparable_progress(action, risk, waiting, claimed, prefer_claim):
    claim = candidate(action, progress(*claimed, best_followup_discard="9t"))
    plan = choose([candidate(Pass(), progress(*waiting)), claim])
    scores = {c.action_key: c.total_score for c in plan.candidates}
    assert scores["pass"] == -100*waiting[0]+waiting[1]
    assert scores[claim.action_key] == -100*claimed[0]+claimed[1]-risk
    assert plan.candidates[0].action_key == (claim.action_key if prefer_claim else "pass")
    assert all(c.total_score == sum(p.value for p in c.score_parts) for c in plan.candidates)


@pytest.mark.parametrize("facts", [None, CandidateFacts(Kind.NOT_APPLICABLE,None),
    CandidateFacts(Kind.ANALYSIS_FAILED,None,completeness=RuleCompleteness.DEGRADED,note="注入"),
    progress(None),progress(True),progress(-1),progress(1,best_followup_discard="9t"),
    progress(1,replacement_draw_unknown=True),progress(1,completeness=RuleCompleteness.DEGRADED,note="降级")])
def test_missing_baseline_keeps_hu_then_pass_and_never_reintroduces_rejected_actions(facts):
    cs = [candidate(Pass(), facts),candidate(Peng(Tile("5w")),progress(0,30)),candidate(Hu())]
    weights = replace(DEFAULT_WEIGHTS_V1,win_now=-1000)
    assert [c.action_key for c in choose(cs,weights=weights).candidates][:2] == ["hu","pass"]
    plan = choose(cs, rejected_attempts=(rejected("hu"),))
    assert plan.candidates[0].action_key == "pass"
    assert "缺可比等待基线" in " ".join(plan.degraded_reasons)
    plan = choose(cs, rejected_attempts=(rejected("hu"),rejected("pass")))
    assert [c.action_key for c in plan.candidates] == ["peng:5w"]


@pytest.mark.parametrize("row",rows(),ids=lambda row:row["name"])
def test_other_action_scores_remain_v1_on_frozen_requests(row):
    request = recorded_request(row)
    v1 = asyncio.run(ReliableHeuristicPolicyV1(monotonic=lambda:0).choose(request,make_budget()))
    v2 = asyncio.run(ComparableHeuristicPolicyV2(monotonic=lambda:0).choose(request,make_budget()))
    signature = lambda plan: [(c.action_key,c.total_score,c.score_parts) for c in plan.candidates if c.action_key != "pass"]
    assert signature(v2) == signature(v1)


def test_v2_filters_duplicates_bad_keys_and_is_deterministic():
    good = candidate(Pass(), progress(1,10))
    bad = replace(candidate(Peng(Tile("5w")),progress(0,20)), action_key="bad-key")
    request = make_request(make_observation(),make_rules([good,good,bad],good))
    policy = ComparableHeuristicPolicyV2(monotonic=lambda:0)
    first = asyncio.run(policy.choose(request,make_budget()))
    assert first == asyncio.run(policy.choose(request,make_budget()))
    assert [c.action_key for c in first.candidates] == ["pass"]
    assert len(request.rules.legal_candidates)==3


@pytest.mark.parametrize("hand,tile,phase,expected", [
    ("5w 5w 9b 8t 4t 6w 北 7b 9t 4b 7t 8t 8b", "5w", "response_peng", "peng:5w"),
    ("5w 5w 1t 2t 3t 4t 5t 6t 7t 8t 9t 2b 3b", "5w", "response_peng", "pass"),
    ("1w 2w 1t 2t 3t 4t 5t 6t 7t 8t 东 2b 9b", "3w", "response_chi", "chi:1w,2w,3w"),
    ("1w 2w 1t 2t 3t 4t 5t 6t 7t 8t 9t 2b 2b", "3w", "response_chi", "pass"),
])
def test_real_rule_observations_cover_claim_and_pass(hand,tile,phase,expected):
    seat=3 if phase == "response_chi" else 2
    rivers=[(),(),(),()]
    rivers[seat]=(Tile(tile),)
    obs=make_observation(phase=phase,responding_seats=(0,),turn_seat=seat,
                         my_hand=tuple(Tile(c) for c in hand.split()),discards=tuple(rivers),
                         last_discard=PublicDiscard(seat,Tile(tile),9))
    analysis=rules_from_engine(obs)
    assert analysis.completeness is RuleCompleteness.COMPLETE
    assert all(c.facts.fact_kind is Kind.HAND_PROGRESS and c.facts.completeness is RuleCompleteness.COMPLETE
               for c in analysis.legal_candidates)
    request=make_request(obs,analysis,phase=WindowPhase(phase))
    plan=asyncio.run(ComparableHeuristicPolicyV2(monotonic=lambda:0).choose(request,make_budget()))
    assert plan.candidates[0].action_key == expected
    assert set(c.action_key for c in plan.candidates)==set(c.action_key for c in analysis.legal_candidates)
    assert "缺可比等待基线" not in " ".join(plan.degraded_reasons)
    for c in plan.candidates:
        facts=next(x.facts for x in analysis.legal_candidates if x.action_key == c.action_key)
        risk=0 if c.action_key=="pass" else 10 if phase=="response_chi" else 6
        assert c.total_score==-100*facts.shanten_after+sum(u.remaining_estimate for u in facts.useful_tiles)-risk


def test_pass_overflow_raises_and_expired_budget_or_cancellation_remains_explicit():
    with pytest.raises(ValueError,match="非有限"):
        choose([candidate(Pass(),progress(4))],weights=replace(DEFAULT_WEIGHTS_V1,shanten_step=1e308))
    request = make_request(make_observation(),make_rules([candidate(Pass(),progress(1))]))
    with pytest.raises(PolicyTimeoutError):
        asyncio.run(ComparableHeuristicPolicyV2(monotonic=lambda:999).choose(request,make_budget()))
    async def cancel():
        task=asyncio.create_task(ComparableHeuristicPolicyV2(monotonic=lambda:0).choose(request,make_budget()))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(cancel())
