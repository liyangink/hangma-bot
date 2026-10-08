"""完整T52关闭后只读分账、来源和既定弱对手组成，不重评分或开桌。

这是确认结果的解释诊断。确认根现在已曝光，后续用作开发，不把按结果
挑出的稀有牌例重新称为独立确认。所有积分仍为原规则实际结算。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t58-qualifier-result-mechanism-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent
CAMPAIGN = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t52-fixed-qualifier-unexposed-long-1')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def save(name, value):
    with (_project_file(_PROJECT_ROOT, HERE / name)).open('xb') as stream:
        stream.write(canonical(value) + b'\n')


def main():
    plan = json.loads((_project_file(_PROJECT_ROOT, CAMPAIGN / 'CAMPAIGN-PLAN.json')).read_text())
    closure = json.loads((_project_file(_PROJECT_ROOT, CAMPAIGN / 'CAMPAIGN-CLOSURE.json')).read_text())
    assert closure['whole_batch_valid'] and closure['actual_started_tables'] == 1024
    composition_path = Path(plan['compositions_file'])
    composition = json.loads(composition_path.read_text())
    by_root = {r['root_id']: r for r in composition['reserved_confirmation']['0.6']}
    paths = [_project_file(_PROJECT_ROOT, CAMPAIGN / f'block-{i:02}/settlements.jsonl.gz') for i in range(1, 5)]
    frozen = {str(path): sha(path) for path in [Path(__file__), composition_path,
        _project_file(_PROJECT_ROOT, CAMPAIGN / 'CAMPAIGN-PLAN.json'), _project_file(_PROJECT_ROOT, CAMPAIGN / 'CAMPAIGN-CLOSURE.json'), *paths]}
    save('PLAN.json', {'schema': 't58-full-closed-qualifier-ledger-analysis/1',
        'frozen_files': frozen, 'expected_actual_hands': 8192,
        'new_model_score_graph_world_table_calls': 0,
        'scope': 'postconfirmation descriptive interpretation; all frozen128 roots, no subset promotion'})
    fan_counts = {a: Counter() for a in ('A','C')}
    dealer = {a: {'dealer': {'hands': 0, 'score': 0}, 'nondealer': {'hands': 0, 'score': 0}} for a in fan_counts}
    root_bands = {a: defaultdict(lambda: defaultdict(lambda: {'hands': 0, 'score': 0})) for a in fan_counts}
    rare = {a: [] for a in fan_counts}
    seen = set()
    for path in paths:
        with gzip.open(path, 'rt', encoding='utf-8') as stream:
            for line in stream:
                row = json.loads(line)
                settlement = row['settlement']
                key = (row['match_id'], row['round_no'])
                assert key not in seen
                seen.add(key)
                arm = 'C' if ':vip:' in row['match_id'] else 'A'
                seat = row['focal_physical_seat']
                assert settlement['round_no'] == row['round_no']
                amount = settlement['score_delta'][seat]
                d = dealer[arm]['dealer' if settlement['dealer_seat'] == seat else 'nondealer']
                d['hands'] += 1
                d['score'] += amount
                if settlement['is_draw']:
                    kind = 'draw'
                elif settlement['winner_seat'] != seat:
                    kind = 'opponent_hu'
                else:
                    fan = settlement['fan']
                    fan_counts[arm][fan] += 1
                    kind = 'own_lt4' if fan < 4 else 'own_4_to7' if fan < 8 else 'own_8_to15' if fan < 16 else 'own_ge16'
                    if fan >= 8:
                        rare[arm].append({k: row[k] for k in ('root_id','round_no','permutation','focal_physical_seat','match_id')} |
                            {'fan': fan, 'dealer_seat': settlement['dealer_seat'], 'score': amount,
                             'details': settlement['details']})
                root_bands[arm][row['root_id']][kind]['hands'] += 1
                root_bands[arm][row['root_id']][kind]['score'] += amount
    assert len(seen) == 8192
    for arm in fan_counts:
        assert sum(d['hands'] for d in dealer[arm].values()) == 4096
        assert sum(d['score'] for d in dealer[arm].values()) == closure['realized_net_by_arm'][arm]
        for kind, old in closure['realized_mutually_exclusive_bands'][arm].items():
            assert sum(bands[kind]['hands'] for bands in root_bands[arm].values()) == old['hands']
            assert sum(bands[kind]['score'] for bands in root_bands[arm].values()) == old['score']
    score_delta = {kind: closure['realized_mutually_exclusive_bands']['C'][kind]['score'] -
                         closure['realized_mutually_exclusive_bands']['A'][kind]['score']
                   for kind in closure['realized_mutually_exclusive_bands']['A']}
    assert sum(score_delta.values()) == closure['realized_net_by_arm']['C'] - closure['realized_net_by_arm']['A'] == 2337
    grouped = defaultdict(list)
    roots = []
    for root, delta in zip(plan['root_ids'], closure['root_mean_deltas']):
        weak = by_root[root]['actual_weak_count']
        grouped[weak].append(delta)
        roots.append({'root_id': root, 'actual_weak_count': weak,
                      'mean_net_table_delta': delta, 'bands_A': dict(root_bands['A'][root]),
                      'bands_C': dict(root_bands['C'][root])})
    assert len(roots) == 128 and statistics.mean(r['mean_net_table_delta'] for r in roots) == closure['net_score_delta_per_table']
    stable = all(sha(Path(path)) == digest for path, digest in frozen.items())
    assert stable
    save('CLOSURE.json', {'schema': 't58-closed-qualifier-ledger-analysis-result/1', 'complete': True,
        'source_stable': stable, 'actual_hand_rows': len(seen), 'root_rows': roots,
        'actual_fan_counts_by_arm': {a: dict(c) for a,c in fan_counts.items()},
        'actual_net_delta_by_mutually_exclusive_band': score_delta,
        'actual_ge4_net_delta': sum(score_delta[k] for k in ('own_4_to7','own_8_to15','own_ge16')),
        'dealer_non_dealer_actual_net': dealer, 'actual_ge8_events': rare,
        'actual_ge8_source_clusters': {a: len({r['root_id'] for r in rows}) for a,rows in rare.items()},
        'weak_count_cohorts_descriptive_only': {str(k): {'independent_roots': len(v),
            'mean_net_table_delta': statistics.mean(v)} for k,v in grouped.items()},
        'existing_confirmation_now_exposed_for_development': True,
        'new_model_score_graph_world_table_calls': 0, 'strength_or_online_admission': False})
    print({'complete': True, 'hand_rows': 8192, 'net_delta': 2337,
        'ge4_net_delta': -48, 'ge8_clusters_A_C': [len({r['root_id'] for r in rare[a]}) for a in ('A','C')]})


if __name__ == '__main__':
    main()
