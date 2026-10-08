"""第二联合提案五源25臂续打，核完整输入、真实执行和原父全座位尾段。

完整世界只经生产模拟器公开API复原；自然与条件来源明确区分，
不换对手、不补新键、不重试业务、不授确认或线上时限信用。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t63-second-joint-same-start-1'

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
from collections import Counter
from dataclasses import asdict
from pathlib import Path
import gzip
import json
import sys
import time

from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.kernel.actions import action_key
from hangma_bot.kernel.serialization import observation_to_json, window_key_from_json, window_key_to_json
from hangma_bot.offline.evaluate import MatchDriverConfig, frame_observation_summary, resume_match
from hangma_bot.offline.forced_action import ForceFirstActionPolicy
from hangma_bot.offline.vip_route_development import build_vip_development_runtime
from hangma_bot.offline.qualifier_opponents import build_qualifier_runtime
from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents
from hangma_bot.offline.vip_route_development import VipDevelopmentAuditPolicy
from hangma_bot.simulation import MatchSpec, SimulationChoice
from hangma_bot.simulation.artifacts import hand_math_runtime_metadata

from prepare import HERE, canonical, pin, save


def need(condition, message):
    """与正常业务失败一同留下可核对错误，不借保底继续授候选成绩。"""
    if not condition:
        raise ValueError(message)


async def main():
    plan = json.loads((_project_file(_PROJECT_ROOT, HERE / 'PREPARED.json')).read_text())
    need(plan['status'] == 'prepared_no_START' and plan['python_version'] == sys.version,
         '准备或Python运行身份不同')
    need(not (_project_file(_PROJECT_ROOT, HERE / 'START.json')).exists(), '本批已进入START，不自动重启')
    for name, digest in plan['files'].items():
        need(pin(Path(name)) == digest, '准备来源漂移: ' + name)
    batch = VipEohBatch.read(Path(plan['batch_file']))
    parent = load_vip_parents([Path(plan['parent_package'])], batch)[0]
    child = load_vip_parents([Path(plan['child_package'])], batch)[0]
    need(parent['identity'] == plan['parent_identity'] and child['identity'] == plan['child_identity'],
         '真父或子执行身份不同')
    backend = hand_math_runtime_metadata()
    expected = child['identity']['math_backend']
    need(all(backend.get(k) == expected.get(k) for k in
             ('implementation', 'semantics_version', 'fallback_reason')) and
         backend['native_sha256'] == expected['native_binary']['sha256'], '实际原生数学身份不同')
    with gzip.open(_project_file(_PROJECT_ROOT, HERE / 'SOURCE-MATERIALS.json.gz'), 'rt') as stream:
        material = json.load(stream)
    need(len(material['roots']) == 5, '五源固定分母不同')
    save(_project_file(_PROJECT_ROOT, HERE / 'START.json'), {'schema': 't63-second-joint-common-continuation-start/1',
        'status': 'START', 'prepared_sha256': pin(_project_file(_PROJECT_ROOT, HERE / 'PREPARED.json'))['sha256'],
        'run_sha256': pin(Path(__file__))['sha256'], 'math_backend': backend,
        'continuations_upper': 25, 'fresh_natural_tables': 0,
        'scope': 'four existing natural and one known conditional world, current-hand endpoints only, not confirmation'})
    start_pin, prepare_pin = pin(_project_file(_PROJECT_ROOT, HERE / 'START.json')), pin(_project_file(_PROJECT_ROOT, HERE / 'PREPARED.json'))
    counts, begun, roots_done = Counter(), time.monotonic(), []
    primary = None
    cap_stream = (_project_file(_PROJECT_ROOT, HERE / 'views.jsonl.gz')).open('x+b')
    capture = ScoringInputCapture(cap_stream, limits=ScoringInputCaptureLimits.from_json(plan['budgets']['capture']))
    actual_rows = []
    decision_stream = gzip.open(_project_file(_PROJECT_ROOT, HERE / 'decisions.jsonl.gz'), 'xt')
    event_stream = gzip.open(_project_file(_PROJECT_ROOT, HERE / 'events.jsonl.gz'), 'xt')

    def check_time():
        need(time.monotonic() - begun < plan['budgets']['wall_clock_seconds'], '整批单调墙钟预算耗尽')

    def call(name, fn, *args, **kwargs):
        check_time()
        counts[name] += 1  # 只计公开API的实际派发，失败也保留。
        return fn(*args, **kwargs)

    def event(row):
        event_stream.write(canonical(row).decode() + '\n')
        event_stream.flush()

    def record(row):
        decision_stream.write(canonical(row).decode() + '\n')
        decision_stream.flush()
        actual_rows.append(row)
        counts['actual_policy_decisions'] += 1
        need(row['status'] == 'chosen' and not any('action_value_failed' in reason for reason in row['degraded_reasons']),
             '失败决策或R18内部评分回退')
        if row.get('focal_vip'):
            need(row['c_self_scored'] and len(row['scoring_calls']) == 1,
                 '候选没有自身完整实际评分')
            score_call = row['scoring_calls'][0]
            counts['actual_vip_score_calls'] += score_call['actual_score_calls']
            need(score_call['status'] == 'SCORED' and score_call['full_legal_keys'] and
                 score_call['input_capture']['saved_before_score'], '候选评分或输入不完整')

    def check_frame(frame, records, rules):
        need(frame.blocked_reason is None and frame.final_scores is None, '恢复提前终局或阻塞')
        need([window_key_to_json(d.window_key) for d in frame.decisions] == [r['window_key'] for r in records],
             '恢复完整同期窗口错位')
        analyses = []
        for decision, row in zip(frame.decisions, records):
            need(observation_to_json(decision.observation) == row['observation'], '完整公开观察不同')
            analysis = call('recovery_rules_analyze', rules.analyze, decision.observation, route_limits=batch.route_limits)
            need(analysis.completeness.value == 'complete' and
                 sorted(c.action_key for c in analysis.legal_candidates) == sorted(row['legal_action_keys']),
                 '恢复全合法键不同或规则不完整')
            analyses.append(analysis)
        return analyses

    def replay(world, frames, engine, rules, root_id, phase):
        need(len(frames) <= plan['budgets']['max_recovery_frames_per_root'], '恢复帧数超过预算')
        for ordinal, old in enumerate(frames):
            frame = call('recovery_frame', engine.frame, world)
            analyses = check_frame(frame, old, rules)
            choices = []
            for decision, row, analysis in zip(frame.decisions, old, analyses):
                options = [c for c in analysis.legal_candidates if c.action_key == row['selected_action_key']]
                need(len(options) == 1, '旧动作当前不唯一合法')
                choices.append(SimulationChoice(decision.window_key, options[0].action))
            receipt = {'event': 'recovery_advance', 'root_id': root_id, 'phase': phase,
                'ordinal': ordinal, 'revision': frame.revision,
                'choices': [{'window_key': window_key_to_json(c.window_key), 'action_key': action_key(c.action)} for c in choices]}
            event(dict(receipt, status='advance_pending'))
            world = call('recovery_advance', engine.advance, world, frame.revision, tuple(choices))
            event(dict(receipt, status='advanced'))
        return world

    class TraceEngine:
        """只记录真实推进；最后句柄只交原引擎导出结算，不读暗字段。"""
        def __init__(self, engine, root_id, arm):
            self.engine, self.root_id, self.arm, self.last = engine, root_id, arm, None
            self.advances = 0

        def frame(self, world):
            self.last = world
            return call('continuation_frame', self.engine.frame, world)

        def advance(self, world, revision, choices):
            receipt = {'event': 'continuation_advance', 'root_id': self.root_id, 'arm': self.arm,
                'revision': revision, 'choices': [{'window_key': window_key_to_json(c.window_key),
                    'action_key': action_key(c.action)} for c in choices]}
            event(dict(receipt, status='advance_pending'))
            self.last = call('continuation_advance', self.engine.advance, world, revision, choices)
            self.advances += 1
            event(dict(receipt, status='advanced'))
            return self.last

    try:
        for root in material['roots']:
            factory = build_qualifier_runtime if root['source_kind'] == 'known-natural-original-world' else build_vip_development_runtime
            extra = (root['composition']['opponent_types_logical_1_2_3'],) if root['source_kind'] == 'known-natural-original-world' else ()
            runtime = call('runtime_constructor', factory, batch, parent['source'], *extra)
            if root['source_kind'] == 'known-conditional-existing-hidden-world':
                for label in ('A', 'M1', 'M2', 'M3'):
                    old_meta, actual_meta = root['original_policy_metadata'][label], runtime.policy_metadata[label]
                    fields = ('registered_name', 'params', 'source_sha256', 'max_operations') if label in ('A', 'M1') else ('name', 'params')
                    need(all(canonical(old_meta.get(k)) == canonical(actual_meta.get(k)) for k in fields),
                         '旧条件来源对手源码或参数不同: ' + label)
            raw_engine, rules = runtime.engine, runtime.rules
            permutation = root['permutation']
            directory = _project_file(_PROJECT_ROOT, HERE / root['root_id'].replace(':', '-'))
            directory.mkdir(exist_ok=False)
            teacher = json.loads(Path(root['teacher_path']).read_text())['hand']
            common = call('recovery_import_hand', raw_engine.from_replay, teacher)
            if 'base_sample_key' in root:
                common = call('recovery_recreate_existing_hidden_world',
                    raw_engine.resample_public_consistent_hidden_world, common,
                    focal_seat=root['focal_seat'], sample_key=root['base_sample_key'])
            common = replay(common, root['prefix'], raw_engine, rules, root['root_id'], 'existing_source_prefix')
            frame = call('recovery_frame', raw_engine.frame, common)
            check_frame(frame, root['target_frame'], rules)
            round_no = root['source_window']['round_no']
            snapshot = {'observation_summary': frame_observation_summary(frame),
                        'match_spec': {'match_id': root['source_window']['game_id']}}
            opponent_labels = ['Q1', 'Q2', 'Q3'] if root['source_kind'] == 'known-natural-original-world' else ['M1', 'M2', 'M3']
            save(directory / 'RECOVERY.json', {'status': 'recovered', 'root_id': root['root_id'],
                'source_window': root['source_window'], 'full_target_observations_equal': True,
                'snapshot': snapshot, 'source_kind': root['source_kind'],
                'existing_hidden_sample_key': root.get('base_sample_key'),
                'single_hand_prefix_frames': len(root['prefix']),
                'actual_opponent_metadata': {k: runtime.policy_metadata[k] for k in opponent_labels},
                'scope': 'known development sources, no new independent root'})
            target = window_key_from_json(root['source_window'])
            results, root_rows = {}, []
            for arm in plan['arm_order']:
                check_time()
                need(counts['continuations_dispatched'] < plan['budgets']['max_continuations'], '超过续打分母')
                source = child['source'] if arm in ('C', 'D') else parent['source']
                fresh = call('runtime_constructor', factory, batch, source, *extra)
                base_id = fresh.baseline_policy_id if arm == 'R18' else fresh.challenger_policy_id
                base = fresh.policies_by_id[base_id]
                context = {'root_id': root['root_id'], 'arm': arm, 'focal_seat': root['focal_seat'], 'focal_vip': arm != 'R18'}
                before_rows = len(actual_rows)
                audited = VipDevelopmentAuditPolicy(base, base_id, lambda context=context: dict(context), record,
                    challenger=arm != 'R18', capture=capture if arm != 'R18' else None)
                forced = None
                focal_policy = audited
                if arm in ('B', 'D'):
                    forced = ForceFirstActionPolicy(audited, target_window=target,
                        forced_action_key=root['child_first'] if arm == 'B' else root['parent_first'],
                        policy_id=base_id + ':' + arm)
                    focal_policy = forced
                logical = [focal_policy]
                for i in range(1, 4):
                    declaration = fresh.declarations[opponent_labels[i - 1]]
                    opponent = fresh.policies_by_id[declaration.policy_id]
                    opponent_context = dict(context, focal_vip=False, opponent_logical=i)
                    logical.append(VipDevelopmentAuditPolicy(opponent, declaration.policy_id,
                        lambda context=opponent_context: dict(context), record))
                policies = tuple(logical[permutation.index(seat)] for seat in range(4))
                traced = TraceEngine(raw_engine, root['root_id'], arm)
                need(frame_observation_summary(traced.frame(common)) == snapshot['observation_summary'], '臂起点不同')
                counts['continuations_dispatched'] += 1
                event({'event': 'continuation_start', 'root_id': root['root_id'], 'arm': arm,
                    'ordinal': counts['continuations_dispatched']})
                outcome = await resume_match(engine=traced, world=common, policies_by_seat=policies, rules=rules,
                    choice_factory=SimulationChoice,
                    config=MatchDriverConfig('logical', plan['budgets']['steps_per_continuation'],
                        BudgetPolicy(), 'T63-common-continuation', True, batch.route_limits),
                    now_monotonic=lambda: 800.0, wall_clock=None, value_limits=batch.route_limits,
                    stage_snapshot=snapshot, remaining_schedule={'declared_endpoint': 'current_single_hand_end'})
                save(directory / (arm + '-outcome.json'), outcome.to_json())
                need(outcome.status == 'complete' and outcome.completed_hands == 1, '没有完成声明的单局终点')
                need(all(getattr(outcome.runtime_counts, name) == 0 for name in
                    ('timeouts', 'illegal_choices', 'fallbacks', 'auto_actions', 'audit_missing')), '运行计数非零')
                executed = [d for d in outcome.decisions if dict(d.window_key) == root['source_window']]
                need(len(executed) == 1, '目标没有唯一实际执行')
                expected_first = root['parent_first'] if arm in ('P', 'D') else root['child_first']
                if arm != 'R18':
                    need(executed[0].action_key == expected_first, '首动作实际执行不同')
                if forced is not None:
                    need(forced.force_count == 1, '首动作干预不是恰好一次')
                this_rows = actual_rows[before_rows:]
                focal_target = [r for r in this_rows if r['window_key'] == root['source_window']]
                need(len(focal_target) == 1, '目标完整观察审计缺失或重复')
                observed = focal_target[0]
                need(observed['observation'] == root['focal_observation'], '候选实际读取非同一公开观察')
                if arm != 'R18':
                    need(observed['scoring_execution']['input_capture']['view_sha256'] == root['expected_input_sha256'],
                         '实际完整候选DTO与冻结评分不同')
                    actual_scores = {c['action_key']: {'score': c['score'], 'trace': c['trace']['detail']}
                                     for c in observed['candidates']}
                    expected_scores = ({c['action_key']: {'score': c['score'], 'trace': c['trace']}
                                        for c in root['expected_child_scores']} if arm in ('C', 'D')
                                       else root['expected_parent_scores'])
                    need(canonical(actual_scores) == canonical(expected_scores), '目标完整分数和解释不同')
                settlement = call('continuation_export_settlement', raw_engine.export_hand_settlement, traced.last, round_no)
                focal_net = settlement['score_delta'][root['focal_seat']]
                result = {'root_id': root['root_id'], 'arm': arm, 'status': 'complete', 'settlement': settlement,
                    'focal_net_score': focal_net, 'executed_first': executed[0].action_key,
                    'force_count': 0 if forced is None else forced.force_count,
                    'successful_advances': traced.advances, 'actual_policy_decisions': len(this_rows),
                    'candidate_self_scores': sum(r['c_self_scored'] for r in this_rows),
                    'outcome_file': str(directory / (arm + '-outcome.json'))}
                save(directory / (arm + '-RESULT.json'), result)
                results[arm] = result
                root_rows.append(result)
                if arm == 'P':
                    expected_tail = root['expected_parent_full_tail']
                    need([(r['window_key'], r['selected_action_key'], r['observation']) for r in this_rows] ==
                         [(r['window_key'], r['selected_action_key'], r['observation']) for r in expected_tail],
                         '真T59父未精确复现其旧全座位尾段')
                counts['continuations_completed'] += 1
                print({'root': root['root_id'], 'arm': arm, 'net': focal_net,
                       'first': executed[0].action_key, 'fan': settlement['fan'],
                       'winner': settlement['winner_seat']}, flush=True)
            deltas = {name: results[name]['focal_net_score'] - results['P']['focal_net_score'] for name in ('C', 'B', 'D', 'R18')}
            deltas['C_minus_B'] = results['C']['focal_net_score'] - results['B']['focal_net_score']
            roots_done.append({'root_id': root['root_id'], 'mother_root': root['mother_root'],
                'category': root['category'], 'results': root_rows, 'deltas': deltas,
                'parent_original_full_tail_exact': True})
            save(directory / 'ROOT-RESULT.json', roots_done[-1])
    except BaseException as exc:
        primary = exc
        event({'event': 'batch_failed', 'error': type(exc).__name__ + ': ' + str(exc), 'actual_counts': dict(counts)})
        raise
    finally:
        decision_stream.close()
        event_stream.close()
        capture_costs = capture.finish()
        terminal = capture_costs['terminal']
        cap_stream.close()
        stable = all(pin(Path(name)) == digest for name, digest in plan['files'].items())
        stable &= pin(_project_file(_PROJECT_ROOT, HERE / 'START.json')) == start_pin and pin(_project_file(_PROJECT_ROOT, HERE / 'PREPARED.json')) == prepare_pin
        valid = primary is None and stable and terminal['terminal_valid'] and len(roots_done) == 5
        valid &= counts['continuations_dispatched'] == counts['continuations_completed'] == 25
        save(_project_file(_PROJECT_ROOT, HERE / 'CLOSURE.json'), {'schema': 't63-second-joint-common-continuation-closure/1',
            'complete': valid, 'source_stable': stable, 'actual_explicit_api_counts': dict(counts),
            'roots': roots_done, 'scoring_input_capture': capture_costs,
            'files': {name: pin(_project_file(_PROJECT_ROOT, HERE / name)) for name in ('decisions.jsonl.gz', 'events.jsonl.gz', 'views.jsonl.gz')},
            'elapsed_monotonic_seconds': time.monotonic() - begun,
            'error': None if primary is None else type(primary).__name__ + ': ' + str(primary),
            'normal_r18_fallbacks': 0 if primary is None else None,
            'actual_new_model_calls': 0, 'actual_new_natural_complete_tables': 0,
            'scope': 'same original closed world interventions, not unseen strength, natural frequency or online deadline evidence'})
        print({'complete': valid, 'completed_continuations': counts['continuations_completed'],
               'actual_vip_score_calls': counts['actual_vip_score_calls']}, flush=True)
        if primary is None and not valid:
            raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true', required=True)
    parser.parse_args()
    asyncio.run(main())
