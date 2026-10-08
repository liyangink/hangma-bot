"""从当前第一方原代码生成隔离研究扩展；不编辑生产源或删除规则分支。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t88-native-execution-prototype-1'

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

from hangma_bot.hangma import public_tile_counts, route_transition
from hangma_bot.policy import action_value_executor, route_heuristic_view, route_vip_heuristic

HERE = Path(__file__).resolve().parent
AUTHOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t75-net-upgrade-joint-author-1')
T84 = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t84-public-shape-dispatch-1')
DIRECTIVES = dict(language_level=3, annotation_typing=False, infer_types=False,
                  boundscheck=True, wraparound=True, nonecheck=True,
                  cdivision=False, overflowcheck=True, binding=True)


def raw(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def sha(content):
    return hashlib.sha256(content).hexdigest()


def generate(module, selected, name):
    """逐字保存函数/私有类源；公共值对象及未知依赖继续引用原模块。"""
    names = sorted(key for key in vars(module) if key.isidentifier()
                   and not key.startswith('__') and key not in selected)
    header = 'from __future__ import annotations\nfrom ' + module.__name__ + ' import (\n'
    header += ''.join('    ' + key + ',\n' for key in names) + ')\n\n'
    copies = {key: inspect.getsource(getattr(module, key)) for key in selected}
    content = header + '\n\n'.join(copies.values()) + '\n'
    path = _project_file(_PROJECT_ROOT, HERE / (name + '.pyx'))
    path.write_text(content)
    return dict(module=module.__name__, extension=name, selected=selected,
                original_file_sha256=sha(Path(inspect.getfile(module)).read_bytes()),
                original_selected_sha256={key: sha(source.encode()) for key, source in copies.items()},
                generated_source=path.name, generated_source_sha256=sha(content.encode()))


transition_functions = [name for name, value in vars(route_transition).items()
                        if inspect.isfunction(value) and value.__module__ == route_transition.__name__]
specs = [
    generate(public_tile_counts, ['_PublicInputGuard', '_conservation_excess', '_claim_proofs',
             '_scan_claim_proofs', '_pending_proof', '_is_inherited_claim', '_claim_token',
             '_claim_vote', '_compute_public_tiles_from_view', '_count_unseen_tiles_from_view'],
             '_t88_counts'),
    generate(route_transition, transition_functions, '_t88_transition'),
    generate(route_heuristic_view, ['_plain'], '_t88_plain'),
    generate(action_value_executor, ['_structure_children', '_unknown_structure_units',
             '_walk_structure', 'structure_cost', 'charge_structure', '_Meter', '_make_runtime'],
             '_t88_executor'),
    generate(route_vip_heuristic, ['_Projection'], '_t88_projection'),
]

candidate_source = (_project_file(_PROJECT_ROOT, AUTHOR / 'S01-model-output/candidate.py')).read_text()
tree = action_value_executor.static_check(candidate_source)
instrumented = action_value_executor._Instrumentor().visit(tree)
ast.fix_missing_locations(instrumented)
runtime_names = sorted(action_value_executor._make_runtime(action_value_executor._Meter(4800000), 8192))
assert all(name.isidentifier() for name in runtime_names)
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

factory = 'def make_candidate(runtime):\n'
factory += '    """每次装载生成独占闭包；不把可变runtime或meter放在模块全局。"""\n'
factory += ''.join('    ' + name + ' = runtime[' + repr(name) + ']\n' for name in runtime_names)
factory += ''.join('    ' + line + '\n' for line in ast.unparse(instrumented).splitlines())
factory += '    return {\n        "__builtins__": {},\n'
factory += ''.join('        ' + repr(name) + ': ' + name + ',\n'
                   for name in runtime_names + top_names) + '    }\n'
candidate_path = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t88-native-execution-prototype-1/_t88_candidate.pyx')
candidate_path.write_text(factory)
specs.append(dict(module='fixed-instrumented-candidate', extension='_t88_candidate', selected=[],
                  candidate_source_sha256=sha(candidate_source.encode()),
                  instrumented_ast_sha256=sha(ast.dump(instrumented, include_attributes=False).encode()),
                  runtime_names=runtime_names, top_names=top_names,
                  generated_source=candidate_path.name, generated_source_sha256=sha(factory.encode())))

plan = dict(schema='t88-native-build/1', parent_source_commit='e555c91b74d8bb4904267b9897afbf377a80e947',
            reference_python_identity=json.loads((_project_file(_PROJECT_ROOT, T84 / 'PLAN.json')).read_text())['parent_runtime_identity'],
            directives=DIRECTIVES, cython_version=cython_version, platform=platform.platform(),
            python_version=sys.version, specs=specs, new_candidate_formulas=0, production_changes=0,
            admission=False, actual_rules_choose_scoring_worlds_tables=0)
with (_project_file(_PROJECT_ROOT, HERE / 'BUILD-PLAN.json')).open('xb') as stream:
    stream.write(raw(plan) + b'\n')
extensions = [Extension(spec['extension'], [str(_project_file(_PROJECT_ROOT, HERE / spec['generated_source']))]) for spec in specs]
setup(name='hangma-t88-native-probe', ext_modules=cythonize(extensions, compiler_directives=DIRECTIVES),
      script_args=['build_ext', '--build-temp', str(_project_file(_PROJECT_ROOT, HERE / 'build/temp')),
                   '--build-lib', str(_project_file(_PROJECT_ROOT, HERE / 'build/lib'))])
manifest = dict(plan=sha((_project_file(_PROJECT_ROOT, HERE / 'BUILD-PLAN.json')).read_bytes()), binaries={})
for spec in specs:
    binary, = (_project_file(_PROJECT_ROOT, HERE / 'build/lib')).glob(spec['extension'] + '*.so')
    manifest['binaries'][spec['extension']] = dict(path=str(binary.relative_to(HERE)),
                         bytes=binary.stat().st_size, sha256=sha(binary.read_bytes()))
with (_project_file(_PROJECT_ROOT, HERE / 'BUILD-CLOSURE.json')).open('xb') as stream:
    stream.write(raw(manifest) + b'\n')
