"""V1 计划消费者契约：执行 rank，而非重新按数值总分排序。"""

from dataclasses import asdict
import json

from hangma_bot.hangma.interface import CandidateFacts, CandidateFactKind, RuleCandidate
from hangma_bot.kernel.actions import Discard, Tile
from hangma_bot.policy import ReliableHeuristicPolicyV1
from tests.unit.policy.support import make_observation,make_request,make_rules,make_budget,run_choose


def test_rank_is_authoritative_while_score_parts_remain_numeric():
    known = RuleCandidate(Discard(Tile('9t')),'discard:9t',(),CandidateFacts(CandidateFactKind.HAND_PROGRESS,4))
    unknown = RuleCandidate(Discard(Tile('1w')),'discard:1w',(),None)
    request = make_request(make_observation(),make_rules([unknown,known],unknown))
    plan = run_choose(ReliableHeuristicPolicyV1(monotonic=lambda:0),request,make_budget())
    payload = json.loads(json.dumps(asdict(plan),allow_nan=False))
    assert [c['rank'] for c in payload['candidates']] == [1,2]
    assert payload['candidates'][0]['action_key'] == 'discard:9t'
    assert payload['candidates'][0]['total_score'] < payload['candidates'][1]['total_score']
    assert payload['candidates'][1]['is_emergency']
    for c in payload['candidates']:
        assert c['total_score'] == sum(p['value'] for p in c['score_parts'])
        assert c['reasons']
