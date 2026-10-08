"""只读已自然闭合的前五个free_v7会话，核官方超时、完整评分及资源。

不发HTTP、不重评分、不续房、不改控制位；输出独占保存，原件漂移即失败。
事件源限于赛后审计，不能成为线上候选输入；超时通知按我方座位和kind单列。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
import json,hashlib
b=Path('tools/research/vip-route-2026-09-30/evidence/t191-four-day-execution-1')
def load(p):return json.loads(p.read_text())
def pin(p):
 raw=p.read_bytes();return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
rows=[];pins={};seen=set();timeout=Counter()
for n in range(1,6):
 d=b/f'batch-{n:03d}';names=['RUN-CLOSED.json','SUMMARY.json','FREE-CHILD-TERMINAL.json','POSTPROCESS-CLOSED.json','PLAN.json'];docs={name:load(d/name) for name in names};s=docs['SUMMARY.json']
 assert docs['FREE-CHILD-TERMINAL.json']['actual_exit_code']==0 and not docs['FREE-CHILD-TERMINAL.json']['controller_sent_termination_signal']
 assert docs['POSTPROCESS-CLOSED.json']['failures']==[] and s['postgame_bundle_verified'] and s['postgame_audit_complete']
 assert s['compute_faults']==s['compute_restarts']==0
 audit=s['audit'][0];assert isinstance(audit['full_plan_legal_key_mismatches'],list) and not audit['full_plan_legal_key_mismatches']
 tables=s['tables'];assert len(tables)==10;gids={x['game_id'] for x in tables};assert not gids&seen;seen|=gids
 for t in s['terminals']:
  counts=t['decision_compute'];assert counts['closed'] is True
  assert all(counts[k]==0 for k in ['owned','pending','active','ready','live_processes','current','bound_games','releasing_games','transport_inflight','late_reap_inflight','late_reap_threads_alive','transport_threads_alive'])
 session=Path(docs['PLAN.json']['free_session']);ownseat={x['game_id']:int(next(iter(x['seat_arm_map']))) for x in tables};checked=set();localtimeouts=Counter()
 for p in sorted(session.glob('official/dl-*/events.json')):
  doc=load(p);gid=doc['game_id']
  if gid not in gids or gid in checked:continue
  assert pin(p)['sha256']==s['official_source_sha256'][gid];checked.add(gid);pins[str(p)]=pin(p)
  for block in doc['blocks']:
   for event in block['events']:
    if event['type']=='timeout' and event.get('seat')==ownseat[gid]:localtimeouts[event.get('data',{}).get('kind','unknown')]+=1
 assert checked==gids;timeout.update(localtimeouts)
 row={'batch':n,'tables':10,'plans':audit['plans'],'complete_plans':audit['complete_plans'],'missing_full':len(audit['failed_plans']),'missing_full_with_choice':sum(len(x['input']['legal'])>1 for x in audit['failed_plans']),'game_request_429':s['game_request_429'],'own_official_timeouts':dict(localtimeouts),'faults':0,'restarts':0,'resources_zero':True,'accounts':s['mutually_exclusive_accounts']['T110'],'failed_plans_by_phase':dict(Counter(x['input']['phase'] for x in audit['failed_plans'])),'rule_statuses_preserved':s['rule_statuses'],'natural_exit':True,'postprocess_success':True}
 assert row['missing_full']==row['plans']-row['complete_plans'];rows.append(row)
 for name in names:pins[str(d/name)]=pin(d/name)
out=b/'FREE-FIRST-FIVE-CLOSED-READBACK.json';assert not out.exists()
record={'schema':'t191-five-closed-free-readback/1','captured_at_utc':datetime.now(timezone.utc).isoformat(),'batches':rows,'unique_tables':len(seen),'single_hands':len(seen)*8,'plans':sum(x['plans'] for x in rows),'complete_plans':sum(x['complete_plans'] for x in rows),'missing_full_with_choice':sum(x['missing_full_with_choice'] for x in rows),'game_request_429':sum(x['game_request_429'] for x in rows),'own_official_timeouts':dict(timeout),'identity_scope':'vip_s02_bounded_d1_free_v7; same formula observational results only','source_pins':pins,'new_business_calls':0,'formal_or_strength_admission':False,'rule_config_unknown_or_failures_not_reclassified':True,'prior_reader_assertion_error':'第一次读full_plan_legal_key_mismatches时按整数0检查实际空列表，在结论写出前失败；本次依据实际schema核空列表和全部明确资源字段，未改原件。'}
out.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:record[k] for k in ['unique_tables','single_hands','plans','complete_plans','missing_full_with_choice','game_request_429','own_official_timeouts','new_business_calls']},ensure_ascii=False))
