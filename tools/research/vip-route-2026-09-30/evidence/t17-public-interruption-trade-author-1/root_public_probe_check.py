"""纯读两份真实公开探针，对齐直接父T16；不重复规则求解或业务评分。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t17-public-interruption-trade-author-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import hashlib,json
from pathlib import Path
from hangma_bot.offline.vip_eoh_generate import VipEohBatch,load_vip_parents
from hangma_bot.offline.vip_eoh_probe_v2 import validate_public_input_probe

HERE=Path(__file__).resolve().parent
PARENT=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t16-conservative-lower-support-author-1/S01-model-output')
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    """实际probe结束后一次验签、逐合法键对账，当前Hu/零白保持全部父值。"""
    batch=VipEohBatch.read(_project_file(_PROJECT_ROOT, HERE/'S01-generation.batch.json'))
    candidate=load_vip_parents([_project_file(_PROJECT_ROOT, HERE/'S01-model-output')],batch)[0]
    parent=load_vip_parents([PARENT],batch)[0]
    cid=candidate['identity']['candidate_id'];pid=parent['identity']['candidate_id']
    details=[];panels=[]
    for name,count in (('S01-cross-source-probe-1',128),('S01-new-A-probe-1',32)):
        directory=_project_file(_PROJECT_ROOT, HERE/name);summary_file=directory/'summary.json'
        plan=read(_project_file(_PROJECT_ROOT, HERE/(name+'.plan.json')))
        validate_public_input_probe(summary_file,candidate,batch,reference_policy=plan['references'])
        summary=read(summary_file)
        assert summary['status']=='probe_complete_not_admitted' and summary['scored_package_windows']==2*count
        rows=[json.loads(line) for line in (directory/'results.jsonl').read_text().splitlines()]
        grouped={}
        for row in rows:grouped.setdefault(row['input_sha256'],[]).append(row)
        import gzip
        with gzip.open(directory/'views.jsonl.gz','rt') as stream:
            views=[json.loads(line) for line in stream]
        assert len(views)==count and len(rows)==count*2
        for view in views:
            matched=grouped[view['input_sha256']];assert len(matched)==2
            old=next(r for r in matched if r['candidate_id']==pid)
            new=next(r for r in matched if r['candidate_id']==cid)
            dto=view['candidate_view'];visible=dto['visible_state'];white=dto['tile_order'][-1]
            has_hu=any(a['action_key']=='hu' for a in dto['actions'])
            current_white=white in visible['my_hand'] or visible['drawn_tile']==white
            oldvalues={e['action_key']:e['score'] for e in old['entries']}
            newvalues={e['action_key']:e['score'] for e in new['entries']}
            assert set(oldvalues)==set(newvalues)==set(a['action_key'] for a in dto['actions'])
            if has_hu or not current_white:assert newvalues==oldvalues
            details.append({'panel':name,'input_sha256':view['input_sha256'],'view_sha256':view['view_sha256'],
                'current_legal_hu':has_hu,'current_zero_white':not current_white,
                'origins':view['origins'],'parent_first':old['preferred_action_key'],
                'candidate_first':new['preferred_action_key'],
                'first_changed':old['preferred_action_key']!=new['preferred_action_key'],
                'order_changed':old['ordered_action_keys']!=new['ordered_action_keys'],
                'score_changed_count':sum(oldvalues[k]!=newvalues[k] for k in oldvalues),
                'score_monotonic_ms':new['score_monotonic_ms'],'operations':new['candidate_counted_operations']})
        panels.append({'name':name,'summary_sha256':sha(summary_file),'windows':count,
            'public_validator_pass':True,'candidate_id':cid,'true_parent_id':pid})
    result={'schema':'t17-root-combined-public-probe-check/1','status':'accepted_complete_mechanical_probe_not_admission',
        'business_calls_in_root_check':0,'new_independent_reviews':0,'panels':panels,'windows':len(details),
        'actual_scored_package_windows':2*len(details),'current_Hu_windows':sum(d['current_legal_hu'] for d in details),
        'current_zero_white_windows':sum(d['current_zero_white'] for d in details),
        'protected_Hu_and_zero_white_all_scores_pointwise_unchanged':True,
        'first_changed':sum(d['first_changed'] for d in details),'order_changed':sum(d['order_changed'] for d in details),
        'scoring_changed_windows':sum(d['score_changed_count']>0 for d in details),
        'max_candidate_operations':max(d['operations'] for d in details),
        'max_candidate_score_monotonic_ms':max(d['score_monotonic_ms'] for d in details),
        'rows':details,'admitted':False}
    with (_project_file(_PROJECT_ROOT, HERE/'ROOT-PUBLIC-PROBE-CHECK.json')).open('x') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('rows',)},ensure_ascii=False))
    print(json.dumps([d for d in details if d['first_changed']],ensure_ascii=False))
if __name__=='__main__':main()
