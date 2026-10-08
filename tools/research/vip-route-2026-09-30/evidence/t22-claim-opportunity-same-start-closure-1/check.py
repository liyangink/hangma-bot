"""纯读T22吃碰机会80臂，核真父同输入、首选执行和结算；不重执行业务。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t22-claim-opportunity-same-start-closure-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import hashlib
import importlib.util
import json
from pathlib import Path
from collections import Counter

HERE = Path(__file__).resolve().parent
E = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')
SOURCE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t22-claim-opportunity-same-start-1')
BASE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t13-joint-route-quality-author-1/focused-closure-1/check.py')
MECHANICS = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t22-same-input-mechanics-2')


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, value):
    with (_project_file(_PROJECT_ROOT, HERE/name)).open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    """全部原件先固定，复用已有图/分母/结算检查，再核自然而非强制C。"""
    plan = read(_project_file(_PROJECT_ROOT, SOURCE/'PREPARED.json'))
    result = read(_project_file(_PROJECT_ROOT, SOURCE/'COSTS-AND-RESULT.json'))
    assert plan['planned_mother_roots'] == result['planned_mother_roots'] == 4
    assert plan['planned_continuation_instances'] == result['completed_arms'] == 80
    files = {str(p.resolve()): {'bytes':p.stat().st_size,'sha256':sha(p)}
             for p in SOURCE.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    write('RAW-FIRST-SEAL.json', {'schema':'t22-early-strict-choice-abc-raw-seal/1',
        'files':files, 'file_count':len(files), 'bytes':sum(v['bytes'] for v in files.values()),
        'before_final_closed_check':True, 'root_effect_preview_before_this_root_seal':False,
        'preview_scope':'only CLI terminal status/completion observed before raw seal; effect inspection follows seal',
        'actual_cli_exit_code':0,'business_calls':0})
    spec = importlib.util.spec_from_file_location('t22_same_tool_pure_checker', BASE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    base = module.check(SOURCE)
    source_scores={r['source']['source_C_full_DTO_sha256']:r['source']['source_C_cached_scores'] for r in plan['roots']}
    assert len(source_scores)==8 and all('hu' not in values for values in source_scores.values())
    parent,child={},{}
    for line in (_project_file(_PROJECT_ROOT, MECHANICS/'SCORES.jsonl')).open():
        row=json.loads(line)
        if row['status']=='scored' and row['view_sha256'] in source_scores:
            key=row['view_sha256']
            if key in parent:
                assert parent[key]==row['cached_parent_scores'] and child[key]==row['scores']
            parent[key]=row['cached_parent_scores'];child[key]=row['scores']
    assert set(parent)==set(child)==set(source_scores) and parent==source_scores
    targets, recovery, paths = {}, Counter(), {}
    for line in (_project_file(_PROJECT_ROOT, SOURCE/'calls-and-choices.jsonl')).open():
        row = json.loads(line)
        key = (row['root_id'], row.get('variant'), row.get('arm'))
        if row['event'] == 'recovery_advance':
            recovery[row['status']] += 1
        if row['event'] == 'advance' and row['status'] == 'advanced':
            paths.setdefault(key, []).append(row['choices'])
        if row['event'] == 'score_call' and row['kind'] == 'C':
            root = next(r for r in plan['roots'] if r['root_id'] == row['root_id'])
            if row['window_key'] == root['source']['target_window']:
                assert key not in targets
                targets[key] = row
                s = root['source']['source_C_full_DTO_sha256']
                assert row['input_capture']['view_sha256'] == s
                expected = child[s] if row['arm'] == 'Sol-C' else parent[s]
                assert {e['action_key']:e['score'] for e in row['scores']['entries']} == expected
    assert len(targets) == 32
    assert result['actual_calls']['target_preflight_projection_calls']==8
    assert result['actual_calls']['target_preflight_candidate_view_reads']==8
    for ordinal,root in enumerate(plan['roots'],1):
        rec=read(_project_file(_PROJECT_ROOT, SOURCE/f'root-{ordinal:02d}'/'TARGET-INPUT-PREFLIGHT.json'))
        assert rec['status']=='exact_actual_DTO_reconstructed_before_any_continuation'
        assert rec['view_sha256']==root['source']['source_C_full_DTO_sha256']
        assert rec['json_bytes']==root['source']['source_C_input_json_bytes'] and rec['score_calls']==0
    expected_advances = sum(len(r['source']['prefix']) + len(r['source']['current_prefix']) for r in plan['roots'])
    assert recovery == {'dispatch':expected_advances, 'advanced':expected_advances}
    rows = []
    for ordinal, root in enumerate(plan['roots'], 1):
        restored = read(_project_file(_PROJECT_ROOT, SOURCE/f'root-{ordinal:02d}'/'RECOVERY-RESULT.json'))
        assert restored['status'] == 'recovered_actual_C_single_hand_start'
        assert restored['all_seat_complete_observation_legal_set_and_window_checked']
        for variant in plan['variant_order']:
            directory = _project_file(_PROJECT_ROOT, SOURCE/f'root-{ordinal:02d}'/variant)
            outcomes = {a:read(directory/(a+'-outcome.json')) for a in plan['arm_order']}
            for arm in ('A','Sol-C','S02-C'):
                assert 'force_count' not in outcomes[arm], 'normal arm was forced'
            first = {a:o['first_action_key'] for a,o in outcomes.items()}
            for name in ('Sol','S02'):
                assert outcomes[name+'-B']['force_count'] == 1
                assert first[name+'-C'] == first[name+'-B']
            for arm in ('Sol-C','S02-C'):
                values = {e['action_key']:e['score'] for e in targets[(root['root_id'],variant,arm)]['scores']['entries']}
                assert first[arm] == sorted(values, key=lambda k:(-values[k], k))[0]
                assert targets[(root['root_id'],plan['variant_order'][0],arm)]['scores']['entries'] == targets[(root['root_id'],variant,arm)]['scores']['entries']
            vals = {a:o['focal_net_score'] for a,o in outcomes.items()}
            rows.append({'mother_root':root['mother_root'],'profile':root['profile'],
                'target_window':root['source']['target_window'],'variant':variant,
                'first_action_keys':first,'focal_single_hand_scores':vals,
                'child_minus_true_parent':vals['Sol-C']-vals['S02-C'],
                'child_minus_R18':vals['Sol-C']-vals['A'],
                'child_followup_minus_R18_same_child_first':vals['Sol-C']-vals['Sol-B'],
                'child_entry_B_minus_R18':vals['Sol-B']-vals['A'],
                'parent_entry_B_minus_R18':vals['S02-B']-vals['A'],
                'parent_followup_C_minus_B':vals['S02-C']-vals['S02-B'],
                'settlements':{a:o['settlement'] for a,o in outcomes.items()},
                'known_development_source_not_fresh_confirmation':True})
    for path, expected in files.items():
        assert sha(Path(path)) == expected['sha256'] and Path(path).stat().st_size == expected['bytes']
    receipt = {**base,'schema':'t22-root-claim-opportunity-causal-closure/1','planned_mother_roots':4,'qualified_mother_roots':4,'qualified_source_windows':8,
        'raw_seal_sha256':sha(_project_file(_PROJECT_ROOT, HERE/'RAW-FIRST-SEAL.json')),'base_checker_sha256':sha(BASE),
        'target_actual_complete_DTO_verified':32,'child_target_same_mechanical_actual_scores_verified':16,
        'true_T19_parent_cached_scores_verified':16,'verified_recovery_advances':expected_advances,
        'all_normal_A_C_unforced':True,'only_B_first_action_forced_once':True,
        'opponent_near_completion_scope':'unknown_in_both_original_and_public_hidden_worlds',
        'business_calls':0,'new_author_calls':0,'new_independent_reviews':0,'admitted':False}
    write('ROOT-CLOSED-CHECK.json', receipt)
    write('DEVELOPMENT-BEHAVIOR.json', {'schema':'t22-early-strict-choice-causal-development/1',
        'status':'closed_known_early_strict_sources_not_strength_confirmation',
        'source_windows':8,'independent_mother_roots':4,'upgrade_roots':0,'worlds':16,'arms':80,'rows':rows,
        'repeated_variants_and_pools_not_independent':True,'control_is_zero_white_only':False,
        'late_wall_positive_white_current_Hu_coverage':False,'all_sources_initial_no_Hu':True,'strict_sources':4,'tie_sources':4,'zero_white_sources':6,'one_white_sources':2})
    print(json.dumps({k:receipt[k] for k in ('status','C_score_calls','R18_score_calls',
        'unique_actual_full_inputs','normal_C_r18_fallbacks','verified_recovery_advances')},ensure_ascii=False))
    print(json.dumps([{k:r[k] for k in ('mother_root','profile','variant','child_minus_true_parent',
        'child_minus_R18','child_followup_minus_R18_same_child_first')} for r in rows],ensure_ascii=False))


if __name__ == '__main__':
    main()
