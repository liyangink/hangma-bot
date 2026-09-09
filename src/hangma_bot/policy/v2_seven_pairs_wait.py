"""门清已听牌时保留七对的窄候选；复用一次摸牌分值，不重算牌型。"""
from __future__ import annotations

from dataclasses import replace

from hangma_bot.hangma.interface import RuleCompleteness
from hangma_bot.kernel.actions import Discard, action_key
from .interface import DecisionBudget, DecisionPlan, DecisionRequest
from .value_one_draw import OneDrawValuePolicy


class V2SevenPairsWaitPolicy(OneDrawValuePolicy):
    """只在不减少有效进张的门清弃牌中接受七对条件分值增益。

    V2和一次摸牌策略均保持冻结。先复用同一完整证明与分值比较，再要求
    最佳方案仍为弃牌、具有七对计分路线且未见有效张数不少于V2首选。
    不放弃立即胡、不改吃碰或杠、不跨向听比较；未见张数不是实际概率。
    整桌净分仍须由独立完整桌赛验证。继承value_weight的0/1开关及预算退路。
    """

    async def _enhance(self, request: DecisionRequest, budget: DecisionBudget,
                       baseline: DecisionPlan) -> DecisionPlan:
        obs = request.observation
        if (not self._value_weight or not baseline.candidates or
                request.rules.completeness is not RuleCompleteness.COMPLETE or obs.observation_issues or
                obs.phase != "draw" or obs.turn_seat != obs.seat or obs.drawn_tile is None or
                obs.melds[obs.seat] or not isinstance(baseline.candidates[0].action, Discard)):
            return baseline
        plan = await super()._enhance(request, budget, baseline)
        first, chosen = baseline.candidates[0], plan.candidates[0]
        if chosen.action_key == first.action_key or not isinstance(chosen.action, Discard):
            return baseline
        available = {}
        for candidate in request.rules.legal_candidates:
            if action_key(candidate.action) == candidate.action_key:
                available.setdefault(candidate.action_key, candidate)
        before, after = available[first.action_key], available[chosen.action_key]
        # 计番明细由规则模块产生；这里识别估值的适用范围，不识别手牌牌型。
        if not any(any(detail == "七对" or detail.startswith("豪华七对×")
                       for detail in route.conditional_settlement.details)
                   for route in after.value_facts.routes):
            return baseline
        old_value = await self._waiting_value(before, obs.seat, budget)
        new_value = await self._waiting_value(after, obs.seat, budget)
        if (old_value is None or new_value is None or
                new_value.unseen_count < old_value.unseen_count or
                new_value.score_mass <= old_value.score_mass):
            return baseline
        explanation = (
            "门清七对听牌增量：有效进张估计 {0}→{1} 张；"
            "下一摸条件分值质量 {2:g}→{3:g}，保持立即胡优先；不表示整单局期望得分"
        ).format(old_value.unseen_count, new_value.unseen_count, old_value.score_mass, new_value.score_mass)
        await self._check_deadline(budget)
        return replace(plan, candidates=(replace(chosen, reasons=chosen.reasons + (explanation,)),) + plan.candidates[1:])
