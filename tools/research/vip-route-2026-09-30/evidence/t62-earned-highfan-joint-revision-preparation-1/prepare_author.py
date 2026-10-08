"""第二联合提案的纯准备；不调用作者、不评分、不生成留出世界。"""

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
from pathlib import Path
import hashlib
import json

from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents, run_vip_eoh_generate

HERE = Path(__file__).resolve().parent
PREVIOUS = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t59-qualifier-highfan-credit-author-1')


def pin(path):
    raw = path.read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def save(name, value):
    with (_project_file(_PROJECT_ROOT, HERE / name)).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    feedback = json.loads((_project_file(_PROJECT_ROOT, HERE / 'MECHANISM-FEEDBACK.json')).read_text())
    for name, digest in feedback['evidence_pins'].items():
        assert pin(Path(name)) == digest
    readback = json.loads((_project_file(_PROJECT_ROOT, PREVIOUS / 'ROOT-READBACK.json')).read_text())
    assert readback['complete']
    for name, digest in readback['files'].items():
        assert pin(_project_file(_PROJECT_ROOT, PREVIOUS / name)) == digest
    raw_batch = json.loads((_project_file(_PROJECT_ROOT, PREVIOUS / 'S01-generation.batch.json')).read_text())
    raw_batch['batch_id'] = 'vip-t62-T59-second-joint-earned-highfan-20261002'
    raw_batch['budgets']['model_calls'] = 1
    save('S02-generation.batch.json', raw_batch)
    batch_file = _project_file(_PROJECT_ROOT, HERE / 'S02-generation.batch.json')
    batch = VipEohBatch.read(batch_file)
    package = _project_file(_PROJECT_ROOT, PREVIOUS / 'S01-model-output')
    parents = load_vip_parents([package], batch)
    assert len(parents) == 1 and parents[0]['identity']['candidate_id'] == feedback['true_parent_candidate_id']
    save('PARENTS-FROZEN.json', parents)
    text = (_project_file(_PROJECT_ROOT, HERE / 'FROZEN-FEEDBACK.txt')).read_text()
    emission = run_vip_eoh_generate(batch_file=batch_file, out_dir=_project_file(_PROJECT_ROOT, HERE / 'S02-prompt-emission'),
        operator='m1', parent_paths=(package,), feedback=text)
    files = {str(path): pin(path) for path in [Path(__file__), _project_file(_PROJECT_ROOT, HERE / 'MECHANISM-FEEDBACK.json'),
        _project_file(_PROJECT_ROOT, HERE / 'FROZEN-FEEDBACK.txt'), _project_file(_PROJECT_ROOT, HERE / 'PARENTS-FROZEN.json'), batch_file,
        _project_file(_PROJECT_ROOT, PREVIOUS / 'ROOT-READBACK.json'), _project_file(_PROJECT_ROOT, PREVIOUS / 'FRESH-ROOTS-BEFORE-AUTHOR.json'),
        _project_file(_PROJECT_ROOT, PREVIOUS / 'COMPOSITIONS-BEFORE-AUTHOR.json')]}
    files.update(feedback['evidence_pins'])
    save('AUTHOR-PREPARATION-CLOSED.json', {'schema': 't62-second-joint-author-preparation/1',
        'status': 'prepared_no_author', 'operator': 'm1', 'proposal_number_in_T59_joint_batch': 2,
        'max_new_proposals_in_joint_batch': 2, 'true_parent_candidate_id': feedback['true_parent_candidate_id'],
        'prompt_sha256': emission['prompt_sha256'], 'frozen_files': files,
        'actual_new_model_score_world_table_calls': 0,
        'fresh8_and_reserved128_remain_previous_pre_author_frozen_unseen': True})
    print({'prepared': True, 'proposal_number': 2, 'new_models_scores_worlds_tables': 0})


if __name__ == '__main__':
    main()
