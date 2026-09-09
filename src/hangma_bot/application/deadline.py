"""单调时钟接缝、动作窗口预算分配和有界退避策略。

为什么单独成文件：动作截止时间属于应用层职责，官方适配器只负责在自己的
请求预算内执行；测试要求注入单调时钟而不是真实长等待（见 tests/AGENTS.md）。
""" 

from __future__ import annotations

import time
from dataclasses import dataclass, field
from math import isfinite, ulp
from typing import Optional, Protocol

from hangma_bot.policy.interface import DecisionBudget
from hangma_bot.application.contracts import DEFAULT_POST_NETWORK_RESERVE_SEC


class RuntimeClock(Protocol):
    """应用层唯一时间来源；禁止业务代码直接调用 time 模块。"""

    def now(self) -> float:
        """返回本机单调时钟秒数；只用于预算和截止时间判断。"""

        ...

    def unix_ms(self) -> int:
        """返回墙上时钟 Unix 毫秒；只用于审计记录，不用于截止时间。"""

        ...

    def budget_wait_seconds(self, deadline_monotonic: float) -> float:
        """把单调预算换算成本次真实异步等待秒数；到点返回 0。

        测试时钟允许按比例缩放（例如 1%），使“策略挂起到截止时间”等
        场景不需要真实等待数秒。
        """

        ...


class SystemClock:
    """生产实现：单调时钟 + 墙上时钟，等待换算比例为 1。"""

    wait_scale = 1.0

    def now(self) -> float:
        return time.monotonic()

    def unix_ms(self) -> int:
        return int(time.time() * 1000)

    def budget_wait_seconds(self, deadline_monotonic: float) -> float:
        return max(0.0, deadline_monotonic - self.now()) * self.wait_scale


class ManualClock:
    """测试用可推进时钟；默认 1% 真实等待换算，避免测试真实长等待。"""

    def __init__(
        self,
        start_monotonic: float = 100.0,
        start_unix_ms: int = 1_800_000_000_000,
        wait_scale: float = 0.01,
    ) -> None:
        self._monotonic = start_monotonic
        self._unix_ms = start_unix_ms
        self.wait_scale = wait_scale

    def now(self) -> float:
        return self._monotonic

    def unix_ms(self) -> int:
        return self._unix_ms

    def budget_wait_seconds(self, deadline_monotonic: float) -> float:
        return max(0.0, deadline_monotonic - self._monotonic) * self.wait_scale

    def advance(self, seconds: float) -> None:
        """推进单调时钟，同时按同比例推进墙上时钟，保持两个时基一致。"""

        self._monotonic += seconds
        self._unix_ms += int(seconds * 1000)


@dataclass(frozen=True)
class BudgetPolicy:
    """先扣固定动作网络余量，再分配计算与保底期限。

    三段语义见接口协议第 3 节：增强计算最早停止，保底选择次之，
    比例仅分配可计算时间，网络余量不随窗口剩余时间缩小。
    这里接受适配器的单调截止，不负责校正两端墙钟。
    """

    enhancement_fraction: float = 0.5
    fallback_fraction: float = 0.7
    post_reserve_seconds: float = DEFAULT_POST_NETWORK_RESERVE_SEC

    def __post_init__(self) -> None:
        if not (0.0 < self.enhancement_fraction <= self.fallback_fraction):
            raise ValueError("预算比例必须满足 0 < 增强 <= 保底")
        if not self.fallback_fraction < 1.0:
            raise ValueError("保底比例必须小于1，为提交前复核留出计算时间")
        if not isfinite(self.post_reserve_seconds) or self.post_reserve_seconds <= 0:
            raise ValueError("动作网络余量必须为有限正秒数")

    def build(
        self,
        received_at_monotonic: float,
        timeout_seconds: float,
        expires_at_monotonic: Optional[float] = None,
    ) -> DecisionBudget:
        """按收到窗口时的剩余时间分配预算；未知官方截止才使用配置时长。

        输入均为本机单调时钟秒或持续秒数，不能传 Unix 时间。已过期窗口
        或不足固定网络余量时返回零预算，不能为旧状态缩短网络余量。
        """

        if not isfinite(received_at_monotonic) or not isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("预算需要有限接收时刻与正持续秒数")
        span = timeout_seconds
        if expires_at_monotonic is not None:
            if not isfinite(expires_at_monotonic):
                raise ValueError("预算截止必须是有限单调时钟秒数")
            span = max(0.0, min(span, expires_at_monotonic - received_at_monotonic))
        span = max(0.0, span - self.post_reserve_seconds)
        # 绝对单调秒相减可能把“恰好只剩网络预算”变成一个浮点尾数。
        # 只容忍该时基的两倍表示精度，不把纳秒级舍入误差当成可发预算。
        if span <= 2 * max(ulp(received_at_monotonic), ulp(received_at_monotonic + span)):
            span = 0.0

        return DecisionBudget(
            enhancement_deadline_monotonic=received_at_monotonic
            + span * self.enhancement_fraction,
            fallback_deadline_monotonic=received_at_monotonic
            + span * self.fallback_fraction,
            latest_send_at_monotonic=received_at_monotonic
            + span,
        )

    def tighten(
        self,
        original: DecisionBudget,
        received_at_monotonic: float,
        timeout_seconds: float,
        expires_at_monotonic: Optional[float],
    ) -> DecisionBudget:
        """409 同窗口刷新只允许收紧原预算；缺少新截止时原样保留。"""

        if expires_at_monotonic is None:
            return original
        refreshed = self.build(received_at_monotonic, timeout_seconds, expires_at_monotonic)
        return DecisionBudget(
            enhancement_deadline_monotonic=min(original.enhancement_deadline_monotonic, refreshed.enhancement_deadline_monotonic),
            fallback_deadline_monotonic=min(original.fallback_deadline_monotonic, refreshed.fallback_deadline_monotonic),
            latest_send_at_monotonic=min(original.latest_send_at_monotonic, refreshed.latest_send_at_monotonic),
        )


@dataclass
class BoundedBackoff:
    """有限次数的指数退避；耗尽后返回 None 表示放弃快速重试。

    监督策略约束：禁止无上限快速重启（application 模块规范），
    因此每次“尝试机会”都必须显式领号，耗尽即转分类处置。
    """

    base_delay_seconds: float = 0.5
    factor: float = 2.0
    max_delay_seconds: float = 8.0
    max_attempts: int = 5
    # 每实例独立的已用次数；不是类级共享状态。
    _attempts: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.base_delay_seconds <= 0 or self.factor < 1.0:
            raise ValueError("退避基数必须为正且因子不小于 1")
        if self.max_attempts <= 0:
            raise ValueError("退避次数必须为正")

    def next_delay_or_none(self) -> Optional[float]:
        """领取下一次重试的延迟；超过上限返回 None。"""

        if self._attempts >= self.max_attempts:
            return None
        delay = min(
            self.base_delay_seconds * (self.factor ** self._attempts),
            self.max_delay_seconds,
        )
        self._attempts += 1
        return delay

    def reset(self) -> None:
        """取得权威进展后清零，重新获得完整重试预算。"""

        self._attempts = 0
