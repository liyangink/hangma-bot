"""工程闭合后冻结128新母牌山和四块1024桌；纯准备，无新世界或评分。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t93-fixed-formula-fresh-natural-confirmation-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import platform
import shutil
import sys

from hangma_bot.hangma._standard import backend_info
from hangma_bot.offline.qualifier_opponents import freeze_qualifier_compositions
from hangma_bot.offline.scoring_sources import REPO_ROOT, source_manifest, write_code_snapshot
from hangma_bot.offline.vip_eoh_generate import VipEohBatch

HERE = Path(__file__).resolve().parent
E = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')
AUTHOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t75-net-upgrade-joint-author-1')
ENGINEERING = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t92-fixed-formula-natural-engineering-1')
SOURCE_ROOTS = ('hangma_bot.offline.qualifier_opponents', 'hangma_bot.offline.evaluate',
    'hangma_bot.offline.vip_route_development', 'hangma_bot.offline.vip_evaluation',
    'hangma_bot.offline.scoring_input_capture')


def sha(path):
    """流式摘要，冻结文件字节而非仅冻结文件名。"""
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def save(name, value):
    """事前计划只新建；实际运行件由每个隔离分块拥有。"""
    with (_project_file(_PROJECT_ROOT, HERE/name)).open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    receipt_path = _project_file(_PROJECT_ROOT, ENGINEERING/'ROOT-READBACK.json')
    receipt = json.loads(receipt_path.read_text())
    assert receipt['complete'] and receipt['actual_tables'] == 16 and receipt['actual_hands'] == 128
    for relative, digest in receipt['files'].items():
        path = _project_file(_PROJECT_ROOT, ENGINEERING/relative)
        assert path.stat().st_size == digest['bytes'] and sha(path) == digest['sha256'], relative
    assert receipt['actual_candidate_score_calls'] == 2374
    engineering_plan = json.loads((_project_file(_PROJECT_ROOT, ENGINEERING/'PLAN.json')).read_text())
    generation_file = Path(engineering_plan['generation_file'])
    source_file = Path(engineering_plan['raw_source_file'])
    batch = VipEohBatch.read(generation_file)
    source = source_file.read_text(encoding='utf-8')
    identity = batch.identity(source)
    assert identity == engineering_plan['candidate_identity']
    assert sha(source_file) == 'f6da2d82eabaf0b95ada0c836d18df582e670a8336bf6a4d61955e62ca13955e'
    namespace = 't93-fixed-t75-natural-confirmation-newroots-20261003-v1'
    roots = [{'root_id': f't93-fixed-t75-confirmation:{i:03d}',
              'seed': int.from_bytes(hashlib.sha256(f'{namespace}:{i}'.encode()).digest()[:8], 'big') & ((1<<63)-1)}
             for i in range(1,129)]
    prior_paths = [_project_file(_PROJECT_ROOT, AUTHOR/'FRESH-ROOTS-BEFORE-AUTHOR.json'), _project_file(_PROJECT_ROOT, AUTHOR/'COMPOSITIONS-BEFORE-AUTHOR.json'),
        _project_file(_PROJECT_ROOT, E/'t49-qualifier-opponent-behavior-1/COMPOSITIONS-BEFORE-TABLES.json'), _project_file(_PROJECT_ROOT, ENGINEERING/'COMPOSITIONS.json')]
    seeds = set()
    def collect(value):
        if isinstance(value, dict):
            if type(value.get('seed')) is int:
                seeds.add(value['seed'])
            for v in value.values():
                collect(v)
        elif isinstance(value, list):
            for v in value:
                collect(v)
    for path in prior_paths:
        collect(json.loads(path.read_text()))
    assert len({r['seed'] for r in roots}) == 128 and not seeds.intersection(r['seed'] for r in roots)
    compositions = freeze_qualifier_compositions(roots, 0.6)
    save('COMPOSITIONS.json', {'schema':'t93-fresh-confirmation-compositions/1', 'roots':compositions,
        'seed_namespace':namespace, 'seed_algorithm':'first8bytes SHA256(namespace:ordinal), unsigned & (2^63-1)',
        'selected_ordinals':[1,128], 'selected_all_ordinals_inclusive':True,
        'checked_prior_seed_files':{str(p):sha(p) for p in prior_paths},
        'checked_prior_distinct_seeds':len(seeds), 'prior_seed_collision':False,
        'scope':'new namespace plus listed prior freezes only; not exhaustive historical seed index',
        'composition_or_outcome_selection':False, 'new_worlds_tables':0})
    manifest = source_manifest(SOURCE_ROOTS)
    manifest.update(identity['source_manifest'])
    contract = _project_file(_PROJECT_ROOT, REPO_ROOT/identity['contract_path'])
    manifest[identity['contract_path']] = {'sha256':sha(contract),'bytes':contract.stat().st_size}
    assert manifest == json.loads((_project_file(_PROJECT_ROOT, ENGINEERING/'FROZEN-SOURCE-MANIFEST.json')).read_text())
    frozen = _project_file(_PROJECT_ROOT, HERE/'frozen-execution')
    frozen.mkdir(exist_ok=False)
    write_code_snapshot(frozen,manifest)
    for relative, digest in manifest.items():
        copied = frozen/'code_snapshot'/relative
        assert copied.stat().st_size == digest['bytes'] and sha(copied) == digest['sha256'], relative
    native = backend_info()
    if native['native_path']:
        path = Path(native['native_path'])
        directory = frozen/'native-backend'
        directory.mkdir()
        shutil.copyfile(path,directory/path.name)
        assert sha(directory/path.name) == identity['math_backend']['native_binary']['sha256']
    save('FROZEN-SOURCE-MANIFEST.json',manifest)
    prerequisites = [receipt_path, _project_file(_PROJECT_ROOT, ENGINEERING/'EXECUTION-IDENTITY.json'), _project_file(_PROJECT_ROOT, ENGINEERING/'PROCESS-TERMINAL.json'),
        _project_file(_PROJECT_ROOT, ENGINEERING/'PLAN.json'), _project_file(_PROJECT_ROOT, AUTHOR/'CURRENT-CANDIDATE-PACKAGE.json'), generation_file,
        source_file, source_file.parent/'generation.json', _project_file(_PROJECT_ROOT, HERE/'COMPOSITIONS.json'),
        _project_file(_PROJECT_ROOT, HERE/'FROZEN-SOURCE-MANIFEST.json'), _project_file(_PROJECT_ROOT, HERE/'prepare.py'), _project_file(_PROJECT_ROOT, HERE/'run_block.py'), _project_file(_PROJECT_ROOT, HERE/'ADAPTATION-DIFF.diff')]
    pins = {str(p.resolve()):sha(p) for p in prerequisites}
    plan = {'schema':'t93-fixed-formula-fresh-natural-confirmation-plan/1',
        'created_at_utc':datetime.now(timezone.utc).isoformat(),
        'stage':'fresh_natural_strength_experiment_current_identity_not_published_admission',
        'candidate_identity':identity, 'raw_source_file':str(source_file), 'generation_file':str(generation_file),
        'source_roots':SOURCE_ROOTS, 'prerequisite_sha256':pins,
        'root_ids':[r['root_id'] for r in roots], 'independent_roots':128,
        'rotations_per_root':4, 'rounds':8, 'paired_tables':512, 'planned_actual_tables':1024,
        'planned_hands':8192, 'planned_hands_per_arm':4096, 'blocks':4, 'roots_per_block':32,
        'compositions_file':str(_project_file(_PROJECT_ROOT, HERE/'COMPOSITIONS.json')), 'main_weak_fraction_setting':0.6,
        'human_majority_weak_prior_accepted':True,
        'actual_weak_opponent_slots':sum(r['actual_weak_count'] for r in compositions),
        'total_logical_opponent_slots':384,
        'primary':'complete-table C minus registered R18 net score, clustered by128 mother roots',
        'confidence':{'method':'mother-root bootstrap percentile','resamples':20000,'seed':2026100393,'interval':0.95},
        'secondary':['mutually exclusive own fan bands','opponent hu payments','highfan source clusters',
                     'ordinary loss versus actual cumulative highfan net','dealer/nondealer','runtime faults'],
        'signal_before_publish':{'net_lower95_gt_zero_required':True,
            'realized_highfan_component_net_positive_required_for_highfan_claim':True,
            'cross_source_highfan_required':True,
            'natural_strength_does_not_replace_condition_causality_or_official_release_gates':True},
        'official_settlement_multiplier':1,
        'ordinary_loss_allowed_if_real_cumulative_highfan_net_covers':True,
        'strong_opponent_each_nonnegative_not_qualifier_hard_gate':True,
        'inspection':'progress/cost/fault only until all four process handles are terminal; no midbatch tuning or seed append',
        'failure':'first engineering/capture/source/incomplete fault stops new pairs globally; keep1024 denominator and costs',
        'source_kind':'simulation', 'formula_and_limits_held_fixed':True,
        'offline_max_operations':batch.max_operations, 'normal_C_r18_fallback_allowed':False,
        'logical_clock_not_deadline_evidence':True, 'research_native_graph_meter_or_payload_overlays_used':False,
        'old_admission_or_results_transferred':False, 'new_author_calls':0,'new_formula':False,
        'confirmation_claim':False,'published':False,'sensitivity_fractions_not_started':[0.5,0.75],
        'python':sys.version,'python_executable':sys.executable,'platform':platform.platform(),'math_backend':native,
        'new_model_rules_choose_scores_worlds_tables_in_preparation':0}
    save('CAMPAIGN-PLAN.json',plan)
    for block in range(1,5):
        save(f'BLOCK-{block:02d}-PLAN.json',dict(plan,block=block,
            root_ids=plan['root_ids'][(block-1)*32:block*32],planned_roots=32,
            independent_roots=32,paired_tables=128,planned_actual_tables=256,
            planned_hands=2048,planned_hands_per_arm=1024,wall_clock_limit_seconds=10800,step_limit=10000,
            scoring_input_capture={'max_view_json_bytes':33554432,'max_total_json_bytes':17179869184,'max_unique_views':100000},
            prerequisite_sha256=dict(pins,**{str((_project_file(_PROJECT_ROOT, HERE/'CAMPAIGN-PLAN.json')).resolve()):sha(_project_file(_PROJECT_ROOT, HERE/'CAMPAIGN-PLAN.json'))})))
    print({'prepared':True,'fresh_mother_roots':128,'planned_actual_tables':1024,
        'actual_weak_slots':plan['actual_weak_opponent_slots'],'total_logical_opponent_slots':384,
        'new_worlds_tables_scores':0})


if __name__ == '__main__':
    main()
