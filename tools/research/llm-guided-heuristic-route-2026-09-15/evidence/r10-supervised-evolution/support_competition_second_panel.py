"""首清单通过后执行第二已见清单；复核复用同身份父代256桌，只新跑候选256桌。"""

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
import strong_seed_batch as b
import support_competition_batch as first
import comparable_shape_second_panel as prior
import route_executor_recovery as engine
import confirmation_execution_identity as identity
from natural_policy_execution_audit import observe_tables
from verify_full_natural_results import verify_full_panel

OUT=b.HERE/'support-competition-second-dev-20260920'

def verify_reused(plan):
    """复用原始终端产物而非摘要成绩；源码、核心、规则、合同、清单及文件身份全核对。"""
    engine.verify(plan)
    if 'execution_identity' in plan:identity.verify(plan['execution_identity'])
    old=b.read(prior.OUT/'manifest.json')
    for key in ('deps_digest','rules_hash','contract_sha256','panel_seed','roots','opponents'):
        assert old[key]==plan[key],key
    assert old['sources']['candidate']==plan['sources']['parent']
    for name,sha in plan['parent_reuse']['files'].items():
        assert b.digest((prior.OUT/'candidate'/name).read_bytes())==sha,name
    assert b.read(prior.OUT/'candidate/closure.json')['status']=='COMPLETE_DEVELOPMENT_ONLY'

def prepare():
    """必须先满足冻结继续条件；复用范围先登记，无额外模型调用或未见根。"""
    assert not OUT.exists()
    sub=first.OUT/first.NAME
    assert b.read(sub/'development-decision.json')['continue_second_seen_panel'] is True
    assert b.read(sub/'batch-closure.json')['full_natural_results_verified']==256
    state=b.search.av_state_load(b.search.av_latest_state_path(sub/'run'))
    assert state['status']=='ITERATION_COMPLETE' and b.search.av_verify_run_identity(state)[0]
    original=b.read(first.OUT/'manifest.json');old=b.read(prior.OUT/'manifest.json')
    parent=b.Path(original['parent'])/'candidate.py';candidate=b.Path(state['iter_dir'])/'generation/candidate.py'
    files=('closure.json','ledger.json','natural-H/panel.json','natural-M/panel.json')
    plan={**old,'created_at_utc':b.search.utc_now(),
          'sources':{k:{'path':str(p),'sha256':b.digest(p.read_bytes())} for k,p in [('parent',parent),('candidate',candidate)]},
          'full_tables':512,'new_full_tables':256,'reused_full_tables':256,'max_full_tables':256,
          'parent_reuse':{'directory':str(prior.OUT/'candidate'),'files':{f:b.digest((prior.OUT/'candidate'/f).read_bytes()) for f in files}},
          'first_panel_decision_sha256':b.digest((sub/'development-decision.json').read_bytes()),
          'first_panel_closure_sha256':b.digest((sub/'batch-closure.json').read_bytes()),
          'scope':'共享支撑竞争第二已见清单；复用同身份直接父代256桌、新候选256桌；不是新增512桌或独立确认。',
          'decision_rule':'候选H/M对V2均正且对直接研究父代等权识别差下界正才进入预登记新开发；否则停止追加，不调常数。',
          'trace_caveat':'共享竞争不是精确面子分解；计费余量有限，未通过真实时限发布门禁。',
          'model_calls':0,'confirmation_roots':0,'release_eligible':False}
    plan['execution_identity']=identity.capture(source_paths=list(b.HERE.glob('*.py'))+[parent,candidate,
        b.ROUTE/'evidence/v4-impl/r9-gate2/run/p12_authorization.py'])
    plan['policy_execution_audit']={'mode':'read_only_driver_observer_v1','parent_historical_counts':'unknown',
        'candidate_tables':'all256includingbaselinearm','note':'旧父代成绩可同身份配对，旧记录缺失的评分失败计数不追认零。'}
    verify_reused(plan)
    contract=b.read(b.ROUTE/'contracts/group-dev-v1.json');checks=[]
    for mix in plan['opponents']:
        panel=b.read(prior.OUT/'candidate'/('natural-'+mix)/'panel.json')
        assert panel['identity']['candidate_source_sha256']==plan['sources']['parent']['sha256']
        assert panel['identity']['panel_seed']==plan['panel_seed']
        checks.append(verify_full_panel(panel,contract,expected_identity=panel['identity'],
                      expected_root_indices=plan['roots'],expected_rules_hash=plan['rules_hash']))
    OUT.mkdir();b.write(OUT/'manifest.json',plan);b.write(OUT/'parent-reuse-verification.json',checks)
    # 只读复用入口供已审查的配对汇总函数读取；本脚本禁止派发parent运行。
    (OUT/'parent').symlink_to(prior.OUT/'candidate',target_is_directory=True)
    folder=OUT/'candidate';folder.mkdir();admission=b.search.av_gates().admit_action_value(candidate.read_text())
    b.write(folder/'admission.json',admission);assert admission['execution_safety_pass']
    auth=b.unified_document(batch_label='support-competition-second-candidate',authorization_id='r10-support-competition-second-candidate',
                           accounts={'tables_full':256},issued_by='lead',issued_at_utc=b.search.utc_now(),legacy_alias=False)
    auth['issuance_basis']='用户持续推进授权；首清单固定条件通过，原父代同身份复用，只新增候选256桌、零作者。'
    b.write(folder/'authorization.json',auth);b.write(OUT/'prepared.json',{'status':'READY','at_utc':b.search.utc_now()})
    print('prepared','new tables',256,'reused tables',256,flush=True)

def run():
    """只运行候选，不重新调用父代；恢复沿用底层已存在启动标识的拒绝规则。"""
    plan=b.read(OUT/'manifest.json');verify_reused(plan)
    sub=first.OUT/first.NAME
    for name,key in [('development-decision.json','first_panel_decision_sha256'),('batch-closure.json','first_panel_closure_sha256')]:
        assert b.digest((sub/name).read_bytes())==plan[key]
    engine.OUT=OUT
    with observe_tables(OUT/'candidate/policy-execution.jsonl'):
        engine.run('candidate')
    verify_reused(plan)

def close():
    """同根共同V2终局核对与配对计算复用既有实现，新增费用和复用数量分别报告。"""
    plan=b.read(OUT/'manifest.json');verify_reused(plan)
    engine.OUT=OUT;engine.NAMES=('parent','candidate');engine.close()
    result=b.read(OUT/'summary.json');result['continue_new_development']=result.pop('continue_second_seen_panel')
    result.update({'new_full_tables':256,'reused_full_tables':256,'scope':plan['scope']})
    import json
    rows=[json.loads(line) for line in (OUT/'candidate/policy-execution.jsonl').read_text().splitlines()]
    assert len(rows)==256 and [r['ordinal'] for r in rows]==list(range(256))
    expected={}
    for mix in plan['opponents']:
        panel=b.read(OUT/'candidate'/('natural-'+mix)/'panel.json')
        for sample in panel['samples']:
            for arm in ('baseline','candidate'):
                for table in sample['raw_arms'][arm]['tables']:
                    key=(table['table_id'],tuple(table['result']['versions']['natural_seat_policy:'+str(i)] for i in range(4)))
                    assert key not in expected;expected[key]=table['policy_execution']
    observed={(r['table_id'],tuple(r['policy_ids_by_seat'])):r['audit'] for r in rows}
    assert len(observed)==256 and observed==expected
    reasons={}
    for row in rows:
        for text,count in row['audit']['failure_reason_counts'].items():reasons[text]=reasons.get(text,0)+count
    result['policy_execution_audit']={k:sum(r['audit'][k] for r in rows) for k in ('decision_count','action_value_scored','action_value_failed','unclassified_action_value','ambiguous_diagnostics')}
    result['policy_execution_audit']['failure_reason_counts']=reasons
    result['policy_execution_audit']['parent_historical_counts']='unknown'
    result['effect_condition_passed']=result['continue_new_development']
    unresolved=any('候选整批失败' in reason for reason in reasons) or any(result['policy_execution_audit'][k] for k in ('unclassified_action_value','ambiguous_diagnostics'))
    result['requires_execution_failure_review']=unresolved
    if unresolved:result['continue_new_development']=False
    b.write(OUT/'summary.json',result);print('continue_new_development',result['continue_new_development'],flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['prepare','run','close']);args=parser.parse_args()
    {'prepare':prepare,'run':run,'close':close}[args.action]()
