"""固定四组已消费正负案例的双臂诊断，最多16桌，零作者和正式确认。"""

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
import asyncio
from collections import Counter
import strong_seed_batch as b
import sitin_natural_panel as natural
import route_executor_recovery as engine
import confirmation_execution_identity as guard
from confirmation_execution_probe import verify_arm
from diagnose_route_decisions import plan_view
from hangma_bot.policy.action_value_seeds import ActionValueScorer
from hangma_bot.policy.action_value_policy import ActionValuePolicy

SOURCE=b.HERE/'pattern-option-new-dev-20260920'
OUT=b.HERE/'pattern-generalization-diagnostic-20260920'


def main():
    """运行前冻结费用/依赖；先复现完整结果，再采纳离线旁路分歧。"""
    assert not OUT.exists(),'禁止隐式重复执行'
    original=b.read(SOURCE/'manifest.json');engine.verify(original)
    assert b.read(SOURCE/'closure.json')['decision']=='STOP_THIS_PROPOSAL_NO_CONFIRMATION_NO_PARAMETER_SWEEP'
    selection=b.read(SOURCE/'next-diagnostic-cases.json')
    contract=b.read(b.ROUTE/'contracts/group-dev-v1.json')
    parent=b.HERE/'v2-seed-terra-02/run/iterations/iter-01/generation/candidate.py'
    child=b.Path(original['sources']['candidate']['path'])
    sources={'parent':parent,'candidate':child}
    paths=list(b.HERE.glob('*.py'))+list(sources.values())+[b.ROUTE/'evidence/v4-impl/r9-gate2/run/p12_authorization.py']
    frozen=guard.capture(source_paths=paths)
    plan={'purpose':'consumed_development_positive_negative_diagnostic','cases':selection['cases'],
        'max_full_tables':16,'max_requests_per_stage':10000,'max_saved_disagreements_per_stage':8,
        'selection_rule':selection['selection_rule'],'selection_sha256':b.digest((SOURCE/'next-diagnostic-cases.json').read_bytes()),
        'original_manifest_sha256':b.digest((SOURCE/'manifest.json').read_bytes()),
        'runtime':frozen,'sources':{k:{'path':str(p),'sha256':b.digest(p.read_bytes())} for k,p in sources.items()},
        'created_at_utc':b.search.utc_now(),'model_calls':0,'confirmation_roots':0,'release_eligible':False}
    OUT.mkdir();(OUT/'windows').mkdir();b.write(OUT/'manifest.json',plan)
    auth=b.unified_document(batch_label='pattern-generalization-diagnostic',authorization_id='r10-pattern-generalization-diagnostic',
        accounts={'tables_full':16},issued_by='lead',issued_at_utc=b.search.utc_now(),legacy_alias=False)
    auth['issuance_basis']='用户持续推进授权；四组既有正负案例双臂诊断，最多16桌；不追加该候选效果评测'
    natural.require_authorization(auth);b.write(OUT/'authorization.json',auth)
    ledger=b.search.ActionValueLedger.load(OUT/'ledger.json',authorized_budgets=b.search.av_ledger_budgets_from_authorization(auth))
    scorers={k:ActionValueScorer(k,p.read_text()) for k,p in sources.items()}
    identity=scorers['candidate'].candidate_identity(b.digest((b.ROUTE.parents[1]/natural.AV_CONTRACT).read_bytes()))
    policies={k:ActionValuePolicy(s) for k,s in scorers.items()}
    policies['v2']=natural.stage.build_panel_policy(natural.BASELINE_FOCAL_POLICY,lambda:0.0)
    reports=[];entries={}
    for case in plan['cases']:
        panel_path=b.Path(case['panel_path']);assert b.digest(panel_path.read_bytes())==case['panel_sha256']
        panel=b.read(panel_path)
        sample=next(s for s in panel['samples'] if s['root_index']==case['root_index'] and s['focal_anchor_seat']==case['focal_anchor_seat'])
        plans=natural.build_seat_stage_plans(contract=contract,opponent=case['mix'],root_index=case['root_index'],
            focal_seat=case['focal_anchor_seat'],panel_seed=original['panel_seed'])
        for arm in ('baseline','candidate'):
            guard.verify(frozen);engine.verify(original)
            label=f"{case['mix']}-root{case['root_index']}-seat{case['focal_anchor_seat']}-{arm}"
            requests=[]
            def observe(request):
                if len(requests)>=plan['max_requests_per_stage']:raise ValueError('采集超出冻结上限')
                requests.append(request)
            reservation=ledger.reserve(step_id=label,account='tables_full',amount=2,note='已消费来源诊断，不新增效果样本')
            try:
                result=natural.run_arm_stage(arm=arm,plans=plans,candidate_scorer=scorers['candidate'],
                    opponent_policies=contract['panel']['opponent_scenarios'][case['mix']]['opponent_policies'],
                    versions_block=natural.stage.contract_versions_block(contract),step_limit=contract['stop']['step_limit'],
                    value_limits=natural.ValueAnalysisLimits(),decision_observer=observe)
            finally:ledger.settle(reservation,usage_unknown=True,note='异常按上界保守计费，成功再核验')
            b.write(OUT/(label+'-stage.json'),result)
            verify_arm(result,arm=arm,plans=plans,contract=contract,identity=identity,rules_hash=original['rules_hash'])
            expected=sample['raw_arms'][arm]
            for key in ('stage_totals_by_participant','stage_place_points_by_participant','u_low','u_high'):
                assert result[key]==expected[key],('stage not reproduced',label,key)
            for actual,old in zip(result['tables'],expected['tables'],strict=True):
                for key in ('scores_before','scores_after','completed_hands','expected_hands','runtime_counts','status','invalid_reasons'):
                    assert actual['result'][key]==old['result'][key],('table not reproduced',label,key)
            ledger.settle(reservation,actual=len(result['tables']))
            counts=Counter();rows=[]
            for index,request in enumerate(requests):
                view=b.behavior.build_scoring_view(request);window=b.behavior.digest(view.candidate_view())
                choices={k:plan_view(asyncio.run(policy.choose(request,b.behavior.DecisionBudget(1.,2.,3.)))) for k,policy in policies.items()}
                assert all(v['order'] and not v['degraded_reasons'] for v in choices.values()),('noncomparable diagnostic',label,index)
                mutation=choices['parent']['order'][0]!=choices['candidate']['order'][0]
                base_diff=choices['v2']['order'][0]!=choices['candidate']['order'][0]
                parent_diff=choices['v2']['order'][0]!=choices['parent']['order'][0]
                counts['requests']+=1;counts['mutation_first_changed']+=mutation
                counts['candidate_vs_v2_first_changed']+=base_diff;counts['parent_vs_v2_first_changed']+=parent_diff
                if (mutation or base_diff) and len(rows)<plan['max_saved_disagreements_per_stage']:
                    record=b.behavior.capture_request(request)
                    rows.append({'request_index':index,'window_id':window,'mutation_first_changed':mutation,
                        'candidate_vs_v2_first_changed':base_diff,'parent_vs_v2_first_changed':parent_diff,'choices':choices})
                    if window not in entries:
                        file='windows/'+window+'.json';b.write(OUT/file,record)
                        entries[window]={'file':file,'candidate_view_sha256':window,'record_sha256':b.behavior.digest(record)}
            report={'label':label,'direction':case['direction'],'arm':arm,'terminal_reproduced':True,'counts':dict(counts),'rows':rows}
            b.write(OUT/(label+'-diagnostic.json'),report);reports.append({k:v for k,v in report.items() if k!='rows'})
            print(reports[-1],flush=True)
    guard.verify(frozen)
    b.write(OUT/'panel.json',{'schema':'sitin-real-behavior-panel/1','purpose':'development_behavior','selection_eligible':False,
        'windows':list(entries.values()),'source':'manifest.json'})
    b.behavior.load_panel(OUT/'panel.json')
    assert ledger.spent('tables_full')==16
    b.write(OUT/'summary.json',{'status':'COMPLETE_DIAGNOSTIC_ONLY','reports':reports,'saved_windows':len(entries),
        'spent':ledger.account_summary(),'model_calls':0,'confirmation_roots':0,'release_eligible':False,
        'limits':'事后正负案例及每阶段前8个分歧，不能作效果或自然频率推断；旁路分数不证明反事实收益；逻辑时钟'})


if __name__=='__main__':main()
