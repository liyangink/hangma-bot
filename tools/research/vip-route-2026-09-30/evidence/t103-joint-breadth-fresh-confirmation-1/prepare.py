"""T102开发通过后，冻结未曝光128母源的T101／R18确认，零新评分。

使用T97第一作者前登记、T101作者禁止读取的确认种子；全部使用，
不按对手组成或结果选根。规则、正式公式、预算沿用T102。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t103-joint-breadth-fresh-confirmation-1'

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
import ast
import difflib
import hashlib
import json
import platform
import sys

from hangma_bot.offline.qualifier_opponents import freeze_qualifier_compositions
from hangma_bot.offline.scoring_sources import REPO_ROOT, source_manifest
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents

HERE=Path(__file__).resolve().parent
E=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')
PILOT=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t102-joint-breadth-fresh-pilot-1')
AUTHOR=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t101-joint-breadth-recovery-author-1')
RESERVATION=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t97-natural-preparation-joint-root-1/FRESH-ROOTS-BEFORE-AUTHOR.json')
BASE=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t93-fixed-formula-fresh-natural-confirmation-1')
SOURCE_ROOTS=('hangma_bot.offline.qualifier_opponents','hangma_bot.offline.evaluate',
    'hangma_bot.offline.vip_route_development','hangma_bot.offline.vip_evaluation',
    'hangma_bot.offline.scoring_input_capture')


def sha(path):
    """对实际字节封条；大原件采用流读，不重算评分。"""
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for part in iter(lambda:f.read(1<<20),b''):h.update(part)
    return h.hexdigest()


def save(name,value):
    """计划只新建；原失败、原费用和原分母不得覆盖。"""
    with (_project_file(_PROJECT_ROOT, HERE/name)).open('x') as f:
        json.dump(value,f,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False);f.write('\n')


def main():
    """核全批实际终态及开发筛选，登记四个32根／256桌进程计划。"""
    receipt=json.loads((_project_file(_PROJECT_ROOT, PILOT/'ROOT-READBACK.json')).read_text())
    assert receipt['complete'] and receipt['predeclared_confirmation_start_screen_passed']
    assert receipt['actual_tables']==256 and receipt['actual_hands']==2048
    assert receipt['actual_readback_tool_terminal']['verified_tool_terminal'] and receipt['actual_readback_tool_terminal']['exit_code']==0
    assert receipt['normal_R18_fallbacks']==0 and receipt['confirmed_mechanical_or_runtime_faults']==0
    assert sha(_project_file(_PROJECT_ROOT, PILOT/'CAMPAIGN-CLOSURE.json'))==receipt['closure_sha256']
    assert sha(_project_file(_PROJECT_ROOT, PILOT/'CLOSED-ARTIFACT-MANIFEST.json'))==receipt['local_raw_manifest_sha256']
    pilot=json.loads((_project_file(_PROJECT_ROOT, PILOT/'CAMPAIGN-PLAN.json')).read_text())
    batch_file=_project_file(_PROJECT_ROOT, AUTHOR/'S02-generation.batch.json');batch=VipEohBatch.read(batch_file)
    candidate=load_vip_parents([_project_file(_PROJECT_ROOT, AUTHOR/'S02-model-output')],batch)[0]
    assert candidate['identity']==pilot['formulas']['T101']
    source_file=_project_file(_PROJECT_ROOT, AUTHOR/'S02-model-output/candidate.py')
    reservation=json.loads(RESERVATION.read_text());roots=reservation['reserved_confirmation']
    assert len(roots)==128 and reservation['author_read_forbidden'] and reservation['worlds_generated']==0
    assert reservation['rounds']==8 and reservation['initial_scores']==[0,0,0,0]
    root_ids=[r['root_id'] for r in roots];seeds={r['seed'] for r in roots}
    assert len(seeds)==len(set(root_ids))==128
    # 只读启动清单和已登记种子；不读取教师世界，也不生成牌墙。
    starts=list(E.glob('t*/block-*/START.json'))
    assert all('t97-natural-preparation:reserved_confirmation:' not in p.read_text() for p in starts)
    prior_compositions=[p for p in E.glob('t*/COMPOSITIONS*.json') if p.parent!=HERE]
    prior_seeds=set()
    def collect(v):
        if isinstance(v,dict):
            if type(v.get('seed')) is int:prior_seeds.add(v['seed'])
            for item in v.values():collect(item)
        elif isinstance(v,list):
            for item in v:collect(item)
    for p in prior_compositions:collect(json.loads(p.read_text()))
    assert not seeds.intersection(prior_seeds)
    save('EXPOSURE-AND-SEED-CHECK.json',{'schema':'t103-bounded-exposure-check/1',
        'confirmation_root_ids_absent_in_named_start_manifests':True,
        'checked_start_files':{str(p):sha(p) for p in starts},
        'checked_composition_files':{str(p):sha(p) for p in prior_compositions},
        'prior_distinct_seeds':len(prior_seeds),'seed_collision':False,
        'scope':'top-level t* composition and block START files only; not an exhaustive historical world index',
        'new_rules_scores_worlds_tables':0})
    compositions=freeze_qualifier_compositions(roots,0.6)
    save('COMPOSITIONS.json',{'schema':'t103-prereserved-confirmation-compositions/1','roots':compositions,
        'reservation_file':str(RESERVATION),'all_128_reserved_roots_used':True,
        'composition_or_outcome_selection':False,'worlds_generated':0})
    original=(_project_file(_PROJECT_ROOT, BASE/'run_block.py')).read_text();runner=original
    replacements={
        "match_id_prefix='t93-fixed-formula-fresh-confirmation'":"match_id_prefix='t103-fixed-t101-fresh-confirmation'",
        "'schema':'t93-fresh-natural-confirmation-block-result/1'":"'schema':'t103-fresh-natural-confirmation-block-result/1'",
        "'scope':'four_block1024table_campaign'":"'scope':'t103_four_block1024table_campaign'",
    }
    for before,after in replacements.items():
        assert runner.count(before)==1,before;runner=runner.replace(before,after)
    ast.parse(runner);(_project_file(_PROJECT_ROOT, HERE/'run_block.py')).write_text(runner)
    (_project_file(_PROJECT_ROOT, HERE/'BASE-RUNNER.py')).write_bytes((_project_file(_PROJECT_ROOT, BASE/'run_block.py')).read_bytes())
    (_project_file(_PROJECT_ROOT, HERE/'ADAPTATION-DIFF.diff')).write_text(''.join(difflib.unified_diff(original.splitlines(True),runner.splitlines(True),fromfile='T93/run_block.py',tofile='T103/run_block.py')))
    original_reader=(_project_file(_PROJECT_ROOT, BASE/'close_campaign.py')).read_text()
    reader=original_reader.replace("'schema':'t93-whole-fresh-natural-confirmation-result/1'","'schema':'t103-whole-fresh-natural-confirmation-result/1'")
    assert reader!=original_reader;ast.parse(reader);(_project_file(_PROJECT_ROOT, HERE/'close_campaign.py')).write_text(reader)
    (_project_file(_PROJECT_ROOT, HERE/'READER-ADAPTATION-DIFF.diff')).write_text(''.join(difflib.unified_diff(original_reader.splitlines(True),reader.splitlines(True),fromfile='T93/close_campaign.py',tofile='T103/close_campaign.py')))
    save('OUTCOME-READER-FREEZE.json',{'stage':'before_actual_worlds','files':{str(_project_file(_PROJECT_ROOT, HERE/'close_campaign.py')):sha(_project_file(_PROJECT_ROOT, HERE/'close_campaign.py'))}})
    manifest=source_manifest(SOURCE_ROOTS);manifest.update(candidate['identity']['source_manifest'])
    contract=_project_file(_PROJECT_ROOT, REPO_ROOT/candidate['identity']['contract_path'])
    manifest[candidate['identity']['contract_path']]={'sha256':sha(contract),'bytes':contract.stat().st_size}
    assert manifest==json.loads((_project_file(_PROJECT_ROOT, PILOT/'FROZEN-SOURCE-MANIFEST.json')).read_text())
    save('FROZEN-SOURCE-MANIFEST.json',manifest)
    files=[_project_file(_PROJECT_ROOT, PILOT/'ROOT-READBACK.json'),_project_file(_PROJECT_ROOT, PILOT/'CAMPAIGN-CLOSURE.json'),_project_file(_PROJECT_ROOT, PILOT/'ACTUAL-READBACK-TERMINAL.json'),
        _project_file(_PROJECT_ROOT, PILOT/'CLOSED-ARTIFACT-MANIFEST.json'),_project_file(_PROJECT_ROOT, PILOT/'FROZEN-SOURCE-MANIFEST.json'),RESERVATION,
        batch_file,source_file,source_file.parent/'generation.json',_project_file(_PROJECT_ROOT, HERE/'prepare.py'),_project_file(_PROJECT_ROOT, HERE/'run_block.py'),
        _project_file(_PROJECT_ROOT, HERE/'BASE-RUNNER.py'),_project_file(_PROJECT_ROOT, HERE/'ADAPTATION-DIFF.diff'),_project_file(_PROJECT_ROOT, HERE/'close_campaign.py'),
        _project_file(_PROJECT_ROOT, HERE/'READER-ADAPTATION-DIFF.diff'),_project_file(_PROJECT_ROOT, HERE/'OUTCOME-READER-FREEZE.json'),
        _project_file(_PROJECT_ROOT, HERE/'EXPOSURE-AND-SEED-CHECK.json'),_project_file(_PROJECT_ROOT, HERE/'COMPOSITIONS.json'),_project_file(_PROJECT_ROOT, HERE/'FROZEN-SOURCE-MANIFEST.json')]
    pins={str(p):sha(p) for p in files}
    plan={'schema':'t103-fixed-t101-prereserved-confirmation-plan/1','created_at_utc':datetime.now(timezone.utc).isoformat(),
        'stage':'unexposed_confirmation_not_automatic_admission','candidate_identity':candidate['identity'],
        'raw_source_file':str(source_file),'generation_file':str(batch_file),'source_roots':SOURCE_ROOTS,'prerequisite_sha256':pins,
        'root_ids':root_ids,'independent_roots':128,'rotations_per_root':4,'rounds':8,'paired_tables':512,
        'planned_actual_tables':1024,'planned_hands':8192,'planned_hands_per_arm':4096,'blocks':4,'roots_per_block':32,
        'compositions_file':str(_project_file(_PROJECT_ROOT, HERE/'COMPOSITIONS.json')),'main_weak_fraction_setting':0.6,
        'human_majority_weak_prior_accepted':True,'actual_weak_opponent_slots':sum(r['actual_weak_count'] for r in compositions),
        'total_logical_opponent_slots':384,
        'primary':'complete-table T101 minus registered R18 net score, clustered by128 independent mother roots',
        'confidence':{'method':'mother-root bootstrap percentile','resamples':20000,'seed':20261003103,'interval':0.95},
        'secondary':['mutually exclusive own fan bands','opponent hu payments','highfan source clusters',
            'ordinary loss versus actual cumulative highfan net','dealer/nondealer','runtime faults'],
        'signal_before_publish':{'net_lower95_gt_zero_required':True,
            'realized_highfan_component_net_positive_required_for_highfan_claim':True,'cross_source_highfan_required':True,
            'natural_strength_does_not_replace_condition_causality_or_official_release_gates':True},
        'official_settlement_multiplier':1,'ordinary_loss_allowed_if_real_cumulative_highfan_net_covers':True,
        'strong_opponent_each_nonnegative_not_qualifier_hard_gate':True,
        'inspection':'progress/cost/fault only until all four actual handles terminal; no midbatch tuning or seed append',
        'failure':'first engineering fault stops new pairs globally; current pairs finish; original1024 denominator and costs retained',
        'source_kind':'simulation','formula_and_limits_held_fixed':True,'offline_max_operations':batch.max_operations,
        'normal_C_r18_fallback_allowed':False,'logical_clock_not_deadline_evidence':True,
        'research_native_graph_meter_or_payload_overlays_used':False,'old_admission_or_results_transferred':False,
        'new_author_calls':0,'new_formula':False,'confirmation_claim':False,'published':False,
        'sensitivity_fractions_not_started':[0.5,0.75],'python':sys.version,'python_executable':sys.executable,
        'platform':platform.platform(),'new_model_rules_choose_scores_worlds_tables_in_preparation':0}
    save('CAMPAIGN-PLAN.json',plan)
    for block in range(1,5):
        save(f'BLOCK-{block:02d}-PLAN.json',dict(plan,block=block,root_ids=root_ids[(block-1)*32:block*32],
            planned_roots=32,independent_roots=32,paired_tables=128,planned_actual_tables=256,
            planned_hands=2048,planned_hands_per_arm=1024,wall_clock_limit_seconds=10800,step_limit=10000,
            scoring_input_capture={'max_view_json_bytes':33554432,'max_total_json_bytes':17179869184,'max_unique_views':100000},
            prerequisite_sha256=dict(pins,**{str(_project_file(_PROJECT_ROOT, HERE/'CAMPAIGN-PLAN.json')):sha(_project_file(_PROJECT_ROOT, HERE/'CAMPAIGN-PLAN.json'))})))
    print({'prepared':True,'fresh_mother_roots':128,'planned_actual_tables':1024,
        'actual_weak_slots':plan['actual_weak_opponent_slots'],'logical_opponent_slots':384,'worlds_scores_tables':0})


if __name__=='__main__':main()
