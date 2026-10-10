"""补充完整阶段的庄闲暴露与条件比率；不改变冻结效果门。

付款单位为模拟规则基准分；比率以实际角色单局为分母。四席属于同一
独立根，先合并根内计数再求比率，区间按根统计，不按单局或四席抽样。
累计取白及庄闲暴露会受策略终止/连庄影响，只作分布描述。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from summarize160 import root_statistics

FIELDS = ('net', 'hands', 'own_hu', 'ordinary_income', 'highfan_income',
          'dealer_hands', 'dealer_hu', 'idle_hu', 'other_dealer_hu',
          'dealer_to_idle_payment', 'idle_to_dealer_payment',
          'idle_to_idle_payment', 'own_draws_to_hu')
COHORTS = ('all', 'final_acquired_white_0', 'final_acquired_white_1',
           'final_acquired_white_2_or_more')


def digest(path):
    """绑定实际读取的完整报告/工具字节，不授运行或发布资格。"""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_counts(value):
    """核收入支付闭合及角色计数；无角色的零分母不能补成零比率。"""
    if any(type(value[k]) not in (int, float) or not math.isfinite(value[k]) for k in FIELDS):
        raise ValueError('缺已知有限计数或积分')
    counts = ('hands', 'own_hu', 'dealer_hands', 'dealer_hu', 'idle_hu',
              'other_dealer_hu', 'own_draws_to_hu')
    if any(type(value[k]) is not int or value[k] < 0 for k in counts):
        raise ValueError('单局/胡牌/摸牌数须为非负整数')
    h, d = value['hands'], value['dealer_hands']
    if (d > h or value['dealer_hu'] > d or value['idle_hu'] > h - d
            or value['other_dealer_hu'] > h - d
            or value['idle_hu'] + value['other_dealer_hu'] > h - d
            or value['own_hu'] != value['dealer_hu'] + value['idle_hu']):
        raise ValueError('庄闲暴露或互斥胡牌计数不一致')
    money = ('ordinary_income', 'highfan_income', 'dealer_to_idle_payment',
             'idle_to_dealer_payment', 'idle_to_idle_payment')
    if any(value[k] < 0 for k in money):
        raise ValueError('收入与付款必须分别非负')
    net = value['ordinary_income'] + value['highfan_income'] - sum(value[k] for k in money[2:])
    if not math.isclose(net, value['net'], abs_tol=1e-9, rel_tol=0):
        raise ValueError('收入减三类付款不等于净积分')
    if not d and (value['dealer_to_idle_payment'] or value['dealer_hu']):
        raise ValueError('无庄家单局却存在庄家付款或胡牌')
    if h == d and (value['idle_to_dealer_payment'] or value['idle_to_idle_payment']):
        raise ValueError('无闲家单局却存在闲家付款')
    if not h and any(value[k] != 0 for k in FIELDS):
        raise ValueError('空白数层不能有积分或事件')
    if not value['own_hu'] and value['own_draws_to_hu']:
        raise ValueError('无本家胡牌却有胡牌摸序累计')


def rates(value):
    """返回角色暴露、条件胡牌率和平均付款；None表示分母为零。

    胡牌率单位为0—1比例，付款为基准分/实际角色单局；胡牌摸序只描述
    已胡单局，含庄家直抽和杠补，不是全部单局的因果速度。
    """
    validate_counts(value)
    h, d, hu = value['hands'], value['dealer_hands'], value['own_hu']
    idle = h - d
    divide = lambda numerator, denominator: None if denominator == 0 else numerator / denominator
    return {
        'dealer_exposure_fraction': divide(d, h),
        'own_hu_per_hand': divide(hu, h),
        'own_dealer_hu_per_dealer_hand': divide(value['dealer_hu'], d),
        'own_idle_hu_per_idle_hand': divide(value['idle_hu'], idle),
        'other_dealer_hu_per_idle_hand': divide(value['other_dealer_hu'], idle),
        'dealer_to_idle_payment_per_dealer_hand': divide(value['dealer_to_idle_payment'], d),
        'idle_to_dealer_payment_per_idle_hand': divide(value['idle_to_dealer_payment'], idle),
        'idle_to_idle_payment_per_idle_hand': divide(value['idle_to_idle_payment'], idle),
        'own_draws_per_own_hu': divide(value['own_draws_to_hu'], hu),
    }


def sum_counts(values):
    """只累加已核计数；四席相关性留在外层独立根，不增加独立样本数。"""
    values = list(values)
    for value in values:
        validate_counts(value)
    return {k: sum(v[k] for v in values) for k in FIELDS}


def rate_delta(parent, child):
    """差为候选减父；任何一臂零分母的条件差保持未知。"""
    p, c = rates(parent), rates(child)
    return {k: None if p[k] is None or c[k] is None else c[k] - p[k] for k in p}


def describe_roots(root_rows):
    """每根四席合计后求角色条件率，保留缺分母根，不筛成完整总体。"""
    if not root_rows or len({r['root'] for r in root_rows}) != len(root_rows):
        raise ValueError('缺独立根或重复根')
    total = {arm: sum_counts(r[arm] for r in root_rows) for arm in ('P0', 'Candidate')}
    deltas = [rate_delta(r['P0'], r['Candidate']) for r in root_rows]
    statistics_by_rate = {}
    for key in deltas[0]:
        values = [r[key] for r in deltas]
        missing = sum(v is None for v in values)
        # 缺分母根仍列账，不用筛除后的区间冒充完整独立根统计。
        statistics_by_rate[key] = {
            'undefined_roots': missing,
            'values_in_root_order': values,
            'complete_root_statistics': None if missing else root_statistics(values),
        }
    return {
        'independent_roots': len(root_rows),
        'actual_correlated_stage_variants': 4 * len(root_rows),
        'counts': total,
        'denominators': {arm: {'all_hands': v['hands'], 'dealer_hands': v['dealer_hands'],
                              'idle_hands': v['hands'] - v['dealer_hands'],
                              'own_hu_hands': v['own_hu']} for arm, v in total.items()},
        'rates': {arm: rates(v) for arm, v in total.items()},
        'aggregate_rate_delta': rate_delta(total['P0'], total['Candidate']),
        'mean_count_delta_per_actual_160_stage': {
            k: (total['Candidate'][k] - total['P0'][k]) / (4 * len(root_rows)) for k in FIELDS},
        'root_rate_delta_statistics': statistics_by_rate,
        'root_rows': root_rows,
    }


def validate_task_ledger(plan, end):
    """要求完整四席十桌两臂矩阵，闭合账逐任务原文相等且唯一。

    同长度、同状态的另一运行或重复闭合行不能代替当前计划。这里只核
    来源接续；规则、逐局守恒及配对牌山由绑定的原完整汇总负责。
    """
    declaration = plan['declaration']
    expected = {(r, v, t, a) for r in declaration['stage_roots']
                for v in range(4) for t in range(10) for a in ('P0', 'Candidate')}
    tasks = plan['tasks']
    required = ('id', 'stage_root', 'seat_variant', 'table_no', 'arm')
    if any(type(t) is not dict or any(k not in t for k in required)
           or type(t['id']) is not str or type(t['seat_variant']) is not int
           or type(t['table_no']) is not int for t in tasks):
        raise ValueError('任务字段或计数类型不完整')
    matrix = {(t['stage_root'], t['seat_variant'], t['table_no'], t['arm']) for t in tasks}
    by_id = {t['id']: t for t in tasks}
    if len(tasks) != len(expected) or len(by_id) != len(tasks) or matrix != expected:
        raise ValueError('任务矩阵缺漏、重复或混入另一根')
    seen = set()
    for result in end['results']:
        task = result.get('task')
        if (type(task) is not dict or type(task.get('id')) is not str
                or task['id'] in seen or task['id'] not in by_id
                or task != by_id[task['id']] or result['status'] != 'complete'):
            raise ValueError('闭合任务重复、来源不符或未完整')
        seen.add(task['id'])
    if seen != set(by_id):
        raise ValueError('闭合账没有逐一覆盖当前计划')


def summarize(directories):
    """只读取两池完整主报告和自然闭合账；混合阶段/候选/规则直接拒绝。"""
    rows = {cohort: [] for cohort in COHORTS}
    pools, identity, bindings = set(), None, {}
    for directory in directories:
        directory = Path(directory)
        read = lambda name: json.loads((directory / name).read_text())
        plan, end, report = read('PLAN.json'), read('RUN-CLOSED.json'), read('SUMMARY.json')
        declaration = plan['declaration']
        current = (declaration['phase'], declaration['candidate']['expected_candidate_id'], declaration['rules_hash'])
        if identity is None:
            identity = current
        if current != identity:
            raise ValueError('不能混合阶段、候选或规则')
        pool = declaration['opponent_pool']
        expected_roots = {'dev': 4, 'confirm': 8}.get(declaration['phase'])
        if pool not in ('homogeneous', 'mixed') or pool in pools or expected_roots is None:
            raise ValueError('对手池或阶段不完整')
        pools.add(pool)
        expected_count = expected_roots * 80
        if (declaration['tables_per_stage'] != 10 or declaration['rounds_per_table'] != 16
                or declaration['seat_variants'] != [0, 1, 2, 3]
                or len(declaration['stage_roots']) != expected_roots
                or len(set(declaration['stage_roots'])) != expected_roots
                or len(plan['tasks']) != expected_count
                or end['complete'] is not True or end['closed'] != expected_count
                or end['planned'] != expected_count or len(end['results']) != expected_count
                or any(r['status'] != 'complete' for r in end['results'])
                or report['complete'] is not True or report['completed_table_instances'] != expected_count
                or report['plan_sha256'] != digest(directory / 'PLAN.json')
                or len(report['roots']) != expected_roots
                or {r['root'] for r in report['roots']} != set(declaration['stage_roots'])):
            raise ValueError('缺完整160单局矩阵、自然闭合账或绑定主报告')
        validate_task_ledger(plan, end)
        bindings[str(directory)] = {name: digest(directory / name) for name in ('PLAN.json', 'RUN-CLOSED.json', 'SUMMARY.json')}
        for root in report['roots']:
            variants = root['variants']
            if len(variants) != 4 or sorted(v['variant'] for v in variants) != [0, 1, 2, 3]:
                raise ValueError('缺四席变体')
            for v in variants:
                if set(v['arms']) != {'P0', 'Candidate'}:
                    raise ValueError('父子缺臂')
                for arm in ('P0', 'Candidate'):
                    counts = v['arms'][arm]
                    if counts['metrics']['hands'] != 160 or set(counts['white_bins']) != {'0', '1', '2'}:
                        raise ValueError('不是完整160单局及三白数层')
                    validate_counts(counts['metrics'])
                    white = sum_counts(counts['white_bins'].values())
                    if any(not math.isclose(white[k], counts['metrics'][k], abs_tol=1e-9, rel_tol=0) for k in FIELDS):
                        raise ValueError('累计取白分账未闭合')
            for index, cohort in enumerate(COHORTS):
                row = {'root': root['root'], 'pool': pool}
                for arm in ('P0', 'Candidate'):
                    row[arm] = sum_counts(v['arms'][arm]['metrics'] if index == 0
                                          else v['arms'][arm]['white_bins'][str(index - 1)] for v in variants)
                rows[cohort].append(row)
    if pools != {'homogeneous', 'mixed'}:
        raise ValueError('缺两池')
    return {'schema': 'astra-stage160-role-exposure/1', 'complete': True,
            'phase': identity[0], 'candidate_id': identity[1], 'rules_hash': identity[2],
            'cohorts': {k: describe_roots(v) for k, v in rows.items()},
            'source_reports': bindings, 'reporter_sha256': digest(__file__),
            'statistics_source_sha256': digest(Path(__file__).with_name('summarize160.py')),
            'scope': '付款总额与角色单局分母分别列账；根内四席合计后求条件率；未知根不筛掉授区间',
            'interpretation': '庄闲和累计取白受策略影响，条件率不是因果防守/速度；总比率差与根比率差均值不同',
            'original_gates_unchanged': True, 'strength_or_production_admission': False}


def main():
    """只生成新补充报告，不覆盖原件，不启动桌赛、玩家或发布。"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--runs', nargs=2, required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    out = Path(args.out)
    if out.exists():
        raise ValueError('不覆盖旧角色报告')
    report = summarize(args.runs)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'complete': True, 'roots': report['cohorts']['all']['independent_roots'],
                      'candidate_id': report['candidate_id'], 'original_gates_unchanged': True}))


if __name__ == '__main__':
    main()
