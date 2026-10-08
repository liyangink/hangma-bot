"""在真实发牌与合法弃牌后，比较碰/过的完整条件续打，不截断未来价值。"""

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
import gzip
import hashlib
import json
import time

from lab import HERE, ROOT, RULESET, HangmaRules, RuleConfig, Tile, request_for, DecisionBudget, describe
from continuation import source_hand
from conditional_play import complete
from upgrade_persistent import upgrade_policy, ValueEvaluationEngine
from piao_bridge_probe import summarize
from hangma_bot.kernel.actions import Discard
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
from hangma_bot.simulation.engine import SimulationEngine
from hangma_bot.simulation.interface import SimulationChoice
from hangma_bot.application.audit_codec import decision_request_to_json

DIRECTORY=_project_file(_PROJECT_ROOT, HERE/'response-opportunity')
CASES=(
    dict(case_id='response-luxury-quad',hand='6t 4b 9t 6t 3t 6t 2t 8t 2t 3t 6t 9t 7t'.split(),offer='3t',
         purpose='保留自然四张与七对一步，或碰到普通型听牌'),
    dict(case_id='response-D',hand='西 5b 发 7b 发 5b 3t 7b 6b 6b 白 西 5t'.split(),offer='发',
         purpose='历史一次摸牌价值偏好过的手形，重新构造合法开局响应'),
    dict(case_id='response-G',hand='9t 9w 5b 南 白 8t 南 9t 9b 白 9w 9b 9t'.split(),offer='南',
         purpose='历史一次摸牌价值仍偏好碰的对照手形'))
SEEDS=range(1130000,1130128)


def root(case,seed):
    """固定本人十三张及庄家此次弃牌，其他暗牌/牌墙均匀；这是条件开局。

抽样条件包含庄家持有并打出指定牌，不估计对手选择该弃牌的概率。
不冒充原牌局中期的同窗口反事实。原始牌谱是完整136张起点。
"""
    source=source_hand(dict(case_id=case['case_id'],initial_hand=case['hand']+[case['offer']]),seed)
    source['initial']['world_payload']['dealer_seat']=1
    raw=SimulationEngine(HangmaRules(RuleConfig(RULESET,1,False)))
    world=raw.from_replay(source)
    frame=raw.frame(world)
    assert len(frame.decisions)==1 and frame.decisions[0].observation.seat==1
    action=Discard(Tile(case['offer']))
    assert any(c.action==action for c in raw.rules.analyze(frame.decisions[0].observation).legal_candidates)
    world=raw.advance(world,frame.revision,(SimulationChoice(frame.decisions[0].window_key,action),))
    return source,raw,world


async def run_world(case,seed):
    source,raw,world=root(case,seed)
    engine=ValueEvaluationEngine(raw)
    obs=next(d.observation for d in raw.frame(world).decisions if d.observation.seat==0)
    analysis=engine.rules.analyze(obs)
    request=request_for(obs,analysis)
    policy=upgrade_policy()
    plan=await policy.choose(request,DecisionBudget(10,11,12))
    actions={c.action_key:c for c in analysis.legal_candidates}
    claim='peng:'+case['offer']
    assert claim in actions and 'pass' in actions
    base=ComparableHeuristicPolicyV2(monotonic=lambda:0)
    arms={}
    for label,key in [('peng',claim),('pass','pass')]:
        arms[label]=await complete(engine,world,upgrade_policy(),base,key)
    return dict(case_id=case['case_id'],seed=seed,baseline_action=plan.candidates[0].action_key,
        source_sha256=hashlib.sha256(json.dumps(source,sort_keys=True).encode()).hexdigest(),
        root_facts={key:describe(actions[key],obs) for key in (claim,'pass')},
        root_request=decision_request_to_json(request),arms=arms,delta=arms['pass']['score']-arms['peng']['score'])


def result_summary(rows):
    """每个固定案例按完整世界计算配对区间；不混成自然完整桌赛指标。"""
    from collections import Counter
    import random
    differences=[r['delta'] for r in rows]
    rng=random.Random(1130999)
    bootstrap=sorted(sum(rng.choices(differences,k=len(rows)))/len(rows) for _ in range(10000))
    results={}
    for key in ('peng','pass'):
        arms=[r['arms'][key] for r in rows]
        results[key]=dict(mean_net=sum(r['score'] for r in arms)/len(rows),
            own_hu=sum(r['winner']==0 for r in arms),opponent_hu=sum(r['winner'] not in (None,0) for r in arms),
            own_fan_counts=dict(Counter(r['fan'] for r in arms if r['winner']==0)),
            own_details=dict(Counter('·'.join(r['details']) for r in arms if r['winner']==0)))
    return dict(worlds=len(rows),hands=2*len(rows),baseline_actions=dict(Counter(r['baseline_action'] for r in rows)),
        pass_minus_peng_mean=sum(differences)/len(rows),interval95=[bootstrap[249],bootstrap[9749]],arms=results)


async def main():
    DIRECTORY.mkdir(exist_ok=False)
    sources=[_project_file(_PROJECT_ROOT, HERE/n) for n in ('response_probe.py','conditional_play.py','continuation.py','continuation_notes.py',
                             'lab.py','upgrade_persistent.py','persistent_seven.py','piao_bridge_probe.py')]
    sources+=sorted((_project_file(_PROJECT_ROOT, ROOT/'src/hangma_bot')).rglob('*.py'))
    sources+=sorted((_project_file(_PROJECT_ROOT, ROOT/'src/hangma_bot/hangma')).glob('*.so'))
    manifest=dict(schema='response-opportunity/1',cases=CASES,seed_range=[SEEDS.start,SEEDS.stop-1],
        you_cai_bi_kao=False,own_seat=0,dealer_seat=1,wall=83,base_score=1,
        sampling='uniform_unseen_given_own_hand_and_dealer_offer',own_continuation='v2_hu_upgrade_v1',
        opponents='weighted_heuristic_v2',stopping='三个固定案例各128世界，两首步完整终局；不追加种子追求显著',
        limitation='条件开局开发，非原窗口反事实，非自然桌赛强度证明；不估计庄家弃牌概率',
        source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
    (DIRECTORY/'freeze.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    started=time.monotonic()
    results={}
    for case in CASES:
        rows=[]
        path=DIRECTORY/(case['case_id']+'.jsonl.gz')
        with gzip.open(path,'xt',encoding='utf8') as stream:
            for seed in SEEDS:
                row=await run_world(case,seed)
                rows.append(row)
                stream.write(json.dumps(row,ensure_ascii=False)+'\n')
        results[case['case_id']]={**result_summary(rows),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        print(case['case_id'],json.dumps(results[case['case_id']],ensure_ascii=False),flush=True)
    (DIRECTORY/'summary.json').write_text(json.dumps(dict(cases=results,elapsed_seconds=time.monotonic()-started),
                                                   ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':
    asyncio.run(main())
