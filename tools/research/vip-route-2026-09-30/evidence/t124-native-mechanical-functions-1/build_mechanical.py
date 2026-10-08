"""逐字拷贝已有机械函数体为隔离原生函数，不改值类型或规则分支。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t124-native-mechanical-functions-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import ast
import dataclasses
import hashlib
import inspect
import json
from pathlib import Path
import platform
import sys
import textwrap

RUNTIME=Path('/Users/liyang/.codex/worktrees/t54-public-count-cache/hangma-bot')
sys.path[:0]=[str(RUNTIME),str(_project_file(_PROJECT_ROOT, RUNTIME/'src'))]
from Cython import __version__ as cython_version
from Cython.Build import cythonize
from setuptools import Extension,setup
from hangma_bot.hangma import public_tile_counts,route_transition

HERE=Path(__file__).resolve().parent
DIRECTIVES=dict(language_level=3,annotation_typing=False,infer_types=False,
    boundscheck=True,wraparound=True,nonecheck=True,cdivision=False,
    overflowcheck=True,binding=True)


def raw(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,
        separators=(',',':'),allow_nan=False).encode()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


assert not (_project_file(_PROJECT_ROOT, HERE/'BUILD-PLAN.json')).exists()
assert not (_project_file(_PROJECT_ROOT, HERE/'_t124_mechanical.pyx')).exists()
targets=[(dataclasses.replace,'replace'),
    (route_transition.ConditionalIdentity.__post_init__,'conditional_identity_post_init'),
    (route_transition.ConditionalRouteState.__post_init__,'conditional_state_post_init'),
    (public_tile_counts.PublicTileView.__post_init__,'public_view_post_init')]
specs=[];functions=[]
for original,name in targets:
    source=textwrap.dedent(inspect.getsource(original))
    renamed=source.replace('def '+original.__name__+'(', 'def '+name+'(',1)
    before,after=ast.parse(source),ast.parse(renamed)
    before.body[0].name=after.body[0].name
    assert ast.dump(before,include_attributes=False)==ast.dump(after,include_attributes=False)
    functions.append(renamed)
    specs.append({'original_module':original.__module__,
        'original_qualname':original.__qualname__,'native_name':name,
        'original_file':inspect.getfile(original),'original_file_sha256':sha(inspect.getfile(original)),
        'original_source_sha256':hashlib.sha256(source.encode()).hexdigest(),
        'native_source_sha256':hashlib.sha256(renamed.encode()).hexdigest(),
        'same_ast_except_function_name':True})
header='''"""冻结机械函数原生执行；所有构造器校验与错误分支保持原函数体。"""
from __future__ import annotations
from dataclasses import (_is_dataclass_instance, _FIELDS, _FIELD_CLASSVAR,
                         _FIELD_INITVAR, MISSING)
from hangma_bot.hangma.route_transition import ConditionalPhase

'''
content=header+'\n\n'.join(functions)+'\n'
with (_project_file(_PROJECT_ROOT, HERE/'_t124_mechanical.pyx')).open('x') as stream:stream.write(content)
plan={'schema':'t124-native-mechanical-functions-build/1','specs':specs,
    'directives':DIRECTIVES,'cython_version':cython_version,'python_version':sys.version,
    'platform':platform.platform(),'builder_sha256':sha(Path(__file__)),
    'generated_source_sha256':sha(_project_file(_PROJECT_ROOT, HERE/'_t124_mechanical.pyx')),
    'original_types_and_post_validation_preserved':True,
    'new_formula':False,'production_changes':0,'admission':False,
    'actual_rule_choose_score_world_table_calls':0}
with (_project_file(_PROJECT_ROOT, HERE/'BUILD-PLAN.json')).open('xb') as stream:stream.write(raw(plan)+b'\n')
setup(name='hangma-t124-native-mechanical',
    ext_modules=cythonize([Extension('_t124_mechanical',[str(_project_file(_PROJECT_ROOT, HERE/'_t124_mechanical.pyx'))])],
        compiler_directives=DIRECTIVES),
    script_args=['build_ext','--build-temp',str(_project_file(_PROJECT_ROOT, HERE/'build/temp')),'--build-lib',str(_project_file(_PROJECT_ROOT, HERE/'build/lib'))])
binary,=(_project_file(_PROJECT_ROOT, HERE/'build/lib')).glob('_t124_mechanical*.so')
with (_project_file(_PROJECT_ROOT, HERE/'BUILD-CLOSURE.json')).open('xb') as stream:
    stream.write(raw({'plan_sha256':sha(_project_file(_PROJECT_ROOT, HERE/'BUILD-PLAN.json')),
        'binary':{'path':str(binary.relative_to(HERE)),'bytes':binary.stat().st_size,'sha256':sha(binary)},
        'actual_rule_choose_score_world_table_calls':0})+b'\n')
