"""八个作者前冻结新开发母根的纯文件准备，不生成牌山、不开始桌赛。

公式与四个分块的完整分母在开桌前固定；只消费pilot，128确认根仍留出。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t77-net-upgrade-fresh-qualifier-pilot-1'

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
AUTHOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t75-net-upgrade-joint-author-1')
CAUSAL = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t76-joint-child-causal-preparation-1')
FIRST = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t75-net-upgrade-joint-author-1')
ENGINEERING = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t49-qualifier-opponent-behavior-1')


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def save(name, value):
    with (_project_file(_PROJECT_ROOT, HERE / name)).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    pointer = json.loads((_project_file(_PROJECT_ROOT, AUTHOR / 'CURRENT-CANDIDATE-PACKAGE.json')).read_text())
    complete = json.loads((_project_file(_PROJECT_ROOT, AUTHOR / pointer['probe_closure'])).read_text())
    assert complete['complete_all_windows'] and complete['candidate_identity'] == pointer['candidate_identity']
    assert complete['changed_windows'] and complete['parent_identity']['candidate_id'] == 'b3f133b8c6beb32d248a19d567808387d0af57d47f2c3f43103a04258034bef2'
    for folder, name in ((AUTHOR, 'ROOT-READBACK.json'), (CAUSAL, 'ROOT-READBACK.json')):
        seal = json.loads((folder / name).read_text())
        assert seal['complete']
        for relative, digest in seal['files'].items():
            path = folder / relative
            assert path.stat().st_size == digest['bytes'] and sha(path) == digest['sha256'], relative
    composition_file = (_project_file(_PROJECT_ROOT, FIRST / 'COMPOSITIONS-BEFORE-AUTHOR.json')).resolve()
    root_file = _project_file(_PROJECT_ROOT, FIRST / 'FRESH-ROOTS-BEFORE-AUTHOR.json')
    compositions = json.loads(composition_file.read_text())
    roots = json.loads(root_file.read_text())['pilot']
    selected = compositions['pilot']['0.6']
    assert len(roots) == len(selected) == len({r['root_id'] for r in selected}) == len({r['seed'] for r in selected}) == 8
    assert [(r['root_id'], r['seed']) for r in roots] == [(r['root_id'], r['seed']) for r in selected]
    assert all(r['permutations'] == [[0, 1, 2, 3], [1, 2, 3, 0], [2, 3, 0, 1], [3, 0, 1, 2]] for r in roots)
    assert all(r['weak_fraction_setting'] == 0.6 for r in selected)
    old_compositions = json.loads((_project_file(_PROJECT_ROOT, ENGINEERING / 'COMPOSITIONS-BEFORE-TABLES.json')).read_text())
    old_seeds = {r['seed'] for group in ('pilot', 'reserved_confirmation') for r in old_compositions[group]['0.6']}
    assert not old_seeds.intersection(r['seed'] for r in selected)
    prerequisites = [_project_file(_PROJECT_ROOT, AUTHOR / 'CURRENT-CANDIDATE-PACKAGE.json'), _project_file(_PROJECT_ROOT, AUTHOR / pointer['relative_batch']),
        _project_file(_PROJECT_ROOT, AUTHOR / pointer['relative_package'] / 'generation.json'), _project_file(_PROJECT_ROOT, AUTHOR / pointer['relative_package'] / 'candidate.py'),
        _project_file(_PROJECT_ROOT, AUTHOR / pointer['probe_closure']), _project_file(_PROJECT_ROOT, AUTHOR / 'ROOT-READBACK.json'), _project_file(_PROJECT_ROOT, CAUSAL / 'ROOT-READBACK.json'),
        _project_file(_PROJECT_ROOT, CAUSAL / 'CLOSURE.json'), _project_file(_PROJECT_ROOT, ENGINEERING / 'smoke-1/summary.json'), _project_file(_PROJECT_ROOT, ENGINEERING / 'PILOT-ROOT-CLOSE-AUDIT.json'),
        composition_file, root_file, Path(__file__), _project_file(_PROJECT_ROOT, HERE / 'pilot_block.py'), _project_file(_PROJECT_ROOT, HERE / 'close_campaign.py')]
    pins = {str(path.resolve()): sha(path) for path in prerequisites}
    plan = {'schema': 't77-second-joint-fresh-development-plan/1',
        'created_at_utc': datetime.now(timezone.utc).isoformat(), 'candidate_identity': pointer['candidate_identity'],
        'candidate_held_fixed_until_all_blocks_closed': True, 'source_kind': 'simulation',
        'main_weak_fraction_setting': 0.6, 'human_majority_weak_prior_accepted': True,
        'actual_weak_opponent_slots': sum(r['actual_weak_count'] for r in selected), 'total_logical_opponent_slots': 24,
        'root_ids': [r['root_id'] for r in selected], 'independent_roots': 8, 'rotations_per_root': 4, 'rounds': 8,
        'paired_tables': 32, 'planned_actual_tables': 64, 'planned_hands': 512, 'planned_hands_per_arm': 256,
        'blocks': 4, 'roots_per_block': 2, 'compositions_file': str(composition_file),
        'prerequisite_sha256': pins, 'primary': 'actual net complete-table score C minus registered R18, clustered by mother root',
        'confidence': {'method': 'exploratory root bootstrap percentile', 'resamples': 20000, 'seed': 2026100277, 'interval': 0.95},
        'secondary': ['own_lt4', 'own_4_to7', 'own_8_to15', 'own_ge16', 'opponent_hu', 'draw',
                      'actual component net differences', 'highfan source clusters', 'dealer/nondealer', 'runtime faults'],
        'official_settlement_multiplier': 1, 'ordinary_loss_allowed_if_real_cumulative_highfan_net_covers': True,
        'inspection': 'progress/cost/fault only until all four processes terminal; no outcome-driven source append or tuning',
        'failure': 'engineering/capture/source/incomplete fault stops new groups globally; preserve full64 table denominator and costs',
        'stage': 'eight fresh development mother roots; does not earn confirmation or admission',
        'normal_C_r18_fallback_allowed': False, 'offline_max_operations': 4800000,
        'online_budget_or_deadline_relaxed': False, 'published': False,
        'reserved_confirmation_roots_not_consumed': 128, 'sensitivity_fractions_not_started': [0.5, 0.75],
        'strong_opponent_each_nonnegative_not_qualifier_hard_gate': True,
        'seed_history': 'original T75 preauthor freeze, withheld from author; none generated before this START',
        'new_model_score_world_table_calls_in_preparation': 0}
    save('CAMPAIGN-PLAN.json', plan)
    for block in range(1, 5):
        save('BLOCK-' + format(block, '02d') + '-PLAN.json', {
            'schema': 't77-fresh-development-block-plan/1', 'block': block,
            'root_ids': [r['root_id'] for r in selected[(block - 1) * 2:block * 2]],
            'compositions_file': str(composition_file), 'prerequisite_sha256': pins,
            'planned_actual_tables': 16, 'planned_roots': 2, 'paired_tables': 8,
            'planned_hands_per_arm': 64, 'rounds': 8, 'main_weak_fraction': 0.6,
            'primary_metric': plan['primary'], 'wall_clock_limit_seconds': 7200, 'step_limit': 10000,
            'scoring_input_capture': {'max_view_json_bytes': 33554432,
                                      'max_total_json_bytes': 17179869184, 'max_unique_views': 100000},
            'scope': 'all64 tables development; no block earns confirmation', 'stop_rule': plan['failure'],
            'online_budget_or_deadline_relaxed': False, 'published': False, 'offline_candidate_max_operations': 4800000})
    print({'prepared': True, 'fresh_mother_roots': 8, 'planned_actual_tables': 64,
           'actual_weak_slots': plan['actual_weak_opponent_slots'], 'new_worlds_tables': 0})


if __name__ == '__main__':
    main()
