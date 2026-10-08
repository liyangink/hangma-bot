"""三个对手已听牌的反向压力条件；他家暗牌只用于构造世界，不提供给策略。"""

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
import gzip
import hashlib
import json
import random
import time

from lab import HERE, ROOT, RULESET, HangmaRules, RuleConfig, Tile, CANONICAL_TILE_ORDER
from continuation import source_hand
from conditional_play import complete
from upgrade_persistent import upgrade_policy, ValueEvaluationEngine
from piao_bridge_probe import cases, summarize
from hangma_bot.hangma.hand_analysis import analyse_hand
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
from hangma_bot.simulation.engine import SimulationEngine

DIRECTORY=_project_file(_PROJECT_ROOT, HERE/'piao-bridge-stress')
SEEDS=range(1120000,1120128)
OPPONENT_HANDS=tuple(s.split() for s in (
    '1b 1b 1b 2b 3b 4b 5b 6b 7b 8b 8b 9b 9b',
    '1t 1t 1t 2t 3t 4t 5t 6t 7t 8t 8t 9t 9t',
    '6w 6w 6w 7w 7w 7w 8w 8w 8w 9w 9w 发 发'))


def stressed_source(case,seed):
    """固定四家已知条件后仅随机牌墙，保持每种牌四张和83张物理剩余。"""
    for hand in OPPONENT_HANDS:
        assert analyse_hand(tuple(Tile(c) for c in hand),0).shanten==0
    used=Counter(case['initial_hand']+[c for hand in OPPONENT_HANDS for c in hand])
    assert max(used.values())<=4
    wall=[c for c in CANONICAL_TILE_ORDER for _ in range(4-used[c])]
    assert len(wall)==83
    random.Random(int(hashlib.sha256(f'{case["case_id"]}:{seed}:opponents-ready'.encode()).hexdigest(),16)).shuffle(wall)
    source=source_hand(case,seed)
    payload=source['initial']['world_payload']
    payload['hands']=[case['initial_hand'][:-1],*OPPONENT_HANDS]
    payload['wall']=wall
    return source


async def run_world(case,seed):
    source=stressed_source(case,seed)
    raw=SimulationEngine(HangmaRules(RuleConfig(RULESET,1,False)))
    engine=ValueEvaluationEngine(raw)
    world=raw.from_replay(source)
    base=ComparableHeuristicPolicyV2(monotonic=lambda:0)
    arms={}
    for label,key in [('hu','hu'),('bridge','discard:白')]:
        arms[label]=await complete(engine,world,upgrade_policy(),base,key)
    assert arms['hu']['trace'][0]['policy_action']=='hu'
    return dict(case_id=case['case_id'],seed=seed,
        source_sha256=hashlib.sha256(json.dumps(source,sort_keys=True).encode()).hexdigest(),
        immediate_score=arms['hu']['score'],arms=arms,delta=arms['bridge']['score']-arms['hu']['score'])


async def main():
    DIRECTORY.mkdir(exist_ok=False)
    sources=[_project_file(_PROJECT_ROOT, HERE/n) for n in ('piao_bridge_stress.py','piao_bridge_probe.py','conditional_play.py','continuation.py',
                             'continuation_notes.py','lab.py','upgrade_persistent.py','persistent_seven.py')]
    sources+=sorted((_project_file(_PROJECT_ROOT, ROOT/'src/hangma_bot')).rglob('*.py'))
    sources+=sorted((_project_file(_PROJECT_ROOT, ROOT/'src/hangma_bot/hangma')).glob('*.so'))
    manifest=dict(schema='piao-bridge-stress/1',cases=cases(),opponent_hands=OPPONENT_HANDS,
        seed_range=[SEEDS.start,SEEDS.stop-1],you_cai_bi_kao=False,wall=83,own_seat=0,dealer_seat=0,
        sampling='uniform_wall_given_all_four_initial_hands',own_continuation='v2_hu_upgrade_v1',
        opponents='weighted_heuristic_v2',stopping='3案例各128世界，两首步至真实单局终局',
        limitation='三个对手已听牌的压力条件；不估计其自然发生概率，不与均匀他家样本混合求均值',
        source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
    (DIRECTORY/'freeze.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    started=time.monotonic()
    results={}
    for case in manifest['cases']:
        path=DIRECTORY/(case['case_id']+'.jsonl.gz')
        rows=[]
        with gzip.open(path,'xt',encoding='utf8') as stream:
            for seed in SEEDS:
                row=await run_world(case,seed)
                rows.append(row)
                stream.write(json.dumps(row,ensure_ascii=False)+'\n')
        result=summarize(rows)
        result['own_white_discards_including_root']=result.pop('followup_white_discards')
        results[case['case_id']]={**result,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        print(case['case_id'],json.dumps(results[case['case_id']],ensure_ascii=False),flush=True)
    (DIRECTORY/'summary.json').write_text(json.dumps(dict(cases=results,elapsed_seconds=time.monotonic()-started),
                                                   ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':
    asyncio.run(main())
