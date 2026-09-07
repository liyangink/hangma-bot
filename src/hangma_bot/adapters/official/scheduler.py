"""每 Token 一次的请求调度与限速（官方适配器内部实现）。

优先级（official-adapter 实施说明）：
  动作 POST(0) > 409/缺口/模糊确认(1) > 场次长轮询(2) > 排名刷新(3)。

官方依据：指南 v18 §2.3（2026-09-06 抓取）规定 state 每用户 16 次/秒，
挂起轮询最多 32 个；SSE 不占 state 频率额度，未声明 state 长轮询免计次。
工程实现采用滚动窗口，避免令牌桶突发和回填叠出同秒 31 次请求。令牌桶仅
保留用于可选的小 burst 平滑，不能突破滚动上限。动作与赛事查询不占 state
额度；全部请求共享并发槽；state 429 只冷却 state，其他来源429保守全局冷却。match 的 10/分钟另由匹配会话管理。

实现说明：单线程 asyncio 事件循环内运行，无锁；在资源可用的等待者中按
优先级授予，动作可越过被 state 额度阻塞的请求。clock 与 sleep 可注入。
"""

from __future__ import annotations

import asyncio
import heapq
import math
import random
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Awaitable, Callable, List, Optional


class Priority(IntEnum):
    """请求优先级；数值越小越优先。"""

    ACTION = 0
    RECOVERY = 1
    POLL = 2
    BACKGROUND = 3


class RequestKind(Enum):
    """适配器内部按端点区分额度；优先级不代表端点类别。"""

    STATE = "state"
    OTHER = "other"


class DeadlineExceeded(Exception):
    """调度等待在预算内未获得许可；调用方必须按预算耗尽处理。"""


@dataclass(order=True)
class _Waiter:
    """等待中的请求占位；(priority, seq) 决定堆序。"""

    priority: int
    seq: int
    request_kind: RequestKind = field(compare=False)
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
        if not math.isfinite(self._rate) or self._rate <= 0:
            raise ValueError("rate_per_second 必须为有限正数")
        if not math.isfinite(self._capacity) or self._capacity < 1:
            raise ValueError("burst 必须为至少 1 的有限数")
        if max_concurrent < 1:
            raise ValueError("max_concurrent 必须为正数")
        self._window_capacity = max(1, math.floor(self._rate))
        self._window_seconds = self._window_capacity / self._rate
        self._state_grants = deque()  # 已许可 state 的单调时钟秒；跨场次共享
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
        self._state_cooldown_until: Optional[float] = None

    @property
    def active_count(self) -> int:
        """当前占用的并发槽数量（测试与诊断用）。"""

        return self._active

    @property
    def cooldown_remaining(self) -> float:
        """所有冷却中的最长剩余秒数（诊断用）；不代表所有端点都受阻。"""

        now = self._clock()
        return max(0.0, (self._cooldown_until or now) - now,
                   (self._state_cooldown_until or now) - now)

    def _refill(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._last_refill)
        if elapsed <= 0:
            return
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now

    def _claim_if_top(self, waiter: _Waiter) -> bool:
        """只授予资源就绪的最高优先级等待者；state 额度不能阻塞其他端点。"""

        while self._waiters and not self._waiters[0].active:
            heapq.heappop(self._waiters)  # 清理已取消的等待者
        if not self._waiters:
            return False
        if self._active >= self._max_concurrent:
            return False
        now = self._clock()
        if self._cooldown_until is not None:
            if now < self._cooldown_until:
                return False
            self._cooldown_until = None  # 冷却结束
        state_ready = self._state_quota_delay() <= 0 and (
            self._state_cooldown_until is None or now >= self._state_cooldown_until)
        eligible = (w for w in self._waiters if w.active and
                    (w.request_kind is RequestKind.OTHER or state_ready))
        if min(eligible, default=None) is not waiter:
            return False
        self._waiters.remove(waiter)
        heapq.heapify(self._waiters)
        if waiter.request_kind is RequestKind.STATE:
            self._tokens -= 1.0
            self._state_grants.append(now)
        self._active += 1
        return True

    async def acquire(
        self,
        priority: Priority,
        deadline_monotonic: Optional[float] = None,
        *,
        request_kind: RequestKind = RequestKind.STATE,
    ) -> SchedulerLease:
        """按优先级获取发送许可；支持异步取消与预算截止。

        deadline_monotonic 绑定动作原始预算：等待（冷却/槽竞争）不会
        超过预算，到点抛 DeadlineExceeded 而不是继续排队——保证 1 秒
        窗口内的恢复请求不会在 429 冷却上阻塞到预算外才返回。
        request_kind 必须由调用方按实际端点传入；默认 STATE 仅兼容旧调用。
        """

        self._seq += 1
        if not isinstance(request_kind, RequestKind):
            raise ValueError("request_kind 必须为 RequestKind")
        waiter = _Waiter(priority=int(priority), seq=self._seq, request_kind=request_kind)
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
                delay = self._next_chance_delay(waiter)
                if deadline_monotonic is not None:
                    delay = min(delay, remaining)
                await self._sleep(delay)
        except BaseException:
            waiter.active = False
            raise

    def _state_quota_delay(self) -> float:
        """state 滚动计次和可选平滑桶均允许时才可发送；单位秒。"""
        now = self._clock()
        while self._state_grants and now >= self._state_grants[0] + self._window_seconds:
            self._state_grants.popleft()
        token_delay = max(0.0, (1.0 - self._tokens) / self._rate)
        window_delay = (max(0.0, self._state_grants[0] + self._window_seconds - now)
                        if len(self._state_grants) >= self._window_capacity else 0.0)
        return max(token_delay, window_delay)

    def _next_chance_delay(self, waiter: _Waiter) -> float:
        """计算下一次尝试前应等待的秒数。"""

        now = self._clock()
        if self._cooldown_until is not None and now < self._cooldown_until:
            return self._cooldown_until - now
        if waiter.request_kind is RequestKind.STATE:
            quota_delay = max(self._state_quota_delay(),
                              (self._state_cooldown_until or now) - now)
            if quota_delay > 0:
                return max(quota_delay, 1e-6)  # 避免浮点舍入导致假时钟/高频循环不前进
        return self._poll_interval

    def _release_slot(self) -> None:
        self._active = max(0, self._active - 1)

    def note_rate_limited(self, retry_after_seconds: Optional[float], *,
                          request_kind: RequestKind = RequestKind.OTHER) -> None:
        """按端点作用域冷却；state 专属429不阻塞独立的动作额度。

        未知或其他端点的429保守全局冷却；state调用方必须显式传 STATE。

        多个在途请求先后收到 429 时取更长的冷却终点：后到的短
        Retry-After 不得缩短先前服务端明确要求的更长等待。
        """

        # 防御（W2-1）：非有限值（inf/nan）会把冷却终点推成永不结束、
        # 冻结整个 Token 的全部请求；任何来源的畸形值都按默认冷却处理。
        # 传输层已在解析处拦截（isfinite + 非负），此处是第二道防线。
        if (retry_after_seconds is None or not math.isfinite(retry_after_seconds)
                or retry_after_seconds < 0):
            # 官方未保证携带 Retry-After；无有效值时至少跨过完整1秒额度窗口。
            # b1 白虎两次429仅隔565ms；审计未存响应头，不能确认当时用了默认值。
            retry_after_seconds = 1.0
        self._refill()
        base = max(retry_after_seconds, self._state_quota_delay())
        jitter = self._rng.uniform(0.0, 0.25)
        candidate = self._clock() + base + jitter
        if request_kind is RequestKind.STATE:
            self._state_cooldown_until = max(self._state_cooldown_until or candidate, candidate)
        else:
            self._cooldown_until = max(self._cooldown_until or candidate, candidate)
