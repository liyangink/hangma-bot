"""收尾字段误读后的纯读核验；不重跑20续打或139候选评分。

原run.py和终端KeyError保持；从闭合压缩流、各臂结果、实际推进和原
全座位公开观察恢复工程收据。不能恢复原进程未保存的计时/构造费用，记未知。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t60-t59-natural-same-start-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from collections import Counter
from pathlib import Path
import gzip
import hashlib
import json
import math

from prepare import HERE, canonical, pin, save


def read(path):
    return json.loads(path.read_text())


def rows(path):
    with gzip.open(path, 'rt') as stream:
        return [json.loads(line) for line in stream]


def main():
    plan = read(_project_file(_PROJECT_ROOT, HERE / 'PREPARED.json'))
    start = read(_project_file(_PROJECT_ROOT, HERE / 'START.json'))
    assert start['prepared_sha256'] == pin(_project_file(_PROJECT_ROOT, HERE / 'PREPARED.json'))['sha256']
    assert start['run_sha256'] == pin(_project_file(_PROJECT_ROOT, HERE / 'run.py'))['sha256']
    for name, digest in plan['files'].items():
        assert pin(Path(name)) == digest, name
    assert not (_project_file(_PROJECT_ROOT, HERE / 'CLOSURE.json')).exists()
    with gzip.open(_project_file(_PROJECT_ROOT, HERE / 'SOURCE-MATERIALS.json.gz'), 'rt') as stream:
        material = json.load(stream)['roots']
    decisions, events, views = (rows(_project_file(_PROJECT_ROOT, HERE / name)) for name in
        ('decisions.jsonl.gz', 'events.jsonl.gz', 'views.jsonl.gz'))
    assert len(material) == 4 and len(decisions) == 625
    by_sha = {}
    for captured in views:
        raw = canonical(captured['view'])
        assert captured['schema'] == 'vip-scoring-input-view/1'
        assert len(raw) == captured['json_bytes']
        assert hashlib.sha256(raw).hexdigest() == captured['view_sha256']
        assert captured['view_sha256'] not in by_sha
        by_sha[captured['view_sha256']] = captured
    assert not any(e['event'] == 'batch_failed' for e in events)
    counters = Counter((e['event'], e.get('status')) for e in events)
    assert counters['continuation_start', None] == 20
    assert counters['continuation_advance', 'advance_pending'] == counters['continuation_advance', 'advanced']
    assert counters['recovery_advance', 'advance_pending'] == counters['recovery_advance', 'advanced']
    seen_calls, used_views, action_scores = set(), set(), 0
    root_results = []
    for root in material:
        directory = _project_file(_PROJECT_ROOT, HERE / root['root_id'].replace(':', '-'))
        recovery = read(directory / 'RECOVERY.json')
        assert recovery['status'] == 'recovered' and recovery['full_target_observations_equal']
        assert recovery['source_window'] == root['source_window']
        result = read(directory / 'ROOT-RESULT.json')
        assert len(result['results']) == 5
        nets = {}
        for arm in plan['arm_order']:
            small = read(directory / (arm + '-RESULT.json'))
            assert small == next(r for r in result['results'] if r['arm'] == arm)
            outcome = read(directory / (arm + '-outcome.json'))
            assert outcome['status'] == 'complete' and outcome['completed_hands'] == 1
            assert all(value == 0 for value in outcome['runtime_counts'].values())
            settlement = small['settlement']
            assert sum(settlement['score_delta']) == 0
            assert [a + d for a, d in zip(settlement['scores_before'], settlement['score_delta'])] == settlement['scores_after']
            assert outcome['final_scores'] == settlement['scores_after']
            assert small['focal_net_score'] == settlement['score_delta'][root['focal_seat']]
            nets[arm] = small['focal_net_score']
            audited = [r for r in decisions if r['root_id'] == root['root_id'] and r['arm'] == arm]
            assert len(audited) == small['actual_policy_decisions'] == len(outcome['decisions'])
            targets = [r for r in audited if r['window_key'] == root['source_window']]
            assert len(targets) == 1 and targets[0]['observation'] == root['focal_observation']
            for audit, actual in zip(audited, outcome['decisions']):
                assert audit['status'] == 'chosen' and not any('action_value_failed' in x for x in audit['degraded_reasons'])
                assert audit['window_key'] == actual['window_key'] and audit['seat'] == actual['seat']
                expected_key = audit['selected_action_key']
                if arm in ('B', 'D') and audit['window_key'] == root['source_window']:
                    expected_key = root['child_first'] if arm == 'B' else root['parent_first']
                assert actual['legal'] and actual['fallback_reason'] is None and actual['action_key'] == expected_key
                assert expected_key in audit['legal_action_keys']
                if audit.get('focal_vip'):
                    assert audit['c_self_scored'] and len(audit['scoring_calls']) == 1
                    call = audit['scoring_calls'][0]
                    assert call['status'] == 'SCORED' and call['score_completed'] and call['full_legal_keys']
                    assert call['actual_score_calls'] == 1 and call['cumulative_failed_calls'] == 0
                    receipt = call['input_capture']
                    assert receipt['saved_before_score'] and receipt['error'] is None
                    assert receipt['store_call_no'] not in seen_calls
                    seen_calls.add(receipt['store_call_no'])
                    captured = by_sha[receipt['view_sha256']]
                    assert captured['json_bytes'] == receipt['json_bytes']
                    used_views.add(receipt['view_sha256'])
                    keys = [a['action_key'] for a in captured['view']['actions']]
                    assert set(keys) == set(call['scored_action_keys']) == set(audit['legal_action_keys'])
                    assert len(keys) == len(call['scored_action_keys']) == len(audit['candidates'])
                    assert all(type(c['score']) in (int, float) and math.isfinite(c['score']) for c in audit['candidates'])
                    action_scores += len(keys)
                    first = sorted(audit['candidates'], key=lambda c: (-c['score'], c['action_key']))[0]['action_key']
                    assert first == audit['selected_action_key']
                    assert 0 < call['candidate_operations'] <= plan['child_identity']['params']['max_operations']
            target = next(x for x in outcome['decisions'] if x['window_key'] == root['source_window'])
            assert target['action_key'] == small['executed_first']
            assert small['force_count'] == (1 if arm in ('B', 'D') else 0)
            if arm != 'R18':
                actual_scores = {c['action_key']: {'score': c['score'], 'trace': c['trace']['detail']}
                                 for c in targets[0]['candidates']}
                expected_scores = ({c['action_key']: {'score': c['score'], 'trace': c['trace']}
                                    for c in root['expected_child_scores']} if arm in ('C', 'D')
                                   else root['expected_parent_scores'])
                assert canonical(actual_scores) == canonical(expected_scores)
                assert targets[0]['scoring_execution']['input_capture']['view_sha256'] == root['expected_input_sha256']
            advances = [e for e in events if e['event'] == 'continuation_advance' and
                        e['root_id'] == root['root_id'] and e['arm'] == arm and e['status'] == 'advanced']
            assert len(advances) == small['successful_advances']
            assert [(c['window_key'], c['action_key']) for e in advances for c in e['choices']] == [
                (d['window_key'], d['action_key']) for d in outcome['decisions']]
            if arm == 'P':
                original = [row for group in root['original_hand_suffix'] for row in group]
                assert [(r['window_key'], r['selected_action_key'], r['observation']) for r in audited] == [
                    (r['window_key'], r['selected_action_key'], r['observation']) for r in original]
        deltas = {name: nets[name] - nets['P'] for name in ('C', 'B', 'D', 'R18')}
        deltas['C_minus_B'] = nets['C'] - nets['B']
        assert result['deltas'] == deltas
        root_results.append({'root_id': root['root_id'], 'mother_root': root['mother_root'],
            'category': root['category'], 'nets': nets, 'deltas': deltas,
            'original_parent_full_tail_exact': True})
    assert seen_calls == set(range(1, 140)) and used_views == set(by_sha)
    files = {str(p.relative_to(HERE)): pin(p) for p in sorted(HERE.rglob('*'))
             if p.is_file() and p.name not in ('CLOSURE-RECOVERY.json', 'ROOT-READBACK.json')}
    output = {'schema': 't60-root-pure-read-closure-recovery/1', 'complete': True,
        'original_runner_exit': 1, 'original_runner_error': "KeyError: 'terminal_valid' after20 complete continuations",
        'return_contract': 'ScoringInputCapture.finish() returns costs with nested terminal; original read wrong level',
        'original_runner_unchanged_no_business_retry': True, 'source_stable': True,
        'completed_actual_continuations': 20, 'recovered_original_mother_sources': 4,
        'actual_decision_rows': len(decisions), 'actual_candidate_score_calls': len(seen_calls),
        'actual_action_scores_read': action_scores, 'unique_actual_full_inputs_verified': len(by_sha),
        'capture_closed_stream_redecoded_and_all_receipts_reconciled': True,
        'old_in_memory_capture_timing_costs': None, 'old_in_memory_constructor_counts': None,
        'recorded_public_advance_counts': {str(k): v for k, v in counters.items()},
        'roots': root_results, 'files': files,
        'new_scores_world_advances_tables_models_in_recovery': 0,
        'normal_r18_fallbacks_in20_actual_continuations': 0,
        'strength_or_online_release': False}
    save(_project_file(_PROJECT_ROOT, HERE / 'CLOSURE-RECOVERY.json'), output)
    print({k: output[k] for k in ('complete', 'completed_actual_continuations',
        'actual_candidate_score_calls', 'unique_actual_full_inputs_verified', 'actual_action_scores_read')})


if __name__ == '__main__':
    main()
