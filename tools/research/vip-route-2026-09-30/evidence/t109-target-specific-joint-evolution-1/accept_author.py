"""首封真实委派原答并装载；回放封装不算新的模型调用，不实际评分。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t109-target-specific-joint-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from hangma_bot.offline.vip_eoh_generate import (
    VipEohBatch, build_vip_eoh_prompt, load_vip_parents, parse_vip_eoh_reply, run_vip_eoh_generate,
)
from hangma_bot.policy.action_value_executor import ActionValueExecutor

HERE = Path(__file__).resolve().parent


def canonical(value):
    """规范有限JSON，原模型源码字节单独保留。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def pin(path):
    """签收实际交付字节和原冻结材料。"""
    raw = Path(path).read_bytes()
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def save(name, value):
    """新建收据，静态失败及原答不得覆盖。"""
    with (_project_file(_PROJECT_ROOT, HERE / name)).open('xb') as stream:
        stream.write(canonical(value) + b'\n')


def main(delegator):
    """真m1父和原答先封条，静态失败按失败保存，不补模型答复。"""
    prep = json.loads((_project_file(_PROJECT_ROOT, HERE / 'AUTHOR-PREPARATION-CLOSED-REVISION-2.json')).read_text())
    assert prep['complete'] and all(pin(p) == h for p, h in prep['frozen_files'].items())
    delivered = {n: pin(_project_file(_PROJECT_ROOT, HERE / n)) for n in ('RAW-REPLY.txt', 'candidate.py', 'STATIC-CHECKS.json', 'AUTHOR-NOTE.md')}
    save('ROOT-AUTHOR-REPLY-FIRST-SEAL.json', {'schema': 't109-first-real-author-seal/1',
        'files': delivered, 'formal_parent': prep['formal_parent'], 'operator': 'm1',
        'requested_model': 'gpt-6.1-sol', 'requested_effort': 'max',
        'actual_author_delegations': 1, 'underlying_api_calls_and_tokens': None,
        'delegator': delegator, 'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'admitted': False})
    batch_file = _project_file(_PROJECT_ROOT, HERE / 'AUTHOR-BATCH.json')
    batch = VipEohBatch.read(batch_file)
    parent_path = Path(json.loads((_project_file(_PROJECT_ROOT, HERE / 'PARENT-IDENTITY.json')).read_text())['path'])
    parent = load_vip_parents([parent_path], batch)[0]
    raw = (_project_file(_PROJECT_ROOT, HERE / 'RAW-REPLY.txt')).read_text()
    failure = None
    try:
        parsed = parse_vip_eoh_reply(raw, 'm1', [parent])
        assert parsed['source_raw'].encode() == (_project_file(_PROJECT_ROOT, HERE / 'candidate.py')).read_bytes()
        assert delivered['candidate.py']['bytes'] <= 65536
        ActionValueExecutor(parsed['source'], max_operations=batch.max_operations,
                            max_local_collection_size=batch.projection_limits.max_nodes)
    except BaseException as exc:
        failure = {'type': type(exc).__name__, 'reason': str(exc)}
    save('ROOT-STATIC-ACCEPTANCE.json', {'complete': failure is None, 'primary_failure': failure,
        'actual_rules_scores_worlds_tables': 0, 'actual_new_model_calls': 0})
    if failure is not None:
        raise SystemExit(1)
    feedback = (_project_file(_PROJECT_ROOT, HERE / 'FROZEN-FEEDBACK.txt')).read_text()
    packet, _ = build_vip_eoh_prompt(batch, 'm1', [parent], feedback)
    assert packet.sha256 == prep['prompt_sha256'] == pin(_project_file(_PROJECT_ROOT, HERE / 'S01-prompt-emission/prompt.txt'))['sha256']
    save('REPLAY-ENVELOPE.json', {'schema': 'sitin-generation-reply/1',
        'captured_at_utc': datetime.now(timezone.utc).isoformat(), 'origin': 'delegated_model_reply',
        'provider': 'codex-collaboration', 'model': 'unknown', 'finish_reason': 'stop',
        'prompt_sha256': packet.sha256, 'reply': raw, 'delegator': delegator,
        'note': 'one actual author delegation; replay makes zero additional model calls; underlying usage unknown'})
    generated = run_vip_eoh_generate(batch_file=batch_file, out_dir=_project_file(_PROJECT_ROOT, HERE / 'S01-model-output'),
        operator='m1', parent_paths=[parent_path], backend='replay', feedback=feedback,
        reply_file=_project_file(_PROJECT_ROOT, HERE / 'REPLAY-ENVELOPE.json'))
    assert generated['status'] == 'loaded_not_admitted' and generated['identity_stable']
    candidate = load_vip_parents([_project_file(_PROJECT_ROOT, HERE / 'S01-model-output')], batch)[0]
    def signatures(source):
        tree = ast.parse(source)
        return {n.name: ast.dump(n, include_attributes=False) for n in tree.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    old, new = signatures(parent['source']), signatures(candidate['source'])
    changed = [k for k in sorted(set(old) | set(new)) if old.get(k) != new.get(k)]
    save('ROOT-SOURCE-SCOPE.json', {'complete': True, 'parent_id': parent['identity']['candidate_id'],
        'candidate_identity': candidate['identity'], 'changed_or_added_functions': changed,
        'all_frozen_material_stable': all(pin(p) == h for p, h in prep['frozen_files'].items()),
        'all_delivered_files_stable': all(pin(_project_file(_PROJECT_ROOT, HERE / p)) == h for p, h in delivered.items()),
        'actual_rules_scores_worlds_tables': 0, 'actual_new_model_calls': 0,
        'strength_deadline_admission': False})
    print({'loaded_not_admitted': True, 'changed_functions': changed,
           'candidate_id': candidate['identity']['candidate_id'], 'new_model_calls': 0})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--delegator', required=True)
    main(parser.parse_args().delegator)
