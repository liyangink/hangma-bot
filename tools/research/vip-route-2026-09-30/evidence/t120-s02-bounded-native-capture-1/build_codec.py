"""只构建隔离的编码扩展；保存参数、源摘要和实际二进制，不改生产模块。"""

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
import hashlib
import json
from pathlib import Path
import platform
import sys

from Cython import __version__ as cython_version
from Cython.Build import cythonize
from setuptools import Extension, setup

HERE = Path(__file__).resolve().parent
RUNTIME = Path('/Users/liyang/.codex/worktrees/t54-public-count-cache/hangma-bot')
SOURCE = _project_file(_PROJECT_ROOT, RUNTIME / 'src/hangma_bot/offline/scoring_input_capture.py')
DIRECTIVES = dict(language_level=3, annotation_typing=False, infer_types=False,
    boundscheck=True, wraparound=True, nonecheck=True, cdivision=False,
    overflowcheck=True, binding=True)


def raw(value):
    """构建收据使用严格规范JSON，首次文件禁止覆盖。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


assert not (_project_file(_PROJECT_ROOT, HERE / 'BUILD-PLAN.json')).exists()
assert sha(SOURCE) == '858c75e621ecf23913b8df0af58af197301e780b1f48c9d4304fe13ad0712e85'
plan = {'schema': 't120-bounded-native-json-build/1',
    'original_capture_source_sha256': sha(SOURCE),
    'prototype_source_sha256': sha(_project_file(_PROJECT_ROOT, HERE / '_t120_codec.pyx')),
    'builder_sha256': sha(Path(__file__)), 'directives': DIRECTIVES,
    'cython_version': cython_version, 'platform': platform.platform(),
    'python_version': sys.version, 'max_fast_json_bytes': 64 * 1024 * 1024,
    'max_fast_depth': 128, 'actual_rule_choose_score_world_table_calls': 0,
    'production_changes': 0, 'admission': False}
with (_project_file(_PROJECT_ROOT, HERE / 'BUILD-PLAN.json')).open('xb') as stream:
    stream.write(raw(plan) + b'\n')
setup(name='hangma-t120-bounded-json-probe',
    ext_modules=cythonize([Extension('_t120_codec', [str(_project_file(_PROJECT_ROOT, HERE / '_t120_codec.pyx'))])],
        compiler_directives=DIRECTIVES),
    script_args=['build_ext', '--build-temp', str(_project_file(_PROJECT_ROOT, HERE / 'build/temp')),
        '--build-lib', str(_project_file(_PROJECT_ROOT, HERE / 'build/lib'))])
binary, = (_project_file(_PROJECT_ROOT, HERE / 'build/lib')).glob('_t120_codec*.so')
with (_project_file(_PROJECT_ROOT, HERE / 'BUILD-CLOSURE.json')).open('xb') as stream:
    stream.write(raw({'plan_sha256': sha(_project_file(_PROJECT_ROOT, HERE / 'BUILD-PLAN.json')),
        'binary': {'path': str(binary.relative_to(HERE)),
            'bytes': binary.stat().st_size, 'sha256': sha(binary)},
        'actual_rule_choose_score_world_table_calls': 0}) + b'\n')
