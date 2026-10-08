"""固定S02的精细诊断；不修改候选、规则、图覆盖或执行优化。

四个诊断模式在独立进程运行，最多六次完整选择。计时、内存和原生
采样分别记录，避免混合测量开销。每次仍验完整输入、全部分数、解释
及操作计量；诊断耗时不授实时准入。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t127-s02-precision-diagnosis-1'

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
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
import gc
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pstats
import resource
import subprocess
import sys
import time
import tracemalloc

HERE = Path(__file__).resolve().parent
PARENT = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t123-s02-optimized-full-panel-1')
T113 = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t113-t110-s02-deadline-preparation-1')
T125 = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t125-native-internal-profile-1')
RUNTIME = Path('/Users/liyang/.codex/worktrees/t54-public-count-cache/hangma-bot')
LABELS = {
    'baseline': ['original-T80-failed-response'],
    'timers': ['old:t74:089:1979', 'old:public:20', 'original-T80-failed-response'],
    'memory': ['original-T80-failed-response'],
    'sample': ['original-T80-failed-response'],
}


def canonical(value):
    """严格完整JSON字节；输入与评分比较不使用浮点容差。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    """只创建新证据，保留首轮和任何失败。"""
    with Path(path).open('xb') as stream:
        stream.write(canonical(value) + b'\n')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def known_profile():
    """重读原完整prof，导出所有函数及调用边，不新增业务调用。"""
    profile = _project_file(_PROJECT_ROOT, T125 / 'actual-full-1/PROFILE-01.prof')
    stats = pstats.Stats(str(profile))
    rows = []
    for (filename, line, name), (primitive, calls, own, cumulative, callers) in stats.stats.items():
        edges = []
        for (parent, parentline, parentname), values in callers.items():
            edges.append({'file': parent, 'line': parentline, 'function': parentname,
                          'pstats_edge_tuple': values})
        rows.append({'file': filename, 'line': line, 'function': name,
                     'calls': calls, 'primitive_calls': primitive,
                     'self_seconds': own, 'inclusive_seconds': cumulative,
                     'callers': edges})
    return {'profile_sha256': sha(profile), 'total_calls': stats.total_calls,
            'total_self_seconds': stats.total_tt,
            'profiled_seconds_are_not_uninstrumented_latency': True,
            'rows': sorted(rows, key=lambda row: -row['self_seconds'])}


def prepare():
    """冻结已有T123装配和诊断源；准备阶段规则/选择/评分调用为零。"""
    HERE.mkdir(exist_ok=True)
    parent = read(_project_file(_PROJECT_ROOT, PARENT / 'PLAN.json'))
    for name in ('native_base.py', 'native_overlay.py'):
        with (_project_file(_PROJECT_ROOT, HERE / name)).open('xb') as stream:
            stream.write((_project_file(_PROJECT_ROOT, PARENT / name)).read_bytes())
    sys.path[:0] = [str(RUNTIME), str(_project_file(_PROJECT_ROOT, RUNTIME / 'src'))]
    overlay = load('t127_freeze_overlay', _project_file(_PROJECT_ROOT, HERE / 'native_overlay.py'))
    with overlay.installed() as identity:
        pass
    frozen = dict(parent['frozen_files'])
    for path in [Path(__file__), _project_file(_PROJECT_ROOT, HERE / 'native_base.py'), _project_file(_PROJECT_ROOT, HERE / 'native_overlay.py'),
                 _project_file(_PROJECT_ROOT, PARENT / 'PLAN.json'), _project_file(_PROJECT_ROOT, PARENT / 'actual-full-1/CLOSURE.json'),
                 _project_file(_PROJECT_ROOT, T125 / 'actual-full-1/PROFILE-01.prof')]:
        frozen[str(path)] = sha(path)
    plan = {'schema': 't127-precision-diagnosis-plan/1',
            'candidate_identity': parent['candidate_identity'],
            'research_execution_identity': identity,
            'frozen_files': frozen, 'modes': LABELS,
            'max_rule_choose_score_calls_each': 6,
            'new_authors_tables_worlds': 0,
            'timed_wrapper_is_not_optimization': True,
            'sample_seconds': 3, 'sample_interval_ms': 1,
            'tracemalloc_frames': 8,
            'source_and_production_changes': 0}
    save(_project_file(_PROJECT_ROOT, HERE / 'PLAN.json'), plan)
    save(_project_file(_PROJECT_ROOT, HERE / 'EXISTING-PROFILE-CALLERS.json'), known_profile())
    print(json.dumps({'prepared': True, 'actual_business_calls': 0,
                      'max_rule_choose_score_calls_each': 6}))


class Timers:
    """选定调用边界计时，独占时间只排除其他已选边界，非指令级自身时间。"""

    def __init__(self):
        self.stack = []
        self.rows = {}
        self.changes = []

    def wrap(self, label, function):
        """原参数、原返回值和原异常直接传递；只增加诊断计时。"""
        def measured(*args, **kwargs):
            frame = [label, time.perf_counter_ns(), 0]
            self.stack.append(frame)
            failed = False
            try:
                return function(*args, **kwargs)
            except BaseException:
                failed = True
                raise
            finally:
                elapsed = time.perf_counter_ns() - frame[1]
                assert self.stack.pop() is frame
                if self.stack:
                    self.stack[-1][2] += elapsed
                row = self.rows.setdefault(label, {'calls': 0, 'errors': 0,
                    'inclusive_ns': 0, 'exclusive_among_selected_ns': 0,
                    'max_call_ns': 0})
                row['calls'] += 1
                row['errors'] += int(failed)
                row['inclusive_ns'] += elapsed
                row['exclusive_among_selected_ns'] += elapsed - frame[2]
                row['max_call_ns'] = max(row['max_call_ns'], elapsed)
        return measured

    def aliases(self, label, function):
        """仅按对象身份替换本进程第一方别名，不修改标准库模块。"""
        replacement = self.wrap(label, function)
        for module in tuple(sys.modules.values()):
            name = '' if module is None else getattr(module, '__name__', '')
            if not name.startswith(('hangma_bot.', '_t88_', '_t120_')):
                continue
            for alias, value in tuple(vars(module).items()):
                if value is function:
                    self.changes.append((module, alias, value))
                    setattr(module, alias, replacement)

    def method(self, owner, name, label):
        """保留静态方法描述符与方法绑定；同一拥有类只安装一次。"""
        original = owner.__dict__[name]
        function = original.__func__ if isinstance(original, staticmethod) else original
        replacement = self.wrap(label, function)
        if isinstance(original, staticmethod):
            replacement = staticmethod(replacement)
        self.changes.append((owner, name, original))
        setattr(owner, name, replacement)

    @contextmanager
    def installed(self):
        """在已验T123装配上附加计时，退出反序恢复。"""
        from hangma_bot.policy import route_vip_heuristic as vip, route_heuristic_view as view
        from hangma_bot.hangma import route_transition as transition
        from hangma_bot.hangma import hand_analysis, route_structure, natural_preparation, public_tile_counts
        import dataclasses
        targets = [
            ('transition.refresh_public', transition._refresh_public),
            ('transition.discard', transition._apply_legal_self_discard),
            ('transition.given_draw', transition.apply_given_draw),
            ('transition.replacement_rules', transition.analyze_given_replacement_draw),
            ('transition.claim_rules', transition.analyze_given_claim_action),
            ('transition.followup_gang', transition.apply_legal_followup_gang),
            ('facts.hand_analysis', hand_analysis.analyse_hand),
            ('facts.route_structure', route_structure.analyze_route_structure),
            ('facts.natural_preparation', natural_preparation.analyze_natural_set_preparation),
            ('public.count_unseen', public_tile_counts.count_unseen_tiles_from_view),
            ('objects.replace', dataclasses.replace),
            ('graph.build', vip.build_vip_route_scoring_view),
        ]
        if hasattr(vip, 'analyze_waiting_hu_witness'):
            targets.append(('facts.hu_witness', vip.analyze_waiting_hu_witness))
        try:
            for label, function in targets:
                self.aliases(label, function)
            for depth, owner in enumerate(vip._Projection.__mro__):
                for name in ('replacement', 'action_choices', 'waiting', 'compatible_codes',
                             'code_width', 'add', 'choices_key', 'public_key', 'replacement_key'):
                    if name in owner.__dict__:
                        self.method(owner, name, f'projection.{depth}.{owner.__name__}.{name}')
            self.method(view.VipRouteScoringView, 'candidate_view', 'objects.candidate_view')
            yield self
        finally:
            for owner, name, original in reversed(self.changes):
                setattr(owner, name, original)
            assert not self.stack

    def calibration(self):
        """纯空函数估计计时器额外成本，不调用规则、候选或模拟。"""
        def noop():
            return None
        n = 50000
        begin = time.perf_counter_ns()
        for _ in range(n):
            noop()
        plain = time.perf_counter_ns() - begin
        measured = self.wrap('calibration', noop)
        begin = time.perf_counter_ns()
        for _ in range(n):
            measured()
        wrapped = time.perf_counter_ns() - begin
        self.rows.clear()
        return {'iterations': n, 'plain_ns': plain, 'wrapped_ns': wrapped,
                'extra_ns_per_call': (wrapped - plain) / n,
                'only_approximate_overhead_not_subtracted_from_real_results': True}


class Memory:
    """Python受跟踪分配、阶段峰值和GC暂停；不包含全部原生malloc。"""

    def __init__(self):
        self.rows = []
        self.previous = None
        self.last_current = 0
        self.gc_events = []
        self.gc_start = {}

    def callback(self, phase, info):
        """只观察正常GC，不主动收集或禁止GC，持续时间使用单调时钟。"""
        generation = info['generation']
        if phase == 'start':
            self.gc_start[generation] = time.perf_counter_ns()
        elif phase == 'stop':
            began = self.gc_start.pop(generation, None)
            self.gc_events.append({'generation': generation,
                'duration_ns': None if began is None else time.perf_counter_ns() - began,
                'collected': info['collected'], 'uncollectable': info['uncollectable']})

    def mark(self, label):
        """保存边界存活量与相邻快照差；快照本身开销单独记。"""
        began = time.perf_counter_ns()
        current, peak = tracemalloc.get_traced_memory()
        snapshot = tracemalloc.take_snapshot()
        statistics = snapshot.statistics('traceback') if self.previous is None else snapshot.compare_to(self.previous, 'traceback')
        top = []
        for item in statistics[:20]:
            top.append({'size_bytes': item.size, 'count': item.count,
                'size_diff_bytes': getattr(item, 'size_diff', item.size),
                'count_diff': getattr(item, 'count_diff', item.count),
                'traceback': [{'file': frame.filename, 'line': frame.lineno} for frame in item.traceback]})
        self.rows.append({'boundary': label, 'traced_current_bytes': current,
            'traced_peak_since_previous_boundary_bytes': peak,
            'peak_above_previous_current_bytes': peak - self.last_current,
            'tracemalloc_internal_bytes': tracemalloc.get_tracemalloc_memory(),
            'ru_maxrss_raw': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'host': sys.platform, 'snapshot_seconds': (time.perf_counter_ns() - began) / 1e9,
            'top_retained_or_net_differences': top})
        self.previous = snapshot
        self.last_current = tracemalloc.get_traced_memory()[0]
        tracemalloc.reset_peak()

    @contextmanager
    def installed(self):
        """只在业务段启用跟踪，退出恢复回调；8层Python调用栈不是C分配栈。"""
        tracemalloc.start(8)
        gc.callbacks.append(self.callback)
        try:
            yield self
        finally:
            gc.callbacks.remove(self.callback)
            tracemalloc.stop()


def static_check():
    plan = read(_project_file(_PROJECT_ROOT, HERE / 'PLAN.json'))
    for path, expected in plan['frozen_files'].items():
        assert sha(path) == expected, path
    helper = load('t127_original_reference', _project_file(_PROJECT_ROOT, T113 / 'run_deadline_corrected.py'))
    _, cases, freeze = helper.static_check()
    prior = read(_project_file(_PROJECT_ROOT, T113 / 'actual-direct-2/CLOSURE.json'))
    assert prior['mathematical_complete']
    assert plan['modes'] == LABELS
    return plan, helper, cases, freeze, prior


async def execute(mode):
    """固定模式仅执行登记请求；原生采样失败保留，不重复业务寻找好结果。"""
    plan, helper, cases, freeze, prior = static_check()
    sys.path[:0] = [str(RUNTIME), str(_project_file(_PROJECT_ROOT, RUNTIME / 'src'))]
    from hangma_bot.application.deadline import BudgetPolicy, SystemClock
    from hangma_bot.hangma.engine import HangmaRules
    from hangma_bot.kernel.observation import CompetitionContext
    from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
    from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
    from hangma_bot.offline.vip_eoh_generate import VipEohBatch
    from hangma_bot.policy.interface import DecisionRequest
    from hangma_bot.policy.route_vip_heuristic import RouteVipHeuristicPolicy
    overlay = load('t127_original_native_overlay', _project_file(_PROJECT_ROOT, HERE / 'native_overlay.py'))
    out = _project_file(_PROJECT_ROOT, HERE / ('actual-' + mode))
    out.mkdir(exist_ok=False)
    helper.OUT = out
    costs = dict.fromkeys(helper.COUNTERS, 0)
    rows, issues, timer_rows = [], [], []
    memory = Memory() if mode == 'memory' else None
    sampler = None
    sample_receipt = None
    save(out / 'START.json', {'mode': mode, 'pid': os.getpid(),
        'started_at_utc': datetime.now(timezone.utc).isoformat(), 'plan_sha256': sha(_project_file(_PROJECT_ROOT, HERE / 'PLAN.json')),
        'labels': LABELS[mode], 'actual_score_limit': len(LABELS[mode]),
        'diagnostic_time_is_not_deadline_evidence': True})
    batch = VipEohBatch.read(helper.AUTHOR / 'AUTHOR-BATCH.json')
    source = (helper.AUTHOR / 'S02-model-output/candidate.py').read_text()
    assert batch.identity(source) == plan['candidate_identity']
    with overlay.installed() as actual_identity:
        assert actual_identity == plan['research_execution_identity']
        policy = RouteVipHeuristicPolicy(batch.rule_config, source=source,
            max_operations=batch.max_operations, projection_limits=batch.projection_limits)
        assert type(policy.executor._fn).__name__ == 'cython_function_or_method'
        timer = Timers() if mode == 'timers' else None
        calibration = timer.calibration() if timer else None
        with (out / 'ACTUAL-INPUTS.jsonl.gz').open('x+b') as stream:
            capture = ScoringInputCapture(stream, limits=ScoringInputCaptureLimits.from_json(freeze['capture_limits']))
            executor = helper.CaptureExecutor(policy.executor, capture, costs, 'direct')
            policy.executor = executor
            if memory:
                original_score = executor.score_vip_route
                def memory_score(view):
                    memory.mark('graph_ready')
                    result = original_score(view)
                    memory.mark('score_returned')
                    return result
                executor.score_vip_route = memory_score
            with (timer.installed() if timer else nullcontext()), (memory.installed() if memory else nullcontext()):
                if memory:
                    memory.mark('before_rules')
                if mode == 'sample':
                    sample_receipt = {'argv': ['/usr/bin/sample', str(os.getpid()), '3', '1', '-mayDie', '-fullPaths', '-file', str(out / 'NATIVE-SAMPLE.txt')],
                                      'started_monotonic': time.monotonic()}
                    sampler = subprocess.Popen(sample_receipt['argv'], stdout=(out / 'SAMPLE-CONSOLE.log').open('xb'), stderr=subprocess.STDOUT)
                    await asyncio.sleep(0.2)
                for ordinal, label in enumerate(LABELS[mode], 1):
                    expected = next(row for row in prior['rows'] if row['label'] == label)
                    obs = observation_from_json(cases[label]['observation'])
                    key = window_key_from_json(cases[label]['window_key'])
                    executor.label = label
                    before = {} if not timer else {name: dict(value) for name, value in timer.rows.items()}
                    clock, budgets = SystemClock(), BudgetPolicy()
                    begin, cpu_begin = clock.now(), time.process_time()
                    budget = budgets.build(begin, 1.0 if obs.phase.startswith('response_') else 3.0)
                    row = {'label': label, 'status': 'not_scored', 'began_monotonic': begin}
                    try:
                        costs['rule_attempts'] += 1
                        rules = HangmaRules(batch.rule_config).analyze(obs, route_limits=batch.route_limits)
                        rules_end = clock.now()
                        if memory:
                            memory.mark('rules_ready')
                        request = DecisionRequest(obs, CompetitionContext('T127-diagnostic', None, None, None, None, (), 0), rules, label, key.trigger_seq, key, ())
                        costs['choose_attempts'] += 1
                        chosen = await policy.choose(request, budget)
                        ready, cpu_end = clock.now(), time.process_time()
                        if memory:
                            memory.mark('choose_returned')
                        assert len(executor.calls) == ordinal and not chosen.degraded_reasons
                        call = executor.calls[-1]
                        actual = [{'action_key': c.action_key, 'score': c.total_score, 'trace': c.score_trace['detail']} for c in chosen.candidates]
                        order = lambda xs: sorted(xs, key=lambda x: x['action_key'])
                        exact = (call['input_capture']['view_sha256'] == expected['actual_input_sha256']
                            and call['operations'] == expected['operations']
                            and canonical(order(actual)) == canonical(order(expected['actual_scores']))
                            and {c['action_key'] for c in actual} == {c.action_key for c in rules.legal_candidates})
                        row.update(status='SCORED', exact_input_all_scores_traces_operations=exact,
                            input_sha256=call['input_capture']['view_sha256'], operations=call['operations'],
                            chosen_action_key=chosen.candidates[0].action_key,
                            ready_monotonic=ready, elapsed_seconds=ready - begin, cpu_seconds=cpu_end - cpu_begin,
                            rules_seconds=rules_end - begin,
                            graph_preparation_seconds=call['input_ready_monotonic'] - rules_end,
                            capture_seconds=call['capture_wall_seconds'], score_seconds=call['score_wall_seconds'])
                        assert exact, '完整数学参考不一致'
                    except BaseException as exc:
                        row.update(status='failed', error=type(exc).__name__ + ': ' + str(exc))
                        issues.append(row['error'])
                    finally:
                        if timer:
                            delta = {}
                            for name, value in timer.rows.items():
                                old = before.get(name, {})
                                delta[name] = {k: v - old.get(k, 0) for k, v in value.items() if k != 'max_call_ns'}
                            timer_rows.append({'label': label, 'rows': delta})
                        save(out / f'CHOOSE-{ordinal:02d}.json', row)
                        rows.append(row)
                        print(json.dumps(row, ensure_ascii=False), flush=True)
                    if issues:
                        break
                if sampler:
                    sampler.wait(timeout=15)
                    sample_receipt.update(exit_code=sampler.returncode, finished_monotonic=time.monotonic(),
                        sample_report_present=(out / 'NATIVE-SAMPLE.txt').exists())
                    save(out / 'SAMPLE-RECEIPT.json', sample_receipt)
            capture_costs = capture.finish()
    if timer:
        save(out / 'FUNCTION-TIMERS.json', {'calibration': calibration, 'per_case': timer_rows,
            'selected_call_boundary_time_not_true_function_self_time': True,
            'time_with_instrumentation_not_deadline_evidence': True})
    if memory:
        save(out / 'MEMORY-GC.json', {'boundaries': memory.rows, 'gc_events': memory.gc_events,
            'native_malloc_not_fully_observed': True, 'net_surviving_allocations_not_total_allocation_volume': True,
            'snapshot_and_tracemalloc_overhead_not_deadline_evidence': True})
    if not capture_costs['terminal']['terminal_valid']:
        issues.append('完整输入捕获终态无效')
    static_check()
    complete = (not issues and len(rows) == len(LABELS[mode])
        and all(row['exact_input_all_scores_traces_operations'] for row in rows)
        and costs['rule_attempts'] == costs['choose_attempts'] == costs['direct_score_attempts'] == len(rows)
        and costs['failed_score_attempts'] == costs['reference_score_attempts'] == 0)
    save(out / 'CLOSURE.json', {'schema': 't127-precision-diagnosis-result/1', 'mode': mode,
        'candidate_identity': plan['candidate_identity'], 'execution_identity': actual_identity,
        'full_math_exact': complete, 'actual_costs': costs, 'rows': rows, 'issues': issues,
        'capture': capture_costs, 'native_sample': sample_receipt,
        'source_and_production_changes': 0, 'new_authors_tables_worlds': 0,
        'deadline_admission': False, 'online_admission': False})
    return 0 if complete else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--mode', choices=LABELS)
    args = parser.parse_args()
    if args.prepare:
        prepare()
        return 0
    if args.check_only:
        static_check()
        print(json.dumps({'static_valid': True, 'actual_business_calls': 0}))
        return 0
    if not args.mode:
        parser.error('必须选择准备、静态核验或一个冻结诊断模式')
    return asyncio.run(execute(args.mode))


if __name__ == '__main__':
    raise SystemExit(main())
