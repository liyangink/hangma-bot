"""终态后纯读签收16完整桌、每次评分输入及结算；不重打或重评分。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t92-fixed-formula-natural-engineering-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
import gzip
import hashlib
import json
import math

from hangma_bot.offline.evaluation_results import read_results_jsonl
from hangma_bot.offline.vip_evaluation import FrozenRoot, audit_vip_batch

HERE = Path(__file__).resolve().parent


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def sha(path):
    """只读字节摘要，不以签收代替真实调用费用。"""
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def rows(path):
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        for line in stream:
            yield json.loads(line)


def distribution(values):
    """描述性分位数；毫秒，包含研究输入记录，不授线上时限。"""
    values = sorted(values)
    return {'n': len(values), 'p50_ms': values[(len(values)-1)//2],
            'p95_ms': values[math.ceil(len(values)*0.95)-1], 'max_ms': values[-1]}


def main():
    terminal = json.loads((_project_file(_PROJECT_ROOT, HERE/'PROCESS-TERMINAL.json')).read_text())
    assert terminal['exit_code'] == 0 and terminal['session_id'] == 36944
    out = _project_file(_PROJECT_ROOT, HERE/'run-1')
    plan = json.loads((_project_file(_PROJECT_ROOT, HERE/'PLAN.json')).read_text())
    start = json.loads((out/'START.json').read_text())
    summary = json.loads((out/'summary.json').read_text())
    assert summary['engineering_complete'] and summary['identity_stable'] and not summary['issues']
    assert summary['observed_result_rows'] == summary['actual_started_table_instances'] == 16
    assert summary['charged_table_instances'] == 16 and summary['completed_hands'] == 128
    assert summary['candidate_identity'] == plan['candidate_identity'] == start['candidate_identity']
    assert not summary['confirmation_claim'] and not summary['published']
    for path, expected in start['frozen_files'].items():
        assert sha(Path(path)) == expected, path
    for relative, digest in start['source_manifest'].items():
        copied = out/'code_snapshot'/relative
        assert copied.stat().st_size == digest['bytes'] and sha(copied) == digest['sha256'], relative
    assert sha(out/'RUNNER.py') == sha(_project_file(_PROJECT_ROOT, HERE/'run_engineering.py'))
    candidate_id = 'vip:'+plan['candidate_identity']['candidate_id']
    archive = {}
    for row in rows(out/'views.jsonl.gz'):
        raw = canonical(row['view'])
        digest = row['view_sha256']
        assert hashlib.sha256(raw).hexdigest() == digest and len(raw) == row['json_bytes']
        assert digest not in archive
        keys = [a['action_key'] for a in row['view']['actions']]
        assert keys and len(keys) == len(set(keys))
        archive[digest] = (len(raw), set(keys))
    calls, used, selected, operations = set(), set(), Counter(), []
    all_decisions = candidate_decisions = action_scores = 0
    latency = defaultdict(list)
    white_counts = Counter()
    views_per_root = Counter()
    for row in rows(out/'decisions.jsonl.gz'):
        all_decisions += 1
        assert row['status'] == 'chosen' and row['selected_action_key'] in row['legal_action_keys']
        if row['policy_id'] != candidate_id:
            continue
        candidate_decisions += 1
        assert row['c_self_scored'] and row['scoring_cumulative_failed_calls'] == 0
        assert not row['degraded_reasons']
        selected[row['selected_action_key'].split(':', 1)[0]] += 1
        white_counts[row['white_count']] += 1
        views_per_root[row['root_id']] += 1
        latency[row['phase']].append(row['policy_compute_ms_observed'])
        keys = [c['action_key'] for c in row['candidates']]
        assert len(keys) == len(set(keys)) and set(keys) == set(row['legal_action_keys'])
        assert row['candidates'][0]['action_key'] == row['selected_action_key']
        assert all(type(c['score']) in (int, float) and math.isfinite(c['score']) for c in row['candidates'])
        action_scores += len(keys)
        assert row['scoring_calls']
        for call in row['scoring_calls']:
            receipt = call['input_capture']
            assert call['status'] == 'SCORED' and call['score_completed'] and call['full_legal_keys']
            assert call['actual_score_calls'] == 1 and call['cumulative_failed_calls'] == 0
            assert receipt['saved_before_score'] and receipt['error'] is None
            seq = receipt['store_call_no']
            assert seq not in calls
            calls.add(seq)
            digest = receipt['view_sha256']
            assert digest in archive and archive[digest][0] == receipt['json_bytes']
            assert archive[digest][1] == set(call['scored_action_keys']) == set(keys)
            used.add(digest)
            assert type(call['candidate_operations']) is int and 0 <= call['candidate_operations'] <= plan['offline_max_operations']
            operations.append(call['candidate_operations'])
    capture = summary['scoring_input_capture']
    assert all_decisions == summary['decision_windows']
    assert capture['terminal']['terminal_valid'] and sha(out/'views.jsonl.gz') == capture['terminal']['compressed_sha256']
    assert len(archive) == capture['terminal']['verified_unique_views'] and used == set(archive)
    assert calls == set(range(1, capture['store_calls']+1))
    outcomes = read_results_jsonl(out/'results.jsonl')
    assert len(outcomes) == 16
    table_keys = set()
    by_match = {}
    for result in outcomes:
        seat = result.seat_permutation[0]
        arm = 'C' if result.policy_ids_by_seat[seat] == candidate_id else 'A'
        key = (result.scenario_id, result.seat_permutation, arm)
        assert key not in table_keys
        table_keys.add(key)
        assert result.status == 'complete' and not result.invalid_reasons
        assert result.expected_hands == result.completed_hands == 8
        assert result.scores_after is not None and result.scores_before is not None
        assert sum(result.scores_after) == sum(result.scores_before)
        assert result.runtime_counts is not None and all(
            getattr(result.runtime_counts, key) == 0
            for key in ('timeouts', 'illegal_choices', 'fallbacks', 'auto_actions', 'audit_missing'))
        by_match[result.result_id] = (result, arm)
    # 核验器的对手池语义不改；每个母根独立核验四座配对。
    root_audits = []
    for root_id in plan['root_ids']:
        subset = [r for r in outcomes if r.scenario_id == root_id]
        baseline_ids = {r.policy_ids_by_seat[r.seat_permutation[0]] for r in subset
                        if r.policy_ids_by_seat[r.seat_permutation[0]] != candidate_id}
        assert len(baseline_ids) == 1
        root = FrozenRoot(root_id, ((0,1,2,3),(1,2,3,0),(2,3,0,1),(3,0,1,2)), ('all_natural',)*4, (0.,)*4)
        audit = audit_vip_batch([root], {'all_natural': 1.}, subset,
            baseline_policy_id=next(iter(baseline_ids)), challenger_policy_id=candidate_id)
        assert audit.confirmable
        root_audits.append(asdict(audit))
    assert canonical(root_audits) == canonical(summary['root_audits'])
    settlement_keys, by_root, arm_sum = set(), {}, {'A': 0, 'C': 0}
    for row in rows(out/'settlements.jsonl.gz'):
        s, seat = row['settlement'], row['focal_physical_seat']
        assert row['evidence'] == 'public_export_hand_settlement'
        assert len(s['score_delta']) == 4 and sum(s['score_delta']) == 0
        arm = 'C' if row['match_id'].endswith(':'+candidate_id) else 'A'
        key = (row['match_id'], row['round_no'])
        assert key not in settlement_keys
        settlement_keys.add(key)
        root = by_root.setdefault(row['root_id'], {a: {'hands': 0, 'score': 0, 'own_ge4': 0} for a in ('A','C')})
        root[arm]['hands'] += 1
        root[arm]['score'] += s['score_delta'][seat]
        arm_sum[arm] += s['score_delta'][seat]
        root[arm]['own_ge4'] += int(not s['is_draw'] and s['winner_seat'] == seat and s['fan'] >= 4)
    assert len(settlement_keys) == 128 and len(by_root) == 2
    assert all(root[a]['hands'] == 32 for root in by_root.values() for a in ('A','C'))
    for arm in ('A','C'):
        ledger = summary['realized_ledger']['counts_and_actual_net_by_arm'][arm]
        assert sum(v['hands'] for v in ledger.values()) == 64 and ledger['unknown']['hands'] == 0
        assert sum(v['focal_score_sum'] for v in ledger.values()) == arm_sum[arm]
        table_sum = sum(r.scores_after[r.seat_permutation[0]]-r.scores_before[r.seat_permutation[0]]
            for r in outcomes if (r.policy_ids_by_seat[r.seat_permutation[0]] == candidate_id) == (arm == 'C'))
        assert table_sum == arm_sum[arm]
    assert summary['descriptive_net_score_delta_per_table'] == (arm_sum['C']-arm_sum['A'])/8
    excluded = {'ROOT-READBACK.json', 'ROOT-READBACK.log'}
    files = {str(p.relative_to(HERE)): {'bytes': p.stat().st_size, 'sha256': sha(p)}
             for p in sorted(HERE.rglob('*')) if p.is_file() and p.name not in excluded}
    result = {'schema': 't92-complete-engineering-readback/1', 'complete': True,
        'actual_tables': 16, 'actual_hands': 128, 'independent_roots': 2,
        'actual_all_seat_decisions': all_decisions, 'actual_candidate_score_calls': len(calls),
        'actual_candidate_decisions': candidate_decisions, 'actual_finite_action_score_outputs': action_scores,
        'unique_complete_actual_views_readback': len(archive),
        'all_capture_refs_legal_outputs_and_net_settlements_reconciled': True,
        'candidate_selected_action_counts': dict(selected), 'white_counts_at_C_decisions': dict(white_counts),
        'C_decisions_per_root': dict(views_per_root), 'max_candidate_operations': max(operations),
        'choose_with_capture_latency_ms_by_phase': {k: distribution(v) for k,v in latency.items()},
        'timing_scope': 'offline logical clock plus capture; not real worker/network/SSE/deadline proof',
        'realized_by_root': by_root, 'realized_net_by_arm': arm_sum,
        'source_stable': True, 'files': files, 'new_models_scores_worlds_tables_in_readback': 0,
        'research_native_overlays_used': False, 'confirmation_admission_publication': False}
    with (_project_file(_PROJECT_ROOT, HERE/'ROOT-READBACK.json')).open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
    print({k: result[k] for k in ('complete','actual_tables','actual_hands', 'actual_candidate_score_calls',
                                'unique_complete_actual_views_readback','actual_finite_action_score_outputs')})


if __name__ == '__main__':
    main()
