"""把已确认的S02原受限插桩源码编译为独占闭包，不生成新评分公式。

使用冻结规则运行目录与T89已验证原生计量ABI。字面量传递助手的调用
只改为同语义原生助手，仍在原位置计费；首次构建原件不可覆盖。
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
import ast
import hashlib
import inspect
import json
from pathlib import Path
import platform
import sys

RUNTIME = Path('/Users/liyang/.codex/worktrees/t54-public-count-cache/hangma-bot')
sys.path[:0] = [str(RUNTIME), str(_project_file(_PROJECT_ROOT, RUNTIME / 'src'))]
from Cython import __version__ as cython_version
from Cython.Build import cythonize
from setuptools import Extension, setup
from hangma_bot.policy import action_value_executor as executor

HERE = Path(__file__).resolve().parent
AUTHOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t110-compact-target-cost-joint-evolution-1')
T89 = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t89-fast-meter-prototype-1')
DIRECTIVES = dict(language_level=3, annotation_typing=False, infer_types=False,
    boundscheck=True, wraparound=True, nonecheck=True, cdivision=False,
    overflowcheck=True, binding=True)


def raw(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


class PassCalls(ast.NodeTransformer):
    """仅替换受限插桩的传递计费助手；调用顺序、参数及结果不改。"""
    def __init__(self):
        self.calls = 0

    def visit_Call(self, node):
        node = self.generic_visit(node)
        if isinstance(node.func, ast.Name) and node.func.id == '_av_pass':
            assert len(node.args) == 1 and not node.keywords
            self.calls += 1
            return ast.copy_location(ast.Call(func=ast.Name(id='_direct_pass', ctx=ast.Load()),
                args=[ast.Name(id='bound_meter', ctx=ast.Load()), node.args[0]], keywords=[]), node)
        return node



class SliceCalls(ast.NodeTransformer):
    """显式构造内部切片对象，保持Python BUILD_SLICE值和原计量位置。"""
    def __init__(self):
        self.calls = 0

    def visit_Call(self, node):
        node = self.generic_visit(node)
        if (isinstance(node.func, ast.Name) and node.func.id == '_av_sub'
                and len(node.args) == 2 and isinstance(node.args[1], ast.Slice)):
            value = node.args[1]
            self.calls += 1
            node.args[1] = ast.copy_location(ast.Call(
                func=ast.Name(id='_direct_slice', ctx=ast.Load()),
                args=[item if item is not None else ast.Constant(value=None)
                      for item in (value.lower, value.upper, value.step)], keywords=[]), value)
        return node

assert not (_project_file(_PROJECT_ROOT, HERE / 'BUILD-PLAN.json')).exists()
old = json.loads((_project_file(_PROJECT_ROOT, T89 / 'BUILD-PLAN.json')).read_text())
assert sha(Path(inspect.getfile(executor)).read_bytes()) == old['original_executor_file_sha256']
runtime_source = inspect.getsource(executor._make_runtime)
assert sha(runtime_source.encode()) == old['original_runtime_source_sha256']
assert sha(inspect.getsource(executor._Meter).encode()) == old['original_meter_source_sha256']
source = (_project_file(_PROJECT_ROOT, AUTHOR / 'S02-model-output/candidate.py')).read_text()
reference = json.loads((_project_file(_PROJECT_ROOT, HERE.parent / 't113-t110-s02-deadline-preparation-1/PLAN.json')).read_text())
assert sha(source.encode()) == reference['candidate_identity']['source_sha256']
tree = executor.static_check(source)
instrumented = executor._Instrumentor().visit(tree)
ast.fix_missing_locations(instrumented)
instrumented_sha = sha(ast.dump(instrumented, include_attributes=False).encode())
pass_rewriter = PassCalls()
direct = pass_rewriter.visit(instrumented)
slice_rewriter = SliceCalls()
direct = slice_rewriter.visit(direct)
ast.fix_missing_locations(direct)
assert not any(isinstance(n, ast.Slice) for n in ast.walk(direct))
runtime_names = sorted(executor._make_runtime(executor._Meter(4800000), 8192))
top_names = []
for statement in tree.body:
    if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
        top_names.append(statement.name)
    elif isinstance(statement, ast.Assign):
        for target in statement.targets:
            assert isinstance(target, ast.Name)
            top_names.append(target.id)
    elif isinstance(statement, ast.AnnAssign):
        assert isinstance(statement.target, ast.Name)
        top_names.append(statement.target.id)
    else:
        assert isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant)

pass_source = next(node for node in ast.parse(runtime_source).body[0].body
                   if isinstance(node, ast.FunctionDef) and node.name == 'av_pass')
pass_text = ast.unparse(pass_source)
pass_text = pass_text.replace('def av_pass(value: Any) -> Any:',
    'cdef inline object _direct_pass(_Meter meter, object value):', 1)
pass_text = pass_text.replace('meter.charge(1)', 'meter._charge_one()', 1)
assert 'cdef inline object _direct_pass' in pass_text
factory = ('from __future__ import annotations\n'
    'from _t89_runtime cimport _Meter\n'
    'from hangma_bot.policy.action_value_executor import WorkloadExceeded, MAX_STRING_CHARS\n\n'
    + pass_text + '\n\n'
    'cdef inline object _direct_slice(object lower, object upper, object step):\n'
    '    return slice(lower, upper, step)\n\n'
    'def make_candidate(runtime, _Meter bound_meter):\n'
    '    """每执行器独占闭包与计量；不使用候选模块全局共享状态。"""\n')
factory += ''.join('    ' + name + ' = runtime[' + repr(name) + ']\n' for name in runtime_names)
factory += ''.join('    ' + line.rstrip() + '\n' for line in ast.unparse(direct).splitlines())
factory += '    return {\n        "__builtins__": {},\n'
factory += ''.join('        ' + repr(name) + ': ' + name + ',\n'
                  for name in runtime_names + top_names) + '    }\n'
generated = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t118-s02-native-slice-lowering-1/_t118_candidate.pyx')
generated.write_text(factory)
plan = {'schema': 't118-current-s02-native-slice-build/1',
    'generator_sha256': sha(Path(__file__).read_bytes()),
    'base_candidate_identity': reference['candidate_identity'],
    'candidate_source_sha256': sha(source.encode()),
    'original_executor_file_sha256': old['original_executor_file_sha256'],
    'instrumented_ast_sha256': instrumented_sha,
    'direct_call_ast_sha256': sha(ast.dump(direct, include_attributes=False).encode()),
    'direct_pass_static_sites': pass_rewriter.calls,
    'slice_lowering_static_sites': slice_rewriter.calls,
    'failed_parent_build_plan_sha256': sha((_project_file(_PROJECT_ROOT, HERE.parent / 't117-s02-native-execution-1/BUILD-PLAN.json')).read_bytes()),
    'generated_source_sha256': sha(factory.encode()),
    'runtime_pxd_sha256': sha((_project_file(_PROJECT_ROOT, T89 / '_t89_runtime.pxd')).read_bytes()),
    'runtime_build_closure_sha256': sha((_project_file(_PROJECT_ROOT, T89 / 'BUILD-CLOSURE.json')).read_bytes()),
    'directives': DIRECTIVES, 'cython_version': cython_version,
    'python_version': sys.version, 'platform': platform.platform(),
    'new_candidate_formulas': 0, 'actual_rules_choose_scores_worlds_tables': 0,
    'production_changes': 0, 'admission': False}
with (_project_file(_PROJECT_ROOT, HERE / 'BUILD-PLAN.json')).open('xb') as stream:
    stream.write(raw(plan) + b'\n')
setup(name='hangma-t118-s02-native-probe',
    ext_modules=cythonize([Extension('_t118_candidate', [str(generated)])],
        compiler_directives=DIRECTIVES, include_path=[str(T89)]),
    script_args=['build_ext', '--build-temp', str(_project_file(_PROJECT_ROOT, HERE / 'build/temp')),
                 '--build-lib', str(_project_file(_PROJECT_ROOT, HERE / 'build/lib'))])
binary, = (_project_file(_PROJECT_ROOT, HERE / 'build/lib')).glob('_t118_candidate*.so')
closure = {'plan_sha256': sha((_project_file(_PROJECT_ROOT, HERE / 'BUILD-PLAN.json')).read_bytes()),
    'binary': {'path': str(binary.relative_to(HERE)), 'bytes': binary.stat().st_size,
               'sha256': sha(binary.read_bytes())}, 'new_formulas_rules_choose_scores_tables': 0}
with (_project_file(_PROJECT_ROOT, HERE / 'BUILD-CLOSURE.json')).open('xb') as stream:
    stream.write(raw(closure) + b'\n')
