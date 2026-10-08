"""在相同704个条件世界加入等胡四臂，诊断前期路线与终点升级的交互。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/big-hand-paths-2026-09-09'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import asyncio
from collections import Counter
from concurrent.futures import ProcessPoolExecutor,as_completed
import gzip
import hashlib
import json
import time

from lab import HERE,ROOT,RULESET,HangmaRules,RuleConfig,request_for,DecisionBudget
from continuation import source_hand
from continuation_notes import finish
from upgrade_persistent import upgrade_policy,UpgradePersistentPolicy,AuditedContinuation,ValueEvaluationEngine
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
from hangma_bot.simulation.engine import SimulationEngine

DIRECTORY=_project_file(_PROJECT_ROOT, HERE/'upgrade-persistent-v2')
INTERRUPTED=_project_file(_PROJECT_ROOT, HERE/'upgrade-persistent')


async def case_run(record):
    case=record['case'];rules=HangmaRules(RuleConfig(RULESET,1,False));raw=SimulationEngine(rules)
    engine=ValueEvaluationEngine(raw);base=ComparableHeuristicPolicyV2(monotonic=lambda:0)
    path=DIRECTORY/f'persistent-{case["case_id"]}.jsonl.gz'
    if path.exists():raise FileExistsError(path)
    totals=Counter();started=time.monotonic()
    previous=[json.loads(x) for x in gzip.open(_project_file(_PROJECT_ROOT, HERE/'pattern-progress'/path.name),'rt')]
    reused=[json.loads(x) for x in gzip.open(INTERRUPTED/path.name,'rt')]
    reuse_by_seed={r['seed']:r for r in reused}
    assert len(reused)==len(reuse_by_seed)
    assert [r['seed'] for r in reused]==[r['seed'] for r in previous[:len(reused)]]
    with gzip.open(path,'wt',encoding='utf8') as stream:
        for before in previous:
            seed=before['seed'];source=source_hand(case,seed)
            source_hash=hashlib.sha256(json.dumps(source,sort_keys=True).encode()).hexdigest()
            assert source_hash==before['source_sha256']
            if seed in reuse_by_seed:
                row=reuse_by_seed[seed]
                assert row['source_sha256']==source_hash and row['case_id']==case['case_id']
                assert row['baseline_action']==record['baseline'] and row['alternative_action']==record['alternative']
                assert len(row['arms'])==4
                for name,result in row['arms'].items():totals[name]+=result['score']
                stream.write(json.dumps(row,ensure_ascii=False)+'\n')
                continue
            world=raw.from_replay(source);obs=raw.frame(world).decisions[0].observation
            analysis=engine.rules.analyze(obs);request=request_for(obs,analysis)
            plan=await base.choose(request,DecisionBudget(10,11,12))
            assert plan.candidates[0].action_key==record['baseline']
            actions={c.action_key:c.action for c in analysis.legal_candidates}
            arms={}
            for action_label,key in [('base',record['baseline']),('seven',record['alternative'])]:
                for policy_label,policy in [('upgrade',upgrade_policy()),('combined',UpgradePersistentPolicy())]:
                    name=action_label+'_'+policy_label;audited=AuditedContinuation(policy)
                    result=await finish(engine,world,actions[key],audited,base)
                    result['hu_choices']=audited.hu_choices
                    result['hu_declines']=sum(c['action']!='hu' for c in audited.hu_choices)
                    arms[name]=result;totals[name]+=result['score']
            stream.write(json.dumps(dict(case_id=case['case_id'],seed=seed,source_sha256=source_hash,
                baseline_action=record['baseline'],alternative_action=record['alternative'],arms=arms),ensure_ascii=False)+'\n')
    return dict(case_id=case['case_id'],worlds=len(previous),hands=4*len(previous),
        reused_worlds=len(reused),new_hands=4*(len(previous)-len(reused)),
        mean_score={name:total/len(previous) for name,total in totals.items()},elapsed_seconds=time.monotonic()-started,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def worker(record):return asyncio.run(case_run(record))


def main():
    """复用全部条件世界和案例，不挑子集；结果不能称为新独立确认。"""
    previous=_project_file(_PROJECT_ROOT, HERE/'pattern-progress/persistent-freeze.json')
    old=json.loads(previous.read_text());DIRECTORY.mkdir(exist_ok=False)
    for name,expected in old['source_sha256'].items():
        assert hashlib.sha256((_project_file(_PROJECT_ROOT, ROOT/name)).read_bytes()).hexdigest()==expected,name
    interrupted=json.loads((INTERRUPTED/'persistent-freeze.json').read_text())
    for name,expected in interrupted['source_sha256'].items():
        p=INTERRUPTED/'attempt-runner.py' if name.endswith('/upgrade_persistent_probe.py') else _project_file(_PROJECT_ROOT, ROOT/name)
        assert hashlib.sha256(p.read_bytes()).hexdigest()==expected,name
    interruption=json.loads((INTERRUPTED/'interruption.json').read_text())
    for record in interruption['cases']:
        assert hashlib.sha256((INTERRUPTED/record['path']).read_bytes()).hexdigest()==record['sha256']
    manifest=dict(old)
    manifest.update(schema='upgrade-persistent-conditional/1',
        factors=dict(root_action=['baseline','closer_seven'],own_continuation=['v2_hu_upgrade_v1','persistent_seven_plus_upgrade']),
        purpose='复用704个条件开发世界的等胡交叉消融，非新独立确认',
        previous_manifest_sha256=hashlib.sha256(previous.read_bytes()).hexdigest(),
        resumed_from=dict(manifest_sha256=hashlib.sha256((INTERRUPTED/'persistent-freeze.json').read_bytes()).hexdigest(),
            cases=interruption['cases'],reason=interruption['reason'],policy_unchanged=True,
            source_snapshot=str((INTERRUPTED/'attempt-runner.py').relative_to(ROOT))),
        source_sha256={**old['source_sha256'],**{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [_project_file(_PROJECT_ROOT, HERE/'upgrade_persistent.py'),_project_file(_PROJECT_ROOT, HERE/'upgrade_persistent_probe.py'),_project_file(_PROJECT_ROOT, HERE/'continuation_notes.py')]}})
    (DIRECTORY/'persistent-freeze.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    results=[];errors=[];started=time.monotonic()
    with ProcessPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(worker,r):r['case']['case_id'] for r in manifest['cases']}
        for future in as_completed(futures):
            try:
                result=future.result();results.append(result);print(json.dumps(result,ensure_ascii=False),flush=True)
            except Exception as exc:
                error=dict(case_id=futures[future],error=type(exc).__name__+': '+str(exc));errors.append(error)
                print(json.dumps(error,ensure_ascii=False),flush=True)
    if errors:
        (DIRECTORY/'errors.json').write_text(json.dumps(errors,ensure_ascii=False,indent=2)+'\n')
        raise RuntimeError('条件续打仍有失败，不生成完成报告')
    result=dict(cases=sorted(results,key=lambda r:r['case_id']),elapsed_seconds=time.monotonic()-started,
        hands=sum(r['hands'] for r in results),worlds=sum(r['worlds'] for r in results),
        new_hands=sum(r['new_hands'] for r in results),reused_worlds=sum(r['reused_worlds'] for r in results))
    (DIRECTORY/'persistent-summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('finished',result['hands'],'hands',result['elapsed_seconds'],'seconds',flush=True)


if __name__=='__main__':main()
