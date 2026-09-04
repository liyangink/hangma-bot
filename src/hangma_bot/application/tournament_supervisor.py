"""跨阶段赛事监督：报名/到位、快照对账、active_games 场次动态编排与终态判定。

权威原则（application 模块规范与接口协议第 6 节）：
- active_games（来自 /api/me 的当前进行中场次）是场次编排的唯一权威：
  空列表不是赛事结束，不能预建固定数量；my_games 是跨阶段累计历史，
  只用于审计，绝不驱动开场/关场；
- 赛事终态（finished/closed/void）与参赛者终态（另含淘汰、认证、版本、
  目标错配）分开判定；身份级致命终态一经写入，不再被后续快照覆盖；
- 生命周期：registering 报名 → 报名成功 → 首次 ready → 等待 running；
  阶段 1 没有 stage_open 确认点且 stage_no 可为 None，到位确认用
  (stage_no, stage_role) 身份键 + 哨兵，消除 None 的"未到位/已到位"歧义；
- 测试房间（RuntimeMode.TEST_ROOM）启动时房间已 finished 是跨轮复用信号
  （指南 v4/v5/v8：幂等报名 + 4 令牌各 ready 一次开启下一轮，空闲自动
  close 是正常终态）；本进程已打过一轮后到达的 finished 仍是该身份正常
  终态，下一轮由身份进程重启后的启动复用路径承接；正式赛事终态不变；
- stage_crashed 关闭旧尝试任务并标记作废；stage_attempt_id 在每次
  阶段实际运行尝试开始时生成（按 stage_no 区分尝试，observed_revision
  只作为到位命令的防陈旧条件，不构成新尝试）。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from hangma_bot.application.audit import AuditTrail, audit_error_text, audit_text
from hangma_bot.application.contracts import (
    AuditKind,
    GameSessionPort,
    OperationStatus,
    ParticipantTerminal,
    ParticipantTerminalReason,
    ReadyResult,
    RegistrationResult,
    RuntimeMode,
    SessionBootstrap,
    StageIdentity,
    TournamentSessionPort,
    TournamentSnapshot,
    TournamentStatus,
)
from hangma_bot.application.deadline import BoundedBackoff
from hangma_bot.application.decision_loop import RuntimeServices
from hangma_bot.application.game_task import GameTask, GameTaskResult, GameTaskStatus
from hangma_bot.kernel.config import TournamentConfig
from hangma_bot.kernel.observation import CompetitionContext

SleepFn = Callable[[float], Awaitable[None]]

# 到位确认哨兵："从未确认到位"与"已确认 (stage_no=None 的阶段)"必须可区分。
# 阶段 1 的 stage_no 可能为 None，None 不能再承担未确认哨兵职责（歧义）；
# 确认键是 (stage_no, stage_role) 元组，(None, None) 是合法的已确认键。
_READY_UNCONFIRMED = object()

_TERMINAL_STATUS_REASON = {
    TournamentStatus.FINISHED: ParticipantTerminalReason.TOURNAMENT_FINISHED,
    TournamentStatus.CLOSED: ParticipantTerminalReason.TOURNAMENT_CLOSED,
    TournamentStatus.VOID: ParticipantTerminalReason.TOURNAMENT_VOID,
}

@dataclass(frozen=True)
class SupervisionPolicy:
    """监督层的退避与重试预算；全部为标量参数，实例按需独立创建。

    不在策略对象里保存可变退避实例：策略对象可能被多个身份共享，
    共享计数会互相污染。
    """

    poll_error_base_delay_seconds: float = 0.5
    poll_error_factor: float = 2.0
    poll_error_max_delay_seconds: float = 8.0
    poll_error_max_attempts: int = 5
    register_base_delay_seconds: float = 1.0
    register_factor: float = 2.0
    register_max_delay_seconds: float = 16.0
    register_max_attempts: int = 4
    ready_base_delay_seconds: float = 1.0
    ready_factor: float = 2.0
    ready_max_delay_seconds: float = 16.0
    ready_max_attempts: int = 4
    ready_call_timeout_seconds: float = 30.0  # 单次 ready 调用超时；基于 asyncio 事件循环的单调时钟（wait_for），不是墙上时钟
    game_item_base_delay_seconds: float = 0.5
    game_item_factor: float = 2.0
    game_item_max_delay_seconds: float = 8.0
    game_item_max_attempts: int = 3
    game_reopen_base_delay_seconds: float = 0.5
    game_reopen_factor: float = 2.0
    game_reopen_max_delay_seconds: float = 8.0
    game_reopen_max_attempts: int = 5
    audit_flush_seconds: float = 5.0

    def _backoff(self, base: float, factor: float, cap: float, attempts: int) -> BoundedBackoff:
        return BoundedBackoff(
            base_delay_seconds=base, factor=factor, max_delay_seconds=cap, max_attempts=attempts
        )

    def new_poll_error_backoff(self) -> BoundedBackoff:
        return self._backoff(self.poll_error_base_delay_seconds, self.poll_error_factor, self.poll_error_max_delay_seconds, self.poll_error_max_attempts)

    def new_register_backoff(self) -> BoundedBackoff:
        return self._backoff(self.register_base_delay_seconds, self.register_factor, self.register_max_delay_seconds, self.register_max_attempts)

    def new_ready_backoff(self) -> BoundedBackoff:
        return self._backoff(self.ready_base_delay_seconds, self.ready_factor, self.ready_max_delay_seconds, self.ready_max_attempts)

    def new_game_item_backoff(self) -> BoundedBackoff:
        return self._backoff(self.game_item_base_delay_seconds, self.game_item_factor, self.game_item_max_delay_seconds, self.game_item_max_attempts)

    def new_game_reopen_backoff(self) -> BoundedBackoff:
        return self._backoff(self.game_reopen_base_delay_seconds, self.game_reopen_factor, self.game_reopen_max_delay_seconds, self.game_reopen_max_attempts)


@dataclass
class _GameSlot:
    """监督层登记的一场：任务与会话。"""

    game_id: str
    session: GameSessionPort
    task: "asyncio.Task[GameTaskResult]"


def _snapshot_payload(snapshot: TournamentSnapshot) -> dict:
    """快照转 JSON 载荷；只保留脱敏后的权威事实字段。"""

    return {
        "status": snapshot.status.value,
        "stage_no": snapshot.stage.stage_no,
        "stage_observed_revision": snapshot.stage.observed_revision,
        "stage_role": snapshot.stage_role,
        "stage_total": snapshot.stage_total,
        "stage_crashed": snapshot.stage_crashed,
        "qualified": snapshot.qualified,
        "qualify_role": snapshot.qualify_role,
        "active_games": list(snapshot.active_games),
        "my_games": list(snapshot.my_games),
        "observed_at_unix_ms": snapshot.observed_at_unix_ms,
    }


class TournamentSupervisor:
    """一个身份的赛事监督循环；由 ParticipantRuntime 创建并在结束时回收。"""

    def __init__(
        self,
        *,
        bootstrap: SessionBootstrap,
        session: TournamentSessionPort,
        services: RuntimeServices,
        supervision: SupervisionPolicy,
        sleep: SleepFn,
        mode: RuntimeMode,
    ) -> None:
        self._bootstrap = bootstrap
        self._session = session
        self._services = services
        self._supervision = supervision
        self._sleep = sleep
        self._mode = mode  # 决定 finished 的语义：正式赛事终态 / 测试房间跨轮复用
        self._config: TournamentConfig = bootstrap.config
        self._audit = services.audit
        self._competition: CompetitionContext = bootstrap.initial_snapshot.competition
        # 退避预算按监督器实例独立创建，避免共享策略对象互相污染。
        self._poll_backoff = supervision.new_poll_error_backoff()
        self._register_backoff = supervision.new_register_backoff()
        self._ready_backoff = supervision.new_ready_backoff()
        self._ready_call_timeout = supervision.ready_call_timeout_seconds
        self._register_succeeded = False
        self._register_attempted = False  # 本次运行是否发出过报名请求（实例级，跨监督器不共享）
        self._register_task: Optional["asyncio.Task[None]"] = None
        self._ready_task: Optional["asyncio.Task[None]"] = None
        # 已确认到位的阶段身份键 (stage_no, stage_role)；哨兵表示从未确认。
        # 不用 Optional[int] stage_no：阶段 1 的 None 与"未到位"歧义必须消除。
        self._ready_confirmed_key: object = _READY_UNCONFIRMED
        # 本进程是否已观察到 running：测试房间 finished 的跨轮复用只服务
        # "启动时房间已结束"场景（register+ready 进入下一轮）；本进程已打过
        # 一轮后到达的 finished 是该身份的正常终态（子进程退出码 0），
        # 下一轮由身份进程重启后的启动复用路径承接。
        self._running_observed = False
        self._stage_attempt_id: Optional[str] = None
        self._stage_attempt_stage_no: Optional[int] = None
        # 到位命令代次：stage_crashed 作废与普通阶段号迁移都递增；
        # 在途 ready 的迟到结果（含 NOT_QUALIFIED）按代次判废。
        self._stage_generation = 0
        self._observed_stage_no: Optional[int] = None
        self._games: dict[str, _GameSlot] = {}
        # 已退出场次登记：finished / unrecoverable_failure / abandoned。
        self._retired_games: dict[str, str] = {}
        # 重开预算按 game_id 在监督器级保存（跨 slot 生死累计）。
        self._reopen_budgets: dict[str, BoundedBackoff] = {}
        self._reopen_tasks: dict[str, "asyncio.Task[None]"] = {}
        # 退役侧任务：被阶段迁移/crash 取代的旧 ready/register 任务。
        # 清引用允许新命令立即启动，但旧任务的收尾仍由 shutdown 统一等待，
        # 不得泄漏到 runtime 返回之后。
        self._retired_side_tasks: set["asyncio.Task[None]"] = set()
        # 正在关闭中的场次（已 pop、aclose 未完成）：对账必须跳过同 ID，
        # 否则旧会话还在关闭途中就会被按新会话重开（真实适配器会拿到
        # 缓存的旧实例），形成同 ID 双会话重叠。
        self._closing_games: set[str] = set()
        self._cleanup_tasks: set["asyncio.Task[None]"] = set()
        self._update_task: Optional["asyncio.Task[object]"] = None
        self._delayed_wake: Optional["asyncio.Task[None]"] = None
        self._wake = asyncio.Event()
        self._wake_task: Optional["asyncio.Future[bool]"] = None
        self._last_status: Optional[TournamentStatus] = None
        self._terminal: Optional[ParticipantTerminal] = None
        self._last_snapshot: Optional[TournamentSnapshot] = bootstrap.initial_snapshot
        self._shutting_down = False  # 关闭期间禁止任何后台命令重启
        # 快照变化通知：STALE_STAGE 等待它而不是退避轮询。
        self._snapshot_epoch = 0
        self._snapshot_cond = asyncio.Condition()

    @property
    def stage_attempt_id(self) -> Optional[str]:
        """当前阶段运行尝试的审计标识。"""

        return self._stage_attempt_id

    def _set_terminal(self, terminal: ParticipantTerminal) -> None:
        """首写优先：身份级终态一经确定，不被后续信号覆盖。"""

        if self._terminal is None:
            self._terminal = terminal

    async def run(self) -> ParticipantTerminal:
        """监督主循环；返回当前身份的参赛者终态。"""

        try:
            await self._handle_snapshot(self._bootstrap.initial_snapshot)
            while self._terminal is None:
                # 轮询退避门：上一轮 next_update 失败后必须等延迟到期再发下一轮。
                poll_gate_open = self._delayed_wake is None or self._delayed_wake.done()
                if poll_gate_open and (self._update_task is None or self._update_task.done()):
                    self._update_task = asyncio.create_task(self._session.next_update())
                self._wake_task = asyncio.ensure_future(self._wake.wait())
                done, _pending = await asyncio.wait(
                    {t for t in (self._update_task, self._wake_task) if t is not None},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if self._wake_task in done:
                    self._wake.clear()
                    self._reap_game_tasks()
                    if self._terminal is None and self._last_snapshot is not None:
                        # 场次任务结束（含计划重开到点）后立即按最新权威快照重新对账。
                        self._reconcile_games(self._last_snapshot)
                if self._update_task is not None and self._update_task in done:
                    if self._wake_task is not None and not self._wake_task.done():
                        # update 先完成：本轮 wake waiter 必须取消，否则随迭代累积泄漏。
                        self._wake_task.cancel()
                    finished_update = self._update_task
                    self._update_task = None
                    if self._terminal is None:
                        await self._consume_update(finished_update)
                    elif not finished_update.cancelled():
                        # 终态后丢弃的已完成任务必须取回异常，避免「异常无人认领」。
                        finished_update.exception()
            return self._terminal
        finally:
            await self._shutdown()

    # ---- 快照处理 -------------------------------------------------------

    async def _handle_snapshot(self, snapshot: TournamentSnapshot) -> None:
        if self._terminal is not None:
            return
        self._last_snapshot = snapshot
        self._snapshot_epoch += 1
        if snapshot.stage.stage_no != self._observed_stage_no:
            # 阶段号迁移（含首次观察）统一作废旧到位命令：代次递增、
            # 到位预算重置（新阶段不继承旧账）、回收旧任务并同步启动
            # 当前命令——不能等 done 回调：同批后续快照（如 RUNNING）
            # 可能先把待办变空，导致新阶段到位永远丢失。
            # 注意 ParticipantTerminal 不在此列：身份级终态跨阶段有效。
            self._observed_stage_no = snapshot.stage.stage_no
            self._stage_generation += 1
            self._ready_backoff = self._supervision.new_ready_backoff()
            if self._ready_task is not None and not self._ready_task.done():
                self._retire_ready_task()
            # 不在此提前启动新命令：qualified=false 淘汰检查在后面，
            # 名单外阶段的到位必须由检查后的正常分支决定。
        async with self._snapshot_cond:
            self._snapshot_cond.notify_all()
        self._competition = snapshot.competition
        self._audit.emit(AuditKind.AUTHORITATIVE_STATE, _snapshot_payload(snapshot))
        prev_status = self._last_status
        if snapshot.status is not prev_status:
            self._audit.emit(
                AuditKind.LIFECYCLE_CHANGED,
                {
                    "event": "status_changed",
                    "from": prev_status.value if prev_status else None,
                    "to": snapshot.status.value,
                },
            )
            self._last_status = snapshot.status

        if snapshot.status is TournamentStatus.RUNNING:
            self._running_observed = True

        terminal_reason = _TERMINAL_STATUS_REASON.get(snapshot.status)
        if (
            self._mode is RuntimeMode.TEST_ROOM
            and snapshot.status is TournamentStatus.FINISHED
            and not self._running_observed
        ):
            # 测试房间跨轮复用（指南 v4/v5/v8）：本进程启动时房间已 finished，
            # 属于等待下一轮的身份——幂等报名（已报名令牌 register 放行）后
            # ready 一次即可开启下一轮（4 令牌各 ready 一次，幂等累积）；
            # 未开赛前房间空闲超时自动 close 是正常终态。本进程已打过一轮后
            # 到达的 finished 不走此路径：是该身份的正常终态（见 _running_observed）。
            if prev_status is not snapshot.status:
                self._ready_confirmed_key = _READY_UNCONFIRMED
                self._ready_backoff = self._supervision.new_ready_backoff()
            if not self._register_succeeded:
                self._maybe_start_register()
        elif terminal_reason is not None:
            self._set_terminal(
                ParticipantTerminal(
                    reason=terminal_reason,
                    last_snapshot=snapshot,
                    detail="赛事进入终态 {}".format(snapshot.status.value),
                )
            )
            return

        if snapshot.stage_crashed:
            # 崩溃快照内不做任何编排：旧尝试的场次必须关闭而不是重开，
            # 等待崩溃后的新权威快照再重新发现。
            await self._void_stage_attempt()
            return

        if snapshot.status is TournamentStatus.STAGE_OPEN and snapshot.qualified is False:
            # stage_open + qualified=false 是名单外正常淘汰，不是平台故障。
            self._set_terminal(
                ParticipantTerminal(
                    reason=ParticipantTerminalReason.ELIMINATED,
                    last_snapshot=snapshot,
                    detail="stage_open 时不在晋级/候补名单（qualify_role={}）".format(
                        snapshot.qualify_role
                    ),
                )
            )
            return

        if snapshot.status is TournamentStatus.REGISTERING and not self._register_succeeded:
            self._maybe_start_register()

        # 待到位的阶段判断统一收敛到 _pending_ready_stage：覆盖
        # stage_open（阶段 2+ 确认）、registering 报名成功后的首次到位
        # （阶段 1 无 stage_open 确认点，stage_no 可为 None）与测试房间
        # finished 跨轮复用。
        if self._pending_ready_stage() is not None:
            self._maybe_start_ready()

        if (
            snapshot.active_games
            and snapshot.status is TournamentStatus.RUNNING
            and (
                self._stage_attempt_id is None
                or self._stage_attempt_stage_no != snapshot.stage.stage_no
            )
        ):
            # 场次实际开跑即为阶段运行尝试；当前尝试不属于本阶段时必须在
            # 开场前生成新标识，否则首个动作的审计会错误归属旧阶段尝试
            # （典型交错：stage1 已确认、stage2 确认响应在途、stage2 已开跑）。
            # 第一阶段（registering 直达 running）没有 stage_open 确认点，
            # 同样由此生成首次尝试标识。
            self._ensure_stage_attempt(snapshot.stage)

        self._reconcile_games(snapshot)

    # ---- 报名 -----------------------------------------------------------

    def _maybe_start_register(self) -> None:
        """报名在后台任务内有界重试；不阻塞监督主循环。"""

        if self._shutting_down or self._terminal is not None:
            return

        if self._register_task is not None and not self._register_task.done():
            return
        self._register_task = asyncio.ensure_future(self._register_coro())
        self._register_task.add_done_callback(self._on_side_task_done)

    def _on_side_task_done(self, task: "asyncio.Task[None]") -> None:
        """后台任务结束的统一回调：唤醒主循环并兜底登记未捕获异常。"""

        if task is self._ready_task:
            self._ready_task = None
            if (
                not self._shutting_down
                and self._terminal is None
                and self._pending_ready_stage() is not None
            ):
                # 旧命令结束（含被阶段迁移取消）而当前仍有待到位阶段：
                # 立即启动新命令，不等下一张快照。
                self._maybe_start_ready()
        if task is self._register_task:
            self._register_task = None
            if (
                not self._shutting_down
                and self._terminal is None
                and self._register_succeeded
                and self._pending_ready_stage() is not None
            ):
                # 报名成功后立即推进首次到位（阶段 1 无 stage_open 确认点）；
                # 测试房间冷启动于 finished 房同样经由此路径进入跨轮 ready。
                self._maybe_start_ready()
        if not task.cancelled() and task.exception() is not None:
            # 协程内部已消化全部业务异常；这里是最后防线，防止残余异常静默丢失。
            exc = task.exception()
            self._audit.emit(
                AuditKind.PROTOCOL_RECOVERED,
                {
                    "area": "supervisor_side_task",
                    "reason": "后台任务异常退出: {}".format(audit_error_text(exc)),
                },
            )
            self._set_terminal(
                ParticipantTerminal(
                    reason=ParticipantTerminalReason.FATAL_PROTOCOL_ERROR,
                    last_snapshot=self._last_snapshot,
                    detail="后台任务异常退出（防御兜底）",
                )
            )
        self._wake.set()

    async def _register_coro(self) -> None:
        try:
            while self._terminal is None and not self._register_succeeded:
                # 每次发起前核对状态：退避期间赛事已推进则不再多打一笔报名。
                if self._register_moot_check():
                    return
                try:
                    outcome = await self._session.register()
                    self._register_attempted = True
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001 - 报名通道异常必须有界恢复
                    if self._register_moot_check():
                        return
                    delay = self._next_retry_or_terminal(
                        self._register_backoff, "register", "报名通道异常", exc
                    )
                    if delay is None:
                        return
                    await self._sleep(delay)
                    continue
                if isinstance(outcome, ParticipantTerminal):
                    self._set_terminal(outcome)
                    return
                result: RegistrationResult = outcome
                if result.status is not OperationStatus.REJECTED:
                    self._register_succeeded = True
                    self._register_backoff.reset()
                    self._audit.emit(
                        AuditKind.LIFECYCLE_CHANGED,
                        {
                            "event": "registered",
                            "status": result.status.value,
                            "official_code": result.official_code,
                        },
                    )
                    return
                if self._register_moot_check():
                    return
                delay = self._next_retry_or_terminal(
                    self._register_backoff,
                    "register",
                    "报名被拒绝 official_code={}".format(result.official_code),
                    None,
                )
                if delay is None:
                    return
                await self._sleep(delay)
        except asyncio.CancelledError:
            raise

    def _register_moot_check(self) -> bool:
        """赛事状态已离开 registering 时报名不再必要。

        覆盖三类交错：发起前赛事已推进（预检）、在途请求期间开赛
        （迟到结果/异常）、退避等待期间开赛（下一次 POST 前）。
        报名拒绝码（如 TOURNAMENT_STARTED）是快照滞后的正常结果，
        绝不能按持续失败重试到身份终态。
        """

        snapshot = self._last_snapshot
        if snapshot is None or snapshot.status is TournamentStatus.REGISTERING:
            return False
        if (
            self._mode is RuntimeMode.TEST_ROOM
            and snapshot.status is TournamentStatus.FINISHED
        ):
            # 测试房间 finished 仍接受幂等报名（跨轮复用冷启动）：报名不 moot。
            return False
        self._register_succeeded = True  # 报名已无必要；编排交给权威快照
        if self._register_attempted:
            self._audit.emit(
                AuditKind.PROTOCOL_RECOVERED,
                {
                    "area": "register",
                    "reason": "报名请求/结果迟到且赛事已推进（{}），停止报名".format(
                        snapshot.status.value
                    ),
                },
            )
        return True

    def _next_retry_or_terminal(
        self,
        backoff: BoundedBackoff,
        area: str,
        reason: str,
        exc: Optional[Exception],
    ) -> Optional[float]:
        """领取下一次重试延迟；预算耗尽时写入永久终态并返回 None。

        返回的延迟必须由调用方内联 await：退避的意义就是让下一次请求
        真正等待，而不是仅记录延迟后立即重发（轮次 2 审查 N1）。
        """

        detail = reason if exc is None else "{}: {}".format(reason, audit_error_text(exc))
        delay = backoff.next_delay_or_none()
        if delay is None:
            self._set_terminal(
                ParticipantTerminal(
                    reason=ParticipantTerminalReason.FATAL_PROTOCOL_ERROR,
                    last_snapshot=self._last_snapshot,
                    detail="{}持续失败，重试预算耗尽".format(area),
                )
            )
            return None
        self._audit.emit(
            AuditKind.PROTOCOL_RECOVERED,
            {"area": area, "reason": detail, "retry_delay_seconds": delay},
        )
        return delay

    # ---- 到位 -----------------------------------------------------------

    def _pending_ready_stage(self) -> Optional[StageIdentity]:
        """当前是否仍有待到位阶段；按阶段身份键判断而非仅 stage_no。

        阶段身份键 = (stage_no, stage_role)；stage_no 为 None 的阶段（阶段 1）
        以哨兵区分"从未确认"与"已确认 (None, ...)"。到位目标是：
        - stage_open：阶段 2+ 确认（名单外永远不是目标）；
        - registering 且报名已成功：阶段 1 直达 running 流程的首次到位；
        - finished 且运行模式为测试房间：跨轮复用的下一轮到位（幂等）。
        """

        snapshot = self._last_snapshot
        if snapshot is None or snapshot.qualified is False:
            # 名单外身份永远不是待到位目标（即便终态尚未写入）。
            return None
        key = (snapshot.stage.stage_no, snapshot.stage_role)
        if self._ready_confirmed_key == key:
            return None
        if snapshot.status is TournamentStatus.STAGE_OPEN:
            return snapshot.stage
        if snapshot.status is TournamentStatus.REGISTERING and self._register_succeeded:
            return snapshot.stage
        if (
            snapshot.status is TournamentStatus.FINISHED
            and self._mode is RuntimeMode.TEST_ROOM
            and not self._running_observed
            and self._register_succeeded
        ):
            return snapshot.stage
        return None

    def _retire_ready_task(self) -> None:
        """取消并退役当前 ready 任务：清引用让新命令可立即启动，
        旧任务转入退役集合由 shutdown 统一等待其收尾。"""

        task = self._ready_task
        if task is None:
            return
        self._ready_task = None
        if not task.done():
            task.cancel()
            self._retired_side_tasks.add(task)
            task.add_done_callback(self._retired_side_tasks.discard)

    def _maybe_start_ready(self) -> None:
        """派发当前待到位阶段的后台到位任务。

        阶段身份在派发时点捕获：报名成功的 done 回调与 next_update 结果消费
        之间没有先后保证，若 ready 任务首次执行前权威快照已被推进（如冷启动
        房间直接进入 running），事后重读会丢失首次到位——捕获时点的身份才是
        命令成立依据；重试路径仍每次重新评估。
        """

        if self._shutting_down or self._ready_task is not None and not self._ready_task.done():
            return
        stage = self._pending_ready_stage()
        if stage is None:
            return
        self._ready_task = asyncio.ensure_future(self._ready_coro(stage))
        self._ready_task.add_done_callback(self._on_side_task_done)

    async def _ready_coro(self, stage: StageIdentity) -> None:
        first_attempt = True  # 首次尝试使用派发时捕获的阶段身份
        try:
            while self._terminal is None:
                if not first_attempt:
                    # 重试路径重新评估：状态推进/阶段迁移/崩溃作废后旧命令
                    # 自然失效（迟到结果按代次判废，见下方分支）。
                    stage = self._pending_ready_stage()
                    if stage is None:
                        return
                first_attempt = False
                # 命令基准：本条 ready 所依据的快照代次与阶段尝试代次；
                # STALE 时等待前者变化，crash 作废后迟到结果按后者判废。
                command_epoch = self._snapshot_epoch
                attempt_generation = self._stage_generation
                try:
                    outcome = await asyncio.wait_for(
                        self._session.ready(stage), timeout=self._ready_call_timeout
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001 - 到位异常/超时有界恢复
                    if self._stage_generation != attempt_generation:
                        # 迟到异常不得消耗新尝试的重试预算。
                        self._audit.emit(
                            AuditKind.PROTOCOL_RECOVERED,
                            {
                                "area": "ready",
                                "reason": "迟到到位异常所属尝试已作废，丢弃",
                                "stage_no": stage.stage_no,
                            },
                        )
                        continue
                    delay = self._next_retry_or_terminal(
                        self._ready_backoff, "ready", "到位调用异常", exc
                    )
                    if delay is None:
                        return
                    await self._sleep(delay)
                    continue
                if isinstance(outcome, ParticipantTerminal):
                    self._set_terminal(outcome)
                    return
                if self._stage_generation != attempt_generation:
                    # 迟到拒绝/确认所属尝试已作废：不消耗预算、不分类处理，
                    # 直接按当前代次重新到位（NOT_QUALIFIED 也不例外）。
                    self._audit.emit(
                        AuditKind.PROTOCOL_RECOVERED,
                        {
                            "area": "ready",
                            "reason": "迟到到位结果所属尝试已作废，丢弃",
                            "stage_no": stage.stage_no,
                        },
                    )
                    continue
                result: ReadyResult = outcome
                if result.status is OperationStatus.REJECTED:
                    if result.official_code == "NOT_QUALIFIED":
                        # 名单外拒绝是正常淘汰；其他拒绝码不得猜成淘汰。
                        self._set_terminal(
                            ParticipantTerminal(
                                reason=ParticipantTerminalReason.ELIMINATED,
                                last_snapshot=self._last_snapshot,
                                detail="到位被拒 NOT_QUALIFIED，按名单外正常淘汰",
                            )
                        )
                        return
                    if result.official_code == "STALE_STAGE":
                        # 阶段在请求期间推进：丢弃旧命令，阻塞等待命令基准之后的
                        # 权威快照；若新快照已到则立即用新修订号重试。
                        self._audit.emit(
                            AuditKind.PROTOCOL_RECOVERED,
                            {
                                "area": "ready",
                                "reason": "到位被拒 STALE_STAGE，等待新阶段快照",
                                "official_code": result.official_code,
                            },
                        )
                        async with self._snapshot_cond:
                            await self._snapshot_cond.wait_for(
                                lambda: self._snapshot_epoch != command_epoch
                                or self._stage_generation != attempt_generation
                                or self._terminal is not None
                            )
                        continue
                    delay = self._next_retry_or_terminal(
                        self._ready_backoff,
                        "ready",
                        "到位被拒 official_code={}".format(result.official_code),
                        None,
                    )
                    if delay is None:
                        return
                    await self._sleep(delay)
                    continue
                # ACCEPTED / ALREADY_DONE：按当前权威快照的阶段身份键确认，
                # 修订号变化不重新到位；(None, None) 是合法的已确认键。
                role = self._last_snapshot.stage_role if self._last_snapshot is not None else None
                self._ready_confirmed_key = (stage.stage_no, role)
                self._ready_backoff.reset()
                self._audit.emit(
                    AuditKind.LIFECYCLE_CHANGED,
                    {
                        "event": "ready",
                        "status": result.status.value,
                        "stage_no": stage.stage_no,
                        "stage_observed_revision": stage.observed_revision,
                        "official_code": result.official_code,
                    },
                )
                self._ensure_stage_attempt(stage)
        except asyncio.CancelledError:
            raise

    # ---- 阶段尝试 -------------------------------------------------------

    def _ensure_stage_attempt(self, stage: StageIdentity) -> None:
        """阶段实际运行尝试开始时生成审计标识；按 stage_no 区分尝试。"""

        if (
            self._stage_attempt_id is not None
            and self._stage_attempt_stage_no == stage.stage_no
        ):
            return
        self._stage_attempt_id = self._services.ids.new_stage_attempt_id(stage.stage_no)
        self._stage_attempt_stage_no = stage.stage_no
        # 新阶段尝试意味着旧场次的重开预算与退出登记一并作废；
        # 到位预算同样按尝试重置——新尝试的到位失败不应继承旧账。
        self._retired_games.clear()
        self._reopen_budgets.clear()
        self._ready_backoff = self._supervision.new_ready_backoff()
        self._audit.emit(
            AuditKind.LIFECYCLE_CHANGED,
            {
                "event": "stage_attempt_started",
                "stage_attempt_id": self._stage_attempt_id,
                "stage_no": stage.stage_no,
                "stage_observed_revision": stage.observed_revision,
            },
        )

    async def _void_stage_attempt(self) -> None:
        """stage_crashed：作废当前尝试并关闭其全部场次任务。"""

        if self._stage_attempt_id is not None:
            self._audit.emit(
                AuditKind.LIFECYCLE_CHANGED,
                {
                    "event": "stage_attempt_voided",
                    "stage_attempt_id": self._stage_attempt_id,
                    "reason": "stage_crashed",
                },
            )
        self._stage_attempt_id = None
        self._stage_attempt_stage_no = None
        self._stage_generation += 1  # 使在途 ready 的迟到结果失效
        # 同阶段号重赛没有 stage_no 迁移可借：必须显式回收旧 ready 任务，
        # 否则其挂起调用占住唯一 worker，新尝试被阻塞到 30 秒超时。
        self._retire_ready_task()
        # 崩溃后即使同阶段号也要重新到位确认。
        self._ready_confirmed_key = _READY_UNCONFIRMED
        self._retired_games.clear()
        self._reopen_budgets.clear()
        # 作废即新尝试的前奏：到位预算随之重置，不继承旧尝试的消耗。
        self._ready_backoff = self._supervision.new_ready_backoff()
        for game_id in list(self._games):
            self._schedule_close(game_id, "stage_crashed")

    # ---- 场次编排 -------------------------------------------------------

    def _desired_games(self, snapshot: TournamentSnapshot) -> set[str]:
        """以 active_games（当前进行中）为编排权威、config.M 为并发上限。"""

        ordered = sorted(snapshot.active_games)
        if len(ordered) > self._config.max_games:
            self._audit.emit(
                AuditKind.PROTOCOL_RECOVERED,
                {
                    "area": "game_reconcile",
                    "reason": "active_games 数量 {} 超过 config.M={}".format(
                        len(ordered), self._config.max_games
                    ),
                    "truncated_to": ordered[: self._config.max_games],
                },
            )
            ordered = ordered[: self._config.max_games]
        return set(ordered)

    def _reconcile_games(self, snapshot: TournamentSnapshot) -> None:
        if self._terminal is not None:
            return
        if snapshot.stage_crashed:
            # 崩溃快照不参与编排：旧尝试的场次只允许关闭，重开必须
            # 等待崩溃后的新权威快照（否则关闭回调会借陈旧 crashed
            # 快照里的 active_games 复活旧阶段场次）。
            return
        desired = self._desired_games(snapshot)
        for game_id in list(self._games):
            if game_id not in desired:
                # 场次从权威列表消失：取消长轮询并回收会话。
                self._schedule_close(game_id, "removed_from_active_games")
        # 权威列表移除后，退出登记与重开预算同步出清；同一 game_id 再次出现按全新场次对待。
        for game_id in list(self._retired_games):
            if game_id not in desired:
                del self._retired_games[game_id]
        for game_id in list(self._reopen_budgets):
            if game_id not in desired:
                del self._reopen_budgets[game_id]
        # 场次从权威列表消失时撤销在途重开任务：否则同 game_id 再次
        # 出现会被过期退避延迟挡住（旧延迟属于上一次生命周期）。
        for game_id in list(self._reopen_tasks):
            if game_id not in desired:
                stale = self._reopen_tasks.pop(game_id)
                if not stale.done():
                    stale.cancel()
                    self._retired_side_tasks.add(stale)
                    stale.add_done_callback(self._retired_side_tasks.discard)
        for game_id in sorted(desired):
            if (
                game_id in self._games
                or game_id in self._retired_games
                or game_id in self._reopen_tasks
                or game_id in self._closing_games
            ):
                continue
            try:
                self._open_game(game_id)
            except Exception as exc:  # noqa: BLE001 - 单场开场异常不得终止身份
                self._handle_open_failure(game_id, exc)

    def _open_game(self, game_id: str) -> None:
        session = self._session.open_game(game_id)
        task = asyncio.create_task(
            GameTask(
                game_id=game_id,
                session=session,
                services=self._services,
                competition_provider=lambda: self._competition,
                stage_attempt_provider=lambda: self._stage_attempt_id,
                item_backoff=self._supervision.new_game_item_backoff(),
                sleep=self._sleep,
            ).run(),
            name="game-{}".format(game_id),
        )
        self._games[game_id] = _GameSlot(game_id=game_id, session=session, task=task)
        task.add_done_callback(lambda _task, _gid=game_id: self._wake.set())
        self._audit.emit(
            AuditKind.LIFECYCLE_CHANGED,
            {"event": "game_opened", "game_id": game_id},
            game_id=game_id,
        )

    def _handle_open_failure(self, game_id: str, exc: Exception) -> None:
        """开场异常按该场的重开预算有界重试；耗尽则登记退出。"""

        budget = self._reopen_budget(game_id)
        delay = budget.next_delay_or_none()
        if delay is None:
            self._retired_games[game_id] = "abandoned"
            self._audit.emit(
                AuditKind.PROTOCOL_RECOVERED,
                {
                    "area": "game_open",
                    "reason": "开场反复异常且预算耗尽，放弃该场: {}".format(
                        audit_error_text(exc)
                    ),
                    "game_id": game_id,
                    "outcome": "abandon",
                },
                game_id=game_id,
            )
            self._audit.emit(
                AuditKind.LIFECYCLE_CHANGED,
                {"event": "game_ended", "game_id": game_id, "status": "abandoned", "detail": ""},
                game_id=game_id,
            )
            return
        self._audit.emit(
            AuditKind.PROTOCOL_RECOVERED,
            {
                "area": "game_open",
                "reason": "开场异常: {}".format(audit_error_text(exc)),
                "game_id": game_id,
                "retry_delay_seconds": delay,
            },
            game_id=game_id,
        )
        self._reopen_tasks[game_id] = asyncio.ensure_future(
            self._reopen_after(game_id, delay)
        )

    def _reopen_budget(self, game_id: str) -> BoundedBackoff:
        budget = self._reopen_budgets.get(game_id)
        if budget is None:
            budget = self._supervision.new_game_reopen_backoff()
            self._reopen_budgets[game_id] = budget
        return budget

    def _schedule_close(self, game_id: str, reason: str) -> None:
        """同步登记关闭并交给后台任务等待取消与 aclose 完成。"""

        slot = self._games.pop(game_id, None)
        if slot is None:
            return
        self._closing_games.add(game_id)
        reopen_task = self._reopen_tasks.pop(game_id, None)
        if reopen_task is not None and not reopen_task.done():
            reopen_task.cancel()
            # 保留清理所有权：被撤销的任务收尾由 shutdown 统一等待。
            self._retired_side_tasks.add(reopen_task)
            reopen_task.add_done_callback(self._retired_side_tasks.discard)
        slot.task.cancel()
        cleanup = asyncio.ensure_future(self._close_quietly(slot, reason))
        self._cleanup_tasks.add(cleanup)
        cleanup.add_done_callback(self._cleanup_tasks.discard)
        self._audit.emit(
            AuditKind.LIFECYCLE_CHANGED,
            {"event": "game_closed", "game_id": game_id, "reason": reason},
            game_id=game_id,
        )

    async def _close_quietly(self, slot: _GameSlot, reason: str) -> None:
        try:
            try:
                await slot.task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - 回收路径不放大异常
                pass
            try:
                await slot.session.aclose(reason)
            except Exception as exc:  # noqa: BLE001 - 关闭失败只记录不传播
                self._audit.emit(
                    AuditKind.PROTOCOL_RECOVERED,
                    {
                        "area": "game_session",
                        "reason": "aclose 异常: {}".format(audit_error_text(exc)),
                        "game_id": slot.game_id,
                    },
                    game_id=slot.game_id,
                )
        finally:
            # 关闭真正完成后才允许同 ID 重开；唤醒对账重新评估。
            self._closing_games.discard(slot.game_id)
            self._wake.set()

    def _reap_game_tasks(self) -> None:
        """回收已结束的场次任务并按分类处置；单场异常不影响其他场。"""

        for game_id, slot in list(self._games.items()):
            if not slot.task.done():
                continue
            del self._games[game_id]
            try:
                result: GameTaskResult = slot.task.result()
            except (asyncio.CancelledError, Exception) as exc:  # noqa: BLE001
                result = GameTaskResult(
                    game_id=game_id,
                    status=GameTaskStatus.RECOVERABLE_FAILURE,
                    detail="任务异常退出: {}".format(audit_error_text(exc)),
                )
            cleanup = asyncio.ensure_future(self._close_quietly(slot, "task_ended"))
            self._closing_games.add(game_id)
            self._cleanup_tasks.add(cleanup)
            cleanup.add_done_callback(self._cleanup_tasks.discard)

            if result.status is GameTaskStatus.FATAL:
                # 当前身份永久故障：结束整个运行，交由 shutdown 关闭其余场次。
                self._set_terminal(
                    result.terminal
                    or ParticipantTerminal(
                        reason=ParticipantTerminalReason.FATAL_PROTOCOL_ERROR,
                        last_snapshot=self._last_snapshot,
                        detail="场次任务报告永久故障但未携带终态（防御合成）",
                    )
                )
                return
            if result.status is GameTaskStatus.RECOVERABLE_FAILURE:
                budget = self._reopen_budget(game_id)
                delay = budget.next_delay_or_none()
                if delay is None:
                    self._retired_games[game_id] = "abandoned"
                    self._audit.emit(
                        AuditKind.PROTOCOL_RECOVERED,
                        {
                            "area": "game_reconcile",
                            "reason": "场次反复失败且重开预算耗尽，放弃该场",
                            "game_id": game_id,
                            "outcome": "abandon",
                        },
                        game_id=game_id,
                    )
                    self._audit.emit(
                        AuditKind.LIFECYCLE_CHANGED,
                        {
                            "event": "game_ended",
                            "game_id": game_id,
                            "status": "abandoned",
                            "detail": "",
                        },
                        game_id=game_id,
                    )
                    continue
                self._audit.emit(
                    AuditKind.PROTOCOL_RECOVERED,
                    {
                        "area": "game_reconcile",
                        "reason": "可恢复故障，计划权威重开: {}".format(
                            audit_text(result.detail)
                        ),
                        "game_id": game_id,
                        "retry_delay_seconds": delay,
                    },
                    game_id=game_id,
                )
                self._reopen_tasks[game_id] = asyncio.ensure_future(
                    self._reopen_after(game_id, delay)
                )
                continue
            # 权威终局或不可恢复故障：登记退出，直到权威列表移除或新尝试。
            if result.status is GameTaskStatus.FINISHED:
                self._retired_games[game_id] = "finished"
            else:
                self._retired_games[game_id] = "unrecoverable_failure"
            self._audit.emit(
                AuditKind.LIFECYCLE_CHANGED,
                {
                    "event": "game_ended",
                    "game_id": game_id,
                    "status": result.status.value,
                    "detail": audit_text(result.detail),
                },
                game_id=game_id,
            )

    async def _reopen_after(self, game_id: str, delay: float) -> None:
        current = asyncio.current_task()
        try:
            await self._sleep(delay)
        except asyncio.CancelledError:
            # 按任务身份判定：被撤销的旧一代协程不得误删新一代的映射，
            # 否则下一张快照会在新延迟仍在途时重复开场。
            if self._reopen_tasks.get(game_id) is current:
                self._reopen_tasks.pop(game_id, None)
            raise
        if self._reopen_tasks.get(game_id) is current:
            self._reopen_tasks.pop(game_id, None)
        # 唤醒对账循环；若该场仍在 active_games 且未退出登记，将建立新会话。
        self._wake.set()

    # ---- 赛事更新轮询 ---------------------------------------------------

    async def _consume_update(self, task: "asyncio.Task[object]") -> None:
        self._update_task = None
        try:
            update = task.result()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - 轮询异常按有界恢复处理
            delay = self._poll_backoff.next_delay_or_none()
            if delay is None:
                self._set_terminal(
                    ParticipantTerminal(
                        reason=ParticipantTerminalReason.FATAL_PROTOCOL_ERROR,
                        last_snapshot=self._last_snapshot,
                        detail="赛事状态轮询连续失败: {}".format(audit_error_text(exc)),
                    )
                )
                return
            self._audit.emit(
                AuditKind.PROTOCOL_RECOVERED,
                {
                    "area": "tournament_poll",
                    "reason": "next_update 异常: {}".format(audit_error_text(exc)),
                    "retry_delay_seconds": delay,
                },
            )
            # 延迟任务本身即轮询门：完成前主循环不再创建下一轮 next_update。
            if self._delayed_wake is not None and not self._delayed_wake.done():
                return
            self._delayed_wake = asyncio.ensure_future(self._poll_gate_coro(delay))
            return
        if isinstance(update, ParticipantTerminal):
            self._set_terminal(update)
            return
        self._poll_backoff.reset()
        await self._handle_snapshot(update)

    async def _poll_gate_coro(self, delay: float) -> None:
        try:
            await self._sleep(delay)
        except asyncio.CancelledError:
            raise
        self._wake.set()

    # ---- 关闭 -----------------------------------------------------------

    async def _shutdown(self) -> None:
        """取消全部任务并回收会话；任何一步失败都不改变终态。"""

        # 关闭门先行：此后 done 回调与启动器都不得复活任何后台命令，
        # 否则取消在途 ready 时回调会立刻重建 worker 并泄漏到关闭之外。
        self._shutting_down = True
        side_tasks: list["asyncio.Task[object]"] = []
        for attr in ("_ready_task", "_register_task"):
            task = getattr(self, attr)
            if task is not None:
                if not task.done():
                    task.cancel()
                side_tasks.append(task)  # 保存旧引用：gather 必须等它完成
            setattr(self, attr, None)  # 先清引用，回调跳过重启判定
        if self._wake_task is not None:
            self._wake_task.cancel()
            # 纳入 gather：runtime 返回前 wake waiter 必须完成取消落地。
            side_tasks.append(self._wake_task)
            self._wake_task = None
        for task in list(self._reopen_tasks.values()):
            task.cancel()
        if self._delayed_wake is not None:
            self._delayed_wake.cancel()
        if self._update_task is not None:
            self._update_task.cancel()
        slots = list(self._games.values())
        self._games.clear()
        for slot in slots:
            slot.task.cancel()
        pending: list["asyncio.Task[object]"] = [slot.task for slot in slots]
        if self._update_task is not None:
            pending.append(self._update_task)
        if self._delayed_wake is not None:
            pending.append(self._delayed_wake)
        pending.extend(side_tasks)
        pending.extend(self._retired_side_tasks)
        pending.extend(self._reopen_tasks.values())
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        for slot in slots:
            await self._close_quietly(slot, "supervisor_shutdown")
        if self._cleanup_tasks:
            await asyncio.gather(*list(self._cleanup_tasks), return_exceptions=True)
        self._cleanup_tasks.clear()

