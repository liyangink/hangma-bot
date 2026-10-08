"""七个原输入走真实发布工厂和十桌专属计算；原截止、全评分摘要不变。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t179-production-wiring-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import asyncio, hashlib, json, os, time
from pathlib import Path
ROOT=_PROJECT_ROOT
HERE=Path(__file__).resolve().parent
def save(path,value):
    with path.open('x') as stream: json.dump(value,stream,ensure_ascii=False,indent=2);stream.write('\n')
def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def cases():
    from hangma_bot.application.audit_codec import decision_request_from_json,decision_budget_from_json
    ref=json.loads((_project_file(_PROJECT_ROOT, HERE.parent/'t173-joint-exact-equivalence-1/joint-actual-001/JOINT-RESULT.json')).read_text())
    refs={r['decision_id']:r for r in ref['rows'] if r['variant']=='baseline' and r['repeat']==0}
    result=[]
    for path in sorted((_project_file(_PROJECT_ROOT, HERE.parent/'t169-closed-state-pressure-1')).glob('dec-*.json')):
        document=json.loads(path.read_text())
        record=next(row['record'] for row in document['records'] if row['record']['kind']=='decision_input')
        req=decision_request_from_json(record['payload']['request']); budget=decision_budget_from_json(record['payload']['budget'])
        spans=tuple(getattr(budget,key)-record['monotonic_ns']/1e9 for key in ('enhancement_deadline_monotonic','fallback_deadline_monotonic','latest_send_at_monotonic'))
        assert hashlib.sha256(path.read_bytes()).hexdigest()==refs[req.decision_id]['original_input_sha256']
        assert [v*1000 for v in spans]==refs[req.decision_id]['original_remaining_ms']
        result.append((req,spans,refs[req.decision_id]))
    assert len(result)==7
    return result
async def main():
    import hangma_bot.bootstrap as b
    from hangma_bot.application.audit_codec import decision_plan_to_json
    from hangma_bot.application.deadline import SystemClock
    from hangma_bot.policy.interface import DecisionBudget
    assert os.nice(0)==0
    package=b._load_vip_free_manifest(); values=cases()
    async def wave(name,selected,concurrent):
        service=b.build_isolated_decision_policy(b._VipWorkerFactory(package['release_package_id'],b.VIP_S02_FREE_STRATEGY),execution_id=package['release_package_id'],clock=SystemClock(),settings=b.VIP_S02_COMPUTE_SETTINGS)
        started=time.monotonic();await service.start();startup=time.monotonic()-started
        for gid in {c[0].window_key.game_id for c in selected}:await service.acquire_game(gid)
        async def one(case):
            request,spans,reference=case;now=time.monotonic()
            try:
                plan=await service.choose(request,DecisionBudget(*(now+v for v in spans)))
                row={'decision_id':request.decision_id,'status':'SCORED','all_scores_traces_ranking_exact':digest(decision_plan_to_json(plan))==reference['observed']['all_scores_traces_and_ranking_sha256']}
            except Exception as exc:
                row={'decision_id':request.decision_id,'status':'FAILED','error':type(exc).__name__+': '+str(exc)}
            row.update(roundtrip_ms=(time.monotonic()-now)*1000,original_remaining_ms=[v*1000 for v in spans])
            return row
        try:
            rows=await asyncio.gather(*(one(v) for v in selected)) if concurrent else [await one(v) for v in selected]
            during=service.snapshot()
            for gid in {c[0].window_key.game_id for c in selected}:await service.release_game(gid)
        finally:await service.close()
        final=service.snapshot()
        assert final['closed'] and all(final[k]==0 for k in ('owned','pending','active','ready','live_processes','current','transport_inflight','transport_threads_alive','late_reap_inflight','late_reap_threads_alive','bound_games','releasing_games')),final
        return {'wave':name,'startup_seconds':startup,'rows':rows,'during':during,'resource_terminal':final}
    heavy=[v for v in values if any(c.action_key.startswith('gang:') for c in v[0].rules.legal_candidates)]
    waves=[await wave('serial-original',values,False),await wave('cold-three',heavy,True)]
    all_ok=all(row['status']=='SCORED' and row['all_scores_traces_ranking_exact'] for w in waves for row in w['rows'])
    result={'waves':waves,'actual_choose':sum(len(w['rows']) for w in waves),'all_original_deadlines_and_scores_exact':all_ok,'package_id':package['release_package_id'],'settings':package['params']['compute_settings'],'cpu_nice':os.nice(0),'synthetic_burst_not_official_same_instant':True,'HTTP_calls':0}
    save(_project_file(_PROJECT_ROOT, HERE/'REAL-FACTORY-RESULT-001.json'),result)
    print(json.dumps({'actual_choose':result['actual_choose'],'all_ok':all_ok,'latencies_ms':[round(r['roundtrip_ms'],3) for w in waves for r in w['rows']]}),flush=True)
    assert all_ok
if __name__=='__main__':asyncio.run(main())
