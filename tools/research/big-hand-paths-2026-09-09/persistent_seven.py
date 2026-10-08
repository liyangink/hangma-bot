"""仅用于续打敏感性实验的七对偏好，不是线上候选或最优价值教师。"""

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
import time

from hangma_bot.hangma.interface import CandidateFactKind, RuleCompleteness
from hangma_bot.kernel.actions import Discard, Pass, Hu, action_key
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
from hangma_bot.policy.interface import ScorePart


class PersistentSevenPolicy:
    """在后续每个可见决策持续考察七对，允许相对最快路线多一向听。

    只调整无圈无链门清窗口；有胡即胡。七对最多三向听，剩余可摸墙
    至少为所需最少本人进张次数的两倍乘四（另扣20张尾墙）。这只是
    固定的研究偏好，不是成胡概率或损失上限。吃碰后不再可能七对，
    因而符合门槛时可改选过；杠补前未知事实不与确定的等待事实比较。
    """
    def __init__(self,monotonic=time.monotonic):
        self._monotonic=monotonic
        self._base=ComparableHeuristicPolicyV2(monotonic=monotonic)

    async def choose(self,request,budget):
        """完整保留V2计划、安全过滤和审计，仅改变满足预定偏好的首选。"""
        base=await self._base.choose(request,budget)
        await asyncio.sleep(0)
        if self._monotonic()>budget.enhancement_deadline_monotonic:
            return replace(base,degraded_reasons=base.degraded_reasons+('研究续打增强超时，沿用V2',))
        obs=request.observation
        if (not base.candidates or isinstance(base.candidates[0].action,Hu)
                or obs.melds[obs.seat] or obs.rule_state.catch_play or obs.rule_state.chain_count
                or obs.gang_draw or obs.remaining_tile_count is None):return base
        facts={}
        for c in request.rules.legal_candidates:
            if c.action_key==action_key(c.action):facts.setdefault(c.action_key,c.facts)
        eligible=[]; fastest=[]
        for c in base.candidates:
            f=facts.get(c.action_key)
            if (f is None or f.fact_kind is not CandidateFactKind.HAND_PROGRESS
                    or f.completeness is not RuleCompleteness.COMPLETE or f.replacement_draw_unknown
                    or f.shanten_after is None or f.shanten_after<0):continue
            fastest.append(f.shanten_after)
            if (not isinstance(c.action,(Discard,Pass)) or f.seven_pairs_shanten_after is None
                    or not 0<=f.seven_pairs_shanten_after<=3 or f.seven_pairs_useful_tiles is None
                    or obs.remaining_tile_count-20 < 8*(f.seven_pairs_shanten_after+1)):
                continue
            if isinstance(c.action,Discard) and c.action.tile==obs.rule_state.wealth_god:
                continue  # 本消融只保留对子路线，不引入新的弃白/飘链策略。
            outs=sum(t.remaining_estimate for t in f.seven_pairs_useful_tiles)
            if outs>0:eligible.append((f.seven_pairs_shanten_after,-outs,c.rank,c))
        if not fastest:return base
        eligible=[x for x in eligible if x[0]<=min(fastest)+1]
        if not eligible:return base
        q,negative_outs,_,chosen=min(eligible,key=lambda x:x[:3])
        if chosen.action_key==base.candidates[0].action_key:return base
        boost=base.candidates[0].total_score-chosen.total_score+1
        chosen=replace(chosen,total_score=chosen.total_score+boost,
            score_parts=chosen.score_parts+(ScorePart('七对持续续打消融',boost),),
            reasons=chosen.reasons+(f'研究续打：七对向听{q}、活进张{-negative_outs}；相对最快路线最多多一向听，非期望净分证明。',))
        return replace(base,candidates=tuple(replace(c,rank=i+1) for i,c in enumerate(
            (chosen,)+tuple(c for c in base.candidates if c.action_key!=chosen.action_key))))
