"""研究组合根的显式临时覆盖；不安装导入钩子，不修改生产源码。

读取已生成二进制与计划组成独立研究执行身份。只在调用进程内替换工厂，
上下文退出时恢复；原Python候选准入身份不能冒充此编译后端身份。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t84-public-shape-dispatch-1'

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
import platform
import sys
from contextlib import contextmanager
from pathlib import Path

from hangma_bot.policy import action_value_executor as executor

HERE = Path(__file__).resolve().parent


def _raw(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


@contextmanager
def installed():
    """装载唯一编译产物并返回身份；结束后恢复本进程原工厂。"""
    plan = json.loads((_project_file(_PROJECT_ROOT, HERE / 'PLAN.json')).read_text())
    original = executor._make_runtime
    assert hashlib.sha256(inspect.getsource(original).encode()).hexdigest() == plan['runtime_factory_sha256']
    binaries = list((_project_file(_PROJECT_ROOT, HERE / 'build/lib')).glob('_t82_runtime*.so'))
    assert len(binaries) == 1
    binary = binaries[0]
    spec = importlib.util.spec_from_file_location('_t82_runtime', binary)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hashlib.sha256((_project_file(_PROJECT_ROOT, HERE / '_t82_runtime.pyx')).read_bytes()).hexdigest() == plan['generated_source_sha256']
    manifest = {'scope':'research-only explicit compiled factory, no old admission inheritance',
                'parent_runtime_identity':plan['parent_runtime_identity'],
                'compiled_source_sha256':plan['generated_source_sha256'],
                'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
                'binary_bytes':binary.stat().st_size,'compiler_version':'3.3.0',
                'compiler_directives':plan['compiler_directives'],
                'python_version':sys.version,'platform':platform.platform()}
    manifest['research_execution_id'] = hashlib.sha256(_raw(manifest)).hexdigest()
    executor._make_runtime = module._make_runtime
    try:
        yield manifest
    finally:
        executor._make_runtime = original
