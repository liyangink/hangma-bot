"""纯读18实际C臂和18既有B别名；核全输入、动作、费用和结算。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t76-joint-child-causal-preparation-1'

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
    return json.loads(Path(path).read_text())


def rows(path):
    with gzip.open(path, 'rt') as stream:
        return [json.loads(line) for line in stream]


def main():
    plan, start, closed = (read(_project_file(_PROJECT_ROOT, HERE / name)) for name in ['PREPARED.json', 'START.json', 'CLOSURE.json'])
    assert plan['planned_actual_C_arms'] == 18 and plan['planned_actual_B_arms'] == 0
    assert closed['complete'] and closed['source_stable'] and closed['error'] is None and not closed['cleanup_errors']
    assert start['prepared_sha256'] == pin(_project_file(_PROJECT_ROOT, HERE / 'PREPARED.json'))['sha256']
    assert start['runner_sha256'] == pin(_project_file(_PROJECT_ROOT, HERE / 'run.py'))['sha256']
    for name, digest in plan['files'].items():
        assert pin(name) == digest, name
    for name, digest in closed['files'].items():
        assert pin(_project_file(_PROJECT_ROOT, HERE / name)) == digest, name
    assert closed['scoring_input_capture']['terminal']['terminal_valid']
    with gzip.open(_project_file(_PROJECT_ROOT, HERE / 'SOURCE-MATERIALS.json.gz'), 'rt') as stream:
        material = json.load(stream)['roots']
    decisions, events, captured_views = (rows(_project_file(_PROJECT_ROOT, HERE / name)) for name in ['decisions.jsonl.gz', 'events.jsonl.gz', 'views.jsonl.gz'])
    assert len(material) == 18 and len({r['mother_root'] for r in material}) == 16
    actual = closed['actual_explicit_api_counts']
    assert len(decisions) == actual['actual_policy_decisions']
    assert actual['continuations_dispatched'] == actual['continuations_completed'] == 18
    assert actual['common_parent_B_aliases'] == 18
    by_sha = {}
    for captured in captured_views:
        raw = canonical(captured['view'])
        assert captured['schema'] == 'vip-scoring-input-view/1' and len(raw) == captured['json_bytes']
        assert hashlib.sha256(raw).hexdigest() == captured['view_sha256']
        assert captured['view_sha256'] not in by_sha
        by_sha[captured['view_sha256']] = captured
    assert not any(e['event'] == 'batch_failed' for e in events)
    event_counts = Counter((e['event'], e.get('status')) for e in events)
    assert event_counts['continuation_start', None] == event_counts['continuation_alias', None] == 18
    for prefix in ['continuation', 'recovery']:
        assert event_counts[prefix + '_advance', 'pending'] == event_counts[prefix + '_advance', 'advanced']
    calls, used, action_scores = set(), set(), 0
    results = []
    for root in material:
        directory = _project_file(_PROJECT_ROOT, HERE / root['root_id'].replace(':', '-'))
        recovered, result = (read(directory / name) for name in ['RECOVERY.json', 'ROOT-RESULT.json'])
        assert recovered['status'] == 'recovered' and recovered['full_target_observations_equal']
        assert recovered['source_window'] == root['source_window']
        assert set(result['results']) == {'C', 'B'}
        small, outcome, alias = (read(directory / name) for name in ['C-RESULT.json', 'C-outcome.json', 'B-RESULT.json'])
        assert small == result['results']['C'] and alias == result['results']['B']
        assert small['status'] == outcome['status'] == 'complete'
        assert small['actual_new_execution'] and small['force_count'] == 0 and outcome['completed_hands'] == 1
        assert all(value == 0 for value in outcome['runtime_counts'].values())
        settlement = small['settlement']
        assert sum(settlement['score_delta']) == 0
        assert [before + delta for before, delta in zip(settlement['scores_before'], settlement['score_delta'])] == settlement['scores_after'] == outcome['final_scores']
        assert small['focal_net_score'] == settlement['score_delta'][root['focal_seat']]
        audited = [d for d in decisions if d['root_id'] == root['root_id'] and d['arm'] == 'C']
        assert len(audited) == small['actual_policy_decisions'] == len(outcome['decisions'])
        targets = [d for d in audited if d['window_key'] == root['source_window']]
        assert len(targets) == 1 and targets[0]['observation'] == root['focal_observation']
        for audit, executed in zip(audited, outcome['decisions']):
            assert audit['status'] == 'chosen' and not any('action_value_failed' in reason for reason in audit['degraded_reasons'])
            assert audit['window_key'] == executed['window_key'] and audit['seat'] == executed['seat']
            assert executed['legal'] and executed['fallback_reason'] is None
            assert audit['selected_action_key'] == executed['action_key'] and executed['action_key'] in audit['legal_action_keys']
            if audit.get('focal_vip'):
                assert audit['c_self_scored'] and len(audit['scoring_calls']) == 1
                call = audit['scoring_calls'][0]
                assert call['status'] == 'SCORED' and call['score_completed'] and call['full_legal_keys']
                assert call['actual_score_calls'] == 1 and call['cumulative_failed_calls'] == 0
                receipt = call['input_capture']
                assert receipt['saved_before_score'] and receipt['error'] is None
                assert receipt['store_call_no'] not in calls
                calls.add(receipt['store_call_no'])
                captured = by_sha[receipt['view_sha256']]
                assert captured['json_bytes'] == receipt['json_bytes']
                used.add(receipt['view_sha256'])
                keys = [a['action_key'] for a in captured['view']['actions']]
                assert set(keys) == set(call['scored_action_keys']) == set(audit['legal_action_keys'])
                assert len(keys) == len(call['scored_action_keys']) == len(audit['candidates'])
                assert all(type(c['score']) in (int, float) and math.isfinite(c['score']) for c in audit['candidates'])
                action_scores += len(keys)
                assert sorted(audit['candidates'], key=lambda c: (-c['score'], c['action_key']))[0]['action_key'] == audit['selected_action_key']
                assert 0 < call['candidate_operations'] <= plan['child_identity']['params']['max_operations']
        target = next(d for d in outcome['decisions'] if d['window_key'] == root['source_window'])
        assert target['action_key'] == small['executed_first'] == root['child_first']
        actual_scores = {c['action_key']: {'score': c['score'], 'trace': c['trace']['detail']} for c in targets[0]['candidates']}
        assert canonical(actual_scores) == canonical(root['expected_child_scores'])
        assert targets[0]['scoring_execution']['input_capture']['view_sha256'] == root['expected_input_sha256']
        pending = [e for e in events if e['event'] == 'continuation_advance' and e['root_id'] == root['root_id'] and e['arm'] == 'C' and e['status'] == 'pending']
        advanced = [e for e in events if e['event'] == 'continuation_advance' and e['root_id'] == root['root_id'] and e['arm'] == 'C' and e['status'] == 'advanced']
        assert len(advanced) == small['successful_advances']
        assert [e['revision'] for e in pending] == [e['revision'] for e in advanced]
        assert [(c['window_key'], c['action_key']) for e in pending for c in e['choices']] == [(d['window_key'], d['action_key']) for d in outcome['decisions']]
        declaration = root['common_parent_B_alias']
        assert declaration is not None and alias['status'] == 'aliased_complete' and not alias['actual_new_execution']
        assert alias['actual_new_policy_decisions'] == alias['actual_new_score_calls'] == alias['actual_new_advances'] == 0
        assert alias['source_directory'] == declaration['directory'] and alias['source_arm'] == declaration['source_arm']
        source = Path(declaration['directory'])
        reference = read(source / (declaration['source_arm'] + '-RESULT.json'))
        baseline = read(source / 'ROOT-RESULT.json')
        assert reference == baseline['results'][declaration['source_arm']]
        assert pin(source / (declaration['source_arm'] + '-RESULT.json')) == alias['source_result_pin']
        assert reference['executed_first'] == alias['executed_first'] == root['child_first']
        assert reference['settlement'] == alias['settlement'] and reference['focal_net_score'] == alias['focal_net_score']
        parent = root['parent_closed_reference']
        assert parent == baseline['results']['P'] == result['parent_closed_reference']
        assert not result['P_new_execution'] and result['same_true_parent_after_first_B']
        assert result['C_minus_P'] == small['focal_net_score'] - parent['focal_net_score']
        assert result['B_minus_P'] == alias['focal_net_score'] - parent['focal_net_score']
        assert result['C_minus_B'] == small['focal_net_score'] - alias['focal_net_score']
        kind = 'draw' if settlement['is_draw'] else 'own_hu' if settlement['winner_seat'] == root['focal_seat'] else 'opponent_hu'
        results.append({'root_id': root['root_id'], 'mother_root': root['mother_root'], 'category': root['category'],
                        'parent_first': root['parent_first'], 'child_first': root['child_first'],
                        'parent_net': parent['focal_net_score'], 'B_net': alias['focal_net_score'], 'child_net': small['focal_net_score'],
                        'C_minus_P': result['C_minus_P'], 'B_minus_P': result['B_minus_P'], 'C_minus_B': result['C_minus_B'],
                        'child_terminal_kind': kind, 'child_fan': settlement['fan'],
                        'parent_fan': parent['settlement']['fan'], 'B_fan': alias['settlement']['fan'],
                        'B_new_execution': False})
    assert calls == set(range(1, actual['actual_vip_score_calls'] + 1)) and used == set(by_sha)
    assert len(by_sha) == closed['scoring_input_capture']['unique_views_saved']
    def stats(values):
        return {'windows': len(values), 'mothers': len({r['mother_root'] for r in values}),
                'child_better_equal_worse': [sum(r['C_minus_P'] > 0 for r in values), sum(r['C_minus_P'] == 0 for r in values), sum(r['C_minus_P'] < 0 for r in values)],
                'descriptive_C_minus_P_sum': sum(r['C_minus_P'] for r in values),
                'descriptive_B_minus_P_sum': sum(r['B_minus_P'] for r in values),
                'descriptive_C_minus_B_sum': sum(r['C_minus_B'] for r in values),
                'child_terminal_kinds': dict(Counter(r['child_terminal_kind'] for r in values)),
                'not_natural_frequency_or_table_mean': True}
    categories = {r['category'] for r in results}
    files = {str(p.relative_to(HERE)): pin(p) for p in sorted(HERE.rglob('*'))
             if p.is_file() and p.name != 'ROOT-READBACK.json' and '__pycache__' not in p.parts}
    output = {'schema': 't76-root-pure-read-closure/1', 'complete': True, 'source_stable': True,
              'actual_new_continuations': 18, 'old_B_reference_aliases': 18, 'old_P_reference_roots': 18,
              'actual_candidate_scores': len(calls), 'actual_full_inputs': len(by_sha),
              'actual_action_values_read': action_scores, 'all_aliases_inputs_receipts_advances_settlements_reconciled': True,
              'rows': results, 'descriptive_stats': stats(results),
              'by_public_category': {k: stats([r for r in results if r['category'] == k]) for k in categories},
              'files': files, 'normal_r18_fallbacks': 0, 'new_business_calls_in_readback': 0,
              'new_natural_tables_or_sources': 0, 'strength_or_release': False}
    save(_project_file(_PROJECT_ROOT, HERE / 'ROOT-READBACK.json'), output)
    print({key: output[key] for key in ['complete', 'actual_new_continuations', 'old_B_reference_aliases',
                                       'actual_candidate_scores', 'actual_full_inputs', 'descriptive_stats']})


if __name__ == '__main__':
    main()
