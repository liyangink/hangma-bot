#!/usr/bin/env python3
"""反事实案例的条件挖掘：把"候选减保底"差值按可识别条件分组，找窄候选。

输入：counterfactual_windows.py 的 branch 产物（含 frontier 签名、动作键、余牌、类别）。
输出：条件分组表（每组样本数、均值、按根聚类 95% 区间、正/零/负计数）。

纪律：
- 分组必须来自**决策时可见**的事实（余牌、动作键、前沿签名差），不得使用赛后结果；
- 样本数 < 30 或根数 < 10 的分组只登记为观察，不作为候选依据；
- 多重比较下不挑单组最好值，报告全表供人工判断。
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
import gzip
import json
import random
from collections import defaultdict


def load(path):
    opener = gzip.open if path.endswith('.gz') else open
    with opener(path, 'rt', encoding='utf-8') as handle:
        return [json.loads(line) for line in handle if line.strip()]


def signature_of(entry):
    return tuple(entry['signature'])


def features(row):
    """从案例可见事实抽取特征；找不到对应动作的签名时为 None。"""
    frontier = {item['action_key']: signature_of(item) for item in row['frontier']}
    base = frontier.get(row['baseline_action'])
    cand = frontier.get(row['candidate_action'])
    if base is None or cand is None:
        return None
    return dict(
        label=row['label'],
        remaining=row['remaining'],
        base_standard=base[0], base_pairs=base[1], base_outs=base[2],
        cand_standard=cand[0], cand_pairs=cand[1], cand_outs=cand[2],
        standard_delta=cand[0] - base[0], pairs_delta=cand[1] - base[1],
        outs_ratio=(cand[2] / base[2]) if base[2] else None,
        pairs_nearer=cand[1] < base[1],
        wall_band='ge64' if row['remaining'] >= 64 else '40_63' if row['remaining'] >= 40 else 'le39',
    )


def group_stats(rows, key):
    buckets = defaultdict(list)
    for row in rows:
        bucket = key(row)
        if bucket is None:
            continue
        buckets[bucket].append(row)
    out = {}
    rng = random.Random(20260910)
    for bucket, items in sorted(buckets.items(), key=lambda kv: str(kv[0])):
        deltas = [item['delta'] for item in items]
        by_root = defaultdict(list)
        for item in items:
            by_root[item['root']].append(item['delta'])
        roots = list(by_root)
        boot = []
        for _ in range(4000):
            picked = [rng.choice(roots) for _ in roots]
            flat = [value for root in picked for value in by_root[root]]
            boot.append(sum(flat) / len(flat))
        boot.sort()
        out[str(bucket)] = dict(
            cases=len(items), roots=len(roots), mean=sum(deltas) / len(deltas),
            ci95=[boot[int(len(boot) * 0.025)], boot[int(len(boot) * 0.975)]],
            positive=sum(1 for value in deltas if value > 0),
            zero=sum(1 for value in deltas if value == 0),
            negative=sum(1 for value in deltas if value < 0))
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--branches', required=True)
    parser.add_argument('--output')
    args = parser.parse_args()
    rows = load(args.branches)
    enriched = []
    for row in rows:
        feat = features(row)
        if feat is None:
            continue
        enriched.append(dict(row, **feat))
    report = dict(
        cases=len(rows), enriched=len(enriched),
        by_label=group_stats(enriched, lambda r: r['label']),
        by_label_and_wall=group_stats(enriched, lambda r: (r['label'], r['wall_band'])),
        by_pairs_delta=group_stats(enriched, lambda r: 'pairs{0:+d}'.format(r['pairs_delta'])),
        by_outs_loss=group_stats(enriched, lambda r: (
            'no_loss' if r['outs_ratio'] is not None and r['outs_ratio'] >= 0.999 else
            'le5pct' if r['outs_ratio'] is not None and r['outs_ratio'] >= 0.95 else
            'le15pct' if r['outs_ratio'] is not None and r['outs_ratio'] >= 0.85 else 'gt15pct')),
        by_pairs_nearer_and_outs=group_stats(enriched, lambda r: (
            ('nearer' if r['pairs_nearer'] else 'not_nearer'), 
            'no_loss' if r['outs_ratio'] is not None and r['outs_ratio'] >= 0.999 else
            'le5pct' if r['outs_ratio'] is not None and r['outs_ratio'] >= 0.95 else
            'le15pct' if r['outs_ratio'] is not None and r['outs_ratio'] >= 0.85 else 'gt15pct')),
        by_standard_delta=group_stats(enriched, lambda r: 'std{0:+d}'.format(r['standard_delta'])),
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + chr(10)
    if args.output:
        open(args.output, 'w', encoding='utf-8').write(rendered)
    print(rendered)


if __name__ == '__main__':
    main()
