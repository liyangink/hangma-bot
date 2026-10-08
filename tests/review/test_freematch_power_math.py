"""自由赛功效换算的数值回归：防止 Student-t 分位低估样本量。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'tests/review'

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


SCRIPT = _project_file(_PROJECT_ROOT, Path(__file__).resolve().parents[2] / "review/freematch-deep-dive-20260925/freematch_power.py")
SPEC = importlib.util.spec_from_file_location("freematch_power", SCRIPT)
POWER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(POWER)


def test_student_t_quantiles_and_cdf_are_valid():
    """校准解析分位数，并保证大样本 CDF 在概率范围内。"""

    assert abs(POWER.t_ppf(0.975, 1) - 12.706204736) < 1e-7
    assert abs(POWER.t_ppf(0.975, 10) - 2.228138852) < 1e-7
    assert abs(POWER.t_ppf(0.8, 678) - 0.842151704) < 1e-7
    assert 0.0 < POWER.t_cdf(0.84, 678) < 1.0


def test_student_t_room_need_does_not_undercut_normal_approximation():
    """Student-t 校正不能把同一目标所需房数算得比 z 近似更少。"""

    for delta in (0.5, 1.0, 2.0, 3.0, 4.0):
        need = POWER.required_rooms(delta, 11.02)
        assert need["t"] >= need["z"]
