"""研究绑定原生机械函数，原类型与构造器仍负责全部字段校验。"""

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
import dataclasses
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import sys
import textwrap

HERE=Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_native():
    """校验实际构建和原函数体，既有扩展绑定不影响源文件的验证。"""
    from hangma_bot.hangma import route_transition,public_tile_counts
    plan=json.loads((_project_file(_PROJECT_ROOT, HERE/'BUILD-PLAN.json')).read_text())
    closure=json.loads((_project_file(_PROJECT_ROOT, HERE/'BUILD-CLOSURE.json')).read_text())
    assert sha(_project_file(_PROJECT_ROOT, HERE/'BUILD-PLAN.json'))==closure['plan_sha256']
    assert sha(_project_file(_PROJECT_ROOT, HERE/'_t124_mechanical.pyx'))==plan['generated_source_sha256']
    objects={'replace':dataclasses.replace,
        'conditional_identity_post_init':route_transition.ConditionalIdentity.__post_init__,
        'conditional_state_post_init':route_transition.ConditionalRouteState.__post_init__,
        'public_view_post_init':public_tile_counts.PublicTileView.__post_init__}
    for spec in plan['specs']:
        original=objects[spec['native_name']]
        assert sha(inspect.getfile(original))==spec['original_file_sha256']
        assert hashlib.sha256(textwrap.dedent(inspect.getsource(original)).encode()).hexdigest()==spec['original_source_sha256']
    binding=closure['binary'];path=_project_file(_PROJECT_ROOT, HERE/binding['path'])
    assert path.stat().st_size==binding['bytes'] and sha(path)==binding['sha256']
    spec=importlib.util.spec_from_file_location('_t124_mechanical',path)
    native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
    identity={'schema':'t124-native-mechanical-binding/1',
        'plan_sha256':closure['plan_sha256'],'native_binary':binding,
        'overlay_sha256':sha(Path(__file__)),
        'original_dataclass_types_preserved':True,'post_validation_not_removed':True,
        'stdlib_dataclasses_module_not_modified':True,'new_formula':False,
        'production_changes':0,'admission':False}
    return native,identity


@contextmanager
def installed():
    """仅重绑定已导入第一方/研究模块别名；公共标准库保持原对象。"""
    from hangma_bot.hangma import route_transition,public_tile_counts
    native,identity=load_native();changes=[]
    try:
        # 已编译转移模块持有自己的global别名，按对象身份一并绑定。
        for module in tuple(sys.modules.values()):
            name='' if module is None else getattr(module,'__name__','')
            if not name.startswith(('hangma_bot.','_t88_','_t89_','_t118_')):continue
            for alias,value in tuple(vars(module).items()):
                if value is dataclasses.replace:
                    changes.append((module,alias,value));setattr(module,alias,native.replace)
        for cls,name in [(route_transition.ConditionalIdentity,'conditional_identity_post_init'),
            (route_transition.ConditionalRouteState,'conditional_state_post_init'),
            (public_tile_counts.PublicTileView,'public_view_post_init')]:
            changes.append((cls,'__post_init__',cls.__post_init__))
            setattr(cls,'__post_init__',getattr(native,name))
        identity['replace_alias_count']=sum(name!='__post_init__' for _,name,_ in changes)
        yield identity
    finally:
        for obj,name,original in reversed(changes):setattr(obj,name,original)
