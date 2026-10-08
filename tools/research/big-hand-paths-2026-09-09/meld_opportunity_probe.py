"""补全吃和暗杠的条件机会成本；不使用任何未来指定进张选择首步。"""

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
from dataclasses import replace
import gzip
import hashlib
import json
import random
import time

from lab import HERE,ROOT,RULESET,HangmaRules,RuleConfig,Tile,request_for,DecisionBudget
from continuation import source_hand
from conditional_play import complete
from upgrade_persistent import upgrade_policy,ValueEvaluationEngine
from hangma_bot.kernel.actions import Discard,Pass
from hangma_bot.application.audit_codec import decision_request_to_json
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
from hangma_bot.simulation.engine import SimulationEngine
from hangma_bot.simulation.interface import SimulationChoice

DIRECTORY=_project_file(_PROJECT_ROOT, HERE/'meld-opportunity')
CASES=(
    dict(case_id='gang-E',kind='gang',hand='5b 东 东 东 中 白 8w 5t 白 8w 东 3t 白 4t'.split(),
         expected='gang:concealed:东',alternative='best_discard'),
    dict(case_id='gang-seven',kind='gang',hand='1w 1w 1w 1w 3w 3w 5b 5b 7b 7b 2t 2t 东 南'.split(),
         expected='discard:东',alternative='gang:concealed:1w'),
    dict(case_id='gang-standard',kind='gang',hand='1w 1w 1w 1w 2w 3w 4w 5w 6w 7w 8w 9w 东 南'.split(),
         expected='discard:东',alternative='gang:concealed:1w'),
    dict(case_id='chi-pairs',kind='chi',hand='1w 1w 2w 2w 3w 3w 5b 5b 7b 7b 8b 9b 白'.split(),
         offer='6b',expected='chi:5b,6b,7b',alternative='pass'),
    dict(case_id='chi-seven',kind='chi',hand='1w 1w 2w 2w 3w 3w 5b 5b 7b 7b 9t 9t 东'.split(),
         offer='4w',expected='pass',alternative='chi:2w,3w,4w'))


def root(case,seed):
    """吃窗口先执行庄家弃牌与碰窗口全部合法过；暗杠窗口为自然开局。

吃案例抽样条件明确包含他家持有指定弃牌并放弃碰，不估计这些行为
概率。抽样的隐藏牌分配不进入首步选择；真实过程全经公开模拟接口。
"""
    hand=case['hand']+([case['offer']] if case['kind']=='chi' else [])
    source=source_hand(dict(case_id=case['case_id'],initial_hand=hand),seed)
    source['initial']['world_payload']['dealer_seat']=3 if case['kind']=='chi' else 0
    raw=SimulationEngine(HangmaRules(RuleConfig(RULESET,1,False)))
    world=raw.from_replay(source)
    if case['kind']=='chi':
        frame=raw.frame(world)
        world=raw.advance(world,frame.revision,(SimulationChoice(frame.decisions[0].window_key,Discard(Tile(case['offer']))),))
        frame=raw.frame(world)
        assert all(d.observation.phase=='response_peng' for d in frame.decisions)
        world=raw.advance(world,frame.revision,tuple(SimulationChoice(d.window_key,Pass()) for d in frame.decisions))
    return source,raw,world


async def run_world(case,seed):
    source,raw,world=root(case,seed)
    engine=ValueEvaluationEngine(raw)
    decision=next(d for d in raw.frame(world).decisions if d.observation.seat==0)
    request=replace(request_for(decision.observation,engine.rules.analyze(decision.observation)),window_key=decision.window_key)
    plan=await upgrade_policy().choose(request,DecisionBudget(10,11,12))
    assert plan.candidates[0].action_key==case['expected']
    alternative=case['alternative']
    if alternative=='best_discard':
        alternative=next(c.action_key for c in plan.candidates if isinstance(c.action,Discard))
    assert alternative!=case['expected'] and any(c.action_key==alternative for c in plan.candidates)
    base=ComparableHeuristicPolicyV2(monotonic=lambda:0)
    arms={}
    for name,key in [('baseline',case['expected']),('alternative',alternative)]:
        arms[name]=await complete(engine,world,upgrade_policy(),base,key)
    return dict(case_id=case['case_id'],seed=seed,baseline_action=case['expected'],alternative_action=alternative,
        source_sha256=hashlib.sha256(json.dumps(source,sort_keys=True).encode()).hexdigest(),
        root_request=decision_request_to_json(request),arms=arms,delta=arms['alternative']['score']-arms['baseline']['score'])


def summarize(rows):
    differences=[r['delta'] for r in rows]
    rng=random.Random(1160999)
    draws=sorted(sum(rng.choices(differences,k=len(rows)))/len(rows) for _ in range(10000))
    arms={}
    for name in ('baseline','alternative'):
        values=[r['arms'][name] for r in rows]
        arms[name]=dict(mean_net=sum(r['score'] for r in values)/len(rows),own_hu=sum(r['winner']==0 for r in values),
            details=dict(Counter('·'.join(r['details']) for r in values if r['winner']==0)))
    return dict(worlds=len(rows),hands=2*len(rows),baseline=rows[0]['baseline_action'],alternative=rows[0]['alternative_action'],
        mean_delta=sum(differences)/len(rows),interval95=[draws[249],draws[9749]],arms=arms)


async def main():
    DIRECTORY.mkdir(exist_ok=False)
    sources=[_project_file(_PROJECT_ROOT, HERE/n) for n in ('meld_opportunity_probe.py','conditional_play.py','continuation.py','continuation_notes.py',
                             'lab.py','upgrade_persistent.py','persistent_seven.py')]
    sources+=sorted((_project_file(_PROJECT_ROOT, ROOT/'src/hangma_bot')).rglob('*.py'))
    sources+=sorted((_project_file(_PROJECT_ROOT, ROOT/'src/hangma_bot/hangma')).glob('*.so'))
    manifest=dict(schema='meld-opportunity/1',cases=CASES,seed_ranges=dict(gang=[1160000,1160063],chi=[1170000,1170063]),
        own_seat=0,wall=83,you_cai_bi_kao=False,opponents='weighted_heuristic_v2',own_continuation='v2_hu_upgrade_v1',
        stopping='五个固定案例各64未知世界，两个首步均到单局真实终局；不追加样本追求显著',
        limitation='条件开发；吃窗口还条件于庄家弃牌及所有碰响应过，不作这些行为的自然概率声明',
        source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
    (DIRECTORY/'freeze.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    started=time.monotonic()
    results={}
    for case in CASES:
        path=DIRECTORY/(case['case_id']+'.jsonl.gz')
        seeds=manifest['seed_ranges'][case['kind']]
        rows=[]
        with gzip.open(path,'xt',encoding='utf8') as stream:
            for seed in range(seeds[0],seeds[1]+1):
                row=await run_world(case,seed)
                rows.append(row)
                stream.write(json.dumps(row,ensure_ascii=False)+'\n')
        results[case['case_id']]={**summarize(rows),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        print(case['case_id'],json.dumps(results[case['case_id']],ensure_ascii=False),flush=True)
    (DIRECTORY/'summary.json').write_text(json.dumps(dict(cases=results,elapsed_seconds=time.monotonic()-started),ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':
    asyncio.run(main())
