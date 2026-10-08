"""T199 P0全计划等价及规则分析前起算的原/名义截止，使用真实每桌专属计算。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t199-four-step-execution-1/runtime/performance'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import asyncio
from dataclasses import asdict
import os
import multiprocessing
from pathlib import Path
import time

from performance_common import HERE, ROOT, P0, OUT, P0Factory, digest, make_request, package, pin, policy, read, resource_zero, root_unchanged, save, slots


async def reference(attempt, resource_slots):
    """一次P0 Python和一次checked native完整choose；宽预算不授截止。"""
    from hangma_bot.application.audit_codec import decision_plan_to_json
    from hangma_bot.policy.interface import DecisionBudget
    inputs=read(OUT/'INPUTS.json');payload=package()
    path=OUT/('reference-'+attempt);path.mkdir(exist_ok=False)
    refs=[];attempts=0;score_calls=0;failure=None
    save(path/'START.json',{'planned_choices':2*len(inputs['rows']),'cpu_nice':os.getpriority(os.PRIO_PROCESS,0),'pid':os.getpid(),'resource_slots':resource_slots,
        'input_pin':pin(OUT/'INPUTS.json'),'P0_identity':payload['candidate_identity'],'HTTP_Token':0})
    journal=(path/'rows.jsonl').open('x')
    try:
        for case in inputs['rows']:
            request,rules=make_request(case)
            plans=[];receipts=[]
            for compiled in (False,True):
                choice=policy(compiled);original_score=choice.executor.score_vip_route
                def counted(view):
                    nonlocal score_calls
                    score_calls+=1
                    return original_score(view)
                choice.executor.score_vip_route=counted
                now=time.monotonic();attempts+=1
                plan=await choice.choose(request,DecisionBudget(now+30,now+31,now+32))
                elapsed=time.monotonic()-now
                encoded=decision_plan_to_json(plan);plans.append(encoded)
                receipts.append({'compiled':compiled,'elapsed_seconds':elapsed,'full_plan_sha256':digest(encoded)})
            if plans[0]!=plans[1]:
                save(path/('MISMATCH-%03d.json'%len(refs)),{'label':case['label'],'reference':plans[0],'native':plans[1]})
                raise ValueError('P0参考/编译完整计划不一致:'+case['label'])
            row={'label':case['label'],'decision_id':request.decision_id,'game_id':request.window_key.game_id,
                'rule_completeness':rules.completeness.value,'legal_action_keys':[c.action_key for c in rules.legal_candidates],
                'emergency_action_key':rules.emergency_candidate.action_key,'full_plan_sha256':digest(plans[0]),'receipts':receipts,
                'complete':True,'original_remaining_seconds':case['original_remaining_seconds']}
            refs.append(row);journal.write(__import__('json').dumps(row,ensure_ascii=False)+'\n');journal.flush()
            print({'reference_done':len(refs),'total':len(inputs['rows']),'label':case['label']},flush=True)
    except Exception as error:
        failure={'type':type(error).__name__,'message':str(error)}
    finally:
        journal.close()
        complete=failure is None and len(refs)==len(inputs['rows'])
        save(path/'CLOSED.json',{'complete':complete,'failure':failure,'references':refs,'actual_choose_attempts':attempts,
            'actual_candidate_score_calls':score_calls,'input_pin':pin(OUT/'INPUTS.json'),'P0_identity':payload['candidate_identity'],
            'package_id':payload['release_package_id'],'rules_source_hash':inputs['rules_source_hash'],'HTTP_Token_tables':0,
            'wide_functional_budget_not_deadline_evidence':True,'source_tool_pins':{str(p):pin(p) for p in (Path(__file__),_project_file(_PROJECT_ROOT, HERE/'performance_common.py'))}})
    if failure:raise ValueError(failure)


async def deadlines(attempt, reference_attempt, resource_slots):
    """原39余量及名义窗口分账；规则分析与IPC共计时，十桌波不改真实桌ID。"""
    from hangma_bot import bootstrap as b
    from hangma_bot.application.audit_codec import decision_plan_to_json
    from hangma_bot.application.deadline import BudgetPolicy,SystemClock
    from hangma_bot.policy.interface import DecisionBudget
    if os.getpriority(os.PRIO_PROCESS,0)!=0:raise ValueError('实际性能必须正常CPU优先级')
    reference_path=OUT/('reference-'+reference_attempt)/'CLOSED.json'
    inputs=read(OUT/'INPUTS.json');ref=read(reference_path)
    if not ref['complete'] or ref['input_pin']!=pin(OUT/'INPUTS.json'):raise ValueError('P0完整计划参考未闭')
    refs={r['label']:r for r in ref['references']};payload=package()
    runtime=b._load_vip_s03_runtime(payload['compiled_runtime']['manifest_sha256'])
    settings=b.VIP_S02_COMPUTE_SETTINGS
    if settings.workers!=10 or not settings.per_game_workers or settings.max_pending!=0:raise ValueError('十桌专属配置不符')
    output=OUT/('deadlines-'+attempt);output.mkdir(exist_ok=False)
    save(output/'START.json',{'input_pin':pin(OUT/'INPUTS.json'),'reference_pin':pin(reference_path),
        'cpu_nice':os.getpriority(os.PRIO_PROCESS,0),'pid':os.getpid(),'resource_slots':resource_slots,'compute_settings':asdict(settings),'timing_origin':'before P0 rule analysis',
        'original_spans_not_extended':True,'HTTP_Token_tables':0,'root_before':root_unchanged()})
    journal=(output/'rows.jsonl').open('x');waves=[];calls=0;failure=None

    async def wave(label,selected,concurrent):
        nonlocal calls
        gids=list(dict.fromkeys(c['window_key']['game_id'] for c in selected))
        if len(gids)>10:raise ValueError('一波超过十真实桌')
        service=b.build_isolated_decision_policy(P0Factory(runtime.execution_id),execution_id=runtime.execution_id,
            clock=SystemClock(),settings=settings)
        value={'wave':label,'rows':[],'game_ids':gids,'concurrent':concurrent};startup=time.monotonic()
        try:
            await service.start()
            for gid in gids:await service.acquire_game(gid)
            value['startup_and_binding_seconds']=time.monotonic()-startup
            value['pre_choose_resources']=service.snapshot()
            value['worker_pids']=[{'pid':child.pid,'name':child.name,'cpu_nice':os.getpriority(os.PRIO_PROCESS,child.pid)} for child in multiprocessing.active_children()]
            if len(value['worker_pids'])!=10 or any(child['cpu_nice']!=0 for child in value['worker_pids']):raise ValueError('实际十worker或正常CPU优先级不符')
            if value['pre_choose_resources']['bound_games']!=len(gids):raise ValueError('专属桌绑定不符')
            async def one(case,shared_start=None):
                nonlocal calls
                now=shared_start if shared_start is not None else time.monotonic()
                spans=case['original_remaining_seconds']
                budget=DecisionBudget(*(now+v for v in spans)) if spans else BudgetPolicy().build(now,case['nominal_seconds'])
                relative=[getattr(budget,k)-now for k in ('enhancement_deadline_monotonic','fallback_deadline_monotonic','latest_send_at_monotonic')]
                request,rules=make_request(case);after_rules=time.monotonic();plan=None;error=None;calls+=1
                try:plan=await service.choose(request,budget)
                except Exception as exception:error={'type':type(exception).__name__,'message':str(exception)}
                returned=time.monotonic()
                # 并发所有choose返回之后才做全计划摘要，避免父进程挡后续IPC。
                return {'label':case['label'],'decision_id':request.decision_id,'original_budget':spans is not None,
                    'relative_budget_seconds':relative,'nominal_window_seconds':None if spans else case['nominal_seconds'],
                    'rules_seconds':after_rules-now,'total_rules_and_IPC_seconds':returned-now,'error':error,
                    'before_enhancement':returned<=budget.enhancement_deadline_monotonic,
                    'before_fallback':returned<=budget.fallback_deadline_monotonic,
                    'before_latest_send':returned<=budget.latest_send_at_monotonic},plan
            burst=time.monotonic() if concurrent else None
            answers=await asyncio.gather(*(one(c,burst) for c in selected)) if concurrent else [await one(c) for c in selected]
            for row,plan in answers:
                row['full_plan_exact']=plan is not None and digest(decision_plan_to_json(plan))==refs[row['label']]['full_plan_sha256']
                row['complete']=row['error'] is None and row['full_plan_exact'] and row['before_fallback']
                value['rows'].append(row);journal.write(__import__('json').dumps(row,ensure_ascii=False)+'\n')
            journal.flush()
            for gid in gids:await service.release_game(gid)
        except Exception as error:value['failure']={'type':type(error).__name__,'message':str(error)}
        finally:
            try:await service.close()
            except Exception as error:value['close_failure']={'type':type(error).__name__,'message':str(error)}
            value['resource_terminal']=service.snapshot();value['resources_released']=resource_zero(value['resource_terminal'])
            value['remaining_child_pids']=[child.pid for child in multiprocessing.active_children()]
            if value['remaining_child_pids']:value['resources_released']=False
            value['complete']=not value.get('failure') and not value.get('close_failure') and len(value['rows'])==len(selected) and all(r['complete'] for r in value['rows']) and value['resources_released']
            save(output/(label+'-CLOSED.json'),value)
            print({'wave':label,'complete':value['complete'],'rows':len(value['rows']),'naturally_closed':value['resources_released']},flush=True)
        return value
    try:
        original=inputs['rows'][:39]
        groups=list(dict.fromkeys(c['group'] for c in original))
        for group in groups:
            selected=[c for c in original if c['group']==group]
            result=await wave('serial-'+group,selected,False);waves.append(result)
            if not result['complete']:raise ValueError('原余量波失败，停止后续:'+group)
        for group in groups:
            selected=[c for c in original if c['group']==group]
            if group.startswith('supplement-'):
                result=await wave('concurrent-ten-'+group,selected,True);waves.append(result)
                if not result['complete']:raise ValueError('十桌原余量失败:'+group)
        # 重型/合成金例只有名义窗口，按原game_id十桌分批，不伪造并发桌ID。
        nominal=inputs['rows'][39:]
        for index in range(0,len(nominal),8):
            selected=nominal[index:index+8]
            result=await wave('nominal-%03d'%index,selected,False);waves.append(result)
            if not result['complete']:raise ValueError('名义窗口波失败')
    except Exception as error:failure={'type':type(error).__name__,'message':str(error)}
    finally:
        journal.close();complete=failure is None and all(w['complete'] for w in waves)
        save(output/'CLOSED.json',{'complete':complete,'failure':failure,'waves':waves,'actual_service_choose':calls,
            'original_and_nominal_separate':True,'from_before_rules':True,'HTTP_Token_tables':0,
            'source_tool_pins':{str(p):pin(p) for p in (Path(__file__),_project_file(_PROJECT_ROOT, HERE/'performance_common.py'))},
            'root_after':root_unchanged(),
            'actual_candidate_scores_if_choose_failed':'unknown;失败不按零评分记账'})
    if failure:raise ValueError(failure)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('phase',choices=('reference','deadlines'))
    parser.add_argument('--attempt',default='002');parser.add_argument('--reference-attempt',default='002');args=parser.parse_args()
    if not args.attempt.isdigit() or not args.reference_attempt.isdigit():raise ValueError('尝试编号必须数字')
    with slots(1 if args.phase=='reference' else 4) as resource_slots:
        asyncio.run(reference(args.attempt,resource_slots) if args.phase=='reference' else deadlines(args.attempt,args.reference_attempt,resource_slots))


if __name__=='__main__':main()
