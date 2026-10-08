"""T88显式研究组合根，逐次安装／恢复；不进入正式生产装配。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t125-native-internal-profile-1/profile_firstparty'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import hashlib
import importlib
import importlib.util
import inspect
import json
import sys
from contextlib import contextmanager
from pathlib import Path

from hangma_bot.policy import action_value_executor as executor

HERE = Path(__file__).resolve().parent


def raw(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


@contextmanager
def installed(*, native_candidate=True):
    """只替换本进程绑定；公共值类型不改，所有原始绑定在finally恢复。"""
    plan = json.loads((_project_file(_PROJECT_ROOT, HERE / 'BUILD-PLAN.json')).read_text())
    closure = json.loads((_project_file(_PROJECT_ROOT, HERE / 'BUILD-CLOSURE.json')).read_text())
    assert hashlib.sha256((_project_file(_PROJECT_ROOT, HERE / 'BUILD-PLAN.json')).read_bytes()).hexdigest() == closure['plan']
    modules = [importlib.import_module(spec['module']) for spec in plan['specs']
               if spec['module'] != 'fixed-instrumented-candidate']
    # 首先验证全部原件，避免前一个覆盖影响后一个模块的source读取。
    for spec, original in zip(plan['specs'], modules):
        assert hashlib.sha256(Path(inspect.getfile(original)).read_bytes()).hexdigest() == spec['original_file_sha256']
        for name, digest in spec['original_selected_sha256'].items():
            assert hashlib.sha256(inspect.getsource(getattr(original, name)).encode()).hexdigest() == digest
    changes = []
    saved_sys = {}
    loaded = {}
    try:
        for item in plan['specs']:
            extension = item['extension']
            generated = _project_file(_PROJECT_ROOT, HERE / item['generated_source'])
            assert hashlib.sha256(generated.read_bytes()).hexdigest() == item['generated_source_sha256']
            binding = closure['binaries'][extension]
            binary = _project_file(_PROJECT_ROOT, HERE / binding['path'])
            assert binary.stat().st_size == binding['bytes']
            assert hashlib.sha256(binary.read_bytes()).hexdigest() == binding['sha256']
            saved_sys[extension] = sys.modules.get(extension)
            spec = importlib.util.spec_from_file_location(extension, binary)
            native = importlib.util.module_from_spec(spec)
            sys.modules[extension] = native
            spec.loader.exec_module(native)
            loaded[extension] = native
            if item['module'] == 'fixed-instrumented-candidate':
                continue
            original = importlib.import_module(item['module'])
            for name in item['selected']:
                before = getattr(original, name)
                after = getattr(native, name)
                # 所有已导入的第一方别名按对象身份重绑定，避免一部分路径仍走旧函数。
                for module in tuple(sys.modules.values()):
                    if module is None or not getattr(module, '__name__', '').startswith('hangma_bot.'):
                        continue
                    for alias, value in tuple(vars(module).items()):
                        if value is before:
                            changes.append((module, alias, before))
                            setattr(module, alias, after)
        candidate_spec = plan['specs'][-1]
        if native_candidate:
            original_init = executor.ActionValueExecutor.__init__

            def initialize(self, source, **kwargs):
                original_init(self, source, **kwargs)
                if hashlib.sha256(source.encode()).hexdigest() == candidate_spec['candidate_source_sha256']:
                    namespace = loaded['_t88_candidate'].make_candidate(self._runtime)
                    self._fn = namespace['score_actions']
                    self._namespace = namespace
                    self._module_snapshot = self._snapshot_module_bindings(namespace)

            changes.append((executor.ActionValueExecutor, '__init__', original_init))
            executor.ActionValueExecutor.__init__ = initialize
        identity = dict(schema='t88-native-execution/1', build_plan=closure['plan'],
                        binaries=closure['binaries'], python_parent=plan['reference_python_identity'],
                        native_candidate=native_candidate, scope='research-only explicit process bindings',
                        production_changes=0, admission=False)
        identity['research_execution_id'] = hashlib.sha256(raw(identity)).hexdigest()
        yield identity
    finally:
        for module, name, before in reversed(changes):
            setattr(module, name, before)
        for name, previous in saved_sys.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
