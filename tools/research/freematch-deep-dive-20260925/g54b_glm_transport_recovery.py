#!/usr/bin/env python3
"""G54 首次六卡全因本地连接失败后的独立输出恢复；不覆盖故障证据。"""

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

from pathlib import Path

import g54_glm_route_author_wave as original


HERE = Path(__file__).resolve().parent
original.OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g54b-glm-route-author-recovery-20260927')
original.PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G54B-TRANSPORT-RECOVERY-2026-09-27.md')


if __name__ == "__main__":
    original.main()
