"""联合参数搜索的选留顺序与新来源分层区间计算。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import math

import v2_parameter_new_development as new_development
import v2_parameter_search as subject


def test_rank_rows_uses_registered_order():
    rows = [
        {"config_id": "b", "fitness_mean_delta_low": 0.1,
         "normalized_l1_from_default": 0.3},
        {"config_id": "a", "fitness_mean_delta_low": 0.1,
         "normalized_l1_from_default": 0.3},
        {"config_id": "c", "fitness_mean_delta_low": 0.1,
         "normalized_l1_from_default": 0.2},
        {"config_id": "d", "fitness_mean_delta_low": 0.2,
         "normalized_l1_from_default": 9.0},
    ]
    assert [row["config_id"] for row in subject.rank_rows(rows)] == ["d", "c", "a", "b"]


def test_new_development_combines_strata_on_conservative_root_delta():
    panels = {
        "H": {"delta_bounds": {"mean_delta_low": 0.02,
                                  "standard_error_low": 0.03}},
        "M": {"delta_bounds": {"mean_delta_low": 0.06,
                                  "standard_error_low": 0.04}},
    }
    result = new_development._root_level_interval(panels)
    assert result["mean"] == 0.04
    assert result["standard_error"] == 0.025
    assert result["interval_95"] == [
        0.04 - new_development.Z_95 * 0.025,
        0.04 + new_development.Z_95 * 0.025,
    ]
    assert math.isclose(result["interval_95"][0], -0.00899909961350135)
