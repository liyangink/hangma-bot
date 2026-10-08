"""执行接线的恢复边界；合成runner只检事务，不冒充完整模拟或正式确认。"""

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
import pytest
import confirmation_execution_probe as probe
import strong_seed_batch as b


def setup(tmp_path):
    ledger=b.search.ActionValueLedger.load(tmp_path/'ledger.json',authorized_budgets={'tables_full':2})
    return ledger,{'step_id':'one-stage','planned_tables':2,'manifest_digest':'frozen-test','arm':'candidate'}


def test_complete_output_resumes_without_running_or_recharging(tmp_path):
    ledger,expected=setup(tmp_path);calls=[]
    def run():calls.append(1);return {'complete':True}
    check=lambda raw:{'tables':2,'complete':raw['complete']}
    first=probe.execute_arm(tmp_path/'arm',expected=expected,ledger=ledger,runner=run,verifier=check)
    reopened=b.search.ActionValueLedger.load(tmp_path/'ledger.json')
    second=probe.execute_arm(tmp_path/'arm',expected=expected,ledger=reopened,runner=run,verifier=check)
    assert first==second and calls==[1] and reopened.spent('tables_full')==2
    assert len(reopened.reservations)==1


def test_started_without_result_refuses_blind_retry_and_keeps_fee(tmp_path):
    ledger,expected=setup(tmp_path);calls=[]
    def fail():calls.append(1);raise RuntimeError('interrupted after dispatch')
    with pytest.raises(RuntimeError):probe.execute_arm(tmp_path/'arm',expected=expected,ledger=ledger,runner=fail,verifier=lambda x:None)
    with pytest.raises(ValueError,match='拒绝盲目重跑'):
        probe.execute_arm(tmp_path/'arm',expected=expected,ledger=ledger,runner=fail,verifier=lambda x:None)
    assert calls==[1] and ledger.spent('tables_full')==2


def test_result_tamper_is_rejected_without_running(tmp_path):
    ledger,expected=setup(tmp_path);calls=[]
    run=lambda:calls.append(1) or {'complete':True}
    check=lambda raw:{'tables':2}
    probe.execute_arm(tmp_path/'arm',expected=expected,ledger=ledger,runner=run,verifier=check)
    path=tmp_path/'arm/result.json';data=b.read(path);data['raw']['complete']=False;b.write(path,data)
    with pytest.raises(ValueError,match='摘要漂移'):
        probe.execute_arm(tmp_path/'arm',expected=expected,ledger=ledger,runner=run,verifier=check)
    assert calls==[1] and ledger.spent('tables_full')==2


def test_candidate_or_plan_change_cannot_resume(tmp_path):
    ledger,expected=setup(tmp_path)
    probe.execute_arm(tmp_path/'arm',expected=expected,ledger=ledger,runner=lambda:{},verifier=lambda raw:{'tables':2})
    with pytest.raises(ValueError,match='恢复身份不一致'):
        probe.execute_arm(tmp_path/'arm',expected=dict(expected,manifest_digest='changed'),ledger=ledger,
            runner=lambda:pytest.fail('must not run'),verifier=lambda raw:{'tables':2})


def test_failed_verification_keeps_conservative_charge(tmp_path):
    ledger,expected=setup(tmp_path)
    def reject(raw):raise ValueError('missing MatchResult')
    with pytest.raises(ValueError,match='missing MatchResult'):
        probe.execute_arm(tmp_path/'arm',expected=expected,ledger=ledger,runner=lambda:{'complete':False},verifier=reject)
    assert ledger.spent('tables_full')==2
    assert ledger.reservations[0]['usage_unknown'] is True
    assert not (tmp_path/'arm/verified.json').exists()


def test_complete_result_after_pre_settlement_crash_can_reconcile(tmp_path):
    ledger,expected=setup(tmp_path)
    reservation=ledger.reserve(step_id='one-stage',account='tables_full',amount=2)
    folder=tmp_path/'arm';folder.mkdir()
    b.write(folder/'begin.json',{'expected':expected,'reservation':reservation})
    raw={'complete':True}
    b.write(folder/'result.json',{'expected':expected,'raw':raw,'raw_digest':probe.analysis.digest(raw)})
    result=probe.execute_arm(folder,expected=expected,ledger=ledger,runner=lambda:pytest.fail('must reuse complete output'),
        verifier=lambda x:{'tables':2})
    assert result['tables']==2 and ledger.spent('tables_full')==2
    assert ledger.reservations[0]['status']=='settled'
