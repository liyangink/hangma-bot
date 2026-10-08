#!/usr/bin/env python3
"""白板反事实的子群分层：按持白张数、墙余、爆头/链状态切分。"""
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
    return 'opening(80+)' if remaining >= 80 else '64-79' if remaining >= 64 else '40-63' if remaining >= 40 else 'le39'


def stats(items, rng):
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
    return dict(n=len(items), roots=len(roots), mean=sum(deltas) / len(deltas),
                ci=[boot[100], boot[-100]],
                pos=sum(1 for v in deltas if v > 0), zero=sum(1 for v in deltas if v == 0),
                neg=sum(1 for v in deltas if v < 0))


def main(cases_path, branches_path):
    cases = {row['case_id']: row for row in load(cases_path)}
    rows = []
    for row in load(branches_path):
        if row.get('delta') is None or not row.get('action_differs'):
            continue
        case = cases.get(row['case_id'])
        if case is None:
            continue
        row['whites'] = case.get('whites_in_hand')
        row['baotou'] = case.get('baotou')
        row['chain'] = case.get('chain_count')
        row['band'] = band(row['remaining'])
        rows.append(row)
    rng = random.Random(20260910)
    for name, key in (('持白张数', lambda r: r['whites']),
                      ('持白张数 × 墙余', lambda r: (r['whites'], r['band'])),
                      ('爆头/链', lambda r: (r['baotou'], r['chain'])),
                      ('墙余', lambda r: r['band'])):
        print('=== ' + name)
        buckets = collections.defaultdict(list)
        for row in rows:
            buckets[key(row)].append(row)
        for bucket in sorted(buckets, key=str):
            value = stats(buckets[bucket], rng)
            star = '  区间不含0' if value['ci'][0] > 0 or value['ci'][1] < 0 else ''
            print('  %-24s n=%-4d roots=%-3d mean=%7.2f ci=[%7.2f,%7.2f] +%d/0%d/-%d%s' % (
                str(bucket), value['n'], value['roots'], value['mean'], value['ci'][0],
                value['ci'][1], value['pos'], value['zero'], value['neg'], star))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
