"""V1 公开决策行为回归：可靠层级、旧偏好、故障和预算边界。"""

import asyncio
from dataclasses import asdict, replace
import json

import pytest

from hangma_bot.hangma.interface import (
    CandidateFactKind as Kind, CandidateFacts, RuleCandidate, RuleCompleteness,
    UsefulTileFact,
)
from hangma_bot.kernel.actions import Chi, Discard, Gang, GangKind, Hu, Pass, Peng, Tile, action_key
from hangma_bot.policy import (
    ReliableHeuristicPolicyV1, WeightedHeuristicPolicy, HeuristicWeightsV1,
    DEFAULT_WEIGHTS, DEFAULT_WEIGHTS_V1, PolicyTimeoutError,
)
from .support import (
    make_observation, make_request, make_rules, make_budget, rejected,
    rules_from_engine, run_choose,
)


def candidate(action, facts=None):
    return RuleCandidate(action, action_key(action), (), facts)


def progress(shanten=2, **overrides):
    return CandidateFacts(Kind.HAND_PROGRESS, shanten, **overrides)


def choose(candidates, emergency=None, observation=None, weights=DEFAULT_WEIGHTS_V1, rejected_attempts=()):
    request = make_request(
        observation or make_observation(), make_rules(candidates, emergency), rejected_attempts,
    )
    return run_choose(ReliableHeuristicPolicyV1(weights, monotonic=lambda: 0), request, make_budget())


def keys(plan):
    return [c.action_key for c in plan.candidates]


@pytest.mark.parametrize('bad_facts', [
    None,
    CandidateFacts(Kind.ANALYSIS_FAILED, None, completeness=RuleCompleteness.DEGRADED, note='注入故障'),
    progress(None), progress(True), progress(-1), progress(1.5),
    progress(0, completeness=RuleCompleteness.DEGRADED, note='部分分析失败'),
    CandidateFacts(Kind.WIN, -1), CandidateFacts(Kind.NOT_APPLICABLE, None),
    CandidateFacts('future_unknown_kind', None),
])
def test_unknown_never_beats_known_negative_score(bad_facts):
    known = candidate(Discard(Tile('9t')), progress(4))
    failed = candidate(Discard(Tile('1w')), bad_facts)
    plan = choose([failed, known], emergency=failed)
    assert keys(plan) == ['discard:9t', 'discard:1w']
    assert plan.candidates[0].total_score < plan.candidates[1].total_score
    assert plan.candidates[1].is_emergency
    assert '未知' in ' '.join(plan.candidates[1].reasons)
    # rank 可以与总分相反，但评分分解仍然是诚实的数值和。
    for item in plan.candidates:
        assert item.total_score == pytest.approx(sum(part.value for part in item.score_parts))
    json.dumps(asdict(plan), ensure_ascii=False, allow_nan=False)


def test_real_fault_injection_does_not_promote_failed_discard():
    hand = tuple(Tile(c) for c in ('1w','2w','4w','5w','7w','8w','1b','2b','3b','5b','6b','3t','4t','6t'))
    obs = make_observation(my_hand=hand[:13], drawn_tile=hand[-1])
    rules = rules_from_engine(obs)
    failed = CandidateFacts(Kind.ANALYSIS_FAILED, None, completeness=RuleCompleteness.DEGRADED, note='单候选注入')
    rules = replace(rules, legal_candidates=tuple(
        replace(c, facts=failed) if c.action_key == 'discard:3b' else c for c in rules.legal_candidates
    ))
    request = make_request(obs, rules)
    v0 = run_choose(WeightedHeuristicPolicy(monotonic=lambda: 0), request, make_budget())
    v1 = run_choose(ReliableHeuristicPolicyV1(monotonic=lambda: 0), request, make_budget())
    assert keys(v0)[0] == 'discard:3b'
    assert keys(v1)[0] == 'discard:1w'
    assert keys(v1)[-1] == 'discard:3b'
    assert set(keys(v0)) == set(keys(v1))


def test_whole_analysis_degraded_keeps_complete_candidate():
    known = candidate(Discard(Tile('9t')), progress(3))
    unknown = candidate(Discard(Tile('1w')))
    rules = replace(make_rules([unknown, known], unknown), completeness=RuleCompleteness.DEGRADED)
    request = make_request(make_observation(), rules)
    assert keys(run_choose(ReliableHeuristicPolicyV1(monotonic=lambda: 0), request, make_budget()))[0] == known.action_key


@pytest.mark.parametrize('emergency_index', [None, 0, 2])
def test_all_unknown_use_emergency_then_action_key(emergency_index):
    cs = [candidate(Discard(Tile(c))) for c in ('9t','1w','5b')]
    emergency = cs[emergency_index] if emergency_index is not None else None
    plan = choose(cs, emergency)
    expected = sorted(c.action_key for c in cs)
    if emergency:
        expected.remove(emergency.action_key)
        expected.insert(0, emergency.action_key)
    assert keys(plan) == expected
    assert [c.rank for c in plan.candidates] == [1,2,3]
    assert plan.degraded_reasons


def test_rejected_emergency_is_not_reintroduced():
    cs = [candidate(Discard(Tile(c))) for c in ('9t','1w','5b')]
    plan = choose(cs, cs[0], rejected_attempts=[rejected(cs[0].action_key)])
    assert keys(plan) == ['discard:1w', 'discard:5b']


def test_hu_priority_is_independent_of_weights_and_facts():
    hu = candidate(Hu())
    gang = candidate(Gang(tile=Tile('1w'), kind=GangKind.CONCEALED), progress(0, replacement_draw_unknown=True))
    weights = replace(DEFAULT_WEIGHTS_V1, win_now=-1000, gang_bonus=1000000)
    plan = choose([gang, hu], gang, weights=weights)
    assert keys(plan)[0] == action_key(Hu())
    assert plan.candidates[0].total_score < plan.candidates[1].total_score
    assert keys(choose([hu, gang], gang, weights=weights, rejected_attempts=[rejected(action_key(Hu()))])) == [gang.action_key]


def test_unknown_replacement_draw_is_not_analysis_failure():
    gang = candidate(Gang(tile=Tile('1w'), kind=GangKind.CONCEALED), progress(3, replacement_draw_unknown=True))
    failed = candidate(Discard(Tile('9t')))
    assert keys(choose([failed, gang], failed))[0] == gang.action_key


@pytest.mark.parametrize('facts', [CandidateFacts(Kind.NOT_APPLICABLE, None), progress(4)])
def test_pass_keeps_neutral_baseline_even_with_future_progress_facts(facts):
    plan = choose([candidate(Pass(), facts), candidate(Peng(Tile('5w')), progress(1))])
    assert keys(plan)[0] == 'pass'
    assert plan.candidates[0].total_score == 0


def test_failed_pass_is_not_trusted_as_neutral():
    cs = [candidate(Pass()), candidate(Peng(Tile('5w')), progress(2))]
    assert keys(choose(cs, cs[0])) == ['peng:5w', 'pass']


def test_complete_action_families_keep_v0_numeric_preferences():
    # 控制事实只用于评分，不以此声称这些动作可在同一真实窗口同时合法。
    actions = [Discard(Tile('1w')), Discard(Tile('白')), Peng(Tile('5w')),
               Chi((Tile('1w'), Tile('2w'), Tile('3w'))),
               Gang(tile=Tile('5b'), kind=GangKind.CONCEALED), Gang(tile=Tile('5b'), kind=GangKind.EXPOSED),
               Gang(tile=Tile('5b'), kind=GangKind.ADDED), Pass(), Hu()]
    cs = [candidate(a, CandidateFacts(Kind.WIN, -1) if isinstance(a, Hu) else
                    CandidateFacts(Kind.NOT_APPLICABLE, None) if isinstance(a, Pass) else
                    progress(1, useful_tiles=(UsefulTileFact('9t',3),))) for a in actions]
    obs = make_observation(my_hand=(Tile('白'), Tile('1w')))
    request = make_request(obs, make_rules(cs, cs[0]))
    old = run_choose(WeightedHeuristicPolicy(monotonic=lambda: 0), request, make_budget())
    new = run_choose(ReliableHeuristicPolicyV1(monotonic=lambda: 0), request, make_budget())
    assert [(c.action_key,c.total_score) for c in old.candidates] == [(c.action_key,c.total_score) for c in new.candidates]
    assert asdict(DEFAULT_WEIGHTS) == asdict(DEFAULT_WEIGHTS_V1)


def test_filters_and_determinism_do_not_mutate_request():
    cs = [candidate(Discard(Tile('9t')), progress(1)), candidate(Discard(Tile('1w')), progress(1))]
    bad = replace(cs[0], action_key='discard:2w')
    request = make_request(make_observation(), make_rules([cs[0],bad,cs[0],cs[1]],cs[1]))
    before = asdict(request)
    policy = ReliableHeuristicPolicyV1(monotonic=lambda: 0)
    first = run_choose(policy, request, make_budget())
    second = run_choose(policy, request, make_budget())
    assert first == second
    assert keys(first) == ['discard:1w','discard:9t']
    assert asdict(request) == before
    assert len(first.degraded_reasons) == 2


def test_empty_and_exhausted_plans_are_explicit():
    assert not choose([]).candidates
    c = candidate(Pass())
    plan = choose([c], c, rejected_attempts=[rejected('pass')])
    assert not plan.candidates
    assert '耗尽' in ' '.join(plan.degraded_reasons)


@pytest.mark.parametrize('value', [float('nan'),float('inf'),-float('inf'),True,'1',None,10**400])
def test_nonfinite_or_nonnumeric_weights_rejected(value):
    with pytest.raises(ValueError, match='有限数值'):
        HeuristicWeightsV1(shanten_step=value)


def test_score_overflow_is_explicit_failure():
    c = candidate(Discard(Tile('1w')), progress(4))
    with pytest.raises(ValueError, match='评分非有限'):
        choose([c], c, weights=replace(DEFAULT_WEIGHTS_V1, shanten_step=1e308))


def test_v0_weights_are_not_changed_or_accepted_accidentally():
    with pytest.raises(TypeError, match='HeuristicWeightsV1'):
        ReliableHeuristicPolicyV1(weights=DEFAULT_WEIGHTS)


def test_expired_budget_and_cancellation():
    request = make_request(make_observation(), make_rules([candidate(Pass())]))
    with pytest.raises(PolicyTimeoutError):
        run_choose(ReliableHeuristicPolicyV1(monotonic=lambda: 999), request, make_budget())

    async def cancelled():
        task = asyncio.create_task(ReliableHeuristicPolicyV1(monotonic=lambda: 0).choose(request, make_budget()))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(cancelled())
