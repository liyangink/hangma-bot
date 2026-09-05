"""每 Token 一次的请求调度与限速（官方适配器内部实现）。

优先级（official-adapter 实施说明）：
  动作 POST(0) > 409/缺口/模糊确认(1) > 场次长轮询(2) > 排名刷新(3)。

限速依据官方约束（指南 v15，2026-09-05 变更记录）：state 轮询频率上限
16 次/秒/用户（每用户聚合，v2/v8 的 5/s→8/s 进一步放宽至 16/s）、
同一用户并发挂起轮询最多 32 个。默认令牌桶 16 令牌、每秒回填 16、并发上限 32。

取舍：令牌桶约束全部优先级（含动作 POST）。M 场并发把桶打满时动作请求
最多等待约 1/rate 秒（默认 62.5ms）；在 1 秒窗口与 0.7 秒安全余量下可接受，
且保证动作请求绝不越过官方全局限速（宁可控延迟，不冒 429 风险）。

实现说明：单线程 asyncio 事件循环内运行，无锁；等待者只在自己位于堆顶时
被授予，避免跨等待者唤醒。clock 与 sleep 均可注入，时间测试不依赖真实等待。
"""

from __future__ import annotations

import asyncio
import heapq
import math
import random
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Awaitable, Callable, List, Optional


class Priority(IntEnum):
    """请求优先级；数值越小越优先。"""

    ACTION = 0
    RECOVERY = 1
    POLL = 2
    BACKGROUND = 3


class DeadlineExceeded(Exception):
    """调度等待在预算内未获得许可；调用方必须按预算耗尽处理。"""


@dataclass(order=True)
class _Waiter:
    """等待中的请求占位；(priority, seq) 决定堆序。"""

    priority: int
    seq: int
    active: bool = field(default=True, compare=False)


class SchedulerLease:
    """调度许可；请求完成后必须 release，否则并发槽泄漏。

    release 幂等：重复调用是安全 no-op（finally 与手动释放交叠时不重复扣减）。
    """

    def __init__(self, scheduler: "RequestScheduler", priority: Priority) -> None:
        self._scheduler = scheduler
        self.priority = priority
        self._released = False

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        self._scheduler._release_slot()

    async def __aenter__(self) -> "SchedulerLease":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self.release()


class RequestScheduler:
    """同 Token 赛事与全部场次共享；跨 Token 各自独立实例。"""

    def __init__(
        self,
        *,
        rate_per_second: float = 16.0,
        burst: Optional[float] = None,
        max_concurrent: int = 32,
        clock: Callable[[], float],
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter_rng: Optional[random.Random] = None,
        poll_interval: float = 0.002,
    ) -> None:
        self._rate = float(rate_per_second)
        self._capacity = float(burst if burst is not None else rate_per_second)
        self._tokens = self._capacity
        self._last_refill = clock()
        self._max_concurrent = max_concurrent
        self._clock = clock
        self._sleep = sleep
        self._rng = jitter_rng if jitter_rng is not None else random.Random()
        self._poll_interval = poll_interval
        self._waiters: List[_Waiter] = []
        self._seq = 0
        self._active = 0
        self._cooldown_until: Optional[float] = None

    @property
    def active_count(self) -> int:
        """当前占用的并发槽数量（测试与诊断用）。"""

        return self._active

    @property
    def cooldown_remaining(self) -> float:
        """429 全局冷却剩余秒数；未冷却时为 0。"""

        now = self._clock()
        if self._cooldown_until is None or now >= self._cooldown_until:
            return 0.0
        return self._cooldown_until - now

    def _refill(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._last_refill)
        if elapsed <= 0:
            return
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now

    def _claim_if_top(self, waiter: _Waiter) -> bool:
        """当且仅当自己是当前最高优先级等待者且资源可用时授予自己。"""

        while self._waiters and not self._waiters[0].active:
            heapq.heappop(self._waiters)  # 清理已取消的等待者
        if not self._waiters or self._waiters[0] is not waiter:
            return False
        if self._active >= self._max_concurrent:
            return False
        now = self._clock()
        if self._cooldown_until is not None:
            if now < self._cooldown_until:
                return False
            self._cooldown_until = None  # 冷却结束
        if self._tokens < 1.0:
            return False
        heapq.heappop(self._waiters)
        self._tokens -= 1.0
        self._active += 1
        return True

    async def acquire(
        self,
        priority: Priority,
        deadline_monotonic: Optional[float] = None,
    ) -> SchedulerLease:
        """按优先级获取发送许可；支持异步取消与预算截止。

        deadline_monotonic 绑定动作原始预算：等待（冷却/槽竞争）不会
        超过预算，到点抛 DeadlineExceeded 而不是继续排队——保证 1 秒
        窗口内的恢复请求不会在 429 冷却上阻塞到预算外才返回。
        """

        self._seq += 1
        waiter = _Waiter(priority=int(priority), seq=self._seq)
        heapq.heappush(self._waiters, waiter)
        try:
            while True:
                if deadline_monotonic is not None:
                    remaining = deadline_monotonic - self._clock()
                    if remaining <= 0:
                        # 等号即拒：到点不得再获许可（与应用层 >= 语义一致）
                        raise DeadlineExceeded("调度等待超出预算")
                self._refill()
                if self._claim_if_top(waiter):
                    return SchedulerLease(self, priority)
                delay = self._next_chance_delay()
                if deadline_monotonic is not None:
                    delay = min(delay, remaining)
                await self._sleep(delay)
        except BaseException:
            waiter.active = False
            raise

    def _next_chance_delay(self) -> float:
        """计算下一次尝试前应等待的秒数。"""

        now = self._clock()
        if self._cooldown_until is not None and now < self._cooldown_until:
            return self._cooldown_until - now
        if self._tokens < 1.0:
            return (1.0 - self._tokens) / self._rate
        return self._poll_interval

    def _release_slot(self) -> None:
        self._active = max(0, self._active - 1)

    def note_rate_limited(self, retry_after_seconds: Optional[float]) -> None:
        """收到官方 429 后进入全局冷却；带抖动避免同批请求同步重试。

        多个在途请求先后收到 429 时取更长的冷却终点：后到的短
        Retry-After 不得缩短先前服务端明确要求的更长等待。
        """

        # 防御（W2-1）：非有限值（inf/nan）会把冷却终点推成永不结束、
        # 冻结整个 Token 的全部请求；任何来源的畸形值都按默认冷却处理。
        # 传输层已在解析处拦截（isfinite + 非负），此处是第二道防线。
        if retry_after_seconds is None or not math.isfinite(retry_after_seconds):
            retry_after_seconds = 0.5
        base = retry_after_seconds if retry_after_seconds > 0 else 0.5
        jitter = self._rng.uniform(0.0, 0.25)
        candidate = self._clock() + base + jitter
        if self._cooldown_until is None or candidate > self._cooldown_until:
            self._cooldown_until = candidate

