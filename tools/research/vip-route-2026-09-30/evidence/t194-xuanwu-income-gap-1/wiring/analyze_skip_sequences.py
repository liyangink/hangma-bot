"""只在自然完赛和官方原事件齐全后逐条核新SSE跳帧，不以水位猜事件。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t194-xuanwu-income-gap-1/wiring'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=_PROJECT_ROOT
OUT=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t194-xuanwu-income-gap-1/wiring/necessary-testroom-1')


def load(path):
    """读公共闭合证据，缺失保持失败。"""
    return json.loads(path.read_text())


def main():
    """用官方seq对照40个座位视角；次数是跳帧数，不声称等量GET实际节省。"""
    closed=load(_project_file(_PROJECT_ROOT, OUT/'CLOSED.json'))
    assert closed['complete'] and closed['postgame_bundle_verified']
    # 失败房也必须逐条诊断；此工具不授宽松工程门或更改原严格失败。
    session=_project_file(_PROJECT_ROOT, ROOT/load(OUT/'PLAN.json')['session'])
    spec=importlib.util.spec_from_file_location('t192_skip_readback', _project_file(_PROJECT_ROOT, HERE.parents[1]/'t165-live-watchdog-1/analyze.py'))
    a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
    tables,official_pins=a.official_tables(session)
    events={}
    for game,table in tables.items():
        events[game]={}
        for block in table['blocks']:
            for event in block['events']:
                seq=event['seq']
                assert seq not in events[game] or events[game][seq]==event
                events[game][seq]=event
    rows=[]; sources={}; legacy=Counter(); runtime_validation=Counter(); run_seats={}; decision_pins={}
    for path in sorted((session/'audit').glob('slot-*/runs/*/participants/u_*/games/*.jsonl')):
        run=path.parents[3]
        manifest=load(run/'manifest.json')['payload']
        if run not in run_seats:
            seats={}
            decision_paths=sorted((run/'participants').glob('u_*/decisions.jsonl'))
            assert len(decision_paths)==1
            for line in decision_paths[0].open():
                record=json.loads(line)
                observation=record.get('payload',{}).get('request',{}).get('observation')
                if isinstance(observation,dict) and type(observation.get('seat')) is int:
                    game=record['context']['game_id']
                    assert game not in seats or seats[game]==observation['seat']
                    seats[game]=observation['seat']
            run_seats[run]=seats
            decision_pins[str(decision_paths[0].relative_to(session))]=hashlib.sha256(decision_paths[0].read_bytes()).hexdigest()
        seats=run_seats[run]
        records=[(number,json.loads(line)) for number,line in enumerate(path.open(),1)]
        for number,record in records:
            payload=record.get('payload',{})
            if type(payload.get('seat')) is int:
                seats[record['context']['game_id']]=payload['seat']
        for number,record in records:
            payload=record.get('payload',{})
            reason=payload.get('sse_skip_reason')
            if reason:
                legacy[reason]+=1
            validation=payload.get('sse_skip_verification')
            if validation:
                runtime_validation[str(validation)]+=1
            if reason!='uninteresting_response_single_step':
                continue
            game=record['context']['game_id']; seq=payload['observed_seq']
            event=events[game].get(seq)
            own=seats.get(game)
            valid=bool(event is not None and (event['type'] in ('pass','timeout') or
                  (event['type'] in ('peng','gang','chi','tile_drawn') and own is not None and event.get('seat')!=own)))
            rows.append({'source':str(path.relative_to(session)),'line':number,'game_id':game,
                         'observed_seq':seq,'consumed_seq':payload['consumed_seq'],
                         'official_event':event,'own_seat':own,'verified':valid})
        sources[str(path.relative_to(session))]=hashlib.sha256(path.read_bytes()).hexdigest()
    assert len(sources)==40, '四席各十桌原审计未齐全'
    complete=all(row['verified'] and row['observed_seq']==row['consumed_seq']+1 for row in rows)
    result={'complete':complete,'source_sha256':sources,'decision_sha256':decision_pins,'official_table_sha256':official_pins,
            'new_skip_count':len(rows),'new_skip_official_types':dict(Counter((r['official_event'] or {}).get('type','missing') for r in rows)),
            'all_skip_reasons':dict(legacy),'runtime_validation':dict(runtime_validation),'rows':rows,
            'actual_GET_saving_equivalent_to_skip_count':False,'queue_causal_effect_proven':False}
    with (_project_file(_PROJECT_ROOT, OUT/'SKIP-SEQUENCES-CLOSED.json')).open('x') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')
    print({'complete':complete,'new_skip_count':len(rows),'own_seat_missing':sum(r['own_seat'] is None for r in rows)})
    assert complete,'官方原事件与新跳帧不符，保留失败，不自然接入新包'


if __name__=='__main__':
    main()
