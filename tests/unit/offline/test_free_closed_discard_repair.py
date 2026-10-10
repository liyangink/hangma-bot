"""第19房真实两层动作链回归：同为摸牌阶段也可能已换行动座位。"""
import copy
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT / 'tools/offline/free_match/runtime/closed_discard_repair.py'
spec = importlib.util.spec_from_file_location('closed_discard_repair_test', TOOL)
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)
BASELINE = ROOT / '.private/lowwhite-160-20261009/free-takeover/repair-second-room/runtime-root/review/vip-route-2026-09-30/evidence/t199-four-step-execution-1/runtime/phase_rejection.py'


def fixture():
    """只取已脱敏公开观察、原合法根和动作审计；不含他家手牌。"""
    return json.loads((ROOT / 'tests/fixtures/offline/free19_closed_discard.json').read_text())


def prover():
    """经真实冻结 prove 执行补丁，不能只测试一个宽免条件。"""
    if not BASELINE.exists():
        pytest.skip('本机冻结原件缺失；座位条件和拒绝未知版本回归仍可运行')
    module = ModuleType('repaired_actual_phase_prover')
    exec(compile(repair.repaired_source(BASELINE.read_bytes()), '<repaired_actual_phase>', 'exec'),
         module.__dict__)
    return module.prove


def prove(fn, case):
    return fn(case['rejection'], case['records'], case['snapshots'],
              {tuple(k): v for k, v in case['post_counts']},
              {tuple(k): v for k, v in case['adapter_counts']})


def test_actual_complete_chain_proves_other_seat_draw_without_claiming_timeout():
    result = prove(prover(), fixture())
    assert result is not None
    assert result['classification'] == 'recovered_server_closed_discard'
    assert result['actual_outcome'] == 'SubmitRejectedClosed'
    assert result['adapter_closed_refresh_phase'] == 'draw'
    assert result['adapter_closed_authoritative_seq'] == 713
    assert result['authoritative_recovery_seq'] == 731
    assert result['recovery_actual_outcome'] == 'SubmitAccepted'
    assert result['clock_unknown'] and result['closure_reason_unknown']
    assert result['timely_send_margin_ms'] is None
    assert 'possible_missed_discard' in result['warning']


@pytest.mark.parametrize('turn', [3, -1, 4, True, False, '0', None])
def test_current_or_invalid_seat_draw_still_blocks(turn):
    case = fixture()
    case['snapshots'][1]['body']['snapshot']['turn'] = turn
    assert prove(prover(), case) is None


@pytest.mark.parametrize('index', [i for i in range(14) if i not in (5, 12)])
def test_each_action_record_is_required(index):
    case = fixture()
    case['records'].pop(index)
    # 两个应用层 outcome 作为原件谱系保留，不能冒称 prove 的必要条件。
    assert prove(prover(), case) is None


@pytest.mark.parametrize('index', range(3))
def test_each_authority_anchor_is_required(index):
    case = fixture()
    case['snapshots'].pop(index)
    assert prove(prover(), case) is None


@pytest.mark.parametrize('fault', ['not_applied', 'gap', 'wrong_round', 'wrong_seat',
                                 'applied_after_outcome', 'double_old_post', 'double_new_post',
                                 'double_old_adapter', 'double_new_adapter', 'invalid_root',
                                 'invalid_validation', 'wrong_wire', 'failed_recovery'])
def test_missing_or_inconsistent_proof_never_bypasses_gate(fault):
    case = copy.deepcopy(fixture())
    closed = case['snapshots'][1]
    if fault == 'not_applied': closed['applied'] = False
    elif fault == 'gap': closed['body']['gap'] = True
    elif fault == 'wrong_round': closed['body']['snapshot']['round_no'] += 1
    elif fault == 'wrong_seat': closed['body']['snapshot']['seat'] = 0
    elif fault == 'applied_after_outcome': closed['applied_at_monotonic_ns'] = case['records'][4]['monotonic_ns'] + 1
    elif fault.startswith('double_'):
        counts = case['post_counts' if fault.endswith('_post') else 'adapter_counts']
        seq = 710 if '_old_' in fault else 731
        next(r for r in counts if r[0][2] == seq)[1] = 2
    elif fault == 'invalid_root': case['records'][0]['payload']['rule_completeness'] = 'partial'
    elif fault == 'invalid_validation': case['records'][1]['payload']['legal'] = False
    elif fault == 'wrong_wire': case['records'][3]['payload']['body']['tile'] = '中'
    elif fault == 'failed_recovery': case['records'][11]['payload']['outcome_type'] = 'SubmitRejectedClosed'
    assert prove(prover(), case) is None


def test_unknown_baseline_is_rejected():
    with pytest.raises(ValueError, match='来源'):
        repair.repaired_source(b'unknown version')


@pytest.mark.parametrize('turn', [0, 1, 2, 3, -1, 4, True, False, '0', None])
def test_public_extra_condition_accepts_only_other_valid_draw_seats(turn):
    assert repair.is_other_seat_draw({'phase': 'draw', 'turn': turn},
                                    ('fixture-game', 4, 710, 'draw', 3)) is (
        type(turn) is int and 0 <= turn < 3)


def test_public_extra_condition_does_not_handle_other_phases_or_windows():
    assert not repair.is_other_seat_draw({'phase': 'response_peng', 'turn': 0},
                                        ('fixture-game', 4, 710, 'draw', 3))
    assert not repair.is_other_seat_draw({'phase': 'draw', 'turn': 0},
                                        ('fixture-game', 4, 710, 'response_chi', 3))
    assert not repair.is_other_seat_draw({'phase': 'draw', 'turn': 0}, ())
