"""独立续飘只进入离线装配，并记录实际启用开关。"""
import asyncio
from scripts.evaluate import build_policy, _effective_weights_snapshot
from hangma_bot.offline.evaluate import PolicyDeclaration
from tests.unit.policy.test_v2_claim_piao import claimed
from tests.unit.policy.test_v2_hu_upgrade import v2
from tests.unit.policy.test_hu_upgrade import BUDGET


def test_disabled_offline_declaration_is_exact_v2_and_metadata_records_scope():
    declaration = PolicyDeclaration('candidate', 'v2_claim_piao_v1', (('continuation_weight', 0),))
    policy = build_policy(declaration, lambda: 0)
    request, *_ = claimed()
    assert asyncio.run(policy.choose(request, BUDGET)) == v2(request)
    metadata = _effective_weights_snapshot(policy)
    assert metadata['base_policy'] == 'weighted_heuristic_v2'
    assert metadata['continuation_weight'] == 0
    assert metadata['continuation_scope'] == 'post-claim-complete-baotou-v1'
