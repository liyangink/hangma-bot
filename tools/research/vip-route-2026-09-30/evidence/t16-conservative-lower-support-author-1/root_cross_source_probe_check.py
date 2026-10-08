"""根核T16公开开发探针：仅读验签并对比真父全动作分数，不重新评分。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t16-conservative-lower-support-author-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import gzip,hashlib,json
from pathlib import Path
from hangma_bot.offline.vip_eoh_generate import VipEohBatch,load_vip_parents
from hangma_bot.offline.vip_eoh_probe_v2 import validate_public_input_probe
BASE=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t16-conservative-lower-support-author-1')
batch=VipEohBatch.read(_project_file(_PROJECT_ROOT, BASE/'S01-generation.batch.json'))
candidate=load_vip_parents([_project_file(_PROJECT_ROOT, BASE/'S01-model-output')],batch)[0]
summary_file=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t16-conservative-lower-support-author-1/S01-cross-source-probe-1/summary.json')
plan=json.loads((_project_file(_PROJECT_ROOT, BASE/'S01-CROSS-SOURCE-PROBE-PLAN.json')).read_text())
checked=validate_public_input_probe(summary_file,candidate,batch,reference_policy=plan['references'])
summary=json.loads(summary_file.read_text())
rows=[json.loads(l) for l in (_project_file(_PROJECT_ROOT, summary_file.parent/'results.jsonl')).read_text().splitlines()]
with gzip.open(_project_file(_PROJECT_ROOT, summary_file.parent/'views.jsonl.gz'),'rt') as f:views=[json.loads(l) for l in f]
details=[]
for v in views:
    matched=[r for r in rows if r['input_sha256']==v['input_sha256']];assert len(matched)==2
    old=next(r for r in matched if r['candidate_id']!=candidate['identity']['candidate_id']);new=next(r for r in matched if r['candidate_id']==candidate['identity']['candidate_id'])
    dto=v['candidate_view'];has_hu=any(a['action_key']=='hu' for a in dto['actions'])
    visible=dto['visible_state'];white=dto['tile_order'][-1]
    whites=sum(x==white for x in visible['my_hand'])+int(visible['drawn_tile']==white)
    oldvalues={e['action_key']:e['score'] for e in old['entries']};newvalues={e['action_key']:e['score'] for e in new['entries']}
    assert set(oldvalues)==set(newvalues)
    same=oldvalues==newvalues
    if has_hu or whites==0:assert same, v['input_sha256']
    details.append({'input_sha256':v['input_sha256'],'projected_view_sha256':v['view_sha256'],'source_roots':sorted({o['mother_root'] for o in v['origins']}),'current_legal_hu':has_hu,'current_white_count':whites,'protected_all_scores_same':same if has_hu or whites==0 else None,'all_scores_same':same,'parent_first':old['preferred_action_key'],'candidate_first':new['preferred_action_key'],'first_changed':old['preferred_action_key']!=new['preferred_action_key'],'order_changed':old['ordered_action_keys']!=new['ordered_action_keys'],'score_changed_count':sum(oldvalues[k]!=newvalues[k] for k in oldvalues),'candidate_operations':new['candidate_counted_operations'],'legal_roots':len(newvalues),'candidate_score_monotonic_ms':new['score_monotonic_ms']})
receipt={'schema':'t16-root-public-probe-check/1','status':'accepted_complete_mechanical_probe_not_admission','business_calls_in_this_check':0,'summary_sha256':hashlib.sha256(summary_file.read_bytes()).hexdigest(),'public_validator_pass':True,'actual_scored_package_windows':len(rows),'captured_inputs':len(views),'current_Hu_windows':sum(d['current_legal_hu'] for d in details),'current_zero_white_windows':sum(d['current_white_count']==0 for d in details),'protected_Hu_and_zero_white_all_scores_pointwise_unchanged':True,'first_changed':sum(d['first_changed'] for d in details),'order_changed':sum(d['order_changed'] for d in details),'scoring_changed_windows':sum(not d['all_scores_same'] for d in details),'max_candidate_operations':max(d['candidate_operations'] for d in details),'max_candidate_score_monotonic_ms':max(d['candidate_score_monotonic_ms'] for d in details),'legal_roots_candidate':sum(d['legal_roots'] for d in details),'rows':details,'new_independent_reviews':0,'admitted':False}
with (_project_file(_PROJECT_ROOT, BASE/'ROOT-CROSS-SOURCE-PROBE-CHECK.json')).open('x') as f:json.dump(receipt,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps({k:v for k,v in receipt.items() if k!='rows'},ensure_ascii=False))
print(json.dumps([d for d in details if d['first_changed']],ensure_ascii=False))
