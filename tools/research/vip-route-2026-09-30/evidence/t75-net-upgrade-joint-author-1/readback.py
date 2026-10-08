"""核原答、56实际输入和全动作分值；只读文件，不新增评分或续打。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t75-net-upgrade-joint-author-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import argparse
import gzip
import json
import math
from pathlib import Path

from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents, parse_vip_eoh_reply
from root_load_and_probe import HERE, PARENT, canonical, pin, public_cases


def main(write_receipt=False):
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / 'S01-generation.batch.json'))
    parents = load_vip_parents([PARENT / 'S02-model-output'], batch)
    child = load_vip_parents([_project_file(_PROJECT_ROOT, HERE / 'S01-model-output')], batch)[0]
    parsed = parse_vip_eoh_reply((_project_file(_PROJECT_ROOT, HERE / 'RAW-REPLY.txt')).read_text(), 'm1', parents)
    assert parsed['source_raw'].encode() == (_project_file(_PROJECT_ROOT, HERE / 'candidate.py')).read_bytes()
    assert parsed['source'] == child['source']
    original = json.loads((_project_file(_PROJECT_ROOT, HERE / 'ROOT-AUTHOR-REPLY-FIRST-SEAL.json')).read_text())
    for name, digest in original['files'].items():
        assert pin(_project_file(_PROJECT_ROOT, HERE / name)) == digest, name
    preparation = json.loads((_project_file(_PROJECT_ROOT, HERE / 'AUTHOR-PREPARATION-CLOSED.json')).read_text())
    for name, digest in preparation['frozen_files'].items():
        assert pin(name) == digest, name
    plan = json.loads((_project_file(_PROJECT_ROOT, HERE / 'PUBLIC-PROBE-START.json')).read_text())
    for name, digest in plan['source_files'].items():
        assert pin(name) == digest, name
    closure = json.loads((_project_file(_PROJECT_ROOT, HERE / 'PUBLIC-PROBE-CLOSURE.json')).read_text())
    assert closure['complete_all_windows'] and closure['identity_stable']
    assert closure['primary_error'] is None and closure['readback_error'] is None
    assert closure['candidate_identity'] == child['identity'] and closure['parent_identity'] == parents[0]['identity']
    assert closure['actual_score_calls'] == closure['actual_full_inputs_readback'] == 56
    assert closure['actual_rule_calls'] == closure['actual_projection_calls'] == 56
    archive = _project_file(_PROJECT_ROOT, HERE / 'ACTUAL-CANDIDATE-PROBE-INPUTS.jsonl.gz')
    assert pin(archive) == closure['input_archive']
    inputs = {}
    with gzip.open(archive, 'rt') as stream:
        for line in stream:
            captured = json.loads(line)
            assert captured['label'] not in inputs
            assert hashlib_sha(captured['candidate_view']) == captured['view_sha256']
            inputs[captured['label']] = captured
    cases, _ = public_cases()
    assert [r['label'] for r in closure['rows']] == [c['label'] for c in cases]
    changes, scores, causal_choices = [], 0, []
    for row, case in zip(closure['rows'], cases):
        assert row['status'] == 'SCORED' and row['saved_before_score'] and row['full_legal_keys']
        captured = inputs[row['label']]
        reference = case['parent_reference']
        assert row['view_sha256'] == captured['view_sha256'] == reference['view_sha256']
        assert row['parent_first_action'] == reference['first_action']
        assert canonical(row['parent_scores']) == canonical(reference['scores'])
        keys = [entry['action_key'] for entry in row['scores']]
        assert len(set(keys)) == len(keys)
        assert set(keys) == {action['action_key'] for action in captured['candidate_view']['actions']}
        assert set(keys) == {entry['action_key'] for entry in row['parent_scores']}
        assert all(type(entry['score']) in (int, float) and math.isfinite(entry['score']) for entry in row['scores'])
        assert 0 < row['operations'] <= batch.max_operations
        first = sorted(row['scores'], key=lambda entry: (-entry['score'], entry['action_key']))[0]['action_key']
        assert first == row['first_action']
        assert row['behavior_changed'] == (first != row['parent_first_action'])
        if row['behavior_changed']:
            changes.append(row['label'])
        scores += len(keys)
        if 'causal_teacher_result' in case:
            teacher = case['causal_teacher_result']
            causal_choices.append({
                'root_id': row['label'], 'category': teacher['category'],
                'parent_first': row['parent_first_action'], 'child_first': first,
                'parent_known_wait_first': teacher['wait_first'],
                'parent_known_wait_minus_hu': teacher['wait_minus_hu'],
                'child_endpoint_not_yet_executed': True,
            })
    assert changes == closure['changed_windows']
    assert len(inputs) == len(closure['rows']) == 56 and len(causal_choices) == 18
    assert closure['normal_r18_fallbacks'] == closure['new_model_world_table_calls'] == 0
    files = {str(path.relative_to(HERE)): pin(path) for path in sorted(HERE.rglob('*'))
             if path.is_file() and path.name != 'ROOT-READBACK.json'
             and not path.name.endswith('.lock') and '__pycache__' not in path.parts}
    receipt = {'schema': 't75-root-pure-readback/1', 'complete': True,
               'candidate_identity': child['identity'], 'full_public_inputs_and_scores': 56,
               'actual_action_scores_read': scores, 'changed_windows': changes,
               'causal_target_choices': causal_choices,
               'new_score_graph_world_table_model_calls_in_readback': 0,
               'strength_or_release_claim': False, 'files': files}
    target = _project_file(_PROJECT_ROOT, HERE / 'ROOT-READBACK.json')
    if write_receipt:
        with target.open('xb') as stream:
            stream.write(canonical(receipt) + b'\n')
    else:
        assert receipt == json.loads(target.read_text())
    print({key: receipt[key] for key in ('complete', 'full_public_inputs_and_scores', 'actual_action_scores_read', 'changed_windows')})


def hashlib_sha(value):
    """规范化公开DTO的精确内容身份。"""
    import hashlib
    return hashlib.sha256(canonical(value)).hexdigest()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--write-receipt', action='store_true')
    main(parser.parse_args().write_receipt)
