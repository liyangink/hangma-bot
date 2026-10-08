"""利用已闭合机械与条件反馈准备第二份联合公式，不读取正在运行的自然桌。"""

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
import ast
import json
from pathlib import Path

from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents, run_vip_eoh_generate
from prepare import canonical, pin, save

HERE = Path(__file__).resolve().parent


def main():
    """保持同一真父和共享最多两作者账本，当前自然桌成绩不进入输入。"""
    public = json.loads((_project_file(_PROJECT_ROOT, HERE / 'S01-public-probe/ROOT-READBACK.json')).read_text())
    behavior = json.loads((_project_file(_PROJECT_ROOT, HERE / 'S01-public-probe/BEHAVIOR-SUMMARY.json')).read_text())
    tails = json.loads((_project_file(_PROJECT_ROOT, HERE / 'S01-CONTINUATION-CLOSED-SUMMARY.json')).read_text())
    assert public['complete'] and public['windows'] == 103
    assert tails['complete'] and tails['current_hand_continuations'] == 18
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / 'AUTHOR-BATCH.json'))
    parent_path = Path(json.loads((_project_file(_PROJECT_ROOT, HERE / 'PARENT-IDENTITY.json')).read_text())['path'])
    parent = load_vip_parents([parent_path], batch)[0]
    first = load_vip_parents([_project_file(_PROJECT_ROOT, HERE / 'S01-model-output')], batch)[0]
    ledger = json.loads((_project_file(_PROJECT_ROOT, HERE / 'AUTHOR-BATCH.vip-eoh-ledger.json')).read_text())
    calls = [row for row in ledger['reservations'] if row['call_started']]
    assert len(calls) == 1 and calls[0]['status'] == 'settled'
    summary = json.loads((_project_file(_PROJECT_ROOT, HERE / 'COMPACT-PUBLIC-FEEDBACK-REVISION-2.json')).read_text())
    summary.pop('failed_Sol_reference')
    summary.pop('T109_S01_failure')
    actual_rows = json.loads((_project_file(_PROJECT_ROOT, HERE / 'S01-public-probe/CLOSURE.json')).read_text())['rows']
    by_label = {row['label']: row for row in actual_rows}
    for case in summary['public_cases']:
        actual = by_label[case['label']]
        case['S01_first'] = actual['child_first']
        case['S01_actual_scores'] = [{k: row[k] for k in ('action_key', 'score', 'trace')}
                                   for row in actual['child_scores']['entries']]
    conditional = []
    for source in tails['results']:
        for result in source['results']:
            conditional.append({'source': source['source'], 'target': result['target'],
                'C_minus_P': result['C_minus_P'], 'A_minus_P': result['A_minus_P'],
                'arms': {arm: {'first': outcome['executed_first'],
                    'focal_net_score': outcome['focal_net_score'],
                    'fan': outcome['settlement']['fan'],
                    'winner_seat': outcome['settlement']['winner_seat'],
                    'details': outcome['settlement']['details'],
                    'forced_first_count': outcome['forced_first_count']}
                    for arm, outcome in result['results'].items()},
                'scope': 'known single continuation outcomes, not action gold or natural probability'})
    feedback = {'public_controls': summary,
        'S01_reference_source_not_formal_parent': first['source'],
        'S01_reference_identity': first['identity']['candidate_id'],
        'S01_mechanical': {'windows': 103, 'actual_scores': 97, 'finite_legal_outputs': 833,
            'max_operations': public['max_operations'], 'normal_R18_fallbacks': 0},
        'behavior': {k: behavior[k] for k in ('first_changed_windows', 'ranking_changed_windows', 'first_change_kinds')},
        'all_first_changes': [row for row in behavior['rows'] if row['first_changed']],
        'target_cost_component': json.loads((_project_file(_PROJECT_ROOT, HERE / 'S01-OWN-TARGET-COST-READBACK.json')).read_text()),
        'conditional_results': conditional,
        'actual_parent_and_child_scores_in_tails': tails['actual_vip_scores_by_arm'],
        'natural_pilot_running_but_all_results_unread_and_excluded': True,
        'no_hidden_hands_walls_teacher_paths_or_new_source_seeds': True}
    save('S02-COMPACT-FEEDBACK.json', feedback)
    prefix = (_project_file(_PROJECT_ROOT, HERE / 'S02-FEEDBACK-PREFIX.txt')).read_text()
    text = prefix + '\n' + canonical(feedback).decode()
    with (_project_file(_PROJECT_ROOT, HERE / 'S02-FROZEN-FEEDBACK.txt')).open('x') as stream:
        stream.write(text)
    result = run_vip_eoh_generate(batch_file=_project_file(_PROJECT_ROOT, HERE / 'AUTHOR-BATCH.json'),
        out_dir=_project_file(_PROJECT_ROOT, HERE / 'S02-prompt-emission'), operator='m1', parent_paths=[parent_path], feedback=text)
    assert result['status'] == 'prompt_emitted' and result['identity_stable']
    prompt_bytes = (_project_file(_PROJECT_ROOT, HERE / 'S02-prompt-emission/prompt.txt')).stat().st_size
    assert prompt_bytes <= 300000, '第二份增加实际参考源码和解释，仍保持紧凑上界'
    probe = (_project_file(_PROJECT_ROOT, HERE / 'probe.py')).read_text().replace('AUTHOR-PREPARATION-CLOSED.json',
                                                 'S02-AUTHOR-PREPARATION-CLOSED.json')
    ast.parse(probe)
    with (_project_file(_PROJECT_ROOT, HERE / 'S02-probe.py')).open('x') as stream:
        stream.write(probe)
    files = [Path(__file__), _project_file(_PROJECT_ROOT, HERE / 'run_second_author.py'), _project_file(_PROJECT_ROOT, HERE / 'S02-probe.py'),
        _project_file(_PROJECT_ROOT, HERE / 'S02-FEEDBACK-PREFIX.txt'), _project_file(_PROJECT_ROOT, HERE / 'S02-COMPACT-FEEDBACK.json'),
        _project_file(_PROJECT_ROOT, HERE / 'S02-FROZEN-FEEDBACK.txt'), _project_file(_PROJECT_ROOT, HERE / 'AUTHOR-BATCH.json'), _project_file(_PROJECT_ROOT, HERE / 'EVOLUTION-PLAN.json'),
        _project_file(_PROJECT_ROOT, HERE / 'PARENT-IDENTITY.json'), _project_file(_PROJECT_ROOT, HERE / 'PUBLIC-PANEL.json'),
        _project_file(_PROJECT_ROOT, HERE / 'FRESH-ROOTS-BEFORE-AUTHOR.json'), _project_file(_PROJECT_ROOT, HERE / 'COMPOSITIONS.json'),
        _project_file(_PROJECT_ROOT, HERE / 'S01-model-output/candidate.py'), _project_file(_PROJECT_ROOT, HERE / 'S01-model-output/generation.json'),
        _project_file(_PROJECT_ROOT, HERE / 'S01-public-probe/ROOT-READBACK.json'), _project_file(_PROJECT_ROOT, HERE / 'S01-public-probe/BEHAVIOR-SUMMARY.json'),
        _project_file(_PROJECT_ROOT, HERE / 'S01-CONTINUATION-CLOSED-SUMMARY.json'), _project_file(_PROJECT_ROOT, HERE / 'S01-OWN-TARGET-COST-READBACK.json'),
        parent_path / 'candidate.py', parent_path / 'generation.json']
    save('S02-AUTHOR-PREPARATION-CLOSED.json', {'complete': True, 'formal_parent': parent['identity']['candidate_id'],
        'S01_reference_only': first['identity']['candidate_id'], 'max_total_actual_author_calls': 2,
        'actual_author_calls_before_start': 1, 'automatic_retry': False,
        'prompt_bytes': prompt_bytes, 'prompt_sha256': result['prompt_sha256'],
        'frozen_files': {str(p): pin(p) for p in files}, 'public_mechanical_windows': 103,
        'partial_public_controls': 11, 'second_prompt_size_bound_bytes': 300000,
        'reasoning_effort': 'provider default, not sent by adapter',
        'new_models_rules_scores_worlds_tables_in_preparation': 0,
        'natural_current_results_read': False})
    print({'prepared': True, 'prompt_bytes': prompt_bytes, 'max_total_actual_author_calls': 2,
           'natural_pilot_results_read': False}, flush=True)


if __name__ == '__main__':
    main()
