"""紧急保底策略：只输出规则紧急候选，不做任何增强计算。

应用层在主策略启动前调用本策略得到保底计划；
本策略不读取时钟、不检查预算、不抛出可预期异常，
保证任何输入下都能立即给出可审计的保守计划。
"""

from __future__ import annotations

from typing import Tuple

from .interface import (
    DecisionBudget,
    DecisionPlan,
    DecisionRequest,
    RankedCandidate,
    ScorePart,
)


class SafeFallbackPolicy:
    """第一阶段保底策略：候选为空时输出空计划并说明原因。"""

    async def choose(
        self,
        request: DecisionRequest,
        budget: DecisionBudget,
    ) -> DecisionPlan:
        """立即返回紧急保底计划；budget 参数仅满足协议，不参与计算。"""

        rules = request.rules
        rejected_keys = frozenset(item.action_key for item in request.rejected_attempts)
        reasons = ["保底策略：不运行任何增强评分，仅使用规则紧急候选"]
        for issue in rules.issues:
            reasons.append("规则降级[{area}]：{reason}".format(area=issue.area, reason=issue.reason))

        candidates: Tuple[RankedCandidate, ...] = ()
        emergency = rules.emergency_candidate
        if emergency is None:
            reasons.append("规则未提供紧急候选，保底计划为空")
        elif emergency.action_key in rejected_keys:
            reasons.append("紧急候选已被官方拒绝：{key}".format(key=emergency.action_key))
        else:
            candidates = (
                RankedCandidate(
                    action=emergency.action,
                    action_key=emergency.action_key,
                    rank=1,
                    total_score=1.0,
                    score_parts=(ScorePart("紧急保底", 1.0),),
                    reasons=("规则紧急路径提供的保底动作",) + tuple(emergency.evidence),
                    is_emergency=True,
                ),
            )

        return DecisionPlan(
            decision_id=request.decision_id,
            window_key=request.window_key,
            based_on_authoritative_seq=request.observation.snapshot_seq,
            revision=len(request.rejected_attempts) + 1,
            candidates=candidates,
            degraded_reasons=tuple(reasons),
        )
