#!/usr/bin/env python3
"""C29 判定脚本：按预登记冻结规则，对筛查批 + 确认批给出逐臂判定。

用法：.venv/bin/python review/freematch-deep-dive-20260925/c29_verdict.py
读：c27-gate/result.json（筛查）、c29-confirm/result.json（确认）、可选 c30-third/result.json（第三批）。
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

import json
import math
import statistics
from pathlib import Path

ROOT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925')
BATCHES = ('c27-gate', 'c29-confirm', 'c30-third')


def load(name):
    path = _project_file(_PROJECT_ROOT, ROOT / name / 'result.json')
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding='utf-8'))
    return {(row['mix'], row['root_index']): row for row in payload['root_clusters']}


def effect(store, arm):
    keys = sorted(store)
    return [store[k]['delta_vs_baseline_per_table'][arm] for k in keys
            if arm in store[k]['delta_vs_baseline_per_table']]


def summary(values):
    n = len(values)
    mean = statistics.fmean(values)
    se = statistics.pstdev(values) / math.sqrt(n) if n > 1 else float('nan')
    return mean, se, mean - 1.96 * se, mean + 1.96 * se


def sign_test(values):
    pos = sum(1 for v in values if v > 0)
    neg = sum(1 for v in values if v < 0)
    n = pos + neg
    if not n:
        return pos, neg, 0.0, 1.0
    z = (pos - n / 2) / math.sqrt(n * 0.25)
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    return pos, neg, z, p


def main() -> int:
    stores = {name: load(name) for name in BATCHES}
    available = {name: store for name, store in stores.items() if store}
    print('可用批次：' + ', '.join('%s(%d 根)' % (n, len(s)) for n, s in available.items()))
    arms = set()
    for store in available.values():
        for row in store.values():
            arms.update(row['delta_vs_baseline_per_table'])
    print()
    print('| 臂 | 批次 | n | 均值 | 95% CI | 池 H | 池 M | 正/负 |')
    print('| --- | --- | --- | --- | --- | --- | --- | --- |')
    for arm in sorted(arms):
        short = arm.split('/')[-1].replace('OPTY-R18-C27-', '').replace('.py', '')
        merged = {}
        for name, store in available.items():
            for key, row in store.items():
                merged[(name,) + key] = row
        for name in list(available) + ['合并']:
            if name == '合并':
                values = effect(merged, arm)
                pools = {}
                for mix in ('H', 'M'):
                    cell = [merged[k]['delta_vs_baseline_per_table'][arm]
                            for k in merged
                            if merged[k]['mix'] == mix
                            and arm in merged[k]['delta_vs_baseline_per_table']]
                    pools[mix] = statistics.fmean(cell) if cell else float('nan')
            else:
                values = effect(available[name], arm)
                pools = {}
                for mix in ('H', 'M'):
                    cell = [available[name][k]['delta_vs_baseline_per_table'][arm]
                            for k in available[name]
                            if available[name][k]['mix'] == mix
                            and arm in available[name][k]['delta_vs_baseline_per_table']]
                    pools[mix] = statistics.fmean(cell) if cell else float('nan')
            if not values:
                continue
            mean, _se, lo, hi = summary(values)
            pos, neg, _z, _p = sign_test(values)
            print('| %s | %s | %d | %+.3f | [%+.3f, %+.3f] | %+.3f | %+.3f | %d/%d |'
                  % (short, name, len(values), mean, lo, hi, pools['H'], pools['M'], pos, neg))
        print()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
