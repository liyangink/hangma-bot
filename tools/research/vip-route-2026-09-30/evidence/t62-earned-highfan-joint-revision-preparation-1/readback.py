"""纯读原答、全部实际输入和38份全动作输出，核根签收后封闭。

只校验原件与有限值、分母、首选及相同公开输入；不重新评分、构图、
推进世界或调用模型。封条生成后再调用本程序只能读回，不能覆盖证据。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t62-earned-highfan-joint-revision-preparation-1'

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
import hashlib
import json
import math
from pathlib import Path

from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents, parse_vip_eoh_reply

HERE = Path(__file__).resolve().parent


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def pin(path):
    raw = path.read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def main(write_receipt=False):
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / 'S02-generation.batch.json'))
    parent_path = _project_file(_PROJECT_ROOT, HERE.parent / 't59-qualifier-highfan-credit-author-1/S01-model-output')
    parents = load_vip_parents([parent_path], batch)
    child = load_vip_parents([_project_file(_PROJECT_ROOT, HERE / 'S02-model-output')], batch)[0]
    parsed = parse_vip_eoh_reply((_project_file(_PROJECT_ROOT, HERE / 'RAW-REPLY.txt')).read_text(), 'm1', parents)
    assert parsed['source_raw'].encode() == (_project_file(_PROJECT_ROOT, HERE / 'candidate.py')).read_bytes()
    assert parsed['source'] == child['source']
    original = json.loads((_project_file(_PROJECT_ROOT, HERE / 'ROOT-AUTHOR-REPLY-FIRST-SEAL.json')).read_text())
    for name, digest in original['files'].items():
        assert pin(_project_file(_PROJECT_ROOT, HERE / name)) == digest
    preparation = json.loads((_project_file(_PROJECT_ROOT, HERE / 'AUTHOR-PREPARATION-CLOSED.json')).read_text())
    for name, digest in preparation['frozen_files'].items():
        assert pin(Path(name)) == digest
    plan = json.loads((_project_file(_PROJECT_ROOT, HERE / 'PUBLIC-PROBE-START.json')).read_text())
    for name, digest in plan['source_files'].items():
        assert pin(Path(name)) == digest
    closure = json.loads((_project_file(_PROJECT_ROOT, HERE / 'PUBLIC-PROBE-CLOSURE.json')).read_text())
    assert closure['complete_all_windows'] and closure['identity_stable']
    assert closure['candidate_identity'] == child['identity']
    assert closure['parent_identity'] == parents[0]['identity']
    assert closure['actual_score_calls'] == closure['actual_full_inputs_readback'] == 38
    archive = _project_file(_PROJECT_ROOT, HERE / 'ACTUAL-CANDIDATE-PROBE-INPUTS.jsonl.gz')
    assert pin(archive) == closure['input_archive']
    inputs = {}
    with gzip.open(archive, 'rt') as stream:
        for line in stream:
            item = json.loads(line)
            assert item['label'] not in inputs
            assert hashlib.sha256(canonical(item['candidate_view'])).hexdigest() == item['view_sha256']
            inputs[item['label']] = item
    changes, scores = [], 0
    for row in closure['rows']:
        assert row['status'] == 'SCORED' and row['saved_before_score'] and row['full_legal_keys']
        captured = inputs[row['label']]
        assert row['view_sha256'] == captured['view_sha256']
        keys = [e['action_key'] for e in row['scores']]
        assert len(set(keys)) == len(keys)
        assert set(keys) == {a['action_key'] for a in captured['candidate_view']['actions']}
        assert set(keys) == {e['action_key'] for e in row['parent_scores']}
        assert all(type(e['score']) in (int, float) and math.isfinite(e['score']) for e in row['scores'])
        assert 0 < row['operations'] <= batch.max_operations
        first = sorted(row['scores'], key=lambda e: (-e['score'], e['action_key']))[0]['action_key']
        assert first == row['first_action']
        assert row['behavior_changed'] == (first != row['parent_first_action'])
        if row['behavior_changed']:
            changes.append(row['label'])
        scores += len(keys)
    assert changes == closure['changed_windows']
    assert len(inputs) == len(closure['rows']) == 38
    assert closure['normal_r18_fallbacks'] == closure['new_model_world_table_calls'] == 0
    files = {}
    for path in sorted(HERE.rglob('*')):
        if (path.is_file() and path.name not in ('ROOT-READBACK.json',)
                and not path.name.endswith('.lock') and '__pycache__' not in path.parts):
            files[str(path.relative_to(HERE))] = pin(path)
    receipt = {'schema': 't62-root-pure-readback/1', 'complete': True,
        'candidate_identity': child['identity'], 'full_public_inputs_and_scores': 38,
        'actual_action_scores_read': scores, 'changed_windows': changes,
        'new_score_graph_world_table_model_calls_in_readback': 0,
        'strength_or_release_claim': False, 'files': files}
    target = _project_file(_PROJECT_ROOT, HERE / 'ROOT-READBACK.json')
    if write_receipt:
        with target.open('xb') as stream:
            stream.write(canonical(receipt) + b'\n')
    else:
        assert receipt == json.loads(target.read_text())
    print({k: receipt[k] for k in ('complete', 'full_public_inputs_and_scores', 'actual_action_scores_read', 'changed_windows')})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--write-receipt', action='store_true')
    main(parser.parse_args().write_receipt)
