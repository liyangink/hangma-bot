"""AutoMatchRuntime：一次 AUTO_MATCH 自动房操作的专用运行时。

职责边界（application 模块规范 + doc/implementation/free-match-start.md §3）：
- 只处理：初始化（入席/恢复）→ 等待开赛 → 按 active_games 运行最多
  config.M 场并发 → 房间终局宽限内汇总/收尾 → 退出；不做 register/ready，
  不产生第二套赛事阶段语义；
- 复用 GameTask / run_action_window（decision_loop）与既有预算；每场会话由
  TournamentSessionPort.open_game 提供（沿用其传输/调度/SSE/动作门安全路径）；
- 房间 finished/closed/void 的参赛者终态判定只在本运行时（适配器一律返回
  普通变化快照）；认证/容量/匹配不可用等会话分类故障原样透传；
- 一个进程只运行一次自动房操作（完成即退出），不在本类内循环参加下一间房。

自动房的场次编排要点（与赛事阶段监督不同）：
- 可运行集合 = 房间 my_games 与 /api/me.active_games 的交集（适配器已投影），
  本运行时只按快照 active_games 建立场次，最多 config.M 个；
- 运行期离开 active_games 的场次任务被关闭（其结果在房间终局宽限内由
  draining 补抓，官方宽限内 /state 仍返回 finished 终局快照）；
- 房间终局（finished）后有官方约 60 秒宽限：本运行时进入 draining 阶段，
  为 my_games 中尚未取得终局记录的场次补开会话并限时汇总；宽限内仍缺失的
  结果按"记录缺失/未知"审计，不伪造终局，也不等待门户页面才关闭记录器；
- 房间 closed 表示平台已关停（此后玩家 API 404）：立即按已有证据收尾并
  记录缺失，不空等剩余宽限。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, List, Optional

from hangma_bot.application.audit import AuditTrail, audit_error_text, audit_text
# audit-plus-v1 RUN_MANIFEST 增强字段共享助手（participant_runtime 定义，
# 方案 §3.2；字段集以该处为唯一来源，避免两个运行时各自维护一份词表）。
from hangma_bot.application.participant_runtime import _audit_plus_manifest_fields
from hangma_bot.application.contracts import (
    AuditKind,
    AuditSink,
    AuditSummary,
    ParticipantTerminal,
    ParticipantTerminalReason,
    RuntimeMode,
    RuntimeTarget,
    SessionBootstrap,
    TournamentSessionPort,
    TournamentSnapshot,
    TournamentStatus,
)
from hangma_bot.application.deadline import (
    BoundedBackoff,
    BudgetPolicy,
    RuntimeClock,
    SystemClock,
)
from hangma_bot.application.decision_loop import RuntimeServices
from hangma_bot.application.game_task import GameTask, GameTaskStatus
from hangma_bot.application.ids import IdGenerator, PrefixedUuidIds
from hangma_bot.application.tournament_supervisor import SupervisionPolicy
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.policy.interface import BotPolicy

DEFAULT_SLEEP: Callable[[float], Awaitable[None]] = asyncio.sleep

# 官方房间状态到参赛者终态原因的映射（自动房无 register/ready/资格语义，
# 只保留赛事终态映射；测试房间跨轮复用分支不适用于自动房）。
_TERMINAL_STATUS_REASON = {
    TournamentStatus.FINISHED: ParticipantTerminalReason.TOURNAMENT_FINISHED,
    TournamentStatus.CLOSED: ParticipantTerminalReason.TOURNAMENT_CLOSED,
    TournamentStatus.VOID: ParticipantTerminalReason.TOURNAMENT_VOID,
}

# 房间终态后宽限收尾的默认值（秒）：官方 finished 后约 60 秒关停
# （API 文档 §2.6），默认在宽限内预留余量完成补抓与汇总。
DEFAULT_DRAIN_GRACE_SECONDS = 45.0


@dataclass(frozen=True)
class AutoMatchSettings:
    """自动匹配运行设置（自由赛线配置模型；时间字段单位均为秒）。

    声明上限与 match 协议参数在会话层使用（见 OfficialAutoMatchSession）；
    drain_grace_seconds 是本运行时在房间终态宽限内的收尾预算。0 表示不声明
    （接受服务默认配置 M=10/Rounds=8，v15 起）。
    """

    source_namespace: str = ""  # 部署配置中的逻辑平台实例名（未来审计身份映射用）
    declared_max_games: int = 0  # 请求体声明的可承受 M；低于服务默认会被本地拦截
    declared_rounds: int = 0  # 请求体声明的可承受 Rounds
    match_min_interval_sec: float = 6.5  # 10 次/分配额：≥6s/次并留余量
    match_max_attempts: int = 5  # 同一次 match 操作的最大尝试次数
    match_busy_wait_cap_sec: float = 60.0  # 单次 MATCH_BUSY/限速等待上限
    drain_grace_seconds: float = DEFAULT_DRAIN_GRACE_SECONDS  # 房间终局收尾宽限
    room_poll_interval_sec: float = 2.0  # 房间轮询间隔（会话层使用）

    def __post_init__(self) -> None:
        for name in ("declared_max_games", "declared_rounds", "match_max_attempts"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("{} 必须是非负整数".format(name))
        if self.match_max_attempts < 1:
            raise ValueError("match_max_attempts 必须 ≥ 1")
        for name in (
            "match_min_interval_sec",
            "match_busy_wait_cap_sec",
            "drain_grace_seconds",
            "room_poll_interval_sec",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise ValueError("{} 必须是非负秒数".format(name))
        if self.drain_grace_seconds <= 0:
            raise ValueError("drain_grace_seconds 必须为正数")


@dataclass
class _GameSlot:
    """一个 game_id 的在管场次：会话与任务成对。"""

    game_id: str
    session: object  # GameSessionPort 实例（运行时只调用其公开方法）
    task: "asyncio.Task"


class AutoMatchRuntime:
    """恰好对应一次 AUTO_MATCH 自动房操作的运行时；run() 返回参赛者终态。

    与 ParticipantRuntime 的差异：目标允许为空（尚未发现自动房），初始化由
    会话完成一次显式 match 入席；运行期只管理一个房间的场次与终局收尾。
    所有出口（正常终态、初始化失败、监督异常、外部取消）都经过统一清理：
    关闭会话、回收任务并限时冲刷审计。
    """

    def __init__(
        self,
        *,
        session: TournamentSessionPort,
        policy: BotPolicy,
        audit_sink: AuditSink,
        target: RuntimeTarget,
        settings: Optional[AutoMatchSettings] = None,
        rules_factory: Callable = HangmaRules,
        clock: Optional[RuntimeClock] = None,
        ids: Optional[IdGenerator] = None,
        budget_policy: Optional[BudgetPolicy] = None,
        supervision: Optional[SupervisionPolicy] = None,
        sleep: Callable[[float], Awaitable[None]] = DEFAULT_SLEEP,
    ) -> None:
        if target.mode is not RuntimeMode.AUTO_MATCH:
            raise ValueError("AutoMatchRuntime 只服务 RuntimeMode.AUTO_MATCH")
        self._session = session
        self._policy = policy
        self._audit_sink = audit_sink
        self._target = target
        self._settings = settings if settings is not None else AutoMatchSettings()
        self._rules_factory = rules_factory
        self._clock = clock if clock is not None else SystemClock()
        self._ids = ids if ids is not None else PrefixedUuidIds()
        self._budget_policy = budget_policy if budget_policy is not None else BudgetPolicy()
        self._supervision = supervision if supervision is not None else SupervisionPolicy()
        self._sleep = sleep
        self._run_id: Optional[str] = None
        self._audit_trail: Optional[AuditTrail] = None
        self._last_audit_summary: Optional[AuditSummary] = None
        # 硬截止放弃的策略任务：动作路径不等待，运行出口限期回收。
        self._abandoned_policy_tasks: set = set()

    @property
    def run_id(self) -> Optional[str]:
        """本次运行的审计 run_id；run() 启动前为空。"""

        return self._run_id

    @property
    def audit_degraded(self) -> bool:
        """审计链是否发生过丢失或降级；动作路径不受其影响。"""

        return self._audit_trail.audit_degraded if self._audit_trail is not None else False

    @property
    def last_audit_summary(self) -> Optional[AuditSummary]:
        """sink 关闭时返回的覆盖统计；run() 结束前为空。"""

        return self._last_audit_summary

    async def run(self) -> ParticipantTerminal:
        """运行一次自动房操作到参赛者终态；支持异步取消。

        出口统一：正常终态、初始化失败/取消、监督异常都写 PARTICIPANT_FINISHED、
        关闭会话并限时冲刷审计（与 ParticipantRuntime 同构）。
        """

        self._run_id = self._ids.new_run_id()
        trail: Optional[AuditTrail] = None
        terminal: Optional[ParticipantTerminal] = None
        finished_emitted = False
        try:
            try:
                bootstrap = await self._session.initialize(self._target)
            except asyncio.CancelledError:
                trail = self._early_trail()
                self._emit_early_manifest(trail, early_exit=True)
                trail.emit(
                    AuditKind.PARTICIPANT_FINISHED,
                    {"reason": "cancelled", "detail": "初始化期间被外部取消"},
                )
                finished_emitted = True
                raise
            except Exception as exc:  # noqa: BLE001 - 初始化异常按永久故障处理
                terminal = ParticipantTerminal(
                    reason=ParticipantTerminalReason.FATAL_PROTOCOL_ERROR,
                    last_snapshot=None,
                    detail="初始化异常: {}".format(audit_error_text(exc)),
                )
                trail = self._early_trail()
                self._emit_early_manifest(trail, early_exit=True)
                trail.emit(
                    AuditKind.LIFECYCLE_CHANGED,
                    {"area": "auto_match", "event": "matching_stopped", "reason": terminal.reason.value},
                )
                trail.emit(
                    AuditKind.PARTICIPANT_FINISHED,
                    {"reason": terminal.reason.value, "detail": terminal.detail},
                )
                finished_emitted = True
                return terminal
            if isinstance(bootstrap, ParticipantTerminal):
                terminal = bootstrap
                trail = self._early_trail()
                self._emit_early_manifest(trail, early_exit=True)
                # 终态事件唯一归应用层（适配器只返回终态值，不再自发射）：
                # 初始化即终态时在这里补 matching_stopped + PARTICIPANT_FINISHED。
                trail.emit(
                    AuditKind.LIFECYCLE_CHANGED,
                    {"area": "auto_match", "event": "matching_stopped", "reason": terminal.reason.value},
                )
                trail.emit(
                    AuditKind.PARTICIPANT_FINISHED,
                    {"reason": terminal.reason.value, "detail": audit_text(terminal.detail)},
                )
                finished_emitted = True
                return terminal

            rejection = self._validate_bootstrap(bootstrap)
            if rejection is not None:
                terminal = rejection
                trail = AuditTrail(
                    self._audit_sink,
                    run_id=self._run_id,
                    tournament_id=bootstrap.tournament_id,
                    participant_id=bootstrap.participant_id,
                    clock=self._clock,
                )
                self._audit_trail = trail
                trail.emit(
                    AuditKind.RUN_MANIFEST,
                    {
                        **_audit_plus_manifest_fields(
                            self._settings.source_namespace, None
                        ),
                        "run_id": self._run_id,
                        "mode": self._target.mode.value,
                        "expected_tournament_id": self._target.expected_tournament_id,
                        "known_guide_version": self._target.known_guide_version,
                        "guide_version": bootstrap.guide.version,
                        "early_exit": True,
                    },
                )
                trail.emit(
                    AuditKind.LIFECYCLE_CHANGED,
                    {"area": "auto_match", "event": "matching_stopped", "reason": terminal.reason.value},
                )
                trail.emit(
                    AuditKind.PARTICIPANT_FINISHED,
                    {"reason": terminal.reason.value, "detail": audit_text(terminal.detail)},
                )
                finished_emitted = True
                return terminal

            trail = AuditTrail(
                self._audit_sink,
                run_id=self._run_id,
                tournament_id=bootstrap.tournament_id,
                participant_id=bootstrap.participant_id,
                clock=self._clock,
            )
            self._audit_trail = trail
            trail.emit(
                AuditKind.RUN_MANIFEST,
                {
                    **_audit_plus_manifest_fields(
                        self._settings.source_namespace, None
                    ),
                    "run_id": self._run_id,
                    "mode": self._target.mode.value,
                    "expected_tournament_id": self._target.expected_tournament_id,
                    "known_guide_version": self._target.known_guide_version,
                    "guide_version": bootstrap.guide.version,
                    "guide_updated_at": bootstrap.guide.updated_at,
                    "participant_id": bootstrap.participant_id,
                    "room_id": bootstrap.tournament_id,
                    "ruleset_version": bootstrap.config.rules.ruleset_version,
                    "max_games": bootstrap.config.max_games,
                    "rounds_per_game": bootstrap.config.rounds_per_game,
                    "timing": {
                        "peng_timeout_sec": bootstrap.config.timing.peng_timeout_sec,
                        "chi_timeout_sec": bootstrap.config.timing.chi_timeout_sec,
                        "discard_timeout_sec": bootstrap.config.timing.discard_timeout_sec,
                    },
                },
            )

            services = RuntimeServices(
                rules=self._rules_factory(bootstrap.config.rules),
                policy=self._policy,
                audit=trail,
                clock=self._clock,
                ids=self._ids,
                budget_policy=self._budget_policy,
                abandoned_tasks=self._abandoned_policy_tasks,
            )
            terminal = await self._run_room(bootstrap, services)
            trail.emit(
                AuditKind.PARTICIPANT_FINISHED,
                {"reason": terminal.reason.value, "detail": audit_text(terminal.detail)},
            )
            finished_emitted = True
            return terminal
        except asyncio.CancelledError:
            raise  # finally 负责清理与尽力冲刷
        except Exception as exc:  # noqa: BLE001 - 监督循环缺陷不能悬挂进程
            if trail is not None:
                trail.emit(
                    AuditKind.PROTOCOL_RECOVERED,
                    {
                        "area": "auto_match",
                        "reason": "监督循环异常退出: {}".format(audit_error_text(exc)),
                    },
                )
            terminal = ParticipantTerminal(
                reason=ParticipantTerminalReason.FATAL_PROTOCOL_ERROR,
                last_snapshot=None,
                detail="监督循环异常: {}".format(audit_error_text(exc)),
            )
            if trail is not None:
                trail.emit(
                    AuditKind.PARTICIPANT_FINISHED,
                    {"reason": terminal.reason.value, "detail": terminal.detail},
                )
                finished_emitted = True
            return terminal
        finally:
            # 覆盖所有出口：取消、异常、早退与正常返回都关闭会话并冲刷审计。
            if trail is not None and not finished_emitted:
                try:
                    trail.emit(
                        AuditKind.PARTICIPANT_FINISHED,
                        {"reason": "cancelled", "detail": "运行被外部取消"},
                    )
                except Exception:  # noqa: BLE001 - 取消路径审计尽力而为
                    pass
            await self._close_session_quietly()
            if self._abandoned_policy_tasks:
                pending_abandoned = {
                    task for task in self._abandoned_policy_tasks if not task.done()
                }
                if pending_abandoned:
                    await asyncio.wait(
                        pending_abandoned,
                        timeout=self._supervision.audit_flush_seconds,
                    )
                    for task in pending_abandoned:
                        if not task.done():
                            task.cancel()
                self._abandoned_policy_tasks.clear()
            try:
                if trail is not None:
                    self._last_audit_summary = await trail.aclose(
                        self._supervision.audit_flush_seconds
                    )
                else:
                    await self._audit_sink.aclose(self._supervision.audit_flush_seconds)
            except Exception:  # noqa: BLE001 - 冲刷失败不掩盖运行结果
                self._last_audit_summary = None

    # ---------- 房间监督循环（自动房专用，无 register/ready/资格） ----------

    async def _run_room(
        self, bootstrap: SessionBootstrap, services: RuntimeServices
    ) -> ParticipantTerminal:
        """运行自动房主循环：等待快照变化 + 内部事件（场次/补开/收尾定时器）。

        结构沿用 TournamentSupervisor.run 的双源事件循环骨架，去掉赛事阶段
        语义：等待（waiting）→ 运行（running，按 active_games 建/收场次）→
        房间终态进入 draining 限时收尾 → 返回参赛者终态。下一轮房间轮询
        与内部事件（场次结束、补开到期、宽限截止）竞速，任一先到即处理。
        """

        self._audit = services.audit
        self._services = services
        self._config = bootstrap.config
        self._competition = bootstrap.initial_snapshot.competition
        self._last_snapshot = bootstrap.initial_snapshot
        self._games: Dict[str, _GameSlot] = {}
        self._retired: Dict[str, str] = {}  # game_id → finished/unrecoverable_failure/abandoned
        self._reopen_budgets: Dict[str, BoundedBackoff] = {}
        self._reopen_tasks: Dict[str, "asyncio.Task"] = {}
        self._closing: set = set()
        self._cleanup_tasks: set = set()
        self._wake = asyncio.Event()
        self._wake_task: Optional["asyncio.Task"] = None
        self._update_task: Optional["asyncio.Task"] = None
        self._drain_timer: Optional["asyncio.Task"] = None
        self._drain_deadline_at: Optional[float] = None
        self._draining = False
        self._drain_missing_reported = False
        self._phase: Optional[str] = None  # waiting/running/draining；None=尚未按快照定相
        self._terminal: Optional[ParticipantTerminal] = None
        self._shutting_down = False
        try:
            self._handle_snapshot(bootstrap.initial_snapshot)
            while self._terminal is None:
                if self._update_task is None or self._update_task.done():
                    if not self._shutting_down:
                        self._update_task = asyncio.create_task(self._session.next_update())
                self._wake_task = asyncio.ensure_future(self._wake.wait())
                done, _pending = await asyncio.wait(
                    {t for t in (self._update_task, self._wake_task) if t is not None},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if self._wake_task in done:
                    self._wake.clear()
                    if self._terminal is not None:
                        continue
                    self._reap_game_tasks()
                    if self._terminal is None and self._last_snapshot is not None:
                        self._reconcile(self._last_snapshot)
                if self._update_task is not None and self._update_task in done:
                    if self._wake_task is not None and not self._wake_task.done():
                        self._wake_task.cancel()
                    finished_update = self._update_task
                    self._update_task = None
                    if self._terminal is None:
                        await self._consume_update(finished_update)
                    elif not finished_update.cancelled():
                        finished_update.exception()
            return self._terminal
        finally:
            await self._shutdown()

    # ---------- 快照处理 ----------

    def _handle_snapshot(self, snapshot: TournamentSnapshot) -> None:
        """按权威快照推进自动房状态；返回前不等待任何后台任务。"""

        if self._terminal is not None:
            return
        self._last_snapshot = snapshot
        self._competition = snapshot.competition
        self._audit.emit(
            AuditKind.AUTHORITATIVE_STATE,
            {
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
            },
        )
        status = snapshot.status
        if status in _TERMINAL_STATUS_REASON:
            if status is TournamentStatus.FINISHED:
                if not self._draining:
                    self._enter_draining(snapshot)
                else:
                    self._reconcile(snapshot)  # my_games 可能有更新：继续补抓
            else:
                # closed/void：平台已关停或作废，不再有可补抓的终局数据。
                self._finalize_room_end(snapshot)
            return
        if self._phase is None:
            self._enter_phase("waiting")
        if self._phase == "waiting" and (snapshot.active_games or snapshot.my_games):
            self._enter_phase("running")
        # 运行/等待中：按 active_games 对账场次（draining 分支见 _reconcile）。
        self._reconcile(snapshot)

    def _finalize_room_end(self, snapshot: TournamentSnapshot) -> None:
        """房间 closed/void 的立即收尾：按已有证据汇总并终态化。

        closed 意味着玩家 API 已 404（官方 finished 后约 60 秒宽限结束），
        未取得终局的场次无法再补抓：记录缺失但不伪造终局。void 无终局
        可留存（官方作废）。
        """

        status = snapshot.status
        if status is TournamentStatus.VOID:
            self._audit.emit(
                AuditKind.PROTOCOL_RECOVERED,
                {
                    "area": "auto_match",
                    "reason": "room_void_no_final_collection",
                    "room_status": status.value,
                },
            )
            self._set_terminal(
                ParticipantTerminalReason.TOURNAMENT_VOID, "自动房进入作废状态，无终局可留存"
            )
            return
        # closed：先按已有证据汇总缺失，再关闭在管场次并终态化。
        missing = [
            g for g in snapshot.my_games if self._retired.get(g) != "finished"
        ]
        if missing:
            self._audit.emit(
                AuditKind.PROTOCOL_RECOVERED,
                {
                    "area": "auto_match",
                    "reason": "drain_missing_finals",
                    "missing_games": missing,
                    "deadline_passed": True,
                },
            )
        for game_id in list(self._games):
            self._schedule_close(game_id, "room_closed")
        suffix = ""
        if missing:
            suffix = "；{} 场缺少终局记录（结果缺失/未知）：{}".format(
                len(missing), ",".join(missing)
            )
        self._set_terminal(
            ParticipantTerminalReason.TOURNAMENT_CLOSED, "自动房已关闭" + suffix
        )

    def _enter_draining(self, snapshot: TournamentSnapshot) -> None:
        """房间 finished：进入宽限收尾（draining），为缺失终局场次补开会话。

        官方 finished 后约 60 秒宽限内，已结束场次的 /state 仍返回终局快照；
        drain_grace_seconds 默认 45 秒，收尾在官方关停前完成。
        """

        if not snapshot.my_games and not self._games and not self._retired:
            # 平台确认 finished 但本进程从未观察到任何场次：不做完整宣称，
            # 显式记录（可能发生在错过全部场次或房间异常作结时）。
            self._audit.emit(
                AuditKind.PROTOCOL_RECOVERED,
                {
                    "area": "auto_match",
                    "reason": "room_finished_without_observed_games",
                    "room_status": snapshot.status.value,
                },
            )
        self._enter_phase("draining")
        self._draining = True
        now = self._clock.now()
        self._drain_deadline_at = now + self._settings.drain_grace_seconds
        self._arm_drain_timer()
        self._audit.emit(
            AuditKind.LIFECYCLE_CHANGED,
            {
                "area": "auto_match",
                "event": "draining",
                "room_status": snapshot.status.value,
                "drain_grace_seconds": self._settings.drain_grace_seconds,
            },
        )
        self._reconcile(snapshot)  # 为缺失终局的场次补开会话

    def _arm_drain_timer(self) -> None:
        """为宽限截止武装定时任务（到点唤醒主循环做最终汇总）。

        已武装（未完成）时不重复创建；终态/关停路径由 _shutdown 取消。
        """

        if self._drain_timer is not None and not self._drain_timer.done():
            return
        if self._drain_deadline_at is None:
            return

        async def _wait_deadline() -> None:
            remaining = self._drain_deadline_at - self._clock.now()
            if remaining > 0:
                await self._sleep(remaining)
            self._wake.set()

        self._drain_timer = asyncio.ensure_future(_wait_deadline())

    def _enter_phase(self, phase: str) -> None:
        """自动房阶段切换（waiting/running/draining）；只发射一次。"""

        if self._phase == phase:
            return
        self._phase = phase
        if phase in ("waiting", "running"):
            self._audit.emit(
                AuditKind.LIFECYCLE_CHANGED, {"area": "auto_match", "event": phase}
            )

    def _set_terminal(self, reason: ParticipantTerminalReason, detail: str) -> None:
        """首写优先的终态化；同时发射收尾生命周期事件。"""

        if self._terminal is not None:
            return
        if reason in (
            ParticipantTerminalReason.TOURNAMENT_FINISHED,
            ParticipantTerminalReason.TOURNAMENT_CLOSED,
            ParticipantTerminalReason.TOURNAMENT_VOID,
        ):
            event = "finished"
        else:
            event = "matching_stopped"
        self._audit.emit(
            AuditKind.LIFECYCLE_CHANGED,
            {"area": "auto_match", "event": event, "reason": reason.value},
        )
        self._terminal = ParticipantTerminal(
            reason=reason, last_snapshot=self._last_snapshot, detail=detail
        )

    def _adopt_terminal(self, terminal: ParticipantTerminal) -> None:
        """原样采纳会话/场次返回的分类终态（首写优先，保留其 last_snapshot）。"""

        if self._terminal is not None:
            return
        self._audit.emit(
            AuditKind.LIFECYCLE_CHANGED,
            {
                "area": "auto_match",
                "event": "finished"
                if terminal.reason
                in (
                    ParticipantTerminalReason.TOURNAMENT_FINISHED,
                    ParticipantTerminalReason.TOURNAMENT_CLOSED,
                    ParticipantTerminalReason.TOURNAMENT_VOID,
                )
                else "matching_stopped",
                "reason": terminal.reason.value,
            },
        )
        self._terminal = terminal

    async def _consume_update(self, update_task: "asyncio.Task") -> None:
        """消费一次 next_update 结果（变化快照或会话分类终态）。"""

        try:
            item = update_task.result()
        except asyncio.CancelledError:
            return
        except Exception as exc:  # noqa: BLE001 - 会话层异常按监督故障处理
            if self._terminal is not None:
                return
            self._audit.emit(
                AuditKind.PROTOCOL_RECOVERED,
                {
                    "area": "auto_match",
                    "reason": "next_update 异常: {}".format(audit_error_text(exc)),
                },
            )
            self._set_terminal(
                ParticipantTerminalReason.FATAL_PROTOCOL_ERROR,
                "房间轮询异常: {}".format(audit_error_text(exc)),
            )
            return
        if isinstance(item, ParticipantTerminal):
            self._adopt_terminal(item)
            return
        self._handle_snapshot(item)

    # ---------- 场次对账与收尾 ----------

    def _reconcile(self, snapshot: TournamentSnapshot) -> None:
        """把在管场次与期望集合对账；draining 期对账把缺失终局场次补开。

        运行期期望集合 = 快照 active_games（防御性截断到 config.M 并诊断，
        正常不触发：适配器已按房间 my_games 交集投影）；收尾期期望集合 =
        my_games 中尚未记录终局的场次（宽限内补抓）。
        """

        if self._terminal is not None or self._shutting_down:
            return
        if self._draining:
            desired: List[str] = self._pending_finals(snapshot)
        else:
            desired = list(snapshot.active_games)
            if len(desired) > self._config.max_games:
                self._audit.emit(
                    AuditKind.PROTOCOL_RECOVERED,
                    {
                        "area": "auto_match",
                        "reason": "active_exceeds_config_m",
                        "active_count": len(desired),
                        "config_max_games": self._config.max_games,
                        "truncated_to": self._config.max_games,
                    },
                )
                desired = desired[: self._config.max_games]
        desired_set = set(desired)
        # 关闭不在期望集合的在管场次（运行期离开 active 的场次由收尾期补抓；
        # 收尾期已记录终局的场次同样退出在管集合）。
        for game_id in list(self._games):
            if game_id not in desired_set:
                self._schedule_close(game_id, "removed_from_expected")
        # 取消不再期望的在途补开任务。
        for game_id in list(self._reopen_tasks):
            if game_id not in desired_set:
                task = self._reopen_tasks.pop(game_id)
                if not task.done():
                    task.cancel()
        # 打开缺失的场次。
        for game_id in desired:
            if game_id in self._games or game_id in self._closing or game_id in self._retired:
                continue
            reopen = self._reopen_tasks.get(game_id)
            if reopen is not None and not reopen.done():
                continue  # 补开在途：等其到期后由对账重开
            self._open_game(game_id)
        # draining 收尾判定：全部已记录、宽限耗尽或已无在管场次。
        if self._draining and self._terminal is None:
            self._check_drain_done()

    def _pending_finals(self, snapshot: TournamentSnapshot) -> List[str]:
        """收尾期仍需补抓的场次：房间 my_games 中无终局记录的场次。

        不可恢复失败/放弃的场次不再补抓（结果缺失已在当时审计）；已取消任务
        但未取得终局的场次仍在补抓名单内（官方宽限内 /state 仍返回终局）。
        """

        pending = []
        for game_id in snapshot.my_games:
            outcome = self._retired.get(game_id)
            if outcome == "finished":
                continue
            if outcome in ("unrecoverable_failure", "abandoned"):
                continue
            if game_id in self._games or game_id in self._closing:
                continue  # 在管任务自己会完成终局记录
            pending.append(game_id)
        return sorted(pending)

    def _open_game(self, game_id: str) -> None:
        """创建一个场次任务；任务结束经回调唤醒主循环做对账。"""

        try:
            session = self._session.open_game(game_id)
        except Exception as exc:  # noqa: BLE001 - 开会话失败按放弃处理并留痕
            self._audit.emit(
                AuditKind.PROTOCOL_RECOVERED,
                {
                    "area": "auto_match",
                    "reason": "open_game 失败: {}".format(audit_error_text(exc)),
                    "game_id": game_id,
                },
                game_id=game_id,
            )
            self._retire_game(game_id, "abandoned")
            return
        task = asyncio.create_task(
            GameTask(
                game_id=game_id,
                session=session,
                services=self._services,
                competition_provider=lambda: self._competition,
                stage_attempt_provider=lambda: None,  # 自动房无阶段尝试
                item_backoff=self._supervision.new_game_item_backoff(),
                sleep=self._sleep,
            ).run(),
            name="auto-game-{}".format(game_id),
        )
        self._games[game_id] = _GameSlot(game_id=game_id, session=session, task=task)
        task.add_done_callback(lambda _t, _gid=game_id: self._wake.set())
        self._audit.emit(
            AuditKind.LIFECYCLE_CHANGED,
            {"area": "auto_match", "event": "game_opened", "game_id": game_id},
            game_id=game_id,
        )
        if self._phase == "waiting":
            self._enter_phase("running")

    def _reap_game_tasks(self) -> None:
        """收集已结束的场次任务并按结果分类处置。"""

        for game_id in list(self._games):
            slot = self._games[game_id]
            if not slot.task.done():
                continue
            self._games.pop(game_id)
            try:
                result = slot.task.result()
            except asyncio.CancelledError:
                # 任务被取消：会话已由 _schedule_close 关闭路径处理，结果缺失
                # 与否由收尾期补抓/汇总判定。
                self._retire_game(game_id, "abandoned")
                continue
            except Exception as exc:  # noqa: BLE001 - 防御：任务异常按可恢复处理
                self._audit.emit(
                    AuditKind.PROTOCOL_RECOVERED,
                    {
                        "area": "auto_match",
                        "reason": "game_task 异常: {}".format(audit_error_text(exc)),
                        "game_id": game_id,
                    },
                    game_id=game_id,
                )
                self._handle_game_failure(game_id)
                continue
            if result.status is GameTaskStatus.FINISHED:
                self._retire_game(game_id, "finished")
            elif result.status is GameTaskStatus.FATAL:
                if result.terminal is not None:
                    self._adopt_terminal(result.terminal)
                else:
                    self._set_terminal(
                        ParticipantTerminalReason.FATAL_PROTOCOL_ERROR,
                        "场次任务致命故障（无终态载体）: {}".format(result.detail),
                    )
            elif result.status is GameTaskStatus.RECOVERABLE_FAILURE:
                self._handle_game_failure(game_id)
            else:  # UNRECOVERABLE_FAILURE
                self._retire_game(game_id, "unrecoverable_failure")
        if self._draining and self._terminal is None:
            self._check_drain_done()

    def _retire_game(self, game_id: str, outcome: str) -> None:
        """记录场次结局并发射生命周期事件；供对账跳过重复处置。"""

        self._retired[game_id] = outcome
        self._audit.emit(
            AuditKind.LIFECYCLE_CHANGED,
            {
                "area": "auto_match",
                "event": "game_ended",
                "game_id": game_id,
                "status": outcome,
            },
            game_id=game_id,
        )

    def _handle_game_failure(self, game_id: str) -> None:
        """可恢复场次故障：按 game_id 有界补开；收尾期受宽限约束。

        超过补开预算、或补开时点已越过房间收尾宽限 → 放弃该场并把结果
        计入缺失（不再补抓）。
        """

        budget = self._reopen_budgets.get(game_id)
        if budget is None:
            budget = self._supervision.new_game_reopen_backoff()
            self._reopen_budgets[game_id] = budget
        delay = budget.next_delay_or_none()
        if delay is None:
            self._audit.emit(
                AuditKind.PROTOCOL_RECOVERED,
                {
                    "area": "auto_match",
                    "reason": "game_reopen_budget_exhausted",
                    "game_id": game_id,
                },
                game_id=game_id,
            )
            self._retire_game(game_id, "abandoned")
            return
        if self._draining and self._drain_deadline_at is not None:
            if self._clock.now() + delay >= self._drain_deadline_at:
                self._audit.emit(
                    AuditKind.PROTOCOL_RECOVERED,
                    {
                        "area": "auto_match",
                        "reason": "game_reopen_beyond_drain_deadline",
                        "game_id": game_id,
                        "retry_delay_seconds": delay,
                    },
                    game_id=game_id,
                )
                self._retire_game(game_id, "abandoned")
                return
        self._audit.emit(
            AuditKind.PROTOCOL_RECOVERED,
            {
                "area": "auto_match",
                "reason": "game_reopen_scheduled",
                "game_id": game_id,
                "retry_delay_seconds": delay,
            },
            game_id=game_id,
        )
        self._schedule_reopen(game_id, delay)

    def _schedule_reopen(self, game_id: str, delay: float) -> None:
        """计划一次场次补开：sleep 到期唤醒主循环，由对账重新 open_game。"""

        async def _reopen_later() -> None:
            await self._sleep(delay)
            if not self._shutting_down and self._terminal is None:
                self._wake.set()

        task = asyncio.ensure_future(_reopen_later())
        self._reopen_tasks[game_id] = task
        task.add_done_callback(lambda _t, _gid=game_id: self._reopen_tasks.pop(_gid, None))

    def _check_drain_done(self) -> None:
        """收尾判定：全部终局已记录，或宽限耗尽 → 汇总缺失并终态化。

        必须同时在管场次为空才判定完成：仍有任务在跑的场次还在等待其
        终局记录（房间 finished 后 /state 仍返回终局，任务自行完成）。
        """

        if self._terminal is not None or self._last_snapshot is None:
            return
        snapshot = self._last_snapshot
        deadline_passed = (
            self._drain_deadline_at is not None and self._clock.now() >= self._drain_deadline_at
        )
        pending = self._pending_finals(snapshot)
        if deadline_passed:
            # 宽限耗尽：不再等待在管场次，直接关闭并记录缺失。
            for game_id in list(self._games):
                self._schedule_close(game_id, "drain_deadline")
        if not (deadline_passed or (not pending and not self._games and not self._closing)):
            return
        missing = [g for g in snapshot.my_games if self._retired.get(g) != "finished"]
        if missing and not self._drain_missing_reported:
            self._drain_missing_reported = True
            self._audit.emit(
                AuditKind.PROTOCOL_RECOVERED,
                {
                    "area": "auto_match",
                    "reason": "drain_missing_finals",
                    "missing_games": missing,
                    "deadline_passed": deadline_passed,
                },
            )
        if self._terminal is None:
            reason = _TERMINAL_STATUS_REASON.get(snapshot.status)
            if reason is None:
                reason = ParticipantTerminalReason.FATAL_PROTOCOL_ERROR
            suffix = ""
            if missing:
                suffix = "；{} 场缺少终局记录（结果缺失/未知）：{}".format(
                    len(missing), ",".join(missing)
                )
            self._set_terminal(reason, "自动房{}".format(snapshot.status.value) + suffix)

    def _schedule_close(self, game_id: str, reason: str) -> None:
        """关闭一场在管场次：取消任务并异步收会话（不阻塞主循环）。"""

        slot = self._games.pop(game_id, None)
        if slot is None:
            return
        if game_id in self._closing:
            return
        self._closing.add(game_id)
        slot.task.cancel()
        self._audit.emit(
            AuditKind.LIFECYCLE_CHANGED,
            {
                "area": "auto_match",
                "event": "game_closed",
                "game_id": game_id,
                "reason": reason,
            },
            game_id=game_id,
        )

        async def _close() -> None:
            try:
                await asyncio.wait_for(
                    asyncio.gather(slot.task, return_exceptions=True),
                    timeout=self._supervision.audit_flush_seconds,
                )
            except Exception:  # noqa: BLE001 - 关闭失败只影响该场收尾
                pass
            try:
                await slot.session.aclose("auto_match:" + reason)
            except Exception:  # noqa: BLE001
                pass
            self._closing.discard(game_id)
            self._wake.set()

        self._cleanup_tasks.add(asyncio.ensure_future(_close()))

    async def _shutdown(self) -> None:
        """取消全部任务并关闭场次会话；取消路径的关闭不发 game_closed 审计。"""

        self._shutting_down = True
        for task in (self._update_task, self._wake_task, self._drain_timer):
            if task is not None and not task.done():
                task.cancel()
        self._update_task = None
        self._wake_task = None
        self._drain_timer = None
        for task in list(self._reopen_tasks.values()):
            if not task.done():
                task.cancel()
        self._reopen_tasks.clear()
        slots = list(self._games.values())
        self._games.clear()
        for slot in slots:
            if not slot.task.done():
                slot.task.cancel()
        pending = [slot.task for slot in slots]
        pending += [t for t in self._cleanup_tasks if not t.done()]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        for slot in slots:
            try:
                await slot.session.aclose("auto_match_shutdown")
            except Exception:  # noqa: BLE001 - 关闭失败不影响终态返回
                pass

    # ---------- 校验与清理 ----------

    def _validate_bootstrap(self, bootstrap: SessionBootstrap) -> Optional[ParticipantTerminal]:
        """版本与目标核对；自动房目标允许为空，成功后的身份必须是已核实事实。"""

        if not bootstrap.tournament_id:
            return ParticipantTerminal(
                reason=ParticipantTerminalReason.FATAL_PROTOCOL_ERROR,
                last_snapshot=bootstrap.initial_snapshot,
                detail="初始化返回空 room_id（契约要求已核实非空身份）",
            )
        if (
            self._target.expected_tournament_id
            and bootstrap.tournament_id != self._target.expected_tournament_id
        ):
            return ParticipantTerminal(
                reason=ParticipantTerminalReason.TARGET_MISMATCH,
                last_snapshot=bootstrap.initial_snapshot,
                detail="目标自动房不匹配: 期望 {} 实际 {}".format(
                    self._target.expected_tournament_id, bootstrap.tournament_id
                ),
            )
        guide = bootstrap.guide
        if guide.version < self._target.known_guide_version or guide.has_unknown_breaking_change:
            return ParticipantTerminal(
                reason=ParticipantTerminalReason.INCOMPATIBLE_GUIDE,
                last_snapshot=bootstrap.initial_snapshot,
                detail="指南版本不兼容: version={} known={} breaking={}".format(
                    guide.version,
                    self._target.known_guide_version,
                    guide.has_unknown_breaking_change,
                ),
            )
        return None

    def _early_trail(self) -> AuditTrail:
        """初始化早退路径的最小审计链：身份未知时用占位标识。"""

        trail = AuditTrail(
            self._audit_sink,
            run_id=self._run_id,
            # 发现模式空目标：身份发现前占位 "unknown"（信封完整性要求非空）。
            tournament_id=self._target.expected_tournament_id or "unknown",
            participant_id="unknown",
            clock=self._clock,
        )
        self._audit_trail = trail
        return trail

    def _emit_early_manifest(self, trail: AuditTrail, *, early_exit: bool) -> None:
        """初始化早退/取消的 RUN_MANIFEST（无 guide 事实的出口）。"""

        trail.emit(
            AuditKind.RUN_MANIFEST,
            {
                **_audit_plus_manifest_fields(
                    self._settings.source_namespace, None
                ),
                "run_id": self._run_id,
                "mode": self._target.mode.value,
                "expected_tournament_id": self._target.expected_tournament_id,
                "known_guide_version": self._target.known_guide_version,
                "early_exit": early_exit,
            },
        )

    async def _close_session_quietly(self) -> None:
        try:
            await self._session.aclose()
        except Exception:  # noqa: BLE001 - 关闭失败不影响终态返回
            pass
