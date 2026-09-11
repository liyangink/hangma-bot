"""较早等待阶段的大牌路线候选；只消费规则事实，不推演牌型或读取未来。"""
from __future__ import annotations

import asyncio
from dataclasses import replace
import time
from typing import Callable

from hangma_bot.hangma.interface import CandidateFactKind, RuleCompleteness
from hangma_bot.kernel.actions import Discard
from .heuristic_v2 import ComparableHeuristicPolicyV2
from .interface import DecisionBudget, DecisionPlan, DecisionRequest, ScorePart


class V2RoutePreservePolicy:
    """在正式赛门清普通出牌中，用不超过 5% 的即时进张损失保留同距离七对。

    首版仅覆盖 V2 弃牌后最优向听为 1 或 2、牌墙至少 48 张、零链无圈。
    替代弃牌不得增加最优向听、减少手留财神；七对向听须下降并且不超过
    原最优向听。此门槛是开发假设，不是期望分公式或已经证明的最优策略。
    已听牌、胡、吃碰、杠以及等胡沿用 V2，便于独立检验较早路线的增量。
    """

    def __init__(self, monotonic: Callable[[], float] = time.monotonic) -> None:
        """注入单调时钟；规则数学、文件和网络均不属于此策略。"""
        self._monotonic = monotonic
        self._baseline = ComparableHeuristicPolicyV2(monotonic=monotonic)

    async def choose(self, request: DecisionRequest, budget: DecisionBudget) -> DecisionPlan:
        """先完成 V2 保底计划；只提升一个有完整事实的候选，其余执行顺序保留。"""
        baseline = await self._baseline.choose(request, budget)
        await asyncio.sleep(0)
        if self._monotonic() > budget.enhancement_deadline_monotonic:
            return replace(baseline, degraded_reasons=baseline.degraded_reasons + ('路线保留增强超时，沿用完整 V2',))
        obs = request.observation
        if (not baseline.candidates or obs.phase != 'draw' or obs.turn_seat != obs.seat
                or obs.drawn_tile is None or obs.melds[obs.seat] or obs.rule_state.catch_play
                or obs.rule_state.chain_count or obs.gang_draw
                or obs.remaining_tile_count is None or obs.remaining_tile_count < 48):
            return baseline
        first = baseline.candidates[0]
        if not isinstance(first.action, Discard):
            return baseline
        facts_by_key = {}
        for candidate in request.rules.legal_candidates:
            facts_by_key.setdefault(candidate.action_key, candidate.facts)
        old = facts_by_key.get(first.action_key)
        if not self._complete(old) or old.shanten_after not in (1,2):
            return baseline
        old_outs = sum(t.remaining_estimate for t in old.useful_tiles)
        if not old_outs:
            return baseline
        choices = []
        for ranked in baseline.candidates:
            if not isinstance(ranked.action, Discard):
                continue
            facts = facts_by_key.get(ranked.action_key)
            if not self._complete(facts):
                continue
            if (facts.shanten_after != old.shanten_after
                    or facts.seven_pairs_shanten_after >= old.seven_pairs_shanten_after
                    or facts.seven_pairs_shanten_after > old.shanten_after):
                continue
            if ranked.action.tile == obs.rule_state.wealth_god and first.action.tile != obs.rule_state.wealth_god:
                continue
            outs = sum(t.remaining_estimate for t in facts.useful_tiles)
            if outs * 100 < old_outs * 95:
                continue
            choices.append((facts.seven_pairs_shanten_after, -outs, ranked.rank, ranked))
        if not choices:
            return baseline
        _, _, _, chosen = min(choices, key=lambda item:item[:3])
        new = facts_by_key[chosen.action_key]
        new_outs = sum(t.remaining_estimate for t in new.useful_tiles)
        boost = first.total_score - chosen.total_score + 1.0
        reason = ('路线保留实验：最优向听均为 {s}，七对向听 {before}→{after}，'
                  '未见有效牌 {old}→{new}；损失不超过 5%，墙余 {wall}。'
                  '这是有限代价启发式，不是期望净分证明。').format(
            s=old.shanten_after,before=old.seven_pairs_shanten_after,after=new.seven_pairs_shanten_after,
            old=old_outs,new=new_outs,wall=obs.remaining_tile_count)
        chosen = replace(chosen, total_score=chosen.total_score+boost,
                         score_parts=chosen.score_parts+(ScorePart('路线保留优先',boost),),
                         reasons=chosen.reasons+(reason,))
        ordered = (chosen,) + tuple(c for c in baseline.candidates if c.action_key != chosen.action_key)
        return replace(baseline,candidates=tuple(replace(c,rank=i+1) for i,c in enumerate(ordered)))

    @staticmethod
    def _complete(facts) -> bool:
        """未知与不适用不填零；只接受完整的动作后等待事实。"""
        return (facts is not None and facts.fact_kind is CandidateFactKind.HAND_PROGRESS
                and facts.completeness is RuleCompleteness.COMPLETE
                and type(facts.shanten_after) is int
                and type(facts.standard_shanten_after) is int
                and type(facts.seven_pairs_shanten_after) is int
                and not facts.replacement_draw_unknown)
