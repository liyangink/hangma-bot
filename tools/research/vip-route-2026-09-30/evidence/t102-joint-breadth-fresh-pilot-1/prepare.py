"""冻结T101、真父T97和注册R18的16新母源比较，不生成世界。

两组配对共256实际完整桌、2048单局；重复R18实际运行并记费用，
独立统计单位为16母牌山。规则、评分合同和正式公式保持不变。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t102-joint-breadth-fresh-pilot-1'

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
AUTHOR=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t101-joint-breadth-recovery-author-1')
PARENT=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t97-natural-preparation-joint-root-1')
BASE=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t99-new-joint-fresh-pilot-1')
SOURCE_ROOTS=('hangma_bot.offline.qualifier_opponents','hangma_bot.offline.evaluate',
    'hangma_bot.offline.vip_route_development','hangma_bot.offline.vip_evaluation',
    'hangma_bot.offline.scoring_input_capture')


def sha(path):
    """摘要按实际文件字节计算，不用名称推断来源。"""
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for part in iter(lambda:f.read(1<<20),b''):h.update(part)
    return h.hexdigest()


def save(name,value):
    """冻结材料只新建；失败与原费用保留，复跑另开批。"""
    with (_project_file(_PROJECT_ROOT, HERE/name)).open('x') as f:
        json.dump(value,f,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False);f.write('\n')


def main():
    """核真实完整评分收据和两正式身份，冻结16根及八进程计划。"""
    probe=json.loads((_project_file(_PROJECT_ROOT, AUTHOR/'PUBLIC-PROBE-CLOSURE.json')).read_text())
    readback=json.loads((_project_file(_PROJECT_ROOT, AUTHOR/'ROOT-PUBLIC-PROBE-READBACK.json')).read_text())
    assert probe['complete'] and readback['complete']
    assert readback['actual_tool_terminal']['verified_tool_terminal'] and readback['actual_tool_terminal']['exit_code']==0
    assert readback['actual_child_scores']==87 and readback['normal_R18_fallbacks']==0
    batch_file=_project_file(_PROJECT_ROOT, AUTHOR/'S02-generation.batch.json');batch=VipEohBatch.read(batch_file)
    new,parent=load_vip_parents([_project_file(_PROJECT_ROOT, AUTHOR/'S02-model-output'),_project_file(_PROJECT_ROOT, PARENT/'S01-model-output')],batch)
    assert new['identity']==probe['candidate_identity']
    assert new['identity']['candidate_id']==readback['candidate_id']
    assert parent['identity']['candidate_id']=='cf11888a2abb632e2ce08dc3e7b5a228f28e23238d02fdc93895e401128cddbd'
    assert new['identity']['source_manifest']==parent['identity']['source_manifest']
    assert new['identity']['params']==parent['identity']['params']
    assert new['identity']['math_backend']==parent['identity']['math_backend']
    reservation=json.loads((_project_file(_PROJECT_ROOT, AUTHOR/'FRESH-ROOTS-BEFORE-AUTHOR.json')).read_text())
    roots=reservation['fresh_pilot'];assert len(roots)==16 and reservation['rounds']==8
    assert reservation['worlds_generated']==0 and reservation['author_read_forbidden']
    seeds={r['seed'] for r in roots};assert len(seeds)==16 and len({r['root_id'] for r in roots})==16
    historical_paths=[_project_file(_PROJECT_ROOT, PARENT/'FRESH-ROOTS-BEFORE-AUTHOR.json'),
        _project_file(_PROJECT_ROOT, E/'t93-fixed-formula-fresh-natural-confirmation-1/COMPOSITIONS.json'),
        _project_file(_PROJECT_ROOT, E/'t75-net-upgrade-joint-author-1/FRESH-ROOTS-BEFORE-AUTHOR.json')]
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
        'all_sixteen_reserved_pilot_roots_used':True,'worlds_generated':0,
        'prior_seed_collision':False,'checked_prior_seed_files':{str(p):sha(p) for p in historical_paths},
        'scope':'collision check limited to named freezes, no exhaustive historical claim'})
    original=(_project_file(_PROJECT_ROOT, BASE/'run_block.py')).read_text();adapted=original
    replacements={
        '八个新母牌山、两个R18配对、共128桌的八块固定公式开发。':'16个新母牌山、两个R18配对、共256桌的八块固定公式开发。',
        '每块2母根16桌；四进程分两波，全终态前只看进度／费用／故障。':'每块4母根32桌；四进程分两波，全终态前只看进度／费用／故障。',
        "if len(selected) != 2 or plan['planned_actual_tables'] != 16 or plan['planned_hands'] != 128:":"if len(selected) != 4 or plan['planned_actual_tables'] != 32 or plan['planned_hands'] != 256:",
        "raise ValueError('每块固定2母根、16完整桌、128单局')":"raise ValueError('每块固定4母根、32完整桌、256单局')",
        "match_id_prefix='t99-fixed-formula-fresh-pilot'":"match_id_prefix='t102-fixed-formula-fresh-pilot'",
        'complete=(not issues and len(results)==16 and len(root_audits)==2 and len(settlements)==128)':'complete=(not issues and len(results)==32 and len(root_audits)==4 and len(settlements)==256)',
        "'schema':'t99-fresh-natural-pilot-block-result/1'":"'schema':'t102-fresh-natural-pilot-block-result/1'",
        "'planned_actual_tables':16":"'planned_actual_tables':32",
        "'descriptive_net_score_delta_per_table':sum(root_means)/2 if complete else None":"'descriptive_net_score_delta_per_table':sum(root_means)/4 if complete else None",
        "'new_formula':plan['variant']=='T97'":"'new_formula':plan['variant']=='T101'",
        "'comparison_scope':'development raw formula versus registered R18'":"'comparison_scope':'frozen formal development formula versus registered R18'",
        "'scope':'eight_block128table_pilot'":"'scope':'eight_block256table_pilot'",
        '保留128分母':'保留256分母',
    }
    for before,after in replacements.items():
        assert adapted.count(before)==1,before
        adapted=adapted.replace(before,after)
    ast.parse(adapted)
    (_project_file(_PROJECT_ROOT, HERE/'BASE-RUNNER.py')).write_bytes((_project_file(_PROJECT_ROOT, BASE/'run_block.py')).read_bytes())
    (_project_file(_PROJECT_ROOT, HERE/'run_block.py')).write_text(adapted)
    (_project_file(_PROJECT_ROOT, HERE/'ADAPTATION-DIFF.diff')).write_text(''.join(difflib.unified_diff(original.splitlines(True),adapted.splitlines(True),fromfile='T99/run_block.py',tofile='T102/run_block.py')))
    original_reader=(_project_file(_PROJECT_ROOT, BASE/'close_pilot.py')).read_text()
    reader=original_reader.replace('T97','T101').replace('T75','T97')
    reader_replacements={
        '纯读核128桌':'纯读核256桌',
        '按八母根计算':'按16母根计算',
        "==summary['charged_table_instances']==16":"==summary['charged_table_instances']==32",
        "assert summary['completed_hands']==128":"assert summary['completed_hands']==256",
        "assert len(rs)==16":"assert len(rs)==32",
        "assert len(by_id)==16":"assert len(by_id)==32",
        "assert duplicate_tables==32 and len(outcomes['T101'])==len(outcomes['T97'])==64":"assert duplicate_tables==64 and len(outcomes['T101'])==len(outcomes['T97'])==128",
        'assert len(seen_hands)==1024':'assert len(seen_hands)==2048',
        "for c in costs)==128":"for c in costs)==256",
        "all(len(pairs[v])==32":"all(len(pairs[v])==64",
        "for x in realized[v][a].values())==256":"for x in realized[v][a].values())==512",
        "'schema':'t99-whole-three-formula-pilot-result/1'":"'schema':'t102-whole-three-formula-pilot-result/1'",
        "'planned_actual_tables':128":"'planned_actual_tables':256",
        "'independent_roots':8":"'independent_roots':16",
        "'scope':'eight new development roots":"'scope':'sixteen new development roots",
    }
    for before,after in reader_replacements.items():
        assert reader.count(before)==1,before
        reader=reader.replace(before,after)
    ast.parse(reader)
    (_project_file(_PROJECT_ROOT, HERE/'close_pilot.py')).write_text(reader)
    (_project_file(_PROJECT_ROOT, HERE/'READER-ADAPTATION-DIFF.diff')).write_text(''.join(difflib.unified_diff(original_reader.splitlines(True),reader.splitlines(True),fromfile='T99/close_pilot.py',tofile='T102/close_pilot.py')))
    helper=_project_file(_PROJECT_ROOT, E/'t93-fixed-formula-fresh-natural-confirmation-1/close_campaign.py')
    save('OUTCOME-READER-FREEZE.json',{'stage':'before_actual_worlds','files':{str(p):sha(p) for p in [_project_file(_PROJECT_ROOT, HERE/'close_pilot.py'),helper]}})
    manifest=source_manifest(SOURCE_ROOTS);manifest.update(new['identity']['source_manifest'])
    contract=_project_file(_PROJECT_ROOT, REPO_ROOT/new['identity']['contract_path'])
    manifest[new['identity']['contract_path']]={'sha256':sha(contract),'bytes':contract.stat().st_size}
    save('FROZEN-SOURCE-MANIFEST.json',manifest)
    frozen=_project_file(_PROJECT_ROOT, HERE/'frozen-execution');frozen.mkdir(exist_ok=False);write_code_snapshot(frozen,manifest)
    native=backend_info();assert native['implementation']=='c_grouped'
    path=Path(native['native_path']);(frozen/'native-backend').mkdir()
    shutil.copyfile(path,frozen/'native-backend'/path.name)
    assert sha(path)==new['identity']['math_backend']['native_binary']['sha256']
    files=[_project_file(_PROJECT_ROOT, HERE/'prepare.py'),_project_file(_PROJECT_ROOT, HERE/'run_block.py'),_project_file(_PROJECT_ROOT, HERE/'BASE-RUNNER.py'),_project_file(_PROJECT_ROOT, HERE/'ADAPTATION-DIFF.diff'),
        _project_file(_PROJECT_ROOT, HERE/'close_pilot.py'),_project_file(_PROJECT_ROOT, HERE/'READER-ADAPTATION-DIFF.diff'),_project_file(_PROJECT_ROOT, HERE/'OUTCOME-READER-FREEZE.json'),
        _project_file(_PROJECT_ROOT, HERE/'COMPOSITIONS.json'),_project_file(_PROJECT_ROOT, HERE/'FROZEN-SOURCE-MANIFEST.json'),batch_file,
        _project_file(_PROJECT_ROOT, AUTHOR/'FRESH-ROOTS-BEFORE-AUTHOR.json'),_project_file(_PROJECT_ROOT, AUTHOR/'S02-model-output/generation.json'),
        _project_file(_PROJECT_ROOT, AUTHOR/'S02-model-output/candidate.py'),_project_file(_PROJECT_ROOT, AUTHOR/'PUBLIC-PROBE-CLOSURE.json'),
        _project_file(_PROJECT_ROOT, AUTHOR/'ROOT-PUBLIC-PROBE-READBACK.json'),_project_file(_PROJECT_ROOT, AUTHOR/'ROOT-AUTHOR-REPLY-FIRST-SEAL.json'),
        _project_file(_PROJECT_ROOT, PARENT/'S01-model-output/generation.json'),_project_file(_PROJECT_ROOT, PARENT/'S01-model-output/candidate.py'),*historical_paths]
    pins={str(p):sha(p) for p in files}
    plan={'schema':'t102-three-formula-paired-pilot/1','created_at_utc':datetime.now(timezone.utc).isoformat(),
        'stage':'new_root_development_not_confirmation','formulas':{'T101':new['identity'],'T97':parent['identity']},
        'generation_file':str(batch_file),'source_roots':SOURCE_ROOTS,'prerequisite_sha256':pins,
        'root_ids':[r['root_id'] for r in roots],'independent_roots':16,'rotations_per_root':4,'rounds':8,
        'planned_actual_tables':256,'planned_hands':2048,'distinct_logical_arm_tables':192,
        'duplicate_R18_tables_actually_run':64,'duplicate_baseline_charged_but_not_independent':True,
        'blocks':8,'roots_per_block':4,'compositions_file':str(_project_file(_PROJECT_ROOT, HERE/'COMPOSITIONS.json')),
        'main_weak_fraction_setting':0.6,'human_majority_weak_prior_accepted':True,
        'actual_weak_opponent_slots':sum(r['actual_weak_count'] for r in compositions),'total_logical_opponent_slots':48,
        'primary':['complete-table T101 minus registered R18','complete-table T101 minus true parent T97'],
        'confidence':{'method':'mother-root bootstrap percentile','resamples':20000,'seed':20261003102,'interval':0.95,'scope':'sixteen-root pilot descriptive only'},
        'secondary':['mutually exclusive own fan bands','opponent hu payments','highfan source clusters','ordinary losses and actual highfan net','runtime faults'],
        'confirmation_start_screen':{'all_engineering_and_duplicate_A_checks_required':True,
            'both_descriptive_mean_deltas_positive_required':True,'realized_highfan_net_improvement_required_for_highfan_candidate':True,
            'multiple_roots_with_positive_highfan_delta_required':True,'one_known_case_or_one_lucky_root_insufficient':True},
        'official_settlement_multiplier':1,'ordinary_loss_allowed_if_real_cumulative_highfan_net_covers':True,
        'inspection':'progress/cost/fault only until all eight handles terminal; no midbatch tuning or seed append',
        'failure':'first engineering fault stops new pairs globally; active pairs finish; original256 planned denominator and actual costs retained',
        'duplicate_A_verification':'full logical outcomes and settlement rows exactly identical; duplicate A not independent',
        'offline_max_operations':batch.max_operations,'normal_C_r18_fallback_allowed':False,
        'logical_clock_not_deadline_evidence':True,'old_admission_or_results_transferred':False,
        'new_author_calls':0,'confirmation_claim':False,'published':False,'new_model_rules_scores_worlds_tables_in_preparation':0,
        'reserved_confirmation_roots_not_started':128,'research_native_graph_meter_or_payload_overlays_used':False}
    save('CAMPAIGN-PLAN.json',plan)
    for block in range(1,9):
        variant='T101' if block<=4 else 'T97';ordinal=(block-1)%4
        identity=new['identity'] if variant=='T101' else parent['identity']
        package=_project_file(_PROJECT_ROOT, AUTHOR/'S02-model-output') if variant=='T101' else _project_file(_PROJECT_ROOT, PARENT/'S01-model-output')
        save(f'BLOCK-{block:02d}-PLAN.json',dict(plan,block=block,variant=variant,
            candidate_identity=identity,raw_source_file=str(package/'candidate.py'),
            root_ids=plan['root_ids'][ordinal*4:ordinal*4+4],planned_roots=4,independent_roots=4,
            planned_actual_tables=32,planned_hands=256,paired_tables=16,
            wall_clock_limit_seconds=3600,step_limit=10000,
            scoring_input_capture={'max_view_json_bytes':33554432,'max_total_json_bytes':2147483648,'max_unique_views':12000},
            prerequisite_sha256=dict(pins,**{str(_project_file(_PROJECT_ROOT, HERE/'CAMPAIGN-PLAN.json')):sha(_project_file(_PROJECT_ROOT, HERE/'CAMPAIGN-PLAN.json'))})))
    print({'prepared':True,'fresh_mother_roots':16,'planned_actual_tables':256,
        'actual_weak_slots':plan['actual_weak_opponent_slots'],'total_slots':48,'worlds_scores_tables':0})


if __name__=='__main__':main()
