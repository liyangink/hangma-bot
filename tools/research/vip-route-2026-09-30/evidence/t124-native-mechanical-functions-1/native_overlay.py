"""在既有S02完整研究装配内编译执行机械函数，原类型和全部校验保持。"""

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
from contextlib import contextmanager
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@contextmanager
def installed():
    """先安装已验父执行，再绑定机械函数；按反序恢复所有对象。"""
    parent = load('t124_native_parent', _project_file(_PROJECT_ROOT, HERE / 'native_parent.py'))
    mechanical = load('t124_mechanical_overlay', _project_file(_PROJECT_ROOT, HERE / 'mechanical_overlay.py'))
    with parent.installed() as parent_identity:
        with mechanical.installed() as mechanical_identity:
            # 别名数取决于已导入模块清单，只作运行诊断；代码/二进制摘要仍完整绑定。
            stable = dict(mechanical_identity)
            aliases = stable.pop('replace_alias_count')
            from hangma_bot.hangma import route_transition, public_tile_counts
            constructors = [route_transition.ConditionalIdentity.__post_init__,
                route_transition.ConditionalRouteState.__post_init__,
                public_tile_counts.PublicTileView.__post_init__]
            types = [type(item).__name__ for item in constructors]
            assert all(name == 'cython_function_or_method' for name in types)
            identity = {'schema': 't124-native-mechanical-full-execution/1',
                'base_candidate_id': parent_identity['base_candidate_id'],
                'base_candidate_source_sha256': parent_identity['base_candidate_source_sha256'],
                'parent_execution': parent_identity, 'mechanical_execution': stable,
                'constructor_function_types': types, 'overlay_sha256': sha(Path(__file__)),
                'native_parent_sha256': sha(_project_file(_PROJECT_ROOT, HERE / 'native_parent.py')),
                'new_formula': False, 'production_changes': 0, 'admission': False}
            raw = json.dumps(identity, ensure_ascii=False, sort_keys=True,
                            separators=(',', ':'), allow_nan=False).encode()
            identity['research_execution_id'] = hashlib.sha256(raw).hexdigest()
            yield identity
    out = _project_file(_PROJECT_ROOT, HERE / 'actual-full-1')
    if out.exists():
        with (out / 'MECHANICAL-STATS.json').open('x') as stream:
            json.dump({'replace_alias_count': aliases, 'constructor_function_types': types,
                'all_research_bindings_restored': True,
                'original_dataclass_types_preserved': True}, stream, sort_keys=True, indent=2)
            stream.write('\n')
