"""四块都自然闭合后核全分母、结算账及128母根区间；不开新桌、不调候选。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t67-second-joint-fixed-qualifier-confirmation-1'

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
from collections import defaultdict
from pathlib import Path

from hangma_bot.offline.evaluation_results import read_results_jsonl, check_complete_consistency

HERE = Path(__file__).resolve().parent


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def main():
    plan = json.loads((_project_file(_PROJECT_ROOT, HERE / 'CAMPAIGN-PLAN.json')).read_text())
    summaries = [_project_file(_PROJECT_ROOT, HERE / ('block-' + format(i, '02d')) / 'summary.json') for i in range(1, 5)]
    if not all(path.exists() for path in summaries):
        print({'status': 'pending', 'closed_blocks': sum(p.exists() for p in summaries), 'outcome_inspection': False})
        raise SystemExit(2)
    issues, pairs, hand_totals, seen_hands = [], defaultdict(dict), defaultdict(int), set()
    realized = {a: {k: {'hands': 0, 'score': 0} for k in
                    ('own_lt4','own_4_to7','own_8_to15','own_ge16','opponent_hu','draw')} for a in ('A','C')}
    table_sums = defaultdict(int)
    root_highfan = {a: set() for a in ('A','C')}
    decision_windows = actual_views = charged = started = 0
    candidate_id = 'vip:' + plan['candidate_identity']['candidate_id']
    try:
        assert not (_project_file(_PROJECT_ROOT, HERE / 'GLOBAL-ENGINEERING-FAILURE.json')).exists(), 'global engineering failure'
        for name, digest in plan['prerequisite_sha256'].items():
            assert sha(Path(name)) == digest, name
        for index, path in enumerate(summaries, 1):
            out = path.parent
            summary = json.loads(path.read_text())
            block_plan = json.loads((_project_file(_PROJECT_ROOT, HERE / ('BLOCK-' + format(index, '02d') + '-PLAN.json'))).read_text())
            assert summary['development_complete'] and not summary['issues']
            assert summary['candidate_identity'] == plan['candidate_identity'] and summary['identity_stable']
            terminal = summary['scoring_input_capture']['terminal']
            assert terminal['terminal_valid'] and terminal['closed'] and terminal['verified']
            assert sha(out / 'views.jsonl.gz') == terminal['compressed_sha256']
            actual_views += terminal['verified_unique_views']
            decision_windows += summary['decision_windows']
            charged += summary['charged_table_instances']
            started += summary['actual_started_table_instances']
            freeze = json.loads((out / 'end-freeze.json').read_text())
            assert freeze['source_stable']
            for name, digest in freeze['frozen_files'].items():
                assert sha(Path(name)) == digest, name
            for name, digest in freeze['source_manifest'].items():
                assert sha(Path(name)) == sha(out / 'code_snapshot' / name) == digest['sha256'], name
            results = read_results_jsonl(out / 'results.jsonl')
            assert len(results) == 256 and all(not check_complete_consistency(r) for r in results)
            by_id = {r.game_key.game_id: r for r in results}
            assert len(by_id) == 256
            for result in results:
                assert result.scenario_id in block_plan['root_ids']
                assert result.status == 'complete' and result.completed_hands == 8
                assert all(getattr(result.runtime_counts, k) == 0 for k in
                           ('timeouts','illegal_choices','fallbacks','auto_actions','audit_missing'))
                seat = result.seat_permutation[0]
                arm = 'C' if result.policy_ids_by_seat[seat] == candidate_id else 'A'
                assert arm == 'C' or result.policy_ids_by_seat[seat].startswith('research-r18-v2:')
                key = (result.scenario_id, result.seat_permutation)
                assert arm not in pairs[key]
                pairs[key][arm] = result.scores_after[seat] - result.scores_before[seat]
                table_sums[arm] += pairs[key][arm]
            with gzip.open(out / 'settlements.jsonl.gz', 'rt', encoding='utf-8') as stream:
                for line in stream:
                    row = json.loads(line)
                    result = by_id[row['match_id']]
                    key = (row['match_id'], row['round_no'])
                    assert key not in seen_hands
                    seen_hands.add(key)
                    seat = result.seat_permutation[0]
                    arm = 'C' if result.policy_ids_by_seat[seat] == candidate_id else 'A'
                    s = row['settlement']
                    assert row['evidence'] == 'public_export_hand_settlement' and row['focal_physical_seat'] == seat
                    delta = s['score_delta']
                    assert sum(delta) == 0 and [b+d for b,d in zip(s['scores_before'],delta)] == s['scores_after']
                    if s['is_draw']:
                        kind = 'draw'
                    elif s['winner_seat'] != seat:
                        kind = 'opponent_hu'
                    else:
                        fan = s['fan']
                        assert type(fan) is int and fan > 0
                        kind = 'own_lt4' if fan < 4 else 'own_4_to7' if fan < 8 else 'own_8_to15' if fan < 16 else 'own_ge16'
                        if fan >= 4:
                            root_highfan[arm].add(row['root_id'])
                    realized[arm][kind]['hands'] += 1
                    realized[arm][kind]['score'] += delta[seat]
                    hand_totals[row['match_id']] += delta[seat]
            assert all(hand_totals[r.game_key.game_id] == r.scores_after[r.seat_permutation[0]] - r.scores_before[r.seat_permutation[0]]
                       for r in results)
        assert charged == started == plan['planned_actual_tables'] == 1024
        assert len(seen_hands) == plan['planned_hands'] == 8192
        assert len(pairs) == plan['paired_tables'] == 512 and all(set(v) == {'A','C'} for v in pairs.values())
        root_means = []
        for root in plan['root_ids']:
            keys = [(root, p) for p in ((0,1,2,3),(1,2,3,0),(2,3,0,1),(3,0,1,2))]
            root_means.append(statistics.mean(pairs[k]['C'] - pairs[k]['A'] for k in keys))
        assert len(root_means) == 128
        for arm in ('A','C'):
            assert sum(v['hands'] for v in realized[arm].values()) == 4096
            assert sum(v['score'] for v in realized[arm].values()) == table_sums[arm]
        mean = statistics.mean(root_means)
        assert mean == (table_sums['C'] - table_sums['A']) / 512
        rng = random.Random(plan['confidence']['seed'])
        boot = sorted(statistics.mean(rng.choices(root_means, k=128)) for _ in range(plan['confidence']['resamples']))
        interval = [boot[500], boot[19499]]
    except Exception as exc:
        issues.append(type(exc).__name__ + ': ' + str(exc))
        mean = interval = root_means = None
    result = {
        'schema': 't67-whole-campaign-readback/1', 'whole_batch_valid': not issues, 'issues': issues,
        'planned_actual_tables': 1024, 'planned_hands': 8192, 'planned_independent_roots': 128,
        'actual_started_tables': started, 'charged_tables': charged, 'observed_hands_readback': len(seen_hands),
        'decision_windows': decision_windows, 'actual_complete_views': actual_views,
        'candidate_identity': plan['candidate_identity'], 'root_mean_deltas': root_means,
        'net_score_delta_per_table': mean, 'root_cluster_percentile_95': interval,
        'realized_net_by_arm': dict(table_sums), 'realized_mutually_exclusive_bands': realized,
        'highfan_root_clusters': {a: sorted(v) for a,v in root_highfan.items()},
        'research_superiority_signal': not issues and interval[0] > 0,
        'scope': 'fixed 60%-weak qualifier offline scenario; no leaderboard/top3/online deadline or publication credit',
        'new_models_scores_worlds_tables_in_readback': 0, 'published': False,
    }
    with (_project_file(_PROJECT_ROOT, HERE / 'CAMPAIGN-CLOSURE.json')).open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
    print({k: result[k] for k in ('whole_batch_valid','issues','actual_started_tables','net_score_delta_per_table',
                                'root_cluster_percentile_95','research_superiority_signal')})
    if issues:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
