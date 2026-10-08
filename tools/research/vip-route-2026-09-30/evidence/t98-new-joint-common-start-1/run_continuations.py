"""T97五个既有公开焦点的自身续打；原P/A终态只读复用。

离线教师用旧整局初态和实际前缀恢复共同世界，策略仅看本座合法观察。
不强制首动作、不调用R18接管；已曝光同源结果只授开发反馈。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t98-new-joint-common-start-1'

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
import hashlib
import json
from pathlib import Path
import time

from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.kernel.actions import action_key
from hangma_bot.kernel.serialization import observation_to_json, window_key_to_json
from hangma_bot.offline.evaluate import MatchDriverConfig, frame_observation_summary, resume_match
from hangma_bot.offline.qualifier_opponents import build_qualifier_runtime
from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
from hangma_bot.offline.scoring_sources import REPO_ROOT
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents
from hangma_bot.offline.vip_route_development import VipDevelopmentAuditPolicy
from hangma_bot.simulation import SimulationChoice

HERE = Path(__file__).resolve().parent


def canonical(value):
    """有限规范JSON，时间费用另记，不把排名点写成积分。"""
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def pin(path):
    """流式首尾封条，冻结字节和长度。"""
    h, size = hashlib.sha256(), 0
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1<<20),b''):
            h.update(block); size += len(block)
    return {'bytes':size,'sha256':h.hexdigest()}


def save(path, value):
    """结果只创建，不覆盖第一次失败或旧运行。"""
    with Path(path).open('xb') as stream:
        stream.write(canonical(value)+b'\n')


async def main():
    """五条预定路径至当前单局结束；合法性与完整评分失败即保留失败。"""
    plan = json.loads((_project_file(_PROJECT_ROOT, HERE/'PLAN.json')).read_text())
    assert all(pin(n)==h for n,h in plan['frozen_files'].items())
    assert all(pin(_project_file(_PROJECT_ROOT, REPO_ROOT/n))==h for n,h in plan['source_manifest'].items())
    batch = VipEohBatch.read(Path(plan['generation_file']))
    candidate = load_vip_parents([Path(plan['candidate_package'])],batch)[0]
    assert candidate['identity'] == plan['candidate_identity']
    targets_by_label = {r['label']:r for r in json.loads(Path(plan['public_feedback_file']).read_text())['targets']}
    probe_by_label = {r['label']:r for r in json.loads(Path(plan['probe_closure_file']).read_text())['rows']}
    save(_project_file(_PROJECT_ROOT, HERE/'START.json'),{'plan':plan,'endpoint':'current_single_hand_end','force_first_action':False,
        'models_new_independent_sources_natural_tables':0,'cached_reference_arms':'existing actual P/A, not new runs'})
    start_pin, plan_pin = pin(_project_file(_PROJECT_ROOT, HERE/'START.json')),pin(_project_file(_PROJECT_ROOT, HERE/'PLAN.json'))
    counts, results = Counter(), []
    records = []
    begun, primary, errors = time.monotonic(),None,[]
    raw = (_project_file(_PROJECT_ROOT, HERE/'VIEWS.jsonl.gz')).open('x+b')
    capture = ScoringInputCapture(raw,limits=ScoringInputCaptureLimits.from_json(plan['capture']))
    decisions = gzip.open(_project_file(_PROJECT_ROOT, HERE/'DECISIONS.jsonl.gz'),'xt')
    events = gzip.open(_project_file(_PROJECT_ROOT, HERE/'EVENTS.jsonl.gz'),'xt')

    def call(kind, fn, *args, **kwargs):
        assert time.monotonic()-begun <= plan['wall_seconds'], '单调墙钟预算耗尽'
        counts[kind] += 1
        return fn(*args,**kwargs)

    def sink(row):
        decisions.write(canonical(row).decode()+'\n'); decisions.flush()
        records.append(row); counts['actual_policy_decisions'] += 1
        assert counts['actual_policy_decisions'] <= plan['max_policy_decisions']
        assert row['status']=='chosen' and row['selected_action_key'] in row['legal_action_keys']
        assert not any('action_value_failed' in x for x in row['degraded_reasons'])
        if row['focal_vip']:
            assert row['c_self_scored'] and len(row['scoring_calls'])==1
            receipt = row['scoring_calls'][0]
            counts['actual_vip_score_calls'] += receipt['actual_score_calls']
            assert counts['actual_vip_score_calls'] <= plan['max_score_calls']
            assert receipt['status']=='SCORED' and receipt['full_legal_keys'] and receipt['input_capture']['saved_before_score']

    def check(frame, old, rules):
        assert frame.blocked_reason is None and frame.final_scores is None
        assert [window_key_to_json(d.window_key) for d in frame.decisions]==[r['window_key'] for r in old]
        analyses=[]
        for d,r in zip(frame.decisions,old):
            assert observation_to_json(d.observation)==r['observation']
            a=call('recovery_rule_analysis',rules.analyze,d.observation,route_limits=batch.route_limits)
            assert a.completeness.value=='complete'
            assert sorted(c.action_key for c in a.legal_candidates)==sorted(r['legal_action_keys'])
            analyses.append(a)
        return analyses

    class TraceEngine:
        """只持不透明世界句柄；公开引擎负责全部规则推进。"""
        def __init__(self,engine,label):
            self.engine,self.label,self.last=engine,label,None
        def frame(self,world):
            self.last=world
            return call('continuation_frame',self.engine.frame,world)
        def advance(self,world,revision,choices):
            events.write(canonical({'label':self.label,'revision':revision,
                'choices':[{'window_key':window_key_to_json(c.window_key),'action_key':action_key(c.action)} for c in choices]}).decode()+'\n')
            events.flush()
            self.last=call('continuation_advance',self.engine.advance,world,revision,choices)
            return self.last

    try:
        for target in plan['targets']:
            label, seq = target['label'],target['trigger_seq']
            with gzip.open(target['trace_file'],'rt') as stream:
                trace=next(r for r in json.load(stream)['traces'] if r['arm']=='C')
            cuts=[i for i,f in enumerate(trace['frames']) if any(
                d['seat']==0 and d['window_key']['round_no']==8 and d['window_key']['phase']=='draw' and d['window_key']['trigger_seq']==seq for d in f)]
            assert len(cuts)==1
            cut=cuts[0]; old=trace['frames'][cut]
            focal=next(d for d in old if d['seat']==0)
            feedback=targets_by_label[label]
            assert focal['window_key']==feedback['window_key'] and focal['observation']==feedback['observation']
            runtime=call('runtime_constructor',build_qualifier_runtime,batch,candidate['source'],trace['composition']['opponent_types_logical_1_2_3'])
            engine,rules=runtime.engine,runtime.rules
            teacher=json.loads(Path(target['teacher_origin_file']).read_text())
            common=call('teacher_import_current_hand',engine.from_replay,teacher['hand'])
            prefix=[f for f in trace['frames'][:cut] if f[0]['window_key']['round_no']==8]
            assert len(prefix)<=plan['max_recovery_frames']
            for frame_rows in prefix:
                frame=call('recovery_frame',engine.frame,common)
                analyses=check(frame,frame_rows,rules)
                choices=[]
                for d,r,a in zip(frame.decisions,frame_rows,analyses):
                    selected=[c for c in a.legal_candidates if c.action_key==r['selected_action_key']]
                    assert len(selected)==1
                    choices.append(SimulationChoice(d.window_key,selected[0].action))
                common=call('recovery_advance',engine.advance,common,frame.revision,tuple(choices))
            frame=call('recovery_frame',engine.frame,common);check(frame,old,rules)
            snapshot={'observation_summary':frame_observation_summary(frame),'match_spec':{'match_id':trace['match_id']}}
            traced=TraceEngine(engine,label)
            context={'root_id':label,'arm':'T97','focal_seat':0,'focal_vip':True}
            policies=[VipDevelopmentAuditPolicy(runtime.policies_by_id[runtime.challenger_policy_id],runtime.challenger_policy_id,
                lambda c=context:dict(c),sink,challenger=True,capture=capture)]
            for i in range(1,4):
                d=runtime.declarations['Q'+str(i)];ctx=dict(context,focal_vip=False,opponent_logical=i)
                policies.append(VipDevelopmentAuditPolicy(runtime.policies_by_id[d.policy_id],d.policy_id,lambda c=ctx:dict(c),sink))
            before=len(records)
            assert counts['continuations_dispatched']<plan['max_continuations']
            counts['continuations_dispatched']+=1
            outcome=await resume_match(engine=traced,world=common,policies_by_seat=tuple(policies),rules=rules,
                choice_factory=SimulationChoice,config=MatchDriverConfig('logical',plan['steps_per_continuation'],BudgetPolicy(),
                    'T98-known-common-start',True,batch.route_limits),now_monotonic=lambda:800.,wall_clock=None,
                value_limits=batch.route_limits,stage_snapshot=snapshot,remaining_schedule={'declared_endpoint':'current_single_hand_end'})
            directory=_project_file(_PROJECT_ROOT, HERE/label.replace(':','-'));directory.mkdir(exist_ok=False)
            save(directory/'OUTCOME.json',outcome.to_json())
            assert outcome.status=='complete' and outcome.completed_hands==1
            assert all(getattr(outcome.runtime_counts,k)==0 for k in ('timeouts','illegal_choices','fallbacks','auto_actions','audit_missing'))
            own=[d for d in outcome.decisions if dict(d.window_key)==focal['window_key']]
            assert len(own)==1
            selected_records=records[before:]
            first=next(r for r in selected_records if r['window_key']==focal['window_key'])
            assert first['observation']==feedback['observation']
            assert first['scoring_execution']['input_capture']['view_sha256']==feedback['view_sha256']
            actual={c['action_key']:(c['score'],c['trace']['detail']) for c in first['candidates']}
            expected={e['action_key']:(e['score'],e['trace']) for e in probe_by_label[label]['scores']['candidate']['entries']}
            assert canonical(actual)==canonical(expected)
            assert own[0].action_key==probe_by_label[label]['scores']['candidate']['first']
            settlement=call('continuation_export_settlement',engine.export_hand_settlement,traced.last,8)
            assert sum(settlement['score_delta'])==0
            references={arm:json.loads(Path(target['reference_result_files'][arm]).read_text()) for arm in ['P','A']}
            result={'label':label,'complete':True,'focal_net_score':settlement['score_delta'][0],
                'settlement':settlement,'executed_first':own[0].action_key,'actual_decisions':len(selected_records),
                'actual_vip_scores':sum(r['c_self_scored'] for r in selected_records),'first_full_score_matches_probe':True,
                'cached_reference_results':references,'T97_minus_cached_P':settlement['score_delta'][0]-references['P']['focal_net_score'],
                'T97_minus_cached_A':settlement['score_delta'][0]-references['A']['focal_net_score'],
                'reference_scores_or_paths_repeated':0,'forced_first_count':0}
            save(directory/'RESULT.json',result);results.append(result)
            counts['continuations_completed']+=1
            print({'label':label,'current_hand_complete':True},flush=True)
    except BaseException as exc:
        primary=exc
        raise
    finally:
        capture_costs=None
        for name,stream in [('decisions',decisions),('events',events)]:
            try:stream.close()
            except BaseException as exc:errors.append(name+':'+type(exc).__name__+':'+str(exc))
        try:capture_costs=capture.finish()
        except BaseException as exc:errors.append('capture:'+type(exc).__name__+':'+str(exc))
        finally:raw.close()
        stable=all(pin(n)==h for n,h in plan['frozen_files'].items()) and all(pin(_project_file(_PROJECT_ROOT, REPO_ROOT/n))==h for n,h in plan['source_manifest'].items())
        stable=stable and pin(_project_file(_PROJECT_ROOT, HERE/'START.json'))==start_pin and pin(_project_file(_PROJECT_ROOT, HERE/'PLAN.json'))==plan_pin
        complete=primary is None and not errors and stable and len(results)==5 and counts['continuations_completed']==counts['continuations_dispatched']==5 and capture_costs is not None and capture_costs['terminal']['terminal_valid']
        save(_project_file(_PROJECT_ROOT, HERE/'CLOSURE.json'),{'complete':complete,'source_stable':stable,'actual_explicit_api_counts':dict(counts),
            'results':results,'scoring_input_capture':capture_costs,'cleanup_errors':errors,
            'error':None if primary is None else type(primary).__name__+': '+str(primary),
            'new_models_natural_tables_independent_sources':0,'independent_development_sources':1,
            'normal_R18_fallbacks':0 if complete else None,'force_first_count':0,
            'scope':'five known public focal windows from one exposed source; candidate own continuation, not natural confirmation',
            'elapsed_monotonic_seconds':time.monotonic()-begun})
        if primary is None and not complete:raise SystemExit(1)


if __name__=='__main__':
    asyncio.run(main())
