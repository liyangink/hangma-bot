"""首清单双正后才运行第二已见开发清单；原父子同核心对照，零新增作者。"""

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
import pattern_option_batch as first
import diverse_second_panel as previous
import route_executor_recovery as engine

OUT=b.HERE/'pattern-option-second-dev-20260920'
NAMES=('parent','candidate')


def prepare():
    """冻结512完整桌的原父子对照，不把重复已见开发根冒充独立确认。"""
    assert not OUT.exists()
    sub=first.OUT/first.NAME
    decision=sub/'development-decision.json';closure=sub/'batch-closure.json'
    assert b.read(decision)['continue_second_seen_panel'] is True
    assert b.read(closure)['full_natural_results_verified']==256
    first_plan=b.read(first.OUT/'manifest.json')
    state=b.search.av_state_load(b.search.av_latest_state_path(sub/'run'))
    assert state['status']=='ITERATION_COMPLETE' and b.search.av_verify_run_identity(state)[0]
    paths={'parent':b.Path(first_plan['parent'])/'candidate.py',
           'candidate':b.Path(state['iter_dir'])/'generation/candidate.py'}
    old=b.read(previous.OUT/'manifest.json')
    plan={**old,'created_at_utc':b.search.utc_now(),
        'sources':{k:{'path':str(p),'sha256':b.digest(p.read_bytes())} for k,p in paths.items()},
        'full_tables':512,'max_full_tables':512,'tables_per_source':256,
        'scope':'普通型/七对选择M1第二已见开发清单；同核心父子各256桌，零作者，非独立确认',
        'first_panel_decision_sha256':b.digest(decision.read_bytes()),
        'first_panel_closure_sha256':b.digest(closure.read_bytes()),
        'decision_rule':'第一清单已通过，本清单H/M对V2均正且对原父代等权识别差下界正，才进入预登记新开发验证；否则本提案停止追加，不修常数。',
        'trace_caveat':'候选未知底分标签仍沿用父代旧名称；严格低于所有已知成立，若晋升须澄清标签并重验。此处保持原源码进行第二清单复核。',
        'model_calls':0,'confirmation_roots':0,'release_eligible':False}
    engine.verify(plan)
    OUT.mkdir();b.write(OUT/'manifest.json',plan)
    for name,path in paths.items():
        folder=OUT/name;folder.mkdir()
        admission=b.search.av_gates().admit_action_value(path.read_text())
        b.write(folder/'admission.json',admission)
        assert admission['execution_safety_pass']
        auth=b.unified_document(batch_label='pattern-second-'+name,authorization_id='r10-pattern-second-'+name,
            accounts={'tables_full':256},issued_by='lead',issued_at_utc=b.search.utc_now(),legacy_alias=False)
        auth['issuance_basis']='用户持续推进授权；已完成第一清单固定分流，原父子第二已见清单各256桌，零新增作者'
        b.write(folder/'authorization.json',auth)
    b.write(OUT/'prepared.json',{'status':'READY','at_utc':b.search.utc_now()})
    print('prepared',plan['panel_seed'],512,flush=True)


def run(name):
    """执行前复核原始分流摘要；每来源独立账本，不隐式重跑。"""
    plan=b.read(OUT/'manifest.json')
    sub=first.OUT/first.NAME
    assert b.digest((sub/'development-decision.json').read_bytes())==plan['first_panel_decision_sha256']
    assert b.digest((sub/'batch-closure.json').read_bytes())==plan['first_panel_closure_sha256']
    engine.OUT=OUT;engine.run(name)


def close():
    """复用已审查原始结果与配对根统计，明确产物是第二开发清单。"""
    engine.OUT=OUT;engine.NAMES=NAMES;engine.close()
    result=b.read(OUT/'summary.json')
    result['continue_new_development']=result.pop('continue_second_seen_panel')
    result['scope']='第二已见开发清单；识别区间非置信区间，未进入独立确认'
    b.write(OUT/'summary.json',result)
    print('continue_new_development',result['continue_new_development'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['prepare','run','close'])
    p.add_argument('--name',choices=NAMES)
    args=p.parse_args()
    if args.action=='prepare':prepare()
    elif args.action=='close':close()
    elif args.name:run(args.name)
    else:p.error('run需要name')
