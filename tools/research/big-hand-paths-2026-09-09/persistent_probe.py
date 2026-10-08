"""首步×后续策略的2×2条件续打；全部到真实终局，不使用截断零残值。"""

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
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
import gzip
import hashlib
import json
import time

from lab import HERE,ROOT,RULESET,HangmaRules,RuleConfig,request_for,DecisionBudget
from continuation import source_hand
from persistent_seven import PersistentSevenPolicy
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
from hangma_bot.simulation.engine import SimulationEngine
from hangma_bot.simulation.interface import SimulationChoice

DIRECTORY=_project_file(_PROJECT_ROOT, HERE/'pattern-progress')
SEEDS=range(1080000,1080064)


async def finish(engine,world,root_action,own_policy,opponents):
    """世界只传给公开接口；本人策略与三家V2分开，记录本人完整可见轨迹。"""
    frame=engine.frame(world)
    world=engine.advance(world,frame.revision,(SimulationChoice(frame.decisions[0].window_key,root_action),))
    trace=[]
    for step in range(5000):
        frame=engine.frame(world)
        if frame.blocked_reason:raise RuntimeError(frame.blocked_reason)
        if frame.final_scores is not None:
            result=engine.export_hand(world,1)
            assert sum(result['score_delta'])==0
            assert result['score_delta']==list(frame.final_scores)
            return dict(score=result['score_delta'][0],winner=result['winner_seat'],fan=result['fan'],
                details=result['details'],steps=step,trace=trace,
                result_hash=hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=False).encode()).hexdigest())
        choices=[]
        for decision in frame.decisions:
            obs=decision.observation;analysis=engine.rules.analyze(obs)
            request=replace(request_for(obs,analysis),window_key=decision.window_key)
            policy=own_policy if obs.seat==0 else opponents
            plan=await policy.choose(request,DecisionBudget(10,11,12))
            if plan.degraded_reasons:raise RuntimeError(str(plan.degraded_reasons))
            chosen=plan.candidates[0]
            if obs.seat==0:
                candidate=next(c for c in analysis.legal_candidates if c.action_key==chosen.action_key)
                f=candidate.facts
                trace.append(dict(seq=obs.consumed_seq if obs.consumed_seq is not None else obs.snapshot_seq,wall=obs.remaining_tile_count,action=chosen.action_key,
                    hand=[t.code for t in obs.my_hand],draw=None if obs.drawn_tile is None else obs.drawn_tile.code,
                    meld_count=len(obs.melds[0]),catch_play=obs.rule_state.catch_play,
                    shanten=None if f is None else f.shanten_after,
                    seven=None if f is None else f.seven_pairs_shanten_after,
                    enhanced=any(p.name=='七对持续续打消融' for p in chosen.score_parts)))
            choices.append(SimulationChoice(decision.window_key,chosen.action))
        world=engine.advance(world,frame.revision,tuple(choices))
    raise RuntimeError('续打超过5000步，不能记作流局')


async def case_run(record):
    """同一个未知世界执行四臂，首步与续打效应分开计算，不挑有利种子。"""
    case=record['case'];rules=HangmaRules(RuleConfig(RULESET,1,False));engine=SimulationEngine(rules)
    base=ComparableHeuristicPolicyV2(monotonic=lambda:0);teacher=PersistentSevenPolicy(monotonic=lambda:0)
    path=DIRECTORY/f'persistent-{case["case_id"]}.jsonl.gz'
    if path.exists():raise FileExistsError(path)
    totals=Counter();started=time.monotonic()
    with gzip.open(path,'wt',encoding='utf8') as stream:
        for seed in SEEDS:
            source=source_hand(case,seed);world=engine.from_replay(source)
            frame=engine.frame(world);assert len(frame.decisions)==1 and frame.decisions[0].observation.seat==0
            obs=frame.decisions[0].observation;analysis=rules.analyze(obs)
            request=request_for(obs,analysis)
            plan=await base.choose(request,DecisionBudget(10,11,12))
            assert plan.candidates[0].action_key==record['baseline']
            root_actions={c.action_key:c.action for c in analysis.legal_candidates}
            arms={}
            for action_label,action_key in [('base',record['baseline']),('seven',record['alternative'])]:
                for policy_label,policy in [('v2',base),('persistent',teacher)]:
                    name=action_label+'_'+policy_label
                    arms[name]=await finish(engine,world,root_actions[action_key],policy,base)
                    totals[name]+=arms[name]['score']
            stream.write(json.dumps(dict(case_id=case['case_id'],seed=seed,
                source_sha256=hashlib.sha256(json.dumps(source,sort_keys=True).encode()).hexdigest(),
                baseline_action=record['baseline'],alternative_action=record['alternative'],arms=arms),ensure_ascii=False)+'\n')
    return dict(case_id=case['case_id'],worlds=len(SEEDS),hands=4*len(SEEDS),
        mean_score={name:total/len(SEEDS) for name,total in totals.items()},elapsed_seconds=time.monotonic()-started,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def worker(record):return asyncio.run(case_run(record))


def main():
    """冻结全部11个非听牌冲突案例、64个条件世界、四臂；不是自然桌赛确认。"""
    input_path=DIRECTORY/'all-opening.jsonl.gz'
    rows=[json.loads(line) for line in gzip.open(input_path,'rt')]
    selected=[]
    for r in rows:
        if r['closer_seven'] and r['baseline_facts']['shanten']>0:
            alt=min(r['closer_seven'],key=lambda a:(a['seven'],a['shanten'],-sum(a['useful'].values()),a['action']))
            selected.append(dict(case=r['case'],baseline=r['baseline'],alternative=alt['action']))
    assert len(selected)==11
    manifest_path=DIRECTORY/'persistent-freeze.json'
    if manifest_path.exists():raise FileExistsError(manifest_path)
    manifest=dict(schema='persistent-conditional/1',cases=selected,seed_range=[min(SEEDS),max(SEEDS)],
        rule_config=dict(you_cai_bi_kao=False,base_score=1),own_seat=0,initial_dealer_seat=0,
        sampling='uniform_unseen_full_world',opponents='weighted_heuristic_v2',
        factors=dict(root_action=['baseline','closer_seven'],own_continuation=['v2','persistent_seven']),
        purpose='条件续打敏感性；非自然发牌效果、非最优路线价值、非发布门禁',
        stopping='全部11案例×64世界×4臂；失败保留部分日志且不计算完整效果',
        source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [_project_file(_PROJECT_ROOT, HERE/'persistent_probe.py'),_project_file(_PROJECT_ROOT, HERE/'persistent_seven.py'),_project_file(_PROJECT_ROOT, HERE/'continuation.py'),_project_file(_PROJECT_ROOT, HERE/'lab.py'),
                *sorted((_project_file(_PROJECT_ROOT, ROOT/'src/hangma_bot')).glob('**/*.py'))]},
        input_sha256=hashlib.sha256(input_path.read_bytes()).hexdigest())
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    results=[];started=time.monotonic()
    with ProcessPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(worker,r) for r in selected]
        for future in as_completed(futures):
            result=future.result();results.append(result)
            print(json.dumps(result,ensure_ascii=False),flush=True)
    summary=dict(cases=sorted(results,key=lambda r:r['case_id']),elapsed_seconds=time.monotonic()-started,
        hands=sum(r['hands'] for r in results),worlds=sum(r['worlds'] for r in results))
    (DIRECTORY/'persistent-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print('finished',summary['hands'],'hands',summary['elapsed_seconds'],'seconds',flush=True)


if __name__=='__main__':main()
