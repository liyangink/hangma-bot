"""第二清单中同M情景一正一负的完整双臂复演；最多8桌，只生成诊断。"""

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
import gzip
import json

import selfdraw_tempo_second_panel as previous
import confirmation_execution_identity as guard
from confirmation_execution_probe import verify_arm
from diagnose_route_decisions import plan_view
from hangma_bot.policy.action_value_seeds import ActionValueScorer
from hangma_bot.policy.action_value_policy import ActionValuePolicy

b=previous.b
natural=previous.natural
OUT=b.HERE/'selfdraw-tempo-diagnostic-20260920'


def main():
    """按根/座位次序固定正负案例，先复现终局再采纳已见窗口的评分差异。"""
    assert not OUT.exists(),'不重复消费诊断预算'
    original=b.read(previous.OUT/'manifest.json');source=previous.verify(original)
    summary=b.read(previous.OUT/'summary.json')
    assert summary['continue_new_development'] is False and summary['zero_internal_failures_verified']
    panel_path=previous.OUT/'natural-M/panel.json';panel=b.read(panel_path)
    cases=[]
    for direction in ('negative','positive'):
        for sample in sorted(panel['samples'],key=lambda s:(s['root_index'],s['focal_anchor_seat'])):
            a,z=sample['arms']['candidate'],sample['arms']['baseline']
            low,high=a['u_low']-z['u_high'],a['u_high']-z['u_low']
            if (high<0 if direction=='negative' else low>0):
                cases.append({'direction':direction,'mix':'M','root_index':sample['root_index'],
                    'focal_anchor_seat':sample['focal_anchor_seat'],'delta_low':low,'delta_high':high})
                break
    assert len(cases)==2
    frozen=guard.capture(source_paths=[*b.HERE.glob('*.py'),b.Path(original['source']['path'])])
    plan={'schema':'selfdraw-tempo-paired-diagnostic/1','created_at_utc':b.search.utc_now(),
        'cases':cases,'panel_path':str(panel_path),'panel_sha256':b.digest(panel_path.read_bytes()),
        'source':original['source'],'panel_seed':original['panel_seed'],
        'max_full_tables':8,'max_requests_per_stage':10000,'max_saved_disagreements_per_stage':8,
        'selection_rule':'第二已见清单M中按根/座位升序分别选最早严格负和严格正的配置；双臂各2桌',
        'runtime':frozen,'model_calls':0,'confirmation_roots':0,'release_eligible':False}
    OUT.mkdir();(OUT/'windows').mkdir();b.write(OUT/'manifest.json',plan)
    auth=b.unified_document(batch_label='selfdraw-tempo-diagnostic',authorization_id='r10-selfdraw-tempo-diagnostic',
        accounts={'tables_full':8},issued_by='lead',issued_at_utc=b.search.utc_now(),legacy_alias=False)
    auth['issuance_basis']='用户持续推进授权；第二清单失败后同情景一正一负已消费配置诊断，8桌，不扩充效果样本'
    natural.require_authorization(auth);b.write(OUT/'authorization.json',auth)
    ledger=b.search.ActionValueLedger.load(OUT/'ledger.json',authorized_budgets=b.search.av_ledger_budgets_from_authorization(auth))
    contract=b.read(b.ROUTE/'contracts/group-dev-v1.json')
    scorer=ActionValueScorer('selfdraw-tempo-diagnostic',source)
    identity=scorer.candidate_identity(b.digest((b.ROUTE.parents[1]/natural.AV_CONTRACT).read_bytes()))
    recorder=b.behavior.RecordingScorer(scorer)
    policies={'candidate':ActionValuePolicy(recorder),
        'v2':natural.stage.build_panel_policy(natural.BASELINE_FOCAL_POLICY,lambda:0.0)}
    reports=[];entries={}
    for case in cases:
        assert b.digest(panel_path.read_bytes())==plan['panel_sha256']
        sample=next(s for s in panel['samples'] if s['root_index']==case['root_index'] and s['focal_anchor_seat']==case['focal_anchor_seat'])
        plans=natural.build_seat_stage_plans(contract=contract,opponent=case['mix'],
            root_index=case['root_index'],focal_seat=case['focal_anchor_seat'],panel_seed=plan['panel_seed'])
        for arm in ('baseline','candidate'):
            guard.verify(frozen);previous.verify(original)
            label=f"M-root{case['root_index']}-seat{case['focal_anchor_seat']}-{arm}"
            requests=[]
            def observe(request):
                if len(requests)>=plan['max_requests_per_stage']:raise ValueError('超过冻结请求上限')
                requests.append(request)
            reservation=ledger.reserve(step_id=label,account='tables_full',amount=len(plans),note='已消费配置的诊断复演，不新增效果样本')
            try:
                raw=natural.run_arm_stage(arm=arm,plans=plans,candidate_scorer=scorer,
                    opponent_policies=contract['panel']['opponent_scenarios'][case['mix']]['opponent_policies'],
                    versions_block=natural.stage.contract_versions_block(contract),step_limit=contract['stop']['step_limit'],
                    value_limits=natural.ValueAnalysisLimits(),decision_observer=observe)
            finally:ledger.settle(reservation,usage_unknown=True,note='若异常保守留存全部预留，成功后按实际核对')
            b.write(OUT/(label+'-stage.json'),raw)
            with gzip.open(OUT/(label+'-requests.json.gz'),'wt',encoding='utf-8') as stream:
                json.dump([b.behavior.capture_request(r) for r in requests],stream,ensure_ascii=False)
            verified=verify_arm(raw,arm=arm,plans=plans,contract=contract,identity=identity,rules_hash=original['rules_hash'])
            expected=sample['raw_arms'][arm]
            for key in ('stage_totals_by_participant','stage_place_points_by_participant','u_low','u_high'):
                assert raw[key]==expected[key],('stage mismatch',label,key)
            for actual,old in zip(raw['tables'],expected['tables'],strict=True):
                for key in ('scores_before','scores_after','completed_hands','expected_hands','runtime_counts','status','invalid_reasons'):
                    assert actual['result'][key]==old['result'][key],('table mismatch',label,key)
            ledger.settle(reservation,actual=len(raw['tables']))
            counts=Counter();transitions=Counter();rows=[]
            for index,request in enumerate(requests):
                recorder.batch=None
                choices={name:plan_view(asyncio.run(policy.choose(request,b.behavior.DecisionBudget(1.,2.,3.)))) for name,policy in policies.items()}
                assert recorder.batch is not None and recorder.batch.status=='SCORED',('unscored diagnostic',label,index)
                old,new=choices['v2']['order'][0],choices['candidate']['order'][0]
                counts['requests']+=1
                if old==new:continue
                counts['first_changed']+=1
                transitions[old.split(':')[0]+' -> '+new.split(':')[0]]+=1
                maps={name:{c['action_key']:c for c in choice['candidates']} for name,choice in choices.items()}
                counts['v2_tie']+=int(abs(maps['v2'][old]['total_score']-maps['v2'][new]['total_score'])<1e-9)
                counts['candidate_tie']+=int(abs(maps['candidate'][old]['total_score']-maps['candidate'][new]['total_score'])<1e-9)
                if len(rows)<plan['max_saved_disagreements_per_stage']:
                    record=b.behavior.capture_request(request);window=record['candidate_view_sha256']
                    rows.append({'request_index':index,'window_id':window,'choices':choices})
                    if window not in entries:
                        file='windows/'+window+'.json';b.write(OUT/file,record)
                        entries[window]={'file':file,'candidate_view_sha256':window,'record_sha256':b.behavior.digest(record)}
            report={'label':label,'direction':case['direction'],'arm':arm,'terminal_reproduced':True,
                'verification':verified,'counts':dict(counts),'transitions':dict(transitions),'rows':rows}
            b.write(OUT/(label+'-diagnostic.json'),report)
            reports.append({k:v for k,v in report.items() if k not in ('rows','verification')})
            print(reports[-1],flush=True)
    guard.verify(frozen);previous.verify(original)
    b.write(OUT/'panel.json',{'schema':'sitin-real-behavior-panel/1','purpose':'development_behavior',
        'selection_eligible':False,'windows':list(entries.values()),'source':'manifest.json'})
    b.behavior.load_panel(OUT/'panel.json')
    assert ledger.spent('tables_full')==8
    b.write(OUT/'summary.json',{'status':'COMPLETE_DIAGNOSTIC_ONLY','reports':reports,'saved_windows':len(entries),
        'spent':ledger.account_summary(),'full_tables':8,'model_calls':0,'confirmation_roots':0,'release_eligible':False,
        'limits':'事后选择同M情景正负配置，不是无偏样本；各阶段前8分歧只是解释材料；双臂共享窗口不算独立观察；不从终局正负归因某一步动作'})
    print('diagnostic complete: 8 tables reproduced',flush=True)


if __name__=='__main__':main()
