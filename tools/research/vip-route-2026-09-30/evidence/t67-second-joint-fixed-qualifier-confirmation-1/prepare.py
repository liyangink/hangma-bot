"""固定第二公式，用原T59作者前128留出来源做完整长批；纯文件准备。

开发只有一母源的小增益，不授确认；扩大以真实自然收益检验追大取舍。
不按开发终分选确认牌山，不改对手，不给实际结算乘数。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t67-second-joint-fixed-qualifier-confirmation-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

HERE = Path(__file__).resolve().parent
E = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')
AUTHOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t62-earned-highfan-joint-revision-preparation-1')
PILOT = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t64-second-joint-fresh-qualifier-pilot-1')
PARENT = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t65-older-parent-common-qualifier-diagnosis-1')
FIRST = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t59-qualifier-highfan-credit-author-1')
ENGINEERING = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t49-qualifier-opponent-behavior-1')


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def save(name, value):
    with (_project_file(_PROJECT_ROOT, HERE / name)).open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    pointer = json.loads((_project_file(_PROJECT_ROOT, AUTHOR / 'CURRENT-CANDIDATE-PACKAGE.json')).read_text())
    probe = json.loads((_project_file(_PROJECT_ROOT, AUTHOR / pointer['probe_closure'])).read_text())
    assert probe['complete_all_windows'] and probe['candidate_identity'] == pointer['candidate_identity']
    for folder in (AUTHOR, PILOT, PARENT):
        seal = json.loads((folder / 'ROOT-READBACK.json').read_text())
        assert seal['complete']
        for name, digest in seal['files'].items():
            path = folder / name
            assert path.stat().st_size == digest['bytes'] and sha(path) == digest['sha256'], name
    comparison = json.loads((_project_file(_PROJECT_ROOT, PARENT / 'COMMON-PARENT-CHILD-COMPARISON.json')).read_text())
    assert comparison['complete'] and comparison['repeated_A_full_public_tails_exact'] == 32
    assert comparison['child_minus_old_parent_mean'] == 0.625
    composition_file = _project_file(_PROJECT_ROOT, FIRST / 'COMPOSITIONS-BEFORE-AUTHOR.json')
    root_file = _project_file(_PROJECT_ROOT, FIRST / 'FRESH-ROOTS-BEFORE-AUTHOR.json')
    selected = json.loads(composition_file.read_text())['reserved_confirmation']['0.6']
    roots = json.loads(root_file.read_text())['reserved_confirmation']
    assert len(selected) == len(roots) == len({r['seed'] for r in selected}) == len({r['root_id'] for r in selected}) == 128
    assert [(r['root_id'], r['seed']) for r in selected] == [(r['root_id'], r['seed']) for r in roots]
    assert all(r['permutations'] == [[0,1,2,3],[1,2,3,0],[2,3,0,1],[3,0,1,2]] for r in roots)
    assert all(r['weak_fraction_setting'] == 0.6 for r in selected)
    old = json.loads((_project_file(_PROJECT_ROOT, ENGINEERING / 'COMPOSITIONS-BEFORE-TABLES.json')).read_text())
    old_seeds = {r['seed'] for g in ('pilot', 'reserved_confirmation') for r in old[g]['0.6']}
    pilot = json.loads(composition_file.read_text())['pilot']['0.6']
    assert not {r['seed'] for r in selected}.intersection(old_seeds | {r['seed'] for r in pilot})
    prerequisites = [_project_file(_PROJECT_ROOT, AUTHOR / 'CURRENT-CANDIDATE-PACKAGE.json'), _project_file(_PROJECT_ROOT, AUTHOR / pointer['relative_batch']),
        _project_file(_PROJECT_ROOT, AUTHOR / pointer['relative_package'] / 'generation.json'), _project_file(_PROJECT_ROOT, AUTHOR / pointer['relative_package'] / 'candidate.py'),
        _project_file(_PROJECT_ROOT, AUTHOR / pointer['probe_closure']), _project_file(_PROJECT_ROOT, AUTHOR / 'ROOT-READBACK.json'),
        _project_file(_PROJECT_ROOT, PILOT / 'CAMPAIGN-CLOSURE.json'), _project_file(_PROJECT_ROOT, PILOT / 'ROOT-READBACK.json'), _project_file(_PROJECT_ROOT, PARENT / 'CAMPAIGN-CLOSURE.json'),
        _project_file(_PROJECT_ROOT, PARENT / 'ROOT-READBACK.json'), _project_file(_PROJECT_ROOT, PARENT / 'COMMON-PARENT-CHILD-COMPARISON.json'), composition_file, root_file,
        _project_file(_PROJECT_ROOT, ENGINEERING / 'smoke-1/summary.json'), _project_file(_PROJECT_ROOT, ENGINEERING / 'PILOT-ROOT-CLOSE-AUDIT.json'),
        Path(__file__), _project_file(_PROJECT_ROOT, HERE / 'confirm_block.py'), _project_file(_PROJECT_ROOT, HERE / 'close_campaign.py'), _project_file(_PROJECT_ROOT, HERE / 'root_readback.py')]
    pins = {str(p.resolve()): sha(p) for p in prerequisites}
    plan = {'schema': 't67-second-joint-fixed-qualifier-confirmation-plan/1',
        'created_at_utc': datetime.now(timezone.utc).isoformat(), 'candidate_identity': pointer['candidate_identity'],
        'candidate_held_fixed_until_all_blocks_closed': True, 'source_kind': 'simulation',
        'main_weak_fraction_setting': 0.6, 'human_majority_weak_prior_accepted': True,
        'actual_weak_opponent_slots': sum(r['actual_weak_count'] for r in selected), 'total_logical_opponent_slots': 384,
        'root_ids': [r['root_id'] for r in selected], 'independent_roots': 128, 'rotations_per_root': 4, 'rounds': 8,
        'paired_tables': 512, 'planned_actual_tables': 1024, 'planned_hands': 8192, 'planned_hands_per_arm': 4096,
        'blocks': 4, 'roots_per_block': 32, 'compositions_file': str(composition_file.resolve()),
        'prerequisite_sha256': pins, 'primary': 'actual net complete-table score C minus registered R18, clustered by mother root',
        'confidence': {'method': 'root bootstrap percentile', 'resamples': 20000, 'seed': 2026100267, 'interval': 0.95},
        'secondary': ['own_lt4','own_4_to7','own_8_to15','own_ge16','opponent_hu','draw',
            'mutually-exclusive real component net differences','highfan root clusters','dealer/nondealer','runtime faults'],
        'ordinary_loss_allowed_if_real_cumulative_highfan_net_covers': True, 'official_settlement_multiplier': 1,
        'development_basis': 'T64 -0.75 vs R18, interval crosses0; T65 +0.625 vs old parent from one natural fan2-to4 gain20. Limited lead, not stable strength; fixed larger test under uncertainty.',
        'inspection': 'progress/cost/fault only until all4 processes terminal; no outcome-driven root append or tuning',
        'failure': 'engineering/capture/source/incomplete fault stops new groups globally; preserve full1024 denominator and all costs',
        'normal_C_r18_fallback_allowed': False, 'offline_max_operations': 4800000,
        'online_budget_or_deadline_relaxed': False, 'published': False,
        'sensitivity_fractions_not_started': [0.5,0.75], 'strong_opponent_each_nonnegative_not_qualifier_hard_gate': True,
        'seed_history': 'original T59 preauthor128 reserve; not handed to either author or generated before this START',
        'new_models_scores_worlds_tables_in_preparation': 0}
    save('CAMPAIGN-PLAN.json', plan)
    for block in range(1,5):
        save('BLOCK-' + format(block,'02d') + '-PLAN.json', {
            'schema':'t67-fixed-confirmation-block-plan/1','block':block,
            'root_ids':[r['root_id'] for r in selected[(block-1)*32:block*32]],
            'compositions_file':str(composition_file.resolve()),'prerequisite_sha256':pins,
            'planned_actual_tables':256,'planned_roots':32,'paired_tables':128,'planned_hands_per_arm':1024,
            'rounds':8,'main_weak_fraction':0.6,'primary_metric':plan['primary'],
            'wall_clock_limit_seconds':14400,'step_limit':10000,
            'scoring_input_capture':{'max_view_json_bytes':33554432,'max_total_json_bytes':17179869184,'max_unique_views':100000},
            'scope':'fixed128 still-unexposed confirmation mother roots; no block wins admission',
            'stop_rule':plan['failure'],'online_budget_or_deadline_relaxed':False,'published':False,
            'offline_candidate_max_operations':4800000})
    print({'prepared':True,'unexposed_roots':128,'planned_actual_tables':1024,
        'actual_weak_slots':plan['actual_weak_opponent_slots'],'total_slots':384,'new_worlds_tables':0})


if __name__ == '__main__':
    main()
