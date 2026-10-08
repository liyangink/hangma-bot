"""持久确认登记的事务、恢复和曝光反例；仅临时数据库与开发测试来源。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import json
import pytest
import confirmation_draft as analysis
import confirmation_pairing as pairing
from confirmation_registry import ConfirmationRegistry
from test_confirmation_draft import fixture


def setup(tmp_path):
    cfg=json.loads((_project_file(_PROJECT_ROOT, Path(__file__).resolve().parents[2]/'contracts/group-dev-v1.json')).read_text())
    registry=ConfirmationRegistry(tmp_path/'registry.sqlite',campaign_id='test-campaign',allocations=[.025,.025])
    roots=[pairing.build_root_plan(contract=cfg,registration_seed=91238,opponent=m,root_index=i)
        for i in (1,2) for m in ('H','M')]
    for root in roots:registry.register_root(root)
    return registry,roots


def registration(registry, roots, slot=0):
    plan,_,_=fixture(n=2)
    plan.update(candidate_source_sha256='a'*64,source_ledger_digest=analysis.digest(registry.source_ledger()),
        roots=[{k:r[k] for k in ('source_root_id','root_content_digest','independence_id','opponent_mix')} for r in roots],
        n_roots=len(roots),alpha=.025,multiplicity={'campaign_id':'test-campaign','allocations':[.025,.025],'slot':slot})
    return plan


def test_reservation_persists_and_exact_resume_is_idempotent(tmp_path):
    registry,roots=setup(tmp_path);plan=registration(registry,roots[:2])
    receipt=registry.reserve_attempt('attempt-a',plan)
    reopened=ConfirmationRegistry(registry.path,campaign_id='test-campaign',allocations=[.025,.025])
    assert reopened.reserve_attempt('attempt-a',plan)==receipt
    assert len(reopened.attempts())==1
    assert all(x['exposures']==[] for x in receipt['source_ledger_before'])
    used=[r for r in reopened.source_ledger() if r['exposures']]
    assert len(used)==2
    assert receipt['alpha_consumed']==.025 and not receipt['release_eligible']


def test_consumed_slot_cannot_be_used_on_other_fresh_roots(tmp_path):
    registry,roots=setup(tmp_path)
    registry.reserve_attempt('a',registration(registry,roots[:2]))
    with pytest.raises(ValueError,match='槽已消费'):
        registry.reserve_attempt('b',registration(registry,roots[2:]))
    assert len(registry.attempts())==1
    assert sum(bool(r['exposures']) for r in registry.source_ledger())==2


def test_failure_after_reservation_neither_refunds_roots_nor_alpha(tmp_path):
    registry,roots=setup(tmp_path)
    registry.reserve_attempt('failed-run',registration(registry,roots[:2]))
    with pytest.raises(ValueError,match='已有开发或确认消费'):
        registry.reserve_attempt('retry-as-new',registration(registry,roots[:2],slot=1))
    assert len(registry.attempts())==1


def test_stale_freshness_snapshot_is_not_allowed(tmp_path):
    registry,roots=setup(tmp_path);plan=registration(registry,roots[:2])
    registry.record_exposure(roots[0]['source_root_id'],event_id='diagnostic',evidence='synthetic-only.json')
    with pytest.raises(ValueError,match='来源台账漂移'):registry.reserve_attempt('a',plan)
    assert registry.attempts()==[]


def test_new_snapshot_does_not_make_exposed_root_fresh(tmp_path):
    registry,roots=setup(tmp_path)
    registry.record_exposure(roots[0]['source_root_id'],event_id='diagnostic',evidence='synthetic-only.json')
    with pytest.raises(ValueError,match='已有开发或确认消费'):
        registry.reserve_attempt('a',registration(registry,roots[:2]))
    assert registry.attempts()==[]


def test_changed_candidate_cannot_resume_same_attempt(tmp_path):
    registry,roots=setup(tmp_path);plan=registration(registry,roots[:2])
    registry.reserve_attempt('a',plan);plan['candidate_source_sha256']='b'*64
    with pytest.raises(ValueError,match='恢复的执行身份'):registry.reserve_attempt('a',plan)


def test_new_campaign_or_allocation_cannot_reset_existing_db(tmp_path):
    registry,_=setup(tmp_path)
    with pytest.raises(ValueError,match='禁止重置预算'):
        ConfirmationRegistry(registry.path,campaign_id='new-name',allocations=[.05])
    assert registry.attempts()==[]


def test_plan_cannot_claim_other_budget(tmp_path):
    registry,roots=setup(tmp_path);plan=registration(registry,roots[:2]);plan['multiplicity']['allocations']=[.05]
    with pytest.raises(ValueError,match='增加误报预算'):registry.reserve_attempt('a',plan)
    assert registry.attempts()==[]


def test_alias_draw_and_tampered_content_rejected(tmp_path):
    registry,roots=setup(tmp_path)
    alias=deepcopy(roots[0]);alias['source_root_id']='renamed-root'
    with pytest.raises(ValueError,match='摘要/结构'):registry.register_root(alias)
    del alias['root_content_digest'];alias['root_content_digest']=analysis.digest(alias)
    with pytest.raises(ValueError,match='别名重复'):registry.register_root(alias)
    assert len(registry.source_ledger())==4


def test_concurrent_identical_resumes_consume_only_once(tmp_path):
    registry,roots=setup(tmp_path);plan=registration(registry,roots[:2])
    with ThreadPoolExecutor(max_workers=4) as workers:
        receipts=list(workers.map(lambda _:registry.reserve_attempt('a',plan),range(4)))
    assert all(r==receipts[0] for r in receipts)
    assert len(registry.attempts())==1


def test_concurrent_competing_attempts_cannot_double_consume(tmp_path):
    registry,roots=setup(tmp_path);plan=registration(registry,roots[:2])
    def reserve(name):
        try:return registry.reserve_attempt(name,plan)['attempt_id']
        except ValueError:return None
    with ThreadPoolExecutor(max_workers=2) as workers:
        results=list(workers.map(reserve,['a','b']))
    assert sum(r is not None for r in results)==1
    assert len(registry.attempts())==1


@pytest.mark.parametrize('allocations',[[.03,.03],[True],[0],[float('nan')],[float('inf')],[]])
def test_invalid_alpha_rejected_without_creating_db(tmp_path,allocations):
    path=tmp_path/'uncreated.sqlite'
    with pytest.raises(ValueError):ConfirmationRegistry(path,campaign_id='test',allocations=allocations)
    assert not path.exists()


def test_both_slots_can_be_spent_only_on_disjoint_registered_roots(tmp_path):
    registry,roots=setup(tmp_path)
    registry.reserve_attempt('a',registration(registry,roots[:2],slot=0))
    registry.reserve_attempt('b',registration(registry,roots[2:],slot=1))
    assert sum(r['alpha_consumed'] for r in registry.attempts())==.05
    assert all(r['exposures'] for r in registry.source_ledger())


def test_persisted_receipt_feeds_existing_analysis_without_rewriting_freshness(tmp_path):
    registry,roots=setup(tmp_path);plan=registration(registry,roots[:2])
    receipt=registry.reserve_attempt('a',plan)
    _,_,samples=fixture(n=2)
    for i,root in enumerate(plan['roots']):
        for sample in samples[i*4:(i+1)*4]:sample.update(root)
    persisted=ConfirmationRegistry(registry.path,campaign_id='test-campaign',allocations=[.025,.025]).attempts()[0]
    result=analysis.analyze(persisted['registration'],samples,
        frozen_digest=persisted['registration_digest'],source_ledger=persisted['source_ledger_before'],
        execution_identity='test-runtime')
    assert result['analysis_status']=='INCONCLUSIVE'
    assert result['n_independent_roots']==2 and result['release_eligible'] is False
    # 只有账本保存的消费前快照可用于该次预登记；当前已消费账本不能伪装成原快照。
    with pytest.raises(ValueError,match='来源台账漂移'):
        analysis.analyze(plan,samples,frozen_digest=receipt['registration_digest'],
            source_ledger=registry.source_ledger(),execution_identity='test-runtime')
