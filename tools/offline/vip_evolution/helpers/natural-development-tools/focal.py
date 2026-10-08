"""自然桌焦点组合根：原受限评分器不变，每窗实际完整choose，无强制首动作。"""
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

import importlib.util
from pathlib import Path
import sys

from common import STAGE,pin


def build_focal(parameters,plan,native):
    """A-H0实际比较器模块按PLAN载入；图内choices与parent评分只用原native。"""
    runner=STAGE/'strategy-runner';sys.path.insert(0,str(runner))
    import runtime_policy
    comparator=Path(plan['comparator']['path'])
    if pin(comparator)!=plan['comparator']['pin']:raise ValueError('根比较器漂移')
    spec=importlib.util.spec_from_file_location('t199_natural_comparator',comparator)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    if Path(module.__file__).resolve()!=comparator:raise ValueError('不是PLAN实际比较器')
    # 只对外部私有薄策略组合根注入该明确函数，不改任何hangma模块或公式。
    runtime_policy.rank_root_entries=module.rank_root_entries
    sources={name:Path(row['path']).read_text() for name,row in plan['sources'].items()}
    if any(pin(row['path'])!=row['pin'] for row in plan['sources'].values()):raise ValueError('原公式源漂移')
    from hangma_bot import bootstrap
    if sources['parent']!=bootstrap.VIP_S03_SOURCE or parameters.identity(sources['parent'])!=plan['candidate_identity']:
        raise ValueError('共同P0原S03公式/核心/参数不同')
    if native.execution_id!=plan['parent_execution_id']:raise ValueError('parent实际native执行身份不同')
    return runtime_policy.T199RoutePolicy(parameters.rule_config,sources=sources,params=plan['candidate_identity']['params'],
        projection_limits=parameters.projection_limits,variant=plan['request_routing_variant'],binding_id=plan['binding_id'],
        compiled_runtimes={'parent':native})
