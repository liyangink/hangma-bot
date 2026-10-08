"""生成T89研究扩展；计量调度及固定公式调用接缝之外复用原代码。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t89-fast-meter-prototype-1'

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
import platform
import sys
from pathlib import Path

from Cython import __version__ as cython_version
from Cython.Build import cythonize
from setuptools import Extension, setup

from hangma_bot.policy import action_value_executor as executor
from fast_meter_source import METER_SOURCE

HERE = Path(__file__).resolve().parent
AUTHOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t75-net-upgrade-joint-author-1')
T88 = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t88-native-execution-prototype-1')
DIRECTIVES = dict(language_level=3, annotation_typing=False, infer_types=False,
                  boundscheck=True, wraparound=True, nonecheck=True,
                  cdivision=False, overflowcheck=True, binding=True)


def raw(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


class MeterCalls(ast.NodeTransformer):
    """只替换字面量零／一的计费调度；调用次序和其他原代码保持。"""
    def __init__(self):
        self.ones = 0
        self.zeros = 0

    def visit_Call(self, node):
        node = self.generic_visit(node)
        if (isinstance(node.func, ast.Attribute) and node.func.attr == 'charge'
                and isinstance(node.func.value, ast.Name) and node.func.value.id == 'meter'
                and len(node.args) == 1 and not node.keywords
                and isinstance(node.args[0], ast.Constant)
                and type(node.args[0].value) is int and node.args[0].value in (0, 1)):
            one = node.args[0].value == 1
            self.ones += one
            self.zeros += not one
            return ast.copy_location(ast.Call(
                func=ast.Attribute(value=node.func.value,
                                   attr='_charge_one' if one else '_charge_zero', ctx=ast.Load()),
                args=[], keywords=[]), node)
        return node


class PassCalls(ast.NodeTransformer):
    """固定插桩AST只把_av_pass调用改成同语义直接助手；不改评分数学。"""
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


# 先拒绝覆盖已有封存计划；每次修订必须另开目录，不能重编封存原件。
assert not (_project_file(_PROJECT_ROOT, HERE / 'BUILD-PLAN.json')).exists()
runtime_source = inspect.getsource(executor._make_runtime)
runtime_tree = ast.parse(runtime_source)
rewriter = MeterCalls()
runtime_tree = rewriter.visit(runtime_tree)
runtime_tree.body[0].name = '_make_native_runtime'
ast.fix_missing_locations(runtime_tree)
runtime_text = ast.unparse(runtime_tree)
runtime_text = runtime_text.replace('def _make_native_runtime(meter: _Meter,',
                                     'def _make_native_runtime(_Meter meter,', 1)
assert 'def _make_native_runtime(_Meter meter,' in runtime_text

names = sorted(name for name in vars(executor) if name.isidentifier()
               and not name.startswith('__') and name not in ('_Meter', '_make_runtime'))
header = 'from __future__ import annotations\nfrom ' + executor.__name__ + ' import (\n'
header += ''.join('    ' + name + ',\n' for name in names) + ')\n'
header += 'from ' + executor.__name__ + ' import _make_runtime as _compat_make_runtime\n\n'
wrapper = '''
def _make_runtime(meter, collection_cap=MAX_LOCAL_COLLECTION_SIZE):
    """精确私有原生类型才走直接计量；其他计数器沿用既有动态调用语义。"""
    if type(meter) is _Meter:
        return _make_native_runtime(meter, collection_cap)
    return _compat_make_runtime(meter, collection_cap)
'''
runtime_path = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t89-fast-meter-prototype-1/_t89_runtime.pyx')
runtime_path.write_text(header + METER_SOURCE + '\n' + runtime_text + '\n' + wrapper)

candidate_source = (_project_file(_PROJECT_ROOT, AUTHOR / 'S01-model-output/candidate.py')).read_text()
original_tree = executor.static_check(candidate_source)
instrumented = executor._Instrumentor().visit(original_tree)
ast.fix_missing_locations(instrumented)
instrumented_sha = sha(ast.dump(instrumented, include_attributes=False).encode())
pass_rewriter = PassCalls()
direct_tree = pass_rewriter.visit(instrumented)
ast.fix_missing_locations(direct_tree)
runtime_names = sorted(executor._make_runtime(executor._Meter(4800000), 8192))
top_names = []
for statement in original_tree.body:
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

candidate_text = ('from __future__ import annotations\n'
    'from _t89_runtime cimport _Meter\n'
    'from hangma_bot.policy.action_value_executor import WorkloadExceeded, MAX_STRING_CHARS\n\n'
    + pass_text + '\n\n'
    'def make_candidate(runtime, _Meter bound_meter):\n'
    '    """每执行器独占原生闭包；计量仍在原插桩位置执行。"""\n')
candidate_text += ''.join('    ' + name + ' = runtime[' + repr(name) + ']\n' for name in runtime_names)
candidate_text += ''.join('    ' + line.rstrip() + '\n' for line in ast.unparse(direct_tree).splitlines())
candidate_text += '    return {\n        "__builtins__": {},\n'
candidate_text += ''.join('        ' + repr(name) + ': ' + name + ',\n'
                         for name in runtime_names + top_names) + '    }\n'
candidate_path = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t89-fast-meter-prototype-1/_t89_candidate.pyx')
candidate_path.write_text(candidate_text)

generated = ['_t89_runtime.pyx', '_t89_runtime.pxd', '_t89_candidate.pyx']
plan = dict(schema='t89-fast-meter-build/1',
    parent_source_commit='e555c91b74d8bb4904267b9897afbf377a80e947',
    parent_native_build_sha256=sha((_project_file(_PROJECT_ROOT, T88 / 'BUILD-CLOSURE.json')).read_bytes()),
    original_executor_file_sha256=sha(Path(inspect.getfile(executor)).read_bytes()),
    original_runtime_source_sha256=sha(runtime_source.encode()),
    original_meter_source_sha256=sha(inspect.getsource(executor._Meter).encode()),
    candidate_source_sha256=sha(candidate_source.encode()),
    instrumented_ast_sha256=instrumented_sha,
    direct_call_ast_sha256=sha(ast.dump(direct_tree, include_attributes=False).encode()),
    direct_meter_literal_one_sites=rewriter.ones, direct_meter_literal_zero_sites=rewriter.zeros,
    direct_pass_static_sites=pass_rewriter.calls, directives=DIRECTIVES,
    python_version=sys.version, platform=platform.platform(), cython_version=cython_version,
    generated_sources={name: sha((_project_file(_PROJECT_ROOT, HERE / name)).read_bytes()) for name in generated},
    generator_sha256=sha(Path(__file__).read_bytes()),
    meter_source_sha256=sha((_project_file(_PROJECT_ROOT, HERE / 'fast_meter_source.py')).read_bytes()),
    candidate_authors_worlds_tables=0, production_changes=0, admission=False)
with (_project_file(_PROJECT_ROOT, HERE / 'BUILD-PLAN.json')).open('xb') as stream:
    stream.write(raw(plan) + b'\n')
extensions = [Extension(name, [str(_project_file(_PROJECT_ROOT, HERE / (name + '.pyx')))])
              for name in ('_t89_runtime', '_t89_candidate')]
setup(name='hangma-t89-fast-meter-probe',
      ext_modules=cythonize(extensions, compiler_directives=DIRECTIVES, include_path=[str(HERE)]),
      script_args=['build_ext', '--build-temp', str(_project_file(_PROJECT_ROOT, HERE / 'build/temp')),
                   '--build-lib', str(_project_file(_PROJECT_ROOT, HERE / 'build/lib'))])
closure = dict(plan_sha256=sha((_project_file(_PROJECT_ROOT, HERE / 'BUILD-PLAN.json')).read_bytes()), binaries={})
for extension in ('_t89_runtime', '_t89_candidate'):
    binary, = (_project_file(_PROJECT_ROOT, HERE / 'build/lib')).glob(extension + '*.so')
    closure['binaries'][extension] = dict(path=str(binary.relative_to(HERE)),
        bytes=binary.stat().st_size, sha256=sha(binary.read_bytes()))
with (_project_file(_PROJECT_ROOT, HERE / 'BUILD-CLOSURE.json')).open('xb') as stream:
    stream.write(raw(closure) + b'\n')
