"""仅重放另外两个已见故障第一桌，核对原终局并验证修复版的故障窗口。"""

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
import gzip
import json
import strong_seed_batch as b
import support_competition_second_panel as second
import support_runtime_repair_batch as repair
import confirmation_execution_identity as guard
import sitin_natural_panel as natural
from hangma_bot.policy.action_value_executor import ActionValueExecutor, WorkloadExceeded
from hangma_bot.policy.action_value_seeds import ActionValueScorer

OUT=b.HERE/'support-workload-remaining-20260920'

def main():
    """两桌固定诊断预算；原策略生成轨迹，修复只对已保存观察离线评分。"""
    assert not OUT.exists()
    plan=b.read(second.OUT/'manifest.json');second.verify_reused(plan)
    old=b.Path(plan['sources']['candidate']['path'])
    new=repair.OUT/repair.NAME/'run/iterations/iter-01/generation/candidate.py'
    assert b.read(repair.OUT/repair.NAME/'runtime-equivalence.json')['status']=='PASS'
    frozen=guard.capture(source_paths=list(b.HERE.glob('*.py'))+[old,new,b.ROUTE/'evidence/v4-impl/r9-gate2/run/p12_authorization.py'])
    cases=[('H',7,0),('M',3,0)]
    OUT.mkdir();b.write(OUT/'manifest.json',{'at_utc':b.search.utc_now(),'cases':cases,'max_full_tables':2,
        'runtime':frozen,'old_sha256':b.digest(old.read_bytes()),'new_sha256':b.digest(new.read_bytes()),
        'scope':'原策略故障轨迹定位，不产生修复版完整阶段效果，不新增独立样本。'})
    auth=b.unified_document(batch_label='support-remaining-workload',authorization_id='r10-support-remaining-workload',
        accounts={'tables_full':2},issued_by='lead',issued_at_utc=b.search.utc_now(),legacy_alias=False)
    auth['issuance_basis']='用户持续推进和修复授权；另外两张已见故障第一桌，最多2完整桌，零作者。'
    natural.require_authorization(auth);b.write(OUT/'authorization.json',auth)
    ledger=b.search.ActionValueLedger.load(OUT/'ledger.json',authorized_budgets=b.search.av_ledger_budgets_from_authorization(auth))
    contract=b.read(b.ROUTE/'contracts/group-dev-v1.json');reports=[]
    for mix,root,seat in cases:
        label=f'{mix}-root{root}-seat{seat}'
        parent_panel=b.read(second.OUT/'candidate'/('natural-'+mix)/'panel.json')
        expected=next(s for s in parent_panel['samples'] if s['root_index']==root and s['focal_anchor_seat']==seat)['raw_arms']['candidate']['tables'][0]
        plans=natural.build_seat_stage_plans(contract=contract,opponent=mix,root_index=root,focal_seat=seat,panel_seed=plan['panel_seed'])[:1]
        requests=[]
        reservation=ledger.reserve(step_id=label,account='tables_full',amount=1,note='已见故障定位，不作效果样本')
        try:
            result=natural.run_arm_stage(arm='candidate',plans=plans,candidate_scorer=ActionValueScorer('av-candidate',old.read_text()),
                opponent_policies=contract['panel']['opponent_scenarios'][mix]['opponent_policies'],
                versions_block=natural.stage.contract_versions_block(contract),step_limit=contract['stop']['step_limit'],
                value_limits=natural.ValueAnalysisLimits(),decision_observer=requests.append)
        finally:ledger.settle(reservation,usage_unknown=True,note='先保守计费')
        b.write(OUT/(label+'-table.json'),result)
        with gzip.open(OUT/(label+'-requests.json.gz'),'wt',encoding='utf-8') as handle:
            json.dump([b.behavior.capture_request(r) for r in requests],handle,ensure_ascii=False)
        assert result['status']=='complete' and len(result['tables'])==1
        actual=result['tables'][0]
        for key in ('table_id','seed','match_status','scores_by_seat','stage_situation','result'):assert actual[key]==expected[key],key
        ledger.settle(reservation,actual=1)
        before=ActionValueExecutor(old.read_text());reference=ActionValueExecutor(old.read_text(),max_operations=1000000)
        after=ActionValueExecutor(new.read_text());failures=[];errors=[];maximum=0
        for i,request in enumerate(requests):
            view=b.behavior.build_scoring_view(request);old_failed=False
            try:a=before.score(view)
            except WorkloadExceeded:old_failed=True;a=reference.score(view)
            try:z=after.score(view)
            except WorkloadExceeded as exc:
                errors.append({'request_index':i,'reason':str(exc)});continue
            maximum=max(maximum,after.last_operation_count)
            left={'status':a.status,'entries':{e.action_key:{'score':e.score,'trace':dict(e.trace)} for e in a.entries}}
            right={'status':z.status,'entries':{e.action_key:{'score':e.score,'trace':dict(e.trace)} for e in z.entries}}
            if json.dumps(left,sort_keys=True)!=json.dumps(right,sort_keys=True):errors.append({'request_index':i,'reason':'output_difference'})
            if old_failed:
                failures.append({'request_index':i,'old_operations':reference.last_operation_count,'new_operations':after.last_operation_count})
                b.write(OUT/(label+'-failure-'+str(i)+'.json'),b.behavior.capture_request(request))
        report={'label':label,'terminal_reproduced':True,'requests':len(requests),'old_failures':failures,'errors':errors,'maximum_repaired_operations':maximum}
        b.write(OUT/(label+'-verification.json'),report);reports.append(report)
        print(report,flush=True)
    guard.verify(frozen)
    assert sum(len(r['old_failures']) for r in reports)==3
    passed=all(not r['errors'] for r in reports)
    b.write(OUT/'summary.json',{'status':'PASS' if passed else 'FAIL','reports':reports,'full_tables':2,
        'model_calls':0,'scope':'仅固定旧轨迹输出等价及成本验证，未评估修复后新轨迹的强度或全域最坏成本。'})
    assert passed

if __name__=='__main__':main()
