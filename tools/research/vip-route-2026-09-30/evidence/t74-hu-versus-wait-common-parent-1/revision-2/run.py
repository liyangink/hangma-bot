"""18个既有公开起点，首手胡／继续、之后同父续打；完整世界不进策略。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t74-hu-versus-wait-common-parent-1/revision-2'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import argparse,asyncio,gzip,json,sys,time
from collections import Counter
from pathlib import Path

from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.kernel.actions import action_key
from hangma_bot.kernel.serialization import observation_to_json,window_key_from_json,window_key_to_json
from hangma_bot.offline.evaluate import MatchDriverConfig,frame_observation_summary,resume_match
from hangma_bot.offline.forced_action import ForceFirstActionPolicy
from hangma_bot.offline.qualifier_opponents import build_qualifier_runtime
from hangma_bot.offline.scoring_input_capture import ScoringInputCapture,ScoringInputCaptureLimits
from hangma_bot.offline.vip_eoh_generate import VipEohBatch,load_vip_parents
from hangma_bot.offline.vip_route_development import VipDevelopmentAuditPolicy
from hangma_bot.simulation import MatchSpec,SimulationChoice
from hangma_bot.simulation.artifacts import hand_math_runtime_metadata
from prepare import HERE,canonical,pin,save

def need(ok,message):
    """错误显式终止并保留费用，不能用R18回退制造候选成绩。"""
    if not ok:raise ValueError(message)

async def main():
    plan=json.loads((_project_file(_PROJECT_ROOT, HERE/'PREPARED.json')).read_text())
    need(plan['status']=='prepared_no_START' and plan['python_version']==sys.version,'准备身份或Python不同')
    need(not (_project_file(_PROJECT_ROOT, HERE/'START.json')).exists(),'已经START；不可重试覆盖')
    for name,digest in plan['files'].items():need(pin(name)==digest,'冻结来源漂移: '+name)
    batch=VipEohBatch.read(Path(plan['batch_file']))
    parent=load_vip_parents([Path(plan['parent_package'])],batch)[0]
    need(parent['identity']==plan['parent_identity'],'父代实际执行身份不同')
    backend=hand_math_runtime_metadata();expected=parent['identity']['math_backend']
    need(all(backend.get(k)==expected.get(k) for k in ('implementation','semantics_version','fallback_reason')) and
         backend['native_sha256']==expected['native_binary']['sha256'],'实际数学后端不同')
    with gzip.open(_project_file(_PROJECT_ROOT, HERE/'SOURCE-MATERIALS.json.gz'),'rt') as stream:roots=json.load(stream)['roots']
    need(len(roots)==18,'窗口分母不同')
    save(_project_file(_PROJECT_ROOT, HERE/'START.json'),{'schema':'t74-common-parent-start/2','status':'START','prepared_sha256':pin(_project_file(_PROJECT_ROOT, HERE/'PREPARED.json'))['sha256'],
        'runner_sha256':pin(__file__)['sha256'],'math_backend':backend,'windows':18,'actual_arm_budget':36,
        'new_models_natural_tables':0,'scope':'complete current-hand causal endpoints, not stage or table confirmation'})
    start_pin=pin(_project_file(_PROJECT_ROOT, HERE/'START.json'));prepare_pin=pin(_project_file(_PROJECT_ROOT, HERE/'PREPARED.json'))
    counts=Counter();begun=time.monotonic();done=[];primary=None
    view_stream=(_project_file(_PROJECT_ROOT, HERE/'views.jsonl.gz')).open('x+b')
    capture=ScoringInputCapture(view_stream,limits=ScoringInputCaptureLimits.from_json(plan['budgets']['capture']))
    records=[];decisions=gzip.open(_project_file(_PROJECT_ROOT, HERE/'decisions.jsonl.gz'),'xt');events=gzip.open(_project_file(_PROJECT_ROOT, HERE/'events.jsonl.gz'),'xt')
    def check_time():need(time.monotonic()-begun<plan['budgets']['wall_clock_seconds'],'本批单调墙钟预算耗尽')
    def call(label,fn,*args,**kwargs):
        check_time();counts[label]+=1
        return fn(*args,**kwargs)
    def event(row):events.write(canonical(row).decode()+'\n');events.flush()
    def record(row):
        decisions.write(canonical(row).decode()+'\n');decisions.flush();records.append(row)
        counts['actual_policy_decisions']+=1
        need(row['status']=='chosen' and not any('action_value_failed' in x for x in row['degraded_reasons']),'失败决策或内部回退')
        if row.get('focal_vip'):
            need(row['c_self_scored'] and len(row['scoring_calls'])==1,'没有完整自评分')
            value=row['scoring_calls'][0];counts['actual_vip_score_calls']+=value['actual_score_calls']
            need(value['status']=='SCORED' and value['full_legal_keys'] and value['input_capture']['saved_before_score'],'实际评分或输入缺失')
    def check_frame(frame,old,rules):
        need(frame.blocked_reason is None and frame.final_scores is None,'恢复提前终局／阻塞')
        need([window_key_to_json(d.window_key) for d in frame.decisions]==[d['window_key'] for d in old],'同期完整窗口错位')
        analyses=[]
        for decision,row in zip(frame.decisions,old):
            need(observation_to_json(decision.observation)==row['observation'],'恢复公开观察不同')
            analysis=call('recovery_rules_analyze',rules.analyze,decision.observation,route_limits=batch.route_limits)
            need(analysis.completeness.value=='complete' and sorted(c.action_key for c in analysis.legal_candidates)==sorted(row['legal_action_keys']),'合法动作不同或规则不完整')
            analyses.append(analysis)
        return analyses
    def replay(world,frames,engine,rules,root_id,label):
        need(len(frames)<=plan['budgets']['max_recovery_frames_per_root'],'恢复帧预算耗尽')
        for i,old in enumerate(frames):
            frame=call('recovery_frame',engine.frame,world);analyses=check_frame(frame,old,rules)
            choices=[]
            for decision,row,analysis in zip(frame.decisions,old,analyses):
                options=[c for c in analysis.legal_candidates if c.action_key==row['selected_action_key']]
                need(len(options)==1,'旧动作不唯一合法');choices.append(SimulationChoice(decision.window_key,options[0].action))
            event({'event':'recovery_advance','root_id':root_id,'phase':label,'ordinal':i,'revision':frame.revision,'status':'pending'})
            world=call('recovery_advance',engine.advance,world,frame.revision,tuple(choices))
            event({'event':'recovery_advance','root_id':root_id,'phase':label,'ordinal':i,'status':'advanced'})
        return world
    class TraceEngine:
        """只持有完整世界的不透明句柄，经唯一模拟引擎推进和导出。"""
        def __init__(self,engine,root_id,arm):self.engine=engine;self.root_id=root_id;self.arm=arm;self.last=None;self.advances=0
        def frame(self,world):self.last=world;return call('continuation_frame',self.engine.frame,world)
        def advance(self,world,revision,choices):
            event({'event':'continuation_advance','root_id':self.root_id,'arm':self.arm,'revision':revision,
                'choices':[{'window_key':window_key_to_json(c.window_key),'action_key':action_key(c.action)} for c in choices],'status':'pending'})
            self.last=call('continuation_advance',self.engine.advance,world,revision,choices);self.advances+=1
            event({'event':'continuation_advance','root_id':self.root_id,'arm':self.arm,'revision':revision,'status':'advanced'})
            return self.last
    try:
        for root in roots:
            runtime=call('runtime_constructor',build_qualifier_runtime,batch,parent['source'],root['composition']['opponent_types_logical_1_2_3'])
            engine,rules=runtime.engine,runtime.rules
            spec=MatchSpec(root['match_id'],root['mother_root'],runtime.config,root['composition']['seed'],root['initial_dealer'],(0,0,0,0))
            world=call('recovery_world_start',engine.start,spec)
            world=replay(world,root['whole_prefix'],engine,rules,root['root_id'],'whole_table')
            target_frame=call('recovery_frame',engine.frame,world);check_frame(target_frame,root['target_frame'],rules)
            directory=_project_file(_PROJECT_ROOT, HERE/root['root_id'].replace(':','-'));directory.mkdir(exist_ok=False)
            round_no=root['source_window']['round_no'];teacher=call('recovery_export_hand',engine.export_hand,world,round_no)
            save(directory/'TEACHER-ORIGIN.json',{'scope':'offline teacher only; no hidden fields to policy or author','hand':teacher})
            common=call('recovery_import_hand',engine.from_replay,teacher)
            common=replay(common,root['current_hand_prefix'],engine,rules,root['root_id'],'single_hand')
            frame=call('recovery_frame',engine.frame,common);check_frame(frame,root['target_frame'],rules)
            need([observation_to_json(d.observation) for d in frame.decisions]==[observation_to_json(d.observation) for d in target_frame.decisions],'单局导入改变目标完整观察')
            snapshot={'observation_summary':frame_observation_summary(frame),'match_spec':{'match_id':root['match_id']}}
            save(directory/'RECOVERY.json',{'status':'recovered','source_window':root['source_window'],'full_target_observations_equal':True,
                'snapshot':snapshot,'whole_prefix_frames':len(root['whole_prefix']),'current_hand_prefix_frames':len(root['current_hand_prefix'])})
            target=window_key_from_json(root['source_window']);results={}
            for arm in plan['arm_order']:
                check_time();need(counts['continuations_dispatched']<plan['budgets']['max_continuations'],'续打预算耗尽')
                fresh=call('runtime_constructor',build_qualifier_runtime,batch,parent['source'],root['composition']['opponent_types_logical_1_2_3'])
                base_id=fresh.challenger_policy_id;base=fresh.policies_by_id[base_id]
                context={'root_id':root['root_id'],'arm':arm,'focal_seat':root['focal_seat'],'focal_vip':True}
                before=len(records)
                audited=VipDevelopmentAuditPolicy(base,base_id,lambda context=context:dict(context),record,challenger=True,capture=capture)
                forced=None
                if arm=='F':forced=ForceFirstActionPolicy(audited,target_window=target,forced_action_key=root['forced_first'],policy_id=base_id+':T74:F')
                logical=[forced if forced is not None else audited]
                for i in range(1,4):
                    declaration=fresh.declarations['Q'+str(i)];opponent=fresh.policies_by_id[declaration.policy_id]
                    other=dict(context,focal_vip=False,opponent_logical=i)
                    logical.append(VipDevelopmentAuditPolicy(opponent,declaration.policy_id,lambda context=other:dict(context),record))
                permutation=root['permutation'];policies=tuple(logical[permutation.index(seat)] for seat in range(4))
                traced=TraceEngine(engine,root['root_id'],arm)
                need(frame_observation_summary(traced.frame(common))==snapshot['observation_summary'],'两臂起点不同')
                counts['continuations_dispatched']+=1
                event({'event':'continuation_start','root_id':root['root_id'],'arm':arm,'ordinal':counts['continuations_dispatched']})
                outcome=await resume_match(engine=traced,world=common,policies_by_seat=policies,rules=rules,choice_factory=SimulationChoice,
                    config=MatchDriverConfig('logical',plan['budgets']['steps_per_continuation'],BudgetPolicy(),'T74-common-parent',True,batch.route_limits),
                    now_monotonic=lambda:800.0,wall_clock=None,value_limits=batch.route_limits,
                    stage_snapshot=snapshot,remaining_schedule={'declared_endpoint':'current_single_hand_end'})
                save(directory/(arm+'-outcome.json'),outcome.to_json())
                need(outcome.status=='complete' and outcome.completed_hands==1,'没有完成当前单局终点')
                need(all(getattr(outcome.runtime_counts,n)==0 for n in ('timeouts','illegal_choices','fallbacks','auto_actions','audit_missing')),'运行错误或回退非零')
                executed=[d for d in outcome.decisions if dict(d.window_key)==root['source_window']]
                expected=root['parent_first'] if arm=='P' else root['forced_first']
                need(len(executed)==1 and executed[0].action_key==expected,'首动作没有唯一实际执行')
                need(forced is None or forced.force_count==1,'不是恰好一次首手干预')
                actual=records[before:];focal=[d for d in actual if d['window_key']==root['source_window']]
                need(len(focal)==1 and focal[0]['observation']==root['focal_observation'],'实际目标观察缺失／不一致')
                need(focal[0]['scoring_execution']['input_capture']['view_sha256']==root['expected_input_sha256'],'实际完整评分输入不同')
                actual_scores={d['action_key']:{'score':d['score'],'trace':d['trace']['detail']} for d in focal[0]['candidates']}
                need(canonical(actual_scores)==canonical(root['expected_parent_scores']),'父代目标完整分数或解释不同')
                if arm=='P':need([(d['window_key'],d['selected_action_key'],d['observation']) for d in actual]==[(d['window_key'],d['selected_action_key'],d['observation']) for d in root['original_hand_suffix']],'P未精确复现原全座位尾段')
                settlement=call('continuation_export_settlement',engine.export_hand_settlement,traced.last,round_no)
                result={'root_id':root['root_id'],'arm':arm,'status':'complete','settlement':settlement,
                    'focal_net_score':settlement['score_delta'][root['focal_seat']],'executed_first':executed[0].action_key,
                    'force_count':0 if forced is None else forced.force_count,'successful_advances':traced.advances,
                    'actual_policy_decisions':len(actual),'candidate_self_scores':sum(d['c_self_scored'] for d in actual)}
                save(directory/(arm+'-RESULT.json'),result);results[arm]=result;counts['continuations_completed']+=1
                print({'root':root['root_id'],'arm':arm,'current_hand_complete':True},flush=True)
            hu_arm='P' if root['parent_first']=='hu' else 'F';wait_arm='F' if hu_arm=='P' else 'P'
            combined={'root_id':root['root_id'],'mother_root':root['mother_root'],'category':root['category'],
                'results':results,'H_alias_actual_arm':hu_arm,'W_alias_actual_arm':wait_arm,
                'wait_minus_hu':results[wait_arm]['focal_net_score']-results[hu_arm]['focal_net_score'],
                'P_original_full_tail_exact':True,'same_parent_after_first':True}
            save(directory/'ROOT-RESULT.json',combined);done.append(combined)
    except BaseException as exc:
        primary=exc;event({'event':'batch_failed','error':type(exc).__name__+': '+str(exc),'actual_counts':dict(counts)});raise
    finally:
        # 独立清理：一项失败不阻断其余费用落盘，也不覆盖原业务异常。
        cleanup_errors=[];capture_costs=None
        for label,stream in [('decisions',decisions),('events',events)]:
            try:stream.close()
            except BaseException as exc:cleanup_errors.append(label+': '+type(exc).__name__+': '+str(exc))
        try:capture_costs=capture.finish()
        except BaseException as exc:cleanup_errors.append('capture.finish: '+type(exc).__name__+': '+str(exc))
        try:view_stream.close()
        except BaseException as exc:cleanup_errors.append('views.close: '+type(exc).__name__+': '+str(exc))
        try:
            stable=all(pin(name)==digest for name,digest in plan['files'].items()) and pin(_project_file(_PROJECT_ROOT, HERE/'START.json'))==start_pin and pin(_project_file(_PROJECT_ROOT, HERE/'PREPARED.json'))==prepare_pin
        except BaseException as exc:
            stable=False;cleanup_errors.append('end source check: '+type(exc).__name__+': '+str(exc))
        file_pins={}
        for name in ['decisions.jsonl.gz','events.jsonl.gz','views.jsonl.gz']:
            try:file_pins[name]=pin(_project_file(_PROJECT_ROOT, HERE/name))
            except BaseException as exc:cleanup_errors.append('file seal '+name+': '+type(exc).__name__+': '+str(exc))
        capture_valid=capture_costs is not None and capture_costs['terminal']['terminal_valid']
        valid=primary is None and not cleanup_errors and stable and capture_valid and len(done)==18
        valid=valid and counts['continuations_dispatched']==counts['continuations_completed']==36
        save(_project_file(_PROJECT_ROOT, HERE/'CLOSURE.json'),{'schema':'t74-hu-wait-common-parent-closure/2','complete':valid,'source_stable':stable,
            'actual_explicit_api_counts':dict(counts),'roots':done,'scoring_input_capture':capture_costs,'files':file_pins,
            'elapsed_monotonic_seconds':time.monotonic()-begun,'error':None if primary is None else type(primary).__name__+': '+str(primary),
            'cleanup_errors':cleanup_errors,'normal_r18_fallbacks':0 if valid else None,'new_model_calls':0,'new_natural_complete_tables':0,
            'scope':'18 selected known public sources one-first-action causal endpoints; no hidden-world frequency, deadline or strength admission'})
        print({'complete':valid,'completed_continuations':counts['continuations_completed'],'actual_vip_scores':counts['actual_vip_score_calls']},flush=True)
        if primary is None and not valid:raise SystemExit(1)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true',required=True);parser.parse_args()
    asyncio.run(main())
