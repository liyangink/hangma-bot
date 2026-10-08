"""当前S02原生执行加有界完整录制；研究装配不授全域或官方发布。"""

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
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def load(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@contextmanager
def installed():
    """先恢复编码与原生绑定，再独立保存实际次数；首次输出不覆盖。"""
    base=load('t120_native_base',_project_file(_PROJECT_ROOT, HERE/'native_base.py'))
    codec=load('t120_native_codec',_project_file(_PROJECT_ROOT, HERE/'codec_overlay.py'))
    with base.installed() as parent:
        with codec.installed() as (capture, stats):
            identity={'schema':'t120-bounded-native-full-execution/1',
                'base_candidate_id':parent['base_candidate_id'],
                'base_candidate_source_sha256':parent['base_candidate_source_sha256'],
                'parent_native_execution':parent, 'complete_capture_execution':capture,
                'native_base_sha256':sha(_project_file(_PROJECT_ROOT, HERE/'native_base.py')),
                'overlay_sha256':sha(Path(__file__)),
                'new_formula':False,'production_changes':0,'admission':False}
            raw=json.dumps(identity,ensure_ascii=False,sort_keys=True,
                separators=(',',':'),allow_nan=False).encode()
            identity['research_execution_id']=hashlib.sha256(raw).hexdigest()
            yield identity
    path=_project_file(_PROJECT_ROOT, HERE/'actual-full-1/CODEC-STATS.json')
    if path.parent.exists():
        with path.open('x') as stream:
            json.dump(stats,stream,sort_keys=True,indent=2);stream.write('\n')
