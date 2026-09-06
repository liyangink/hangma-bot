"""V2 可比牌效：沿用 V1 可靠排序，统一过牌与吃碰的等待基准。

输出完整 DecisionPlan，不执行提交；候选一律来自 RuleAnalysis，
本策略不声明任何动作合法。超时、输入异常时抛出可捕获错误，
由应用层切换到已经准备好的紧急保底计划。
"""

from __future__ import annotations

import asyncio
import time
from typing import Callable, List, Optional, Set, Tuple

from hangma_bot.hangma.interface import RuleCandidate, RuleCompleteness
from hangma_bot.kernel.actions import Hu, Pass, action_key

from .errors import PolicyTimeoutError
from .evaluation_v2 import build_context, score_candidates, has_waiting_baseline
from .interface import (
    DecisionBudget,
    DecisionPlan,
    DecisionRequest,
    RankedCandidate,
)
from .weights_v1 import DEFAULT_WEIGHTS_V1, HeuristicWeightsV1


class ComparableHeuristicPolicyV2:
    """候选 V2：先合法胡，再按可比等待牌效排序；缺基线则以合法过牌退路。

    同输入同配置输出逐字节相同；每一步评分在增强截止时间前完成，
    超时立即抛 PolicyTimeoutError，不吞掉时间预算。
    """

    def __init__(
        self,
        weights: HeuristicWeightsV1 = DEFAULT_WEIGHTS_V1,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        """绑定不可变权重与单调时钟；时钟仅用于截止时间判断，不影响评分。"""

        if not isinstance(weights, HeuristicWeightsV1):
            raise TypeError("V2 复用冻结的 HeuristicWeightsV1 配置")
        self._weights = weights
        self._monotonic = monotonic

    async def _check_deadline(self, budget: DecisionBudget) -> None:
        """先让出事件循环再检查截止时间。

        让出点保证应用层的 asyncio.wait_for 能在保底截止时间抢占
        本协程（专家审查 F1）；超过增强截止时间立即失败，
        应用层随后使用紧急保底计划。
        """

        await asyncio.sleep(0)
        now = self._monotonic()
        if now > budget.enhancement_deadline_monotonic:
            raise PolicyTimeoutError(
                "增强计算超过截止时间：单调时钟 {now:.3f} > {deadline:.3f}".format(
                    now=now, deadline=budget.enhancement_deadline_monotonic
                )
            )

    async def choose(
        self,
        request: DecisionRequest,
        budget: DecisionBudget,
    ) -> DecisionPlan:
        """给规则候选排序并返回完整计划；不访问网络、文件或完整世界状态。"""

        await self._check_deadline(budget)

        rules = request.rules
        rejected_keys = frozenset(item.action_key for item in request.rejected_attempts)
        notes: List[str] = []
        audit_reasons: List[str] = []

        for issue in rules.issues:
            audit_reasons.append("规则降级[{area}]：{reason}".format(area=issue.area, reason=issue.reason))
        if rules.completeness == RuleCompleteness.DEGRADED:
            audit_reasons.append("规则分析不完整（DEGRADED）：策略按保守排序继续")
        if request.observation.rule_state.catch_play:
            audit_reasons.append("抓打圈生效：排序仅在规则允许的硬约束候选内进行")

        seen: Set[str] = set()
        intake: List[RuleCandidate] = []
        for candidate in rules.legal_candidates:
            key = candidate.action_key
            if key in rejected_keys:
                audit_reasons.append("过滤已拒绝候选：{key}".format(key=key))
                continue
            if key in seen:
                audit_reasons.append("过滤重复候选：{key}".format(key=key))
                continue
            try:
                canonical = action_key(candidate.action)
            except TypeError:
                audit_reasons.append("过滤未知动作类型候选：{key}".format(key=key))
                continue
            if canonical != key:
                audit_reasons.append("过滤动作键不一致候选：{key}".format(key=key))
                continue
            seen.add(key)
            intake.append(candidate)

        emergency = rules.emergency_candidate
        emergency_key: Optional[str] = emergency.action_key if emergency is not None else None
        if emergency_key is not None and emergency_key in rejected_keys:
            notes.append("紧急候选已被官方拒绝：{key}".format(key=emergency_key))
        if emergency is None and rules.legal_candidates:
            notes.append("规则未提供紧急候选，主策略计划未包含保底动作")

        candidates: Tuple[RankedCandidate, ...] = ()
        if intake:
            observation = request.observation
            context = build_context(observation)
            scored = await score_candidates(
                tuple(intake),
                context,
                self._weights,
                lambda: self._check_deadline(budget),
            )
            # 只在过滤后的合法未拒过牌存在且缺基线时退路优先；合法胡永远在前。
            pass_candidates = [c for c in intake if isinstance(c.action, Pass)]
            missing_baseline = bool(pass_candidates) and not any(has_waiting_baseline(c) for c in pass_candidates)
            if missing_baseline:
                ordered = sorted(scored, key=lambda item: (
                    0 if isinstance(item.candidate.action, Hu) else 1 if isinstance(item.candidate.action, Pass) else 2,
                    item.priority, -item.total if item.priority < 2 else 0.0, item.action_key,
                ))
                audit_reasons.append("V2 缺可比等待基线：合法胡优先，其次使用未拒绝的过牌退路")
            # 未知层不比较伪牌效；没有可信候选时先用规则紧急动作。
            elif all(item.priority == 2 for item in scored):
                ordered = sorted(scored, key=lambda item: (
                    item.action_key != emergency_key, item.action_key,
                ))
                audit_reasons.append("全部候选事实未知：紧急候选优先，其余按 action_key 排列")
            else:
                ordered = sorted(scored, key=lambda item: (
                    item.priority, -item.total if item.priority < 2 else 0.0, item.action_key,
                ))
            await self._check_deadline(budget)
            candidates = tuple(
                RankedCandidate(
                    action=item.candidate.action,
                    action_key=item.action_key,
                    rank=index + 1,
                    total_score=item.total,
                    score_parts=item.parts,
                    reasons=item.reasons,
                    is_emergency=(item.action_key == emergency_key),
                )
                for index, item in enumerate(ordered)
            )
            if emergency_key is not None and emergency_key in seen:
                if not any(item.action_key == emergency_key for item in candidates):
                    # 理论上不可达的防御检查：紧急候选绝不能被排序阶段删除。
                    notes.append("防御检查：紧急候选意外缺失于计划")
        else:
            if not rules.legal_candidates:
                notes.append("规则未产生任何合法候选，计划为空")
            elif rejected_keys:
                notes.append("候选耗尽：全部合法候选均已被官方拒绝")
            else:
                notes.append("候选耗尽：全部候选被防御性过滤，计划为空")

        await self._check_deadline(budget)
        return DecisionPlan(
            decision_id=request.decision_id,
            window_key=request.window_key,
            based_on_authoritative_seq=request.observation.snapshot_seq,
            revision=len(request.rejected_attempts) + 1,
            candidates=candidates,
            degraded_reasons=tuple(audit_reasons + notes),
        )
