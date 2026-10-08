"""双路线候选的自主首步效果与单项增量，仍只解释条件开发案例。"""

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
    analyze(_project_file(_PROJECT_ROOT, HERE/'dual-route'),_project_file(_PROJECT_ROOT, HERE/'upgrade-persistent-v2'),{
        'autonomous_vs_upgrade':('auto_dual','base_upgrade'),
        'continuation_on_base_vs_upgrade':('base_dual','base_upgrade'),
        'continuation_on_seven_vs_upgrade':('seven_dual','seven_upgrade'),
        'root_with_dual':('seven_dual','base_dual'),
    },1080996)
    analyze(_project_file(_PROJECT_ROOT, HERE/'dual-route'),_project_file(_PROJECT_ROOT, HERE/'progress-guard'),{
        'dual_on_base_vs_guard':('base_dual','base_guard'),
        'dual_on_seven_vs_guard':('seven_dual','seven_guard'),
    },1080995,output_filename='against-progress-guard.json')
