"""逐进张核对普通型不退步，再保留更近七对；研发候选，不改变冻结V2。"""
from __future__ import annotations

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
from typing import Callable

from hangma_bot.hangma.interface import CandidateFactKind, RuleCompleteness
from hangma_bot.kernel.actions import Discard, action_key
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
from hangma_bot.policy.interface import DecisionBudget, DecisionPlan, DecisionRequest, ScorePart


def preserves_standard_progress(new, old) -> bool:
    """比较同一弃牌窗口的普通型推进；一张进张至多降低一次向听。

    普通型已更近一向听时，任意下一摸也不会比旧方案更远；同距离时，
    旧方案每张活进张必须仍可推进新方案。两种弃牌后未见牌池相同：
    打出的牌从本人手牌转为公开牌，没有凭空增加可摸副本。
    """
    if new.standard_shanten_after > old.standard_shanten_after:
        return False
    if new.standard_shanten_after < old.standard_shanten_after:
        return True
    support={t.code:t.remaining_estimate for t in new.standard_useful_tiles}
    return all(t.remaining_estimate==0 or support.get(t.code)==t.remaining_estimate
               for t in old.standard_useful_tiles)


class V2RouteFrontierPolicy:
    """长墙普通弃牌中保留较近七对，并要求普通型逐进张不退步。

    与首版区别：使用实际分牌型进张支持集，不容忍凭张数定义的5%损失；
    已听普通型也可保留更远的七对潜力。七对最多三向听，三向听要求墙64，
    更近时墙48。它是局部推进事实上的有界偏好，不声称长期净分支配。
    """
    def __init__(self,monotonic:Callable[[],float]=time.monotonic) -> None:
        """只组合已有V2和时钟；不建立规则、文件或网络依赖。"""
        self._monotonic=monotonic
        self._baseline=ComparableHeuristicPolicyV2(monotonic=monotonic)

    async def choose(self,request:DecisionRequest,budget:DecisionBudget) -> DecisionPlan:
        """保留完整V2安全计划，仅提升原排名最靠前的满足条件候选。"""
        baseline=await self._baseline.choose(request,budget)
        await asyncio.sleep(0)
        if self._monotonic()>budget.enhancement_deadline_monotonic:
            return replace(baseline,degraded_reasons=baseline.degraded_reasons+('分牌型进张增强超时，沿用完整V2',))
        obs=request.observation
        if (not baseline.candidates or obs.phase!='draw' or obs.turn_seat!=obs.seat
                or obs.drawn_tile is None or obs.melds[obs.seat] or obs.rule_state.catch_play
                or obs.rule_state.chain_count or obs.gang_draw or obs.remaining_tile_count is None
                or obs.remaining_tile_count<48):
            return baseline
        first=baseline.candidates[0]
        if not isinstance(first.action,Discard):
            return baseline
        available={}
        for c in request.rules.legal_candidates:
            try:
                if c.action_key==action_key(c.action):available.setdefault(c.action_key,c.facts)
            except TypeError:
                continue
        old=available.get(first.action_key)
        if not self._complete(old):return baseline
        for ranked in baseline.candidates[1:]:
            if not isinstance(ranked.action,Discard):continue
            new=available.get(ranked.action_key)
            if not self._complete(new):continue
            if (new.seven_pairs_shanten_after>=old.seven_pairs_shanten_after
                    or new.seven_pairs_shanten_after>3
                    or new.shanten_after>old.shanten_after
                    or (new.seven_pairs_shanten_after==3 and obs.remaining_tile_count<64)
                    or not any(t.remaining_estimate>0 for t in new.seven_pairs_useful_tiles)):
                continue
            if ranked.action.tile==obs.rule_state.wealth_god and first.action.tile!=obs.rule_state.wealth_god:
                continue
            if not preserves_standard_progress(new,old):continue
            boost=first.total_score-ranked.total_score+1
            reason=('逐进张路线保留：普通型向听 {s0}→{s1}，原有活进张不退步；'
                    '七对向听 {q0}→{q1}，墙余 {wall}。仅为局部推进偏好，不是长期净分支配证明。').format(
                s0=old.standard_shanten_after,s1=new.standard_shanten_after,
                q0=old.seven_pairs_shanten_after,q1=new.seven_pairs_shanten_after,wall=obs.remaining_tile_count)
            chosen=replace(ranked,total_score=ranked.total_score+boost,
                score_parts=ranked.score_parts+(ScorePart('逐进张路线保留',boost),),reasons=ranked.reasons+(reason,))
            ordered=(chosen,)+tuple(c for c in baseline.candidates if c.action_key!=chosen.action_key)
            return replace(baseline,candidates=tuple(replace(c,rank=i+1) for i,c in enumerate(ordered)))
        return baseline

    @staticmethod
    def _complete(facts) -> bool:
        """所需新集合必须完整；缺失、局部计数失败、有副露均不参与排序。"""
        return (facts is not None and facts.fact_kind is CandidateFactKind.HAND_PROGRESS
                and facts.completeness is RuleCompleteness.COMPLETE
                and type(facts.shanten_after) is int and facts.shanten_after>=0
                and type(facts.standard_shanten_after) is int and facts.standard_shanten_after>=0
                and type(facts.seven_pairs_shanten_after) is int and facts.seven_pairs_shanten_after>=0
                and facts.standard_useful_tiles is not None and facts.seven_pairs_useful_tiles is not None
                and not facts.replacement_draw_unknown)
