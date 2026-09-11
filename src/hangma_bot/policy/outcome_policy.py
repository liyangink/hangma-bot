"""将独立的结果生产器与赛事目标接入唯一 choose 入口；默认策略不使用它。"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Callable

from hangma_bot.competition.outcome_utility import expected_utility
from hangma_bot.kernel.actions import Hu
from hangma_bot.kernel.outcome_codec import observation_key
from hangma_bot.kernel.outcomes import (
    HandObjectiveKind, HandOutcomeObjective, OutcomeBatch, OutcomeDecisionTrace, OutcomeModelVersion,
)
from hangma_bot.learning.outcome_model import OutcomePredictor, OutcomeQuery
from .interface import BotPolicy, DecisionBudget, DecisionPlan, DecisionRequest, ScorePart


class OutcomePolicy:
    """先建立保底和基线，仅在整批结果通过复核且预算充足时替换评分。

    本版保留合法立即胡；缺覆盖、目标未知、结果不兼容时不混合不同量纲。
    生产器须合作取消，不能把同步长计算放入事件循环后声称超时可抢占。
    """

    def __init__(self, *, baseline: BotPolicy, fallback: BotPolicy,
                 predictor: OutcomePredictor | None, expected_version: OutcomeModelVersion,
                 runtime_rules_hash: str,
                 objective: Callable[[DecisionRequest], HandOutcomeObjective],
                 monotonic: Callable[[], float]) -> None:
        """注入实际依赖和单调时钟；不在模块内创建模型、策略或记录器。"""
        if not isinstance(expected_version, OutcomeModelVersion):
            raise ValueError("expected_version 必须是固定模型版本")
        self._baseline, self._fallback = baseline, fallback
        self._predictor, self._version = predictor, expected_version
        self._runtime_rules_hash = runtime_rules_hash
        self._objective, self._monotonic = objective, monotonic

    async def choose(self, request: DecisionRequest, budget: DecisionBudget) -> DecisionPlan:
        """返回原基线或全候选结果计划；失败原因进入结构化审计，不提交动作。"""
        plan = await self._fallback.choose(request, budget)
        objective = None
        batch = None

        def finish(status: str, reason: str) -> DecisionPlan:
            notes = plan.degraded_reasons + (("outcome:" + reason,) if status == "fallback" else ())
            return replace(plan, degraded_reasons=notes,
                           outcome_trace=OutcomeDecisionTrace(status, reason, self._version, objective, batch))

        def remaining() -> float:
            return budget.enhancement_deadline_monotonic - self._monotonic()

        if remaining() <= 0:
            return finish("fallback", "budget_exhausted")
        try:
            baseline_plan = await asyncio.wait_for(self._baseline.choose(request, budget), timeout=remaining())
        except TimeoutError:
            return finish("fallback", "baseline_timeout")
        except Exception:
            return finish("fallback", "baseline_error")
        # 空/过期/错动作基线不能成为模型的承载计划；保底在调用前已经建立。
        legal = {c.action_key: c.action for c in request.rules.legal_candidates}
        rejected = {a.action_key for a in request.rejected_attempts}
        if not isinstance(baseline_plan, DecisionPlan):
            return finish("fallback", "baseline_invalid")
        keys = [c.action_key for c in baseline_plan.candidates]
        if (baseline_plan.decision_id != request.decision_id
                or baseline_plan.window_key != request.window_key
                or baseline_plan.based_on_authoritative_seq != request.observation.snapshot_seq
                or len(set(keys)) != len(keys)
                or (not keys and bool(set(legal) - rejected))
                or any(c.action_key in rejected or legal.get(c.action_key) != c.action
                       or c.rank != i + 1 for i, c in enumerate(baseline_plan.candidates))):
            return finish("fallback", "baseline_invalid")
        plan = baseline_plan
        if remaining() <= 0:
            return finish("fallback", "budget_exhausted")
        if not plan.candidates:
            return finish("bypassed", "empty_plan")
        if any(isinstance(c.action, Hu) for c in plan.candidates):
            return finish("bypassed", "immediate_hu")
        if self._predictor is None:
            return finish("fallback", "model_missing")
        if self._runtime_rules_hash != self._version.rules_hash:
            return finish("fallback", "runtime_rules_mismatch")
        try:
            objective = self._objective(request)
            if not isinstance(objective, HandOutcomeObjective):
                objective = None
                return finish("fallback", "objective_invalid")
            if objective.kind is HandObjectiveKind.UNAVAILABLE:
                return finish("fallback", "objective_unavailable")
            if objective.seat != request.observation.seat:
                return finish("fallback", "objective_seat_mismatch")
            if request.rules.ruleset_version != self._version.ruleset_version:
                return finish("fallback", "rules_version_mismatch")
            candidates = tuple(c for c in request.rules.legal_candidates if c.action_key not in rejected)
            query = OutcomeQuery(request.observation, candidates, request.rules.ruleset_version)
            # 不向仅保留子集的基线添加新执行候选；先恢复完整可靠基线再增强。
            if {c.action_key for c in candidates} != {c.action_key for c in plan.candidates}:
                return finish("fallback", "baseline_coverage_mismatch")
            key = observation_key(request.observation)
            if remaining() <= 0:
                return finish("fallback", "budget_exhausted")
            result = await asyncio.wait_for(self._predictor(query), timeout=remaining())
            if remaining() <= 0:
                return finish("fallback", "model_timeout")
            if not isinstance(result, OutcomeBatch):
                return finish("fallback", "model_result_invalid")
            batch = result
            if batch.version != self._version:
                return finish("fallback", "model_version_mismatch")
            if batch.observation_key != key:
                return finish("fallback", "stale_observation")
            by_key = {c.action_key: c.estimate for c in batch.candidates}
            if set(by_key) != {c.action_key for c in candidates}:
                return finish("fallback", "candidate_coverage_mismatch")
            scores = {key: expected_utility(estimate, objective) for key, estimate in by_key.items()}
            if remaining() <= 0:
                return finish("fallback", "budget_exhausted")
        except TimeoutError:
            return finish("fallback", "model_timeout")
        except ValueError:
            return finish("fallback", "result_or_objective_incompatible")
        except Exception:
            return finish("fallback", "model_or_objective_error")
        ranked = sorted(plan.candidates, key=lambda c: (-scores[c.action_key], c.action_key))
        # 基线的启发式分不与积分/概率相加；保留动作与紧急标记，完整记录替换来源。
        enhanced = replace(plan, candidates=tuple(
            replace(c, rank=index + 1, total_score=scores[c.action_key],
                    score_parts=(ScorePart("outcome_" + objective.kind.value, scores[c.action_key]),),
                    reasons=c.reasons + ("候选结果按单局目标重新评分：" + objective.source,))
            for index, c in enumerate(ranked)
        ))
        if remaining() <= 0:
            return finish("fallback", "budget_exhausted")
        plan = enhanced
        return finish("applied", "outcome_utility")
