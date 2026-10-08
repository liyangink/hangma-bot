#!/usr/bin/env python3
"""反事实差值尾部特征：区分"实质不同"的替代与"等价"替代，找可识别条件。

只读 branch 产物；输出各规则的完整分层表 + 正向尾部（≥+10）与负向尾部案例特征。
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

import collections
import gzip
import json
import sys


def load(path):
    with gzip.open(path, 'rt', encoding='utf-8') as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main(path):
    rows = [row for row in load(path) if row.get('delta') is not None]
    print('总行数', len(rows))
    print('=== 按规则/类别 ===')
    table = collections.defaultdict(list)
    for row in rows:
        table[(row['rule'], row['label'])].append(row['delta'])
    for key in sorted(table):
        values = table[key]
        zeros = sum(1 for v in values if v == 0)
        print('%-46s n=%-4d mean=%7.3f zero=%3d pos=%3d neg=%3d' % (
            key[0] + '/' + key[1], len(values), sum(values) / len(values), zeros,
            sum(1 for v in values if v > 0), sum(1 for v in values if v < 0)))
    print('=== 非零差值分布 ===')
    nonzero = [row for row in rows if row['delta'] != 0]
    print('非零占比 %.1f%%' % (100.0 * len(nonzero) / len(rows)))
    buckets = collections.Counter()
    for row in nonzero:
        value = row['delta']
        buckets['le-20' if value <= -20 else
                '-19..-10' if value <= -10 else
                '-9..-1' if value < 0 else
                '1..9' if value < 10 else
                '10..19' if value < 20 else 'ge20'] += 1
    print(dict(buckets))
    print('=== 正向尾部（≥+20）特征 ===')
    tail = [row for row in rows if row['delta'] >= 20]
    print('数量', len(tail))
    for row in sorted(tail, key=lambda r: -r['delta'])[:12]:
        print(' +%-3d %-28s %-14s rem=%-3s base=%-12s cand=%-12s fan %s' % (
            row['delta'], row['rule'], row['label'], row['remaining'],
            row['baseline_action'], row.get('rule_key'),
            row['candidate']['fan']))
    print('=== 负向尾部（≤-20）特征 ===')
    tail = [row for row in rows if row['delta'] <= -20]
    print('数量', len(tail))
    for row in sorted(tail, key=lambda r: r['delta'])[:12]:
        print(' %-4d %-28s %-14s rem=%-3s base=%-12s cand=%-12s fan %s' % (
            row['delta'], row['rule'], row['label'], row['remaining'],
            row['baseline_action'], row.get('rule_key'), row['candidate']['fan']))


if __name__ == '__main__':
    main(sys.argv[1])
