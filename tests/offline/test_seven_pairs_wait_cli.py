"""离线七对候选的可复现装配与关闭模式。"""
import asyncio
from scripts.evaluate import build_policy, _effective_weights_snapshot
from hangma_bot.offline.evaluate import PolicyDeclaration
from tests.unit.policy.test_v2_seven_pairs_wait import recorded
from tests.unit.policy.test_v2_hu_upgrade import v2
from tests.unit.policy.test_hu_upgrade import BUDGET


def test_seven_pairs_wait_records_scope_and_zero_weight_returns_v2():
    policy=build_policy(PolicyDeclaration('candidate','v2_seven_pairs_wait_v1',(('value_weight',0),)),lambda:0)
    request=recorded()
    assert asyncio.run(policy.choose(request,BUDGET))==v2(request)
    snapshot=_effective_weights_snapshot(policy)
    assert snapshot['value_weight']==0
    assert snapshot['value_scope']=='closed-ready-seven-nondecreasing-outs-v1'
    assert snapshot['base_policy']=='weighted_heuristic_v2'
