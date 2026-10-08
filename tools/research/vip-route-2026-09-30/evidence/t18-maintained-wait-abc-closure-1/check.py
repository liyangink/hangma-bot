"""纯读已闭40条首手干预，逐源核目标输入、即时胡基准及续打路径。

不调用规则、评分或世界。强制弃牌是干预，不当候选自然首选；两个B
同首手同续策只用于确定性验证，不作为重复增强样本。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t18-maintained-wait-abc-closure-1'

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

HERE=Path(__file__).resolve().parent
SOURCE=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t18-actual-C-maintained-wait-abc-preparation-2')

def read(path):return json.loads(path.read_bytes())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def write(name,value):
    with (_project_file(_PROJECT_ROOT, HERE/name)).open('x') as stream:json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')

def main():
    plan=read(_project_file(_PROJECT_ROOT, SOURCE/'PREPARED.json'));result=read(_project_file(_PROJECT_ROOT, SOURCE/'COSTS-AND-RESULT.json'))
    assert plan['planned_mother_roots']==result['planned_mother_roots']==4
    assert plan['planned_continuation_instances']==result['completed_arms']==40
    files={str(p.resolve()):{'bytes':p.stat().st_size,'sha256':sha(p)} for p in SOURCE.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    write('RAW-FIRST-SEAL.json',{'status':'closed_original_bytes_first_seal','files':files,'file_count':len(files),
        'original_bytes':sum(f['bytes'] for f in files.values()),'actual_cli_exit_code':0,'business_calls':0})
    spec=importlib.util.spec_from_file_location('t18_pure_base_checker',_project_file(_PROJECT_ROOT, HERE/'base_check.py'));mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    base=mod.check(SOURCE)
    selection=read(_project_file(_PROJECT_ROOT, SOURCE/'SOURCE-SELECTION.json'));cached=read(Path(selection['inputs_file']))['rows']
    target_calls={};recovery=Counter();paths={}
    for line in (_project_file(_PROJECT_ROOT, SOURCE/'calls-and-choices.jsonl')).open():
        row=json.loads(line);key=(row['root_id'],row.get('variant'),row.get('arm'))
        if row['event']=='recovery_advance':recovery[row['status']]+=1
        if row['event']=='advance' and row['status']=='advanced':paths.setdefault(key,[]).append(row['choices'])
        if row['event']=='score_call' and row['kind']=='C':
            root=next(r for r in plan['roots'] if r['root_id']==row['root_id'])
            if row['window_key']==root['source']['target_window']:
                assert key not in target_calls;target_calls[key]=row
                assert row['input_capture']['view_sha256']==root['source']['source_C_full_DTO_sha256']
                if row['arm']=='Sol-C':
                    old=next(r for r in cached if r['pool']==root['pool'] and r['window_key']==root['source']['target_window'])
                    assert {e['action_key']:e['score'] for e in row['scores']['entries']}=={e['action_key']:e['score'] for e in old['actual_scored_candidates']}
    assert len(target_calls)==16
    expected=sum(len(r['source']['prefix'])+len(r['source']['current_prefix']) for r in plan['roots'])
    assert recovery=={'dispatch':expected,'advanced':expected}
    rows=[]
    for ordinal,root in enumerate(plan['roots'],1):
        restored=read(_project_file(_PROJECT_ROOT, SOURCE/f'root-{ordinal:02d}'/'RECOVERY-RESULT.json'))
        assert restored['status']=='recovered_actual_C_single_hand_start' and restored['all_seat_complete_observation_legal_set_and_window_checked']
        assert restored['whole_table_prefix_advance_calls']==len(root['source']['prefix']) and restored['single_hand_prefix_advance_calls']==len(root['source']['current_prefix'])
        source_fact=next(s['fact'] for s in selection['selected'] if s['fact']['window_key']==root['source']['target_window'])
        for variant in plan['variant_order']:
            directory=_project_file(_PROJECT_ROOT, SOURCE/f'root-{ordinal:02d}'/variant);outcomes={a:read(directory/(a+'-outcome.json')) for a in plan['arm_order']}
            assert outcomes['A']['first_action_key']=='hu' and outcomes['A']['settlement']['fan']==source_fact['current_fan']
            assert outcomes['A']['settlement']['winner_seat']==root['permutation'][0]
            for arm,outcome in outcomes.items():
                assert outcome['force_count']==1
                assert outcome['first_action_key']==('hu' if arm=='A' else root['intervention_action_key'])
            assert paths[(root['root_id'],variant,'Sol-B')]==paths[(root['root_id'],variant,'S02-B')]
            assert outcomes['Sol-B']['settlement']==outcomes['S02-B']['settlement']
            for arm in ('Sol-C','S02-C'):
                assert target_calls[(root['root_id'],plan['variant_order'][0],arm)]['scores']['entries']==target_calls[(root['root_id'],variant,arm)]['scores']['entries']
            vals={a:o['focal_net_score'] for a,o in outcomes.items()}
            rows.append({'mother_root':root['mother_root'],'profile':root['profile'],'target_window':root['source']['target_window'],
                'variant':variant,'first_action_keys':{a:o['first_action_key'] for a,o in outcomes.items()},'focal_single_hand_scores':vals,
                'deltas_vs_immediate_Hu':{a:vals[a]-vals['A'] for a in ('Sol-B','Sol-C','S02-C')},
                'continuation_delta_T17_minus_R18':vals['Sol-C']-vals['Sol-B'],
                'continuation_delta_T16_minus_R18':vals['S02-C']-vals['S02-B'],
                'settlements':{a:o['settlement'] for a,o in outcomes.items()},'not_natural_candidate_result':True})
    for path,pin in files.items():assert sha(Path(path))==pin['sha256'] and Path(path).stat().st_size==pin['bytes']
    receipt={**base,'schema':'t18-root-forced-maintained-wait-closure/1','raw_seal_sha256':sha(_project_file(_PROJECT_ROOT, HERE/'RAW-FIRST-SEAL.json')),
        'target_complete_DTO_verified_calls':16,'T17_target_cached_scoring_verified':8,'verified_recovery_advances':expected,
        'all_40_first_interventions_exactly_once':True,'two_R18_B_paths_verified_each_world':8,
        'source_mother_roots':4,'independent_upgrade_source_roots':3,'new_author_calls':0,
        'review_role':'root routine closed-batch check after one concentrated first-tool review','business_calls':0,'admitted':False}
    write('ROOT-CLOSED-CHECK.json',receipt)
    write('DEVELOPMENT-BEHAVIOR.json',{'status':'closed_public_maintained_wait_intervention_diagnostic_not_strength',
        'source_roots':4,'upgrade_source_roots':3,'control_source_roots':1,'worlds':8,'arms':40,'rows':rows,
        'hidden_variant_not_history_posterior':True,'no_outcome_selected_source':True,'not_natural_candidate_performance':True})
    print(json.dumps(receipt,ensure_ascii=False))
    print(json.dumps([{k:v for k,v in r.items() if k not in ('settlements','target_window')} for r in rows],ensure_ascii=False))

if __name__=='__main__':main()
