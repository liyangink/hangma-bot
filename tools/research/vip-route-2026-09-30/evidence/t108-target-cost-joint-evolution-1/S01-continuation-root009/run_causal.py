"""第9来源四白当前胡及等待代价：原C、首手干预后C、注册R18。

复用T74/T76的公开恢复、首手干预和单局续打接口。C正常路径自己完整
评分，不回退R18。已知结局来源只作开发反例，不估自然频率或晋级概率。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t108-target-cost-joint-evolution-1/S01-continuation-root009'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import asyncio
import gzip
import json
import time
from collections import Counter
from pathlib import Path

from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.kernel.actions import action_key
from hangma_bot.kernel.serialization import observation_to_json, window_key_from_json, window_key_to_json
from hangma_bot.offline.evaluate import MatchDriverConfig, frame_observation_summary, resume_match
from hangma_bot.offline.qualifier_opponents import build_qualifier_runtime
from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
from hangma_bot.offline.scoring_sources import REPO_ROOT
from hangma_bot.offline.vip_eoh_generate import VipEohBatch
from hangma_bot.offline.vip_route_development import VipDevelopmentAuditPolicy
from hangma_bot.simulation import MatchSpec, SimulationChoice
from io_helpers import HERE, canonical, pin, save


def need(condition, message):
    """失败原样终止，不以保底、重启或跳过来源掩盖不一致。"""
    if not condition:
        raise ValueError(message)


async def main():
    plan = json.loads((_project_file(_PROJECT_ROOT, HERE/'RUN-PREPARED.json')).read_text())
    for name, digest in plan['files'].items():
        need(pin(name) == digest, '冻结证据漂移:'+name)
    for relative, digest in plan['source_manifest'].items():
        need(pin(_project_file(_PROJECT_ROOT, REPO_ROOT/relative)) == digest, '执行源码漂移:'+relative)
    batch = VipEohBatch.read(Path(plan['generation_file']))
    source = Path(plan['raw_source_file']).read_text()
    need(batch.identity(source) == plan['candidate_identity'], '父执行身份不同')
    child_source = Path(plan['child_source_file']).read_text()
    need(batch.identity(child_source) == plan['child_identity'], '子执行身份不同')
    with gzip.open(_project_file(_PROJECT_ROOT, HERE/'TEACHER-SOURCE-TRACES.json.gz'), 'rt') as stream:
        trace = next(t for t in json.load(stream)['traces'] if t['arm'] == 'C')
    public = json.loads((_project_file(_PROJECT_ROOT, HERE/'PUBLIC-TARGETS.json')).read_text())
    counts = Counter()
    begun = time.monotonic()
    results = []
    primary = None
    records = []
    save(_project_file(_PROJECT_ROOT, HERE/'CAUSAL-START.json'), {'schema':'t108-known-case-causal-start/1',
        'plan':plan, 'declared_endpoint':'current_single_hand_end',
        'new_model_calls':0, 'new_independent_sources_or_natural_tables':0})
    start_pin, prepared_pin = pin(_project_file(_PROJECT_ROOT, HERE/'CAUSAL-START.json')), pin(_project_file(_PROJECT_ROOT, HERE/'RUN-PREPARED.json'))
    raw = (_project_file(_PROJECT_ROOT, HERE/'CAUSAL-VIEWS.jsonl.gz')).open('x+b')
    capture = ScoringInputCapture(raw, limits=ScoringInputCaptureLimits.from_json(plan['capture']))
    decisions = gzip.open(_project_file(_PROJECT_ROOT, HERE/'CAUSAL-DECISIONS.jsonl.gz'), 'xt')
    events = gzip.open(_project_file(_PROJECT_ROOT, HERE/'CAUSAL-EVENTS.jsonl.gz'), 'xt')

    def call(label, fn, *args, **kwargs):
        need(time.monotonic()-begun <= plan['wall_seconds'], '单调墙钟预算耗尽')
        counts[label] += 1
        return fn(*args, **kwargs)

    def event(value):
        events.write(canonical(value).decode()+'\n')
        events.flush()

    def record(value):
        decisions.write(canonical(value).decode()+'\n')
        decisions.flush()
        records.append(value)
        counts['actual_policy_decisions'] += 1
        need(value['status'] == 'chosen' and value['selected_action_key'] in value['legal_action_keys'],
             '失败或非法决策')
        need(not any('action_value_failed' in x for x in value['degraded_reasons']), '内部评分回退')
        if value.get('focal_vip'):
            need(value['c_self_scored'] and len(value['scoring_calls']) == 1, 'C没有完整独立评分')
            receipt = value['scoring_calls'][0]
            counts['actual_vip_score_calls'] += receipt['actual_score_calls']
            need(receipt['status'] == 'SCORED' and receipt['full_legal_keys'] and
                 receipt['input_capture']['saved_before_score'], '评分或实际输入缺失')

    def check_frame(frame, old, rules):
        need(frame.blocked_reason is None and frame.final_scores is None, '恢复提前终局或阻塞')
        need([window_key_to_json(d.window_key) for d in frame.decisions] ==
             [d['window_key'] for d in old], '恢复窗口不同')
        analyses = []
        for d, row in zip(frame.decisions, old):
            need(observation_to_json(d.observation) == row['observation'], '恢复完整观察不同')
            analysis = call('recovery_rules_analyze', rules.analyze, d.observation,
                            route_limits=batch.route_limits)
            need(analysis.completeness.value == 'complete' and
                 sorted(c.action_key for c in analysis.legal_candidates) == sorted(row['legal_action_keys']),
                 '恢复合法动作集合不同')
            analyses.append(analysis)
        return analyses

    def replay(world, frames, engine, rules):
        need(len(frames) <= plan['max_recovery_frames'], '恢复帧数超额')
        for old in frames:
            frame = call('recovery_frame', engine.frame, world)
            analyses = check_frame(frame, old, rules)
            choices = []
            for d, row, analysis in zip(frame.decisions, old, analyses):
                selected = [c for c in analysis.legal_candidates if c.action_key == row['selected_action_key']]
                need(len(selected) == 1, '原动作不是唯一合法选择')
                choices.append(SimulationChoice(d.window_key, selected[0].action))
            world = call('recovery_advance', engine.advance, world, frame.revision, tuple(choices))
        return world

    class TraceEngine:
        """只保存不透明世界句柄，所有推进和导出经唯一模拟引擎公开接口。"""
        def __init__(self, engine, target_name, arm):
            self.engine, self.target_name, self.arm = engine, target_name, arm
            self.last = None
            self.advances = 0

        def frame(self, world):
            self.last = world
            return call('continuation_frame', self.engine.frame, world)

        def advance(self, world, revision, choices):
            event({'event':'continuation_advance', 'target':self.target_name, 'arm':self.arm,
                'revision':revision, 'choices':[{'window_key':window_key_to_json(c.window_key),
                    'action_key':action_key(c.action)} for c in choices], 'status':'pending'})
            self.last = call('continuation_advance', self.engine.advance, world, revision, choices)
            self.advances += 1
            return self.last

    try:
        for target in plan['targets']:
            seq = target['trigger_seq']
            cuts = [i for i, frame in enumerate(trace['frames']) if any(
                d['seat'] == 0 and d['window_key']['round_no'] == plan['hand_no'] and
                d['window_key']['trigger_seq'] == seq and d['window_key']['phase'] == 'draw' for d in frame)]
            need(len(cuts) == 1, '目标帧不是唯一')
            cut = cuts[0]
            old = trace['frames'][cut]
            focal = next(d for d in old if d['seat'] == 0)
            need(focal['selected_action_key'] == target['original_first'] and
                 target['forced_first'] in focal['legal_action_keys'], '冻结的首手动作不合法或不一致')
            runtime = call('runtime_constructor', build_qualifier_runtime, batch, source,
                           trace['composition']['opponent_types_logical_1_2_3'])
            engine, rules = runtime.engine, runtime.rules
            spec = MatchSpec(trace['match_id'], plan['mother_root'], runtime.config,
                trace['composition']['seed'], trace['initial_dealer'], (0,0,0,0))
            world = call('recovery_world_start', engine.start, spec)
            world = replay(world, trace['frames'][:cut], engine, rules)
            original_frame = call('recovery_frame', engine.frame, world)
            check_frame(original_frame, old, rules)
            directory = _project_file(_PROJECT_ROOT, HERE/target['name'])
            directory.mkdir(exist_ok=False)
            teacher = call('recovery_export_hand', engine.export_hand, world, plan['hand_no'])
            save(directory/'TEACHER-ORIGIN.json', {'scope':'offline teacher only; forbidden author input', 'hand':teacher})
            common = call('recovery_import_hand', engine.from_replay, teacher)
            prefix = [f for f in trace['frames'][:cut] if f[0]['window_key']['round_no'] == plan['hand_no']]
            common = replay(common, prefix, engine, rules)
            current = call('recovery_frame', engine.frame, common)
            check_frame(current, old, rules)
            need([observation_to_json(d.observation) for d in current.decisions] ==
                 [observation_to_json(d.observation) for d in original_frame.decisions], '单局导入改变目标观察')
            snapshot = {'observation_summary':frame_observation_summary(current),
                        'match_spec':{'match_id':trace['match_id']}}
            target_window = window_key_from_json(focal['window_key'])
            per_target = {}
            for arm in ('P','C','A'):
                need(counts['continuations_dispatched'] < plan['max_continuations'], '续打预留超额')
                active_source = child_source if arm == 'C' else source
                fresh = call('runtime_constructor', build_qualifier_runtime, batch, active_source,
                             trace['composition']['opponent_types_logical_1_2_3'])
                policy_id = fresh.baseline_policy_id if arm == 'A' else fresh.challenger_policy_id
                context = {'root_id':target['name'], 'mother_root':plan['mother_root'],
                           'arm':arm, 'focal_seat':0, 'focal_vip':arm != 'A'}
                audited = VipDevelopmentAuditPolicy(fresh.policies_by_id[policy_id], policy_id,
                    lambda c=context:dict(c), record, challenger=arm != 'A',
                    capture=capture if arm != 'A' else None)
                policies = [audited]
                for i in range(1,4):
                    declaration = fresh.declarations['Q'+str(i)]
                    other = dict(context, focal_vip=False, opponent_logical=i)
                    policies.append(VipDevelopmentAuditPolicy(fresh.policies_by_id[declaration.policy_id],
                        declaration.policy_id, lambda c=other:dict(c), record))
                traced = TraceEngine(engine, target['name'], arm)
                need(frame_observation_summary(traced.frame(common)) == snapshot['observation_summary'], '三臂起点不相同')
                before = len(records)
                counts['continuations_dispatched'] += 1
                event({'event':'continuation_start', 'target':target['name'], 'arm':arm})
                outcome = await resume_match(engine=traced, world=common, policies_by_seat=tuple(policies),
                    rules=rules, choice_factory=SimulationChoice,
                    config=MatchDriverConfig('logical', plan['steps_per_continuation'], BudgetPolicy(),
                        'T108-known-case-common-start', True, batch.route_limits),
                    now_monotonic=lambda:800.0, wall_clock=None, value_limits=batch.route_limits,
                    stage_snapshot=snapshot, remaining_schedule={'declared_endpoint':'current_single_hand_end'})
                save(directory/(arm+'-OUTCOME.json'), outcome.to_json())
                need(outcome.status == 'complete' and outcome.completed_hands == 1, '未完成当前单局')
                need(all(getattr(outcome.runtime_counts, k) == 0 for k in
                    ('timeouts','illegal_choices','fallbacks','auto_actions','audit_missing')), '运行错误或正常回退')
                own = [d for d in outcome.decisions if dict(d.window_key) == focal['window_key']]
                need(len(own) == 1, '首动作未唯一实际执行')
                if arm == 'P':
                    expected = [(d['window_key'], d['selected_action_key'], d['seat'])
                        for f in trace['frames'][cut:] if f[0]['window_key']['round_no'] == plan['hand_no'] for d in f]
                    actual = [(dict(d.window_key), d.action_key, d.seat) for d in outcome.decisions]
                    need(actual == expected, '原C全席尾段未精确复现')
                selected_records = records[before:]
                target_record = next(r for r in selected_records if r['window_key'] == focal['window_key'])
                need(target_record['observation'] == focal['observation'], '实际目标观察不一致')
                if arm == 'P':
                    known = next((r for r in public['targets'] if r['arm'] == 'C' and
                                  r['window_key'] == focal['window_key']), None)
                    if known is not None:
                        need(target_record['scoring_execution']['input_capture']['view_sha256'] == known['view_sha256'],
                             '已保存目标DTO身份不同')
                        got = {c['action_key']:{'score':c['score'], 'trace':c['trace']} for c in target_record['candidates']}
                        old_scores = {c['action_key']:{'score':c['score'], 'trace':c['trace']} for c in known['original_full_scores']}
                        need(canonical(got) == canonical(old_scores), '固定公式原分值或解释改变')
                settlement = call('continuation_export_settlement', engine.export_hand_settlement, traced.last, plan['hand_no'])
                if arm == 'P':
                    need(settlement['score_delta'][0] == plan['original_C_hand_net'] and settlement['fan'] == plan['original_C_hand_fan'],
                         '原C终局没有精确复现')
                result = {'target':target['name'], 'arm':arm, 'complete':True, 'settlement':settlement,
                    'focal_net_score':settlement['score_delta'][0], 'executed_first':own[0].action_key,
                    'forced_first_count':0,
                    'actual_decisions':len(selected_records), 'actual_vip_scores':sum(r['c_self_scored'] for r in selected_records),
                    'P_original_whole_tail_exact':arm == 'P'}
                save(directory/(arm+'-RESULT.json'), result)
                per_target[arm] = result
                counts['continuations_completed'] += 1
                print({'target':target['name'], 'arm':arm, 'current_hand_complete':True}, flush=True)
            combined = {'target':target['name'], 'source_window':focal['window_key'], 'results':per_target,
                'C_minus_P':per_target['C']['focal_net_score']-per_target['P']['focal_net_score'],
                'A_minus_P':per_target['A']['focal_net_score']-per_target['P']['focal_net_score']}
            save(directory/'RESULT.json', combined)
            results.append(combined)
    except BaseException as exc:
        primary = exc
        raise
    finally:
        errors = []
        capture_costs = None
        for label, stream in (('decisions',decisions), ('events',events)):
            try:
                stream.close()
            except BaseException as exc:
                errors.append(label+': '+type(exc).__name__+': '+str(exc))
        try:
            capture_costs = capture.finish()
        except BaseException as exc:
            errors.append('capture: '+type(exc).__name__+': '+str(exc))
            try:
                capture_costs = capture.costs
            except BaseException as secondary:
                errors.append('capture.costs: '+type(secondary).__name__+': '+str(secondary))
        try:
            raw.close()
        except BaseException as exc:
            errors.append('views: '+type(exc).__name__+': '+str(exc))
        try:
            stable = all(pin(n) == h for n,h in plan['files'].items())
            stable = stable and all(pin(_project_file(_PROJECT_ROOT, REPO_ROOT/n)) == h for n,h in plan['source_manifest'].items())
            stable = stable and pin(_project_file(_PROJECT_ROOT, HERE/'CAUSAL-START.json')) == start_pin and pin(_project_file(_PROJECT_ROOT, HERE/'RUN-PREPARED.json')) == prepared_pin
        except BaseException as exc:
            stable = False
            errors.append('end-freeze: '+type(exc).__name__+': '+str(exc))
        complete = (primary is None and not errors and stable and capture_costs is not None and
            capture_costs['terminal']['terminal_valid'] and len(results) == len(plan['targets']) and
            counts['continuations_dispatched'] == counts['continuations_completed'] == plan['max_continuations'])
        closure = {'schema':'t108-known-case-causal-closure/1', 'complete':complete, 'source_stable':stable,
            'actual_explicit_api_counts':dict(counts), 'results':results, 'scoring_input_capture':capture_costs,
            'cleanup_errors':errors, 'error':None if primary is None else type(primary).__name__+': '+str(primary),
            'actual_new_independent_sources_or_natural_tables_or_model_calls':0,
            'independent_development_sources':1, 'fresh_result_blind_confirmation':False,
            'normal_R18_fallbacks':0 if complete else None,
            'scope':'known-source whole child formula continuation versus original parent and R18; no frequency/deadline/strength/publication claim',
            'elapsed_monotonic_seconds':time.monotonic()-begun}
        try:
            save(_project_file(_PROJECT_ROOT, HERE/'CAUSAL-CLOSURE.json'), closure)
        except BaseException as secondary:
            if primary is None:
                raise
            primary.add_note('closure write: '+type(secondary).__name__+': '+str(secondary))
        if primary is not None:
            for note in errors:
                primary.add_note(note)
        if primary is None and not complete:
            raise SystemExit(1)
        try:
            print({'complete':complete, 'completed_continuations':counts['continuations_completed'],
                   'actual_vip_scores':counts['actual_vip_score_calls']}, flush=True)
        except BaseException as secondary:
            if primary is None:
                raise
            primary.add_note('terminal print: '+type(secondary).__name__+': '+str(secondary))


if __name__ == '__main__':
    asyncio.run(main())
