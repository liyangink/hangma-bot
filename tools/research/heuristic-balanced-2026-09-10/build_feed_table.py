#!/usr/bin/env python3
"""从喂牌经验样本构建风险表：P(被鸣 | 牌张类别 × 墙余带) 与逐牌张表。

数据来源必须是**同一对手池**（本工作线用 V2 对手的模拟桌赛），不做跨环境迁移；
样本来自 counterfactual_windows.py capture 的 feed-samples.jsonl.gz。
"""
from __future__ import annotations

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

import argparse
import collections
import gzip
import json
from pathlib import Path

HONORS = ('东', '南', '西', '北', '中', '发', '白')


def category(tile: str) -> str:
    if tile in HONORS:
        return 'honor'
    if len(tile) == 2 and tile[0] in '19':
        return 'terminal'
    return 'middle'


def band(wall: int) -> str:
    return 'opening' if wall >= 80 else '64_79' if wall >= 64 else '40_63' if wall >= 40 else 'le39'


def main(path: Path, output: Path) -> None:
    with gzip.open(path, 'rt', encoding='utf-8') as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    total = len(rows)
    claimed = sum(1 for row in rows if row['claimed'])
    cells = collections.defaultdict(lambda: [0, 0])
    tiles = collections.defaultdict(lambda: [0, 0])
    kinds = collections.Counter(row.get('claim_kind') for row in rows if row['claimed'])
    for row in rows:
        cell = (category(row['tile']), band(row['wall']))
        cells[cell][0] += 1
        cells[cell][1] += 1 if row['claimed'] else 0
        tiles[row['tile']][0] += 1
        tiles[row['tile']][1] += 1 if row['claimed'] else 0
    table = dict(
        samples=total, claimed=claimed, claim_rate=claimed / total if total else None,
        by_kind=dict(kinds),
        cells={f'{key[0]}|{key[1]}': dict(n=value[0], claimed=value[1],
                                          rate=value[1] / value[0] if value[0] else None)
               for key, value in sorted(cells.items())},
        tiles={tile: dict(n=value[0], claimed=value[1],
                          rate=value[1] / value[0] if value[0] else None)
               for tile, value in sorted(tiles.items())},
        category_rates={name: dict(n=sum(v[0] for k, v in cells.items() if k[0] == name),
                                   claimed=sum(v[1] for k, v in cells.items() if k[0] == name),
                                   rate=(sum(v[1] for k, v in cells.items() if k[0] == name) /
                                         max(1, sum(v[0] for k, v in cells.items() if k[0] == name))))
                        for name in ('honor', 'terminal', 'middle')},
    )
    output.write_text(json.dumps(table, ensure_ascii=False, indent=2) + chr(10), encoding='utf-8')
    print(json.dumps({k: table[k] for k in ('samples', 'claimed', 'claim_rate', 'by_kind',
                                            'category_rates')}, ensure_ascii=False, indent=2))
    print('=== 单元格（类别|墙余带）')
    for key, value in table['cells'].items():
        print('  %-20s n=%-5d rate=%.4f' % (key, value['n'], value['rate']))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('samples', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    main(args.samples, args.output)
