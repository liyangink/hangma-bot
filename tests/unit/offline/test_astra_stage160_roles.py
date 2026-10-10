"""角色分母、防止假压庄及独立根范围的补充统计合同。"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

DIRECTORY = Path(__file__).resolve().parents[3] / 'tools/research/astra-evolution-2026-10-10'
sys.path.insert(0, str(DIRECTORY))
spec = importlib.util.spec_from_file_location('roles160_test', DIRECTORY / 'roles160.py')
roles = importlib.util.module_from_spec(spec)
spec.loader.exec_module(roles)


def counts(dealer=40, idle_payment=240):
    """固定完整160单局的统计夹具，不伪装真实牌谱或策略效果。"""
    value = {k: 0 for k in roles.FIELDS}
    value.update(hands=160, dealer_hands=dealer, dealer_hu=10 if dealer else 0,
                 idle_hu=10 if dealer else 20, own_hu=20, other_dealer_hu=40,
                 ordinary_income=120, dealer_to_idle_payment=40 if dealer else 0,
                 idle_to_dealer_payment=idle_payment, idle_to_idle_payment=20,
                 own_draws_to_hu=100)
    value['net'] = 120 - value['dealer_to_idle_payment'] - idle_payment - 20
    return value


def test_less_idle_payment_can_hide_worse_payment_and_dealer_hu_per_idle_hand():
    parent, child = counts(), counts(dealer=60, idle_payment=210)
    assert child['idle_to_dealer_payment'] < parent['idle_to_dealer_payment']
    result = roles.rate_delta(parent, child)
    assert result['idle_to_dealer_payment_per_idle_hand'] > 0
    assert result['other_dealer_hu_per_idle_hand'] > 0
    assert result['own_dealer_hu_per_dealer_hand'] < 0


def test_zero_role_denominator_is_unknown_not_zero_or_missing_root():
    parent, child = counts(), counts(dealer=0)
    assert roles.rates(child)['dealer_to_idle_payment_per_dealer_hand'] is None
    report = roles.describe_roots([
        {'root': 'r1', 'pool': 'homogeneous', 'P0': parent, 'Candidate': child},
        {'root': 'r2', 'pool': 'mixed', 'P0': parent, 'Candidate': parent},
    ])
    stat = report['root_rate_delta_statistics']['dealer_to_idle_payment_per_dealer_hand']
    assert stat['values_in_root_order'] == [None, 0]
    assert stat['undefined_roots'] == 1
    assert stat['complete_root_statistics'] is None
    assert len(report['root_rows']) == 2


@pytest.mark.parametrize('fault', ['cash', 'impossible_role', 'nan', 'no_hu_draws'])
def test_inconsistent_accounting_does_not_generate_comparison(fault):
    value = counts()
    if fault == 'cash': value['net'] += 1
    elif fault == 'impossible_role': value['dealer_hands'] = 200
    elif fault == 'nan': value['idle_to_dealer_payment'] = float('nan')
    elif fault == 'no_hu_draws':
        value.update(own_hu=0, dealer_hu=0, idle_hu=0)
    with pytest.raises(ValueError): roles.rates(value)


def make_run(root, pool, *, candidate='same', phase='dev', heterogeneous=False):
    """生成只检验统计接口的合成完整矩阵，不调用规则或策略。"""
    root.mkdir()
    names = [pool + str(i) for i in range(4)]
    declaration = {'phase': phase, 'candidate': {'expected_candidate_id': candidate},
        'rules_hash': 'same-rules', 'opponent_pool': pool, 'stage_roots': names,
        'tables_per_stage': 10, 'rounds_per_table': 16, 'seat_variants': [0, 1, 2, 3]}
    tasks = [{'id': f'{r}:{v}:{t}:{a}', 'stage_root': r, 'seat_variant': v,
              'table_no': t, 'arm': a, 'candidate_id': candidate, 'rules_hash': 'same-rules'}
             for r in names for v in range(4) for t in range(10) for a in ('P0', 'Candidate')]
    plan = {'declaration': declaration, 'tasks': tasks}
    (root / 'PLAN.json').write_text(json.dumps(plan))
    end = {'complete': True, 'closed': 320, 'planned': 320,
           'results': [{'status': 'complete', 'task': t.copy()} for t in tasks]}
    (root / 'RUN-CLOSED.json').write_text(json.dumps(end))
    roots = []
    empty = {k: 0 for k in roles.FIELDS}
    for name in names:
        variants = []
        for variant in range(4):
            arms = {}
            for arm in ('P0', 'Candidate'):
                value = counts() if arm == 'P0' else counts(60, 210)
                if heterogeneous and arm == 'P0':
                    value = counts(20 if variant == 0 else 60)
                    value['dealer_to_idle_payment'] = 10 if variant == 0 else 40
                    value['net'] = 120 - value['dealer_to_idle_payment'] - 240 - 20
                arms[arm] = {'metrics': value,
                    'white_bins': {'0': value.copy(), '1': empty.copy(), '2': empty.copy()}}
            variants.append({'variant': variant, 'arms': arms})
        roots.append({'root': name, 'variants': variants})
    summary = {'complete': True, 'completed_table_instances': 320, 'roots': roots,
        'plan_sha256': hashlib.sha256((root / 'PLAN.json').read_bytes()).hexdigest()}
    (root / 'SUMMARY.json').write_text(json.dumps(summary))
    return root


def test_four_seats_are_combined_before_root_interval(monkeypatch, tmp_path):
    runs = [make_run(tmp_path / p, p) for p in ('homogeneous', 'mixed')]
    observed = []
    def inspect_roots(values):
        observed.append(list(values))
        return {'independent_roots': len(values)}
    monkeypatch.setattr(roles, 'root_statistics', inspect_roots)
    report = roles.summarize(runs)['cohorts']['all']
    assert report['independent_roots'] == 8
    assert report['actual_correlated_stage_variants'] == 32
    assert report['counts']['P0']['hands'] == 5120
    assert report['denominators']['P0']['idle_hands'] == 3840
    assert report['mean_count_delta_per_actual_160_stage']['idle_to_dealer_payment'] == -30
    assert observed and all(len(values) == 8 for values in observed)


def test_heterogeneous_seats_use_actual_combined_role_denominator(monkeypatch, tmp_path):
    runs = [make_run(tmp_path / p, p, heterogeneous=True) for p in ('homogeneous', 'mixed')]
    monkeypatch.setattr(roles, 'root_statistics', lambda v: {'independent_roots': len(v)})
    report = roles.summarize(runs)['cohorts']['all']
    # 一席10/20，其余三席40/60；总付款130/总庄局200=0.65，不能均值各席率。
    assert report['rates']['P0']['dealer_to_idle_payment_per_dealer_hand'] == .65
    assert report['root_rows'][0]['P0']['dealer_hands'] == 200
    delta = report['root_rate_delta_statistics']['dealer_to_idle_payment_per_dealer_hand']
    assert delta['values_in_root_order'] == pytest.approx([2 / 3 - .65] * 8)


@pytest.mark.parametrize('fault', ['missing_table', 'failed_table', 'candidate', 'phase', 'white_partition',
    'duplicate_closed', 'foreign_candidate_task', 'foreign_rule_task', 'matrix_duplicate', 'task_id_duplicate'])
def test_partial_or_incompatible_sources_are_rejected(fault, tmp_path):
    runs = [make_run(tmp_path / p, p) for p in ('homogeneous', 'mixed')]
    directory = runs[-1]
    if fault in ('missing_table', 'failed_table', 'duplicate_closed', 'foreign_candidate_task', 'foreign_rule_task'):
        path = directory / 'RUN-CLOSED.json'; data = json.loads(path.read_text())
        if fault == 'missing_table': data['closed'] -= 1
        elif fault == 'failed_table': data['results'][0]['status'] = 'failed'
        elif fault == 'duplicate_closed': data['results'][1] = copy.deepcopy(data['results'][0])
        elif fault == 'foreign_candidate_task': data['results'][0]['task']['candidate_id'] = 'other'
        else: data['results'][0]['task']['rules_hash'] = 'other-rules'
    elif fault in ('candidate', 'phase', 'matrix_duplicate', 'task_id_duplicate'):
        path = directory / 'PLAN.json'; data = json.loads(path.read_text())
        if fault == 'candidate': data['declaration']['candidate']['expected_candidate_id'] = 'other'
        elif fault == 'phase': data['declaration']['phase'] = 'confirm'
        elif fault == 'matrix_duplicate':
            data['tasks'][1].update({k: data['tasks'][0][k] for k in ('stage_root', 'seat_variant', 'table_no', 'arm')})
        else: data['tasks'][1]['id'] = data['tasks'][0]['id']
        if fault in ('matrix_duplicate', 'task_id_duplicate'):
            (directory / 'PLAN.json').write_text(json.dumps(data))
            main = directory / 'SUMMARY.json'; report = json.loads(main.read_text())
            report['plan_sha256'] = hashlib.sha256((directory / 'PLAN.json').read_bytes()).hexdigest()
            main.write_text(json.dumps(report))
    else:
        path = directory / 'SUMMARY.json'; data = json.loads(path.read_text())
        data['roots'][0]['variants'][0]['arms']['P0']['white_bins']['0']['hands'] -= 1
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError): roles.summarize(runs)
