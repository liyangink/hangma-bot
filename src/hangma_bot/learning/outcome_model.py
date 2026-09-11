"""候选结果接入的真实最小生产器，不是已训练的泛化网络。

经验表汇总同一可见观察下的逐候选完整续打样本，用于标签复核、
离线结果重放和跨线契约。未覆盖观察/候选保持缺失，不向新局面外推。
"""

from __future__ import annotations

import asyncio
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Awaitable, Callable

from hangma_bot.hangma.interface import RuleCandidate
from hangma_bot.kernel.actions import action_key
from hangma_bot.kernel.observation import PlayerObservation
from hangma_bot.kernel.outcome_codec import observation_key
from hangma_bot.kernel.outcomes import (
    CandidateOutcome, JointOutcome, MeanOutcome, OutcomeAtom, OutcomeBatch,
    OutcomeModelVersion, SeatFloatVector,
)


@dataclass(frozen=True)
class OutcomeQuery:
    """结果生产器的可见输入；候选已由规则确认，排除了明确拒绝动作。"""

    observation: PlayerObservation  # 不含教师世界或赛后标签
    candidates: tuple[RuleCandidate, ...]  # 携带共享规则事实，顺序不影响输出身份
    ruleset_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.observation, PlayerObservation):
            raise ValueError("observation 必须为 PlayerObservation")
        if not isinstance(self.ruleset_version, str) or not self.ruleset_version.strip():
            raise ValueError("ruleset_version 必须非空")
        if not isinstance(self.candidates, tuple) or any(not isinstance(c, RuleCandidate) for c in self.candidates):
            raise ValueError("candidates 必须为规则候选元组")
        keys = [c.action_key for c in self.candidates]
        if len(set(keys)) != len(keys) or any(c.action_key != action_key(c.action) for c in self.candidates):
            raise ValueError("候选动作键重复或不匹配")


# 函数接触面，不预建单实现的模型注册协议。异步生产器必须合作取消；
# 同步网络计算需自行约束批次工作量/隔离执行，不能靠 wait_for 抢占。
OutcomePredictor = Callable[[OutcomeQuery], Awaitable[OutcomeBatch]]


@dataclass(frozen=True)
class CandidateOutcomeSample:
    """离线样本标签：首动作前到本单局结束的四家积分，不进入学生特征。"""

    observation_key: str  # 仅做观察关联；不能用作网络输入
    action_key: str
    score_delta: SeatFloatVector  # 物理座位 0—3，桌内积分

    def __post_init__(self) -> None:
        for value in (self.observation_key, self.action_key):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("样本观察/动作键必须非空")
        MeanOutcome(self.score_delta)  # 复用有限性和零和约束，不重写结算


class EmpiricalOutcomeModel:
    """在构建时汇总逐候选样本，推理只查询冻结经验表；不访问文件或世界。"""

    def __init__(self, samples: tuple[CandidateOutcomeSample, ...], version: OutcomeModelVersion, *, output: str = "joint") -> None:
        """构建经验表；output 只能是 mean/joint，版本由数据交付者显式提供。"""
        if not isinstance(version, OutcomeModelVersion) or output not in ("mean", "joint"):
            raise ValueError("经验模型版本或输出类型错误")
        if not isinstance(samples, tuple) or any(not isinstance(s, CandidateOutcomeSample) for s in samples):
            raise ValueError("samples 必须为标签元组")
        grouped = defaultdict(list)
        for sample in samples:
            grouped[(sample.observation_key, sample.action_key)].append(sample.score_delta)
        self._version = version
        self._table = {}
        for key, values in grouped.items():
            if output == "mean":
                estimate = MeanOutcome(tuple(math.fsum(v[seat] / len(values) for v in values) for seat in range(4)))
            else:
                counts = Counter(values)
                estimate = JointOutcome(tuple(OutcomeAtom(scores, count / len(values)) for scores, count in sorted(counts.items())))
            self._table[key] = estimate

    async def predict(self, query: OutcomeQuery) -> OutcomeBatch:
        """批量返回已覆盖候选；规则版本错误抛 ValueError，缺覆盖不填零。"""
        await asyncio.sleep(0)
        if query.ruleset_version != self._version.ruleset_version:
            raise ValueError("经验表规则版本不匹配")
        key = observation_key(query.observation)
        return OutcomeBatch(key, self._version, tuple(
            CandidateOutcome(candidate.action_key, self._table[(key, candidate.action_key)])
            for candidate in query.candidates if (key, candidate.action_key) in self._table
        ))
