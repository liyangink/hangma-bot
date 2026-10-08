#!/usr/bin/env python3
"""C24 负向对照 maker：把「墙短时向听更贵」反过来（墙短时**放宽**向听权重）。

用途：证明这条通道**不是结构性为空**，而是**方向不成立**。
"""
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

import sys
from pathlib import Path

ROOT = _PROJECT_ROOT
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))
from hangma_bot.policy.r18_integrated_positive_v2 import R18_INTEGRATED_POSITIVE_V2_SOURCE  # noqa: E402

NL = chr(10)
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates')
ANCHOR = "                base = -100.0 * float(shanten) + round(support, 1)" + NL
BLOCK_LINES = [
    '                wall_left = visible.get("remaining_tile_count")',
    "                if wall_left is not None and wall_left is not True and wall_left is not False:",
    "                    wall_value = float(wall_left)",
    "                    if wall_value < 60:",
    "                        relief = min(__R__ * (60 - wall_value), 90)",
    "                        base = base + relief * float(shanten)",
]

for token in ("1", "3"):
    block = NL.join(line.replace("__R__", token) for line in BLOCK_LINES) + NL
    candidate = R18_INTEGRATED_POSITIVE_V2_SOURCE.replace(ANCHOR, ANCHOR + block)
    assert candidate.count(ANCHOR) == 1
    name = "OPTY-R18-C24-CONTROL-RELIEF%s.py" % token
    path = _project_file(_PROJECT_ROOT, OUT / name)
    path.write_text(candidate, encoding="utf-8")
    compile(candidate, str(path), "exec")
    print("wrote", name)