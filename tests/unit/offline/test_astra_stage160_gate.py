"""完整独立根门：不能以局部活动或相关变体替代两池收益及保护。"""
import copy
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


DIRECTORY = Path(__file__).resolve().parents[3] / 'tools/research/astra-evolution-2026-10-10'
sys.path.insert(0, str(DIRECTORY))
spec = importlib.util.spec_from_file_location('astra_gate_test', DIRECTORY / 'gate160.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


LIMITS = {'independent_roots': 8, 'pool_roots': 4, 'positive_roots_minimum': 2,
          'each_pool_positive_roots_minimum': 1, 'actual_changed_windows_minimum': 1,
          'mean_highfan_income_delta_minimum': 0, 'mean_multiwhite_income_delta_minimum': 0}


def roots():
    return {pool: [{'root': f'{pool}-{i}', 'mean_delta_four_correlated_variants':
                   {'net': 1.0, 'changed_windows': 0.25, 'highfan_income': 0,
                    'multiwhite_income': 0, 'place_points': 0}} for i in range(4)]
            for pool in ('homogeneous', 'mixed')}


def test_full_independent_roots_can_pass_but_do_not_grant_production():
    report = gate.evaluate_gates('development', {'development': LIMITS}, roots())
    assert report['effect_gate_pass'] and not report['production_admission']
    assert report['root_statistics']['net']['independent_roots'] == 8


@pytest.mark.parametrize('kind', ['missing', 'duplicate', 'correlated_variants'])
def test_missing_duplicate_or_correlated_roots_cannot_pass(kind):
    rows = roots()
    if kind == 'missing':
        rows['mixed'].pop()
    elif kind == 'duplicate':
        rows['mixed'][0]['root'] = rows['homogeneous'][0]['root']
    else:
        rows = {p: [dict(r, root=f"{r['root']}-v{v}") for r in rr for v in range(4)]
                for p, rr in rows.items()}
    with pytest.raises(ValueError, match='独立根'):
        gate.evaluate_gates('development', {'development': LIMITS}, rows)


def test_one_pool_zero_and_highfan_loss_fail_even_with_activity_and_positive_total():
    rows = copy.deepcopy(roots())
    for r in rows['mixed']:
        r['mean_delta_four_correlated_variants']['net'] = 0
    rows['homogeneous'][0]['mean_delta_four_correlated_variants']['highfan_income'] = -1
    report = gate.evaluate_gates('development', {'development': LIMITS}, rows)
    assert not report['effect_gate_pass']
    assert not report['checks']['positive_roots_each_pool']
    assert not report['checks']['highfan_income']
    assert report['checks']['mean_net_positive'] and report['checks']['actual_activity']


def test_actual_choose_overrun_is_visible_even_when_model_reports_soft_cap(tmp_path):
    import json
    details = {'candidate_id': 'frozen', 'reason': 'enhancement_deadline',
               'original_enhancement_deadline_monotonic': 801.4,
               'extra_elapsed_seconds': 1.2,
               'model': {'complete': False, 'completed_pairs': 27}}
    (tmp_path / 'FOCAL.json').write_text(json.dumps([
        {'details': details, 'changed': False, 'choose_seconds': 2.0}]))
    plan = {'declaration': {'candidate': {'expected_candidate_id': 'frozen'}},
            'tasks': [{'arm': 'Candidate', 'out': str(tmp_path)}]}
    report = gate.activity_audit(plan, SimpleNamespace(enhancement_fraction=0.5, fallback_fraction=0.7))
    assert report['choose_over_original_fallback_span'] == 1
    assert report['complete_models'] == 0 and report['completed_pair_counts'] == {'27': 1}


def test_confirmation_uses_independent_ci_floor_and_does_not_grant_production():
    limits = {'independent_roots': 16, 'pool_roots': 8, 'mean_net_delta_per160_minimum': 1,
              'mean_place_points_delta_minimum': 0,
              'root_bootstrap_95_highfan_income_lower_minimum': -20,
              'root_bootstrap_95_multiwhite_income_lower_minimum': -20,
              'net_root_lower_quartile_minimum': -20}
    rows = roots()
    for pool, rr in rows.items():
        rr.extend([dict(copy.deepcopy(r), root=f"{r['root']}-new") for r in rr])
    report = gate.evaluate_gates('confirmation', {'confirmation': limits}, rows)
    assert report['effect_gate_pass'] and not report['production_admission']
    rows['mixed'][0]['mean_delta_four_correlated_variants']['net'] = -100
    report = gate.evaluate_gates('confirmation', {'confirmation': limits}, rows)
    assert not report['checks']['net_lower_strictly_positive']
