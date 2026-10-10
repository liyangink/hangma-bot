"""按已冻结门检查两池完整阶段；根内四席先平均，不按决策数授强度。

只给效果门结果。即使确认通过，仍须原截止并发、包和生命周期门及人审。
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics
import sys

import summarize160 as summary


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def evaluate_gates(phase, gates, roots_by_pool):
    """输入为每独立根的四个相关变体均值；任何缺根或重复根拒绝。"""
    limits = gates[phase]
    if set(roots_by_pool) != {'homogeneous', 'mixed'}:
        raise ValueError('两池缺漏')
    roots = [r for rows in roots_by_pool.values() for r in rows]
    ids = [r['root'] for r in roots]
    if (len(roots) != limits['independent_roots'] or len(set(ids)) != len(ids)
            or any(len(rows) != limits['pool_roots'] for rows in roots_by_pool.values())):
        raise ValueError('独立根数缺漏或把相关变体当独立根')
    metrics = ('net', 'changed_windows', 'highfan_income', 'multiwhite_income', 'place_points')
    values = {k: [r['mean_delta_four_correlated_variants'][k] for r in roots] for k in metrics}
    stats = {k: summary.root_statistics(v) for k, v in values.items()}
    pool_net = {p: statistics.mean(r['mean_delta_four_correlated_variants']['net'] for r in rows)
                for p, rows in roots_by_pool.items()}
    if phase == 'development':
        checks = {
            'mean_net_positive': stats['net']['mean'] > 0,
            'positive_roots': stats['net']['positive_roots'] >= limits['positive_roots_minimum'],
            'positive_roots_each_pool': all(sum(r['mean_delta_four_correlated_variants']['net'] > 0
                                               for r in rows) >= limits['each_pool_positive_roots_minimum']
                                          for rows in roots_by_pool.values()),
            'actual_activity': sum(values['changed_windows']) * 4 >= limits['actual_changed_windows_minimum'],
            'highfan_income': stats['highfan_income']['mean'] >= limits['mean_highfan_income_delta_minimum'],
            'multiwhite_income': stats['multiwhite_income']['mean'] >= limits['mean_multiwhite_income_delta_minimum'],
        }
    else:
        q1 = statistics.quantiles(values['net'], n=4, method='inclusive')[0]
        checks = {
            'net_lower_strictly_positive': stats['net']['root_bootstrap_95_percent_interval'][0] > 0,
            'mean_net_investment_floor': stats['net']['mean'] >= limits['mean_net_delta_per160_minimum'],
            'each_pool_mean_positive': all(v > 0 for v in pool_net.values()),
            'place_points': stats['place_points']['mean'] >= limits['mean_place_points_delta_minimum'],
            'highfan_income_lower': stats['highfan_income']['root_bootstrap_95_percent_interval'][0]
                                   >= limits['root_bootstrap_95_highfan_income_lower_minimum'],
            'multiwhite_income_lower': stats['multiwhite_income']['root_bootstrap_95_percent_interval'][0]
                                      >= limits['root_bootstrap_95_multiwhite_income_lower_minimum'],
            'net_lower_quartile': q1 >= limits['net_root_lower_quartile_minimum'],
        }
    return {'checks': checks, 'effect_gate_pass': all(checks.values()), 'root_statistics': stats,
            'pool_mean_net': pool_net, 'independent_root_ids': ids,
            'quartile_method': 'inclusive', 'production_admission': False}


def activity_audit(plan, budget_policy):
    """保留截止回退、完整样本及实际choose耗时；逻辑驱动不抢占同步计算。"""
    reasons = Counter()
    pairs = Counter()
    windows = complete = model_windows = changed = over_fallback = 0
    max_seconds = 0.0
    for task in plan['tasks']:
        if task['arm'] != 'Candidate':
            continue
        for row in read(Path(task['out']) / 'FOCAL.json'):
            details = row['details']
            if details['candidate_id'] != plan['declaration']['candidate']['expected_candidate_id']:
                raise ValueError('实际候选审计身份不符')
            windows += 1
            changed += bool(row['changed'])
            reasons[details['reason']] += 1
            max_seconds = max(max_seconds, row['choose_seconds'])
            enhancement_span = details['original_enhancement_deadline_monotonic'] - 800.0
            fallback_span = enhancement_span * budget_policy.fallback_fraction / budget_policy.enhancement_fraction
            over_fallback += row['choose_seconds'] > fallback_span
            model = details.get('model')
            if model is not None:
                model_windows += 1
                complete += bool(model['complete'])
                pairs[str(model['completed_pairs'])] += 1
    return {'candidate_windows': windows, 'model_windows': model_windows, 'complete_models': complete,
            'changed_windows': changed, 'reason_counts': dict(reasons), 'completed_pair_counts': dict(pairs),
            'maximum_choose_seconds': max_seconds, 'choose_over_original_fallback_span': over_fallback,
            'timing_scope': 'choose入口含父和辅助；规则前序、排队及网络未计入；不授线上准入'}


def evaluate_runs(gates_path, phase, directories):
    """核声明摘要、完整主报告与全部根；未完成批次不能产生通过结果。"""
    gates = read(gates_path)
    roots_by_pool = {}
    audits = {}
    phase_tag = {'development': 'dev', 'confirmation': 'confirm'}[phase]
    for directory in directories:
        directory = Path(directory)
        plan = read(directory / 'PLAN.json')
        end = read(directory / 'RUN-CLOSED.json')
        report = read(directory / 'SUMMARY.json')
        declaration = plan['declaration']
        pool = declaration['opponent_pool']
        if pool in roots_by_pool:
            raise ValueError('重复对手池')
        if (not end['complete'] or not report['complete'] or declaration['phase'] != phase_tag
                or report['completed_table_instances'] != len(plan['tasks'])
                or report['plan_sha256'] != digest(directory / 'PLAN.json')):
            raise ValueError('缺完整计划与阶段主报告')
        frozen = [(Path(p), h) for p, h in gates['declarations'].items()
                  if h == plan['declaration_sha256']]
        if len(frozen) != 1 or digest(frozen[0][0]) != frozen[0][1]:
            raise ValueError('不是事前冻结声明')
        if declaration != read(frozen[0][0]):
            raise ValueError('嵌入声明与事前原文不同')
        if declaration['candidate']['expected_candidate_id'] != gates['candidate_id']:
            raise ValueError('不是冻结候选')
        if {r['root'] for r in report['roots']} != set(declaration['stage_roots']):
            raise ValueError('报告根与声明不同')
        # 只复用冻结预算比例，避免用写死的1.2秒代替原fallback截止。
        sys.path.insert(0, str(Path(declaration['runtime_root']) / 'src'))
        from hangma_bot.application.deadline import BudgetPolicy
        audits[pool] = activity_audit(plan, BudgetPolicy())
        roots_by_pool[pool] = report['roots']
    result = evaluate_gates(phase, gates, roots_by_pool)
    result['runtime_span_gate_pass'] = all(a['choose_over_original_fallback_span'] == 0 for a in audits.values())
    result['stage_gate_pass'] = result['effect_gate_pass'] and result['runtime_span_gate_pass']
    result.update(schema='astra-stage160-gate/1', phase=phase, candidate_id=gates['candidate_id'],
                  activity=audits, gates_sha256=digest(gates_path), reporter_sha256=digest(__file__))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gates', required=True)
    parser.add_argument('--phase', required=True, choices=['development', 'confirmation'])
    parser.add_argument('--runs', required=True, nargs=2)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    out = Path(args.out)
    if out.exists():
        raise ValueError('不覆盖已有门报告')
    result = evaluate_runs(args.gates, args.phase, args.runs)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('phase', 'checks', 'stage_gate_pass')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
