"""实际160单局风险不由四席均值替代；重采样保持根和并列范围。"""
import importlib.util
import hashlib
import json
from pathlib import Path

import pytest

FILE = Path(__file__).resolve().parents[3] / 'tools/research/astra-evolution-2026-10-10/distribution160.py'
spec = importlib.util.spec_from_file_location('astra_distribution_test', FILE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def root(name='one', values=None):
    return {'root': name, 'pool': 'homogeneous', 'net_deltas': values or [-110, 35, -47, 278],
            'rank_changes': ['same_interval'] * 4}


def test_positive_root_mean_does_not_hide_negative_actual_stage_tail():
    report = module.distribution([root()])
    assert report['root_mean_net_delta']['mean'] == 39
    assert report['actual_160_variant_net_delta']['q25'] == -62.75
    assert report['actual_160_variant_net_delta']['negative'] == 2
    assert report['root_cluster_stratified_95_intervals'] is None


def test_related_variants_and_duplicate_roots_not_independent_samples():
    with pytest.raises(ValueError, match='重复'):
        module.distribution([root(), root()])
    with pytest.raises(ValueError, match='四席'):
        module.distribution([root(values=[1])])


def test_cluster_sampling_reports_roots_and_retains_zero_variants():
    report = module.distribution([root('a', [0, 0, 4, 0]), root('b', [0, 0, 0, 0])], resamples=1000)
    assert report['independent_roots'] == 2 and report['actual_160_variant_net_delta']['count'] == 8
    assert report['actual_160_variant_net_delta']['zero'] == 7
    assert report['root_cluster_stratified_95_intervals']['negative_variant_fraction'] == [0, 0]


@pytest.mark.parametrize('parent,child,expected', [([2, 2], [1, 1], 'strictly_better'),
    ([2, 2], [3, 3], 'strictly_worse'), ([2, 3], [3, 4], 'overlap_ambiguous'),
    ([2, 3], [2, 3], 'same_interval')])
def test_tied_rank_intervals_are_not_forced_to_midpoint(parent, child, expected):
    assert module.rank_change(parent, child) == expected


def pool_files(path, pool, phase='dev', candidate='frozen'):
    path.mkdir()
    names = [f'{pool}-{i}' for i in range(4)]
    plan = {'declaration': {'phase': phase, 'opponent_pool': pool, 'rules_hash': 'rules',
                            'candidate': {'expected_candidate_id': candidate}, 'stage_roots': names},
            'tasks': [{}] * 320}
    raw = json.dumps(plan).encode()
    (path / 'PLAN.json').write_bytes(raw)
    variants = [{'variant': v, 'delta': {'net': 0}, 'ledger':
                 {a: {'focal_rank_interval': [2, 2]} for a in ('P0', 'Candidate')}} for v in range(4)]
    report = {'complete': True, 'completed_table_instances': 320,
              'plan_sha256': hashlib.sha256(raw).hexdigest(),
              'roots': [{'root': n, 'variants': variants} for n in names]}
    (path / 'SUMMARY.json').write_text(json.dumps(report))


@pytest.mark.parametrize('phase,candidate', [('confirm', 'frozen'), ('dev', 'other')])
def test_complete_reports_from_different_phases_or_candidates_cannot_be_mixed(tmp_path, phase, candidate):
    a, b = tmp_path / 'a', tmp_path / 'b'
    pool_files(a, 'homogeneous')
    pool_files(b, 'mixed', phase, candidate)
    with pytest.raises(ValueError, match='不能混合'):
        module.summarize([a, b])
