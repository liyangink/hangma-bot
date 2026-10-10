"""补充实际160单局变体尾部和桌赛池排序，不改已冻结效果门。

均值区间仍按独立根；实际阶段分布保留每根四席，抽样整根且保持两池
原比例。四席相关，不能把32/64变体当独立样本；池内单根不授区间。
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import statistics


def describe(values):
    """分布描述保留负值和零值；不把条件均值解释成比赛保证。"""
    q = statistics.quantiles(values, n=4, method='inclusive')
    return {'count': len(values), 'mean': statistics.mean(values), 'minimum': min(values),
            'q25': q[0], 'median': q[1], 'q75': q[2], 'maximum': max(values),
            'positive': sum(v > 0 for v in values), 'zero': sum(v == 0 for v in values),
            'negative': sum(v < 0 for v in values)}


def distribution(clusters, *, resamples=10000, seed=2026101041):
    """每个cluster是一完整根；整根重采样且池内根数不变。"""
    if not clusters or len({r['root'] for r in clusters}) != len(clusters):
        raise ValueError('独立根缺漏或重复')
    if any(len(r['net_deltas']) != 4 or len(r['rank_changes']) != 4 for r in clusters):
        raise ValueError('缺完整四席变体')
    values = [v for r in clusters for v in r['net_deltas']]
    ranks = Counter(v for r in clusters for v in r['rank_changes'])
    point = {'actual_160_variant_net_delta': describe(values),
             'root_mean_net_delta': describe([statistics.mean(r['net_deltas']) for r in clusters])
                                    if len(clusters) >= 2 else {'mean': statistics.mean(values)},
             'rank_change_counts': dict(ranks), 'independent_roots': len(clusters),
             'variants_are_correlated': True}
    pools = {p: [r for r in clusters if r['pool'] == p] for p in {r['pool'] for r in clusters}}
    if any(len(rows) < 2 for rows in pools.values()):
        return {**point, 'root_cluster_stratified_95_intervals': None}
    rng = random.Random(seed)
    sampled = {'variant_q25': [], 'negative_variant_fraction': [], 'strictly_worse_lab_rank_fraction': []}
    for _ in range(resamples):
        roots = [rng.choice(rows) for p, rows in sorted(pools.items()) for _ in range(len(rows))]
        deltas = [v for r in roots for v in r['net_deltas']]
        sampled['variant_q25'].append(statistics.quantiles(deltas, n=4, method='inclusive')[0])
        sampled['negative_variant_fraction'].append(sum(v < 0 for v in deltas) / len(deltas))
        sampled['strictly_worse_lab_rank_fraction'].append(
            sum(v == 'strictly_worse' for r in roots for v in r['rank_changes']) / len(deltas))
    intervals = {}
    for key, values in sampled.items():
        ordered = sorted(values)
        intervals[key] = [ordered[int(.025 * resamples)], ordered[int(.975 * resamples) - 1]]
    return {**point, 'root_cluster_stratified_95_intervals': intervals,
            'bootstrap_seed': seed, 'resamples': resamples, 'pool_counts': {p: len(r) for p, r in pools.items()}}


def rank_change(parent, child):
    """并列用排名区间；只有整个新区间越过旧区间才记严格改善／下降。"""
    if child[1] < parent[0]:
        return 'strictly_better'
    if child[0] > parent[1]:
        return 'strictly_worse'
    return 'same_interval' if parent == child else 'overlap_ambiguous'


def summarize(directories):
    """只从完整主报告取实际阶段变体，不重算规则或追加优化样本。"""
    clusters = []
    bindings = {}
    pools = set()
    identity = None
    for directory in directories:
        directory = Path(directory)
        plan = json.loads((directory / 'PLAN.json').read_text())
        report = json.loads((directory / 'SUMMARY.json').read_text())
        declaration = plan['declaration']
        pool = declaration['opponent_pool']
        current = (declaration['phase'], declaration['candidate']['expected_candidate_id'],
                   declaration['rules_hash'])
        if identity is None:
            identity = current
        elif current != identity:
            raise ValueError('不能混合开发／确认、不同候选或规则')
        expected_roots = {'dev': 4, 'confirm': 8}.get(declaration['phase'])
        if (expected_roots is None or len(declaration['stage_roots']) != expected_roots
                or {r['root'] for r in report['roots']} != set(declaration['stage_roots'])
                or len(plan['tasks']) != expected_roots * 80):
            raise ValueError('缺当前声明完整根矩阵')
        if pool in pools:
            raise ValueError('重复池')
        pools.add(pool)
        if (not report['complete'] or report['completed_table_instances'] != len(plan['tasks'])
                or report['plan_sha256'] != hashlib.sha256((directory / 'PLAN.json').read_bytes()).hexdigest()):
            raise ValueError('缺完整阶段主报告')
        bindings[str(directory)] = hashlib.sha256((directory / 'SUMMARY.json').read_bytes()).hexdigest()
        for root in report['roots']:
            variants = root['variants']
            if sorted(v['variant'] for v in variants) != [0, 1, 2, 3]:
                raise ValueError('缺四席')
            clusters.append({'root': root['root'], 'pool': pool,
                             'net_deltas': [v['delta']['net'] for v in variants],
                             'rank_changes': [rank_change(v['ledger']['P0']['focal_rank_interval'],
                                                         v['ledger']['Candidate']['focal_rank_interval']) for v in variants]})
    if pools != {'homogeneous', 'mixed'}:
        raise ValueError('缺两池')
    return {'schema': 'astra-actual160-distribution/1', 'metrics': distribution(clusters), 'clusters': clusters,
            'source_summaries': bindings, 'reporter_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'scope': '实际160单局变体与四席均值分别列账；置信区间按整根分层抽样；实验四角色排序不是官方晋级率',
            'original_profit_gates_unchanged': True, 'strength_or_production_admission': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runs', required=True, nargs=2)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    path = Path(args.out)
    if path.exists():
        raise ValueError('不覆盖旧分布报告')
    result = summarize(args.runs)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result['metrics'], ensure_ascii=False))


if __name__ == '__main__':
    main()
