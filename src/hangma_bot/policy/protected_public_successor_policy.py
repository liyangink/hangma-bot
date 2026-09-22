"""在累计能力计划之后运行 R17 公开后继弃牌搜索。

本策略先完成基线计划。只要任一候选的有界评分解释表明已触发受保护能力，
或评分解释结构不可核验，就完整返回基线计划；其余自摸弃牌窗口复用 R17
固定归约，只重排已经合法且未被拒绝的弃牌位置。规则分析、非弃牌动作、
紧急候选、原评分及提交行为均不由本模块改变。
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
import time
from typing import Callable, Dict, Mapping, Optional, Tuple

from hangma_bot.hangma.interface import PublicSuccessorAnalysis
from hangma_bot.kernel.actions import Discard, WindowPhase
from hangma_bot.kernel.observation import PlayerObservation

from .interface import (
    BotPolicy,
    DecisionBudget,
    DecisionPlan,
    DecisionRequest,
    RankedCandidate,
)
from .public_successor_leaf_executor import LeafProgramExecutor
from .public_successor_search import (
    order_discard_keys_by_fronts,
    reduce_public_successors,
)


SuccessorProvider = Callable[[PlayerObservation], PublicSuccessorAnalysis]


def protected_trace_state(
    plan: DecisionPlan, protected_trace_keys: Tuple[str, ...]
) -> tuple[bool, Tuple[str, ...]]:
    """返回是否应保持基线及实际触发键；解释缺失或畸形时保守保持。

    ``score_trace`` 是评分器已经受大小限制的审计载荷。组合层只读取
    ``detail.<key>.triggered``，不重新推断麻将规则。只要无法证明当前计划
    没有专项覆盖，就不让后继搜索覆盖它。
    """

    if not protected_trace_keys:
        raise ValueError("protected_trace_keys 不能为空")
    triggered: set[str] = set()
    for candidate in plan.candidates:
        outer = candidate.score_trace
        if not isinstance(outer, Mapping):
            return True, ("trace_unavailable",)
        detail = outer.get("detail")
        if not isinstance(detail, Mapping):
            return True, ("trace_detail_unavailable",)
        for key in protected_trace_keys:
            value = detail.get(key)
            if isinstance(value, Mapping) and value.get("triggered") is True:
                triggered.add(key)
    ordered = tuple(key for key in protected_trace_keys if key in triggered)
    return bool(ordered), ordered


class ProtectedPublicSuccessorSearchPolicy:
    """累计能力优先、普通弃牌才运行 R17 的确定性组合策略。"""

    def __init__(
        self,
        successor_provider: SuccessorProvider,
        leaf_executor: LeafProgramExecutor,
        *,
        candidate_identity: str,
        baseline: BotPolicy,
        protected_trace_keys: Tuple[str, ...],
        monotonic: Callable[[], float] = time.monotonic,
        enabled: bool = True,
    ) -> None:
        if not callable(successor_provider):
            raise TypeError("successor_provider 必须可调用")
        if not isinstance(leaf_executor, LeafProgramExecutor):
            raise TypeError("leaf_executor 必须是 LeafProgramExecutor")
        if not isinstance(candidate_identity, str) or not candidate_identity:
            raise ValueError("candidate_identity 必须是非空字符串")
        keys = tuple(protected_trace_keys)
        if not keys or any(not isinstance(key, str) or not key for key in keys):
            raise ValueError("protected_trace_keys 必须是非空字符串元组")
        if len(set(keys)) != len(keys):
            raise ValueError("protected_trace_keys 不得重复")
        self._provider = successor_provider
        self._executor = leaf_executor
        self._identity = candidate_identity
        self._baseline = baseline
        self._protected_trace_keys = keys
        self._monotonic = monotonic
        self._enabled = bool(enabled)
        self.policy_id = "protected-r17:" + candidate_identity[:12]
        self.max_operations = leaf_executor.max_operations_per_window

    async def _within_enhancement_budget(self, budget: DecisionBudget) -> bool:
        await asyncio.sleep(0)
        return self._monotonic() <= budget.enhancement_deadline_monotonic

    async def choose(
        self,
        request: DecisionRequest,
        budget: DecisionBudget,
    ) -> DecisionPlan:
        baseline = await self._baseline.choose(request, budget)
        protected, _keys = protected_trace_state(
            baseline, self._protected_trace_keys
        )
        if protected:
            return baseline
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
            ordered_keys = order_discard_keys_by_fronts(reduction, baseline_keys)
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
                    "累计专项未触发；R17公开后继固定归约重排；候选={0}".format(
                        short_identity
                    ),
                ),
            )
        result = [replace(item, rank=index + 1) for index, item in enumerate(result)]
        return replace(baseline, candidates=tuple(result))


__all__ = ["ProtectedPublicSuccessorSearchPolicy", "protected_trace_state"]
