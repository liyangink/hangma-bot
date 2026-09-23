"""用户共享的状态查询额度与场次资源隔离，均为官方适配器内部实现。

官方指南 v34（2026-09-23 本地快照）：state 每用户 16 次/秒，跨场共享；每场仍
最多一个在途 state 和一个在途动作。已知查询按最迟发起时刻排序；
恢复及已确认响应周期的进度查询优先于普通轮询；无截止请求按
可见风险与等待晋级排序，同级按入队先后。
同一身份动作 POST 不消费 state
额度。所有时刻均为单调秒。
"""
from __future__ import annotations

import asyncio
import math
import random
from collections import deque
from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import Awaitable, Callable, Optional

from .deadline_clock import DeadlineClock

# 工程余量（秒），不是官方窗口长度：本机发起与服务端到达存在波动。
# 16笔记账至少保留1.05秒。长期均匀放行让服务器收到的短时簇更小；
# 到达波动超出本地余量时仍由共享429冷却恢复。
DEFAULT_STATE_ARRIVAL_GUARD_SEC = 0.05
DEFAULT_PRODUCTION_STATE_MIN_SPACING_SEC = 1.0 / 14.5
# 十场会话共用16/s时不能先发满16笔再出现近一秒查询盲区。
# 生产入口最多保留四笔即刻查询，供十场同时启动及增量后的权威快照；其余按
# 16/s 补充令牌。滚动窗口仍负责官方硬上限与到达余量。
DEFAULT_PRODUCTION_STATE_BURST = 4.0
# 软等待上限只改变无已知期限查询的排序，不绕过 16/1.05 硬账。
# 从该身份实际可服务的时刻起算，避免启动或 429 冷却使低类请求
# 一解冻就压过刚出现的一秒风险；到龄后与摸牌监听同级，先入先发。
DEFAULT_DISCARD_WATCH_PROMOTION_SEC = 0.8
DEFAULT_POLL_PROMOTION_SEC = 1.2


class Priority(IntEnum):
    """请求用途优先级；明确截止后依次保已知响应、预期弃牌和普通轮询。"""

    ACTION = 0
    RECOVERY = 1
    DRAW_WATCH = 2
    DISCARD_WATCH = 3
    POLL = 4
    BACKGROUND = 5


class RequestKind(Enum):
    """端点所属额度；动作和赛事查询不消费状态查询次数。"""

    STATE = "state"
    OTHER = "other"


class DeadlineExceeded(Exception):
    """最迟发起时刻已到，尚未发送的请求不能继续领取额度。"""


@dataclass(eq=False)
class _Waiter:
    owner: RequestScheduler
    priority: Priority
    seq: int
    request_kind: RequestKind
    deadline: Optional[float]
    ready: float
    reservation: Optional[StateQueryReservation]
    active: bool = True


class StateQueryReservation:
    """未来必要查询的时间提示，不占次数或连接槽，也不是另一个 HTTP 请求。

    ready_at_monotonic 是最早可发时刻，latest_start_at_monotonic 是最迟
    安全发起时刻；调用方在对应 acquire 中显式关联，并在用途失效时取消。
    """

    def __init__(self, owner: RequestScheduler, ready: float, latest: float) -> None:
        self.owner = owner
        self.ready_at_monotonic = ready
        self.latest_start_at_monotonic = latest
        self.cancelled = False

    def cancel(self) -> None:
        """幂等撤销未来提示并唤醒等待者，不退还已经发送的查询次数。"""
        if self.cancelled:
            return
        self.cancelled = True
        root = self.owner._root
        if self in root._reservations:
            root._reservations.remove(self)
        root._notify()


class SchedulerLease:
    """一个场内连接槽及可选状态额度预占；必须在 finally 中 release。

    生产状态查询使用 reserve_only，真正进入传输前调用 mark_sent。
    未发即取消会退预占；已发后的成功、失败、取消都不退滚动计次。
    """

    def __init__(self, scheduler: RequestScheduler, priority: Priority,
                 request_kind: RequestKind, reservation: Optional[StateQueryReservation]) -> None:
        self._scheduler = scheduler
        self.priority = priority
        self._request_kind = request_kind
        self._reservation = reservation
        self._released = False
        self._sent = False

    def mark_sent(self, started_at_monotonic: Optional[float] = None) -> None:
        """把预占转换为发送记录；生产传入审计入口同一次采样的单调秒。"""
        if self._released:
            raise RuntimeError("已释放许可不能发送")
        if self._sent:
            return
        self._sent = True
        root = self._scheduler._root
        if self._request_kind is RequestKind.STATE:
            root._state_reserved -= 1
            root._state_grants.append(root._clock() if started_at_monotonic is None else started_at_monotonic)
        if self._reservation is not None:
            self._reservation.cancel()
        root._notify()

    def release(self) -> None:
        """幂等释放本场连接槽；尚未发出的状态预占可退还。"""
        if self._released:
            return
        self._released = True
        owner, root = self._scheduler, self._scheduler._root
        owner._active -= 1
        if self._request_kind is RequestKind.STATE:
            owner._active_state -= 1
            if not self._sent:
                root._state_reserved -= 1
                root._tokens = min(root._capacity, root._tokens + 1.0)
        root._notify()

    async def __aenter__(self) -> SchedulerLease:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self.release()


class RequestScheduler:
    """同用户共享 state 账与调度；各场连接槽、动作冷却和身份仍独立。"""

    def __init__(self, *, rate_per_second: float = 16.0, burst: Optional[float] = None,
                 max_concurrent: int = 32, max_state_concurrent: Optional[int] = None,
                 clock: Callable[[], float], sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                 jitter_rng: Optional[random.Random] = None, poll_interval: float = 0.002,
                 state_startup_delay_sec: float = 0.0,
                 state_arrival_guard_sec: float = 0.0,
                 state_min_spacing_sec: float = 0.0,
                 _root: Optional[RequestScheduler] = None) -> None:
        self._rate = float(rate_per_second)
        self._capacity = float(burst if burst is not None else rate_per_second)
        if not math.isfinite(self._rate) or self._rate <= 0:
            raise ValueError("rate_per_second 必须为有限正数")
        if not math.isfinite(self._capacity) or self._capacity < 1:
            raise ValueError("burst 必须为至少 1 的有限数")
        if not math.isfinite(state_startup_delay_sec) or state_startup_delay_sec < 0:
            raise ValueError("state_startup_delay_sec 必须为有限非负秒数")
        if not math.isfinite(state_arrival_guard_sec) or state_arrival_guard_sec < 0:
            raise ValueError("state_arrival_guard_sec 必须为有限非负秒数")
        if not math.isfinite(state_min_spacing_sec) or state_min_spacing_sec < 0:
            raise ValueError("state_min_spacing_sec 必须为有限非负秒数")
        if max_concurrent < 1 or (max_state_concurrent is not None
                                 and not 1 <= max_state_concurrent <= max_concurrent):
            raise ValueError("并发上限必须为正数，state 上限不得超过总上限")
        self._root = _root or self
        self._clock, self._sleep = clock, sleep
        self._rng = jitter_rng if jitter_rng is not None else random.Random()
        self._poll_interval = max(0.0, poll_interval)
        self._max_concurrent = max_concurrent
        self._max_state_concurrent = max_state_concurrent or max_concurrent
        self._active = self._active_state = 0
        self._last_service = -1
        self._cooldown_until = 0.0  # 非 state 的429只影响本场或本控制面
        self._game_scopes: dict[str, RequestScheduler] = {}
        if self._root is self:
            self._deadline_clock = DeadlineClock()
            self._window_capacity = max(1, math.floor(self._rate))
            self._window_seconds = self._window_capacity / self._rate + state_arrival_guard_sec
            self._state_grants = deque()
            self._state_reserved = 0
            self._tokens = self._capacity
            self._last_refill = clock()
            self._state_min_spacing_sec = state_min_spacing_sec
            # 首个官方计数窗口维持原四笔即刻突发与16/s补充，保证十场
            # 同时开局的首次动作；此后才加均匀间隔，避免长期突发/空档。
            self._state_initial_burst_remaining = self._window_capacity
            self._next_paced_state_grant_at = self._last_refill
            # 进程重启不能恢复旧发送账。生产新建用户账时先跨过一秒，
            # 场次重开复用本账；控制查询与动作POST不受此保护等待影响。
            self._state_cooldown_until = self._last_refill + state_startup_delay_sec
            self._waiters: list[_Waiter] = []
            self._reservations: list[StateQueryReservation] = []
            self._seq = self._service_seq = 0
            self._changed = asyncio.Event()

    def for_game(self, game_id: str, *, max_games: int) -> RequestScheduler:
        """同场重开复用资源域；M 只校验并发配置，不再静态平分 state 次数。"""
        if not isinstance(game_id, str) or not game_id:
            raise ValueError("game_id 必须非空")
        if type(max_games) is not int or not 1 <= max_games <= 16:
            raise ValueError("官方场次上限M必须在1至16之间")
        root = self._root
        if game_id not in root._game_scopes:
            root._game_scopes[game_id] = RequestScheduler(
                clock=root._clock, sleep=root._sleep, jitter_rng=root._rng,
                max_concurrent=2, max_state_concurrent=1, _root=root,
                poll_interval=root._poll_interval)
        return root._game_scopes[game_id]

    @property
    def deadline_clock(self) -> DeadlineClock:
        """同用户期限映射复用同一账；不同用户的时钟估计不互相污染。"""
        return self._root._deadline_clock

    @property
    def active_count(self) -> int:
        """当前场或控制面的在途/预占连接槽数，不是用户聚合数。"""
        return self._active

    @property
    def state_used_count(self) -> int:
        """用户当前记账窗口内发起次数（生产含到达余量），不含预占。"""
        self._root._refresh()
        return len(self._root._state_grants)

    @property
    def state_backlog_delay_sec(self) -> float:
        """按当前state许可等待和已排队工作量估计新增查询的等待秒数。

        只供动作缓发的0.5秒上限使用；这不是将来事件的预测或截止保证。
        不把尚未到达ready时刻的保护提示计为实际排队请求。
        """
        root = self._root
        root._refresh()
        now = root._clock()
        queued = sum(waiter.active and waiter.request_kind is RequestKind.STATE
                     and waiter.ready <= now for waiter in root._waiters)
        return min(0.5, max(root._state_quota_delay(), queued / root._rate))

    @property
    def cooldown_remaining(self) -> float:
        """本资源域及用户 state 冷却中的最长剩余秒数，仅用于诊断。"""
        return max(0.0, self._cooldown_until - self._clock(),
                   self._root._state_cooldown_until - self._clock())

    def protect_state_query(self, *, ready_at_monotonic: float,
                            latest_start_at_monotonic: float) -> StateQueryReservation:
        """登记本场未来必要查询；替换旧提示，不提前占用实际发送额度。"""
        if not (math.isfinite(ready_at_monotonic) and math.isfinite(latest_start_at_monotonic)
                and ready_at_monotonic < latest_start_at_monotonic):
            raise ValueError("未来查询需要有限且有正余量的单调时间")
        root = self._root
        for old in tuple(root._reservations):
            if old.owner is self:
                old.cancel()
        reservation = StateQueryReservation(self, ready_at_monotonic, latest_start_at_monotonic)
        root._reservations.append(reservation)
        root._notify()
        return reservation

    def _notify(self) -> None:
        root = self._root
        previous = root._changed
        root._changed = asyncio.Event()
        previous.set()

    def _refresh(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._last_refill)
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now
        while self._state_grants and now >= self._state_grants[0] + self._window_seconds:
            self._state_grants.popleft()
        for reservation in tuple(self._reservations):
            if reservation.latest_start_at_monotonic <= now:
                reservation.cancel()

    def _state_quota_delay(self) -> float:
        root = self._root
        root._refresh()
        token_delay = max(0.0, (1.0 - root._tokens) / root._rate)
        count = len(root._state_grants) + root._state_reserved
        window_delay = 0.0
        if count >= root._window_capacity:
            # 预占不会按许可时刻自然过期，必须等 mark_sent 或 release 唤醒。
            window_delay = (max(0.0, root._state_grants[0] + root._window_seconds - root._clock())
                            if root._state_grants else math.inf)
        spacing_delay = 0.0
        if root._state_min_spacing_sec and root._state_initial_burst_remaining <= 0:
            spacing_delay = max(0.0, root._next_paced_state_grant_at - root._clock())
        return max(token_delay, window_delay, spacing_delay)

    def _required_queries(self, selected: Optional[_Waiter] = None) -> list[tuple[float, float]]:
        """取已经知道的查询期限；不从未来世界或未知他家动作推导期限。"""
        now = self._clock()
        rows = []
        for hint in self._reservations:
            if not hint.cancelled and (selected is None or hint is not selected.reservation):
                rows.append((hint.ready_at_monotonic, hint.latest_start_at_monotonic))
        for waiter in self._waiters:
            if (waiter.active and waiter is not selected and waiter.request_kind is RequestKind.STATE
                    and waiter.deadline is not None and waiter.deadline > now
                    and (waiter.reservation is None or waiter.reservation.cancelled)):
                rows.append((waiter.ready, waiter.deadline))
        return rows

    def _schedule_possible(self, requirements: list[tuple[float, float]], *, spend_now: bool) -> bool:
        """按真实发放约束预演已知查询；未知事件及未来 429 不在预演内。"""
        now = self._clock()
        history = deque(sorted(self._state_grants))
        # 已领取但尚未发送的许可不能按假设发送时刻自动过期；在预演期间
        # 始终占据滚动窗口的一份容量，直到真实 mark_sent/release 唤醒。
        reserved = self._state_reserved
        tokens = self._tokens
        refill_at = now
        initial_burst = self._state_initial_burst_remaining
        next_paced = self._next_paced_state_grant_at

        def record_grant(sent_at: float) -> None:
            nonlocal tokens, initial_burst, next_paced
            history.append(sent_at)
            tokens -= 1.0
            if self._state_min_spacing_sec:
                if initial_burst > 0:
                    initial_burst -= 1
                    if initial_burst == 0:
                        next_paced = sent_at + self._state_min_spacing_sec
                else:
                    next_paced = max(sent_at, next_paced) + self._state_min_spacing_sec

        if spend_now:
            # 调用方仅在当前 quota/槽均可发时检查本条件。预演这次真实
            # 许可对令牌、平滑间距与滚动账的全部影响，而不只加一条历史。
            record_grant(now)
        at = now
        for ready, latest in sorted(requirements, key=lambda item: item[1]):
            at = max(at, ready, self._state_cooldown_until)
            while True:
                elapsed = max(0.0, at - refill_at)
                tokens = min(self._capacity, tokens + elapsed * self._rate)
                refill_at = at
                while history and at >= history[0] + self._window_seconds:
                    history.popleft()
                next_at = at
                if tokens < 1.0:
                    next_at = max(next_at, at + (1.0 - tokens) / self._rate)
                if self._state_min_spacing_sec and initial_burst <= 0:
                    next_at = max(next_at, next_paced)
                if len(history) + reserved >= self._window_capacity:
                    if not history:
                        return False  # 未发送预占没有可推导的自然释放时刻。
                    next_at = max(next_at, history[0] + self._window_seconds)
                if next_at == at:
                    break
                at = next_at
                if at >= latest:
                    return False
            if at >= latest:
                return False
            record_grant(at)
        return True

    def _spending_preserves_known_queries(self, waiter: _Waiter) -> bool:
        before = self._required_queries()
        if not before:
            return True
        after = self._required_queries(waiter)
        if self._schedule_possible(after, spend_now=True):
            return True
        # 已知需求本来无解时，仍允许真实有截止的请求尽力争取；普通查询
        # 不能以“无解”为由再占去它们当前仅剩的许可。
        return (waiter.deadline is not None
                and not self._schedule_possible(before, spend_now=False))

    def _resource_ready(self, waiter: _Waiter) -> bool:
        owner, now = waiter.owner, self._clock()
        if (not waiter.active or now < waiter.ready
                or (waiter.deadline is not None and now >= waiter.deadline)
                or owner._active >= owner._max_concurrent or now < owner._cooldown_until):
            return False
        if waiter.request_kind is RequestKind.OTHER:
            return True
        return (owner._active_state < owner._max_state_concurrent
                and now >= self._state_cooldown_until and self._state_quota_delay() <= 0
                and self._spending_preserves_known_queries(waiter))

    def _rank(self, waiter: _Waiter) -> tuple:
        if waiter.request_kind is RequestKind.OTHER:
            return (0 if waiter.priority is Priority.ACTION else 3, int(waiter.priority), waiter.seq)
        if waiter.deadline is not None:
            return (1, waiter.deadline, waiter.owner._last_service, waiter.seq)
        priority = int(waiter.priority)
        served_age = self._clock() - max(waiter.ready, self._state_cooldown_until)
        if (waiter.priority is Priority.DISCARD_WATCH
                and served_age >= DEFAULT_DISCARD_WATCH_PROMOTION_SEC):
            priority = int(Priority.DRAW_WATCH)
        elif waiter.priority is Priority.POLL and served_age >= DEFAULT_POLL_PROMOTION_SEC:
            priority = int(Priority.DRAW_WATCH)
        return (2, priority, waiter.seq)

    def _claim(self, waiter: _Waiter, reserve_only: bool) -> Optional[SchedulerLease]:
        self._refresh()
        chosen = min((w for w in self._waiters if self._resource_ready(w)),
                     key=self._rank, default=None)
        if chosen is not waiter:
            return None
        waiter.active = False
        self._waiters.remove(waiter)
        owner = waiter.owner
        owner._active += 1
        if waiter.request_kind is RequestKind.STATE:
            self._state_reserved += 1
            self._tokens -= 1.0
            if self._state_min_spacing_sec:
                if self._state_initial_burst_remaining > 0:
                    self._state_initial_burst_remaining -= 1
                    if self._state_initial_burst_remaining == 0:
                        self._next_paced_state_grant_at = self._clock() + self._state_min_spacing_sec
                else:
                    self._next_paced_state_grant_at = (
                        max(self._clock(), self._next_paced_state_grant_at)
                        + self._state_min_spacing_sec)
            owner._active_state += 1
            self._service_seq += 1
            owner._last_service = self._service_seq
        lease = SchedulerLease(owner, waiter.priority, waiter.request_kind, waiter.reservation)
        if not reserve_only:
            lease.mark_sent()
        self._notify()
        return lease

    def _next_delay(self, waiter: _Waiter) -> Optional[float]:
        now, owner = self._clock(), waiter.owner
        times = []
        if waiter.deadline is not None:
            times.append(waiter.deadline)
        if waiter.ready > now:
            times.append(waiter.ready)
        if owner._cooldown_until > now:
            times.append(owner._cooldown_until)
        if waiter.request_kind is RequestKind.STATE:
            if self._state_cooldown_until > now:
                times.append(self._state_cooldown_until)
            quota = self._state_quota_delay()
            if math.isfinite(quota) and quota > 0:
                times.append(now + max(quota, 1e-6))
            for hint in self._reservations:
                times.append(hint.latest_start_at_monotonic)
                if hint.ready_at_monotonic > now:
                    times.append(hint.ready_at_monotonic)
            for queued in self._waiters:
                if queued.ready > now:
                    times.append(queued.ready)
        return max(0.0, min(times) - now) if times else None

    async def _wait_change(self, delay: Optional[float], signal: asyncio.Event) -> None:
        if signal.is_set():
            return
        if delay is None:
            await signal.wait()
            return
        sleeper = asyncio.ensure_future(self._sleep(delay))
        changed = asyncio.ensure_future(signal.wait())
        try:
            await asyncio.wait((sleeper, changed), return_when=asyncio.FIRST_COMPLETED)
            if sleeper.done():
                sleeper.result()
        finally:
            for task in (sleeper, changed):
                if not task.done():
                    task.cancel()
            await asyncio.gather(sleeper, changed, return_exceptions=True)

    async def acquire(self, priority: Priority, deadline_monotonic: Optional[float] = None, *,
                      request_kind: RequestKind = RequestKind.STATE,
                      not_before_monotonic: Optional[float] = None,
                      reservation: Optional[StateQueryReservation] = None,
                      reserve_only: bool = False) -> SchedulerLease:
        """等待可发请求的许可；deadline 仅限制发起，HTTP 完成预算由会话另算。

        reserve_only 默认为兼容旧内部调用的即刻计次；生产 state 使用 True，
        在真正调用传输前 mark_sent。已知边界可指定 not_before 和对应提示。
        """
        if not isinstance(request_kind, RequestKind):
            raise ValueError("request_kind 必须为 RequestKind")
        for value in (deadline_monotonic, not_before_monotonic):
            if value is not None and not math.isfinite(value):
                raise ValueError("调度时刻必须是有限单调时钟秒")
        if reservation is not None and (reservation.owner is not self or request_kind is not RequestKind.STATE):
            raise ValueError("未来查询提示必须属于本场 state")
        root = self._root
        ready = self._clock() if not_before_monotonic is None else not_before_monotonic
        if reservation is not None and not reservation.cancelled:
            ready = max(ready, reservation.ready_at_monotonic)
            deadline_monotonic = min(deadline_monotonic if deadline_monotonic is not None else math.inf,
                                     reservation.latest_start_at_monotonic)
        root._seq += 1
        waiter = _Waiter(self, priority, root._seq, request_kind, deadline_monotonic, ready, reservation)
        root._waiters.append(waiter)
        root._notify()
        try:
            while True:
                if waiter.deadline is not None and self._clock() >= waiter.deadline:
                    raise DeadlineExceeded("调度等待超出最迟发起时刻")
                lease = root._claim(waiter, reserve_only)
                if lease is not None:
                    return lease
                signal = root._changed
                await self._wait_change(root._next_delay(waiter), signal)
        finally:
            if waiter.active:
                waiter.active = False
                if waiter in root._waiters:
                    root._waiters.remove(waiter)
                root._notify()

    def note_rate_limited(self, retry_after_seconds: Optional[float], *,
                          request_kind: RequestKind = RequestKind.OTHER) -> None:
        """state 429 冷却同用户全部状态查询；OTHER 429 只冷却所属资源域。"""
        if (retry_after_seconds is None or not math.isfinite(retry_after_seconds)
                or retry_after_seconds < 0):
            retry_after_seconds = 1.0
        root = self._root
        root._refresh()
        quota = root._state_quota_delay() if request_kind is RequestKind.STATE else 0.0
        base = max(retry_after_seconds, quota if math.isfinite(quota) else 0.0)
        candidate = self._clock() + base + self._rng.uniform(0.0, 0.25)
        if request_kind is RequestKind.STATE:
            root._state_cooldown_until = max(root._state_cooldown_until, candidate)
        else:
            self._cooldown_until = max(self._cooldown_until, candidate)
        root._notify()
