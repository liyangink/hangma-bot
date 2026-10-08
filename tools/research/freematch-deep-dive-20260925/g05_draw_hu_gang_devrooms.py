#!/usr/bin/env python3
"""在已冻结的第三、四间开发房复用胡/杠重建器，不读取留出房。"""

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

import json
from pathlib import Path

import g05_draw_hu_gang_reconstruction as base


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g05-draw-hu-gang-devrooms-03-04')


def main() -> None:
    """只设置开发房来源并调用同一规则核验逻辑；拒绝覆盖证据。"""
    if OUT.exists():
        raise FileExistsError("开发房结果目录已有文件，拒绝覆盖")
    base.ROOMS = (
        ("a_852fb97c102e", "g05-strong-draw-devroom-03"),
        ("a_2a8aa14dc8a1", "g05-strong-draw-devroom-04"),
    )
    payload = base.run()
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "result.json")).write_text(
        json.dumps({key: value for key, value in payload.items() if key != "windows"},
                   ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (_project_file(_PROJECT_ROOT, OUT / "windows.json")).write_text(
        json.dumps({"schema": "g05-draw-hu-gang-windows/1", "windows": payload["windows"]},
                   ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"total_counts": payload["total_counts"],
                      "failures": len(payload["failures"])}, ensure_ascii=False))


if __name__ == "__main__":
    main()
