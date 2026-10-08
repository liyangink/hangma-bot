"""已曝光首个超额窗口定位：只重放其阶段第一桌，单独计1完整桌，不新增强度样本。"""

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
import confirmation_execution_identity as guard
import sitin_natural_panel as natural
from hangma_bot.policy.action_value_seeds import ActionValueScorer
from hangma_bot.policy.action_value_executor import WorkloadExceeded, ActionValueExecutor

OUT=b.HERE/'support-workload-diagnostic-20260920'

def main():
    """公开请求与失败评分视图先存证，复现终局在完整旧面板落盘后核对。"""
    assert not OUT.exists()
    source_plan=b.read(second.OUT/'manifest.json');second.verify_reused(source_plan)
    audit_rows=[json.loads(line) for line in (second.OUT/'candidate/policy-execution.jsonl').read_text().splitlines()]
    first=next(r for r in audit_rows if any('WorkloadExceeded' in s for s in r['audit']['failure_reason_counts']))
    assert first['table_id']=='np-H-2026092097-r02-s3-t1'
    source=b.Path(source_plan['sources']['candidate']['path']);scorer=ActionValueScorer('av-candidate',source.read_text())
    contract=b.read(b.ROUTE/'contracts/group-dev-v1.json')
    plans=natural.build_seat_stage_plans(contract=contract,opponent='H',root_index=2,focal_seat=3,panel_seed=2026092097)[:1]
    assert len(plans)==1 and plans[0].table_id==first['table_id']
    frozen=guard.capture(source_paths=list(b.HERE.glob('*.py'))+[source,b.ROUTE/'evidence/v4-impl/r9-gate2/run/p12_authorization.py'])
    OUT.mkdir();b.write(OUT/'manifest.json',{'created_at_utc':b.search.utc_now(),'max_full_tables':1,'model_calls':0,
        'source':source_plan['sources']['candidate'],'selected_first_failure':first,'runtime':frozen,
        'scope':'已曝光首个运行成本故障定位，只重放第一桌；不用于阶段强度或独立确认'})
    auth=b.unified_document(batch_label='support-workload-diagnostic',authorization_id='r10-support-workload-diagnostic',
        accounts={'tables_full':1},issued_by='lead',issued_at_utc=b.search.utc_now(),legacy_alias=False)
    auth['issuance_basis']='用户持续推进和修复授权；真实操作超额首例，1完整桌诊断，不改正在评测的源码。'
    natural.require_authorization(auth);b.write(OUT/'authorization.json',auth)
    ledger=b.search.ActionValueLedger.load(OUT/'ledger.json',authorized_budgets=b.search.av_ledger_budgets_from_authorization(auth))
    requests=[];failures=[]
    class CaptureScorer:
        """只保存失败输入并原样抛错，让生产策略执行同一保底路径。"""
        name=scorer.name
        def score(self,view):
            try:return scorer.score(view)
            except WorkloadExceeded as exc:
                failures.append({'request_index':len(requests)-1,'error':str(exc),'view':view.candidate_view()})
                raise
    reservation=ledger.reserve(step_id='first-workload-table',account='tables_full',amount=1,note='已见故障定位')
    try:
        result=natural.run_arm_stage(arm='candidate',plans=plans,candidate_scorer=CaptureScorer(),
            opponent_policies=contract['panel']['opponent_scenarios']['H']['opponent_policies'],
            versions_block=natural.stage.contract_versions_block(contract),step_limit=contract['stop']['step_limit'],
            value_limits=natural.ValueAnalysisLimits(),decision_observer=requests.append)
    finally:ledger.settle(reservation,usage_unknown=True,note='先保守计费，完整桌核实后结算')
    b.write(OUT/'table-replay.json',result)
    with gzip.open(OUT/'requests.json.gz','wt',encoding='utf-8') as handle:
        json.dump([b.behavior.capture_request(r) for r in requests],handle,ensure_ascii=False)
    b.write(OUT/'failures.json',failures)
    assert result['status']=='complete' and len(result['tables'])==1
    table=result['tables'][0];assert table['result']['status']=='complete' and table['result']['completed_hands']==8
    assert len(failures)==1
    request=requests[failures[0]['request_index']];b.write(OUT/'failing-request.json',b.behavior.capture_request(request))
    executor=ActionValueExecutor(source.read_text());error=None
    try:executor.score(b.behavior.build_scoring_view(request))
    except WorkloadExceeded as exc:error=str(exc)
    assert error and executor.last_operation_count==100001
    ledger.settle(reservation,actual=1);guard.verify(frozen)
    b.write(OUT/'summary.json',{'status':'REPRODUCED_WORKLOAD_FAILURE','requests':len(requests),'failures':len(failures),
        'operation_count':executor.last_operation_count,'full_tables':1,'model_calls':0,
        'source_sha256':b.digest(source.read_bytes()),'original_terminal_comparison':'pending full panel closure',
        'note':'只重放第一桌，run_arm_stage返回的单桌U不作阶段效果；等待原完整面板落盘后逐桌核对。'})
    print('REPRODUCED',len(requests),'requests',executor.last_operation_count,'operations','1 full table',flush=True)

if __name__=='__main__':main()
