"""闭批后纯读对照：核真父复现旧16世界，定位父子首次实际路径分歧。"""

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
import json,hashlib
from pathlib import Path
from collections import defaultdict
HERE=Path(__file__).resolve().parent
E=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')
S=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t22-claim-opportunity-same-start-1')
def read(p):return json.loads(p.read_bytes())
def canon(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',', ':'),allow_nan=False)
def write(n,v):
    with (_project_file(_PROJECT_ROOT, HERE/n)).open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
def main():
    assert read(_project_file(_PROJECT_ROOT, HERE/'ROOT-CLOSED-CHECK.json'))['status']=='accepted_engineering_only'
    plan=read(_project_file(_PROJECT_ROOT, S/'PREPARED.json')); paths=defaultdict(list);scores={};choices={}
    roots={r['root_id']:r for r in plan['roots']}
    for line in (_project_file(_PROJECT_ROOT, S/'calls-and-choices.jsonl')).open():
        row=json.loads(line);scope=(row['root_id'],row.get('variant'),row.get('arm'))
        if row['event']=='advance' and row['status']=='advanced':paths[scope].append(row['choices'])
        if row['event']=='score_call' and row['kind']=='C':scores[scope+(canon(row['window_key']),)]=row
        if row['event']=='policy_choose' and row['seat']==roots[row['root_id']]['permutation'][0]:choices[scope+(canon(row['window_key']),)]=row
    replays=[];divergences=[];unchanged=[]
    for i,root in enumerate(plan['roots'],1):
        oldpath=Path(root['t22_origin_prepared_file']).parent
        prior=read(oldpath/'PREPARED.json');j=next(n for n,r in enumerate(prior['roots'],1) if r['root_id']==root['root_id'])
        for variant in plan['variant_order']:
            directory=_project_file(_PROJECT_ROOT, S/f'root-{i:02d}'/variant)
            previous=read(oldpath/f'root-{j:02d}'/variant/'Sol-C-outcome.json')
            parent=read(directory/'S02-C-outcome.json');child=read(directory/'Sol-C-outcome.json')
            shape=lambda out:[(d['window_key'],d['action_key']) for d in out['outcome']['decisions']]
            assert shape(parent)==shape(previous) and parent['settlement']==previous['settlement']
            replays.append({'root_id':root['root_id'],'mother_root':root['mother_root'],'variant':variant,'prior_closed_T19_path_and_settlement_exact':True,'decisions':len(shape(parent))})
            a=paths[(root['root_id'],variant,'Sol-C')];b=paths[(root['root_id'],variant,'S02-C')]
            delta=child['focal_net_score']-parent['focal_net_score']
            if a==b:
                assert child['settlement']==parent['settlement'];unchanged.append({'root_id':root['root_id'],'variant':variant,'actual_full_path_equal':True,'delta':delta});continue
            first=next((n for n,(x,y) in enumerate(zip(a,b)) if x!=y),None)
            assert first is not None,'one completed path strict prefix of another without divergent choice'
            assert a[:first]==b[:first]
            focal=root['permutation'][0]
            left=next(c for c in a[first] if c['window_key']['seat']==focal)
            right=next(c for c in b[first] if c['window_key']['seat']==focal)
            assert left['window_key']==right['window_key'] and left['action_key']!=right['action_key']
            w=canon(left['window_key']);cs=scores[(root['root_id'],variant,'Sol-C',w)];ps=scores[(root['root_id'],variant,'S02-C',w)]
            cp=choices[(root['root_id'],variant,'Sol-C',w)];pp=choices[(root['root_id'],variant,'S02-C',w)]
            assert cp['observation']==pp['observation'] and cp['legal_action_keys']==pp['legal_action_keys']
            assert cs['input_capture']['view_sha256']==ps['input_capture']['view_sha256']
            cvals={x['action_key']:x['score'] for x in cs['scores']['entries']};pvals={x['action_key']:x['score'] for x in ps['scores']['entries']}
            changed=[k for k in cvals if cvals[k]!=pvals[k]]
            assert all(k.startswith(('chi:','peng:')) for k in changed) and 'hu' not in cvals
            divergences.append({'root_id':root['root_id'],'mother_root':root['mother_root'],'variant':variant,'advance_ordinal':first+1,'window_key':left['window_key'],'view_sha256':cs['input_capture']['view_sha256'],'complete_observation_legal_keys_DTO_equal_before_first_path_divergence':True,'child_action':left['action_key'],'parent_action':right['action_key'],'child_scores':cvals,'parent_scores':pvals,'changed_claim_entries':[x for x in cs['scores']['entries'] if x['action_key'] in changed],'whole_continuation_child_minus_parent':delta,'not_isolated_action_causal_credit':True})
    write('PARENT-REPLAY-AND-FIRST-PATH-DIFF.json',{'schema':'t22-parent-replay-first-diff/1','status':'accepted','parent_paths_reproduced':replays,'exact_parent_prior_worlds':len(replays),'parent_child_identical_world_paths':unchanged,'actual_first_path_differences':divergences,'not_confirmation_or_release':True,'new_business_calls':0,'new_independent_reviews':0})
    print(json.dumps({'parent_exact_prior_worlds':len(replays),'same_paths':len(unchanged),'differing_paths':len(divergences),'deltas_at_differing_paths':[d['whole_continuation_child_minus_parent'] for d in divergences]}))
if __name__=='__main__':main()
