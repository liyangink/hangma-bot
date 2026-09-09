"""早期路线保留的公开行为；真实手牌事实由唯一规则引擎生成。"""
import asyncio
from dataclasses import replace

import pytest

from hangma_bot.hangma import HangmaRules
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
from hangma_bot.policy.route_preserve import V2RoutePreservePolicy
from .support import make_observation, make_request, make_budget, rejected

CASES = (
    ('2t 2w 发 5t 白 发 2w 2t 3w 4t 4b 3t 1t 8b','discard:2w','discard:1t'),
    ('5t 2t 2w 发 5t 白 发 2w 2t 3w 4b 4w 4t 5t','discard:2t','discard:4t'),
    ('4w 白 2w 4w 4w 8t 4t 1b 2w 4t 3b 白 3t 5b','discard:4t','discard:8t'),
    ('1w 1w 1w 1w 2w 2w 3w 3w 4w 5w 5w 6t 6w 3b','discard:5w','discard:6w'),
)


def request(hand=CASES[0][0], **kwargs):
    tiles=tuple(Tile(c) for c in hand.split())
    obs=make_observation(my_hand=tiles[:-1],drawn_tile=tiles[-1],remaining_tile_count=83,**kwargs)
    rules=HangmaRules(RuleConfig('hangma-mvp-v10-public-counts',1,False))
    return make_request(obs,rules.analyze(obs))


def choose(req, candidate=True):
    policy=V2RoutePreservePolicy(monotonic=lambda:0) if candidate else ComparableHeuristicPolicyV2(monotonic=lambda:0)
    return asyncio.run(policy.choose(req,make_budget()))


@pytest.mark.parametrize('hand,old,new',CASES)
def test_small_efficiency_cost_preserves_an_equally_close_seven_pairs_route(hand,old,new):
    req=request(hand)
    base=choose(req,False); plan=choose(req)
    assert base.candidates[0].action_key == old
    assert plan.candidates[0].action_key == new
    assert {c.action_key for c in plan.candidates} == {c.action_key for c in base.candidates}
    assert any(c.is_emergency for c in plan.candidates)
    assert all(c.total_score==sum(p.value for p in c.score_parts) for c in plan.candidates)
    assert '不是期望净分证明' in plan.candidates[0].reasons[-1]
    assert plan == choose(req)


@pytest.mark.parametrize('wall',[None,20,24,47])
def test_short_or_unknown_wall_returns_the_entire_baseline(wall):
    req=request();req=replace(req,observation=replace(req.observation,remaining_tile_count=wall))
    assert choose(req)==choose(req,False)


@pytest.mark.parametrize('field',['standard_shanten_after','seven_pairs_shanten_after'])
def test_legacy_unknown_is_not_zero_or_a_seven_pairs_claim(field):
    req=request();req=replace(req,rules=replace(req.rules,legal_candidates=tuple(
        replace(c,facts=replace(c.facts,**{field:None})) if c.facts else c for c in req.rules.legal_candidates)))
    assert choose(req)==choose(req,False)


@pytest.mark.parametrize('hand',[
    '5t 2w 发 5t 白 发 2w 3w 4b 4b 4w 5t 3b 6w',
    '5t 2t 2w 发 5t 白 发 2t 3w 4b 7w 3b 6w 4w',
    '1w 2w 3w 4w 5w 6w 8b 9b 白 白 2w 1t 4b 6w',
    '1w 2w 3w 4w 5w 6w 7b 8b 9b 2t 3t 4t 白 东',
])
def test_large_efficiency_cost_or_immediate_hu_does_not_trigger(hand):
    req=request(hand)
    assert choose(req)==choose(req,False)


def test_rejected_action_is_not_reintroduced():
    req=request(); chosen=choose(req).candidates[0]
    req=replace(req,rejected_attempts=(rejected(chosen.action_key),))
    assert chosen.action_key not in {c.action_key for c in choose(req).candidates}


def test_duplicate_later_facts_do_not_replace_the_first_legal_candidate():
    req=request(); first=req.rules.legal_candidates[0]
    duplicate=replace(first,facts=None)
    changed=replace(req,rules=replace(req.rules,legal_candidates=req.rules.legal_candidates+(duplicate,)))
    assert choose(changed).candidates[0].action_key == choose(req).candidates[0].action_key
