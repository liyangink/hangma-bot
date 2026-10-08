"""T199 P0生产动作循环窄验收：原十桌同到达合法提交和独立名义窗口。"""
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
import gzip
import json
import multiprocessing
import os
from pathlib import Path
import time

from performance_common import HERE,OUT,P0Factory,package,pin,read,resource_zero,root_unchanged,save,slots


async def probe(attempt,resource_slots):
    """复用T191十窗同到达口径；评分可显式跳过，当前规则合法动作必须原截止前发送。"""
    from hangma_bot import bootstrap as b
    from hangma_bot.application.audit import AuditTrail
    from hangma_bot.application.contracts import AuditReceipt,ObservedActionWindow,SubmitAccepted
    from hangma_bot.application.deadline import BudgetPolicy,SystemClock
    from hangma_bot.application.decision_loop import RuntimeServices,run_action_window
    from hangma_bot.application.ids import PrefixedUuidIds
    from hangma_bot.hangma.engine import HangmaRules
    from hangma_bot.kernel.config import RuleConfig
    from hangma_bot.kernel.observation import CompetitionContext
    from hangma_bot.kernel.serialization import observation_from_json,window_key_from_json

    if os.getpriority(os.PRIO_PROCESS,0)!=0:raise ValueError('必须正常优先级')
    inputs=read(OUT/'INPUTS.json');payload=package()
    ref=read(OUT/'reference-002/CLOSED.json')
    if not ref['complete'] or ref['input_pin']!=pin(OUT/'INPUTS.json'):raise ValueError('原完整参考未闭')
    runtime=b._load_vip_s03_runtime(payload['compiled_runtime']['manifest_sha256'])
    config=RuleConfig(**payload['candidate_identity']['params']['rule_config']);clock=SystemClock();budget_policy=BudgetPolicy()
    out=OUT/('timely-legal-'+attempt);out.mkdir(exist_ok=False)
    identity={'candidate_identity':payload['candidate_identity'],'core_id':payload['candidate_identity']['candidate_id'],
        'params':payload['candidate_identity']['params'],'compiled_runtime':payload['compiled_runtime'],
        'execution_id':runtime.execution_id,'rules_source_hash':payload['rules_source_hash'],'package_id':payload['release_package_id']}
    settings=b.VIP_S02_COMPUTE_SETTINGS
    save(out/'START.json',dict(identity,input_pin=pin(OUT/'INPUTS.json'),reference_pin=pin(OUT/'reference-002/CLOSED.json'),
        cpu_nice=os.getpriority(os.PRIO_PROCESS,0),pid=os.getpid(),resource_slots=resource_slots,
        compute_settings=asdict(settings),root_before=root_unchanged(),HTTP_Token_tables=0,
        clock='真实SystemClock单调秒；十原窗共同新起点，原39余量不变',
        historical_method='T191 test_vip_tournament_wiring.test_ten_simultaneous_games_use_exclusive_preheated_workers 的合法及时口径'))
    service=b.build_isolated_decision_policy(P0Factory(runtime.execution_id),execution_id=runtime.execution_id,clock=clock,settings=settings)
    waves=[];failure=None;worker_pids=[];startup=time.monotonic();all_records=[]

    async def wave(label,selected,concurrent,fail_analysis=False):
        """输入解码先准备；动作规则分析／审计／计算往返／最终复核全部计入同原截止。"""
        decoded=[(case,observation_from_json(case['observation']),window_key_from_json(case['window_key'])) for case in selected]
        gids=list(dict.fromkeys(key.game_id for _,_,key in decoded));records=[];results=[];submissions=[]
        real_rules=HangmaRules(config)

        class FaultRules:
            """仅增强分析抛错；紧急／最终复核委托冻结P0真正规则。"""
            config=real_rules.config
            def emergency_action(self,observation):return real_rules.emergency_action(observation)
            def validate(self,observation,action):return real_rules.validate(observation,action)
            def analyze(self,observation,**kwargs):raise RuntimeError('t199-gold-independent-emergency-analysis-failure')

        class Sink:
            def emit(self,record):
                records.append(record)
                return AuditReceipt(True,False)

        audit=AuditTrail(Sink(),run_id='t199-p0-timely-legal',tournament_id='offline-only',participant_id='fake-seat',clock=clock)
        services=RuntimeServices(FaultRules() if fail_analysis else real_rules,service,audit,clock,PrefixedUuidIds(),budget_policy,
            route_limits=b.VIP_S02_ROUTE_LIMITS,requires_conditional_roots=True)
        for gid in gids:await service.acquire_game(gid)
        before=service.snapshot();start=clock.now() if concurrent else None

        async def one(decoded_case):
            case,observation,key=decoded_case;origin=start if concurrent else clock.now();spans=case['original_remaining_seconds']
            # 原已用规则时间不返还：反推接收基准，让生产BudgetPolicy再现三段原余量。
            received=origin if spans is None else origin+2*spans[0]-spans[2]
            expires=origin+case['nominal_seconds'] if spans is None else origin+spans[2]+budget_policy.post_reserve_seconds
            window=ObservedActionWindow(observation,key,observation.snapshot_seq,received,case['nominal_seconds'],expires,False)
            budget=budget_policy.build(received,case['nominal_seconds'],expires)
            actual=[getattr(budget,name)-origin for name in ('enhancement_deadline_monotonic','fallback_deadline_monotonic','latest_send_at_monotonic')]
            if spans and any(abs(x-y)>1e-8 for x,y in zip(actual,spans)):raise ValueError('原窗口三段余量未重现')
            sent=[]

            class FakeGameSession:
                """唯一内存提交口；不用官方端点，不生成非幂等网络请求。"""
                async def submit(self,attempt):
                    sent_at=clock.now()
                    validations=[record for record in records if record.kind.value=='candidate_validated' and record.context.decision_id==attempt.decision_id and record.payload['action_key']==attempt.action_key]
                    legal=bool(validations and validations[-1].payload['legal'] is True)
                    row={'label':case['label'],'decision_id':attempt.decision_id,'game_id':key.game_id,
                        'action_key':attempt.action_key,'sent_at_monotonic':sent_at,'shared_origin_monotonic':origin,
                        'relative_budget_seconds':actual,'original_remaining_seconds':spans,
                        'nominal_window_seconds':None if spans else case['nominal_seconds'],
                        'received_to_submit_seconds':sent_at-origin,'legal':legal,
                        'before_original_latest_send':sent_at<budget.latest_send_at_monotonic,
                        'latest_send_unchanged':attempt.latest_send_at_monotonic==budget.latest_send_at_monotonic}
                    sent.append(row);submissions.append(row)
                    return SubmitAccepted('200',attempt.based_on_authoritative_seq+1)

            competition=CompetitionContext('offline-only',None,None,None,None,(),0)
            result=await run_action_window(session=FakeGameSession(),window=window,services=services,competition=competition,stage_attempt_id=None)
            return {'label':case['label'],'outcome':result.outcome_kind,'local_attempts':len(sent),'complete':
                result.outcome_kind=='accepted' and len(sent)==1 and all(row['legal'] and row['before_original_latest_send'] and row['latest_send_unchanged'] for row in sent)}

        try:
            results=await asyncio.gather(*(one(case) for case in decoded)) if concurrent else [await one(case) for case in decoded]
            # 完整审计编码和磁盘封存只在所有动作循环结束后，不挡十窗热区。
            planned=[record for record in records if record.kind.value=='decision_planned']
            complete_scoring=sum(record.payload['returned_plan'] is not None for record in planned)
            value={'wave':label,'complete':len(results)==len(selected) and all(row['complete'] for row in results),
                'concurrent_shared_start':concurrent,'fail_rule_analysis':fail_analysis,'rows':results,'submissions':submissions,
                'complete_scoring':complete_scoring,'explicit_fallback_or_skip':len(planned)-complete_scoring,
                'timely_legal_submissions':sum(row['legal'] and row['before_original_latest_send'] for row in submissions),
                'resources_before':before,'resources_after_actions':service.snapshot()}
        except Exception as error:
            value={'wave':label,'complete':False,'failure':{'type':type(error).__name__,'message':str(error)},'submissions':submissions,'rows':results}
        finally:
            for gid in gids:await service.release_game(gid)
            all_records.extend(records)
        save(out/(label+'-CLOSED.json'),value);print({key:value.get(key) for key in ('wave','complete','complete_scoring','timely_legal_submissions')},flush=True)
        return value

    try:
        await service.start();worker_pids=[{'pid':child.pid,'cpu_nice':os.getpriority(os.PRIO_PROCESS,child.pid)} for child in multiprocessing.active_children()]
        if len(worker_pids)!=10 or any(row['cpu_nice']!=0 for row in worker_pids):raise ValueError('未真实预热十正常优先级worker')
        warm_seconds=clock.now()-startup
        # 未执行的31名义输入独立分账；失败原十评分波不被重跑或覆盖。
        for index in range(39,len(inputs['rows']),8):
            waves.append(await wave('nominal-%03d'%index,inputs['rows'][index:index+8],False))
        for group in dict.fromkeys(case['group'] for case in inputs['rows'][:39] if case['group'].startswith('supplement-')):
            selected=[case for case in inputs['rows'][:39] if case['group']==group]
            if len(selected)!=10 or len({case['window_key']['game_id'] for case in selected})!=10:raise ValueError('未用原十个不同桌')
            waves.append(await wave('original-ten-'+group,selected,True))
        extra=[next(case for case in inputs['rows'] if case['label']=='gold:'+tag) for tag in ('SYN03-six-natural-pairs-white','SYN11-chain-four-white-formula')]
        waves.append(await wave('gold-positive-chain-independent-fallback',extra,False,True))
    except Exception as error:failure={'type':type(error).__name__,'message':str(error)}
    finally:
        try:await service.close()
        except Exception as error:failure={'type':type(error).__name__,'message':str(error),'phase':'service.close'}
        terminal=service.snapshot();remaining=[child.pid for child in multiprocessing.active_children()]
        with gzip.open(out/'production-audit.jsonl.gz','xt') as stream:
            for record in all_records:stream.write(json.dumps(asdict(record),ensure_ascii=False,separators=(',',':'))+'\n')
        released=resource_zero(terminal) and not remaining
        complete=failure is None and len(waves)==7 and all(wave['complete'] for wave in waves) and released
        save(out/'CLOSED.json',dict(identity,complete=complete,failure=failure,waves=waves,resource_terminal=terminal,
            resources_released=released,remaining_child_pids=remaining,worker_pids=worker_pids,warm_seconds=locals().get('warm_seconds'),
            original_budget_legal_timely=sum(wave.get('timely_legal_submissions',0) for wave in waves if wave['wave'].startswith('original-ten-')),
            nominal_legal_timely=sum(wave.get('timely_legal_submissions',0) for wave in waves if wave['wave'].startswith('nominal-')),
            original_and_nominal_separate=True,original_full_scoring_deadline_failed_receipt=pin(OUT/'deadlines-002/CLOSED.json'),
            audited_full_scoring_count=sum(wave.get('complete_scoring',0) for wave in waves),
            HTTP_Token_tables=0,root_after=root_unchanged(),audit_pin=pin(out/'production-audit.jsonl.gz'),
            source_tool_pins={str(path):pin(path) for path in (Path(__file__),_project_file(_PROJECT_ROOT, HERE/'performance_common.py'))}))
    if not complete:raise ValueError('生产合法及时或资源门未全部通过；保留CLOSED原失败')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--attempt',default='001');args=parser.parse_args()
    if not args.attempt.isdigit():raise ValueError('尝试编号必须数字')
    with slots(4) as resource_slots:asyncio.run(probe(args.attempt,resource_slots))
