"""按首轮结果追加一条构造器分段诊断和一条原生采样。

首轮等待态未归入子计时边界的成本超过200毫秒；原生sample返回255。
因此最多追加两次完整选择。原六次、失败和源件均保留，不改冻结计划。
"""

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
import ast
from contextlib import contextmanager
import gc
import inspect
import json
from pathlib import Path
import sys
import textwrap
import time

import diagnose as base

HERE = Path(__file__).resolve().parent


def check_extension():
    """原封条及追加来源均重新核验，不将失败采样抹去。"""
    plan = base.read(_project_file(_PROJECT_ROOT, HERE / 'DEPTH-PLAN.json'))
    for path, digest in plan['frozen_files'].items():
        assert base.sha(path) == digest, path
    return plan


class DeepTimers(base.Timers):
    """进一步拆构造器、手牌计数与公开校验，所有返回和异常保持原样。"""

    def __init__(self):
        super().__init__()
        self.line_rows = {}
        self.instrumented_sources = []
        self.gc_observer = base.Memory()

    def instrument_statements(self, owner, name):
        """只在原顶层语句前后加时钟，不改变任何原AST语句。"""
        original = owner.__dict__[name]
        source_lines, first = inspect.getsourcelines(original)
        source = textwrap.dedent(''.join(source_lines))
        tree = ast.parse(source)
        function = tree.body[0]
        assert isinstance(function, ast.FunctionDef) and not original.__code__.co_freevars
        assert '__t127_statement_clock' not in source
        before = ast.dump(function, include_attributes=False)
        original_body = list(function.body)
        replacement = []
        metadata = []
        for stmt in original_body:
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
                replacement.append(stmt)
                continue
            label = f'{owner.__name__}.{name}:{first + stmt.lineno - 1}-{first + stmt.end_lineno - 1}'
            marker = ast.parse('__t127_statement_clock = __t127_clock_ns()').body[0]
            after = ast.parse(f'__t127_record_statement({label!r}, __t127_statement_clock)').body[0]
            replacement.extend([marker, stmt, after])
            metadata.append({'label': label, 'source': ast.get_source_segment(source, stmt)})
        function.body = replacement
        recovered = []
        for stmt in function.body:
            if isinstance(stmt, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '__t127_statement_clock' for t in stmt.targets):
                continue
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call) and isinstance(stmt.value.func, ast.Name) and stmt.value.func.id == '__t127_record_statement':
                continue
            recovered.append(stmt)
        function.body = recovered
        assert ast.dump(function, include_attributes=False) == before
        function.body = replacement
        ast.fix_missing_locations(tree)
        def record(label, began):
            duration = time.perf_counter_ns() - began
            row = self.line_rows.setdefault(label, {'calls': 0, 'inclusive_ns': 0})
            row['calls'] += 1
            row['inclusive_ns'] += duration
        namespace = dict(original.__globals__)
        namespace.update(__t127_clock_ns=time.perf_counter_ns, __t127_record_statement=record)
        exec(compile(tree, inspect.getfile(original), 'exec'), namespace)
        instrumented = namespace[name]
        self.changes.append((owner, name, original))
        setattr(owner, name, instrumented)
        self.instrumented_sources.append({'file': inspect.getfile(original),
            'function': name, 'first_line': first, 'source_sha256': base.hashlib.sha256(source.encode()).hexdigest(),
            'original_AST_preserved_after_removing_clock_statements': True, 'segments': metadata})

    @contextmanager
    def installed(self):
        """复用首轮同一装配，只增加更细观测，不启用内存追踪。"""
        from hangma_bot.policy import route_heuristic_view as view, route_vip_heuristic as vip
        from hangma_bot.hangma import route_transition, public_tile_counts, hand_analysis
        with super().installed():
            self.instrument_statements(view.RouteWaitingView, '__post_init__')
            self.method(view.RouteWaitingView, '__post_init__', 'constructors.waiting_view')
            for owner, label in [(route_transition.ConditionalRouteState, 'constructors.conditional_state'),
                                 (public_tile_counts.PublicTileView, 'constructors.public_view')]:
                if '__post_init__' in owner.__dict__:
                    self.method(owner, '__post_init__', label)
            for name in ('_analyse_progress_math', '_analyse_counts_progress_math'):
                if hasattr(hand_analysis, name):
                    self.aliases('hand_math.' + name, getattr(hand_analysis, name))
            if hasattr(vip, '_counts_from_visible_tiles'):
                self.aliases('facts.counts_from_tiles', vip._counts_from_visible_tiles)
            gc.callbacks.append(self.gc_observer.callback)
            try:
                yield self
            finally:
                gc.callbacks.remove(self.gc_observer.callback)
                out = _project_file(_PROJECT_ROOT, HERE / 'actual-depth')
                if out.exists():
                    base.save(out / 'CONSTRUCTOR-STATEMENTS.json', {'sources': self.instrumented_sources,
                        'segments': self.line_rows, 'gc_events_without_tracemalloc': self.gc_observer.gc_events,
                        'statement_inclusive_times_not_instruction_self_times': True,
                        'diagnostic_time_is_not_deadline_evidence': True})


def prepare():
    """仅在明确证据缺口满足时登记追加诊断，规则/评分调用零。"""
    first = base.read(_project_file(_PROJECT_ROOT, HERE / 'actual-timers/FUNCTION-TIMERS.json'))
    response = next(r for r in first['per_case'] if r['label'] == 'original-T80-failed-response')
    assert response['rows']['projection.2._Projection.waiting']['exclusive_among_selected_ns'] > 200000000
    sample = base.read(_project_file(_PROJECT_ROOT, HERE / 'actual-sample/SAMPLE-RECEIPT.json'))
    assert sample['exit_code'] == 255 and not sample['sample_report_present']
    original = base.static_check()[0]
    frozen = dict(original['frozen_files'])
    for path in [Path(__file__), _project_file(_PROJECT_ROOT, HERE / 'PLAN.json'), _project_file(_PROJECT_ROOT, HERE / 'actual-timers/FUNCTION-TIMERS.json'),
                 _project_file(_PROJECT_ROOT, HERE / 'actual-sample/SAMPLE-RECEIPT.json'), _project_file(_PROJECT_ROOT, HERE / 'actual-sample/SAMPLE-CONSOLE.log')]:
        frozen[str(path)] = base.sha(path)
    base.save(_project_file(_PROJECT_ROOT, HERE / 'DEPTH-PLAN.json'), {'schema': 't127-conditional-depth-plan/1',
        'frozen_files': frozen, 'modes': ['depth', 'sample2'],
        'max_additional_rule_choose_score_calls_each': 2, 'max_total_calls_each': 8,
        'reasons': ['waiting_unattributed_over_200ms', 'native_sampler_no_report_exit255'],
        'new_algorithm_or_optimization': False, 'source_and_production_changes': 0})
    print(json.dumps({'prepared': True, 'additional_call_limit': 2, 'actual_business_calls': 0}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--mode', choices=['depth', 'sample2'])
    args = parser.parse_args()
    if args.prepare:
        prepare()
        return 0
    check_extension()
    original_check, original_labels = base.static_check, dict(base.LABELS)
    expanded = dict(original_labels)
    expanded.update(depth=['original-T80-failed-response'], sample2=['original-T80-failed-response'])
    def checked():
        check_extension()
        base.LABELS = original_labels
        try:
            prepared = original_check()
        finally:
            base.LABELS = expanded
        return prepared
    base.static_check = checked
    base.LABELS = expanded
    if args.mode == 'depth':
        base.Timers = DeepTimers
    elif args.mode == 'sample2':
        # sample分支保持首轮原参数，只重定向输出模式；独立追加采样身份。
        source = inspect.getsource(base.execute)
        expected = source.count("if mode == 'sample':")
        assert expected == 1
        changed = source.replace("if mode == 'sample':", "if mode == 'sample2':")
        namespace = dict(base.__dict__)
        exec(compile(changed, str(_project_file(_PROJECT_ROOT, HERE / 'diagnose.py')), 'exec'), namespace)
        base.execute = namespace['execute']
    else:
        parser.error('请选择准备或已登记模式')
    # 首轮仅timers模式会安装计时器；追加depth按同一控制点安装。
    if args.mode == 'depth':
        source = inspect.getsource(base.execute)
        assert source.count("if mode == 'timers' else None") == 1
        namespace = dict(base.__dict__)
        exec(compile(source.replace("if mode == 'timers' else None", "if mode == 'depth' else None"), str(_project_file(_PROJECT_ROOT, HERE / 'diagnose.py')), 'exec'), namespace)
        base.execute = namespace['execute']
    return base.asyncio.run(base.execute(args.mode))


if __name__ == '__main__':
    raise SystemExit(main())
