"""实际向听约束的单项配对诊断。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/big-hand-paths-2026-09-09'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from lab import HERE
from conditional_analysis import analyze

if __name__=='__main__':
    analyze(_project_file(_PROJECT_ROOT, HERE/'progress-guard'),_project_file(_PROJECT_ROOT, HERE/'upgrade-persistent-v2'),{
        'guard_on_base_vs_upgrade':('base_guard','base_upgrade'),
        'guard_on_seven_vs_upgrade':('seven_guard','seven_upgrade'),
        'guard_on_base_vs_persistent':('base_guard','base_combined'),
        'guard_on_seven_vs_persistent':('seven_guard','seven_combined'),
        'root_with_guard':('seven_guard','base_guard'),
    },1080997)
