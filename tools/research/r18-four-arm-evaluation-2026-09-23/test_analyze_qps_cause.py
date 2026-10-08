"""QPS 复算按时间选择完整运行，避免早期失败运行覆盖它。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/r18-four-arm-evaluation-2026-09-23'

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


SOURCE = Path(__file__).with_name("analyze_qps_cause.py")
SPEC = importlib.util.spec_from_file_location("qps_cause_report", SOURCE)
REPORT = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(REPORT)


def test_latest_runs_choose_newest_run_per_slot(tmp_path):
    for slot in ("slot-qinglong", "slot-baihu"):
        runs = tmp_path / slot / "runs"
        runs.mkdir(parents=True)
        (runs / "run-z-old").mkdir()
        (runs / "run-a-new").mkdir()
    # 控制修改时间：字母顺序与真实运行先后相反。
    import os
    for slot in ("slot-qinglong", "slot-baihu"):
        runs = tmp_path / slot / "runs"
        os.utime(runs / "run-z-old", ns=(1_000_000_000, 1_000_000_000))
        os.utime(runs / "run-a-new", ns=(2_000_000_000, 2_000_000_000))
    assert {slot: path.name for slot, path in REPORT.latest_runs(tmp_path).items()} == {
        "slot-baihu": "run-a-new", "slot-qinglong": "run-a-new"}
