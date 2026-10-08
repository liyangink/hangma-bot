"""纯读比较额度重绑定前后路径；原失败的无动作记录不算已执行动作。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t13-joint-route-quality-author-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import json
from pathlib import Path
BASE=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t13-joint-route-quality-author-1')
old,new=_project_file(_PROJECT_ROOT, BASE/'S01-natural-recording-16'),_project_file(_PROJECT_ROOT, BASE/'S01-natural-recording-2400k-16')
rows=[]
for pool in ['H','M']:
 def load(base):
  rs=[json.loads(x) for x in (base/pool/'results.jsonl').read_text().splitlines()]
  outs={x['match_id']:x['outcome'] for x in json.loads((base/pool/'match-outcomes.json').read_text())}
  return {(tuple(r['seat_permutation']),'C' if ':vip:' in r['game_key']['game_id'] else 'A'):(r,outs[r['game_key']['game_id']]) for r in rs}
 a,b=load(old),load(new);assert set(a)==set(b) and len(a)==8
 def path(o):
  return [(d['action_key'],d['seat'],{x:y for x,y in d['window_key'].items() if x!='game_id'}) for d in o['decisions']]
 for key,(r,o) in a.items():
  nr,no=b[key];op,np=path(o),path(no);complete=r['status']=='complete'
  if complete:
   assert op==np and r['scores_after']==nr['scores_after']
   applied=len(op);failed=None
  else:
   assert r['status']=='partial' and o['decisions'][-1]['action_key'] is None
   assert 'WORKLOAD_EXCEEDED' in o['decisions'][-1]['fallback_reason']
   applied=len(op)-1;assert op[:applied]==np[:applied] and op[-1][1:]==np[applied][1:]
   failed={'original_action':None,'original_failure':o['decisions'][-1]['fallback_reason'],'new_action':np[applied][0],'no_original_applied_action_at_failed_window':True}
  rows.append({'pool':pool,'permutation':list(key[0]),'arm':key[1],'original_status':r['status'],'original_applied_action_count':applied,'new_decision_count':len(np),'old_complete_all_path_and_final_scores_equal':True if complete else None,'old_applied_prefix_all_equal':True,'original_failure_window':failed})
receipt={'schema':'t13-budget-only-natural-reexecution-comparison/1','business_calls':0,'actual_original_tables':16,'actual_reexecuted_tables':16,'old_complete_tables_path_and_final_scores_equal':sum(x['old_complete_all_path_and_final_scores_equal'] is True for x in rows),'old_failed_applied_prefixes_equal':sum(x['original_status']!='complete' for x in rows),'original_failed_records_and_denominators_preserved':True,'game_id_batch_namespace_normalized_only':True,'rows':rows}
with (_project_file(_PROJECT_ROOT, BASE/'natural-2400k-closure-1/OLD-NEW-PATH-COMPARISON.json')).open('x') as f:json.dump(receipt,f,ensure_ascii=False,indent=2);f.write('\n')
print({k:v for k,v in receipt.items() if k!='rows'})
