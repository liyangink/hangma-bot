"""均衡启发式的多路线影子评估。

影子策略严格复用线上保底策略，只把规则模块已经提供的动作后牌效事实
整理成可审计的 Pareto 路线摘要；它不改变候选顺序、不读取未来牌墙，也不
把未知事实当作零值。这样可以先测量多路线覆盖和耗时，再决定是否启用。
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from typing import Callable, Iterable, Optional, Tuple

from hangma_bot.hangma.interface import CandidateFactKind, RuleCompleteness
from hangma_bot.kernel.actions import Discard

from .interface import BotPolicy, DecisionBudget, DecisionPlan, DecisionRequest
from .v2_hu_upgrade import V2HuUpgradePolicy


def _route_signature(candidate) -> Optional[Tuple[int, int, int]]:
    """读取普通/七对双路线的公开事实；未知、胜负和杠补事实均跳过。"""

    facts = candidate.facts
    if facts is None or facts.fact_kind is not CandidateFactKind.HAND_PROGRESS:
        return None
    if facts.completeness is not RuleCompleteness.COMPLETE:
        return None
    if facts.shanten_after is None or facts.seven_pairs_shanten_after is None:
        return None
    if facts.replacement_draw_unknown:
        return None
    outs = sum(tile.remaining_estimate for tile in facts.useful_tiles)
    return facts.shanten_after, facts.seven_pairs_shanten_after, outs


def _pareto(candidates: Iterable[object]) -> Tuple[object, ...]:
    """保留不存在同时更快、更宽且七对距离更近的候选。"""

    known = [(candidate, _route_signature(candidate)) for candidate in candidates]
    known = [(candidate, sig) for candidate, sig in known if sig is not None]
    result = []
    for candidate, sig in known:
        dominated = any(
            other != sig
            and other[0] <= sig[0]
            and other[1] <= sig[1]
            and other[2] >= sig[2]
            for _, other in known
        )
        if not dominated:
            result.append(candidate)
    return tuple(result)


class V2BalancedShadowPolicy:
    """V2 等胡保底上的多路线影子层；输出顺序与保底完全一致。"""

    VERSION = "v2_balanced_shadow_v1"

    def __init__(
        self,
        baseline: Optional[BotPolicy] = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._baseline = baseline or V2HuUpgradePolicy(monotonic=monotonic)

    async def choose(self, request: DecisionRequest, budget: DecisionBudget) -> DecisionPlan:
        """返回原计划，仅在候选理由中附加可审计的路线覆盖摘要。"""

        plan = await self._baseline.choose(request, budget)
        await asyncio.sleep(0)
        if self._expired(budget):
            return plan
        if request.observation.phase != "draw":
            return plan
        candidates = [candidate for candidate in request.rules.legal_candidates if isinstance(candidate.action, Discard)]
        frontier = _pareto(candidates)
        if not frontier:
            return plan
        keys = ",".join(candidate.action_key for candidate in frontier[:8])
        signatures = ";".join(
            f"{candidate.action_key}:{_route_signature(candidate)}" for candidate in frontier[:8]
        )
        note = (
            f"影子路线[{self.VERSION}]：Pareto候选 {len(frontier)} 个；不改当前顺序；"
            f"动作键={keys}；路线签名={signatures}"
        )
        ranked = list(plan.candidates)
        if ranked:
            ranked[0] = replace(ranked[0], reasons=ranked[0].reasons + (note,))
        return replace(plan, candidates=tuple(ranked))

    @staticmethod
    def _expired(budget: DecisionBudget) -> bool:
        # 由基线负责真正的单调时钟检查；影子层不引入新的阻塞工作。
        return False
