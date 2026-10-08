#!/usr/bin/env python3
"""按墙余分段的规则效果：区分开局首弃（对称赌博）与中后局（可能有系统价值）。"""
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

import collections
import gzip
import json
import random
import sys


def load(path):
    with gzip.open(path, 'rt', encoding='utf-8') as handle:
        return [json.loads(line) for line in handle if line.strip()]


def band(remaining):
    if remaining >= 80:
        return 'opening(80+)'
    if remaining >= 64:
        return '64-79'
    if remaining >= 40:
        return '40-63'
    return 'le39'


def main(path):
    rows = [row for row in load(path) if row.get('delta') is not None]
    for row in rows:
        row['band'] = band(row['remaining'])
    table = collections.defaultdict(list)
    for row in rows:
        table[(row['rule'], row['band'])].append(row)
    rng = random.Random(20260910)
    print('%-40s %5s %5s %8s %18s %6s %6s %6s' % ('规则/墙余', 'n', 'roots', 'mean', 'ci95', 'pos', 'zero', 'neg'))
    for key in sorted(table):
        items = table[key]
        deltas = [item['delta'] for item in items]
        by_root = collections.defaultdict(list)
        for item in items:
            by_root[item['root']].append(item['delta'])
        roots = list(by_root)
        boot = []
        for _ in range(4000):
            picked = [rng.choice(roots) for _ in roots]
            flat = [value for root in picked for value in by_root[root]]
            boot.append(sum(flat) / len(flat))
        boot.sort()
        print('%-40s %5d %5d %8.3f [%7.2f,%7.2f] %6d %6d %6d' % (
            key[0] + '/' + key[1], len(items), len(roots), sum(deltas) / len(deltas),
            boot[100], boot[-100],
            sum(1 for v in deltas if v > 0), sum(1 for v in deltas if v == 0),
            sum(1 for v in deltas if v < 0)))


if __name__ == '__main__':
    main(sys.argv[1])
