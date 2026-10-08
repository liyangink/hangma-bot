"""纯读T99全部候选配对，提取共同前缀后的首分歧及合法公开输入。

不调用规则、模型、评分或模拟。终分标签包含两种完整续策的差别，
不能解释为单次动作的因果价值。完整教师世界与未来牌墙不进入反馈。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t100-joint-pilot-divergence-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OLD = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t99-new-joint-fresh-pilot-1')


def canonical(value):
    """有限规范JSON，用于不含机器时钟的字节对照。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def sha(path):
    """流式检查实际旧证据，不把清单当成证据已存在。"""
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def save(name, value):
    """只创建新读回产物，失败原件不可覆盖。"""
    with (_project_file(_PROJECT_ROOT, HERE / name)).open('xb') as f:
        f.write(canonical(value) + b'\n')


def rows(path):
    """旧压缩记录按行只读，不重放世界。"""
    with gzip.open(path, 'rt') as f:
        for line in f:
            yield json.loads(line)


def window(value):
    """只去掉已知不同的场次ID，保留完整动作窗口语义。"""
    return {k: v for k, v in value.items() if k != 'game_id'}


def observation(value):
    """比较本座公开观察，只去场次ID；其余事实包括完整事件历史均保留。"""
    return {k: v for k, v in value.items() if k != 'game_id'}


def action_signature(value):
    """比较全部座位的真实动作和窗口，不比较策略标识或计算时钟。"""
    return (window(value['window_key']), value['seat'], value['plan_revision'],
            value['action_key'], value['legal'])


def candidate(group):
    """显式选候选臂，拒绝把重复R18臂混成候选轨迹。"""
    records = [r for r in group['match_records'] if ':vip:' in r['match_id']]
    assert len(records) == 1
    record = records[0]
    result = next(r for r in group['results']
                  if r['game_key']['game_id'] == record['match_id'])
    return record, result


def main():
    """核全部32对，然后产生本座公开事实及非因果的实测终分标签。"""
    plan = json.loads((_project_file(_PROJECT_ROOT, HERE / 'PLAN.json')).read_text())
    for relative, digest in plan['source_sha256'].items():
        assert sha(_project_file(_PROJECT_ROOT, OLD / relative)) == digest
    closed = json.loads((_project_file(_PROJECT_ROOT, OLD / 'CAMPAIGN-CLOSURE.json')).read_text())
    assert closed['whole_batch_valid'] and closed['duplicate_R18_tables_verified'] == 32
    save('START.json', {'scope': 'known development roots, complete paired policies',
                        'new_business_calls': 0, 'all_32_pairs_included': True,
                        'single_action_causal_claim': False})
    pairs, wanted, settlements = [], {}, {}
    for block in range(1, 5):
        for name in sorted((_project_file(_PROJECT_ROOT, OLD / f'block-{block:02d}')).glob('group-*.json.gz')):
            groups = []
            for number in (block, block + 4):
                with gzip.open(_project_file(_PROJECT_ROOT, OLD / f'block-{number:02d}' / name.name), 'rt') as f:
                    groups.append(json.load(f))
            (new, nr), (old, pr) = [candidate(g) for g in groups]
            assert nr['scenario_id'] == pr['scenario_id']
            assert nr['seat_permutation'] == pr['seat_permutation']
            seat = nr['seat_permutation'][0]
            nt, pt = new['outcome']['decisions'], old['outcome']['decisions']
            assert new['outcome']['status'] == old['outcome']['status'] == 'complete'
            cut = next((i for i, (a, b) in enumerate(zip(nt, pt))
                        if action_signature(a) != action_signature(b)), None)
            pair = {'label': f'pair-{len(pairs)+1:02d}', 'root_id': nr['scenario_id'],
                    'permutation': nr['seat_permutation'], 'focal_seat': seat,
                    'new_block': block, 'old_block': block + 4,
                    'new_match_id': new['match_id'], 'old_match_id': old['match_id'],
                    'T97_table_score': nr['scores_after'][seat] - nr['scores_before'][seat],
                    'T75_table_score': pr['scores_after'][seat] - pr['scores_before'][seat],
                    'first_divergence_index': cut,
                    'outcome_label_scope': 'complete distinct continuation policies; not single-action cause'}
            pair['table_delta'] = pair['T97_table_score'] - pair['T75_table_score']
            if cut is None:
                assert len(nt) == len(pt) and nr['scores_after'] == pr['scores_after']
                pair['trajectory_equal'] = True
            else:
                a, b = nt[cut], pt[cut]
                assert window(a['window_key']) == window(b['window_key'])
                assert a['seat'] == b['seat'] == seat
                assert a['plan_revision'] == b['plan_revision'] and a['action_key'] != b['action_key']
                pair.update(trajectory_equal=False, window=window(a['window_key']),
                            T97_action=a['action_key'], T75_action=b['action_key'])
                for variant, number, row, mid in [('T97', block, a, new['match_id']),
                                                   ('T75', block + 4, b, old['match_id'])]:
                    key = (number, mid, row['decision_id'])
                    assert key not in wanted
                    wanted[key] = (pair['label'], variant)
            pairs.append(pair)
    assert len(pairs) == 32 and len({r['root_id'] for r in pairs}) == 8
    selected, found = {}, set()
    for number in range(1, 9):
        for row in rows(_project_file(_PROJECT_ROOT, OLD / f'block-{number:02d}' / 'decisions.jsonl.gz')):
            key = (number, row['match_id'], row['decision_id'])
            if key not in wanted:
                continue
            assert key not in found
            found.add(key)
            assert row['policy_id'].startswith('vip:') and row['c_self_scored']
            assert row['status'] == 'chosen' and not row['degraded_reasons']
            assert len(row['scoring_calls']) == 1
            call = row['scoring_calls'][0]
            assert call['status'] == 'SCORED' and call['full_legal_keys']
            assert call['input_capture']['saved_before_score']
            label, variant = wanted[key]
            selected.setdefault(label, {})[variant] = row
        for row in rows(_project_file(_PROJECT_ROOT, OLD / f'block-{number:02d}' / 'settlements.jsonl.gz')):
            key = (number, row['match_id'], row['round_no'])
            assert key not in settlements
            settlements[key] = row['settlement']
    assert found == set(wanted)
    needed_views, views = set(), {}
    for variants in selected.values():
        a, b = variants['T97'], variants['T75']
        assert window(a['window_key']) == window(b['window_key'])
        assert observation(a['observation']) == observation(b['observation'])
        assert set(a['legal_action_keys']) == set(b['legal_action_keys'])
        av = a['scoring_calls'][0]['input_capture']['view_sha256']
        bv = b['scoring_calls'][0]['input_capture']['view_sha256']
        assert av == bv
        needed_views.add(av)
    for number in range(1, 9):
        for row in rows(_project_file(_PROJECT_ROOT, OLD / f'block-{number:02d}' / 'views.jsonl.gz')):
            digest = row['view_sha256']
            if digest in needed_views:
                assert hashlib.sha256(canonical(row['view'])).hexdigest() == digest
                if digest in views:
                    assert views[digest] == row['view']
                views[digest] = row['view']
    assert set(views) == needed_views
    feedback = []
    for pair in pairs:
        if pair['trajectory_equal']:
            continue
        a, b = selected[pair['label']]['T97'], selected[pair['label']]['T75']
        digest = a['scoring_calls'][0]['input_capture']['view_sha256']
        round_no = a['window_key']['round_no']
        labels = {}
        for variant, number, mid in [('T97', pair['new_block'], pair['new_match_id']),
                                   ('T75', pair['old_block'], pair['old_match_id'])]:
            s = settlements[(number, mid, round_no)]
            labels[variant] = {'focal_score': s['score_delta'][pair['focal_seat']],
                               'winner_seat': s['winner_seat'], 'fan': s['fan'],
                               'is_draw': s['is_draw']}
        pair['white_count'] = a['white_count']
        pair['first_divergence_hand_delta'] = labels['T97']['focal_score'] - labels['T75']['focal_score']
        feedback.append({'label': pair['label'], 'window': pair['window'],
                         'public_observation': observation(a['observation']),
                         'complete_view_sha256': digest, 'complete_view': views[digest],
                         'T97_action': pair['T97_action'], 'T75_action': pair['T75_action'],
                         'T97_actual_scores': a['candidates'], 'T75_actual_scores': b['candidates'],
                         'actual_trajectory_labels': labels, 'table_delta': pair['table_delta'],
                         'label_scope': pair['outcome_label_scope']})
    with gzip.open(_project_file(_PROJECT_ROOT, HERE / 'PUBLIC-FIRST-DIVERGENCES.json.gz'), 'xb') as f:
        f.write(canonical({'scope': 'all changed complete development pairs', 'rows': feedback}))
    save('PAIR-READBACK.json', {'pairs': pairs, 'all_32_pairs_included': True,
                               'actual_new_business_calls': 0})
    changed = [p for p in pairs if not p['trajectory_equal']]
    summary = {'complete': True, 'independent_roots': 8, 'pairs': 32,
               'changed_trajectories': len(changed), 'equal_trajectories': 32-len(changed),
               'same_public_observation_and_view_for_every_first_divergence': True,
               'white_counts_at_first_divergence': dict(Counter(p['white_count'] for p in changed)),
               'action_pairs': dict(Counter(p['T75_action'].split(':')[0]+'->'+p['T97_action'].split(':')[0] for p in changed)),
               'table_delta_sum': sum(p['table_delta'] for p in pairs),
               'table_signs': dict(Counter('positive' if p['table_delta']>0 else 'negative' if p['table_delta']<0 else 'zero' for p in pairs)),
               'first_divergence_hand_delta_sum_not_causal': sum(p['first_divergence_hand_delta'] for p in changed),
               'new_models_scores_rules_worlds_tables': 0,
               'single_action_causal_or_holdout_claim': False}
    assert summary['table_delta_sum'] == -463
    save('CLOSURE.json', summary)
    print(summary)


if __name__ == '__main__':
    main()
