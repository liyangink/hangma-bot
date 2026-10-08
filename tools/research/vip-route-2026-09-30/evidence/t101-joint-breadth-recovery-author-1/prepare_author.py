"""为本联合批第二提案冻结跨来源反思与合法公开输入，不评分或模拟。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t101-joint-breadth-recovery-author-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path

from hangma_bot.offline.vip_eoh_generate import (
    VipEohBatch, load_vip_parents, run_vip_eoh_generate,
)

HERE = Path(__file__).resolve().parent
PREVIOUS = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t97-natural-preparation-joint-root-1')
DIAGNOSTIC = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t100-joint-pilot-divergence-1')
PILOT = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t99-new-joint-fresh-pilot-1')


def canonical(value):
    """规范有限JSON；来源标签是研发标签，不是线上条件。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def pin(path):
    """冻结实际字节及长度，不读不必要教师世界。"""
    raw = path.read_bytes()
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def save(name, value):
    """只创建新材料；原作者、失败和成绩均不改写。"""
    with (_project_file(_PROJECT_ROOT, HERE / name)).open('xb') as f:
        f.write(canonical(value) + b'\n')


def main():
    """实际装载兼容T97父包，发出m1提示；作者和评分由后续阶段负责。"""
    diagnostic = json.loads((_project_file(_PROJECT_ROOT, DIAGNOSTIC / 'CLOSURE.json')).read_text())
    readback = json.loads((_project_file(_PROJECT_ROOT, DIAGNOSTIC / 'ROOT-READBACK.json')).read_text())
    assert diagnostic['complete'] and readback['complete']
    assert diagnostic['pairs'] == diagnostic['changed_trajectories'] == 32
    assert diagnostic['white_counts_at_first_divergence']['0'] == 19
    assert readback['exact_score_ties'] == 13
    closure = json.loads((_project_file(_PROJECT_ROOT, PILOT / 'CAMPAIGN-CLOSURE.json')).read_text())
    assert closure['whole_batch_valid'] and not closure['predeclared_confirmation_start_screen_passed']
    with gzip.open(_project_file(_PROJECT_ROOT, DIAGNOSTIC / 'PUBLIC-FIRST-DIVERGENCES.json.gz'), 'rt') as f:
        all_rows = json.load(f)['rows']
    all_pairs = json.loads((_project_file(_PROJECT_ROOT, DIAGNOSTIC / 'PAIR-READBACK.json')).read_text())['pairs']
    # 每来源至少一代表；另补普通出口负例。全部32对仍在摘要，不伪装盲选。
    chosen = ['pair-03', 'pair-07', 'pair-10', 'pair-16', 'pair-20',
              'pair-21', 'pair-23', 'pair-27', 'pair-29', 'pair-31']
    public = []
    owned = []
    for label in chosen:
        row = next(r for r in all_rows if r['label'] == label)
        name = label + '-VIEW.json.gz'
        with gzip.open(_project_file(_PROJECT_ROOT, HERE / name), 'xb') as f:
            f.write(canonical({'view_sha256': row['complete_view_sha256'],
                              'view': row['complete_view']}))
        owned.append(name)
        brief = {k: v for k, v in row.items() if k != 'complete_view'}
        brief['complete_view_file'] = name
        brief['public_observation'] = {k: v for k, v in brief['public_observation'].items()
                                        if k != 'public_history'}
        brief['public_history_omitted_in_brief'] = True
        public.append(brief)
    chosen_roots = {r['root_id'] for r in all_pairs if r['label'] in chosen}
    assert len(chosen_roots) == 8
    save('SELECTED-PUBLIC-CASES.json', {
        'schema': 't101-lawful-divergence-feedback/1', 'rows': public,
        'selection': 'post-outcome development representatives covering all8 roots; full32 paired labels retained',
        'online_inputs': 'own publicly permitted observation and complete scoring DTO only',
        'hidden_world_other_hands_or_future_wall_included': False,
        'causal_credit': False,
    })
    save('ALL32-PAIR-LABELS.json', {
        'scope': 'complete development continuations of two different policies; not action gold labels',
        'pairs': [{k: v for k, v in r.items()
                   if k not in ('new_match_id', 'old_match_id')} for r in all_pairs],
        'whole_pilot_comparisons': closure['descriptive_comparisons'],
        'realized_bands': closure['realized_mutually_exclusive_bands'],
        'first_divergence_summary': diagnostic,
        'exact_score_ties': 13,
    })
    raw = json.loads((_project_file(_PROJECT_ROOT, PREVIOUS / 'S01-generation.batch.json')).read_text())
    raw['batch_id'] = 'vip-t101-joint-breadth-recovery-m1-20261003'
    save('S02-generation.batch.json', raw)
    batch_file = _project_file(_PROJECT_ROOT, HERE / 'S02-generation.batch.json')
    batch = VipEohBatch.read(batch_file)
    parent_path = _project_file(_PROJECT_ROOT, PREVIOUS / 'S01-model-output')
    parent = load_vip_parents([parent_path], batch)[0]
    assert parent['identity'] == json.loads((_project_file(_PROJECT_ROOT, PILOT / 'CAMPAIGN-PLAN.json')).read_text())['formulas']['T97']
    save('PARENT-IDENTITY.json', {'operator': 'm1', 'formal_parent_paths': [str(parent_path)],
                                  'identity': parent['identity'], 'old_results_transferred': False,
                                  'parent_status': 'compatible experimental proposal, not admitted'})
    # 新开发来源在第二作者前登记。原128确认源保持不动、禁止作者读取。
    fresh = []
    for i in range(16):
        root = f't101-joint-breadth:fresh-pilot:{i+1:03d}'
        seed = int.from_bytes(hashlib.sha256((root + ':20261003:unseen').encode()).digest()[:8], 'big') % 2**63
        fresh.append({'root_id': root, 'seed': seed})
    assert len({r['seed'] for r in fresh}) == 16
    save('FRESH-ROOTS-BEFORE-AUTHOR.json', {'schema': 't101-reservation-not-start/1',
        'fresh_pilot': fresh, 'rotations': [[(s+t) % 4 for s in range(4)] for t in range(4)],
        'rounds': 8, 'worlds_generated': 0, 'author_read_forbidden': True,
        'reference': 'registered R18; old T97 contrast only if later explicitly frozen',
        'main_weak_fraction_setting': .6, 'official_score_multiplier': 1,
        'start_requires_frozen_candidate_mechanical_and_development_screen': True})
    feedback = (_project_file(_PROJECT_ROOT, HERE / 'FROZEN-FEEDBACK.txt')).read_text()
    emission = run_vip_eoh_generate(batch_file=batch_file, out_dir=_project_file(_PROJECT_ROOT, HERE / 'S02-prompt-emission'),
                                     operator='m1', parent_paths=(parent_path,), feedback=feedback)
    assert emission['status'] == 'prompt_emitted' and emission['identity_stable']
    names = ['prepare_author.py', 'FROZEN-FEEDBACK.txt', 'AUTHOR-TASK.txt',
             'SELECTED-PUBLIC-CASES.json', 'ALL32-PAIR-LABELS.json',
             'S02-generation.batch.json', 'PARENT-IDENTITY.json',
             'FRESH-ROOTS-BEFORE-AUTHOR.json', *owned]
    frozen = {str(_project_file(_PROJECT_ROOT, HERE / n)): pin(_project_file(_PROJECT_ROOT, HERE / n)) for n in names}
    for path in (_project_file(_PROJECT_ROOT, PREVIOUS / 'S01-model-output/candidate.py'), _project_file(_PROJECT_ROOT, PREVIOUS / 'S01-model-output/generation.json'),
                 _project_file(_PROJECT_ROOT, PREVIOUS / 'T75-REFERENCE-SOURCE.py'), _project_file(_PROJECT_ROOT, PREVIOUS / 'PUBLIC-CAUSAL-FEEDBACK.json'),
                 _project_file(_PROJECT_ROOT, PREVIOUS / 'PUBLIC-TARGET-VIEWS.jsonl.gz'), _project_file(_PROJECT_ROOT, DIAGNOSTIC / 'CLOSURE.json'),
                 _project_file(_PROJECT_ROOT, DIAGNOSTIC / 'ROOT-READBACK.json'), _project_file(_PROJECT_ROOT, PILOT / 'CAMPAIGN-CLOSURE.json')):
        frozen[str(path)] = pin(path)
    save('AUTHOR-PREPARATION-CLOSED.json', {'schema': 't101-second-joint-author-preparation/1',
        'proposal_number_in_T97_joint_batch': 2, 'max_proposals_in_joint_batch': 2,
        'operator': 'm1', 'formal_parents': [parent['identity']['candidate_id']],
        'requested_model': 'gpt-6.1-sol', 'requested_effort': 'max',
        'prompt_sha256': emission['prompt_sha256'], 'frozen_files': frozen,
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'new_models_scores_rules_worlds_tables': 0, 'reserved_confirmation_sources_used': False,
        'family': 'same natural composition family; no fourth family',
        'admitted': False, 'published': False, 'status': 'prepared_no_author'})
    print({'prepared': True, 'formal_parent': parent['identity']['candidate_id'],
           'actual_model_score_world_table_calls': 0, 'public_representatives': 10,
           'independent_development_roots': 8, 'fresh_roots_reserved': 16})


if __name__ == '__main__':
    main()
