"""真实审计输入验证窄七对分值增量；不靠合成奖励证明策略提高。"""
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import pytest
from hangma_bot.application.audit_codec import decision_request_from_json
from hangma_bot.hangma import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits, RuleCompleteness
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.policy.v2_seven_pairs_wait import V2SevenPairsWaitPolicy
from .test_hu_upgrade import BUDGET, historical, replace_candidates
from .test_v2_hu_upgrade import v2
from .support import rejected

ROOT=Path(__file__).resolve().parents[3]
CASES=ROOT/'review/seven-pairs-route-2026-09-09/cases'
GOOD='dec-4da1b9747a3d42e3af55d55796d21be4'


def recorded(decision_id=GOOD):
    raw=json.loads((CASES/(decision_id+'.json')).read_text())['request']
    request=decision_request_from_json(raw)
    rules=HangmaRules(RuleConfig('hangma-mvp-v10-public-counts',1,False))
    return replace(request,rules=rules.analyze(request.observation,value_limits=ValueAnalysisLimits()))


def choose(request,**kwargs):
    return asyncio.run(V2SevenPairsWaitPolicy(monotonic=lambda:0,**kwargs).choose(request,BUDGET))


@pytest.mark.parametrize('did,key',[
    (GOOD,'discard:3b'),('dec-2f9db74f5e2648a7924f7bb24fc7ce5b','discard:9t'),
    ('dec-8f19a68f6985458292240e8916d3a61b','discard:4w'),
    ('dec-7d14e090b5d14425b461082fac3dd0a6','discard:4w')])
def test_real_equal_or_more_outs_keep_valuable_routes(did,key):
    request=recorded(did);base=v2(request);plan=choose(request)
    assert base.candidates[0].action_key!=key
    assert plan.candidates[0].action_key==key
    assert plan==choose(request)
    assert {c.action_key for c in plan.candidates}=={c.action_key for c in base.candidates}
    assert {c.action_key for c in plan.candidates if c.is_emergency}=={c.action_key for c in base.candidates if c.is_emergency}
    assert all(c.total_score==sum(p.value for p in c.score_parts) for c in plan.candidates)
    assert [c.rank for c in plan.candidates]==list(range(1,len(plan.candidates)+1))


@pytest.mark.parametrize('did',[
    'dec-e5a4d4e4523a477e8e4f0460f2feff9c', # 七对分值高，但少一张有效进张。
    'dec-bea36e4482ba42cfb06be567c1b2403d', # 响应碰/过不在本轮范围。
    'dec-6d33e3beb5f544d1b2e8285539e5447b', # 补牌时机未知，不跨杠排序。
    'dec-c5ef00f11cd5428f9c36d05e5676f75b', # 一向听尚未提供下一摸胡牌价值。
])
def test_do_not_expand_scope_to_outs_tradeoff_claim_gang_or_one_shanten(did):
    request=recorded(did)
    assert choose(request)==v2(request)


@pytest.mark.parametrize('name',list('ACDEFGH'))
def test_historical_hu_open_hand_and_ordinary_choices_unchanged(name):
    request=historical(name)
    assert choose(request)==v2(request)


def test_switch_rejection_missing_values_and_degraded_rules_keep_v2():
    request=recorded()
    assert choose(request,value_weight=0)==v2(request)
    for changed in [
        replace(request,rejected_attempts=(rejected('discard:3b'),)),
        replace_candidates(request,lambda c:replace(c,value_facts=None)),
        replace(request,rules=replace(request.rules,completeness=RuleCompleteness.DEGRADED)),
    ]:
        assert choose(changed)==v2(changed)


def test_deadline_falls_back_and_cancel_propagates(monkeypatch):
    request=recorded();base=v2(request);policy=V2SevenPairsWaitPolicy(monotonic=lambda:101)
    async def done(*args):return base
    monkeypatch.setattr(policy._baseline,'choose',done)
    plan=asyncio.run(policy.choose(request,BUDGET))
    assert plan.candidates==base.candidates and 'PolicyTimeoutError' in plan.degraded_reasons[-1]
    async def cancel(*args):raise asyncio.CancelledError
    monkeypatch.setattr(policy,'_check_deadline',cancel)
    with pytest.raises(asyncio.CancelledError):asyncio.run(policy.choose(request,BUDGET))
