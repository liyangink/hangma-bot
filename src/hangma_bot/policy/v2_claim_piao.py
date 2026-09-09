"""吃碰后续飘的独立离线候选；只消费规则给出的下一摸条件结算。"""

from __future__ import annotations

import asyncio
import math
import time
from dataclasses import replace
from typing import Callable

from hangma_bot.hangma.interface import RuleCompleteness, ValueCoverage
from hangma_bot.kernel.actions import Discard, Hu, action_key
from .errors import PolicyTimeoutError
from .heuristic_v2 import ComparableHeuristicPolicyV2
from .interface import DecisionBudget, DecisionPlan, DecisionRequest, ScorePart
from .weights_v1 import DEFAULT_WEIGHTS_V1, HeuristicWeightsV1


def _proof(candidate, seat):
    """读取同一摸前状态的完整任意听证明，返回逐进张净分及未见张数。

    任意听由规则 facts 的 baotou 证明；未见张数只用于核对两方案支持集，
    不解释为真实摸牌概率，不把互斥进张的分数直接相加。
    """
    facts = candidate.value_facts
    if (facts is None or facts.coverage is not ValueCoverage.COMPLETE or facts.issues or
            facts.immediate_settlement is not None or not facts.routes):
        return None
    conditions = facts.routes[0].conditions
    if conditions.draw_kind != "normal" or conditions.baotou is not True:
        return None
    values = {}
    for route in facts.routes:
        if (route.conditions != conditions or route.followup_discard is not None or
                route.support != "conditional_witness" or route.shanten != 0):
            return None
        gain = route.conditional_settlement.score_delta[seat]
        if type(gain) not in (int, float) or not math.isfinite(gain) or gain <= 0:
            return None
        for tile in route.useful_tiles:
            if tile.code in values or type(tile.remaining_estimate) is not int or tile.remaining_estimate <= 0:
                return None
            values[tile.code] = (tile.remaining_estimate, gain)
    return (conditions, values) if values else None


class V2ClaimPiaoPolicy:
    """无立即胡的吃碰后窗口中，优先条件分值严格占优的续白。

    不改变此前吃碰取舍，不放弃立即胡，不估计下一摸前的存活概率。
    两种弃牌均须由规则证明普通摸任意牌爆头，且有相同进张支持集；
    续白的最低条件净分必须超过 V2 弃牌的最高条件净分。
    整单局效果仍由独立完整桌赛检验，不能从条件占优推导已实现得分。
    """

    def __init__(self, weights: HeuristicWeightsV1 = DEFAULT_WEIGHTS_V1,
                 monotonic: Callable[[], float] = time.monotonic, *, continuation_weight: float = 1) -> None:
        """注入冻结 V2 权重与单调时钟；开关为 0 时完全返回 V2 计划。"""
        if type(continuation_weight) not in (int, float) or continuation_weight not in (0, 1):
            raise ValueError("continuation_weight 只允许 0 或 1")
        self._weights = weights
        self._monotonic = monotonic
        self._continuation_weight = continuation_weight
        self._baseline = ComparableHeuristicPolicyV2(weights, monotonic)

    async def _check_deadline(self, budget):
        await asyncio.sleep(0)
        if self._monotonic() > budget.enhancement_deadline_monotonic:
            raise PolicyTimeoutError("吃碰后续飘超过增强截止时间")

    async def choose(self, request: DecisionRequest, budget: DecisionBudget) -> DecisionPlan:
        """增强失败保留完整 V2；取消向上传播，明确拒绝的动作沿用 V2 过滤。"""
        baseline = await self._baseline.choose(request, budget)
        try:
            return await self._enhance(request, budget, baseline)
        except Exception as exc:
            return replace(baseline, degraded_reasons=baseline.degraded_reasons + (
                "吃碰后续飘失败，沿用完整V2计划：{0}：{1}".format(type(exc).__name__, str(exc)[:240]),))

    async def _enhance(self, request, budget, baseline):
        obs = request.observation
        if (not self._continuation_weight or not baseline.candidates or
                request.rules.completeness is not RuleCompleteness.COMPLETE or obs.observation_issues or
                obs.phase != "draw" or obs.turn_seat != obs.seat or obs.drawn_tile is not None or
                obs.gang_draw or not obs.melds[obs.seat] or obs.rule_state.baotou is not True or
                obs.chain_piao is None or obs.chain_piao <= 0 or obs.rule_state.chain_count <= 0):
            return baseline
        # 吃碰后的无摸牌弃牌窗口由观察契约表示；圈内合法性和链后态由规则证明。
        # 不重复解析公开历史判圈主，避免与规则引擎恢复快照的语义漂移。
        await self._check_deadline(budget)
        if any(isinstance(c.action, Hu) for c in request.rules.legal_candidates):
            return baseline
        first = baseline.candidates[0]
        white = next((c for c in baseline.candidates if c.action_key == "discard:白"), None)
        if not isinstance(first.action, Discard) or white is None or first.action_key == white.action_key:
            return baseline
        available = {c.action_key: c for c in request.rules.legal_candidates if action_key(c.action) == c.action_key}
        if first.action_key not in available or white.action_key not in available:
            return baseline
        ordinary = _proof(available[first.action_key], obs.seat)
        continuation = _proof(available[white.action_key], obs.seat)
        if ordinary is None or continuation is None:
            return baseline
        old_conditions, old = ordinary
        new_conditions, new = continuation
        if (old_conditions.chain_piao != 0 or new_conditions.chain_piao != obs.chain_piao + 1 or
                new_conditions.chain_count != obs.rule_state.chain_count + 1 or
                {k: v[0] for k, v in old.items()} != {k: v[0] for k, v in new.items()}):
            return baseline
        floor, ceiling = min(v[1] for v in new.values()), max(v[1] for v in old.values())
        if floor <= ceiling:
            return baseline
        parts = white.score_parts + (
            ScorePart("吃碰后续飘-抵消基线总分", -sum(p.value for p in white.score_parts)),
            ScorePart("吃碰后续飘-下一摸条件净分下界", float(floor)),)
        selected = replace(white, total_score=sum(p.value for p in parts), score_parts=parts,
                           reasons=white.reasons + (
                               "吃碰后续飘：两种弃牌均任意听，续白下一摸条件净分至少 {0:g}，"
                               "V2 {1} 至多 {2:g}；未估计摸牌前他家胡牌或后续鸣牌的影响".format(floor, first.action_key, ceiling),))
        result = [selected] + [c for c in baseline.candidates if c.action_key != white.action_key]
        await self._check_deadline(budget)
        return replace(baseline, candidates=tuple(replace(c, rank=i + 1) for i, c in enumerate(result)))
