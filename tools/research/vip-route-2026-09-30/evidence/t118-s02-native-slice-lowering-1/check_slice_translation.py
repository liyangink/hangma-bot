"""在真实S02插桩调用点比较切片翻译；仅语法及合成操作，不调用评分。

原AST经Python编译后直接执行，作为切片及计量参考。修后源码须可解析，
每个真实切片点的返回值与计量均和原AST相同。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t118-s02-native-slice-lowering-1'

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
import copy
import json
from pathlib import Path
import sys

RUNTIME = Path('/Users/liyang/.codex/worktrees/t54-public-count-cache/hangma-bot')
sys.path[:0] = [str(RUNTIME), str(_project_file(_PROJECT_ROOT, RUNTIME / 'src'))]
from hangma_bot.policy import action_value_executor as executor

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--lowered', action='store_true')
    args = parser.parse_args()
    source = (_project_file(_PROJECT_ROOT, HERE.parent / 't110-compact-target-cost-joint-evolution-1/S02-model-output/candidate.py')).read_text()
    tree = executor._Instrumentor().visit(executor.static_check(source))
    ast.fix_missing_locations(tree)
    targets = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name) and n.func.id == '_av_sub'
        and len(n.args) == 2 and isinstance(n.args[1], ast.Slice)]
    assert len(targets) == 2
    builder = ast.parse((_project_file(_PROJECT_ROOT, HERE / 'build_candidate.py')).read_text())
    definition = next(n for n in builder.body if isinstance(n, ast.ClassDef) and n.name == 'SliceCalls')
    module = ast.Module(body=[definition], type_ignores=[])
    namespace = {'ast': ast}
    exec(compile(module, 'actual-SliceCalls', 'exec'), namespace)
    rows = []
    for original in targets:
        meter = executor._Meter(40000)
        env = executor._make_runtime(meter, 8192)
        env['option'] = tuple(range(16))
        baseline = eval(compile(ast.Expression(body=original), 'actual-original-slice', 'eval'), env)
        baseline_ops = meter.used
        lowered = namespace['SliceCalls']().visit(copy.deepcopy(original)) if args.lowered else copy.deepcopy(original)
        ast.fix_missing_locations(lowered)
        rendered = ast.unparse(lowered)
        syntax_error = None
        try:
            parsed = ast.parse(rendered, mode='eval')
        except SyntaxError as exc:
            syntax_error = str(exc)
        row = {'original_rendered': ast.unparse(original), 'rendered': rendered,
               'source_parseable': syntax_error is None, 'syntax_error': syntax_error,
               'baseline_result': baseline, 'baseline_operations': baseline_ops}
        if syntax_error is None:
            fresh = executor._Meter(40000)
            env = executor._make_runtime(fresh, 8192)
            env.update(option=tuple(range(16)), _direct_slice=lambda a, b, c: slice(a, b, c))
            result = eval(compile(parsed, 'actual-lowered-slice', 'eval'), env)
            row.update(result=result, operations=fresh.used,
                       exact_result_and_operations=result == baseline and fresh.used == baseline_ops)
        rows.append(row)
    print(json.dumps({'lowered': args.lowered, 'actual_source_slice_sites': len(targets),
        'synthetic_slice_evaluations': 4 if args.lowered else 2,
        'candidate_scores_rules_models_worlds_tables': 0, 'rows': rows}), flush=True)
    assert all(r['source_parseable'] and r.get('exact_result_and_operations') for r in rows), '实际切片点源码翻译未完整通过'


if __name__ == '__main__':
    main()
