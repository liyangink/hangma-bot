"""当前S02原生及完整编码，加完成杠补子图引用复用的研究装配。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t129-s02-grouped-optimization-1'

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
T120=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t120-s02-bounded-native-capture-1')
T122=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t122-s02-completed-replacement-cache-1')


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@contextmanager
def installed():
    """完成引用复用不允许跨选择共享；恢复原类后保存诊断。"""
    from hangma_bot.policy import route_vip_heuristic as vip
    base=load('t122_native_base',_project_file(_PROJECT_ROOT, HERE/'native_base.py'))
    codec=load('t122_native_codec',_project_file(_PROJECT_ROOT, T120/'codec_overlay.py'))
    cache=load('t123_completed_replacement',_project_file(_PROJECT_ROOT, T122/'replacement_cache.py'))
    with base.installed() as parent:
        with codec.installed() as (capture,codec_stats):
            original=vip._Projection
            projection=cache.make_projection(original)
            vip._Projection=projection
            try:
                identity={'schema':'t123-optimized-full-panel-native-execution/1',
                    'base_candidate_id':parent['base_candidate_id'],
                    'base_candidate_source_sha256':parent['base_candidate_source_sha256'],
                    'parent_native_execution':parent,'complete_capture_execution':capture,
                    'native_base_sha256':sha(_project_file(_PROJECT_ROOT, HERE/'native_base.py')),
                    'replacement_overlay_sha256':sha(_project_file(_PROJECT_ROOT, T122/'replacement_cache.py')),
                    'root_identity_retained':True,'public_meld_order_retained':True,
                    'overlay_sha256':sha(Path(__file__)),
                    'new_formula':False,'production_changes':0,'admission':False}
                raw=json.dumps(identity,ensure_ascii=False,sort_keys=True,
                    separators=(',',':'),allow_nan=False).encode()
                identity['research_execution_id']=hashlib.sha256(raw).hexdigest()
                yield identity
            finally:
                vip._Projection=original
                rows=[{'calls':item.replacement_calls,'hits':item.replacement_hits,
                    'misses':item.replacement_misses,'bypasses':item.replacement_bypasses,
                    'entries':len(item.completed_replacements),'max_entries':item.limits.max_nodes}
                    for item in projection.instances]
    path=_project_file(_PROJECT_ROOT, HERE/'actual-full-1/REPLACEMENT-STATS.json')
    if path.parent.exists():
        with path.open('x') as stream:
            json.dump({'replacement_scopes':rows,'codec':codec_stats,
                'original_bindings_restored':True},stream,sort_keys=True,indent=2);stream.write('\n')
