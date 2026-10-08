"""G239：独立收益试验身份；选择逻辑与已冻结 G237 完全相同。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import g237_numeric_inversion_policy as frozen


POLICY_ID = "action_value_v1:research:g239-numeric-route-fullwindow-v1"


class NumericRoutePolicy(frozen.NumericInversionPolicy):
    """只区分研究身份，不重写已冻结的 `select` 或 `choose`。"""

    policy_id = POLICY_ID


research_parent_factory = frozen.research_parent_factory
select = frozen.select


def policy_factory(metrics: list[dict]):
    """装配每张完整桌独立的候选实例和只读指标接收器。"""

    def build(monotonic):
        return NumericRoutePolicy(research_parent_factory(monotonic), metrics)

    return build
