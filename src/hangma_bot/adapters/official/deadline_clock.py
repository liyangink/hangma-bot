"""由官方当前阶段估计期限映射；不访问墙钟、网络或牌局策略。

指南v27（2026-09-09）：当前阶段的剩余时间在0至配置窗口长度L之间。
GET在本机单调S开始、R完成，快照Unix截止D，故映射K满足
D-L-R <= K <= D-S。成立前提是快照phase与截止一致；冲突即失效重学。
"""
from collections import deque
from dataclasses import dataclass
import math

DEADLINE_CLOCK_VERSION = 'snapshot-interval-v1'


@dataclass(frozen=True)
class DeadlineInterval:
    """同一官方时刻在本机单调时钟上的区间，单位秒。"""
    earliest: float  # 提交只能使用较早边界，再扣独立的网络预算
    latest: float  # 等待阶段切换使用较晚边界，不能借给动作预算


class DeadlineClock:
    """每用户共享的有界样本账，最多256项，不为校准额外查询。

    两份以上样本交集宽度<=100ms时使用，60秒后过期；每秒向两边扩张1ms
    容纳漂移，额外1ms覆盖官方整数毫秒取整。不是任意时钟跳变的保证。
    """
    def __init__(self):
        self._samples = deque(maxlen=256)
        self._resets = 0

    def observe(self, *, deadline_unix_ms, duration_sec, started_at, completed_at):
        """吸收已验证的活跃快照和对应请求的单调秒；畸形输入不生成样本。"""
        if (type(deadline_unix_ms) is not int or deadline_unix_ms <= 0
                or not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                           and math.isfinite(v) for v in (duration_sec, started_at, completed_at))
                or duration_sec <= 0 or completed_at < started_at):
            return False
        # 请求可乱序完成；同用户同一单调钟下按实际完成顺序吸收。
        if self._samples and completed_at < self._samples[-1][0]:
            return False
        d = deadline_unix_ms / 1000
        sample = (completed_at, d - duration_sec - completed_at - .001,
                  d - started_at + .001)
        self._samples.append(sample)
        lo, hi = self._range(completed_at)
        if lo > hi:
            self._samples.clear()
            self._samples.append(sample)
            self._resets += 1
        return True

    def _range(self, now):
        while self._samples and now - self._samples[0][0] > 60:
            self._samples.popleft()
        lo, hi = -math.inf, math.inf
        for at, lower, upper in self._samples:
            drift = max(0, now - at) * .001
            lo, hi = max(lo, lower - drift), min(hi, upper + drift)
        return lo, hi

    def deadline(self, deadline_unix_ms, now):
        """返回可用映射区间；不足、过宽、失效时返回None交由已有路径保底。"""
        if not math.isfinite(now):
            return None
        lo, hi = self._range(now)
        if len(self._samples) < 2 or hi < lo or hi - lo > .1:
            return None
        return DeadlineInterval(deadline_unix_ms / 1000 - hi,
                                deadline_unix_ms / 1000 - lo)

    def metadata(self, now):
        """返回本机单调采样时刻的估计状态，供审计，不包含凭证或手牌。"""
        lo, hi = self._range(now)
        return {'version': DEADLINE_CLOCK_VERSION, 'samples': len(self._samples),
                'ready': self.deadline(0, now) is not None,
                'width_sec': hi-lo if math.isfinite(hi-lo) else None,
                'resets': self._resets}
