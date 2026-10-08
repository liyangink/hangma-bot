"""等胡组合只装配现有规则/策略；真实可胡案例核对终点升级未被覆盖。"""

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
from dataclasses import asdict

from lab import RULESET,HangmaRules,RuleConfig,observation,request_for,DecisionBudget,ValueAnalysisLimits
from mutations import generated_cases
from continuation import source_hand
from persistent_probe import finish
from continuation_notes import finish as finish_with_notes,unexpected_notes,NORMAL_CATCH_NOTE
from persistent_seven import PersistentSevenPolicy
from upgrade_persistent import upgrade_policy,UpgradePersistentPolicy,ValueEvaluationEngine
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
from hangma_bot.simulation.engine import SimulationEngine


def test_seven_pairs_hu_can_reserve_white_for_baotou_without_being_overridden():
    async def run():
        hand='1w 1w 3w 3w 5w 5w 2b 2b 4b 4b 6b 6b 8t 白'.split()
        obs=observation(hand,case_id='seven-to-baotou',wall=83,dealer=0)
        rules=HangmaRules(RuleConfig(RULESET,1,False))
        analysis=rules.analyze(obs,value_limits=ValueAnalysisLimits());req=request_for(obs,analysis)
        a=await upgrade_policy().choose(req,DecisionBudget(10,11,12))
        b=await UpgradePersistentPolicy().choose(req,DecisionBudget(10,11,12))
        assert a==b and a.candidates[0].action_key=='discard:8t'
        hu=next(c for c in analysis.legal_candidates if c.action_key=='hu')
        wait=next(c for c in analysis.legal_candidates if c.action_key=='discard:8t')
        assert hu.value_facts.immediate_settlement.score_delta[0]==48
        assert all(r.conditional_settlement.score_delta[0]==96 and r.conditions.baotou for r in wait.value_facts.routes)
    asyncio.run(run())


def test_combination_uses_the_same_persistent_policy_before_legal_hu():
    async def run():
        case=next(c for c in generated_cases() if c.case_id=='mutation-1-82')
        obs=observation(case.initial_hand,case_id=case.case_id,wall=83,dealer=0)
        rules=HangmaRules(RuleConfig(RULESET,1,False))
        request=request_for(obs,rules.analyze(obs,value_limits=ValueAnalysisLimits()))
        assert all(c.action_key!='hu' for c in request.rules.legal_candidates)
        a=await PersistentSevenPolicy(monotonic=lambda:0).choose(request,DecisionBudget(10,11,12))
        b=await UpgradePersistentPolicy().choose(request,DecisionBudget(10,11,12))
        assert a==b
    asyncio.run(run())


def test_value_facts_adapter_does_not_change_v2_full_world_continuation():
    async def run():
        case=asdict(next(c for c in generated_cases() if c.case_id=='mutation-1-82'))
        raw=SimulationEngine(HangmaRules(RuleConfig(RULESET,1,False)))
        wrapped=ValueEvaluationEngine(raw);world=raw.from_replay(source_hand(case,1050000))
        obs=raw.frame(world).decisions[0].observation
        request=request_for(obs,raw.rules.analyze(obs));base=ComparableHeuristicPolicyV2(monotonic=lambda:0)
        action=(await base.choose(request,DecisionBudget(10,11,12))).candidates[0].action
        old=await finish(raw,world,action,base,base)
        new=await finish(wrapped,world,action,base,base)
        assert old==new
        assert await finish_with_notes(wrapped,world,action,base,base)==old
    asyncio.run(run())


def test_unknown_or_mismatched_notes_are_not_silently_ignored():
    from dataclasses import replace
    async def run():
        case=next(c for c in generated_cases() if c.case_id=='mutation-1-82')
        obs=observation(case.initial_hand,case_id=case.case_id,wall=83,dealer=0)
        rules=HangmaRules(RuleConfig(RULESET,1,False));req=request_for(obs,rules.analyze(obs))
        plan=await ComparableHeuristicPolicyV2(monotonic=lambda:0).choose(req,DecisionBudget(10,11,12))
        note_plan=replace(plan,degraded_reasons=(NORMAL_CATCH_NOTE,'未知错误'))
        assert unexpected_notes(note_plan,req)==note_plan.degraded_reasons
        catch_req=replace(req,observation=replace(obs,rule_state=replace(obs.rule_state,catch_play=True)))
        assert unexpected_notes(note_plan,catch_req)==('未知错误',)
    asyncio.run(run())


def test_real_interrupted_world_completes_and_keeps_catch_play_audit():
    async def run():
        case=asdict(next(c for c in generated_cases() if c.case_id=='mutation-1-82'))
        raw=SimulationEngine(HangmaRules(RuleConfig(RULESET,1,False)));engine=ValueEvaluationEngine(raw)
        world=raw.from_replay(source_hand(case,1080030));obs=raw.frame(world).decisions[0].observation
        analysis=engine.rules.analyze(obs);base=ComparableHeuristicPolicyV2(monotonic=lambda:0)
        results=[]
        for key in ['discard:2t','discard:4t']:
            action=next(c.action for c in analysis.legal_candidates if c.action_key==key)
            for policy in [upgrade_policy(),UpgradePersistentPolicy()]:
                results.append(await finish_with_notes(engine,world,action,policy,base))
        notes=[note for result in results for note in result.get('normal_audit_notes',[])]
        assert notes and all(n['reasons']==[NORMAL_CATCH_NOTE] for n in notes)
    asyncio.run(run())
