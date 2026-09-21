"""离线反事实续打的首动作干预器。

本模块只在离线评估中使用。它在一个已经冻结的动作窗口把规则确认合法的
指定动作提升到计划首位，随后所有窗口继续委托原策略。它不读取
``WorldState``，不产生新动作，也不改变线上 ``BotPolicy`` 接口。
"""

from __future__ import annotations

from typing import Any

from hangma_bot.kernel.actions import WindowKey
from hangma_bot.policy.interface import DecisionBudget, DecisionPlan, DecisionRequest, RankedCandidate


class ForceFirstActionPolicy:
    """只在指定窗口强制一次合法动作，随后恢复委托策略。

    ``target_window`` 绑定场次、局号、事件序号、阶段和座位；窗口不完全相等
    时绝不干预。指定动作必须同时存在于规则候选和委托策略的完整计划中，
    否则抛错让该反事实臂失效，避免用合成动作或保底动作冒充干预成功。
    """

    def __init__(
        self,
        inner: Any,
        *,
        target_window: WindowKey,
        forced_action_key: str,
        policy_id: str,
    ) -> None:
        if not isinstance(target_window, WindowKey):
            raise TypeError("target_window 必须是 WindowKey")
        if not isinstance(forced_action_key, str) or not forced_action_key:
            raise ValueError("forced_action_key 必须是非空动作键")
        if not isinstance(policy_id, str) or not policy_id:
            raise ValueError("policy_id 必须是非空字符串")
        self._inner = inner
        self._target_window = target_window
        self._forced_action_key = forced_action_key
        self.policy_id = policy_id
        self.force_count = 0

    async def choose(
        self,
        request: DecisionRequest,
        budget: DecisionBudget,
    ) -> DecisionPlan:
        """返回委托计划；首次命中目标窗口时把指定合法候选稳定提升到首位。"""

        plan = await self._inner.choose(request, budget)
        if request.window_key != self._target_window or self.force_count:
            return plan

        legal_keys = {candidate.action_key for candidate in request.rules.legal_candidates}
        if self._forced_action_key not in legal_keys:
            raise ValueError(
                "反事实首动作不在目标窗口合法候选中：" + self._forced_action_key
            )
        forced = next(
            (
                candidate
                for candidate in plan.candidates
                if candidate.action_key == self._forced_action_key
            ),
            None,
        )
        if forced is None:
            raise ValueError(
                "反事实首动作不在委托策略完整计划中：" + self._forced_action_key
            )

        ordered = (forced,) + tuple(
            candidate
            for candidate in plan.candidates
            if candidate.action_key != self._forced_action_key
        )
        reranked = tuple(
            RankedCandidate(
                action=candidate.action,
                action_key=candidate.action_key,
                rank=index + 1,
                total_score=candidate.total_score,
                score_parts=candidate.score_parts,
                reasons=candidate.reasons,
                is_emergency=candidate.is_emergency,
                score_trace=candidate.score_trace,
            )
            for index, candidate in enumerate(ordered)
        )
        self.force_count += 1
        return DecisionPlan(
            decision_id=plan.decision_id,
            window_key=plan.window_key,
            based_on_authoritative_seq=plan.based_on_authoritative_seq,
            revision=plan.revision,
            candidates=reranked,
            degraded_reasons=plan.degraded_reasons
            + (
                "offline_counterfactual_force_first:"
                + self._forced_action_key,
            ),
            outcome_trace=plan.outcome_trace,
        )


__all__ = ["ForceFirstActionPolicy"]
