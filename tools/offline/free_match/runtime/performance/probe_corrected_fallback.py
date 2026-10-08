"""T199冻结P0公开动作循环负例；无HTTP，假会话只记录真实动作尝试。"""
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

import asyncio
import argparse
from dataclasses import asdict,replace
from pathlib import Path

from performance_common import HERE,OUT,P0,make_request,package,pin,policy,read,root_unchanged,save,slots


async def probe(attempt):
    """编译／规则增强失败仍走当前P0独立合法保底；明确拒绝不重授原截止。"""
    from hangma_bot.application.audit import AuditTrail
    from hangma_bot.application.contracts import AuditReceipt,ObservedActionWindow,SubmitAccepted,SubmitAmbiguous,SubmitRejectedRetryable
    from hangma_bot.application.deadline import BudgetPolicy,ManualClock
    from hangma_bot.application.decision_loop import RuntimeServices,run_action_window
    from hangma_bot.application.ids import PrefixedUuidIds
    from hangma_bot.hangma.engine import HangmaRules
    from hangma_bot.kernel.config import RuleConfig
    from hangma_bot.kernel.actions import action_key
    from hangma_bot import bootstrap as b

    inputs=read(OUT/'INPUTS.json');payload=package();config=RuleConfig(**payload['candidate_identity']['params']['rule_config'])
    destination=OUT/('corrected-fallback-'+attempt);destination.mkdir(exist_ok=False)
    original=next(case for case in inputs['rows'][:39] if case['observation']['phase']=='draw' and len(make_request(case)[1].legal_candidates)>1)
    cases=[('compiled_failure',original),('rules_failure',original),('both_failure',original),
        ('reject_then_compiled_failure',original),('reject_then_rules_failure',original),
        ('ambiguous_no_repeat',original),('reject_at_original_deadline',original),
        ('corrected_negative_rules_failure',next(case for case in inputs['rows'] if case['label']=='gold:SYN01-branch-global-only')),
        ('corrected_positive_rules_failure',next(case for case in inputs['rows'] if case['label']=='gold:SYN06-order-permutation'))]
    rows=[];failure=None;actual_scores=0
    try:
        for scenario,case in cases:
            request,_=make_request(case);clock=ManualClock(wait_scale=1.0);sink_records=[];budgets=[];policy_requests=[];rule_events=[];attempts=[]
            spans=case['original_remaining_seconds']
            # 原记录在分析后取得的39余量，用生产BudgetPolicy反推同一原接收时刻。
            # 不把历史增强分析已用的时间返还给此负例。
            received=clock.now() if spans is None else clock.now()+2*spans[0]-spans[2]
            expires=None if spans is None else clock.now()+spans[2]+BudgetPolicy().post_reserve_seconds
            window=ObservedActionWindow(request.observation,request.window_key,request.observation.snapshot_seq,received,case['nominal_seconds'],expires,spans is None)
            original_budget=BudgetPolicy().build(received,case['nominal_seconds'],expires)
            if spans is not None:
                actual=[getattr(original_budget,key)-clock.now() for key in ('enhancement_deadline_monotonic','fallback_deadline_monotonic','latest_send_at_monotonic')]
                if any(abs(left-right)>1e-8 for left,right in zip(actual,spans)):raise ValueError('原预算不能由生产预算策略复现')
            real_rules=HangmaRules(config)
            force_rule='rules_failure' in scenario or scenario=='both_failure'

            class Rules:
                """只注入增强分析异常；紧急和最终复核仍是冻结P0真正规则。"""
                config=real_rules.config
                def emergency_action(self,observation):
                    rule_events.append('independent_emergency')
                    return real_rules.emergency_action(observation)
                def analyze(self,observation,**kwargs):
                    rule_events.append('analyze')
                    if force_rule:raise RuntimeError('t199-injected-rule-enhancement-failure')
                    return real_rules.analyze(observation,**kwargs)
                def validate(self,observation,action):
                    rule_events.append('validate:'+action_key(action))
                    return real_rules.validate(observation,action)

            selected=policy(True)
            def fail_score(view):
                nonlocal actual_scores
                actual_scores+=1
                raise RuntimeError('t199-injected-checked-native-scoring-failure')
            selected.executor.score_vip_route=fail_score

            class Policy:
                """实际RouteVip choose；仅其checked native评分调用被故障注入。"""
                async def choose(self,request,budget):
                    budgets.append(budget);policy_requests.append(request)
                    if not rule_events or rule_events[0]!='independent_emergency':raise AssertionError('评分前没有独立保底')
                    return await selected.choose(request,budget)

            class Sink:
                def emit(self,record):
                    sink_records.append(record)
                    return AuditReceipt(True,False)

            class Session:
                """提交只写内存；明确拒绝的权威刷新保持原窗口并尝试伪延长期限。"""
                async def submit(self,attempt):
                    attempts.append(attempt)
                    if attempt.latest_send_at_monotonic!=original_budget.latest_send_at_monotonic:raise AssertionError('延长原最迟发送')
                    if clock.now()>=attempt.latest_send_at_monotonic:raise AssertionError('截止后仍提交')
                    if scenario=='ambiguous_no_repeat':return SubmitAmbiguous('fake-recovery','t199-injected-ambiguous')
                    if scenario.startswith('reject_') and len(attempts)==1:
                        if scenario=='reject_at_original_deadline':clock.advance(original_budget.latest_send_at_monotonic-clock.now()+.001)
                        else:clock.advance(.01)
                        observation=replace(window.observation,snapshot_seq=window.authoritative_seq+1,consumed_seq=window.authoritative_seq+1)
                        refreshed=replace(window,observation=observation,authoritative_seq=observation.snapshot_seq,
                            received_at_monotonic=clock.now(),expires_at_monotonic=original_budget.latest_send_at_monotonic+100)
                        return SubmitRejectedRetryable('CONFLICT',attempt.action_key,refreshed)
                    return SubmitAccepted('200',attempt.based_on_authoritative_seq+1)

            services=RuntimeServices(Rules(),Policy(),AuditTrail(Sink(),run_id='t199-p0-fallback',tournament_id='offline-only',participant_id='fake-seat',clock=clock),
                clock,PrefixedUuidIds(),BudgetPolicy(),route_limits=b.VIP_S02_ROUTE_LIMITS,requires_conditional_roots=True)
            result=await run_action_window(session=Session(),window=window,services=services,competition=request.competition,stage_attempt_id=None)
            expected='ambiguous' if scenario=='ambiguous_no_repeat' else 'deadline' if scenario=='reject_at_original_deadline' else 'exhausted' if scenario=='reject_then_rules_failure' else 'accepted'
            expected_count=2 if scenario=='reject_then_compiled_failure' else 1
            if result.outcome_kind!=expected or len(attempts)!=expected_count:raise AssertionError((scenario,result,len(attempts),expected,expected_count))
            if any(budget!=original_budget for budget in budgets):raise AssertionError('权威刷新改变原预算')
            if len({attempt.action_key for attempt in attempts})!=len(attempts):raise AssertionError('重发已明确拒绝动作')
            for attempt in attempts:
                if not real_rules.validate(window.observation,attempt.action).legal:raise AssertionError('保底不符合P0规则')
            if expected_count==2:
                if not policy_requests[1].rejected_attempts or policy_requests[1].rejected_attempts[0].action_key!=attempts[0].action_key:raise AssertionError('拒绝记录缺失')
                backups=[record.payload for record in sink_records if record.payload.get('area')=='rejected_emergency_backup']
                if not backups or backups[0]['is_rule_emergency'] is not False:raise AssertionError('备用错误冒认规则紧急候选')
            row={'scenario':scenario,'label':case['label'],'complete':True,'outcome':result.outcome_kind,
                'action_keys':[attempt.action_key for attempt in attempts],'original_remaining_seconds':spans,
                'budget_mode':'39原余量复现' if spans else '名义窗口逻辑负例，非性能证据',
                'budget_unchanged':True,'rule_events':rule_events,'policy_calls':len(policy_requests),
                'local_attempts':len(attempts),'HTTP_calls':0,'rejected_actions_excluded':True,
                'policy_exception_notes':[record.payload for record in sink_records if record.payload.get('area')=='decision_loop']}
            rows.append(row);save(destination/(scenario+'.json'),row)
            print({'fallback':scenario,'complete':True,'local_attempts':len(attempts)},flush=True)
    except Exception as error:failure={'type':type(error).__name__,'message':str(error)}
    finally:
        save(destination/'CLOSED.json',{'complete':failure is None and len(rows)==len(cases),'failure':failure,
            'cases':rows,'actual_injected_native_score_calls':actual_scores,'local_attempts':sum(row['local_attempts'] for row in rows),
            'HTTP_Token_tables':0,'candidate_identity':payload['candidate_identity'],'package_id':payload['release_package_id'],
            'rules_source_hash':inputs['rules_source_hash'],'root_after':root_unchanged(),
            'source_tool_pins':{str(path):pin(path) for path in (Path(__file__),_project_file(_PROJECT_ROOT, HERE/'performance_common.py'))}})
    if failure:raise ValueError(failure)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--attempt',default='002');args=parser.parse_args()
    if not args.attempt.isdigit():raise ValueError('尝试编号必须数字')
    with slots(1):asyncio.run(probe(args.attempt))
