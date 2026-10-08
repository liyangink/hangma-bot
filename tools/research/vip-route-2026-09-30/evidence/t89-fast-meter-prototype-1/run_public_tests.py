"""在显式原生覆盖下运行受影响公开回归；固定T75原生AST另行验收。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t89-fast-meter-prototype-1'

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

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('t89_test_overlay', _project_file(_PROJECT_ROOT, HERE / 'fast_overlay.py'))
overlay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(overlay)
files = [
    'tests/unit/policy/test_action_value_executor_workload_bounds.py',
    'tests/unit/policy/test_action_value_executor_scalar_fastpath.py',
    'tests/unit/policy/test_action_value_executor_r8_bounds.py',
    'tests/unit/policy/test_action_value_executor_list_alias.py',
    'tests/unit/policy/test_action_value_executor_r9b_views_trace.py',
    'tests/unit/policy/test_action_value_executor_r9_bounds.py',
    'tests/unit/policy/test_route_vip_heuristic.py',
    'tests/unit/hangma/test_route_transition_audit.py',
    'tests/unit/hangma/test_route_transition_composition.py',
    'tests/unit/hangma/test_route_transition.py',
    'tests/unit/hangma/test_route_transition_v35_parity.py',
    'tests/unit/hangma/test_public_tile_counts.py',
]
with overlay.installed() as identity:
    print('research_execution_id=' + identity['research_execution_id'], flush=True)
    code = pytest.main(['-q', '-p', 'no:cacheprovider'] + files)
raise SystemExit(code)
