"""复用一个已闭合的吃响应来源，纯文件准备，不评分或生成新牌山。

这是旧条件开发例，不能估海选发生率。冻结原相容世界的采样键及七个
公开前缀帧；完整教师牌只用于复原，作者和策略均不能读取。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t61-t59-response-same-start-2'

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


def canonical(value):
    """规范JSON保持观察、积分和时间字段原值，拒绝非有限数字。"""
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
    """新证据只写一次；已有START或收据不能被重试覆盖。"""
    with path.open('xb') as stream:
        stream.write(canonical(value) + b'\n')


def main():
    previous = _project_file(_PROJECT_ROOT, E / 't60-t59-natural-same-start-1')
    failed = _project_file(_PROJECT_ROOT, E / 't61-t59-response-same-start-1')
    failure = json.loads((failed / 'CLOSURE.json').read_text())
    assert not failure['complete'] and failure['actual_explicit_api_counts'].get('actual_vip_score_calls', 0) == 0
    assert failure['actual_explicit_api_counts'].get('continuations_dispatched', 0) == 0
    old = _project_file(_PROJECT_ROOT, E / 't33-highfan-followup-isolation-preparation-1')
    closure = _project_file(_PROJECT_ROOT, E / 't33-highfan-followup-isolation-closure-1')
    author = _project_file(_PROJECT_ROOT, E / 't59-qualifier-highfan-credit-author-1')
    public = _project_file(_PROJECT_ROOT, E / 't48-v3-natural-highfan-joint-author-1/PUBLIC-CASES.json')
    teacher = _project_file(_PROJECT_ROOT, E / 't32-new-multiwhite-source-preparation-1/root-08/single-hand-teacher-origin.json')
    previous_plan = json.loads((previous / 'PREPARED.json').read_text())
    assert json.loads((previous / 'CLOSURE-RECOVERY.json').read_text())['complete']
    sealed = json.loads((closure / 'RAW-FIRST-SEAL.json').read_text())
    assert pin(old / 'PREPARED.json') == sealed['files'][str((old / 'PREPARED.json').resolve())]
    accepted = json.loads((closure / 'ROOT-CLOSED-CHECK.json').read_text())
    assert accepted['status'] == 'accepted_engineering_only' and accepted['source_identity_rechecked']
    old_plan = json.loads((old / 'PREPARED.json').read_text())
    teacher_digest = old_plan['files'][str(teacher.resolve())]
    assert pin(teacher) == teacher_digest
    old_root = old_plan['roots'][3]
    nested = old_root['nested_start']
    case = json.loads(public.read_text())['cases'][3]
    probe = json.loads((author / 'PUBLIC-PROBE-CLOSURE.json').read_text())
    scored = next(row for row in probe['rows'] if row['label'] == 'public:3')
    assert case['window_key'] == nested['target_window']
    assert case['observation'] == nested['focal_observation']
    assert scored['parent_first_action'] == 'chi:1w,2w,3w' and scored['first_action'] == 'pass'
    assert old_root['permutation'] == [0, 1, 2, 3]
    assert nested['target_revision'] == nested['original_advance_cut'] == len(nested['prefix']) == 7
    root = {'root_id': 't61:public:3', 'mother_root': old_root['mother_root'],
        'category': 'known-conditional-three-white-response', 'focal_seat': 0,
        'permutation': old_root['permutation'], 'logical_labels': old_root['logical_labels'],
        'original_policy_metadata': old_root['policy_metadata'],
        'source_window': case['window_key'], 'focal_observation': case['observation'],
        'teacher_path': str(teacher.resolve()), 'base_sample_key': nested['base_sample_key'],
        'parent_first': scored['parent_first_action'], 'child_first': scored['first_action'],
        'expected_input_sha256': scored['view_sha256'],
        'expected_parent_scores': {c['action_key']: {'score': c['score'], 'trace': c['trace']}
                                   for c in scored['parent_scores']},
        'expected_child_scores': scored['scores'], 'target_frame': nested['target_records'],
        'whole_prefix': [[dict(row, selected_action_key=row['action_key']) for row in frame['records']]
                         for frame in nested['prefix']],
        'known_outcome_selected_historical_source': True,
        'source_kind': 'reused_T33_existing_public_consistent_hidden_world_not_natural'}
    save(_project_file(_PROJECT_ROOT, HERE / 'SOURCE-SELECTION.json'), {k: root[k] for k in
        ('root_id', 'mother_root', 'category', 'source_window', 'parent_first', 'child_first',
         'known_outcome_selected_historical_source', 'source_kind')})
    with gzip.open(_project_file(_PROJECT_ROOT, HERE / 'SOURCE-MATERIALS.json.gz'), 'xb') as stream:
        stream.write(canonical({'schema': 't61-known-response-source/1', 'roots': [root]}) + b'\n')
    files = dict(previous_plan['files'])
    for path in (Path(__file__), _project_file(_PROJECT_ROOT, HERE / 'run.py'), failed / 'run.py', failed / 'PREPARED.json', failed / 'CLOSURE.json', old / 'PREPARED.json', closure / 'RAW-FIRST-SEAL.json',
                 closure / 'ROOT-CLOSED-CHECK.json', teacher, public, author / 'PUBLIC-PROBE-CLOSURE.json',
                 previous / 'CLOSURE-RECOVERY.json', _project_file(_PROJECT_ROOT, HERE / 'SOURCE-SELECTION.json'), _project_file(_PROJECT_ROOT, HERE / 'SOURCE-MATERIALS.json.gz')):
        files[str(path.resolve())] = pin(path)
    for name, digest in files.items():
        assert pin(Path(name)) == digest, name
    save(_project_file(_PROJECT_ROOT, HERE / 'PREPARED.json'), {
        'schema': 't61-reused-conditional-response-prepared/1', 'status': 'prepared_no_START',
        'python_version': sys.version, 'files': files,
        **{k: previous_plan[k] for k in ('parent_package', 'child_package', 'batch_file',
                                         'parent_identity', 'child_identity')},
        'arm_order': ['P', 'C', 'B', 'D', 'R18'],
        'budgets': {'max_continuations': 5, 'steps_per_continuation': 5000,
                    'max_recovery_frames_per_root': 10, 'wall_clock_seconds': 1200,
                    'capture': {'max_total_json_bytes': 2147483648,
                                'max_unique_views': 12000, 'max_view_json_bytes': 67108864}},
        'new_mother_roots': 0, 'new_distinct_hidden_samples': 0,
        'prior_wrapper_failure': {'directory': str(failed.resolve()),
            'error': failure['error'], 'actual_explicit_api_counts': failure['actual_explicit_api_counts'],
            'new_actual_scores_or_continuations_in_prior_attempt': 0},
        'scope': 'one reused conditional world, five actual single-hand continuations; no strength or release'})
    print({'prepared': True, 'roots': 1, 'continuations_upper': 5,
           'new_scores_worlds_tables_model_calls': 0}, flush=True)


if __name__ == '__main__':
    main()
