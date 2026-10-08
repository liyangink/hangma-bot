"""保留首版输入大小失败，只省略重复解释和部分样例节点；原机械范围不变。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t110-compact-target-cost-joint-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import hashlib
import json
from pathlib import Path

from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents, run_vip_eoh_generate
from prepare import canonical, pin, save

HERE = Path(__file__).resolve().parent
OLD = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t109-target-specific-joint-evolution-1')


def main():
    """不重建种子、对手或规则；两次emit均零模型调用，然后才允许真实API。"""
    original = json.loads((_project_file(_PROJECT_ROOT, HERE / 'COMPACT-PUBLIC-FEEDBACK.json')).read_text())
    parent_path = Path(json.loads((_project_file(_PROJECT_ROOT, HERE / 'PARENT-IDENTITY.json')).read_text())['path'])
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / 'AUTHOR-BATCH.json'))
    parent = load_vip_parents([parent_path], batch)[0]
    feedback = json.loads(canonical(original))
    source = feedback.pop('failed_Sol_source_reference_not_formal_parent')
    feedback['failed_Sol_reference'] = {
        'sha256': hashlib.sha256(source.encode()).hexdigest(),
        'source_omitted_from_author_feedback': True, 'formal_parent': False,
        'effort_expression': 'D + 0.18 * natural_discard + 0.32 * white_discard + 0.50 * terminal_draw',
        'full_score_not_validated': True}
    for new_case, old_case in zip(feedback['public_cases'], original['public_cases']):
        assert new_case['label'] == old_case['label']
        new_case['T101_actual_scores'] = [{k: row[k] for k in ('action_key', 'score')}
            for row in old_case['T101_actual_scores']]
        new_case['parent_score_traces_omitted_in_author_summary'] = True
        new_case['waiting_samples'] = old_case['waiting_samples'][:2]
        new_case['scope'] = 'partial public DTO summary; at most two selected waiting nodes, all remaining nodes omitted'
        assert [(row['action_key'], row['score']) for row in new_case['T101_actual_scores']] == [
            (row['action_key'], row['score']) for row in old_case['T101_actual_scores']]
    assert len(feedback['public_cases']) == 11
    prefix = (_project_file(_PROJECT_ROOT, HERE / 'FEEDBACK-PREFIX.txt')).read_text().replace(
        '每处最多三个真实等待节点', '每处最多两个真实等待节点').replace(
        '该源码只是参考，不是正式父。',
        '该源码只作失败参考，完整原码未放入本次作者提示；只给实际身份、成本表达式和诊断，不是正式父。')
    with (_project_file(_PROJECT_ROOT, HERE / 'FEEDBACK-PREFIX-REVISION-2.txt')).open('x') as stream:
        stream.write(prefix)
    save('COMPACT-PUBLIC-FEEDBACK-REVISION-2.json', feedback)
    text = prefix + '\n' + canonical(feedback).decode()
    with (_project_file(_PROJECT_ROOT, HERE / 'FROZEN-FEEDBACK-REVISION-2.txt')).open('x') as stream:
        stream.write(text)
    emitted = run_vip_eoh_generate(batch_file=_project_file(_PROJECT_ROOT, HERE / 'AUTHOR-BATCH.json'),
        out_dir=_project_file(_PROJECT_ROOT, HERE / 'S01-prompt-emission-revision-2'), operator='m1',
        parent_paths=[parent_path], feedback=text)
    assert emitted['status'] == 'prompt_emitted' and emitted['identity_stable']
    prompt_bytes = (_project_file(_PROJECT_ROOT, HERE / 'S01-prompt-emission-revision-2/prompt.txt')).stat().st_size
    assert prompt_bytes <= 240000
    files = [p for p in HERE.iterdir() if p.is_file() and not p.name.endswith(('.log', '.lock'))
        and 'vip-eoh-ledger' not in p.name and p.name != 'README.md']
    inputs = [_project_file(_PROJECT_ROOT, OLD / name) for name in ('S02-ACTUAL-FAILURE-READBACK.json',
        'S01-public-probe/FAILED-MECHANICAL-READBACK.json', 'S01-OWN-TARGET-COST-ALGEBRA.json',
        'S01-model-output/candidate.py', 'SELECTED-PUBLIC-FEEDBACK.json')]
    inputs += [parent_path / 'candidate.py', parent_path / 'generation.json']
    save('AUTHOR-PREPARATION-CLOSED.json', {'complete': True, 'before_actual_API_call': True,
        'formal_parent': parent['identity']['candidate_id'],
        'frozen_files': {str(p): pin(p) for p in files+inputs},
        'prompt_bytes': prompt_bytes, 'prompt_sha256': emitted['prompt_sha256'],
        'public_mechanical_windows': 103, 'unique_full_mechanical_DTOs': 97,
        'partial_author_feedback_cases': 11, 'waiting_samples_per_case_max': 2,
        'whole_parent_source_contract_and_fields_kept': True,
        'original_seed_and_opponent_files_reused_without_modification': True,
        'first_size_guard_failure_retained': True,
        'new_models_rules_scores_worlds_tables': 0, 'max_actual_author_calls': 2,
        'automatic_retry': False, 'actual_feedback_file': 'FROZEN-FEEDBACK-REVISION-2.txt'})
    print({'prepared': True, 'prompt_bytes': prompt_bytes, 'public_mechanical_windows': 103,
           'partial_author_feedback_cases': 11, 'original_seeds_preserved': True}, flush=True)


if __name__ == '__main__':
    main()
