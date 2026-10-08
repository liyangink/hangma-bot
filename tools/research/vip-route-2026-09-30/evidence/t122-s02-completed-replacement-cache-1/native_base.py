"""当前S02的显式原生研究装配；各二进制验签，每次恢复全部绑定。

T88第一方编译模块与T89计量仅作为代码实现依赖，不搬用旧候选效果。
S02自身原插桩源码另行编译，图、分数及计量必须用当前参考重新验证。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t122-s02-completed-replacement-cache-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from contextlib import contextmanager
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import sys

HERE = _project_file(_PROJECT_ROOT, Path(__file__).resolve().parent.parent / 't118-s02-native-slice-lowering-1')
T88 = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t88-native-execution-prototype-1')
T89 = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t89-fast-meter-prototype-1')
T116 = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t116-s02-completed-choice-cache-1')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


@contextmanager
def installed():
    """只对原S02 SHA装配编译闭包，其他输入保留原静态受限装载行为。"""
    from hangma_bot.policy import action_value_executor as executor
    from hangma_bot.policy import route_vip_heuristic as vip
    build = json.loads((_project_file(_PROJECT_ROOT, HERE / 'BUILD-PLAN.json')).read_text())
    closed = json.loads((_project_file(_PROJECT_ROOT, HERE / 'BUILD-CLOSURE.json')).read_text())
    old = json.loads((_project_file(_PROJECT_ROOT, T89 / 'BUILD-PLAN.json')).read_text())
    old_closed = json.loads((_project_file(_PROJECT_ROOT, T89 / 'BUILD-CLOSURE.json')).read_text())
    assert sha(_project_file(_PROJECT_ROOT, HERE / 'BUILD-PLAN.json')) == closed['plan_sha256']
    assert sha(_project_file(_PROJECT_ROOT, HERE / '_t118_candidate.pyx')) == build['generated_source_sha256']
    assert sha(_project_file(_PROJECT_ROOT, T89 / 'BUILD-CLOSURE.json')) == build['runtime_build_closure_sha256']
    assert sha(_project_file(_PROJECT_ROOT, T89 / '_t89_runtime.pxd')) == build['runtime_pxd_sha256']
    assert sha(inspect.getfile(executor)) == old['original_executor_file_sha256']
    for name, digest in old['generated_sources'].items():
        assert sha(_project_file(_PROJECT_ROOT, T89 / name)) == digest
    parent = module('t118_parent_native_overlay', _project_file(_PROJECT_ROOT, T88 / 'native_overlay.py'))
    cache = module('t118_completed_choices', _project_file(_PROJECT_ROOT, T116 / 'choice_cache.py'))
    changes, saved_sys = [], {}
    with parent.installed(native_candidate=False) as parent_identity:
        try:
            binaries = {'_t89_runtime': (T89, old_closed['binaries']['_t89_runtime']),
                        '_t118_candidate': (HERE, closed['binary'])}
            loaded = {}
            for name, (base, binding) in binaries.items():
                path = base / binding['path']
                assert path.stat().st_size == binding['bytes'] and sha(path) == binding['sha256']
                saved_sys[name] = sys.modules.get(name)
                spec = importlib.util.spec_from_file_location(name, path)
                native = importlib.util.module_from_spec(spec)
                sys.modules[name] = native
                spec.loader.exec_module(native)
                loaded[name] = native
            for name in ('_Meter', '_make_runtime'):
                before, after = getattr(executor, name), getattr(loaded['_t89_runtime'], name)
                for item in tuple(sys.modules.values()):
                    if item is None or not getattr(item, '__name__', '').startswith('hangma_bot.'):
                        continue
                    for alias, value in tuple(vars(item).items()):
                        if value is before:
                            changes.append((item, alias, before))
                            setattr(item, alias, after)
            original_init = executor.ActionValueExecutor.__init__

            def initialize(self, source, **kwargs):
                original_init(self, source, **kwargs)
                if hashlib.sha256(source.encode()).hexdigest() == build['candidate_source_sha256']:
                    namespace = loaded['_t118_candidate'].make_candidate(self._runtime, self._meter)
                    self._fn = namespace['score_actions']
                    self._namespace = namespace
                    self._module_snapshot = self._snapshot_module_bindings(namespace)

            changes.append((executor.ActionValueExecutor, '__init__', original_init))
            executor.ActionValueExecutor.__init__ = initialize
            projection = cache.make_projection(vip._Projection)
            changes.append((vip, '_Projection', vip._Projection))
            vip._Projection = projection
            identity = {'schema': 't118-s02-native-slice-execution/1',
                'base_candidate_id': build['base_candidate_identity']['candidate_id'],
                'base_candidate_source_sha256': build['candidate_source_sha256'],
                'parent_compiled_modules': parent_identity,
                'meter_binary': old_closed['binaries']['_t89_runtime'],
                'current_candidate_binary': closed['binary'],
                'build_plan_sha256': closed['plan_sha256'],
                'completed_choices_source_sha256': sha(_project_file(_PROJECT_ROOT, T116 / 'choice_cache.py')),
                'LRU_guard_overlay': False, 'new_formula': False,
                'production_changes': 0, 'admission': False}
            identity['research_execution_id'] = hashlib.sha256(canonical(identity)).hexdigest()
            yield identity
        finally:
            for item, name, before in reversed(changes):
                setattr(item, name, before)
            for name, previous in saved_sys.items():
                if previous is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = previous
            if 'projection' in locals():
                rows = [{'calls': x.calls, 'hits': x.hits, 'misses': x.misses,
                         'bypasses': x.bypasses, 'entries': len(x.completed_choices),
                         'key_seconds': x.key_seconds, 'expanded_nodes': len(x.nodes)}
                        for x in projection.instances]
                path = _project_file(_PROJECT_ROOT, Path(__file__).resolve().parent / 'actual-full-1/CACHE-STATS.json')
                if path.parent.exists():
                    with path.open('x') as stream:
                        json.dump({'rows': rows, 'bindings_restored_before_parent_exit': True},
                                  stream, sort_keys=True, indent=2)
                        stream.write('\n')
