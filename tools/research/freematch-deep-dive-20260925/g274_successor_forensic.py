"""G274：复核六个官方超时窗的事件、SSE 水位与相邻请求时间线。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import collections
import datetime
import gzip
import json
import sys
from pathlib import Path
ROOT=_PROJECT_ROOT
sys.path.insert(0,str(_project_file(_PROJECT_ROOT, ROOT/'review/freematch-deep-dive-20260925')))
import g265_expired_response_audit as g265
r=json.loads((_project_file(_PROJECT_ROOT, ROOT/'review/freematch-deep-dive-20260925/evidence/g274-sse-chi-canary-20260929/successor-response-window-complete.json')).read_text())
targets=[x for x in r['nonpass_legal_timeout_rows'] if x['r18_top_action']!='pass']
ledger=json.loads((_project_file(_PROJECT_ROOT, ROOT/'runs/auto-match-watchdog/auto-match-watchdog-state.json')).read_text())
room=next(x for x in ledger['rooms'] if x['room_id']=='a_920ebd847493')
audit=_project_file(_PROJECT_ROOT, ROOT/room['audit_dir']);decisions=audit/'participants'/g265.live.ME/'decisions.jsonl'
requests=collections.defaultdict(list)
for line in decisions.open():
 rec=json.loads(line);z=rec.get('payload') or {};gid=(rec.get('context') or {}).get('game_id')
 if rec.get('kind')!='http_request' or z.get('phase')!='finished' or not gid:continue
 timing=z.get('request_timing') or {}
 q=timing.get('queued_at_monotonic'); gr=timing.get('granted_at_monotonic');st=timing.get('transport_started_at_monotonic');co=timing.get('completed_at_monotonic')
 requests[gid].append({'wall_ms':rec.get('wall_time_unix_ms'),'endpoint':z.get('endpoint'),'status':z.get('http_status'),'error':z.get('error_type'),'purpose':timing.get('query_purpose'),'priority':timing.get('scheduler_priority'),'queue_ms':None if q is None or gr is None else round((gr-q)*1000,1),'network_ms':None if st is None or co is None else round((co-st)*1000,1),'request_id':z.get('request_id')})
sources,_=g265.official_sources({x['game_id'] for x in targets})
raw=collections.defaultdict(lambda:{'frames':[],'states':[]})
for gid in sources:
 for path in sorted((audit/'participants'/g265.live.ME/'raw').glob(gid+'.*.jsonl.gz')):
  with gzip.open(path,'rt') as handle:
   for line in handle:
    rec=json.loads(line);z=rec.get('payload') or {};source=z.get('source')
    if source=='sse_frame':raw[gid]['frames'].append({'wall_ms':rec.get('wall_time_unix_ms'),'seq':z.get('seq'),'closed':z.get('closed')})
    if source=='state_response':
     body=z.get('raw')
     if isinstance(body,str):
      try:body=json.loads(body)
      except ValueError:body={}
     if not isinstance(body,dict):body={}
     snap=body.get('snapshot') or {};tm=z.get('request_timing') or {}
     raw[gid]['states'].append({'wall_ms':rec.get('wall_time_unix_ms'),'seq':body.get('seq'),'phase':snap.get('phase'),'round_no':snap.get('round_no'),'last_discard':snap.get('last_discard'),'status':z.get('http_status'),'purpose':tm.get('query_purpose')})

def fmt(ms):
 """将官方或本地 Unix 毫秒转为北京时间，仅用于可读时间线。"""
 if ms is None:return None
 return datetime.datetime.fromtimestamp(ms/1000,datetime.timezone(datetime.timedelta(hours=8))).strftime('%H:%M:%S.%f')[:12]
rows=[]
for target in targets:
 gid=target['game_id'];doc=json.loads(sources[gid].read_text());events=[e for b in doc['blocks'] for e in b.get('events') or []]
 ds=target['discard_seq'];to=target['timeout_seq'];evt={e['seq']:e for e in events};dms=evt[ds]['ts']*1000;tms=evt[to]['ts']*1000
 frames=sorted(raw[gid]['frames'],key=lambda x:x['wall_ms']);states=[x for x in raw[gid]['states'] if x['round_no']==target['round_no'] and x['seq'] is not None]
 f_discard=next((x for x in frames if x['seq'] is not None and x['seq']>=ds and dms-1000<=x['wall_ms']<=tms+3000),None)
 f_timeout=next((x for x in frames if x['seq'] is not None and x['seq']>=to and dms-1000<=x['wall_ms']<=tms+3000),None)
 before=max((x for x in states if x['seq']<ds),key=lambda x:x['seq'],default=None)
 after=min((x for x in states if x['seq']>=to),key=lambda x:x['seq'],default=None)
 req=[x for x in requests[gid] if dms-1500<=x['wall_ms']<=tms+2000]
 rows.append({'game_id':gid,'round_no':target['round_no'],'discard_seq':ds,'timeout_seq':to,'phase':target['phase'],'top':target['r18_top_action'],'scores':target['r18_scores'],
 'official_events':[{'seq':e['seq'],'type':e['type'],'seat':e.get('seat'),'tile':e.get('tile'),'ts_beijing':fmt(e['ts']*1000),'data':e.get('data')} for e in events if ds-1<=e['seq']<=to+1],
 'first_sse_at_or_after_discard':f_discard,'first_sse_at_or_after_timeout':f_timeout,'last_state_before_discard':before,'first_state_at_or_after_timeout':after,'nearby_requests':req})
print(json.dumps([{'game_id':x['game_id'],'discard_seq':x['discard_seq'],
                   'timeout_seq':x['timeout_seq'],'top':x['top'],
                   'sse_in_window':x['first_sse_at_or_after_discard'] is not None}
                  for x in rows],ensure_ascii=False))
Path('/tmp/g274_successor_forensic.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
