"""冻结紧凑作者输入与完整验收范围；不调用规则、评分、模型或模拟。"""

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
import gzip
import hashlib
import json
from pathlib import Path

from hangma_bot.offline.qualifier_opponents import freeze_qualifier_compositions
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents, run_vip_eoh_generate

HERE = Path(__file__).resolve().parent
EVIDENCE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')
OLD = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t109-target-specific-joint-evolution-1')
PARENT = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t101-joint-breadth-recovery-author-1/S02-model-output')


def canonical(value):
    """保留未知和有限数值；用于精确字节绑定，不作状态相似度。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def pin(path):
    """绑定明确文件，排除运行日志、生成账本和私有认证配置。"""
    raw = Path(path).read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def save(name, value):
    """仅新建本批记录，不覆盖已关闭批次及失败分母。"""
    with (_project_file(_PROJECT_ROOT, HERE / name)).open('xb') as stream:
        stream.write(canonical(value) + b'\n')


def waiting_summary(waiting):
    """压缩一份真实等待事实；这是反馈摘要，不是完整候选DTO。"""
    target_fields = ('family', 'target_stage', 'retained_whites', 'white_used',
        'natural_need', 'target_natural_draw_lower_bound',
        'target_natural_discard_lower_bound', 'target_white_discard_lower_bound',
        'requires_terminal_draw', 'witness_status', 'conditional_need_improvement_codes')
    structure = waiting['structure']
    preparation = waiting['natural_preparation']
    payments = waiting['normal_draw_hu_payments']
    # 同码抓打假设仍逐条列出，保持互斥；积分向量座位顺序为0、1、2、3。
    payment_fields = ('draw_code', 'catch_restricted', 'draw_capacity_before',
        'baotou_after_draw', 'chain_count', 'chain_piao', 'score_delta_0_1_2_3', 'fan')
    payment_rows = None if payments is None else [[
        row['draw_code'], row['catch_restricted'], row['draw_capacity_before'],
        row['baotou_after_draw'], row['chain_count'], row['chain_piao'],
        row['settlement']['score_delta'], row['settlement']['fan']]
        for row in payments]
    return {'scope': 'partial actual waiting facts; other DTO fields omitted',
        'structure': {k: structure[k] for k in ('natural_counts33', 'whites_held',
            'meld_set_count', 'natural_pair_count', 'standard_shanten', 'seven_pairs_shanten')},
        'target_columns': target_fields,
        'targets': [[target[k] for k in target_fields] for target in structure['targets']],
        'natural_preparation': None if preparation is None else {k: preparation[k] for k in (
            'sets_left', 'natural_draw_lower_bound', 'natural_discard_lower_bound',
            'natural_need_improvement_codes')},
        'payment_columns': payment_fields, 'payments': payment_rows,
        'widths_and_qualification': {k: waiting[k] for k in (
            'useful_code_width', 'useful_codes', 'standard_useful_codes',
            'seven_pairs_useful_codes', 'combined_useful_codes',
            'target_improvement_code_widths', 'natural_preparation_code_width',
            'legal_hu_draw_codes', 'qualification_unknown_codes',
            'qualification_scope', 'qualification_missing_reason')},
        'unseen_capacities': waiting['unseen_capacities'],
        'unseen_evidence': waiting['unseen_evidence'], 'chain_count': waiting['chain_count']}


def main():
    """先冻结两作者、103原公开窗和144新母源；作者只收到紧凑公开反馈。"""
    prior = json.loads((_project_file(_PROJECT_ROOT, OLD / 'S02-ACTUAL-FAILURE-READBACK.json')).read_text())
    assert prior['complete'] and prior['error']['http_status'] == 500
    assert not prior['candidate_delivered'] and prior['actual_model_calls'] == 1
    raw = json.loads((_project_file(_PROJECT_ROOT, OLD / 'S02-API-BATCH.json')).read_text())
    raw['batch_id'] = 'vip-t110-compact-target-cost-joint-two-slot-20261003'
    raw['budgets'].update(model_calls=2, input_tokens=2097152, output_tokens=131072,
                          wall_clock_seconds=5400)
    save('AUTHOR-BATCH.json', raw)
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE / 'AUTHOR-BATCH.json'))
    parent = load_vip_parents([PARENT], batch)[0]
    assert parent['identity']['candidate_id'] == '10cba94704291038653f586127be1809ef518dcaf68fa1fe38d1fc9ab92ca18f'
    save('PARENT-IDENTITY.json', {'formal_parent': parent['identity'], 'path': str(PARENT),
        'admitted': False, 'old_results_transferred': False,
        'failed_source_reference_only': str(_project_file(_PROJECT_ROOT, OLD / 'S01-model-output'))})
    for name in ('PUBLIC-PANEL.json', 'PUBLIC-PANEL-VIEWS.jsonl.gz'):
        with (_project_file(_PROJECT_ROOT, HERE / name)).open('xb') as stream:
            stream.write((_project_file(_PROJECT_ROOT, OLD / name)).read_bytes())
    cases = json.loads((_project_file(_PROJECT_ROOT, HERE / 'PUBLIC-PANEL.json')).read_text())['cases']
    assert len(cases) == 103
    views = {}
    with gzip.open(_project_file(_PROJECT_ROOT, HERE / 'PUBLIC-PANEL-VIEWS.jsonl.gz'), 'rt') as stream:
        for row in map(json.loads, stream):
            assert hashlib.sha256(canonical(row['view'])).hexdigest() == row['view_sha256']
            views[row['view_sha256']] = row['view']
    assert len(views) == 97

    labels = ('T105:954', 'T94:1757', 'T96:1815', 'T105:1074', 'T105:761',
        'T108:root003-loss', 'T108:root030-gain', 'T108-S02-first:011',
        'T108-S02-first:012', 'T108-S02-first:027', 'old:public:20')
    compact = []
    previous_feedback = json.loads((_project_file(_PROJECT_ROOT, OLD / 'SELECTED-PUBLIC-FEEDBACK.json')).read_text())
    alternatives = {'T105:954': 'discard:2w', 'T108:root003-loss': 'discard:发',
                    'T108:root030-gain': 'discard:4t', 'T108-S02-first:027': 'pass'}
    for label in labels:
        case = next(case for case in cases if case['label'] == label)
        view = views[case['view_sha256']]
        by_key = {node['node_key']: node for node in view['nodes']}
        selected = []
        for action in view['actions']:
            if action['action_key'] in (case['parent_first'], alternatives.get(label)):
                node = by_key[action['node_key']]
                if node['waiting'] is not None and node not in selected:
                    selected.append(node)
        for node in view['nodes']:
            if node['waiting'] is not None and node not in selected and len(selected) < 3:
                selected.append(node)
        assert len(selected) <= 3
        compact.append({'label': label, 'view_sha256': case['view_sha256'],
            'scope': 'partial public DTO summary; at most three waiting nodes, remaining nodes omitted',
            'visible_state': view['visible_state'], 'tile_order': view['tile_order'],
            'legal_root_actions': view['actions'], 'workload': view['workload'],
            'T101_actual_scores': case['parent_scores'], 'T101_first': case['parent_first'],
            'current_settlements': [{'node_key': n['node_key'], 'settlement': n['settlement']}
                for n in view['nodes'] if n['settlement'] is not None],
            'waiting_samples': [{'node_key': n['node_key'], 'kind': n['kind'],
                'waiting': waiting_summary(n['waiting'])} for n in selected],
            'action_gold': False})

    failed = json.loads((_project_file(_PROJECT_ROOT, OLD / 'S01-public-probe/FAILED-MECHANICAL-READBACK.json')).read_text())
    algebra = json.loads((_project_file(_PROJECT_ROOT, OLD / 'S01-OWN-TARGET-COST-ALGEBRA.json')).read_text())
    feedback = {'public_cases': compact,
        'current_hand_observed': [{k: row[k] for k in ('label', 'current_hand_observed', 'not_optimal_action_gold')}
            for row in previous_feedback['earlier_public_controls']['new_public_cases']],
        'T108_complete_32_source_scores': previous_feedback['closed_whole_batch'],
        'T109_S01_failure': {k: failed[k] for k in ('actual_tool_terminal', 'failed_attempts', 'failures')},
        'target_cost_component': {k: algebra[k] for k in ('scope', 'counts', 'examples')},
        'failed_Sol_source_reference_not_formal_parent': (_project_file(_PROJECT_ROOT, OLD / 'S01-model-output/candidate.py')).read_text(),
        'no_hidden_hands_future_walls_teacher_paths_or_reserved_seeds': True}
    save('COMPACT-PUBLIC-FEEDBACK.json', feedback)
    prefix = (_project_file(_PROJECT_ROOT, HERE / 'FEEDBACK-PREFIX.txt')).read_text()
    text = prefix + '\n' + canonical(feedback).decode()
    with (_project_file(_PROJECT_ROOT, HERE / 'FROZEN-FEEDBACK.txt')).open('x') as stream:
        stream.write(text)

    # 只登记种子和对手组成，不生成完整世界。作者不能读取这两份文件。
    paths = sorted(set(EVIDENCE.glob('t*/**/START.json')) |
        set(EVIDENCE.glob('t*/COMPOSITIONS*.json')) |
        set(EVIDENCE.glob('t*/FRESH-ROOTS-BEFORE-AUTHOR.json')))
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
            root = f't110-compact-target-cost:{pool}:{index:03d}'
            seed = int.from_bytes(hashlib.sha256((root + ':20261003:unseen').encode()).digest()[:8], 'big') % 2**63
            pools[pool].append({'root_id': root, 'seed': seed})
    seeds = {row['seed'] for rows in pools.values() for row in rows}
    assert len(seeds) == 144 and not seeds.intersection(prior_seeds)
    save('FRESH-ROOTS-BEFORE-AUTHOR.json', dict(pools, author_read_forbidden=True,
        worlds_generated=0, rounds=8, initial_scores=[0, 0, 0, 0],
        rotations=[[0,1,2,3], [1,2,3,0], [2,3,0,1], [3,0,1,2]],
        main_weak_fraction_setting=0.6, official_score_multiplier=1))
    save('COMPOSITIONS.json', {'pools': {pool: freeze_qualifier_compositions(roots, 0.6)
        for pool, roots in pools.items()}, 'worlds_generated': 0, 'author_read_forbidden': True})
    save('EXPOSURE-AND-SEED-CHECK.json', {'scope': 'bounded t* START/composition/reservation files, not exhaustive history',
        'prior_seed_count': len(prior_seeds), 'new_seed_count': len(seeds), 'collision': False,
        'old_T109_unused_roots_not_reused': True, 'source_files': {str(p): pin(p) for p in paths}})
    plan = json.loads((_project_file(_PROJECT_ROOT, OLD / 'EVOLUTION-PLAN.json')).read_text())
    plan.update(schema='t110-compact-target-cost-plan/1',
        S01={'operator': 'm1', 'model': 'glm-5.3', 'reasoning_effort': 'provider default, no max claim',
             'formal_parent': parent['identity']['candidate_id']},
        S02='reserved after actual first-candidate feedback; at most two actual author calls',
        mechanism=['target own cost with compact streaming computation',
                   'marginal support without repeated per-target object construction',
                   'condition-bound payment jointly with ordinary exit'],
        active_formulas=['T101', 'T75 risk reference', 'at most T110 S01 and S02'],
        previous_failed_batch=str(OLD), old_results_transferred=False)
    save('EVOLUTION-PLAN.json', plan)
    for name in ('probe.py', 'read_probe.py', 'read_failed_probe.py', 'read_behavior.py',
                 'prepare_continuations.py'):
        source = (_project_file(_PROJECT_ROOT, OLD / name)).read_text().replace('AUTHOR-PREPARATION-CLOSED-REVISION-2.json',
            'AUTHOR-PREPARATION-CLOSED.json').replace('t109', 't110')
        ast.parse(source)
        with (_project_file(_PROJECT_ROOT, HERE / name)).open('x') as stream:
            stream.write(source)
    # 完整契约、父源码及字段附录仍由正式生成器提供，不改模型或执行协议。
    emitted = run_vip_eoh_generate(batch_file=_project_file(_PROJECT_ROOT, HERE / 'AUTHOR-BATCH.json'),
        out_dir=_project_file(_PROJECT_ROOT, HERE / 'S01-prompt-emission'), operator='m1', parent_paths=[PARENT], feedback=text)
    assert emitted['status'] == 'prompt_emitted' and emitted['identity_stable']
    prompt_bytes = (_project_file(_PROJECT_ROOT, HERE / 'S01-prompt-emission/prompt.txt')).stat().st_size
    assert prompt_bytes <= 240000, '先修准备范围，再调用；不能静默丢案例'
    files = [p for p in HERE.iterdir() if p.is_file() and not p.name.endswith(('.log', '.lock'))
             and 'vip-eoh-ledger' not in p.name]
    inputs = [_project_file(_PROJECT_ROOT, OLD / name) for name in ('S02-ACTUAL-FAILURE-READBACK.json',
        'S01-public-probe/FAILED-MECHANICAL-READBACK.json', 'S01-OWN-TARGET-COST-ALGEBRA.json',
        'S01-model-output/candidate.py', 'SELECTED-PUBLIC-FEEDBACK.json')]
    inputs += [_project_file(_PROJECT_ROOT, PARENT / 'candidate.py'), _project_file(_PROJECT_ROOT, PARENT / 'generation.json')]
    save('AUTHOR-PREPARATION-CLOSED.json', {'complete': True, 'before_actual_API_call': True,
        'formal_parent': parent['identity']['candidate_id'], 'frozen_files': {str(p): pin(p) for p in files+inputs},
        'prompt_bytes': prompt_bytes, 'prompt_sha256': emitted['prompt_sha256'],
        'public_mechanical_windows': 103, 'unique_full_mechanical_DTOs': 97,
        'partial_author_feedback_cases': len(compact), 'new_models_rules_scores_worlds_tables': 0,
        'max_actual_author_calls': 2, 'automatic_retry': False})
    print({'prepared': True, 'prompt_bytes': prompt_bytes,
           'public_mechanical_windows': 103, 'partial_author_feedback_cases': len(compact)}, flush=True)


if __name__ == '__main__':
    main()
