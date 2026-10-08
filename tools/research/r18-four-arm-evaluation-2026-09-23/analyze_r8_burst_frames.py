
from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/r18-four-arm-evaluation-2026-09-23'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import bisect
import glob
import json
from collections import Counter, defaultdict
from pathlib import Path

AUDIT = Path('artifacts/sessions/sse-phase-20260924-r8/audit')
OFFICIAL = Path('runs/sse-phase-20260924/official-events-r8')

events = {}
for path in OFFICIAL.glob('batch-*/events.json'):
    batch = int(path.parent.name.split('-')[-1])
    data = json.loads(path.read_text())
    events[batch] = {event['seq']: event for block in data['blocks'] for event in block['events']}

for slot in ['slot-baihu', 'slot-qinglong', 'slot-xuanwu', 'slot-zhuque']:
    state = []
    frames = defaultdict(list)
    seats = {}
    for path in glob.glob(str(AUDIT / slot / 'runs' / '*' / 'participants' / '*' / 'raw' / '*.jsonl')):
        for line in open(path):
            record = json.loads(line)
            payload = record.get('payload') or {}
            endpoint = payload.get('endpoint', '')
            game = record.get('context', {}).get('game_id')
            if not game:
                continue
            if payload.get('source') == 'sse_frame':
                frames[game].append((record['monotonic_ns']/1e9, payload.get('seq')))
            if not endpoint.endswith('/state'):
                continue
            timing = payload.get('request_timing') or {}
            q, g, st, end = (timing.get(x) for x in ['queued_at_monotonic', 'granted_at_monotonic',
                                                     'transport_started_at_monotonic', 'completed_at_monotonic'])
            if not all(isinstance(x, (int, float)) for x in [q,g,st,end]):
                continue
            row = {'q':q,'g':g,'st':st,'end':end,'game':game,'status':payload.get('http_status'),
                   'purpose':timing.get('query_purpose'),'wall':record['wall_time_unix_ms']}
            state.append(row)
            if payload.get('seq_requested') == 0 and game not in seats:
                try: seats[game] = json.loads(payload['raw'])['snapshot']['seat']
                except (ValueError,TypeError,KeyError): pass
    state.sort(key=lambda r:r['q'])
    for game in frames: frames[game].sort()
    rejections = sorted((r for r in state if r['status']==429), key=lambda r:r['st'])
    slow = [r for r in state if r['g']-r['q'] >=1]
    episodes=[]
    for r in slow:
        if not episodes or r['q']-episodes[-1][-1]['q']>1.05: episodes.append([r])
        else: episodes[-1].append(r)
    print('\nSLOT',slot,'episodes',len(episodes))
    for ep in episodes:
        before=[r for r in rejections if ep[0]['q']-1.3<=r['end']<=ep[-1]['g']]
        print(' episode',round(ep[0]['q']-state[0]['q'],1),'n',len(ep),
              'maxwait',round(max(r['g']-r['q'] for r in ep),3),'games',len(set(r['game'] for r in ep)),
              '429',len(before),'purpose',dict(Counter(r['purpose'] for r in ep)))
    for i,reject in enumerate(rejections,1):
        pre=[r for r in state if reject['st']-1.05 <= r['q']<=reject['st']]
        prev=[r for r in state if reject['st']-2.10 <= r['q']<reject['st']-1.05]
        pending=[r for r in state if r['q']<=reject['end']<r['g']]
        following=min((r['st'] for r in state if r['st']>reject['end']), default=reject['end'])
        kinds=Counter(); origins=Counter(); lag=[]
        for r in pre:
            origins[r['purpose']]+=1
            if r['purpose']!='sse_frame':continue
            trail=frames[r['game']]
            pos=bisect.bisect_right(trail,(r['q'],10**9))-1
            if pos<0: kinds['unmatched']+=1;continue
            ft,seq=trail[pos]
            if r['q']-ft>0.050: kinds['lag>50ms']+=1;continue
            lag.append(r['q']-ft)
            prevseq=trail[pos-1][1] if pos else 0
            batch=int(r['game'].split('_b')[-1].split('_')[0])
            ev=[events[batch].get(s) for s in range(prevseq+1,seq+1)]
            ev=[e for e in ev if e]
            key='+'.join((e['type'] if e['type']!='timeout' else 'timeout('+e['data']['window']+')') for e in ev)
            if key=='timeout(chi)+tile_drawn':
                key += ' own' if ev[-1]['seat']==seats.get(r['game']) else ' other'
            kinds[key]+=1
        print(' 429',i,'wall',reject['wall'],'pre',len(pre),'prev',len(prev),'pending',len(pending),
              'game',reject['game'].split('_b')[-1],'next_gap',round(following-reject['end'],3),
              'origins',dict(origins),'events',dict(kinds),'lagmax',round(max(lag,default=0),3))
