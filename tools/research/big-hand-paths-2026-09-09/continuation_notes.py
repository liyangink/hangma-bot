"""允许已确认正常审计说明的续打验收；未知说明和真实降级继续失败。

独立于已封存 persistent_probe.finish，保留原实验的源码可验证性。
只改变实验验收/记录，不改变观察、候选、策略或世界推进。
"""

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
from dataclasses import replace
import hashlib
import json

from lab import request_for,DecisionBudget
from hangma_bot.hangma.interface import RuleCompleteness
from hangma_bot.simulation.interface import SimulationChoice

NORMAL_CATCH_NOTE='抓打圈生效：排序仅在规则允许的硬约束候选内进行'


def unexpected_notes(plan,request):
    """仅豁免与完整抓打圈观察一致的固定正常说明，不静默过滤任何其他原因。"""
    normal=(request.observation.rule_state.catch_play
            and request.rules.completeness is RuleCompleteness.COMPLETE and not request.rules.issues)
    return tuple(n for n in plan.degraded_reasons if not(normal and n==NORMAL_CATCH_NOTE))


async def finish(engine,world,root_action,own_policy,opponents):
    """经公开模拟接口到真实终局；所有正常说明仍保存在本人/对手旁路审计中。"""
    frame=engine.frame(world)
    world=engine.advance(world,frame.revision,(SimulationChoice(frame.decisions[0].window_key,root_action),))
    trace=[];audit_notes=[]
    for step in range(5000):
        frame=engine.frame(world)
        if frame.blocked_reason:raise RuntimeError(frame.blocked_reason)
        if frame.final_scores is not None:
            result=engine.export_hand(world,1)
            assert sum(result['score_delta'])==0
            assert result['score_delta']==list(frame.final_scores)
            output=dict(score=result['score_delta'][0],winner=result['winner_seat'],fan=result['fan'],
                details=result['details'],steps=step,trace=trace,
                result_hash=hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=False).encode()).hexdigest())
            if audit_notes:output['normal_audit_notes']=audit_notes
            return output
        choices=[]
        for decision in frame.decisions:
            obs=decision.observation;analysis=engine.rules.analyze(obs)
            request=replace(request_for(obs,analysis),window_key=decision.window_key)
            policy=own_policy if obs.seat==0 else opponents
            plan=await policy.choose(request,DecisionBudget(10,11,12))
            failures=unexpected_notes(plan,request)
            if failures:raise RuntimeError(str(failures))
            if plan.degraded_reasons:
                audit_notes.append(dict(seat=obs.seat,seq=request.trigger_seq,reasons=list(plan.degraded_reasons)))
            chosen=plan.candidates[0]
            if obs.seat==0:
                candidate=next(c for c in analysis.legal_candidates if c.action_key==chosen.action_key)
                f=candidate.facts
                trace.append(dict(seq=obs.consumed_seq if obs.consumed_seq is not None else obs.snapshot_seq,
                    wall=obs.remaining_tile_count,action=chosen.action_key,
                    hand=[t.code for t in obs.my_hand],draw=None if obs.drawn_tile is None else obs.drawn_tile.code,
                    meld_count=len(obs.melds[0]),catch_play=obs.rule_state.catch_play,
                    shanten=None if f is None else f.shanten_after,
                    seven=None if f is None else f.seven_pairs_shanten_after,
                    enhanced=any(p.name=='七对持续续打消融' for p in chosen.score_parts)))
            choices.append(SimulationChoice(decision.window_key,chosen.action))
        world=engine.advance(world,frame.revision,tuple(choices))
    raise RuntimeError('续打超过5000步，不能记作流局')
