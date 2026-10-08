"""冻结目标自身代价联合批；复用公开实际记录，不评分或生成牌墙。"""

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
from datetime import datetime, timezone
import ast
import gzip
import hashlib
import json
from pathlib import Path

from hangma_bot.offline.qualifier_opponents import freeze_qualifier_compositions
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents, run_vip_eoh_generate

HERE = Path(__file__).resolve().parent
E = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')
PREVIOUS = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t108-target-cost-joint-evolution-1')
PARENT = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t101-joint-breadth-recovery-author-1/S02-model-output')


def canonical(value):
    """规范有限JSON；完整输入摘要只用于精确复用，不代表状态相似。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def pin(path):
    """绑定只读实际字节，不读取认证配置或未来牌墙。"""
    raw = Path(path).read_bytes()
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def save(name, value):
    """只创建本批新材料，旧失败和成绩保持原样。"""
    with (_project_file(_PROJECT_ROOT, HERE / name)).open('xb') as stream:
        stream.write(canonical(value) + b'\n')


def archive(path):
    """读取已记录的本座公开完整DTO，保持空值、未知及版本字段。"""
    result = {}
    with gzip.open(path, 'rt') as stream:
        for row in map(json.loads, stream):
            digest = hashlib.sha256(canonical(row['view'])).hexdigest()
            assert digest == row['view_sha256']
            if digest in result:
                assert result[digest] == row['view']
            result[digest] = row['view']
    return result


def main():
    """先冻结两作者上限、103公开窗、16开发和128确认母源，再发作者提示。"""
    campaign = _project_file(_PROJECT_ROOT, PREVIOUS / 'S02-natural-development-1')
    closure = json.loads((campaign / 'CAMPAIGN-CLOSURE.json').read_text())
    terminal = json.loads((campaign / 'ACTUAL-READBACK-TERMINAL.json').read_text())
    assert closure['whole_batch_valid'] and terminal['exit_code'] == 0
    assert not closure['predeclared_confirmation_start_screen_passed']
    prior_probe = json.loads((_project_file(_PROJECT_ROOT, PREVIOUS / 'S02-public-probe/ROOT-READBACK.json')).read_text())
    assert prior_probe['complete'] and prior_probe['windows'] == 100
    raw = json.loads((_project_file(_PROJECT_ROOT, E / 't101-joint-breadth-recovery-author-1/S02-generation.batch.json')).read_text())
    raw['batch_id'] = 'vip-t109-target-specific-joint-two-slot-20261003'
    raw['budgets'].update(model_calls=2, input_tokens=2097152, output_tokens=131072,
                          wall_clock_seconds=5400)
    # 委派模型的底层输入上限未独立验证，不移植GLM供应商的限额证明。
    raw['input_bound'] = None
    save('AUTHOR-BATCH.json', raw)
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / 'AUTHOR-BATCH.json'))
    parent = load_vip_parents([PARENT], batch)[0]
    assert parent['identity']['candidate_id'] == '10cba94704291038653f586127be1809ef518dcaf68fa1fe38d1fc9ab92ca18f'
    save('PARENT-IDENTITY.json', {'formal_parent': parent['identity'], 'path': str(PARENT),
         'admitted': False, 'old_results_transferred': False,
         'S02_reference_only': str(_project_file(_PROJECT_ROOT, PREVIOUS / 'S02-model-output'))})

    panel = json.loads((_project_file(_PROJECT_ROOT, PREVIOUS / 'S02-PUBLIC-PANEL.json')).read_text())
    assert len(panel['cases']) == 100
    public_first = json.loads((_project_file(_PROJECT_ROOT, PREVIOUS / 'S02-PUBLIC-FIRST-CASES.json')).read_text())
    assert len(public_first['cases']) == 3
    for case in public_first['cases']:
        assert case['public_prefix_equal'] and case['not_optimal_action_gold']
        p = case['arms']['P']
        panel['cases'].append({'label': case['label'], 'observation': case['observation'],
            'window_key': case['window_key'], 'view_sha256': p['view_sha256'],
            'parent_first': p['first_action'], 'parent_scores': [
                {'action_key': r['action_key'], 'score': r['score'], 'trace': r['trace']}
                for r in p['actual_scores']],
            'scope': 'exposed fixed-0123 public first divergence; no optimal-action gold'})
    assert len(panel['cases']) == len({r['label'] for r in panel['cases']}) == 103
    panel.update(schema='t109-exposed-public-panel/1', confirmation=False,
                 scope='103 exposed development windows; no action gold labels')
    save('PUBLIC-PANEL.json', panel)
    views = archive(_project_file(_PROJECT_ROOT, PREVIOUS / 'S02-public-probe/VIEWS.jsonl.gz'))
    views.update(archive(_project_file(_PROJECT_ROOT, PREVIOUS / 'S02-PUBLIC-FIRST-CASE-VIEWS.jsonl.gz')))
    needed = {r['view_sha256'] for r in panel['cases']}
    assert needed == set(views)
    for case in panel['cases']:
        assert {r['action_key'] for r in views[case['view_sha256']]['actions']} == {
            r['action_key'] for r in case['parent_scores']}
    with gzip.open(_project_file(_PROJECT_ROOT, HERE / 'PUBLIC-PANEL-VIEWS.jsonl.gz'), 'xb') as stream:
        for digest in sorted(needed):
            stream.write(canonical({'view_sha256': digest, 'view': views[digest]}) + b'\n')

    paths = sorted(set(E.glob('t*/**/START.json')) | set(E.glob('t*/COMPOSITIONS*.json'))
                   | set(E.glob('t*/FRESH-ROOTS-BEFORE-AUTHOR.json')))
    prior_seeds = set()
    def collect(value):
        if isinstance(value, dict):
            if type(value.get('seed')) is int:
                prior_seeds.add(value['seed'])
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)
    for path in paths:
        collect(json.loads(path.read_text()))
    pools = {}
    for pool, size in (('fresh_development', 16), ('reserved_confirmation', 128)):
        pools[pool] = []
        for index in range(1, size + 1):
            root = f't109-target-specific-joint:{pool}:{index:03d}'
            seed = int.from_bytes(hashlib.sha256((root + ':20261003:unseen').encode()).digest()[:8], 'big') % 2**63
            pools[pool].append({'root_id': root, 'seed': seed})
    new_seeds = {r['seed'] for roots in pools.values() for r in roots}
    assert len(new_seeds) == 144 and not new_seeds.intersection(prior_seeds)
    save('EXPOSURE-AND-SEED-CHECK.json', {'scope': 'all bounded t* START/compositions/reservations, not exhaustive world history',
         'source_files': {str(p): pin(p) for p in paths}, 'prior_seeds': len(prior_seeds),
         'new_distinct_seeds': 144, 'collision': False, 'worlds_generated': 0})
    save('FRESH-ROOTS-BEFORE-AUTHOR.json', dict(pools, schema='t109-prereservation/1',
         author_read_forbidden=True, worlds_generated=0, rounds=8, initial_scores=[0, 0, 0, 0],
         rotations=[[0,1,2,3], [1,2,3,0], [2,3,0,1], [3,0,1,2]],
         main_weak_fraction_setting=0.6, official_score_multiplier=1))
    save('COMPOSITIONS.json', {'pools': {pool: freeze_qualifier_compositions(roots, 0.6)
         for pool, roots in pools.items()}, 'worlds_generated': 0,
         'composition_or_result_selection': False, 'author_read_forbidden': True})
    save('EVOLUTION-PLAN.json', {'schema': 't109-target-specific-joint-plan/1',
        'created_at_utc': datetime.now(timezone.utc).isoformat(), 'max_author_proposals': 2,
        'S01': {'operator': 'm1', 'requested_model': 'gpt-6.1-sol', 'requested_effort': 'max',
                'formal_parent': parent['identity']['candidate_id'], 'underlying_usage': None},
        'S02': 'reserved; GLM adaptation only after actual first candidate feedback; provider effort separately recorded',
        'family': 'natural-composition joint; no new family',
        'active_formulas': ['T101', 'T75 risk reference', 'at most S01 and S02'],
        'historical_packages_not_active_population': True,
        'mechanism': ['target own completion cost', 'bounded marginal backup support', 'condition-bound value'],
        'public_panel': {'windows': 103, 'case_actions_not_hard_gold': True,
                         'start_natural_only_if_valid_and_relevant_real_behavior_change': True},
        'development': {'roots': 16, 'rotations': 4, 'rounds': 8, 'max_children': 2,
            'max_actual_tables_including_parent_and_repeated_R18': 384,
            'sample_size_reason': 'small fixed screening after 118/128 unchanged policy pairs; independent 128-root confirmation retained',
            'reference': 'registered R18 and actual formal T101 parent on all same roots',
            'start_after_public_mechanical_and_focal_continuation_checks': True,
            'confirmation_start_screen': {'whole_engineering_valid': True,
                'mean_delta_vs_R18_positive': True, 'mean_delta_vs_T101_positive': True,
                'highfan_income_net_positive': True, 'positive_highfan_roots_at_least': 2}},
        'conditional': {'max_current_hand_continuations_first_slot': 24,
            'scope': 'existing exposed positive/negative first-action and current-Hu cases; all declared sources retained',
            'same_root_rotations_do_not_add_independent_sources': True},
        'confirmation': {'roots': 128, 'rotations': 4, 'rounds': 8, 'max_candidates': 1,
            'actual_tables': 1024, 'start_only_after_development_screen': True,
            'selection': 'highest development net among eligible children; no confirmation peeking',
            'required': ['root-cluster lower95 net delta >0', 'cross-source highfan increment',
                         'rules, real deadlines and official release gates separately']},
        'normal_C_R18_fallback_allowed': False, 'ordinary_loss_allowed_if_real_highfan_net_covers': True,
        'tournament_pressure': 'record only', 'exact_long_horizon_EV_required': False,
        'progress_fault_and_cost_only_until_whole_terminal': True,
        'published': False, 'real_deadline_passed': False})

    old_feedback = (_project_file(_PROJECT_ROOT, PREVIOUS / 'S02-FROZEN-FEEDBACK.txt')).read_text()
    marker = '{"new_public_cases":'
    assert marker in old_feedback
    earlier = json.loads(old_feedback[old_feedback.index(marker):])
    additions = []
    for case in public_first['cases']:
        p = case['arms']['P']
        additions.append({'label': case['label'], 'complete_public_view': views[p['view_sha256']],
            'T101_first': p['first_action'], 'T101_scores': p['actual_scores'],
            'S02_first': case['arms']['C']['first_action'], 'not_optimal_action_gold': True,
            'view_equal_and_public_prefix_equal': True})
    feedback_data = {'earlier_public_controls': earlier, 'all_three_new_public_first_cases': additions,
        'closed_whole_batch': {k: closure[k] for k in ('descriptive_comparisons', 'highfan_deltas',
                                                      'realized_mutually_exclusive_bands')},
        'no_teacher_world_future_wall_or_reserved_seeds': True}
    save('SELECTED-PUBLIC-FEEDBACK.json', feedback_data)
    feedback = (_project_file(_PROJECT_ROOT, HERE / 'FEEDBACK-PREFIX.txt')).read_text() + '\n' + canonical(feedback_data).decode()
    (_project_file(_PROJECT_ROOT, HERE / 'FROZEN-FEEDBACK.txt')).write_text(feedback)
    emitted = run_vip_eoh_generate(batch_file=_project_file(_PROJECT_ROOT, HERE / 'AUTHOR-BATCH.json'), out_dir=_project_file(_PROJECT_ROOT, HERE / 'S01-prompt-emission'),
        operator='m1', parent_paths=[PARENT], feedback=feedback)
    assert emitted['status'] == 'prompt_emitted' and emitted['identity_stable']
    for name in ('probe.py', 'read_probe.py'):
        text = (_project_file(_PROJECT_ROOT, PREVIOUS / name)).read_text().replace('98', '103').replace('t108', 't109')
        ast.parse(text)
        (_project_file(_PROJECT_ROOT, HERE / name)).write_text(text)
    sources = [_project_file(_PROJECT_ROOT, PREVIOUS / n) for n in ('S02-PUBLIC-PANEL.json', 'S02-PUBLIC-FIRST-CASES.json',
        'S02-PUBLIC-FIRST-CASE-VIEWS.jsonl.gz', 'S02-FROZEN-FEEDBACK.txt',
        'S02-public-probe/ROOT-READBACK.json', 'S02-public-probe/VIEWS.jsonl.gz',
        'S02-TARGET-COST-FINDING.md', 'S02-CLOSED-TARGET-COST-ALGEBRA.json',
        'S02-model-output/candidate.py', 'S02-model-output/generation.json',
        'S02-natural-development-1/CAMPAIGN-CLOSURE.json',
        'S02-natural-development-1/ACTUAL-READBACK-TERMINAL.json')]
    owned = [p for p in HERE.iterdir() if p.is_file()]
    sources.extend([_project_file(_PROJECT_ROOT, E.parent / 'T109-TARGET-SPECIFIC-METHOD-RECHECK.md'), _project_file(_PROJECT_ROOT, PARENT / 'candidate.py'),
                    _project_file(_PROJECT_ROOT, PARENT / 'generation.json')])
    save('AUTHOR-PREPARATION-CLOSED.json', {'complete': True, 'stage': 'before_real_author_delegation',
        'formal_parent': parent['identity']['candidate_id'], 'public_windows': 103,
        'unique_full_inputs': len(needed), 'prompt_sha256': emitted['prompt_sha256'],
        'prompt_bytes': (_project_file(_PROJECT_ROOT, HERE / 'S01-prompt-emission/prompt.txt')).stat().st_size,
        'requested_model': 'gpt-6.1-sol', 'requested_effort': 'max', 'underlying_usage': None,
        'new_models_rules_scores_worlds_tables': 0,
        'frozen_files': {str(p): pin(p) for p in [*owned, *sources]}})
    print({'prepared': True, 'public_windows': 103, 'distinct_full_inputs': len(needed),
           'prompt_bytes': (_project_file(_PROJECT_ROOT, HERE / 'S01-prompt-emission/prompt.txt')).stat().st_size,
           'author_delegations': 0, 'new_scores_worlds_tables': 0})


if __name__ == '__main__':
    main()
