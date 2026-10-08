"""在任何世界执行前冻结128新根、固定公式、全分母和查看规则。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t52-fixed-qualifier-unexposed-long-1'

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
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
AUTHOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t51-t48-same-formula-efficiency-author-1')
ENGINEERING = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t49-qualifier-opponent-behavior-1')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, value):
    with (_project_file(_PROJECT_ROOT, HERE / name)).open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    pointer = json.loads((_project_file(_PROJECT_ROOT, AUTHOR / 'CURRENT-RESEARCH-CANDIDATE-PACKAGE.json')).read_text())
    closure = json.loads((_project_file(_PROJECT_ROOT, AUTHOR / pointer['probe_closure'])).read_text())
    assert closure['complete_all_windows'] and closure['candidate_identity'] == pointer['candidate_identity']
    assert json.loads((_project_file(_PROJECT_ROOT, AUTHOR / 'RECOVERY-NATURAL-EQUIVALENCE-CLOSURE.json')).read_text())['complete']
    assert json.loads((_project_file(_PROJECT_ROOT, ENGINEERING / 'PILOT-ROOT-CLOSE-AUDIT.json')).read_text())['complete']
    composition_file = (_project_file(_PROJECT_ROOT, ENGINEERING / 'COMPOSITIONS-BEFORE-TABLES.json')).resolve()
    compositions = json.loads(composition_file.read_text())
    roots = compositions['reserved_confirmation']['0.6']
    assert len(roots) == len({r['root_id'] for r in roots}) == len({r['seed'] for r in roots}) == 128
    pilot_ids = {r['root_id'] for r in compositions['pilot']['0.6']}
    assert not pilot_ids.intersection(r['root_id'] for r in roots)
    prerequisites = [_project_file(_PROJECT_ROOT, AUTHOR / 'CURRENT-RESEARCH-CANDIDATE-PACKAGE.json'),
                     _project_file(_PROJECT_ROOT, AUTHOR / pointer['relative_batch']), _project_file(_PROJECT_ROOT, AUTHOR / pointer['relative_package'] / 'generation.json'),
                     _project_file(_PROJECT_ROOT, AUTHOR / pointer['relative_package'] / 'candidate.py'), _project_file(_PROJECT_ROOT, AUTHOR / pointer['probe_closure']),
                     _project_file(_PROJECT_ROOT, AUTHOR / 'RECOVERY-NATURAL-EQUIVALENCE-CLOSURE.json'),
                     _project_file(_PROJECT_ROOT, ENGINEERING / 'PILOT-ROOT-CLOSE-AUDIT.json'), composition_file,
                     Path(compositions['root_file']), _project_file(_PROJECT_ROOT, HERE / 'confirm_block.py'), _project_file(_PROJECT_ROOT, HERE / 'close_campaign.py')]
    pins = {str(path.resolve()): sha(path) for path in prerequisites}
    campaign = {
        'schema': 't52-fixed-qualifier-long-prereg/1', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'source_kind': 'simulation', 'candidate_identity': pointer['candidate_identity'],
        'candidate_held_fixed_until_all_blocks_closed': True,
        'main_weak_fraction_setting': 0.6, 'actual_weak_opponent_slots': sum(r['actual_weak_count'] for r in roots),
        'total_logical_opponent_slots': 384,
        'root_ids': [r['root_id'] for r in roots], 'independent_roots': 128,
        'rotations_per_root': 4, 'rounds': 8, 'paired_tables': 512,
        'planned_actual_tables': 1024, 'planned_hands': 8192, 'planned_hands_per_arm': 4096,
        'blocks': 4, 'roots_per_block': 32, 'compositions_file': str(composition_file),
        'prerequisite_sha256': pins,
        'primary': 'mean actual net table score C minus R18; 128 independent root clusters, four seats averaged within root',
        'confidence': {'method': 'root bootstrap percentile', 'resamples': 20000, 'seed': 2026100252,
                       'interval': 0.95, 'research_superiority_signal': 'full batch valid and lower endpoint > 0'},
        'secondary': ['own_lt4', 'own_4_to7', 'own_8_to15', 'own_ge16', 'opponent_hu', 'draw',
                      'all actual net components', 'root clusters with highfan', 'dealer/nondealer', 'runtime counters'],
        'official_settlement_multiplier': 1,
        'ordinary_efficiency_loss_allowed_if_actual_total_supports_highfan_tradeoff': True,
        'inspection': 'progress/cost/fault only during run; no outcome-driven early stop, tuning or favorable-source append',
        'failure': 'any engineering/capture/source/incomplete failure cancels whole1024-table primary; stop new groups globally, preserve all costs and denominator',
        'strength_scope': '60% weak qualifier scenario; not real leaderboard, top-three probability or full tournament admission',
        'published': False, 'online_budget_or_deadline_relaxed': False,
        'offline_max_operations': 4800000,
        'budget_note': 'same optimized source; 2400000 normal probe22 and192 natural equivalent; offline4800000 only provides research headroom',
        'sensitivity_fractions_not_started': [0.5, 0.75],
        'H_M': 'strong-opponent diagnostic later, not separate each-nonnegative qualifier hard gate',
        'confirmation_root_history': 'roots/compositions frozen before original author; no worlds or tables started before this campaign',
        'new_model_calls_in_campaign': 0, 'new_worlds_tables_before_freeze': 0,
    }
    save('CAMPAIGN-PLAN.json', campaign)
    for block in range(1, 5):
        plan = {
            'schema': 't52-fixed-qualifier-long-block-plan/1', 'block': block,
            'root_ids': [r['root_id'] for r in roots[(block - 1) * 32:block * 32]],
            'compositions_file': str(composition_file), 'prerequisite_sha256': pins,
            'planned_actual_tables': 256, 'planned_roots': 32, 'paired_tables': 128,
            'planned_hands_per_arm': 1024, 'rounds': 8, 'main_weak_fraction': 0.6,
            'primary_metric': campaign['primary'], 'wall_clock_limit_seconds': 21600,
            'step_limit': 10000,
            'scoring_input_capture': {'max_view_json_bytes': 33554432,
                                      'max_total_json_bytes': 17179869184, 'max_unique_views': 100000},
            'promotion_scope': 'whole128root offline research only; no block earns standalone confirmation',
            'stop_rule': campaign['failure'], 'online_budget_or_deadline_relaxed': False,
            'published': False, 'offline_candidate_max_operations': 4800000,
        }
        save('BLOCK-' + format(block, '02d') + '-PLAN.json', plan)
    print({'prepared_roots': 128, 'planned_actual_tables': 1024, 'weak_slots': campaign['actual_weak_opponent_slots'],
           'new_worlds_tables': 0}, flush=True)


if __name__ == '__main__':
    main()
