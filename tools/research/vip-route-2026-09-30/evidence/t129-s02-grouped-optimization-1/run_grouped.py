"""集中消除重复工作，固定八选择完整差分与原时限；不自动授上线。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t129-s02-grouped-optimization-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from contextlib import contextmanager
from dataclasses import asdict
import argparse
import asyncio
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import sys
import textwrap
import time

HERE = Path(__file__).resolve().parent
T127 = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t127-s02-precision-diagnosis-1')
sys.path.insert(0, str(T127))
import diagnose as base


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def optimized_installed():
    """只在新研究进程安装，退出恢复；第一批不改变展开、公式或预算。"""
    native = load('t129_native_parent', _project_file(_PROJECT_ROOT, HERE / 'native_overlay.py'))
    math = load('t129_math', _project_file(_PROJECT_ROOT, HERE / 'math_batch.py'))
    graph = load('t129_graph', _project_file(_PROJECT_ROOT, HERE / 'graph_batch.py'))
    conversion = load('t129_conversion', _project_file(_PROJECT_ROOT, HERE / 'single_conversion.py'))
    from hangma_bot.policy.route_heuristic_view import VipRouteScoringView
    with native.installed() as parent, math.installed() as (maths, math_stats), graph.installed() as (graphs, graph_stats):
        with conversion.installed(VipRouteScoringView) as (scope, stats):
            identity = {'schema': 't129-grouped-execution/1', 'parent': parent,
                'math': maths, 'graph': graphs,
                'sources': {name: base.sha(_project_file(_PROJECT_ROOT, HERE / name)) for name in
                    ('math_batch.py', 'graph_batch.py', 'single_conversion.py', 'run_grouped.py')},
                'formula_changed': False, 'graph_depth_changed': False,
                'production_changes': 0, 'admission': False}
            identity['execution_id'] = hashlib.sha256(base.canonical(identity)).hexdigest()
            # 只重写研究记录器的两条数据流：生成一次，再让评分消费同次原件。
            # 原记录成功条件、调用计费、异常与落盘收据逻辑保留。
            helper = ACTIVE_HELPER or base.static_check()[1]
            source = textwrap.dedent(inspect.getsource(helper.CaptureExecutor.score_vip_route))
            assert source.count('self.capture.store(view.candidate_view())') == 1
            assert source.count('result = self.original.score_vip_route(view)') == 1
            source = source.replace('receipt = self.capture.store(view.candidate_view())',
                'dto = view.candidate_view()\n    receipt = self.capture.store(dto)')
            source = source.replace('result = self.original.score_vip_route(view)',
                'with __prepared_scope(view, dto):\n            result = self.original.score_vip_route(view)')
            namespace = dict(helper.__dict__, __prepared_scope=scope)
            exec(compile(source, str(_project_file(_PROJECT_ROOT, HERE / 'single_conversion.py')), 'exec'), namespace)
            actual = namespace['score_vip_route']
            original_method = helper.CaptureExecutor.score_vip_route
            helper.CaptureExecutor.score_vip_route = actual
            try:
                yield identity
            finally:
                helper.CaptureExecutor.score_vip_route = original_method
    base.save(_project_file(_PROJECT_ROOT, HERE / 'CONVERSION-STATS.json'), stats)
    base.save(_project_file(_PROJECT_ROOT, HERE / 'MATH-STATS.json'), math_stats)
    base.save(_project_file(_PROJECT_ROOT, HERE / 'GRAPH-STATS.json'), graph_stats)


def prepare():
    """冻结实现与原参考后再执行；不新增规则/评分/作者/桌赛。"""
    parent, helper, cases, freeze, prior = base.static_check()
    for name in ('native_base.py', 'native_overlay.py'):
        with (_project_file(_PROJECT_ROOT, HERE / name)).open('xb') as stream:
            stream.write((_project_file(_PROJECT_ROOT, T127 / name)).read_bytes())
    frozen = dict(parent['frozen_files'])
    for name in ('native_base.py', 'native_overlay.py', 'math_batch.py',
                 'graph_batch.py', 'single_conversion.py', 'run_grouped.py'):
        frozen[str(_project_file(_PROJECT_ROOT, HERE / name))] = base.sha(_project_file(_PROJECT_ROOT, HERE / name))
    labels = helper.read(helper.HERE / 'PLAN.json')['ordered_direct_choose_requests']
    sys.path[:0] = [str(base.RUNTIME), str(base.RUNTIME / 'src')]
    with optimized_installed() as identity:
        pass
    # 准备阶段的空转换统计不用作实际执行统计。
    for name in ('CONVERSION-STATS.json', 'MATH-STATS.json', 'GRAPH-STATS.json'):
        (_project_file(_PROJECT_ROOT, HERE / name)).unlink()
    base.save(_project_file(_PROJECT_ROOT, HERE / 'PLAN.json'), {'schema': 't129-grouped-optimization-plan/1',
        'candidate_identity': parent['candidate_identity'],
        'research_execution_identity': identity, 'frozen_files': frozen,
        'modes': {'grouped': labels}, 'max_rule_choose_score_calls_each': 8,
        'new_authors_tables_worlds': 0, 'original_return_budgets_seconds': [0.63, 2.03],
        'capture_remains_complete_before_score': True,
        'followup': '若仍超时，另身份研究后继杠链有限展开，不能继承原数学全等结论'})
    print(json.dumps({'prepared': True, 'max_choose': 8, 'production_changes': 0}))


def check():
    global ACTIVE_HELPER
    plan = base.read(_project_file(_PROJECT_ROOT, HERE / 'PLAN.json'))
    for path, digest in plan['frozen_files'].items():
        assert base.sha(path) == digest, path
    _, helper, cases, freeze, prior = base.static_check()
    ACTIVE_HELPER = helper
    return plan, helper, cases, freeze, prior


execution_namespace = {}
ACTIVE_HELPER = None


def execute():
    """保留原固定控制流；移除诊断插桩，增加原返回预算的逐请求判断。"""
    plan, *_ = check()
    code = inspect.getsource(base.execute)
    code = code.replace("overlay = load('t127_original_native_overlay', HERE / 'native_overlay.py')",
                        'overlay = __optimized_overlay')
    code = code.replace("'diagnostic_time_is_not_deadline_evidence': True", "'uninstrumented_latency': True")
    code = code.replace("assert exact, '完整数学参考不一致'",
        "row['return_budget_seconds'] = budget.fallback_deadline_monotonic - begin\n"
        "                        row['within_return_budget'] = ready <= budget.fallback_deadline_monotonic\n"
        "                        assert exact, '完整数学参考不一致'")
    execution_namespace.update(base.__dict__)
    execution_namespace.update(HERE=HERE, static_check=check, LABELS=plan['modes'],
        __optimized_overlay=type('Overlay', (), {'installed': staticmethod(optimized_installed)}))
    exec(compile(code, str(_project_file(_PROJECT_ROOT, HERE / 'run_grouped.py')), 'exec'), execution_namespace)
    result = asyncio.run(execution_namespace['execute']('grouped'))
    closed = base.read(_project_file(_PROJECT_ROOT, HERE / 'actual-grouped/CLOSURE.json'))
    base.save(_project_file(_PROJECT_ROOT, HERE / 'TIMING-RESULT.json'), {'full_math_exact': closed['full_math_exact'],
        'timely': sum(bool(row.get('within_return_budget')) for row in closed['rows']),
        'requests': len(closed['rows']), 'rows': closed['rows'],
        'formula_depth_unchanged': True, 'official_admission': False})
    if result:
        return result
    return 0 if all(row.get('within_return_budget') for row in closed['rows']) else 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    if args.prepare:
        prepare()
    elif args.check_only:
        check()
        print(json.dumps({'static_valid': True, 'business_calls': 0}))
    else:
        raise SystemExit(execute())
