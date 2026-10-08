"""冻结T97新公式、T75原码及注册R18的八新母根开发比较，不生成世界。

复用既有两臂完整桌工具：两组配对共128实际桌，R18实际重复两遍。
重复基线须逐动作核相同；独立统计单位仍只有八母牌山。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t99-new-joint-fresh-pilot-1'

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
import difflib
import hashlib
import json
from pathlib import Path
import shutil

from hangma_bot.hangma._standard import backend_info
from hangma_bot.offline.qualifier_opponents import freeze_qualifier_compositions
from hangma_bot.offline.scoring_sources import REPO_ROOT, source_manifest, write_code_snapshot
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents

HERE=Path(__file__).resolve().parent
E=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')
AUTHOR=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t97-natural-preparation-joint-root-1')
CAUSAL=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t98-new-joint-common-start-1')
OLD=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t93-fixed-formula-fresh-natural-confirmation-1')
SOURCE_ROOTS=('hangma_bot.offline.qualifier_opponents','hangma_bot.offline.evaluate',
    'hangma_bot.offline.vip_route_development','hangma_bot.offline.vip_evaluation',
    'hangma_bot.offline.scoring_input_capture')


def sha(path):
    """流式字节封条，不把路径名称当身份。"""
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for part in iter(lambda:f.read(1<<20),b''):h.update(part)
    return h.hexdigest()


def save(name,value):
    """计划只新建；中途修改或复跑须另批登记。"""
    with (_project_file(_PROJECT_ROOT, HERE/name)).open('x') as f:
        json.dump(value,f,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False);f.write('\n')


def main():
    """核机械/续打收据，冻结公式与比例，再生成八份隔离进程计划。"""
    causal=json.loads((_project_file(_PROJECT_ROOT, CAUSAL/'ROOT-READBACK.json')).read_text())
    assert causal['complete'] and causal['actual_continuations']==5 and causal['normal_R18_fallbacks']==0
    for name,identity in causal['source_pins'].items():
        p=_project_file(_PROJECT_ROOT, CAUSAL/name);assert p.stat().st_size==identity['bytes'] and sha(p)==identity['sha256']
    probe=json.loads((_project_file(_PROJECT_ROOT, AUTHOR/'PUBLIC-PROBE-COMBINED-CLOSURE.json')).read_text())
    assert probe['complete'] and probe['total_actual_score_calls']==122
    batch_file=_project_file(_PROJECT_ROOT, AUTHOR/'S01-generation.batch.json');batch=VipEohBatch.read(batch_file)
    new=load_vip_parents([_project_file(_PROJECT_ROOT, AUTHOR/'S01-model-output')],batch)[0]
    assert new['identity']==probe['candidate_identity']
    ref_file=_project_file(_PROJECT_ROOT, AUTHOR/'T75-REFERENCE-SOURCE.py');reference=ref_file.read_text()
    ref_identity=batch.identity(reference);assert ref_identity==probe['reference_raw_identity']
    reservation=json.loads((_project_file(_PROJECT_ROOT, AUTHOR/'FRESH-ROOTS-BEFORE-AUTHOR.json')).read_text())
    roots=reservation['pilot'];assert len(roots)==8 and reservation['rounds']==8
    seeds={r['seed'] for r in roots};assert len(seeds)==8 and not seeds.intersection(r['seed'] for r in reservation['reserved_confirmation'])
    historical_paths=[_project_file(_PROJECT_ROOT, OLD/'COMPOSITIONS.json'),_project_file(_PROJECT_ROOT, E/'t75-net-upgrade-joint-author-1/FRESH-ROOTS-BEFORE-AUTHOR.json')]
    historical_seeds=set()
    def collect(v):
        if isinstance(v,dict):
            if type(v.get('seed')) is int:historical_seeds.add(v['seed'])
            for item in v.values():collect(item)
        elif isinstance(v,list):
            for item in v:collect(item)
    for p in historical_paths:collect(json.loads(p.read_text()))
    assert not seeds.intersection(historical_seeds)
    compositions=freeze_qualifier_compositions(roots,0.6)
    save('COMPOSITIONS.json',{'roots':compositions,'seed_source':str(_project_file(_PROJECT_ROOT, AUTHOR/'FRESH-ROOTS-BEFORE-AUTHOR.json')),
        'main_weak_fraction_setting':0.6,'weak_type_split':[0.5,0.5],
        'all_eight_reserved_pilot_roots_used':True,'worlds_generated':0,
        'prior_seed_collision':False,'checked_prior_seed_files':{str(p):sha(p) for p in historical_paths},
        'scope':'collision check limited to named freezes, no exhaustive historical claim'})
    original=(_project_file(_PROJECT_ROOT, OLD/'run_block.py')).read_text()
    adapted=original
    replacements={
        '128新母牌山、四座配对1024桌的四分块固定公式验证。':'八个新母牌山、两个R18配对、共128桌的八块固定公式开发。',
        '每块32母根256桌；四进程全终态前仅看进度／费用／故障，不读取中途积分。':'每块2母根16桌；四进程分两波，全终态前只看进度／费用／故障。',
        "if len(selected) != 32 or plan['planned_actual_tables'] != 256 or plan['planned_hands'] != 2048:":"if len(selected) != 2 or plan['planned_actual_tables'] != 16 or plan['planned_hands'] != 128:",
        "raise ValueError('每块固定32母根、256完整桌、2048单局')":"raise ValueError('每块固定2母根、16完整桌、128单局')",
        "match_id_prefix='t93-fixed-formula-fresh-confirmation'":"match_id_prefix='t99-fixed-formula-fresh-pilot'",
        'complete=(not issues and len(results)==256 and len(root_audits)==32 and len(settlements)==2048)':'complete=(not issues and len(results)==16 and len(root_audits)==2 and len(settlements)==128)',
        "'schema':'t93-fresh-natural-confirmation-block-result/1'":"'schema':'t99-fresh-natural-pilot-block-result/1'",
        "'planned_actual_tables':256":"'planned_actual_tables':16",
        "'descriptive_net_score_delta_per_table':sum(root_means)/32 if complete else None":"'descriptive_net_score_delta_per_table':sum(root_means)/2 if complete else None",
        "'strength_confirmation':False,'new_author_calls':0,'new_formula':False":"'strength_confirmation':False,'new_author_calls':0,'new_formula':plan['variant']=='T97',\n        'variant':plan['variant'],'comparison_scope':'development raw formula versus registered R18'",
        "'scope':'four_block1024table_campaign'":"'scope':'eight_block128table_pilot'",
        'choices=range(1,5)':'choices=range(1,9)',
        '保留1024分母':'保留128分母',
    }
    for before,after in replacements.items():
        assert adapted.count(before)==1, before
        adapted=adapted.replace(before,after)
    ast.parse(adapted)
    (_project_file(_PROJECT_ROOT, HERE/'BASE-RUNNER.py')).write_bytes((_project_file(_PROJECT_ROOT, OLD/'run_block.py')).read_bytes())
    (_project_file(_PROJECT_ROOT, HERE/'run_block.py')).write_text(adapted)
    (_project_file(_PROJECT_ROOT, HERE/'ADAPTATION-DIFF.diff')).write_text(''.join(difflib.unified_diff(original.splitlines(True),adapted.splitlines(True),fromfile='T93/run_block.py',tofile='T99/run_block.py')))
    manifest=source_manifest(SOURCE_ROOTS);manifest.update(new['identity']['source_manifest'])
    contract=_project_file(_PROJECT_ROOT, REPO_ROOT/new['identity']['contract_path'])
    manifest[new['identity']['contract_path']]={'sha256':sha(contract),'bytes':contract.stat().st_size}
    assert all(new['identity']['source_manifest'][n]==ref_identity['source_manifest'][n] for n in new['identity']['source_manifest'])
    save('FROZEN-SOURCE-MANIFEST.json',manifest)
    frozen=_project_file(_PROJECT_ROOT, HERE/'frozen-execution');frozen.mkdir(exist_ok=False);write_code_snapshot(frozen,manifest)
    native=backend_info()
    assert native['implementation']=='c_grouped'
    if native['native_path']:
        path=Path(native['native_path']);(frozen/'native-backend').mkdir()
        shutil.copyfile(path,frozen/'native-backend'/path.name)
        assert sha(path)==new['identity']['math_backend']['native_binary']['sha256']
    files=[_project_file(_PROJECT_ROOT, HERE/'prepare.py'),_project_file(_PROJECT_ROOT, HERE/'run_block.py'),_project_file(_PROJECT_ROOT, HERE/'BASE-RUNNER.py'),_project_file(_PROJECT_ROOT, HERE/'ADAPTATION-DIFF.diff'),
        _project_file(_PROJECT_ROOT, HERE/'COMPOSITIONS.json'),_project_file(_PROJECT_ROOT, HERE/'FROZEN-SOURCE-MANIFEST.json'),batch_file,ref_file,
        _project_file(_PROJECT_ROOT, AUTHOR/'FRESH-ROOTS-BEFORE-AUTHOR.json'),_project_file(_PROJECT_ROOT, AUTHOR/'S01-model-output/generation.json'),
        _project_file(_PROJECT_ROOT, AUTHOR/'S01-model-output/candidate.py'),_project_file(_PROJECT_ROOT, AUTHOR/'PUBLIC-PROBE-COMBINED-CLOSURE.json'),
        _project_file(_PROJECT_ROOT, CAUSAL/'ROOT-READBACK.json'),_project_file(_PROJECT_ROOT, CAUSAL/'CLOSURE.json')]
    pins={str(p):sha(p) for p in files}
    plan={'schema':'t99-three-formula-paired-pilot/1','created_at_utc':datetime.now(timezone.utc).isoformat(),
        'stage':'new_root_development_not_confirmation','formulas':{'T97':new['identity'],'T75':ref_identity},
        'generation_file':str(batch_file),'source_roots':SOURCE_ROOTS,'prerequisite_sha256':pins,
        'root_ids':[r['root_id'] for r in roots],'independent_roots':8,'rotations_per_root':4,'rounds':8,
        'planned_actual_tables':128,'planned_hands':1024,'distinct_logical_arm_tables':96,
        'duplicate_R18_tables_actually_run':32,'duplicate_baseline_charged_but_not_independent':True,
        'blocks':8,'roots_per_block':2,'compositions_file':str(_project_file(_PROJECT_ROOT, HERE/'COMPOSITIONS.json')),
        'main_weak_fraction_setting':0.6,'human_majority_weak_prior_accepted':True,
        'actual_weak_opponent_slots':sum(r['actual_weak_count'] for r in compositions),'total_logical_opponent_slots':24,
        'primary':['complete-table T97 minus registered R18','complete-table T97 minus fixed current T75 raw reference'],
        'confidence':{'method':'mother-root bootstrap percentile','resamples':20000,'seed':2026100399,'interval':0.95,'scope':'eight-root pilot descriptive only'},
        'secondary':['mutually exclusive own fan bands','opponent hu payments','highfan source clusters','ordinary losses and actual highfan net','runtime faults'],
        'confirmation_start_screen':{'all_engineering_and_duplicate_A_checks_required':True,
            'both_descriptive_mean_deltas_positive_required':True,'realized_highfan_net_improvement_required_for_highfan_candidate':True,
            'multiple_roots_with_positive_highfan_delta_required':True,'one_known_case_or_one_lucky_root_insufficient':True},
        'official_settlement_multiplier':1,'ordinary_loss_allowed_if_real_cumulative_highfan_net_covers':True,
        'inspection':'progress/cost/fault only until all eight handles terminal; no midbatch tuning or seed append',
        'failure':'first engineering fault stops new pairs globally; active pairs finish; original128 planned denominator and actual costs retained',
        'duplicate_A_verification':'normalize no gameplay fields; compare window keys, actual action/seat and settlements, full outcomes except policy compute timings',
        'offline_max_operations':batch.max_operations,'normal_C_r18_fallback_allowed':False,
        'logical_clock_not_deadline_evidence':True,'old_admission_or_results_transferred':False,
        'new_author_calls':0,'confirmation_claim':False,'published':False,'new_model_rules_scores_worlds_tables_in_preparation':0,
        'reserved_confirmation_roots_not_started':128,'research_native_graph_meter_or_payload_overlays_used':False}
    save('CAMPAIGN-PLAN.json',plan)
    for block in range(1,9):
        variant='T97' if block<=4 else 'T75';ordinal=(block-1)%4
        save(f'BLOCK-{block:02d}-PLAN.json',dict(plan,block=block,variant=variant,
            candidate_identity=new['identity'] if variant=='T97' else ref_identity,
            raw_source_file=str(_project_file(_PROJECT_ROOT, AUTHOR/'S01-model-output/candidate.py')) if variant=='T97' else str(ref_file),
            root_ids=plan['root_ids'][ordinal*2:ordinal*2+2],planned_roots=2,independent_roots=2,
            planned_actual_tables=16,planned_hands=128,paired_tables=8,
            wall_clock_limit_seconds=3600,step_limit=10000,
            scoring_input_capture={'max_view_json_bytes':33554432,'max_total_json_bytes':2147483648,'max_unique_views':12000},
            prerequisite_sha256=dict(pins,**{str(_project_file(_PROJECT_ROOT, HERE/'CAMPAIGN-PLAN.json')):sha(_project_file(_PROJECT_ROOT, HERE/'CAMPAIGN-PLAN.json'))})))
    print({'prepared':True,'fresh_mother_roots':8,'planned_actual_tables':128,
        'actual_weak_slots':plan['actual_weak_opponent_slots'],'total_slots':24,'worlds_scores_tables':0})


if __name__=='__main__':main()
