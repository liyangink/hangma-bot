"""序列策略网络的有界线上包装；先保底、后基线、最后尝试模型。

本模块是唯一使用该模型的线上决策接缝：对外仍只有
``BotPolicy.choose(DecisionRequest, DecisionBudget)``，不读取 `WorldState`、
不提交 HTTP、不访问训练目录。
"""
from __future__ import annotations

import asyncio
from dataclasses import asdict, replace
import math

import torch

from hangma_bot.hangma.interface import RuleCompleteness
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.outcome_codec import observation_key
from hangma_bot.learning.sequence_encoding import (
    SEQUENCE_INPUT_CONTRACT_VERSION, SequenceInput, encode_sequence_input,
)
from hangma_bot.learning.sequence_model_artifact import SequenceModelArtifact
from hangma_bot.learning.sequence_policy import SequenceActorCritic, batch_sequence_inputs
from .interface import BotPolicy, DecisionBudget, DecisionPlan, DecisionRequest, ScorePart


class SequenceModelPolicy:
    """全部合法候选由单个独立网络排序，其余行为沿用可靠基线。

    失败、超时、规则/制品身份不符或预算不足时恢复基线的候选顺序与原评分，
    并写入结构化 `degraded_reasons`。模型不参与合法动作生成，紧急动作与
    已拒绝动作过滤始终由基线与应用层保持。
    """

    def __init__(self, *, baseline: BotPolicy, fallback: BotPolicy,
                 network: SequenceActorCritic, artifact: SequenceModelArtifact,
                 runtime_rules: RuleConfig, monotonic) -> None:
        """注入实际依赖；不在模块内创建模型、策略或记录器。

        ``runtime_rules`` 必须来自实际运行配置，用于与制品声明的规则逐项核对。
        """

        self._baseline, self._fallback = baseline, fallback
        self._network = network.eval()
        self._artifact, self._rules = artifact, runtime_rules
        self._monotonic = monotonic

    @property
    def model_id(self) -> str:
        """稳定模型标识，供审计关联；不是文件路径。"""

        return self._artifact.model_id

    async def choose(self, request: DecisionRequest, budget: DecisionBudget) -> DecisionPlan:
        """保持拒绝过滤与紧急动作；不因模型延长原单调时钟截止时间。"""

        plan = await self._fallback.choose(request, budget)

        def remaining() -> float:
            return budget.enhancement_deadline_monotonic - self._monotonic()

        def fail(reason: str) -> DecisionPlan:
            return replace(plan, degraded_reasons=plan.degraded_reasons + ("sequence_model:" + reason,))

        if remaining() <= 0:
            return fail("budget_exhausted")
        try:
            baseline = await asyncio.wait_for(self._baseline.choose(request, budget), remaining())
        except TimeoutError:
            return fail("baseline_timeout")
        except Exception:
            return fail("baseline_error")
        rejected = {item.action_key for item in request.rejected_attempts}
        legal = {item.action_key: item.action for item in request.rules.legal_candidates
                 if item.action_key not in rejected}
        if (not isinstance(baseline, DecisionPlan) or baseline.decision_id != request.decision_id
                or baseline.window_key != request.window_key
                or baseline.based_on_authoritative_seq != request.observation.snapshot_seq
                or not baseline.candidates
                or len({c.action_key for c in baseline.candidates}) != len(baseline.candidates)
                or any(legal.get(c.action_key) != c.action or c.rank != index + 1
                       for index, c in enumerate(baseline.candidates))):
            return fail("baseline_invalid")
        plan = baseline
        if remaining() <= 0:
            return fail("budget_exhausted")
        # 规则不完整或版本不符时模型输入口径与训练不同，恢复基线全部行为。
        if (request.rules.completeness != RuleCompleteness.COMPLETE
                or request.rules.ruleset_version != self._rules.ruleset_version
                or asdict(self._rules) != self._artifact.rule_config):
            return fail("model_or_rules_unavailable")
        # 权威快照及后续连续增量是正常输入；本地原事件归档覆盖不是准入条件。
        if request.observation.observation_issues:
            return fail("observation_issues")
        if set(legal) != {c.action_key for c in plan.candidates}:
            return fail("baseline_coverage")
        candidates = tuple(item for item in request.rules.legal_candidates
                           if item.action_key not in rejected)
        if len(candidates) < 2:
            # 唯一合法候选是强制动作，不运行网络也不改变任何评分。
            return plan
        try:
            logits = await asyncio.wait_for(self._predict(request, candidates), remaining())
            if remaining() <= 0:
                return fail("budget_exhausted")
            if set(logits) != set(legal) or any(not math.isfinite(v) for v in logits.values()):
                return fail("invalid_logits")
            ranked = sorted(plan.candidates, key=lambda c: (-logits[c.action_key], c.action_key))
            enhanced = replace(plan, candidates=tuple(
                replace(c, rank=index + 1, total_score=logits[c.action_key],
                        score_parts=(ScorePart("sequence_model_logit", logits[c.action_key]),),
                        reasons=("全候选独立策略网络，偏好不是积分", "model_id=" + self.model_id,
                                 "input_contract: " + SEQUENCE_INPUT_CONTRACT_VERSION))
                for index, c in enumerate(ranked)))
            return enhanced if remaining() > 0 else fail("budget_exhausted")
        except TimeoutError:
            return fail("model_timeout")
        except Exception:
            return fail("model_error")

    async def _predict(self, request: DecisionRequest, candidates) -> dict:
        """在线程中编码并前向，避免阻塞事件循环。

        ``wait_for`` 不能抢占已开始的同步计算，因此本函数的阻塞上界是
        单次编码加一次前向的实测最坏值（512 行公开历史、128 个候选约
        十一毫秒），调用方据此保留 ``post_network_reserve_sec`` 余量。
        """

        def run() -> dict:
            encoded: SequenceInput = encode_sequence_input(request.observation, candidates)
            with torch.inference_mode():
                logits, _ = self._network(batch_sequence_inputs((encoded,)))
            values = logits[0, :len(encoded.action_keys)].tolist()
            if len(values) != len(encoded.action_keys):
                raise ValueError("模型输出长度与候选数不符")
            return dict(zip(encoded.action_keys, values, strict=True))

        return await asyncio.to_thread(run)


__all__ = ["SequenceModelPolicy"]
