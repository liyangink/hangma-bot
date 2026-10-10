"""快速版必须另立身份、完整新根和原预算，不能继承旧效果。"""
import copy
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
FILE = ROOT / 'tools/research/astra-evolution-2026-10-10/freeze_fast160.py'
spec = importlib.util.spec_from_file_location('fast_freeze_test', FILE)
freeze = importlib.util.module_from_spec(spec)
spec.loader.exec_module(freeze)


def inputs(phase='dev', pool='homogeneous'):
    """构造可重算的身份，测试不宣称实际native或候选性能已验证。"""
    params = {'samples': 32, 'normal_draw_depth': 3, 'minimum_extra_seconds': 1.2,
              'max_extra_seconds': 1.2, 'seed': 2026101037}
    identity = {'factory_sha256': 'a' * 64, 'model_sha256': 'b' * 64,
                'export_adapter_sha256': 'c' * 64, 'native_binding_sha256': 'd' * 64,
                'actual_native_binding': {'manifest_sha256': 'e' * 64}, 'params': params}
    cid = freeze.digest(freeze.canonical(identity))
    proof = {'candidate_id': cid, 'candidate_identity': identity, 'assembly_sha256': 'f' * 64}
    frozen = {'candidate_id': cid, 'execution_id': freeze.digest(freeze.canonical(proof)),
              'actual_source_proof': proof, 'params': params,
              'runtime_files': {'paired_continuation_policy.py': 'a' * 64,
                                'paired_continuation_model.py': 'b' * 64,
                                'export_adapter.py': 'c' * 64,
                                'native_binding.py': 'd' * 64, 'assembly.py': 'f' * 64}}
    count = 4 if phase == 'dev' else 8
    base = {'tables_per_stage': 10, 'rounds_per_table': 16, 'seat_variants': [0, 1, 2, 3],
            'phase': phase, 'opponent_pool': pool, 'stage_roots': [f'old-{i}' for i in range(count)],
            'workers': 10, 'cpu_cores': 14, 'candidate': {'params': params},
            'frozen_files': {'old-source': 'old-sha'},
            'development_gate': {'highfan_income': 0}, 'confirmation_gate': {'net_lower': 0},
            'evaluation_clock_mode': 'original-deadlines'}
    return base, frozen


@pytest.mark.parametrize('phase', ['dev', 'confirm'])
@pytest.mark.parametrize('pool', ['homogeneous', 'mixed'])
def test_new_complete_roots_and_identity_keep_original_gate_budget_and_sources(phase, pool, tmp_path):
    base, frozen = inputs(phase, pool)
    original = copy.deepcopy(base)
    result = freeze.build_declaration(base, frozen, tmp_path, created_at=1.)
    assert base == original
    assert len(result['stage_roots']) == (4 if phase == 'dev' else 8)
    assert not set(result['stage_roots']) & set(base['stage_roots'])
    assert result['candidate']['expected_candidate_id'] == frozen['candidate_id']
    assert result['candidate']['params'] == base['candidate']['params']
    assert len(result['candidate']['auxiliary_files']) == 3
    assert result['evaluated_parent_policy_tag'] == 'P0'
    assert not result['inherits_v1_effect_or_release_admission']
    for key in ('development_gate', 'confirmation_gate', 'evaluation_clock_mode'):
        assert result[key] == base[key]
    assert result['frozen_files']['old-source'] == 'old-sha'


@pytest.mark.parametrize('fault', ['candidate_id', 'execution_id', 'params', 'model', 'export',
                                 'native_binding', 'missing_assembly', 'short_stage',
                                 'seat_variants', 'missing_root', 'duplicate_root', 'over_cpu'])
def test_unbound_identity_parameters_sources_and_incomplete_stage_are_rejected(fault, tmp_path):
    base, frozen = inputs()
    if fault == 'candidate_id': frozen['candidate_id'] = '0' * 64
    elif fault == 'execution_id': frozen['execution_id'] = '0' * 64
    elif fault == 'params': base['candidate'] = {'params': dict(frozen['params'], max_extra_seconds=1.3)}
    elif fault == 'model': frozen['runtime_files']['paired_continuation_model.py'] = '0' * 64
    elif fault == 'export': frozen['runtime_files']['export_adapter.py'] = '0' * 64
    elif fault == 'native_binding': frozen['runtime_files']['native_binding.py'] = '0' * 64
    elif fault == 'missing_assembly': frozen['runtime_files'].pop('assembly.py')
    elif fault == 'short_stage': base['rounds_per_table'] = 8
    elif fault == 'seat_variants': base['seat_variants'] = [0]
    elif fault == 'missing_root': base['stage_roots'].pop()
    elif fault == 'duplicate_root': base['stage_roots'][1] = base['stage_roots'][0]
    elif fault == 'over_cpu': base['workers'] = 12
    with pytest.raises(ValueError):
        freeze.build_declaration(base, frozen, tmp_path, created_at=1.)
