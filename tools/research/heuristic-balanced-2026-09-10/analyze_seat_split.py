#!/usr/bin/env python3
"""庄闲切分：把已有反事实批次的差值按"本人是否庄家"分层。

用途：检验座位条件规则假设——若同一规则在庄位与闲位表现不同（例如庄位偏差较小），
说明保底策略在某一座位上系统性偏离；若两侧一致为负/中性，则该族无座位空间。
case 记录的 hand_row.initial.dealer_seat 给出本局庄家，window_key.seat 给出本人座位。
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
import random
import sys
from pathlib import Path


def load(path: Path):
    with gzip.open(path, 'rt', encoding='utf-8') as handle:
        return [json.loads(line) for line in handle if line.strip()]


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
    return dict(n=len(items), mean=sum(deltas) / len(deltas), ci=[boot[100], boot[-100]],
                pos=sum(1 for v in deltas if v > 0), zero=sum(1 for v in deltas if v == 0),
                neg=sum(1 for v in deltas if v < 0))


def main(directory: Path):
    rng = random.Random(20260910)
    for name in sorted(p.name for p in directory.iterdir() if p.is_dir()):
        cases_path = directory / name / 'cases.jsonl.gz'
        pair = [(cases_path, directory / name / 'branches-rules.jsonl.gz'),
                (cases_path, directory / name / 'branches.jsonl.gz')]
        cases_file, branches_file = next(((c, b) for c, b in pair if b.is_file()), (None, None))
        if cases_file is None:
            continue
        cases = {row['case_id']: row for row in load(cases_file)}
        rows = []
        for row in load(branches_file):
            if row.get('delta') is None:
                continue
            case = cases.get(row['case_id'])
            if case is None:
                continue
            dealer_seat = (case.get('hand_row') or {}).get('initial', {}).get('dealer_seat')
            seat = (case.get('window_key') or {}).get('seat')
            row['is_dealer'] = (dealer_seat is not None and seat == dealer_seat)
            row['role'] = '庄' if row['is_dealer'] else '闲'
            rows.append(row)
        print('===== ' + name, '（行数 %d）' % len(rows))
        for label, key in (('全部', lambda r: r['role']),
                           ('按类别', lambda r: (r['label'], r['role']))):
            buckets = collections.defaultdict(list)
            for row in rows:
                buckets[key(row)].append(row)
            for bucket in sorted(buckets, key=str):
                value = stats(buckets[bucket], rng)
                if value['n'] < 20:
                    continue
                star = '  区间不含0' if value['ci'][0] > 0 or value['ci'][1] < 0 else ''
                print('  %-30s n=%-4d mean=%7.2f ci=[%7.2f,%7.2f]%s' % (
                    str(bucket), value['n'], value['mean'], value['ci'][0], value['ci'][1], star))


if __name__ == '__main__':
    main(Path(sys.argv[1]))
