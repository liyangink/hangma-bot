"""有限等待只改变明确可比听牌组，并保持已有胡牌增强与不完整事实回退。"""

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
from dataclasses import replace
import math

from finite_wait import hit_weight
from finite_wait_guarded import GuardedFiniteWaitingPolicy as FiniteWaitingPolicy
from response_probe import CASES,root
from upgrade_persistent import ValueEvaluationEngine,upgrade_policy
from lab import request_for,DecisionBudget


def test_hit_weight_matches_no_replacement_probability_and_single_draw():
    assert math.isclose(hit_weight(10,3,1,0.8),0.3*0.8)
    assert math.isclose(hit_weight(10,3,4,1),1-math.comb(7,4)/math.comb(10,4))
    assert hit_weight(10,10,10,1)==1
    assert hit_weight(10,0,10,1)==0


def test_longer_wait_changes_seven_ready_response_but_not_nonready_comparison():
    async def run():
        for case,expected in [(CASES[0],'peng:3t'),(CASES[2],'pass')]:
            _,raw,world=root(case,1130000)
            obs=next(d.observation for d in raw.frame(world).decisions if d.observation.seat==0)
            engine=ValueEvaluationEngine(raw)
            req=request_for(obs,engine.rules.analyze(obs))
            plan=await FiniteWaitingPolicy().choose(req,DecisionBudget(10,11,12))
            assert plan.candidates[0].action_key==expected
            assert {c.action_key for c in plan.candidates}=={c.action_key for c in req.rules.legal_candidates}
            missing=replace(req,observation=replace(obs,remaining_tile_count=None))
            assert await FiniteWaitingPolicy().choose(missing,DecisionBudget(10,11,12))==await upgrade_policy().choose(missing,DecisionBudget(10,11,12))
            no_values=replace(req,rules=replace(req.rules,legal_candidates=tuple(replace(c,value_facts=None) for c in req.rules.legal_candidates)))
            assert await FiniteWaitingPolicy().choose(no_values,DecisionBudget(10,11,12))==await upgrade_policy().choose(no_values,DecisionBudget(10,11,12))
    asyncio.run(run())


def test_current_hu_upgrade_discard_is_not_reranked_as_an_ordinary_wait():
    from lab import observation,HangmaRules,RuleConfig,RULESET,ValueAnalysisLimits
    async def run():
        hand='1w 1w 3w 3w 5w 5w 2b 2b 4b 4b 6b 6b 8t 白'.split()
        obs=observation(hand,case_id='finite-hu-guard',wall=83,dealer=0)
        rules=HangmaRules(RuleConfig(RULESET,1,False))
        req=request_for(obs,rules.analyze(obs,value_limits=ValueAnalysisLimits()))
        old=await upgrade_policy().choose(req,DecisionBudget(10,11,12))
        assert old.candidates[0].action_key=='discard:8t'
        assert await FiniteWaitingPolicy().choose(req,DecisionBudget(10,11,12))==old
    asyncio.run(run())
