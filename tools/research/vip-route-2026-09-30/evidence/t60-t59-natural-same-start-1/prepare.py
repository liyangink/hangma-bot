"""四个真实已曝光自然窗的纯文件准备，不评分、不恢复或推进世界。

选择已在读取原全座位路径前固定：新弃胡、原继续、仍胡和零白普通出口。
旧完整牌局只供离线复原，策略只收自己的PlayerObservation；不改自然留出。
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
from pathlib import Path
import gzip
import hashlib
import json
import sys

HERE = Path(__file__).resolve().parent
REPO = _PROJECT_ROOT
E = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')
T52 = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t52-fixed-qualifier-unexposed-long-1')
T58 = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t58-qualifier-result-mechanism-1')
T59 = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t59-qualifier-highfan-credit-author-1')
PARENT = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t51-t48-same-formula-efficiency-author-1')
SELECTION = [(0, 'new-continue'), (1, 'existing-continue'),
             (3, 'immediate-hu-control'), (10, 'zero-white-control')]


def canonical(value):
    """规范JSON只统一容器，不改变原观察、时间或积分。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def pin(path):
    digest, size = hashlib.sha256(), 0
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            digest.update(chunk)
            size += len(chunk)
    return {'bytes': size, 'sha256': digest.hexdigest()}


def save(path, value):
    with path.open('xb') as stream:
        stream.write(canonical(value) + b'\n')


def frame_key(window):
    return tuple(window[k] for k in ('game_id', 'round_no', 'trigger_seq', 'phase'))


def main():
    complete = json.loads((_project_file(_PROJECT_ROOT, T52 / 'CAMPAIGN-CLOSURE.json')).read_text())
    assert complete['whole_batch_valid'] and complete['actual_started_tables'] == 1024
    child_probe = json.loads((_project_file(_PROJECT_ROOT, T59 / 'PUBLIC-PROBE-CLOSURE.json')).read_text())
    child_readback = json.loads((_project_file(_PROJECT_ROOT, T59 / 'ROOT-READBACK.json')).read_text())
    assert child_probe['complete_all_windows'] and child_readback['complete']
    assert child_readback['candidate_identity'] == child_probe['candidate_identity']
    for name, digest in child_readback['files'].items():
        assert pin(_project_file(_PROJECT_ROOT, T59 / name)) == digest, name
    natural = json.loads((_project_file(_PROJECT_ROOT, T58 / 'NATURAL-PUBLIC-CASES.json')).read_text())['cases']
    parent_probe = json.loads((_project_file(_PROJECT_ROOT, T58 / 'PARENT-REPLAY-CLOSURE.json')).read_text())
    assert parent_probe['complete']
    files = {}
    def bind(path):
        path = path.resolve()
        files[str(path)] = pin(path)
    for path in (Path(__file__), _project_file(_PROJECT_ROOT, HERE / 'run.py'), _project_file(_PROJECT_ROOT, T52 / 'CAMPAIGN-CLOSURE.json'),
                 _project_file(_PROJECT_ROOT, T58 / 'NATURAL-PUBLIC-CASES.json'), _project_file(_PROJECT_ROOT, T58 / 'PARENT-REPLAY-CLOSURE.json'),
                 _project_file(_PROJECT_ROOT, T59 / 'PUBLIC-PROBE-CLOSURE.json'), _project_file(_PROJECT_ROOT, T59 / 'ROOT-READBACK.json'),
                 _project_file(_PROJECT_ROOT, T59 / 'S01-generation.batch.json'),
                 _project_file(_PROJECT_ROOT, T59 / 'FRESH-ROOTS-BEFORE-AUTHOR.json'), _project_file(_PROJECT_ROOT, T59 / 'COMPOSITIONS-BEFORE-AUTHOR.json')):
        bind(path)
    roots = []
    for index, category in SELECTION:
        raw = natural[index]
        label = 'natural:' + format(index, '02')
        scored = next(r for r in child_probe['rows'] if r['label'] == label)
        old = next(r for r in parent_probe['rows'] if r['label'] == label)
        assert raw['selected_action_key'] == old['selected_action_key'] == scored['parent_first_action']
        source = Path(raw['source_file'])
        block = json.loads((source.parent / 'START.json').read_text())
        composition = next(r for r in block['opponent_compositions'] if r['root_id'] == raw['root_id'])
        bind(source)
        bind(source.parent / 'START.json')
        bind(source.parent / 'end-freeze.json')
        for path, digest in block['frozen_files'].items():
            assert pin(Path(path))['sha256'] == digest, path
            bind(Path(path))
        for name, digest in block['source_manifest'].items():
            assert pin(_project_file(_PROJECT_ROOT, REPO / name)) == digest, name
            assert pin(source.parent / 'code_snapshot' / name) == digest, name
            bind(_project_file(_PROJECT_ROOT, REPO / name))
            bind(source.parent / 'code_snapshot' / name)
        assert raw['root_id'] not in {r['mother_root'] for r in roots}
        roots.append({'root_id': 't60:' + label, 'mother_root': raw['root_id'],
            'category': category, 'source_file': str(source), 'match_id': raw['match_id'],
            'source_window': raw['window_key'], 'focal_observation': raw['observation'],
            'parent_first': old['selected_action_key'], 'child_first': scored['first_action'],
            'expected_input_sha256': old['actual_input_sha256'],
            'expected_parent_scores': old['full_scores'], 'expected_child_scores': scored['scores'],
            'composition': composition, 'original_rows': [],
            'focal_seat': raw['window_key']['seat'], 'original_category': raw['category']})
    # 所有目标先登记，再读原路径；不用终分、赢家或未来牌选择来源。
    save(_project_file(_PROJECT_ROOT, HERE / 'SOURCE-SELECTION.json'), {'schema': 't60-known-public-before-path-read/1',
        'selection': SELECTION, 'roots': [{k: r[k] for k in
            ('root_id', 'mother_root', 'category', 'source_window', 'parent_first', 'child_first')} for r in roots],
        'terminal_outcome_used_for_selection': False, 'new_business_calls': 0})
    for source in sorted({r['source_file'] for r in roots}):
        wanted = {r['match_id']: r for r in roots if r['source_file'] == source}
        with gzip.open(source, 'rt') as stream:
            for line in stream:
                if not any(mid in line for mid in wanted):
                    continue
                row = json.loads(line)
                if row['match_id'] not in wanted:
                    continue
                root = wanted[row['match_id']]
                assert row['status'] == 'chosen' and not any('action_value_failed' in reason for reason in row['degraded_reasons'])
                assert row['root_id'] == root['mother_root']
                assert row['opponent_types_logical_1_2_3'] == root['composition']['opponent_types_logical_1_2_3']
                root.setdefault('permutation', row['permutation'])
                root.setdefault('initial_dealer', row['initial_dealer_physical'])
                assert row['permutation'] == root['permutation'] and row['initial_dealer_physical'] == root['initial_dealer']
                root['original_rows'].append({k: row[k] for k in
                    ('window_key', 'observation', 'legal_action_keys', 'selected_action_key', 'policy_id', 'seat')})
        print({'source': Path(source).parent.name, 'matched_tables': len(wanted)}, flush=True)
    for root in roots:
        groups, seen = [], set()
        for row in root.pop('original_rows'):
            w = canonical(row['window_key'])
            assert w not in seen
            seen.add(w)
            if not groups or frame_key(groups[-1][0]['window_key']) != frame_key(row['window_key']):
                groups.append([])
            groups[-1].append(row)
        cuts = [i for i, frame in enumerate(groups) if any(row['window_key'] == root['source_window'] for row in frame)]
        assert len(cuts) == 1
        cut = cuts[0]
        target = next(r for r in groups[cut] if r['window_key'] == root['source_window'])
        assert target['observation'] == root['focal_observation']
        assert target['selected_action_key'] == root['parent_first']
        assert root['child_first'] in target['legal_action_keys']
        root['whole_prefix'] = groups[:cut]
        root['current_hand_prefix'] = [frame for frame in groups[:cut]
            if frame[0]['window_key']['round_no'] == root['source_window']['round_no']]
        root['target_frame'] = groups[cut]
        root['original_hand_suffix'] = [frame for frame in groups[cut:]
            if frame[0]['window_key']['round_no'] == root['source_window']['round_no']]
        assert root['initial_dealer'] == 0 and root['permutation'][0] == root['focal_seat']
    with gzip.open(_project_file(_PROJECT_ROOT, HERE / 'SOURCE-MATERIALS.json.gz'), 'xb') as stream:
        stream.write(canonical({'schema': 't60-closed-T52-C-natural-public-prefix/1', 'roots': roots}) + b'\n')
    bind(_project_file(_PROJECT_ROOT, HERE / 'SOURCE-MATERIALS.json.gz'))
    bind(_project_file(_PROJECT_ROOT, HERE / 'SOURCE-SELECTION.json'))
    for name in ('parent', 'child'):
        package = _project_file(_PROJECT_ROOT, PARENT / 'S01-research-capacity') if name == 'parent' else _project_file(_PROJECT_ROOT, T59 / 'S01-model-output')
        for path in (package / 'candidate.py', package / 'generation.json'):
            bind(path)
    assert all(pin(Path(name)) == digest for name, digest in files.items())
    save(_project_file(_PROJECT_ROOT, HERE / 'PREPARED.json'), {'schema': 't60-natural-common-continuation-prepared/1',
        'status': 'prepared_no_START', 'files': files, 'python_version': sys.version,
        'parent_package': str((_project_file(_PROJECT_ROOT, PARENT / 'S01-research-capacity')).resolve()),
        'child_package': str((_project_file(_PROJECT_ROOT, T59 / 'S01-model-output')).resolve()),
        'batch_file': str((_project_file(_PROJECT_ROOT, T59 / 'S01-generation.batch.json')).resolve()),
        'parent_identity': parent_probe['candidate_identity'], 'child_identity': child_probe['candidate_identity'],
        'roots': [{'root_id': r['root_id'], 'mother_root': r['mother_root'], 'category': r['category'],
            'source_window': r['source_window'], 'whole_prefix_frames': len(r['whole_prefix']),
            'current_hand_prefix_frames': len(r['current_hand_prefix']),
            'original_suffix_decisions': sum(map(len, r['original_hand_suffix']))} for r in roots],
        'budgets': {'wall_clock_seconds': 3600, 'max_continuations': 20,
            'max_recovery_frames_per_root': 5000, 'steps_per_continuation': 5000,
            'capture': {'max_view_json_bytes': 33554432, 'max_total_json_bytes': 2147483648, 'max_unique_views': 12000}},
        'arm_order': ['P', 'C', 'B', 'D', 'R18'],
        'arms': {'P': 'parent throughout', 'C': 'child throughout',
            'B': 'child first action then parent', 'D': 'parent first action then child', 'R18': 'R18 throughout'},
        'no_new_hidden_sample': True, 'no_new_natural_table': True,
        'score_model_world_table_calls_in_preparation': 0,
        'scope': 'four exposed development sources, same complete world; not fresh confirmation or probability estimate'})
    print({'prepared': True, 'roots': 4, 'continuations_upper': 20, 'new_business_calls': 0})


if __name__ == '__main__':
    main()
