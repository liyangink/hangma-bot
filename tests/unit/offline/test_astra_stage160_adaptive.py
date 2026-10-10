"""一槽与十槽交接只由自然闭合或经核验的资源释放触发。"""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

DIRECTORY = Path(__file__).resolve().parents[3] / 'tools/research/astra-evolution-2026-10-10'
sys.path.insert(0, str(DIRECTORY))
spec = importlib.util.spec_from_file_location('adaptive160_test', DIRECTORY / 'stage160_adaptive.py')
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


def setup_schedule(tmp_path, *, status='confirmation_running', passed=None):
    source = tmp_path / 'pipeline.py'; source.write_text('# fixed source\n')
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    state = {'pipeline_sha256': digest, 'candidate_id': 'old-candidate', 'gates_sha256': 'old-gate',
             'status': status, 'confirmation_stage_gate_pass': passed,
             'commands': [{'status': 'complete', 'exit_code': 0}]}
    state_path = tmp_path / 'state.json'; state_path.write_text(json.dumps(state))
    return {'initial_workers': 1, 'released_workers': 10, 'source_exec_session_id': 35427,
            'source_pipeline_path': str(source), 'source_pipeline_sha256': digest,
            'source_state_path': str(state_path), 'source_candidate_id': 'old-candidate',
            'source_gates_sha256': 'old-gate', 'release_file': str(tmp_path / 'release.json')}


@pytest.mark.parametrize('status,passed', [('confirmation_running', None),
    ('confirmation_reporting', None), ('dependency_failed', False),
    ('confirmation_closed_reliability_review_pending', True)])
def test_running_ambiguous_failure_and_positive_gate_do_not_expand(status, passed, tmp_path):
    assert driver.expansion_evidence(setup_schedule(tmp_path, status=status, passed=passed)) is None


def test_original_negative_after_all_commands_join_can_expand(tmp_path):
    schedule = setup_schedule(tmp_path, status='confirmation_closed_reliability_review_pending', passed=False)
    assert driver.expansion_evidence(schedule)['kind'] == 'original_confirmation_negative_natural_join'


@pytest.mark.parametrize('kind', ['pending_command', 'bad_exit', 'empty_commands', 'state_identity', 'source_drift'])
def test_missing_join_or_binding_blocks_expansion(kind, tmp_path):
    schedule = setup_schedule(tmp_path, status='confirmation_closed_reliability_review_pending', passed=False)
    path = Path(schedule['source_state_path']); state = json.loads(path.read_text())
    if kind == 'pending_command': state['commands'][0]['status'] = 'running'
    elif kind == 'bad_exit': state['commands'][0]['exit_code'] = 1
    elif kind == 'empty_commands': state['commands'] = []
    elif kind == 'state_identity': state['candidate_id'] = 'other'
    elif kind == 'source_drift': Path(schedule['source_pipeline_path']).write_text('# changed\n')
    path.write_text(json.dumps(state))
    if kind in ('state_identity', 'source_drift'):
        with pytest.raises(ValueError): driver.expansion_evidence(schedule)
    else:
        assert driver.expansion_evidence(schedule) is None


@pytest.mark.parametrize('fault', [None, 'bool_exit', 'wrong_session', 'missing_slots', 'bad_pipeline'])
def test_manual_release_requires_actual_handle_binding_and_zero_exit(fault, tmp_path):
    schedule = setup_schedule(tmp_path)
    release = {'schema': 'astra-stage160-cpu-release/1', 'source_exec_session_id': 35427,
               'source_pipeline_sha256': schedule['source_pipeline_sha256'],
               'source_terminal_exit_code': 0, 'heavy_slots_released': 10}
    if fault == 'bool_exit': release['source_terminal_exit_code'] = False
    elif fault == 'wrong_session': release['source_exec_session_id'] += 1
    elif fault == 'missing_slots': release.pop('heavy_slots_released')
    elif fault == 'bad_pipeline': release['source_pipeline_sha256'] = 'other'
    Path(schedule['release_file']).write_text(json.dumps(release))
    if fault:
        with pytest.raises(ValueError): driver.expansion_evidence(schedule)
    else:
        assert driver.expansion_evidence(schedule)['kind'] == 'root_verified_release'


def test_less_than_eleven_core_budget_cannot_overlap_old_ten(tmp_path):
    schedule = setup_schedule(tmp_path)
    with pytest.raises(ValueError):
        driver.verify_schedule({'workers': 10, 'cpu_cores': 13, 'worker_schedule': schedule})
    assert driver.verify_schedule({'workers': 10, 'cpu_cores': 14, 'worker_schedule': schedule}) == schedule
