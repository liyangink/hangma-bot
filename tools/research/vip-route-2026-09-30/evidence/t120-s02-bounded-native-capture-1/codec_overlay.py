"""离线录制器的显式研究装配；退出即恢复原编码器，生产文件不改写。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t120-s02-bounded-native-capture-1'

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

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_native():
    """核验构建源与ABI二进制后装载，不执行规则、评分或写入。"""
    from hangma_bot.offline import scoring_input_capture as capture
    plan = json.loads((_project_file(_PROJECT_ROOT, HERE / 'BUILD-PLAN.json')).read_text())
    closure = json.loads((_project_file(_PROJECT_ROOT, HERE / 'BUILD-CLOSURE.json')).read_text())
    assert sha(_project_file(_PROJECT_ROOT, HERE / 'BUILD-PLAN.json')) == closure['plan_sha256']
    assert sha(_project_file(_PROJECT_ROOT, HERE / '_t120_codec.pyx')) == plan['prototype_source_sha256']
    assert sha(inspect.getfile(capture)) == plan['original_capture_source_sha256']
    binary = closure['binary']
    path = _project_file(_PROJECT_ROOT, HERE / binary['path'])
    assert path.stat().st_size == binary['bytes'] and sha(path) == binary['sha256']
    spec = importlib.util.spec_from_file_location('_t120_codec', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, {'schema': 't120-bounded-full-capture/1',
        'build_plan_sha256': closure['plan_sha256'], 'native_binary': binary,
        'original_capture_source_sha256': plan['original_capture_source_sha256'],
        'codec_overlay_sha256': sha(Path(__file__)),
        'max_fast_json_bytes': plan['max_fast_json_bytes'],
        'max_fast_depth': plan['max_fast_depth'],
        'complete_bytes_and_limits_preserved': True,
        'new_formula': False, 'production_changes': 0, 'admission': False}


@contextmanager
def installed():
    """记录快路径与原路径次数；异常不改为成功，恢复先于退出。"""
    from hangma_bot.offline import scoring_input_capture as capture
    module, identity = load_native()
    original = capture._encode
    stats = {'calls': 0, 'fast_successes': 0, 'original_successes': 0,
        'failed_calls': 0, 'normalization_or_truncation': False}

    def encode(value, ceiling):
        stats['calls'] += 1
        try:
            raw, fast = module.bounded_encode(value, ceiling, original)
        except BaseException:
            stats['failed_calls'] += 1
            raise
        stats['fast_successes' if fast else 'original_successes'] += 1
        return raw

    capture._encode = encode
    try:
        yield identity, stats
    finally:
        capture._encode = original
        stats['original_binding_restored'] = capture._encode is original
