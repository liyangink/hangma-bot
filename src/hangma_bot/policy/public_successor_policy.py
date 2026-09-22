"""把冻结 R17 公开后继归约接到完整 V2 计划上的薄包装器。

包装器先取得稳定 V2 计划，再只重排其中已有的未拒绝弃牌位置；胡、杠、
响应动作、紧急标记、分数分解和非弃牌相对位置均保持。搜索提供者由组合
根注入，只能以请求中的 ``PlayerObservation`` 调用同版本 ``HangmaRules``。
任一搜索、候选、预算或合同失败都原样返回已经完成的 V2 计划。
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
import time
from typing import Callable, Dict, Optional, Tuple

from hangma_bot.hangma.interface import PublicSuccessorAnalysis
from hangma_bot.kernel.actions import Discard, WindowPhase
from hangma_bot.kernel.observation import PlayerObservation

from .heuristic_v2 import ComparableHeuristicPolicyV2
from .interface import (
    BotPolicy,
    DecisionBudget,
    DecisionPlan,
    DecisionRequest,
    RankedCandidate,
)
from .public_successor_leaf_executor import LeafProgramExecutor
from .public_successor_search import (
    SearchReduction,
    order_discard_keys_by_fronts,
    reduce_public_successors,
)


SuccessorProvider = Callable[[PlayerObservation], PublicSuccessorAnalysis]
DiscardOrderer = Callable[[SearchReduction, Tuple[str, ...]], Tuple[str, ...]]


class PublicSuccessorSearchPolicy:
    """R17 研究策略：V2 先完成，公开后继只作可全量回退的弃牌重排。"""

    def __init__(
        self,
        successor_provider: SuccessorProvider,
        leaf_executor: LeafProgramExecutor,
        *,
        candidate_identity: str,
        baseline: Optional[BotPolicy] = None,
        monotonic: Callable[[], float] = time.monotonic,
        enabled: bool = True,
        orderer: Optional[DiscardOrderer] = None,
    ) -> None:
        if not callable(successor_provider):
            raise TypeError("successor_provider 必须可调用")
        if not isinstance(leaf_executor, LeafProgramExecutor):
            raise TypeError("leaf_executor 必须是 LeafProgramExecutor")
        if not isinstance(candidate_identity, str) or not candidate_identity:
            raise ValueError("candidate_identity 必须是非空字符串")
        if orderer is not None and not callable(orderer):
            raise TypeError("orderer 必须可调用")
        self._provider = successor_provider
        self._executor = leaf_executor
        self._identity = candidate_identity
        self.policy_id = "r17-public-successor:" + candidate_identity[:12]
        self.max_operations = leaf_executor.max_operations_per_window
        self._monotonic = monotonic
        self._enabled = bool(enabled)
        self._orderer = orderer
        self._baseline: BotPolicy = (
            baseline
            if baseline is not None
            else ComparableHeuristicPolicyV2(monotonic=monotonic)
        )

    async def _within_enhancement_budget(self, budget: DecisionBudget) -> bool:
        await asyncio.sleep(0)
        return self._monotonic() <= budget.enhancement_deadline_monotonic

    async def choose(
        self,
        request: DecisionRequest,
        budget: DecisionBudget,
    ) -> DecisionPlan:
        baseline = await self._baseline.choose(request, budget)
        if (
            not self._enabled
            or request.observation.phase != "draw"
            or request.window_key.phase is not WindowPhase.DRAW
        ):
            return baseline
        if not await self._within_enhancement_budget(budget):
            return baseline

        discard_positions = tuple(
            index
            for index, item in enumerate(baseline.candidates)
            if isinstance(item.action, Discard)
        )
        if len(discard_positions) < 2:
            return baseline
        baseline_keys = tuple(
            baseline.candidates[index].action_key for index in discard_positions
        )
        try:
            successors = self._provider(request.observation)
            if not await self._within_enhancement_budget(budget):
                return baseline
            scorer = self._executor.window_scorer()
            reduction = reduce_public_successors(request, successors, scorer)
            orderer = self._orderer or order_discard_keys_by_fronts
            ordered_keys = orderer(reduction, baseline_keys)
            if not reduction.complete or ordered_keys == baseline_keys:
                return baseline
            if not await self._within_enhancement_budget(budget):
                return baseline
        except Exception:
            return baseline

        by_key: Dict[str, RankedCandidate] = {
            baseline.candidates[index].action_key: baseline.candidates[index]
            for index in discard_positions
        }
        if set(by_key) != set(ordered_keys):
            return baseline
        result = list(baseline.candidates)
        short_identity = self._identity[:12]
        for position, key in zip(discard_positions, ordered_keys):
            item = by_key[key]
            result[position] = replace(
                item,
                reasons=item.reasons + (
                    "R17公开后继固定归约重排；候选={0}；原V2分数保留供审计".format(
                        short_identity
                    ),
                ),
            )
        result = [replace(item, rank=index + 1) for index, item in enumerate(result)]
        return replace(baseline, candidates=tuple(result))


__all__ = ["DiscardOrderer", "PublicSuccessorSearchPolicy", "SuccessorProvider"]
