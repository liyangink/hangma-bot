"""源码/根/配置漂移必须在模拟前被拒绝；事务替身不计作真实效果样本。"""

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
import copy
from pathlib import Path
import pytest
import confirmation_guarded_execution as guard

@pytest.fixture
def case(tmp_path,monkeypatch):
    core={'simulator':'v1','baseline':'v1'}
    monkeypatch.setattr(guard.identity.batch.search,'av_frozen_manifest',lambda:copy.deepcopy(core))
    monkeypatch.setattr(guard.identity.batch.search,'av_frozen_manifest_digest',guard.execution.analysis.digest)
    entry=tmp_path/'entry.py';entry.write_text('# actual entry fixture')
    candidate=tmp_path/'candidate.py';candidate.write_text('# candidate bytes fixture; never executed')
    contract=guard.b.ROUTE/'contracts/group-dev-v1.json'
    root=guard.execution.pairing.build_root_plan(contract=guard.b.read(contract),registration_seed=91237,opponent='H',root_index=1)
    frozen=guard.capture(entry_path=entry,candidate_path=candidate,contract_path=contract)
    expected={'step_id':'H-seat0-candidate','planned_tables':2,'arm':'candidate',
              'root_content_digest':root['root_content_digest'],'plans_digest':guard.execution.analysis.digest(root['configurations'][0]),
              'candidate_source_sha256':frozen['dependencies']['explicit_sources'][str(candidate)],
              'execution_identity_digest':guard.execution.analysis.digest(frozen),'manifest_digest':'synthetic-test-only'}
    ledger=guard.b.search.ActionValueLedger.load(tmp_path/'ledger.json',authorized_budgets={'tables_full':2})
    calls=[]
    def run():calls.append(1);return {'complete':True}
    return dict(folder=tmp_path/'arm',frozen=frozen,root=root,expected=expected,ledger=ledger,
                runner=run,verifier=lambda raw:{'tables':2,'complete':raw['complete']}),core,calls,entry,candidate


def test_completed_arm_resumes_without_new_simulation_or_charge(case):
    args,_,calls,_,_=case
    first=guard.execute_arm(**args);second=guard.execute_arm(**args)
    assert first==second and calls==[1] and args['ledger'].spent('tables_full')==2
    assert len(args['ledger'].reservations)==1

@pytest.mark.parametrize('surface',['core','entry','candidate','missing_helper','tables','wrong_config','wrong_candidate_hash'])
def test_drift_refuses_before_reservation(case,surface):
    args,core,calls,entry,candidate=case
    if surface=='core':core['simulator']='v2'
    elif surface=='entry':entry.write_text('# changed')
    elif surface=='candidate':candidate.write_text('# changed')
    elif surface=='missing_helper':args['frozen']['dependencies']['explicit_sources'].pop(str(Path(guard.execution.__file__).resolve()))
    elif surface=='tables':args['expected']['planned_tables']=1
    elif surface=='wrong_config':args['expected']['plans_digest']='forged'
    else:args['expected']['candidate_source_sha256']='forged'
    with pytest.raises(ValueError):guard.execute_arm(**args)
    assert calls==[] and args['ledger'].spent('tables_full')==0
    assert not (args['folder']/'begin.json').exists()


def test_self_consistent_root_with_stale_runtime_is_rejected(case):
    args,_,calls,_,_=case
    root=args['root'];root['runtime_identity']['source_sha256']['shuffle']='0'*64
    body=dict(root);body.pop('root_content_digest');root['root_content_digest']=guard.execution.analysis.digest(body)
    args['expected']['root_content_digest']=root['root_content_digest']
    with pytest.raises(ValueError,match='运行身份'):guard.execute_arm(**args)
    assert calls==[] and args['ledger'].spent('tables_full')==0


def test_drift_during_simulation_preserves_charge_but_refuses_verified_marker(case):
    args,core,calls,_,_=case
    def run():calls.append(1);core['simulator']='v2';return {'complete':True}
    args['runner']=run
    with pytest.raises(ValueError,match='漂移'):guard.execute_arm(**args)
    assert calls==[1] and args['ledger'].spent('tables_full')==2
    assert args['ledger'].reservations[0]['usage_unknown'] is True
    assert not (args['folder']/'verified.json').exists()


def test_drift_after_completed_arm_refuses_resume_without_recharge(case):
    args,core,calls,_,_=case
    guard.execute_arm(**args);core['baseline']='v2'
    with pytest.raises(ValueError,match='漂移'):guard.execute_arm(**args)
    assert calls==[1] and args['ledger'].spent('tables_full')==2


def test_drift_inside_verifier_refuses_success(case):
    args,core,calls,_,_=case
    def verifier(raw):core['baseline']='v2';return {'tables':2}
    args['verifier']=verifier
    with pytest.raises(ValueError,match='漂移'):guard.execute_arm(**args)
    assert calls==[1] and not (args['folder']/'verified.json').exists()
