"""普通弃财保护：只筛选规则已给出的弃牌候选，不判断合法性或重算财飘。"""

from __future__ import annotations

from dataclasses import replace

from hangma_bot.kernel.actions import Discard, action_key

from .interface import (
    BotPolicy,
    DecisionBudget,
    DecisionPlan,
    DecisionRequest,
    RankedCandidate,
    ScorePart,
)

WHITE_DISCARD_GUARD_VERSION = "white-discard-guard-v1"


class WhiteDiscardGuardPolicy:
    """有其它未拒绝弃牌时，阻止非爆头状态下主动弃财。

    ``base_policy`` 是公开的被包装策略，供离线记录有效权重时继续读取。
    本包装器只改变评分输入副本；原始观察、规则事实和时间预算不变。
    """

    def __init__(self, base_policy: BotPolicy) -> None:
        """绑定已有策略；不创建规则引擎、时钟或外部资源。"""
        self.base_policy = base_policy

    async def choose(
        self, request: DecisionRequest, budget: DecisionBudget
    ) -> DecisionPlan:
        """筛选普通弃财后委托排序；异常、超时与取消原样交给调用方。

        爆头状态和没有其它可用弃牌的窗口原样委托。旧请求中的白板紧急
        候选仅能作为非白计划的最后退路，不能重新进入底层评分优先级。
        """
        observation = request.observation
        if (
            observation.phase != "draw"
            or observation.turn_seat != observation.seat
            or observation.rule_state.baotou
        ):
            return await self.base_policy.choose(request, budget)

        wealth_god = observation.rule_state.wealth_god
        rejected_keys = {attempt.action_key for attempt in request.rejected_attempts}
        non_white_keys = {
            candidate.action_key
            for candidate in request.rules.legal_candidates
            if isinstance(candidate.action, Discard)
            and candidate.action.tile != wealth_god
            and candidate.action_key == action_key(candidate.action)
            and candidate.action_key not in rejected_keys
        }
        if not non_white_keys:
            return await self.base_policy.choose(request, budget)

        def is_white_discard(action: object) -> bool:
            return isinstance(action, Discard) and action.tile == wealth_god

        legal_candidates = tuple(
            candidate
            for candidate in request.rules.legal_candidates
            if not is_white_discard(candidate.action)
        )
        emergency = request.rules.emergency_candidate
        old_white_emergency = (
            emergency is not None and is_white_discard(emergency.action)
        )
        if (
            len(legal_candidates) == len(request.rules.legal_candidates)
            and not old_white_emergency
        ):
            return await self.base_policy.choose(request, budget)

        view = replace(
            request,
            rules=replace(
                request.rules,
                legal_candidates=legal_candidates,
                emergency_candidate=None if old_white_emergency else emergency,
            ),
        )
        plan = await self.base_policy.choose(view, budget)
        candidates = [
            candidate
            for candidate in sorted(plan.candidates, key=lambda item: item.rank)
            if not is_white_discard(candidate.action)
        ]
        reasons = plan.degraded_reasons + (
            f"评分保护[{WHITE_DISCARD_GUARD_VERSION}]：非爆头且有未拒绝的非财神弃牌，"
            "普通弃财不参与评分；原始规则事实保持不变",
        )

        # 旧规则可能以白板作为紧急动作。仅保留原合法集内、规范且未拒绝的
        # 同一动作；底层未给出非白计划时不能靠补白掩盖空计划等故障。
        if (
            old_white_emergency
            and emergency is not None
            and emergency.action_key == action_key(emergency.action)
            and emergency.action_key not in rejected_keys
            and any(
                candidate.action_key == emergency.action_key
                and candidate.action == emergency.action
                for candidate in request.rules.legal_candidates
            )
            and any(
                candidate.action_key in non_white_keys
                and isinstance(candidate.action, Discard)
                and candidate.action_key == action_key(candidate.action)
                for candidate in candidates
            )
        ):
            reason = (
                f"保护兼容[{WHITE_DISCARD_GUARD_VERSION}]：旧白板紧急候选仅作最后退路"
            )
            candidates.append(
                RankedCandidate(
                    action=emergency.action,
                    action_key=emergency.action_key,
                    rank=len(candidates) + 1,
                    total_score=0.0,
                    score_parts=(ScorePart("旧白板紧急退路（不参与评分）", 0.0),),
                    reasons=(reason,) + tuple(emergency.evidence),
                    is_emergency=True,
                )
            )
            reasons += (reason,)

        return replace(
            plan,
            candidates=tuple(
                replace(candidate, rank=index)
                for index, candidate in enumerate(candidates, 1)
            ),
            degraded_reasons=reasons,
        )
