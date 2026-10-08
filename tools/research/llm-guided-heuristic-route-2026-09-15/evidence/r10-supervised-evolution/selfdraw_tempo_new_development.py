"""自摸竞速双清单通过后的32根新开发验证；不生成正式确认来源。"""

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
import argparse
import secrets
import statistics
import subprocess

import selfdraw_tempo_second_panel as second
import confirmation_execution_identity as execution_identity
import sitin_natural_panel as natural
from verify_full_natural_results import verify_full_panel

b=second.b
OUT=b.HERE/'selfdraw-tempo-new-dev-20260920'


def verify(plan):
    """冻结候选与依赖不变，并核对第二清单完整结案与原准入身份。"""
    execution_identity.verify(plan['execution_identity'])
    prior=second.OUT/'summary.json'
    assert b.digest(prior.read_bytes())==plan['previous_summary_sha256']
    assert b.read(prior)['continue_new_development'] is True
    path=b.Path(plan['source']['path'])
    assert b.digest(path.read_bytes())==plan['source']['sha256']
    assert b.digest((b.ROUTE/'contracts/group-dev-v1.json').read_bytes())==plan['contract_sha256']
    admission=b.read(OUT/'admission.json')
    ok,why=b.search.av_gates().av_record_identity_matches(admission,path.read_text())
    assert ok and admission['controlled_research_eligible'] and admission['execution_safety_pass'],why
    return path.read_text()


def prepare():
    """尚未通过第二清单时零副作用；通过后一次抽取来源种子并预登记。"""
    summary=second.OUT/'summary.json'
    assert summary.exists() and b.read(summary)['continue_new_development'] is True
    assert b.read(summary)['full_tables_verified']==256
    assert not OUT.exists()
    previous=b.read(second.OUT/'manifest.json');second.verify(previous)
    seed=secrets.randbits(48)
    scan=subprocess.run(['rg','-l','-F',str(seed),str(b.ROUTE/'evidence'),
        '-g','*.json','-g','*.jsonl','-g','*.md','-g','*.py'],capture_output=True,text=True,check=False)
    assert scan.returncode==1 and not scan.stdout,('来源种子已有记录或检索失败',scan.returncode)
    source=b.Path(previous['source']['path'])
    plan={'schema':'selfdraw-tempo-new-development/1','created_at_utc':b.search.utc_now(),
        'source':previous['source'],'rules_hash':previous['rules_hash'],
        'contract_sha256':previous['contract_sha256'],
        'previous_summary_sha256':b.digest(summary.read_bytes()),
        'panel_seed':seed,'roots':list(range(1,17)),'opponents':['H','M'],
        'full_tables':512,'max_operations':100000,'model_calls':0,'confirmation_roots':0,
        'scope':'候选冻结后签发32个新开发根；配置内同牌山配对，不是独立确认',
        'decision_rule':'全量512桌、身份/费用/完整结果/执行审计通过，H/M相对V2分别正且等权平分识别差下界正，才进入正式确认准备；否则停止本提案扩评，不追加本批根，不调常数。',
        'seed_selection':'候选冻结后secrets.randbits(48)一次抽取，运行前登记；仓库evidence指定文本类型未命中，不声称覆盖全部外部历史来源',
        'seed_inventory_scan':{'returncode':scan.returncode,'scope':str(b.ROUTE/'evidence'),'types':['json','jsonl','md','py']},
        'execution_identity':execution_identity.capture(source_paths=[*b.HERE.glob('*.py'),source]),
        'release_eligible':False}
    OUT.mkdir();b.write(OUT/'manifest.json',plan)
    b.write(OUT/'admission.json',b.read(second.OUT/'admission.json'))
    auth=b.unified_document(batch_label='selfdraw-tempo-new-dev',authorization_id='r10-selfdraw-tempo-new-dev',
        accounts={'tables_full':512},issued_by='lead',issued_at_utc=b.search.utc_now(),legacy_alias=False)
    auth['issuance_basis']='用户持续推进授权；两张已见清单完整通过后固定32个新开发根，512桌、0作者、0正式确认'
    b.write(OUT/'authorization.json',auth)
    verify(plan)
    b.write(OUT/'prepared.json',{'status':'READY','at_utc':b.search.utc_now()})
    print('new development frozen: 32 roots, 512 tables, zero authors',flush=True)


def run():
    """执行固定完整清单；逐面板留存原始结果，不按中途成绩停止或补样。"""
    plan=b.read(OUT/'manifest.json');source=verify(plan)
    assert b.read(OUT/'prepared.json')['status']=='READY' and not (OUT/'started.json').exists()
    b.write(OUT/'started.json',{'at_utc':b.search.utc_now()})
    auth=b.read(OUT/'authorization.json');contract=b.read(b.ROUTE/'contracts/group-dev-v1.json')
    checks=[];stats={}
    for mix in plan['opponents']:
        verify(plan)
        natural.run_natural_panel(candidate_source=source,opponent=mix,roots=len(plan['roots']),
            seats_per_root=4,contract=contract,out_dir=OUT/('natural-'+mix),authorization=auth,
            panel_seed=plan['panel_seed'],ledger_path=OUT/'ledger.json',
            ledger_authorized_budgets=b.search.av_ledger_budgets_from_authorization(auth),min_roots=len(plan['roots']))
        panel=b.read(OUT/('natural-'+mix)/'panel.json')
        assert panel['identity']['candidate_source_sha256']==plan['source']['sha256']
        assert panel['identity']['panel_seed']==plan['panel_seed']
        assert panel['identity']['candidate_execution_profile']['max_operations']==plan['max_operations']
        checks.append(verify_full_panel(panel,contract,expected_identity=panel['identity'],
            expected_root_indices=plan['roots'],expected_rules_hash=plan['rules_hash']))
        stats[mix]=next(iter(panel['statistics']['by_candidate'].values()))['panels']['normal']['panels'][mix]
        print(mix,'complete and verified',checks[-1]['full_results_verified'],flush=True)
    verify(plan)
    ledger=b.read(OUT/'ledger.json')
    assert ledger['spent']['tables_full']==plan['full_tables']
    assert not any(r['status']=='reserved' for r in ledger['reservations'])
    low=statistics.mean(s['delta_bounds']['mean_delta_low'] for s in stats.values())
    high=statistics.mean(s['delta_bounds']['mean_delta_high'] for s in stats.values())
    positive=low>0 and all(s['mean_delta']>0 for s in stats.values())
    clean=all(c['execution_review']['zero_internal_failures_verified'] for c in checks)
    b.write(OUT/'summary.json',{'status':'COMPLETE_NEW_DEVELOPMENT','statistics':stats,'verification':checks,
        'candidate_source_sha256':plan['source']['sha256'],'full_tables_verified':sum(c['full_results_verified'] for c in checks),
        'spent':ledger['spent'],'equal_mix_vs_v2':statistics.mean(s['mean_delta'] for s in stats.values()),
        'equal_mix_identification_low':low,'equal_mix_identification_high':high,
        'effect_condition_passed':positive,'zero_internal_failures_verified':clean,
        'continue_confirmation_preparation':positive and clean,'effect_positive_needs_execution_review':positive and not clean,
        'interval_kind':'平分识别区间，非置信区间','model_calls':0,'confirmation_roots':0,'release_eligible':False})
    print('new development complete; effect_condition_passed',positive,'execution_clean',clean,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','run'))
    args=parser.parse_args()
    prepare() if args.action=='prepare' else run()
