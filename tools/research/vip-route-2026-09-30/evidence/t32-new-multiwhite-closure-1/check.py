"""纯读多白条件批；先封原件，复用全链核验，再按四公开牌形分层。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t32-new-multiwhite-closure-1'

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
import importlib.util
import json

HERE = Path(__file__).resolve().parent
SOURCE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t32-new-multiwhite-source-preparation-1')
BASE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t13-joint-route-quality-author-1/focused-closure-1/check.py')


def read(path):
    return json.loads(path.read_bytes())


def identity(path):
    h, size = hashlib.sha256(), 0
    with path.open('rb') as stream:
        while block := stream.read(1024*1024):
            h.update(block)
            size += len(block)
    return {'bytes': size, 'sha256': h.hexdigest()}


def put(name, value):
    with (_project_file(_PROJECT_ROOT, HERE/name)).open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    """候选只获可见输入；人工题净分不混入自然频率或确认分母。"""
    plan, end = read(_project_file(_PROJECT_ROOT, SOURCE/'PREPARED.json')), read(_project_file(_PROJECT_ROOT, SOURCE/'COSTS-AND-RESULT.json'))
    assert plan['planned_continuation_instances'] == 80 and plan['planned_mother_roots'] == 8
    assert end['status'] == 'diagnostic_batch_closed_not_strength_confirmation'
    files = {str(p.resolve()): identity(p) for p in sorted(SOURCE.rglob('*'))
             if p.is_file() and '__pycache__' not in p.parts}
    put('RAW-FIRST-SEAL.json', {'files': files, 'file_count': len(files),
        'bytes': sum(r['bytes'] for r in files.values()), 'actual_cli_exit_code': 0,
        'before_effect_analysis': True, 'preview': 'terminal completion only', 'business_calls': 0})
    spec = importlib.util.spec_from_file_location('t32_reused_pure_chain', BASE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    verified = module.check(SOURCE)
    conditions = read(_project_file(_PROJECT_ROOT, SOURCE/'SOURCE-CONDITIONS.json'))
    original = {p['root_id']: p for p in conditions['proposals']}
    templates = read(_project_file(_PROJECT_ROOT, SOURCE/'CONTROL-TEMPLATES.json'))
    assert {p['root_id'] for p in templates['proposals']} == set(original)
    for proposal in templates['proposals']:
        assert all(proposal[k] == original[proposal['root_id']][k]
                   for k in ('full_physical_deck', 'deck_sha256', 'qualification', 'profile'))
    rows, failed, target_calls = [], [], {}
    for line in (_project_file(_PROJECT_ROOT, SOURCE/'calls-and-choices.jsonl')).open():
        call = json.loads(line)
        if call['event'] == 'score_call' and call['kind'] == 'C':
            target_calls.setdefault((call['root_id'], call['variant'], call['arm']), []).append(call)
    for ordinal, root in enumerate(plan['roots'], 1):
        condition = original[root['root_id']]
        result = read(_project_file(_PROJECT_ROOT, SOURCE/f'root-{ordinal:02d}/ROOT-RESULT.json'))
        if result['status'] == 'qualification_failed_original_slots_retained':
            failed.append({'root_id': root['root_id'], 'shape': condition['shape'],
                'opponent_condition': condition['opponent_condition'], 'original_result': result})
            continue
        assert result['status'] == 'complete'
        for variant in plan['variant_order']:
            directory = _project_file(_PROJECT_ROOT, SOURCE/f'root-{ordinal:02d}'/variant)
            outcomes = {a: read(directory/(a+'-outcome.json')) for a in plan['arm_order']}
            first_calls = {arm: target_calls[root['root_id'], variant, arm][0] for arm in ('Sol-C', 'S02-C')}
            assert first_calls['Sol-C']['input_capture']['view_sha256'] == first_calls['S02-C']['input_capture']['view_sha256']
            for arm in ('A', 'Sol-C', 'S02-C'):
                assert 'force_count' not in outcomes[arm]
            if condition['qualification']['current_legal_hu']:
                assert {e['action_key']: e['score'] for e in first_calls['Sol-C']['scores']['entries']} == {
                    e['action_key']: e['score'] for e in first_calls['S02-C']['scores']['entries']}
            scores = {a: o['focal_net_score'] for a, o in outcomes.items()}
            rows.append({'root_id': root['root_id'], 'shape': condition['shape'],
                'opponent_condition': condition['opponent_condition'], 'variant': variant,
                'teacher_near_ready_scope': 'original qualified only; hidden variant unknown',
                'first_actions': {a: o['first_action_key'] for a, o in outcomes.items()},
                'focal_net_scores': scores, 'settlements': {a: o['settlement'] for a, o in outcomes.items()},
                'child_C_minus_parent_C': scores['Sol-C']-scores['S02-C'],
                'child_C_minus_R18_A': scores['Sol-C']-scores['A'],
                'child_first_B_minus_parent_first_B': scores['Sol-B']-scores['S02-B'],
                'child_followup_C_minus_own_B': scores['Sol-C']-scores['Sol-B'],
                'parent_followup_C_minus_own_B': scores['S02-C']-scores['S02-B']})
    assert len(rows)*5 == end['completed_arms']
    assert len(failed)*10 == end['missing_or_failed_arms']
    for path, expected in files.items():
        assert identity(Path(path)) == expected
    put('ROOT-CLOSED-CHECK.json', {**verified, 'schema': 't32-new-physical-multiwhite-closure/1',
        'raw_seal_sha256': identity(_project_file(_PROJECT_ROOT, HERE/'RAW-FIRST-SEAL.json'))['sha256'],
        'original_conditions_not_replaced': True, 'shape_families': 4,
        'current_Hu_parent_child_first_score_maps_protected': True,
        'business_calls': 0, 'new_reviews': 0, 'new_authors': 0, 'not_admitted': True})
    put('CONDITIONAL-BEHAVIOR.json', {'schema': 't32-four-shape-condition-development/1',
        'rows': rows, 'qualification_failures': failed, 'planned_physical_roots': 8,
        'public_shape_families': 4, 'late_wall_coverage': False,
        'opponent_control_pairs_not_eight_distinct_public_shapes': True,
        'not_natural_prevalence_or_confirmation': True, 'business_calls': 0})
    print(json.dumps({'status': verified['status'], 'completed': end['completed_arms'],
        'qualification_failed_slots': end['missing_or_failed_arms'], 'C_calls': verified['C_score_calls'],
        'R18_calls': verified['R18_score_calls'], 'full_inputs': verified['unique_actual_full_inputs'],
        'normal_fallbacks': verified['normal_C_r18_fallbacks']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
