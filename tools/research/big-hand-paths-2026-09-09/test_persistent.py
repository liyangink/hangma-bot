"""续打实验的信息边界、安全计划和确定性；不把某条未来结果写成必胜断言。"""

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
from dataclasses import asdict, replace

import pytest

from lab import observation,HangmaRules,RuleConfig,RULESET,request_for,DecisionBudget,generate
from persistent_seven import PersistentSevenPolicy
from persistent_probe import finish
from continuation import finish as previous_finish,source_hand
from mutations import generated_cases
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
from hangma_bot.simulation.engine import SimulationEngine


def request(hand='5t 2t 2w 发 5t 白 发 2w 2t 3w 4b 4w 4t 5t'):
    obs=observation(hand.split(),case_id='persistent-test',wall=83,dealer=0)
    rules=HangmaRules(RuleConfig(RULESET,1,False))
    return request_for(obs,rules.analyze(obs))


async def plans(req):
    base=await ComparableHeuristicPolicyV2(monotonic=lambda:0).choose(req,DecisionBudget(10,11,12))
    new=await PersistentSevenPolicy(monotonic=lambda:0).choose(req,DecisionBudget(10,11,12))
    return base,new


def test_persistent_route_uses_complete_legal_plan_and_can_differ_from_v2():
    req=request();base,new=asyncio.run(plans(req))
    assert base.candidates[0].action_key!=new.candidates[0].action_key
    assert {c.action_key for c in new.candidates}=={c.action_key for c in base.candidates}
    assert any(c.is_emergency for c in new.candidates)
    assert all(c.total_score==sum(p.value for p in c.score_parts) for c in new.candidates)
    assert asyncio.run(plans(req))[1]==new


@pytest.mark.parametrize('wall',[None,20,24])
def test_short_or_unknown_wall_does_not_force_a_route(wall):
    req=request();req=replace(req,observation=replace(req.observation,remaining_tile_count=wall))
    base,new=asyncio.run(plans(req));assert base==new


def test_missing_pattern_facts_returns_the_entire_v2_plan():
    req=request();req=replace(req,rules=replace(req.rules,legal_candidates=tuple(
        replace(c,facts=replace(c.facts,seven_pairs_useful_tiles=None)) if c.facts else c
        for c in req.rules.legal_candidates)))
    base,new=asyncio.run(plans(req));assert base==new


def test_actual_legal_hu_is_not_delayed_by_the_continuation_ablation():
    base,new=asyncio.run(plans(request('1w 2w 3w 4w 5w 6w 7b 8b 9b 2t 3t 4t 白 东')))
    assert base.candidates[0].action_key=='hu'
    assert base==new


def test_split_own_opponent_policies_preserves_old_v2_full_continuation():
    async def run():
        case=asdict(next(c for c in generated_cases() if c.case_id=='mutation-1-82'))
        engine=SimulationEngine(HangmaRules(RuleConfig(RULESET,1,False)))
        world=engine.from_replay(source_hand(case,1050000))
        obs=engine.frame(world).decisions[0].observation
        req=request_for(obs,engine.rules.analyze(obs));base=ComparableHeuristicPolicyV2(monotonic=lambda:0)
        plan=await base.choose(req,DecisionBudget(10,11,12));action=plan.candidates[0].action
        old=await previous_finish(engine,world,action,base)
        new=await finish(engine,world,action,base,base)
        assert old['result_hash']==new['result_hash']
        assert all(t['enhanced'] is False for t in new['trace'])
    asyncio.run(run())


def test_generator_refactor_preserves_all_originally_selected_opening_inputs():
    import json
    from lab import HERE
    generated={c.case_id:asdict(c) for c in generated_cases()}
    assert len(generated)==2525
    old=json.loads((_project_file(_PROJECT_ROOT, HERE/'mutation-opening.json')).read_text())
    for row in old['cases']:
        # 元组转JSON数组只为与已封存文件比较，不修改原案例。
        assert json.loads(json.dumps(generated[row['case']['case_id']]))==row['case']
