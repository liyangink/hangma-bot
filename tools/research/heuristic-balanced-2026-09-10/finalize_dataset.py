#!/usr/bin/env python3
"""就地补齐数据集派生的 is_draw 字段（导出器后续版本已内置该推导）。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/heuristic-balanced-2026-09-10'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import gzip, json, sys
from pathlib import Path

for name in sys.argv[1:]:
    path = Path(name)
    tmp = path.with_suffix('.tmp.gz')
    fixed = 0
    with gzip.open(path, 'rt', encoding='utf-8') as src, gzip.open(tmp, 'wt', encoding='utf-8') as dst:
        for line in src:
            row = json.loads(line)
            outcome = row.get('outcome')
            if outcome is not None and outcome.get('is_draw') is None:
                outcome['is_draw'] = outcome.get('winner_seat') is None or not outcome.get('fan')
                fixed += 1
            dst.write(json.dumps(row, ensure_ascii=False) + chr(10))
    tmp.replace(path)
    print(name, '补齐行数', fixed)
