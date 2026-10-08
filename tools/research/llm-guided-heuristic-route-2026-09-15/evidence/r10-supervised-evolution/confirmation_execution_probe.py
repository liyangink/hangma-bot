"""确认赛程的真实执行接线探针：只允许已曝光开发用途，不能签发正式确认。"""

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
import json
from pathlib import Path
import strong_seed_batch as b
import confirmation_pairing as pairing
import confirmation_draft as analysis
import curate_pattern_trace as candidate
import route_executor_recovery as engine
import sitin_natural_panel as natural
import verify_natural_evidence as summary_verify
import verify_full_natural_results as full_verify
from hangma_bot.policy.action_value_seeds import ActionValueScorer

OUT=b.HERE/'confirmation-execution-check-20260920'


def execution_sources():
    """绑定探针及其核验器，改实现后拒绝恢复旧执行。"""
    modules=[Path(__file__),Path(pairing.__file__),Path(summary_verify.__file__),Path(full_verify.__file__)]
    return {str(p):b.digest(p.read_bytes()) for p in modules}


def prepare():
    """冻结32桌开发检查；不消耗正式确认显著性或确认预算。"""
    assert not OUT.exists()
    contract=b.read(b.ROUTE/'contracts/group-dev-v1.json')
    source=candidate.OUT/'candidate.py'
    assert b.read(candidate.OUT/'admission.json')['execution_safety_pass']
    roots=[pairing.build_root_plan(contract=contract,registration_seed=91237,opponent=m,root_index=1) for m in ('H','M')]
    old=b.read(b.HERE/'pattern-option-new-dev-20260920/manifest.json')
    plan={**old,'created_at_utc':b.search.utc_now(),'sources':{'candidate':{'path':str(source),'sha256':b.digest(source.read_bytes())}},
        'root_plans':roots,'execution_sources':execution_sources(),'full_tables':32,'max_full_tables':32,
        'scope':'已曝光开发种子上的执行接线检查，不参与候选效果选留，不是正式确认',
        'model_calls':0,'confirmation_roots':0,'formal_alpha_spent':0,'release_eligible':False}
    # 去除继承自另一批的随机来源/分流字段，避免探针冒充新开发验证。
    for key in ('panel_seed','roots','tables_per_source','decision_rule','previous_summary_sha256','seed_selection','seed_inventory_scan'):
        plan.pop(key,None)
    engine.verify(plan)
    OUT.mkdir();b.write(OUT/'manifest.json',plan)
    auth=b.unified_document(batch_label='confirmation-execution-check',authorization_id='r10-confirmation-execution-check',
        accounts={'tables_full':32},issued_by='lead',issued_at_utc=b.search.utc_now(),legacy_alias=False)
    auth['issuance_basis']='用户持续推进授权；已曝光测试种子的32桌确认执行接线验证，零模型，正式确认账户为0'
    b.write(OUT/'authorization.json',auth)
    print('prepared 32 development wiring tables',flush=True)


def verify_identity(plan):
    """每个臂调用前和恢复时复核源码、规则、合同、核验器与赛程。"""
    engine.verify(plan)
    assert plan['execution_sources']==execution_sources()
    for root in plan['root_plans']:
        body=dict(root);digest=body.pop('root_content_digest')
        assert analysis.digest(body)==digest


def verify_arm(raw, *, arm, plans, contract, identity, rules_hash):
    """复用阶段账复算及完整MatchResult核验，不用产物自报成功代替验收。"""
    slim=natural._arm_sample_view(raw,candidate_id=identity,is_candidate=arm=='candidate',baseline_id=b.search.AV_BASELINE_ID)
    summary_verify._verify_arm(raw,slim,label=arm,identity=identity if arm=='candidate' else b.search.AV_BASELINE_ID,
        plans=plans,rounds=contract['versions']['rounds_per_game'])
    checks=[full_verify.verify_full_table(table,expected,contract,rules_hash,require_execution_audit=True)
        for table,expected in zip(raw['tables'],plans,strict=True)]
    review=natural.execution_audit.review_tables(raw['tables'])
    if raw.get('execution_review')!=review:
        raise ValueError('阶段评分执行汇总不符')
    return {'tables':len(checks),'results_digest':analysis.digest(checks),'slim':slim,
            'execution_review':review}


def execute_arm(folder, *, expected, ledger, runner, verifier):
    """先预留后标开始；完整产物可恢复，只有开始标记而无结果时拒绝盲跑。

    runner返回原始两桌阶段结果。失败或进程中断用量不明时保留全部预留。
    此探针只允许单进程驱动同一个folder；跨进程竞争由独占begin文件拒绝。
    """
    folder.mkdir(parents=True,exist_ok=True)
    begun=folder/'begin.json';result_path=folder/'result.json';reservation=None
    if begun.exists():
        begin=b.read(begun)
        if begin['expected']!=expected:raise ValueError('恢复身份不一致')
        reservation=begin['reservation']
        if not result_path.exists():raise ValueError('已开始但没有完整产物，拒绝盲目重跑或退款')
    else:
        reservation=ledger.reserve(step_id=expected['step_id'],account='tables_full',amount=expected['planned_tables'],note='确认执行接线开发检查')
        # 独占创建，禁止第二进程覆盖派发标记；若冲突，预留也不得隐式退费。
        with begun.open('x',encoding='utf-8') as stream:
            stream.write(json.dumps({'expected':expected,'reservation':reservation},ensure_ascii=False))
        raw=runner()
        b.write(result_path,{'expected':expected,'raw':raw,'raw_digest':analysis.digest(raw)})
    bundle=b.read(result_path)
    if bundle['expected']!=expected or analysis.digest(bundle['raw'])!=bundle['raw_digest']:
        raise ValueError('完整产物身份或摘要漂移')
    try:checked=verifier(bundle['raw'])
    except Exception:
        ledger.settle(reservation,usage_unknown=True,note='核验失败，保守保留计划费用，不选留不重跑')
        raise
    assert checked['tables']==expected['planned_tables']
    ledger.settle(reservation,actual=checked['tables'],note='完整MatchResult及阶段账核验通过')
    b.write(folder/'verified.json',checked)
    return checked


def run():
    """顺序执行或核验已有完整臂；不打印/使用开发探针效果作选留。"""
    plan=b.read(OUT/'manifest.json');verify_identity(plan)
    auth=b.read(OUT/'authorization.json');natural.require_authorization(auth)
    ledger=b.search.ActionValueLedger.load(OUT/'ledger.json',authorized_budgets=b.search.av_ledger_budgets_from_authorization(auth))
    contract=b.read(b.ROUTE/'contracts/group-dev-v1.json')
    source=b.Path(plan['sources']['candidate']['path']).read_text()
    scorer=ActionValueScorer('confirmation-execution-development-probe',source)
    identity=scorer.candidate_identity(b.digest((b.ROUTE.parents[1]/natural.AV_CONTRACT).read_bytes()))
    total=0;readings=[]
    for root in plan['root_plans']:
        mix=root['opponent_mix']
        for cfg in root['configurations']:
            plans=[natural.stage.TablePlan.from_json(x) for x in cfg['tables']]
            for arm in ('baseline','candidate'):
                verify_identity(plan)
                label=f"{mix}-seat{cfg['focal_anchor_seat']}-{arm}"
                expected={'step_id':label,'planned_tables':len(plans),'root_content_digest':root['root_content_digest'],
                    'manifest_digest':analysis.digest(plan),'plans_digest':analysis.digest(cfg),'arm':arm,'candidate_id':identity}
                checked=execute_arm(OUT/'arms'/label,expected=expected,ledger=ledger,
                    runner=lambda:natural.run_arm_stage(arm=arm,plans=plans,candidate_scorer=scorer,
                        opponent_policies=contract['panel']['opponent_scenarios'][mix]['opponent_policies'],
                        versions_block=natural.stage.contract_versions_block(contract),step_limit=contract['stop']['step_limit'],value_limits=natural.ValueAnalysisLimits()),
                    verifier=lambda raw:verify_arm(raw,arm=arm,plans=plans,contract=contract,identity=identity,rules_hash=plan['rules_hash']))
                total+=checked['tables'];readings.append({'label':label,'results_digest':checked['results_digest']})
        print(mix,'wiring verified',flush=True)
    verify_identity(plan)
    assert total==32 and ledger.spent('tables_full')==32
    b.write(OUT/'summary.json',{'status':'COMPLETE_DEVELOPMENT_WIRING_CHECK','full_tables_verified':total,'readings':readings,
        'spent':ledger.account_summary(),'model_calls':0,'confirmation_roots':0,'formal_alpha_spent':0,
        'selection_eligible':False,'release_eligible':False,'scope':'真实模拟执行接线，不评算法效果，不代表正式确认或真实动作时限'})
    print('32 complete tables verified; no algorithm selection claim',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);args=p.parse_args()
    prepare() if args.action=='prepare' else run()
