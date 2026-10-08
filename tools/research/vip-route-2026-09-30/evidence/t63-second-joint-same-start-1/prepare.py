"""第二提案机械闭包后的五源纯准备，不评分、不复原或推进世界。

沿用T60四个公开自然控制及T61一个已知条件反例，根数与来源不按新成绩
改选。父代尾段使用已闭合T59实际路径；完整教师只供离线重建。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t63-second-joint-same-start-1'

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
E = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')
REPO = _PROJECT_ROOT
AUTHOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t62-earned-highfan-joint-revision-preparation-1')
FIRST = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t59-qualifier-highfan-credit-author-1')
NATURAL = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t60-t59-natural-same-start-1')
RESPONSE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t61-t59-response-same-start-2')


def canonical(value):
    """规范JSON不改变观察、规则事实、时间或积分。"""
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
    """新证据只写一次，不能重试覆盖START或失败结果。"""
    with path.open('xb') as stream:
        stream.write(canonical(value) + b'\n')


def load(path):
    return json.loads(path.read_text())


def compressed(path):
    with gzip.open(path, 'rt') as stream:
        return json.load(stream)


def check_seal(folder, name):
    seal = load(folder / name)
    assert seal['complete']
    for relative, digest in seal['files'].items():
        assert pin(folder / relative) == digest, relative


def main():
    check_seal(AUTHOR, 'ROOT-READBACK.json')
    check_seal(FIRST, 'ROOT-READBACK.json')
    check_seal(NATURAL, 'CLOSURE-RECOVERY.json')
    check_seal(RESPONSE, 'ROOT-READBACK.json')
    candidate = load(_project_file(_PROJECT_ROOT, AUTHOR / 'PUBLIC-PROBE-CLOSURE.json'))
    parent = load(_project_file(_PROJECT_ROOT, FIRST / 'PUBLIC-PROBE-CLOSURE.json'))
    assert candidate['complete_all_windows'] and candidate['parent_identity'] == parent['candidate_identity']
    child_rows = {r['label']: r for r in candidate['rows']}
    parent_rows = {r['label']: r for r in parent['rows']}
    files = dict(load(_project_file(_PROJECT_ROOT, NATURAL / 'PREPARED.json'))['files'])

    def bind(path):
        files[str(path.resolve())] = pin(path)

    roots = []
    for folder, source_kind, originals in (
        (NATURAL, 'known-natural-original-world', compressed(_project_file(_PROJECT_ROOT, NATURAL / 'SOURCE-MATERIALS.json.gz'))['roots']),
        (RESPONSE, 'known-conditional-existing-hidden-world', compressed(_project_file(_PROJECT_ROOT, RESPONSE / 'SOURCE-MATERIALS.json.gz'))['roots'])):
        with gzip.open(folder / 'decisions.jsonl.gz', 'rt') as stream:
            decisions = [json.loads(line) for line in stream]
        for original in originals:
            label = original['root_id'].split(':', 1)[1]
            p, c = parent_rows[label], child_rows[label]
            assert c['view_sha256'] == p['view_sha256'] == original['expected_input_sha256']
            teacher = (folder / original['root_id'].replace(':', '-') / 'TEACHER-ORIGIN.json'
                       if source_kind == 'known-natural-original-world' else Path(original['teacher_path']))
            bind(teacher)
            tail = [{k: row[k] for k in ('window_key', 'observation', 'selected_action_key', 'legal_action_keys', 'seat')}
                    for row in decisions if row['root_id'] == original['root_id'] and row['arm'] == 'C']
            assert tail and next(row for row in tail if row['window_key'] == original['source_window'])['selected_action_key'] == p['first_action']
            root = {'root_id': 't63:' + label, 'mother_root': original['mother_root'],
                'category': original['category'], 'source_kind': source_kind,
                'permutation': original['permutation'], 'focal_seat': original['focal_seat'],
                'teacher_path': str(teacher.resolve()), 'source_window': original['source_window'],
                'focal_observation': original['focal_observation'], 'target_frame': original['target_frame'],
                'prefix': original['current_hand_prefix'] if source_kind == 'known-natural-original-world' else original['whole_prefix'],
                'parent_first': p['first_action'], 'child_first': c['first_action'],
                'expected_input_sha256': p['view_sha256'],
                'expected_parent_scores': {x['action_key']: {'score': x['score'], 'trace': x['trace']} for x in p['scores']},
                'expected_child_scores': c['scores'], 'expected_parent_full_tail': tail}
            if source_kind == 'known-natural-original-world':
                root['composition'] = original['composition']
            else:
                root['base_sample_key'] = original['base_sample_key']
                root['original_policy_metadata'] = original['original_policy_metadata']
            roots.append(root)
        for name in ('SOURCE-MATERIALS.json.gz', 'decisions.jsonl.gz', 'PREPARED.json'):
            bind(folder / name)
    assert len(roots) == 5 and len({r['mother_root'] for r in roots}) == 5
    save(_project_file(_PROJECT_ROOT, HERE / 'SOURCE-SELECTION.json'), {'schema': 't63-fixed-existing-five-sources/1',
        'roots': [{k: r[k] for k in ('root_id', 'mother_root', 'category', 'source_kind', 'source_window', 'parent_first', 'child_first')} for r in roots],
        'selection_inherited_before_second_author': True, 'new_outcomes_used_for_selection': False,
        'response_known_outcome_selected_historically': True, 'new_business_calls': 0})
    with gzip.open(_project_file(_PROJECT_ROOT, HERE / 'SOURCE-MATERIALS.json.gz'), 'xb') as stream:
        stream.write(canonical({'schema': 't63-existing-source-materials/1', 'roots': roots}) + b'\n')
    for path in (Path(__file__), _project_file(_PROJECT_ROOT, HERE / 'run.py'), _project_file(_PROJECT_ROOT, HERE / 'SOURCE-SELECTION.json'), _project_file(_PROJECT_ROOT, HERE / 'SOURCE-MATERIALS.json.gz'),
                 _project_file(_PROJECT_ROOT, AUTHOR / 'ROOT-READBACK.json'), _project_file(_PROJECT_ROOT, AUTHOR / 'PUBLIC-PROBE-CLOSURE.json'), _project_file(_PROJECT_ROOT, FIRST / 'ROOT-READBACK.json'),
                 _project_file(_PROJECT_ROOT, FIRST / 'PUBLIC-PROBE-CLOSURE.json'), _project_file(_PROJECT_ROOT, NATURAL / 'CLOSURE-RECOVERY.json'), _project_file(_PROJECT_ROOT, RESPONSE / 'ROOT-READBACK.json'),
                 _project_file(_PROJECT_ROOT, AUTHOR / 'S02-generation.batch.json'), _project_file(_PROJECT_ROOT, FIRST / 'FRESH-ROOTS-BEFORE-AUTHOR.json'),
                 _project_file(_PROJECT_ROOT, FIRST / 'COMPOSITIONS-BEFORE-AUTHOR.json')):
        bind(path)
    for folder in (_project_file(_PROJECT_ROOT, FIRST / 'S01-model-output'), _project_file(_PROJECT_ROOT, AUTHOR / 'S02-model-output')):
        for name in ('generation.json', 'candidate.py'):
            bind(folder / name)
    for name, digest in files.items():
        assert pin(Path(name)) == digest, name
    save(_project_file(_PROJECT_ROOT, HERE / 'PREPARED.json'), {'schema': 't63-second-joint-common-continuation-prepared/1',
        'status': 'prepared_no_START', 'python_version': sys.version, 'files': files,
        'parent_package': str((_project_file(_PROJECT_ROOT, FIRST / 'S01-model-output')).resolve()),
        'child_package': str((_project_file(_PROJECT_ROOT, AUTHOR / 'S02-model-output')).resolve()),
        'batch_file': str((_project_file(_PROJECT_ROOT, AUTHOR / 'S02-generation.batch.json')).resolve()),
        'parent_identity': parent['candidate_identity'], 'child_identity': candidate['candidate_identity'],
        'arm_order': ['P', 'C', 'B', 'D', 'R18'],
        'budgets': {'max_continuations': 25, 'steps_per_continuation': 5000,
                    'max_recovery_frames_per_root': 5000, 'wall_clock_seconds': 3600,
                    'capture': {'max_total_json_bytes': 2147483648,
                                'max_unique_views': 12000, 'max_view_json_bytes': 67108864}},
        'new_independent_roots': 0, 'new_natural_complete_tables': 0,
        'scope': 'fixed four existing natural plus one known conditional current-hand sources; no confirmation or deadline credit'})
    print({'prepared': True, 'sources': 5, 'max_continuations': 25, 'new_business_calls': 0})


if __name__ == '__main__':
    main()
