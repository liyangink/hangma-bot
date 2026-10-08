"""独立读回64桌、512结算和全部实际评分输入；不评分、不生成新世界。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t49-qualifier-opponent-behavior-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import gzip
import hashlib
import json
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from hangma_bot.offline.evaluation_results import read_results_jsonl, check_complete_consistency
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents
from hangma_bot.offline.qualifier_opponents import build_qualifier_runtime

HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t49-qualifier-opponent-behavior-1/candidate-pilot-1')
AUTHOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t48-v3-natural-highfan-joint-author-1')


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def read_gzip(name):
    with gzip.open(_project_file(_PROJECT_ROOT, OUT / name), 'rt', encoding='utf-8') as stream:
        for line in stream:
            yield json.loads(line)


def main():
    start = json.loads((_project_file(_PROJECT_ROOT, OUT / 'START.json')).read_text())
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / 'summary.json')).read_text())
    end = json.loads((_project_file(_PROJECT_ROOT, OUT / 'end-freeze.json')).read_text())
    for name, digest in start['frozen_files'].items():
        assert sha(Path(name)) == digest, name
    assert start['source_manifest'] == end['source_manifest'] and end['source_stable']
    for name, digest in start['source_manifest'].items():
        assert sha(Path(name)) == digest['sha256'], name
        assert sha(_project_file(_PROJECT_ROOT, OUT / 'code_snapshot' / name)) == digest['sha256'], name
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, AUTHOR / 'S01-research.batch.json'))
    candidate = load_vip_parents([_project_file(_PROJECT_ROOT, AUTHOR / 'S01-research-capacity')], batch)[0]
    assert candidate['identity'] == summary['candidate_identity'] == start['candidate_identity']
    compositions = start['opponent_compositions']
    results = read_results_jsonl(_project_file(_PROJECT_ROOT, OUT / 'results.jsonl'))
    assert len(results) == 64 and all(not check_complete_consistency(r) for r in results)
    by_id = {r.game_key.game_id: r for r in results}
    assert len(by_id) == 64
    pools = {}
    for root in compositions:
        runtime = build_qualifier_runtime(batch, candidate['source'], root['opponent_types_logical_1_2_3'])
        pools[root['root_id']] = runtime
    pairs = defaultdict(dict)
    table_totals = defaultdict(int)
    for result in results:
        assert result.status == 'complete' and result.completed_hands == 8
        assert result.scores_before == (0, 0, 0, 0) and sum(result.scores_after) == 0
        assert all(getattr(result.runtime_counts, key) == 0 for key in
                   ('timeouts', 'illegal_choices', 'fallbacks', 'auto_actions', 'audit_missing'))
        runtime = pools[result.scenario_id]
        ids = tuple(result.policy_ids_by_seat[result.seat_permutation[i]] for i in range(4))
        arm = 'C' if ids[0] == runtime.challenger_policy_id else 'A'
        assert ids[0] == (runtime.challenger_policy_id if arm == 'C' else runtime.baseline_policy_id)
        assert ids[1:] == tuple(runtime.declarations['Q' + str(i)].policy_id for i in range(1, 4))
        pair = (result.scenario_id, result.seat_permutation)
        assert arm not in pairs[pair]
        pairs[pair][arm] = result.scores_after[result.seat_permutation[0]]
        table_totals[arm] += pairs[pair][arm]
    assert len(pairs) == 32 and all(set(pair) == {'A', 'C'} for pair in pairs.values())
    bands = ('own_lt4', 'own_4_to7', 'own_8_to15', 'own_ge16', 'opponent_hu', 'draw')
    totals = {a: {k: {'hands': 0, 'focal_score_sum': 0} for k in bands} for a in ('A', 'C')}
    by_root = {root['root_id']: {a: {k: {'hands': 0, 'score': 0} for k in bands}
                               for a in ('A', 'C')} for root in compositions}
    seen_hands, hand_sums = set(), defaultdict(int)
    dealer_totals = {a: {k: {'hands': 0, 'score': 0} for k in ('dealer', 'non_dealer')} for a in ('A', 'C')}
    for row in read_gzip('settlements.jsonl.gz'):
        key = (row['match_id'], row['round_no'])
        assert key not in seen_hands
        seen_hands.add(key)
        result = by_id[row['match_id']]
        runtime = pools[result.scenario_id]
        seat = result.seat_permutation[0]
        assert row['focal_physical_seat'] == seat and row['permutation'] == list(result.seat_permutation)
        arm = 'C' if result.policy_ids_by_seat[seat] == runtime.challenger_policy_id else 'A'
        settlement = row['settlement']
        assert row['evidence'] == 'public_export_hand_settlement'
        delta = settlement['score_delta']
        assert len(delta) == 4 and sum(delta) == 0
        assert [b + d for b, d in zip(settlement['scores_before'], delta)] == settlement['scores_after']
        score = delta[seat]
        if settlement['is_draw']:
            kind = 'draw'
        elif settlement['winner_seat'] != seat:
            kind = 'opponent_hu'
        else:
            fan = settlement['fan']
            assert type(fan) is int and fan > 0
            kind = 'own_lt4' if fan < 4 else 'own_4_to7' if fan < 8 else 'own_8_to15' if fan < 16 else 'own_ge16'
        totals[arm][kind]['hands'] += 1
        totals[arm][kind]['focal_score_sum'] += score
        by_root[row['root_id']][arm][kind]['hands'] += 1
        by_root[row['root_id']][arm][kind]['score'] += score
        dealer = 'dealer' if settlement['dealer_seat'] == seat else 'non_dealer'
        dealer_totals[arm][dealer]['hands'] += 1
        dealer_totals[arm][dealer]['score'] += score
        hand_sums[row['match_id']] += score
    assert len(seen_hands) == 512 and all(sum(totals[a][k]['hands'] for k in bands) == 256 for a in ('A', 'C'))
    assert all(hand_sums[r.game_key.game_id] == r.scores_after[r.seat_permutation[0]] for r in results)
    expected = summary['realized_ledger']['counts_and_actual_net_by_arm']
    assert all(totals[a][k] == expected[a][k] for a in ('A', 'C') for k in bands)
    assert all(expected[a]['unknown'] == {'hands': 0, 'focal_score_sum': 0} for a in ('A', 'C'))
    capture_refs, decisions, c_decisions = [], 0, 0
    action_counts = Counter()
    for row in read_gzip('decisions.jsonl.gz'):
        decisions += 1
        assert row['status'] == 'chosen' and row['selected_action_key'] in row['legal_action_keys']
        if row['policy_id'].startswith('vip:'):
            c_decisions += 1
            assert row['c_self_scored'] and row['scoring_cumulative_failed_calls'] == 0
            assert not row['degraded_reasons']
            action_counts[row['selected_action_key'].split(':', 1)[0]] += 1
            for call in row['scoring_calls']:
                capture = call['input_capture']
                assert call['score_completed'] and call['full_legal_keys'] and capture['saved_before_score']
                capture_refs.append((capture['store_call_no'], capture['view_sha256'], capture['json_bytes']))
    refs = sorted(capture_refs)
    assert [r[0] for r in refs] == list(range(1, len(refs) + 1))
    views = list((r['view_sha256'], r['json_bytes']) for r in read_gzip('views.jsonl.gz')
                 if hashlib.sha256(canonical(r['view'])).hexdigest() == r['view_sha256']
                 and len(canonical(r['view'])) == r['json_bytes'])
    assert views == [(s, n) for _, s, n in refs]
    terminal = summary['scoring_input_capture']['terminal']
    assert terminal['terminal_valid'] and terminal['verified_unique_views'] == len(views) == len(refs)
    assert sha(_project_file(_PROJECT_ROOT, OUT / 'views.jsonl.gz')) == terminal['compressed_sha256']
    assert decisions == summary['decision_windows'] and c_decisions == len(views) == 10726
    means = [statistics.mean(pairs[(root['root_id'], tuple(p))]['C'] - pairs[(root['root_id'], tuple(p))]['A']
                             for p in ((0,1,2,3),(1,2,3,0),(2,3,0,1),(3,0,1,2))) for root in compositions]
    assert statistics.mean(means) == summary['estimated_net_score_delta_per_table'] == 4.75
    component_deltas = {k: totals['C'][k]['focal_score_sum'] - totals['A'][k]['focal_score_sum'] for k in bands}
    assert sum(component_deltas.values()) == table_totals['C'] - table_totals['A'] == 152
    rng = random.Random(2026100249)
    boot = sorted(statistics.mean(rng.choices(means, k=len(means))) for _ in range(20000))
    receipt = {
        'schema': 't49-independent-readback/1', 'complete': True,
        'actual_tables': 64, 'actual_hands': 512, 'paired_tables': 32, 'independent_roots': 8,
        'decisions': decisions, 'c_score_calls': c_decisions, 'full_actual_views_readback': len(views),
        'all_runtime_fault_counts_zero': True, 'all_scores_settlements_capture_refs_and_frozen_bytes_reconciled': True,
        'actual_weak_opponents': sum(r['actual_weak_count'] for r in compositions), 'logical_opponent_slots': 24,
        'net_actual_total_by_arm': dict(table_totals), 'actual_component_net_deltas': component_deltas,
        'root_mean_table_deltas': means, 'positive_negative_roots': [sum(x > 0 for x in means), sum(x < 0 for x in means)],
        'descriptive_mean_delta_per_table': statistics.mean(means),
        'exploratory_root_bootstrap_percentile_95': [boot[500], boot[19499]],
        'bootstrap_seed': 2026100249, 'bootstrap_resamples': 20000,
        'bootstrap_scope': '8 development roots; four seats remain one cluster; not admission or tail-frequency guarantee',
        'realized_by_root': by_root, 'dealer_and_non_dealer_actual_sums': dealer_totals,
        'c_selected_action_counts': dict(action_counts),
        'same_round_difference_not_single_action_causal_claim': True,
        'new_models_scores_worlds_tables': 0, 'confirmation_admission_publication': False,
        'next': 'fixed formula unexposed long batch; no artificial highfan multiplier; deadlines and stronger-pool diagnostics separate',
    }
    with (_project_file(_PROJECT_ROOT, HERE / 'PILOT-ROOT-CLOSE-AUDIT.json')).open('xb') as stream:
        stream.write(canonical(receipt) + b'\n')
    print({k: receipt[k] for k in ('complete','actual_tables','actual_hands','full_actual_views_readback',
                                  'actual_component_net_deltas','exploratory_root_bootstrap_percentile_95')}, flush=True)


if __name__ == '__main__':
    main()
