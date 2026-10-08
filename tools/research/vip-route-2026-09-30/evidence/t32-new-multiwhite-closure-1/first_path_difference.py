"""纯读三处高番正差的首次共同观察分歧；不是动作金标或新评分。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t32-new-multiwhite-closure-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t32-new-multiwhite-source-preparation-1')


def read(path):
    return json.loads(path.read_bytes())


def window(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def main():
    """以已知开发收益定位后续机制；保留父代共有效、子代新增的区别。"""
    plan = read(_project_file(_PROJECT_ROOT, SOURCE/'PREPARED.json'))
    choices, scores = {}, {}
    for line in (_project_file(_PROJECT_ROOT, SOURCE/'calls-and-choices.jsonl')).open():
        row = json.loads(line)
        key = (row['root_id'], row.get('variant'), row.get('arm'))
        if row['event'] == 'policy_choose':
            full = (*key, window(row['window_key']))
            assert full not in choices
            choices[full] = row
        elif row['event'] == 'score_call':
            full = (*key, window(row['window_key']))
            assert full not in scores
            scores[full] = row
    tests = ((2026103005, 'original', 'Sol-C', 'Sol-B'),
             (2026103006, 'public_consistent_hidden_1', 'Sol-C', 'Sol-B'),
             (2026103006, 'public_consistent_hidden_1', 'Sol-C', 'S02-C'),
             (2026103008, 'public_consistent_hidden_1', 'Sol-C', 'Sol-B'))
    witnesses = []
    for seed, variant, left, right in tests:
        root_id = 'vip-t32-new-multiwhite-'+str(seed)
        ordinal = next(i for i, r in enumerate(plan['roots'], 1) if r['root_id'] == root_id)
        directory = _project_file(_PROJECT_ROOT, SOURCE/f'root-{ordinal:02d}'/variant)
        outcomes = {a: read(directory/(a+'-outcome.json')) for a in (left, right)}
        paths = {a: outcomes[a]['outcome']['decisions'] for a in (left, right)}
        for index, (a, b) in enumerate(zip(paths[left], paths[right])):
            assert a['window_key'] == b['window_key'] and a['seat'] == b['seat']
            if a['action_key'] != b['action_key']:
                assert a['seat'] == 0
                ac = choices[root_id, variant, left, window(a['window_key'])]
                bc = choices[root_id, variant, right, window(b['window_key'])]
                assert ac['observation'] == bc['observation']
                assert set(ac['legal_action_keys']) == set(bc['legal_action_keys'])
                aa = scores[root_id, variant, left, window(a['window_key'])]
                bb = scores[root_id, variant, right, window(b['window_key'])]
                selected = {a['action_key'], b['action_key']}
                witnesses.append({'root_id': root_id, 'variant': variant, 'left': left, 'right': right,
                    'common_all_seat_action_prefix': index, 'window_key': a['window_key'],
                    'complete_public_observation': ac['observation'], 'legal_action_keys': ac['legal_action_keys'],
                    'left_action': a['action_key'], 'right_action': b['action_key'],
                    'left_view_sha256': aa['input_capture']['view_sha256'],
                    'right_view_sha256': bb['input_capture']['view_sha256'],
                    'left_actual_two_entries': [e for e in aa['scores']['entries'] if e['action_key'] in selected],
                    'right_actual_two_entries': [e for e in bb['scores']['entries'] if e['action_key'] in selected],
                    'left_focal_score': outcomes[left]['focal_net_score'],
                    'right_focal_score': outcomes[right]['focal_net_score'],
                    'same_complete_observation_and_legal_set': True,
                    'first_difference_not_individually_causal_gold': True})
                break
        else:
            raise AssertionError('positive terminal difference without action divergence')
    seal = read(_project_file(_PROJECT_ROOT, HERE/'RAW-FIRST-SEAL.json'))
    for path, expected in seal['files'].items():
        data = Path(path).read_bytes()
        assert len(data) == expected['bytes'] and hashlib.sha256(data).hexdigest() == expected['sha256']
    result = {'schema': 't32-known-highfan-first-public-difference/1', 'rows': witnesses,
        'business_calls': 0, 'new_authors': 0, 'new_reviews': 0,
        'selection_is_exposed_positive_development_diagnosis_not_unexposed_sample': True}
    with (_project_file(_PROJECT_ROOT, HERE/'FIRST-HIGHFAN-PATH-DIFFERENCES.json')).open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps([{k: r[k] for k in ('root_id', 'variant', 'left', 'right', 'window_key',
        'left_action', 'right_action', 'left_focal_score', 'right_focal_score')} for r in witnesses], ensure_ascii=False))


if __name__ == '__main__':
    main()
