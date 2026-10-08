"""G43b：仅修离线执行审查识别身份，不改变 G43 动作算法。"""

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

import g43_edge_three_draw_policy as original


def policy_factory(metrics: list[dict]):
    """保持原策略、原评分与三摸判据，只声明可审核的受限评分身份。"""
    build_original = original.policy_factory(metrics)

    def build(monotonic):
        policy = build_original(monotonic)
        policy.policy_id = "action_value_v1:research:g43-edge-three-draw-filter-v1"
        policy.max_operations = policy.baseline.max_operations
        return policy

    return build
