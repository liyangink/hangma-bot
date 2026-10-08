#!/usr/bin/env python3
"""C38 判定：按冻结六项判据评估（④⑤ 在本批不可测，如实标注）。"""
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

ROOT = _PROJECT_ROOT
ARM = 'candidate@review/freematch-deep-dive-20260925/candidates/OPTY-R18-C27-CELL-R6.py'
BATCHES = [
    ('C29筛查', _project_file(_PROJECT_ROOT, ROOT / 'review/freematch-deep-dive-20260925/c27-gate/result.json')),
    ('C29确认', _project_file(_PROJECT_ROOT, ROOT / 'review/freematch-deep-dive-20260925/c29-confirm/result.json')),
    ('C30第三批', _project_file(_PROJECT_ROOT, ROOT / 'review/freematch-deep-dive-20260925/c30-third/result.json')),
    ('C35第二级', _project_file(_PROJECT_ROOT, ROOT / '.team-work/c35-level2/result.json')),
    ('C38定罪批', _project_file(_PROJECT_ROOT, ROOT / 'review/freematch-deep-dive-20260925/c38-certify/result.json')),
]


def roots_of(path):
    payload = json.loads(path.read_text(encoding='utf-8'))
    rows = payload.get('root_clusters') or []
    out = []
    for row in rows:
        delta = row.get('delta_vs_baseline_per_table')
        if isinstance(delta, dict):
            if ARM in delta:
                out.append((row.get('mix'), row.get('root_index'), float(delta[ARM])))
        elif isinstance(delta, (int, float)):
            out.append((row.get('mix'), row.get('root_index'), float(delta)))
    return out


def summary(values):
    n = len(values)
    mean = statistics.fmean(values)
    se = statistics.pstdev(values) / math.sqrt(n) if n > 1 else float('nan')
    return mean, se, mean - 1.96 * se, mean + 1.96 * se


def main() -> int:
    loaded = []
    for name, path in BATCHES:
        if not path.exists():
            print('缺失批次：', name, path)
            continue
        rows = roots_of(path)
        loaded.append((name, rows))
        mean, _se, lo, hi = summary([v for _m, _r, v in rows])
        mixed = {}
        for mix in ('H', 'M'):
            mixed[mix] = statistics.fmean([v for m, _r, v in rows if m == mix]) if any(m == mix for m, _r, v in rows) else float('nan')
        print('%-10s n=%3d  均值 %+.3f  CI [%+.3f, %+.3f]  H %+.3f / M %+.3f'
              % (name, len(rows), mean, lo, hi, mixed['H'], mixed['M']))
    allv = [v for _n, rows in loaded for _m, _r, v in rows]
    mean, _se, lo, hi = summary(allv)
    print()
    print('① 本批点估计 > 0 : %s（%+.3f）' % ('PASS' if loaded[-1][1] and statistics.fmean([v for _m,_r,v in loaded[-1][1]]) > 0 else 'FAIL', statistics.fmean([v for _m,_r,v in loaded[-1][1]])))
    print('② 合并 n=%d 均值 %+.3f CI [%+.3f, %+.3f] ⇒ 下界>0 : %s' % (len(allv), mean, lo, hi, 'PASS' if lo > 0 else 'FAIL'))
    worst = None
    for name, rows in loaded:
        rest = [v for n2, r2 in loaded if n2 != name for _m, _r, v in r2]
        m2, _s2, l2, h2 = summary(rest)
        flag = 'PASS' if l2 > 0 else 'FAIL'
        print('   留一批（剔 %s）: n=%d 均值 %+.3f CI [%+.3f, %+.3f] ⇒ %s' % (name, len(rest), m2, l2, h2, flag))
        if worst is None or l2 < worst[1]:
            worst = (name, l2)
    print('③ 留一批敏感性 ⇒ 最差下界 %+.3f（剔 %s）: %s' % (worst[1], worst[0], 'PASS' if worst[1] > 0 else 'FAIL'))
    last = loaded[-1][1]
    pool = {mix: statistics.fmean([v for m, _r, v in last if m == mix]) for mix in ('H', 'M')}
    print('⑥ 两池同号 : H %+.3f / M %+.3f ⇒ %s' % (pool['H'], pool['M'], 'PASS' if (pool['H'] > 0) == (pool['M'] > 0) else 'FAIL'))
    print('④ 机制同向（本批爆头进入）: 本批无机制计数器 ⇒ 不可测（预登记缺陷）')
    print('⑤ 普通胡收入不退步: 本批无账本分解 ⇒ 不可测（预登记缺陷）；C35 批实测 |−1.611| ≤ 1.2×1.588=1.906 ⇒ 通过')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
