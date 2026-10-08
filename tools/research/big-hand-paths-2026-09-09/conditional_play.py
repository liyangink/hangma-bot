"""支持多人响应根窗口的条件续打采集；只使用模拟器公开接口。"""

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

from lab import request_for, DecisionBudget
from continuation_notes import unexpected_notes
from hangma_bot.simulation.interface import SimulationChoice


async def complete(engine, world, own_policy, opponents, forced_action_key):
    """首帧只强制座位 0 的合法动作，其余同期响应和之后所有动作正常决策。

返回座位顺序 0—3 的单局净分、终局计番及本人可见动作审计；隐藏世界
只在 frame/advance/export_hand 间传递，不读取其内部字段。
"""
    trace=[]
    audit_notes=[]
    for step in range(5000):
        frame=engine.frame(world)
        if frame.blocked_reason:
            raise RuntimeError(frame.blocked_reason)
        if frame.final_scores is not None:
            result=engine.export_hand(world,1)
            assert sum(result['score_delta'])==0
            assert result['score_delta']==list(frame.final_scores)
            return dict(score=result['score_delta'][0], score_delta=result['score_delta'],
                winner=result['winner_seat'],fan=result['fan'],details=result['details'],
                steps=step,trace=trace,normal_audit_notes=audit_notes,
                result_hash=hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=False).encode()).hexdigest())
        if step==0:
            assert sum(d.observation.seat==0 for d in frame.decisions)==1
        choices=[]
        for decision in frame.decisions:
            obs=decision.observation
            analysis=engine.rules.analyze(obs)
            request=replace(request_for(obs,analysis),window_key=decision.window_key)
            policy=own_policy if obs.seat==0 else opponents
            plan=await policy.choose(request,DecisionBudget(10,11,12))
            failures=unexpected_notes(plan,request)
            if failures:
                raise RuntimeError(str(failures))
            if plan.degraded_reasons:
                audit_notes.append(dict(seat=obs.seat,seq=request.trigger_seq,reasons=list(plan.degraded_reasons)))
            key=forced_action_key if step==0 and obs.seat==0 else plan.candidates[0].action_key
            candidate=next(c for c in analysis.legal_candidates if c.action_key==key)
            if obs.seat==0:
                hu=next((c for c in analysis.legal_candidates if c.action_key=='hu'),None)
                settlement=None if hu is None or hu.value_facts is None else hu.value_facts.immediate_settlement
                trace.append(dict(seq=request.trigger_seq,wall=obs.remaining_tile_count,
                    phase=obs.phase,action=key,policy_action=plan.candidates[0].action_key,
                    hand=[t.code for t in obs.my_hand],draw=None if obs.drawn_tile is None else obs.drawn_tile.code,
                    meld_count=len(obs.melds[0]),chain_count=obs.rule_state.chain_count,piao=obs.chain_piao,
                    baotou=obs.rule_state.baotou,catch_play=obs.rule_state.catch_play,
                    current_hu_score=None if settlement is None else settlement.score_delta[0]))
            choices.append(SimulationChoice(decision.window_key,candidate.action))
        world=engine.advance(world,frame.revision,tuple(choices))
    raise RuntimeError('完整续打超过5000步；不能以零值或流局补齐')
