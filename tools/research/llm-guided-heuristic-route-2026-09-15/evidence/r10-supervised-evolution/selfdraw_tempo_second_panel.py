"""独立自摸竞速原源码的第二张已见开发清单；0作者、256完整桌赛。"""

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
import statistics

import selfdraw_tempo_batch as first
import confirmation_execution_identity as execution_identity
import sitin_natural_panel as natural
from verify_full_natural_results import verify_full_panel
from hangma_bot.simulation.artifacts import compute_rules_hash

b=first.b
OUT=b.HERE/'selfdraw-tempo-second-dev-20260920'
SUB=first.OUT/first.NAME


def verify(plan):
    """每个面板前后核对原源码、合同、首清单分流与完整执行身份。"""
    execution_identity.verify(plan['execution_identity'])
    source=b.Path(plan['source']['path'])
    assert b.digest(source.read_bytes())==plan['source']['sha256']
    for name,sha in plan['prerequisites'].items():assert b.digest((SUB/name).read_bytes())==sha
    assert b.digest((b.ROUTE/'contracts/group-dev-v1.json').read_bytes())==plan['contract_sha256']
    assert compute_rules_hash(b.ROUTE.parents[1])==plan['rules_hash']
    admission=b.read(OUT/'admission.json')
    ok,reason=b.search.av_gates().av_record_identity_matches(admission,source.read_text())
    assert ok,reason
    assert admission['controlled_research_eligible'] and admission['execution_safety_pass']
    return source.read_text()


def prepare():
    """首清单双正与执行清洁才签发，不沿用旧核心成绩或冒充独立确认。"""
    assert not OUT.exists()
    assert b.read(SUB/'development-decision.json')['continue_second_seen_panel'] is True
    assert b.read(SUB/'batch-closure.json')['full_natural_results_verified']==256
    state=b.search.av_state_load(b.search.av_latest_state_path(SUB/'run'))
    assert state['status']=='ITERATION_COMPLETE' and b.search.av_verify_run_identity(state)[0]
    source=b.Path(state['iter_dir'])/'generation/candidate.py'
    admission=b.Path(state['iter_dir'])/'admission/admission.json'
    conditional=b.read(b.Path(state['iter_dir'])/'conditional/evaluation.json')
    assert all(a['execution_review']['zero_internal_failures_verified'] for a in conditional['double_arm']['arms'].values())
    plan={'schema':'selfdraw-tempo-second-seen/1','created_at_utc':b.search.utc_now(),
        'source':{'path':str(source),'sha256':b.digest(source.read_bytes())},
        'rules_hash':compute_rules_hash(b.ROUTE.parents[1]),
        'contract_sha256':b.digest((b.ROUTE/'contracts/group-dev-v1.json').read_bytes()),
        'prerequisites':{name:b.digest((SUB/name).read_bytes()) for name in ('development-decision.json','batch-closure.json','source-review.json')},
        'panel_seed':2026092097,'roots':list(range(1,9)),'opponents':['H','M'],
        'full_tables':256,'max_full_tables':256,'model_calls':0,'confirmation_roots':0,
        'max_operations':100000,'scope':'原源码第二已见开发清单；内部配置配对牌山、四座位配置，不是未见开发或独立确认',
        'decision_rule':'H/M相对稳定V2均正且等权平分识别差下界正，并通过完整结果与执行审计，才签发新的开发来源验证；否则停止该提案扩评，不调常数。仅性能问题不抹去机制价值。',
        'parent':None,'primary_comparator':'stable_v2','release_eligible':False,
        'admission_reuse':'复用同源码同依赖同额度的已验收准入，执行前重新核验摘要；不冒充新增准入测试',
        'execution_identity':execution_identity.capture(source_paths=[*b.HERE.glob('*.py'),source])}
    OUT.mkdir();b.write(OUT/'manifest.json',plan)
    b.write(OUT/'admission.json',b.read(admission))
    auth=b.unified_document(batch_label='selfdraw-tempo-second-dev',authorization_id='r10-selfdraw-tempo-second-dev',
        accounts={'tables_full':256},issued_by='lead',issued_at_utc=b.search.utc_now(),legacy_alias=False)
    auth['issuance_basis']='用户持续推进授权；完整第一清单满足冻结继续条件，第二已见清单256桌、0新作者'
    b.write(OUT/'authorization.json',auth)
    verify(plan)
    b.write(OUT/'prepared.json',{'status':'READY','at_utc':b.search.utc_now()})
    print('second seen panel frozen: 256 tables, zero authors',flush=True)


def run():
    """完整执行固定H/M并核验实际产物；启动过则拒绝隐式重复运行。"""
    plan=b.read(OUT/'manifest.json');source=verify(plan)
    assert b.read(OUT/'prepared.json')['status']=='READY'
    assert not (OUT/'started.json').exists()
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
    b.write(OUT/'summary.json',{'status':'COMPLETE_SEEN_DEVELOPMENT','statistics':stats,'verification':checks,
        'candidate_source_sha256':plan['source']['sha256'],'full_tables_verified':sum(c['full_results_verified'] for c in checks),
        'spent':ledger['spent'],'equal_mix_vs_v2':statistics.mean(s['mean_delta'] for s in stats.values()),
        'equal_mix_identification_low':low,'equal_mix_identification_high':high,
        'effect_condition_passed':positive,'zero_internal_failures_verified':clean,
        'continue_new_development':positive and clean,'effect_positive_needs_execution_review':positive and not clean,
        'interval_kind':'平分识别区间，非置信区间','model_calls':0,'confirmation_roots':0,'release_eligible':False})
    print('second seen complete; effect_condition_passed',positive,'execution_clean',clean,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','run'))
    args=parser.parse_args()
    prepare() if args.action=='prepare' else run()
