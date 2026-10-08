"""T89显式离线装配；先验证原件，每次恢复绑定，不改生产组合根。"""

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
import hashlib
import importlib.util
import inspect
import json
import sys
from contextlib import contextmanager
from pathlib import Path

from hangma_bot.policy import action_value_executor as executor

HERE = Path(__file__).resolve().parent
T88 = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t88-native-execution-prototype-1')


def raw(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@contextmanager
def installed(*, direct_pass=True):
    """固定T75使用独占原生计量；零／一直接调用，其他候选仍原插桩源码。"""
    plan = json.loads((_project_file(_PROJECT_ROOT, HERE / 'BUILD-PLAN.json')).read_text())
    closure = json.loads((_project_file(_PROJECT_ROOT, HERE / 'BUILD-CLOSURE.json')).read_text())
    assert hashlib.sha256((_project_file(_PROJECT_ROOT, HERE / 'BUILD-PLAN.json')).read_bytes()).hexdigest() == closure['plan_sha256']
    assert hashlib.sha256((_project_file(_PROJECT_ROOT, T88 / 'BUILD-CLOSURE.json')).read_bytes()).hexdigest() == plan['parent_native_build_sha256']
    assert hashlib.sha256(Path(inspect.getfile(executor)).read_bytes()).hexdigest() == plan['original_executor_file_sha256']
    assert hashlib.sha256(inspect.getsource(executor._make_runtime).encode()).hexdigest() == plan['original_runtime_source_sha256']
    assert hashlib.sha256(inspect.getsource(executor._Meter).encode()).hexdigest() == plan['original_meter_source_sha256']
    for name, digest in plan['generated_sources'].items():
        assert hashlib.sha256((_project_file(_PROJECT_ROOT, HERE / name)).read_bytes()).hexdigest() == digest
    native = module('t89_parent_overlay', _project_file(_PROJECT_ROOT, T88 / 'native_overlay.py'))
    changes = []
    saved_sys = {}
    with native.installed(native_candidate=False) as parent:
        try:
            loaded = {}
            # cimport扩展须先有_runtime；不依赖JSON键排序决定载入顺序。
            for extension in ('_t89_runtime', '_t89_candidate'):
                binding = closure['binaries'][extension]
                binary = _project_file(_PROJECT_ROOT, HERE / binding['path'])
                assert binary.stat().st_size == binding['bytes']
                assert hashlib.sha256(binary.read_bytes()).hexdigest() == binding['sha256']
                saved_sys[extension] = sys.modules.get(extension)
                spec = importlib.util.spec_from_file_location(extension, binary)
                result = importlib.util.module_from_spec(spec)
                sys.modules[extension] = result
                spec.loader.exec_module(result)
                loaded[extension] = result
            for name in ('_Meter', '_make_runtime'):
                before = getattr(executor, name)
                after = getattr(loaded['_t89_runtime'], name)
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
                if hashlib.sha256(source.encode()).hexdigest() == plan['candidate_source_sha256']:
                    if direct_pass:
                        namespace = loaded['_t89_candidate'].make_candidate(self._runtime, self._meter)
                    else:
                        namespace = sys.modules['_t88_candidate'].make_candidate(self._runtime)
                    self._fn = namespace['score_actions']
                    self._namespace = namespace
                    self._module_snapshot = self._snapshot_module_bindings(namespace)

            changes.append((executor.ActionValueExecutor, '__init__', original_init))
            executor.ActionValueExecutor.__init__ = initialize
            identity = dict(schema='t89-fast-meter-execution/1', parent=parent,
                build_plan_sha256=closure['plan_sha256'], binaries=closure['binaries'],
                direct_pass=direct_pass, scope='fixed T75 and research runtime; not production admission',
                production_changes=0, admission=False)
            identity['research_execution_id'] = hashlib.sha256(raw(identity)).hexdigest()
            yield identity
        finally:
            for item, name, original in reversed(changes):
                setattr(item, name, original)
            for name, previous in saved_sys.items():
                if previous is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = previous
