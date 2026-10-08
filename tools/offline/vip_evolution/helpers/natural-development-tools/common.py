"""T199固定8母×四换座的单臂诊断；只复用已冻结P0和精确信息说明helper。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = '.private/t199-four-step-execution/natural-development-tools'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from dataclasses import dataclass
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
STAGE=_project_file(_PROJECT_ROOT, '.private/t199-four-step-execution')
ROOT=_project_file(_PROJECT_ROOT, '.private/t199-four-step-execution/runtime-workspace/runtime-root-p0')
PLAN=_project_file(_PROJECT_ROOT, '.private/t199-four-step-execution/natural-development-tools/PLAN.json')
MEASUREMENT=_project_file(_PROJECT_ROOT, '.private/t199-four-step-execution/p0-impact-32-attempt-004')


def canonical(value):
    """严格有限JSON；绝对时刻用单调秒，终分四座顺序独立标注。"""
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def pin(path):
    """只读取计划中已列的非凭据文件，按原字节绑定。"""
    data=Path(path).read_bytes();return {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}


def save(path,value,*,replace=False):
    """失败/启动独占保存，进度原子替换；不覆盖已完成桌或重试。"""
    path=Path(path)
    if replace:
        temporary=path.with_name(path.name+'.tmp.'+str(os.getpid()));temporary.write_bytes(canonical(value)+b'\n');temporary.replace(path)
    else:
        with path.open('xb') as stream:stream.write(canonical(value)+b'\n');stream.flush();os.fsync(stream.fileno())


def unchanged(plan):
    """源码/helper/比较器/参考原件全部固定，ROOT不能混main。"""
    return (HERE==Path(plan['output_directory']).resolve()
        and all(pin(Path(path))==expected for path,expected in plan['files'].items())
        and all(pin(_project_file(_PROJECT_ROOT, ROOT/path))==expected for path,expected in plan['runtime_files'].items()))


def execution_approved(plan,stage):
    """缺根确切批准则0hangma导入/规则/评分/世界；pilot为唯一table1，余31另有门。"""
    approval=json.loads((_project_file(_PROJECT_ROOT, HERE/'EXECUTION-APPROVAL.json')).read_text())
    key='approved_for_natural_pilot' if stage=='pilot' else 'approved_for_remaining_natural_development'
    if not (approval.get(key) is True and approval.get('plan_pin')==pin(PLAN)
        and approval.get('binding_id')==plan['binding_id'] and approval.get('selected_variant')==plan['selected_variant'] and approval.get('max_new_tables')==32
        and approval.get('pilot_ordinals')==[0] and approval.get('remaining_ordinals')==list(range(1,32))):
        raise ValueError('缺固定A-H0自然诊断/首桌批准；0规则/评分/World')
    if not unchanged(plan):raise ValueError('固定首8自然源或工具漂移')


def stop_new_tables(reason):
    """任何真实失败只阻止尚未开始桌，已开本地桌自然关闭；原失败不补试。"""
    path=_project_file(_PROJECT_ROOT, HERE/'STOP-NEW-TABLES.json')
    try:save(path,reason)
    except FileExistsError:pass


def loaded_paths(plan):
    """实际项目模块必须来自冻结P0，私有策略和比较器另给真实路径。"""
    rows={}
    for name,module in tuple(sys.modules.items()):
        path=getattr(module,'__file__',None)
        if name=='hangma_bot' or name.startswith('hangma_bot.'):
            if path is None or not Path(path).resolve().is_relative_to(_project_file(_PROJECT_ROOT, ROOT/'src')):raise ValueError('项目模块混main:'+name)
            rows[name]=str(Path(path).resolve())
    for name in ('runtime_policy','t199_natural_comparator','t199_natural_measurement'):
        module=sys.modules.get(name)
        if module is not None:
            path=str(Path(module.__file__).resolve())
            if path not in plan['files'] or pin(path)!=plan['files'][path]:raise ValueError('实际外部策略/比较器漂移')
            rows[name]=path
    return rows


def _measurement():
    """精确原helper模块，不重新实现R18/normal_v0/catch-play白名单。"""
    name='t199_natural_measurement';spec=importlib.util.spec_from_file_location(name,_project_file(_PROJECT_ROOT, MEASUREMENT/'common.py'))
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return module


_ORIGINAL=_measurement()
true_degradations=_ORIGINAL.true_degradations
batch=_ORIGINAL.batch
