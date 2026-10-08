"""仅为剖析重建既有五个第一方扩展；profile开销不能用作时限结论。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t125-native-internal-profile-1'

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

HERE = Path(__file__).resolve().parent
OLD = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t88-native-execution-prototype-1')
OUT = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t125-native-internal-profile-1/profile_firstparty')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')


def main():
    """逐字复用生成源码，只打开Cython函数级剖析。"""
    OUT.mkdir(exist_ok=False)
    original = json.loads((_project_file(_PROJECT_ROOT, OLD / 'BUILD-PLAN.json')).read_text())
    plan = dict(original)
    plan['schema'] = 't125-firstparty-profile-build/1'
    plan['specs'] = [item for item in original['specs']
                     if item['module'] != 'fixed-instrumented-candidate']
    assert len(plan['specs']) == 5
    for item in plan['specs']:
        module = importlib.import_module(item['module'])
        assert sha(inspect.getfile(module)) == item['original_file_sha256']
        for name, expected in item['original_selected_sha256'].items():
            assert hashlib.sha256(inspect.getsource(getattr(module, name)).encode()).hexdigest() == expected
        path = _project_file(_PROJECT_ROOT, OLD / item['generated_source'])
        assert sha(path) == item['generated_source_sha256']
        with (_project_file(_PROJECT_ROOT, OUT / path.name)).open('xb') as stream:
            stream.write(path.read_bytes())
    with (_project_file(_PROJECT_ROOT, OUT / 'native_overlay.py')).open('xb') as stream:
        stream.write((_project_file(_PROJECT_ROOT, OLD / 'native_overlay.py')).read_bytes())
    directives = dict(original['directives'], profile=True)
    plan.update(directives=directives, cython_version=cython_version,
        platform=platform.platform(), python_version=sys.version,
        generator_sha256=sha(Path(__file__)),
        original_plan_sha256=sha(_project_file(_PROJECT_ROOT, OLD / 'BUILD-PLAN.json')),
        profiled_time_is_not_deadline_evidence=True,
        actual_rules_choose_scoring_worlds_tables=0)
    save(_project_file(_PROJECT_ROOT, OUT / 'BUILD-PLAN.json'), plan)
    extensions = [Extension(item['extension'], [str(_project_file(_PROJECT_ROOT, OUT / item['generated_source']))])
                  for item in plan['specs']]
    setup(name='hangma-t125-internal-profile',
        ext_modules=cythonize(extensions, compiler_directives=directives),
        script_args=['build_ext', '--build-temp', str(_project_file(_PROJECT_ROOT, OUT / 'build/temp')),
                     '--build-lib', str(_project_file(_PROJECT_ROOT, OUT / 'build/lib'))])
    closed = {'plan': sha(_project_file(_PROJECT_ROOT, OUT / 'BUILD-PLAN.json')), 'binaries': {}}
    for item in plan['specs']:
        binary, = (_project_file(_PROJECT_ROOT, OUT / 'build/lib')).glob(item['extension'] + '*.so')
        closed['binaries'][item['extension']] = {'path': str(binary.relative_to(OUT)),
            'bytes': binary.stat().st_size, 'sha256': sha(binary)}
    save(_project_file(_PROJECT_ROOT, OUT / 'BUILD-CLOSURE.json'), closed)


if __name__ == '__main__':
    main()
