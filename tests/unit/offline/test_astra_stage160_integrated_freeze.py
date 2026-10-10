"""实际集成来源、原参数与新完整阶段不能借旧实验身份或资格。"""
import copy
import hashlib
import importlib.util
from pathlib import Path

import pytest

FILE = Path(__file__).resolve().parents[3] / 'tools/research/astra-evolution-2026-10-10/freeze_integrated160.py'
spec = importlib.util.spec_from_file_location('integrated_freeze_test', FILE)
freeze = importlib.util.module_from_spec(spec)
spec.loader.exec_module(freeze)


def inputs(phase='dev', pool='homogeneous'):
    params = {'samples': 32, 'normal_draw_depth': 3, 'max_extra_seconds': 1.2}
    identity = {'params': params, 'rules_source_hash': 'rules', 'runtime_source_manifest': {'src/pure.py': 'a' * 64}}
    cid = hashlib.sha256(freeze.canonical(identity)).hexdigest()
    execution = {'schema': 'paired-integrated-execution/1', 'candidate_id': cid,
                 'source_identity': identity, 'audit': 'bounded-runtime-audit-revision-003',
                 'clock': 'SystemClock host monotonic seconds', 'compute_settings': {'workers': 10},
                 'execution_identity_does_not_grant_admission': True}
    eid = hashlib.sha256(freeze.canonical(execution)).hexdigest()
    delivery = {'candidate_id': cid, 'execution_id': eid, 'algorithm_params': params,
                'rules_source_hash': 'rules', 'runtime_root': '/synthetic/runtime',
                'factory_path': '/synthetic/runtime/factory.py', 'factory_sha256': 'b' * 64,
                'startup_admitted': False, 'strength_admission': False, 'effects_inherited': False}
    manifest = {'candidate_id': cid, 'execution_id': eid, 'source_identity': identity,
                'compute_settings': {'workers': 10}, 'startup_admitted': False, 'strength_admission': False}
    base = {'candidate': {'params': params}, 'rules_hash': 'rules', 'tables_per_stage': 10,
            'rounds_per_table': 16, 'seat_variants': [0, 1, 2, 3], 'workers': 10,
            'phase': phase, 'opponent_pool': pool, 'stage_roots': [f'old-{i}' for i in range(4 if phase == 'dev' else 8)],
            'confirmation_gate': {'floor': 1}}
    return base, delivery, manifest


@pytest.mark.parametrize('phase', ['dev', 'confirm'])
@pytest.mark.parametrize('pool', ['homogeneous', 'mixed'])
def test_integrated_actual_root_new_identity_and_complete_fresh_seed_cohort(phase, pool):
    base, delivery, manifest = inputs(phase, pool); original = copy.deepcopy(base)
    d = freeze.integrated_declaration(base, delivery, manifest, schedule={'initial_workers': 1}, created_at=0.)
    assert base == original
    assert len(d['stage_roots']) == (4 if phase == 'dev' else 8)
    assert not set(d['stage_roots']) & set(base['stage_roots'])
    assert d['runtime_root'] == delivery['runtime_root']
    assert d['candidate']['expected_candidate_id'] == delivery['candidate_id']
    assert d['candidate_execution_id'] == delivery['execution_id']
    assert d['candidate']['auxiliary_files'] == {'/synthetic/runtime/src/pure.py': 'a' * 64}
    assert d['confirmation_gate'] == base['confirmation_gate']
    assert not d['inherits_v1_or_fast_v2_effect']


@pytest.mark.parametrize('fault', ['candidate', 'execution', 'admission', 'inheritance',
                                 'params', 'rules', 'short', 'missing_root'])
def test_unbound_changed_or_prematurely_admitted_candidate_is_rejected(fault):
    base, delivery, manifest = inputs()
    if fault == 'candidate': delivery['candidate_id'] = 'bad'
    elif fault == 'execution': delivery['execution_id'] = manifest['execution_id'] = 'bad'
    elif fault == 'admission': delivery['startup_admitted'] = True
    elif fault == 'inheritance': delivery['effects_inherited'] = True
    elif fault == 'params': base['candidate'] = {'params': {'max_extra_seconds': 3}}
    elif fault == 'rules': base['rules_hash'] = 'other'
    elif fault == 'short': base['rounds_per_table'] = 8
    elif fault == 'missing_root': base['stage_roots'].pop()
    with pytest.raises(ValueError):
        freeze.integrated_declaration(base, delivery, manifest, schedule={}, created_at=0.)
