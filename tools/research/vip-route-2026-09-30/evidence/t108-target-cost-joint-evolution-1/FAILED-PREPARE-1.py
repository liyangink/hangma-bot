"""冻结新联合批的公开反馈、真实父分值与新来源；不评分或生成牌墙。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t108-target-cost-joint-evolution-1'

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
import importlib.util
import json
from pathlib import Path

from hangma_bot.offline.qualifier_opponents import freeze_qualifier_compositions
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents, run_vip_eoh_generate

HERE = Path(__file__).resolve().parent
E = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')
PARENT = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t101-joint-breadth-recovery-author-1')
T105 = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t105-confirmation-opportunity-diagnosis-1')


def canonical(value):
    """规范有限JSON；不同完整输入不能仅凭观察近似而复用分值。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def pin(path):
    """对实际只读字节封条，不读取凭据或隐藏牌墙。"""
    raw = Path(path).read_bytes()
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def save(name, value):
    """材料只新建，原失败及原成绩不覆盖。"""
    with (_project_file(_PROJECT_ROOT, HERE / name)).open('xb') as stream:
        stream.write(canonical(value) + b'\n')


def archive(path):
    """读取已核完整公开评分视图，不调用业务评分。"""
    result = {}
    with gzip.open(path, 'rt') as stream:
        for line in stream:
            row = json.loads(line)
            assert hashlib.sha256(canonical(row['view'])).hexdigest() == row['view_sha256']
            result[row['view_sha256']] = row['view']
    return result


def main():
    """新批至多两个作者；98开发窗口和32开发／128确认母源先冻结。"""
    for name in ('t103-joint-breadth-fresh-confirmation-1',
                 't106-first-width-and-hu-credit-1', 't107-four-white-wait-credit-1'):
        assert json.loads((_project_file(_PROJECT_ROOT, E / name / 'ROOT-READBACK.json')).read_text())['complete']
    raw = json.loads((_project_file(_PROJECT_ROOT, PARENT / 'S02-generation.batch.json')).read_text())
    api_bound = json.loads((_project_file(_PROJECT_ROOT, E / 't9-joint-author-execution-preparation-1/author-three-slot.batch.json')).read_text())['input_bound']
    raw['batch_id'] = 'vip-t108-target-cost-joint-two-slot-20261003'
    raw['input_bound'] = api_bound
    raw['budgets'].update(model_calls=2, input_tokens=2097152, output_tokens=131072,
                          wall_clock_seconds=5400)
    save('AUTHOR-BATCH.json', raw)
    batch_file = _project_file(_PROJECT_ROOT, HERE / 'AUTHOR-BATCH.json')
    batch = VipEohBatch.read(batch_file)
    parent = load_vip_parents([_project_file(_PROJECT_ROOT, PARENT / 'S02-model-output')], batch)[0]
    assert parent['identity']['candidate_id'] == '10cba94704291038653f586127be1809ef518dcaf68fa1fe38d1fc9ab92ca18f'
    save('PARENT-IDENTITY.json', {'formal_parent': parent['identity'],
         'path': str(_project_file(_PROJECT_ROOT, PARENT / 'S02-model-output')), 'admitted': False,
         'old_results_transferred': False})

    spec = importlib.util.spec_from_file_location('t101_readonly_public_cases', _project_file(_PROJECT_ROOT, PARENT / 'accept_and_probe.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    old, old_inputs = module.cases()
    old_actual = {r['label']: r for r in json.loads((_project_file(_PROJECT_ROOT, PARENT / 'PUBLIC-PROBE-CLOSURE.json')).read_text())['rows']}
    cases = []
    for row in old:
        actual = old_actual[row['label']]
        assert actual['status'] == 'complete' and actual['view_sha256'] == row['view_sha256']
        cases.append(dict(row, parent_scores=actual['child_scores']['entries'],
                          parent_first=actual['child_first']))
    targets = json.loads((_project_file(_PROJECT_ROOT, T105 / 'PUBLIC-TARGETS.json')).read_text())
    additions = [r for r in targets['targets'] if r['arm'] == 'C' and r['window_key']['trigger_seq'] == 1074]
    additions.extend(r for r in targets['four_white_targets'] if r['window_key']['trigger_seq'] in (761, 785, 266))
    assert len(additions) == 4
    for row in additions:
        cases.append({'label': 'T105:' + str(row['window_key']['trigger_seq']),
             'observation': row['observation'], 'window_key': row['window_key'],
             'view_sha256': row['view_sha256'], 'parent_scores': row['original_full_scores'],
             'parent_first': row['original_first'], 'scope': 'exposed development; no action gold label'})
    fork = json.loads((_project_file(_PROJECT_ROOT, T105 / 'FIRST-FORK-READBACK.json')).read_text())
    original = fork['C_actual_public_record']
    cases.append({'label': 'T105:954', 'observation': original['observation'],
         'window_key': original['window_key'], 'view_sha256': fork['C_view_sha256'],
         'parent_scores': [{'action_key': r['action_key'], 'score': r['score'], 'trace': r['trace']}
                           for r in original['candidates']],
         'parent_first': original['selected_action_key'], 'scope': 'exposed causal development; no universal gold label'})
    assert len(cases) == len({r['label'] for r in cases}) == 98
    views = archive(_project_file(_PROJECT_ROOT, PARENT / 'PUBLIC-PROBE-VIEWS.jsonl.gz'))
    views.update(archive(_project_file(_PROJECT_ROOT, T105 / 'ORIGINAL-C-VIEWS.jsonl.gz')))
    views.update(archive(_project_file(_PROJECT_ROOT, T105 / 'FORK-ORIGINAL-C-VIEW.json.gz')))
    for row in cases:
        view = views[row['view_sha256']]
        assert {a['action_key'] for a in view['actions']} == {r['action_key'] for r in row['parent_scores']}
    save('PUBLIC-PANEL.json', {'schema': 't108-exposed-public-panel/1', 'cases': cases,
         'actual_parent_score_calls': 0, 'parent_scores': 'T101 verified actual full-input records',
         'hidden_worlds_included': False, 'confirmation': False})
    with gzip.open(_project_file(_PROJECT_ROOT, HERE / 'PUBLIC-PANEL-VIEWS.jsonl.gz'), 'xb') as stream:
        for digest in sorted({r['view_sha256'] for r in cases}):
            stream.write(canonical({'view_sha256': digest, 'view': views[digest]}) + b'\n')

    # 只检查已有START、COMPOSITIONS及作者前保留清单，不生成未来牌墙。
    prior_paths = sorted(set(E.glob('t*/block-*/START.json'))
                         | set(E.glob('t*/COMPOSITIONS*.json'))
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
    for path in prior_paths:
        collect(json.loads(path.read_text()))
    pools = {}
    for pool, size in (('fresh_development', 32), ('reserved_confirmation', 128)):
        roots = []
        for index in range(1, size + 1):
            root = f't108-target-cost-joint:{pool}:{index:03d}'
            seed = int.from_bytes(hashlib.sha256((root + ':20261003:unseen').encode()).digest()[:8], 'big') % 2**63
            roots.append({'root_id': root, 'seed': seed})
        pools[pool] = roots
    fresh_seeds = {r['seed'] for rows in pools.values() for r in rows}
    assert len(fresh_seeds) == 160 and not fresh_seeds.intersection(prior_seeds)
    save('EXPOSURE-AND-SEED-CHECK.json', {'scope': 'bounded t* START/compositions/reservations; not exhaustive world history',
         'files': {str(p): pin(p) for p in prior_paths}, 'prior_seeds': len(prior_seeds),
         'new_distinct_seeds': 160, 'collision': False, 'new_worlds': 0})
    save('FRESH-ROOTS-BEFORE-AUTHOR.json', dict(pools, schema='t108-prereservation/1',
         author_read_forbidden=True, worlds_generated=0, rounds=8, initial_scores=[0, 0, 0, 0],
         rotations=[[0,1,2,3], [1,2,3,0], [2,3,0,1], [3,0,1,2]],
         main_weak_fraction_setting=0.6, official_score_multiplier=1))
    compositions = {pool: freeze_qualifier_compositions(roots, 0.6) for pool, roots in pools.items()}
    save('COMPOSITIONS.json', {'pools': compositions, 'worlds_generated': 0,
         'composition_or_result_selection': False, 'author_read_forbidden': True})
    save('EVOLUTION-PLAN.json', {'schema': 't108-two-joint-author-plan/1',
         'created_at_utc': datetime.now(timezone.utc).isoformat(), 'max_author_proposals': 2,
         'S01': {'operator': 'm1', 'model': 'glm-5.3', 'formal_parent': parent['identity']['candidate_id']},
         'S02': 'reserved; adaptation from S01 evidence permitted, same predeclared sources',
         'family': 'natural-composition joint formula; no new family',
         'active_formulas': ['T101 parent', 'T75 archived-risk reference', 'at most S01 and S02'],
         'historical_parent_registry_is_not_active_population': True,
         'public_behavior_panel': {'windows': 98, 'causal_cases_not_mechanical_gold': True,
                                  'rules_or_score_failure_rejects': True},
         'development': {'roots': 32, 'rotations': 4, 'rounds': 8,
             'reference': 'registered R18 and true parent T101 on same roots',
             'max_child_formulas': 2, 'max_actual_tables_including_parent_and_repeated_R18': 768,
             'duplicate_R18_tables_charge_but_not_independent': True,
             'start_after_complete_public_score_and_causal_reproduction': True,
             'confirmation_start_screen': {'whole_engineering_valid': True,
                 'mean_delta_vs_R18_positive': True, 'mean_delta_vs_T101_positive': True,
                 'highfan_income_net_positive': True, 'positive_highfan_roots_at_least': 2}},
         'confirmation': {'roots': 128, 'rotations': 4, 'rounds': 8,
             'max_candidates': 1, 'actual_tables': 1024,
             'start_only_after_development_screen': True,
             'selection': 'largest development mean net gain among eligible children; no confirmation peeking',
             'required': ['root-cluster lower95 net delta >0', 'cross-source highfan net increment',
                          'rules, real deadlines and official release gates separately']},
         'progress_stop_or_fault_checks_only_until_each_closed_batch': True,
         'ordinary_loss_allowed_if_actual_highfan_net_covers': True,
         'normal_C_R18_fallback_allowed': False, 'official_multiplier': 1,
         'publication': False, 'old_T103_sources_now_development': True,
         'real_deadline_passed': False})

    chosen = ['T105:954', 'T105:1074', 'T105:761', 'T105:785', 'T105:266',
              'T94:1757', 'T94:1875', 'T96:1815', 'T100:pair-03']
    selected = [{'label': r['label'], 'observation': r['observation'],
                 'window_key': r['window_key'], 'T101_first': r['parent_first'],
                 'T101_scores': r['parent_scores'], 'complete_public_view': views[r['view_sha256']]}
                for label in chosen for r in cases if r['label'] == label]
    assert len(selected) == 9
    save('SELECTED-PUBLIC-FEEDBACK.json', {'source': 'exposed development focal lawful observation/DTO only',
         'selected_post_outcome': True, 'targets_not_optimal_action_gold': True, 'cases': selected})
    brief = (_project_file(_PROJECT_ROOT, HERE / 'S01-FEEDBACK-PREFIX.txt')).read_text()
    feedback = brief + '\n以下九个已曝光公开完整输入是开发材料，不含其他座位暗牌或未来牌墙：\n' + canonical(selected).decode()
    (_project_file(_PROJECT_ROOT, HERE / 'S01-FROZEN-FEEDBACK.txt')).write_text(feedback)
    emission = run_vip_eoh_generate(batch_file=batch_file, out_dir=_project_file(_PROJECT_ROOT, HERE / 'S01-prompt-emission'),
         operator='m1', parent_paths=[_project_file(_PROJECT_ROOT, PARENT / 'S02-model-output')], feedback=feedback)
    assert emission['status'] == 'prompt_emitted' and emission['identity_stable']
    owned = ['prepare.py', 'AUTHOR-BATCH.json', 'PARENT-IDENTITY.json', 'PUBLIC-PANEL.json',
             'PUBLIC-PANEL-VIEWS.jsonl.gz', 'EXPOSURE-AND-SEED-CHECK.json',
             'FRESH-ROOTS-BEFORE-AUTHOR.json', 'COMPOSITIONS.json', 'EVOLUTION-PLAN.json',
             'SELECTED-PUBLIC-FEEDBACK.json', 'S01-FEEDBACK-PREFIX.txt', 'S01-FROZEN-FEEDBACK.txt']
    sources = [_project_file(_PROJECT_ROOT, PARENT / 'S02-model-output/generation.json'), _project_file(_PROJECT_ROOT, PARENT / 'S02-model-output/candidate.py'),
               _project_file(_PROJECT_ROOT, PARENT / 'PUBLIC-PROBE-CLOSURE.json'), _project_file(_PROJECT_ROOT, PARENT / 'PUBLIC-PROBE-VIEWS.jsonl.gz'),
               _project_file(_PROJECT_ROOT, T105 / 'PUBLIC-TARGETS.json'), _project_file(_PROJECT_ROOT, T105 / 'FIRST-FORK-READBACK.json'),
               _project_file(_PROJECT_ROOT, T105 / 'ORIGINAL-C-VIEWS.jsonl.gz'), _project_file(_PROJECT_ROOT, T105 / 'FORK-ORIGINAL-C-VIEW.json.gz'),
               *old_inputs, _project_file(_PROJECT_ROOT, E / 't103-joint-breadth-fresh-confirmation-1/ROOT-READBACK.json'),
               _project_file(_PROJECT_ROOT, E / 't106-first-width-and-hu-credit-1/ROOT-READBACK.json'),
               _project_file(_PROJECT_ROOT, E / 't107-four-white-wait-credit-1/ROOT-READBACK.json')]
    save('AUTHOR-PREPARATION-CLOSED.json', {'complete': True,
         'stage': 'before_real_model_call', 'new_models_rules_scores_worlds_tables': 0,
         'formal_parent': parent['identity']['candidate_id'], 'public_windows': 98,
         'prompt_sha256': emission['prompt_sha256'], 'prompt_bytes': (_project_file(_PROJECT_ROOT, HERE / 'S01-prompt-emission/prompt.txt')).stat().st_size,
         'model': 'glm-5.3', 'output_limit': 65536,
         'reasoning_effort': 'not sent by existing API backend; provider default, do not claim max',
         'frozen_files': {str(p): pin(p) for p in [*[_project_file(_PROJECT_ROOT, HERE / n) for n in owned], *sources]}})
    print({'prepared': True, 'public_windows': 98, 'fresh_sources': 160,
           'prompt_bytes': (_project_file(_PROJECT_ROOT, HERE / 'S01-prompt-emission/prompt.txt')).stat().st_size,
           'real_model_calls': 0})


if __name__ == '__main__':
    main()
