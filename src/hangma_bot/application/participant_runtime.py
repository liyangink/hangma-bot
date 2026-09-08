"""ParticipantRuntime：一个 Token 对应身份的完整赛事运行时。

职责边界（application 模块规范）：
- 初始化核对版本、身份、目标赛事和规则配置；初始化本身不报名或到位；
- 委托 TournamentSupervisor 完成跨阶段监督；
- 结束时取消全部任务、关闭赛事会话并尽力刷新审计。
"""

from __future__ import annotations

import asyncio
import platform
from typing import Callable, Mapping, Optional

from hangma_bot.application.audit import AuditTrail, audit_error_text, audit_text
from hangma_bot.application.audit_codec import (
    AUDIT_PRODUCER_APPLICATION,
    CAPTURE_PROFILE_AUDIT_PLUS_V1,
)
from hangma_bot.application.contracts import (
    AuditKind,
    AuditSink,
    AuditSummary,
    ParticipantTerminal,
    ParticipantTerminalReason,
    RuntimeTarget,
    SessionBootstrap,
    TournamentSessionPort,
)
from hangma_bot.application.deadline import BudgetPolicy, RuntimeClock, SystemClock
from hangma_bot.application.decision_loop import RuntimeServices
from hangma_bot.application.ids import IdGenerator, PrefixedUuidIds
from hangma_bot.application.tournament_supervisor import (
    SupervisionPolicy,
    TournamentSupervisor,
)
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import ValueAnalysisLimits
from hangma_bot.policy.interface import BotPolicy

DEFAULT_SLEEP = asyncio.sleep


def _audit_plus_manifest_fields(
    source_namespace: Optional[str],
    manifest_extra: Optional[Mapping[str, object]],
) -> dict:
    """RUN_MANIFEST 的 audit-plus-v1 增强字段（方案 §3.2）。

    初始化阶段未知的事实（源码提交/哈希、策略版本与完整权重等）可空：
    由组合根经 manifest_extra 注入，缺省为 null。保留键不允许覆盖。
    """

    fields: dict[str, object] = {
        "capture_profile": CAPTURE_PROFILE_AUDIT_PLUS_V1,
        "audit_producer": AUDIT_PRODUCER_APPLICATION,
        "source_namespace": source_namespace,
        "python_version": platform.python_version(),
        "git_commit": None,
        "git_dirty": None,
        "source_file_hashes": None,
        "policy_version": None,
        "policy_weights": None,
        "redaction_configured": True,
    }
    # 保留键分两类：身份/安全键（capture_profile、audit_producer、
    # source_namespace、python_version、redaction_configured）禁止覆盖；
    # 版本事实键（git_commit、git_dirty、source_file_hashes、policy_version、
    # policy_weights）默认 null、允许组合根注入——否则这些字段永远无法
    # 记录真实版本事实（主审集成修正 2026-09-06）。
    injectable = {
        "git_commit",
        "git_dirty",
        "source_file_hashes",
        "policy_version",
        "policy_weights",
    }
    if manifest_extra:
        for key, value in manifest_extra.items():
            if key in fields and key not in injectable:
                raise ValueError("manifest_extra 不得覆盖保留键: " + str(key))
            fields[key] = value
    return fields


class ParticipantRuntime:
    """恰好对应一个 Token 的运行时；测试房间用四个隔离进程各启动一个。"""

    def __init__(
        self,
        *,
        session: TournamentSessionPort,
        policy: BotPolicy,
        audit_sink: AuditSink,
        target: RuntimeTarget,
        rules_factory: Callable = HangmaRules,
        clock: Optional[RuntimeClock] = None,
        ids: Optional[IdGenerator] = None,
        budget_policy: Optional[BudgetPolicy] = None,
        supervision: Optional[SupervisionPolicy] = None,
        sleep=DEFAULT_SLEEP,
        source_namespace: Optional[str] = None,
        manifest_extra: Optional[Mapping[str, object]] = None,
        value_limits: Optional[ValueAnalysisLimits] = None,
    ) -> None:
        self._session = session
        self._policy = policy
        self._audit_sink = audit_sink
        self._target = target
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
        # audit-plus-v1 manifest 增强来源（方案 §3.2）：source_namespace 是
        # 部署配置中的逻辑平台实例名；manifest_extra 由组合根注入源码提交、
        # 策略版本等初始化期事实，缺省可空。
        self._source_namespace = source_namespace
        self._manifest_extra = manifest_extra
        # 组合根按候选策略显式启用，普通参赛身份不承担这部分规则工作量。
        if value_limits is not None and not isinstance(value_limits, ValueAnalysisLimits):
            raise TypeError("value_limits 必须是 ValueAnalysisLimits 或 None")
        self._value_limits = value_limits

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
        """运行到当前身份的参赛者终态；支持异步取消。

        所有出口（正常终态、初始化失败、目标校验拒绝、监督异常、外部取消）
        都经过统一 finally：关闭赛事会话并对审计记录器做限时冲刷；
        早退路径同样写入 PARTICIPANT_FINISHED，保证每次运行可审计。
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
                trail.emit(
                    AuditKind.RUN_MANIFEST,
                    {
                        **_audit_plus_manifest_fields(self._source_namespace, self._manifest_extra),
                        "run_id": self._run_id,
                        "mode": self._target.mode.value,
                        "expected_tournament_id": self._target.expected_tournament_id,
                        "known_guide_version": self._target.known_guide_version,
                        "early_exit": True,
                    },
                )
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
                trail.emit(
                    AuditKind.RUN_MANIFEST,
                    {
                        **_audit_plus_manifest_fields(self._source_namespace, self._manifest_extra),
                        "run_id": self._run_id,
                        "mode": self._target.mode.value,
                        "expected_tournament_id": self._target.expected_tournament_id,
                        "known_guide_version": self._target.known_guide_version,
                        "early_exit": True,
                    },
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
                trail.emit(
                    AuditKind.RUN_MANIFEST,
                    {
                        **_audit_plus_manifest_fields(self._source_namespace, self._manifest_extra),
                        "run_id": self._run_id,
                        "mode": self._target.mode.value,
                        "expected_tournament_id": self._target.expected_tournament_id,
                        "known_guide_version": self._target.known_guide_version,
                        "early_exit": True,
                    },
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
                        **_audit_plus_manifest_fields(self._source_namespace, self._manifest_extra),
                        "run_id": self._run_id,
                        "mode": self._target.mode.value,
                        "expected_tournament_id": self._target.expected_tournament_id,
                        "known_guide_version": self._target.known_guide_version,
                        "guide_version": bootstrap.guide.version,
                        "early_exit": True,
                    },
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
                    **_audit_plus_manifest_fields(self._source_namespace, self._manifest_extra),
                    "run_id": self._run_id,
                    "mode": self._target.mode.value,
                    "expected_tournament_id": self._target.expected_tournament_id,
                    "known_guide_version": self._target.known_guide_version,
                    "guide_version": bootstrap.guide.version,
                    "guide_updated_at": bootstrap.guide.updated_at,
                    "participant_id": bootstrap.participant_id,
                    "ruleset_version": bootstrap.config.rules.ruleset_version,
                    "base_score": bootstrap.config.rules.base_score,
                    "you_cai_bi_kao": bootstrap.config.rules.you_cai_bi_kao,
                    "value_analysis_limits": (
                        None if self._value_limits is None else {
                            "max_expansions": self._value_limits.max_expansions,
                            "max_routes_per_candidate": self._value_limits.max_routes_per_candidate,
                        }
                    ),
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
                value_limits=self._value_limits,
            )
            supervisor = TournamentSupervisor(
                bootstrap=bootstrap,
                session=self._session,
                services=services,
                supervision=self._supervision,
                sleep=self._sleep,
                mode=self._target.mode,
            )
            terminal = await supervisor.run()
            trail.emit(
                AuditKind.PARTICIPANT_FINISHED,
                {
                    "reason": terminal.reason.value,
                    "detail": audit_text(terminal.detail),
                },
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
                        "area": "supervisor",
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
                # 硬截止放弃的策略任务：关闭时限期等待其收尾，超时再取消；
                # 已完成的任务由回调即时出表，防止运行期间注册表线性增长。
                pending_abandoned = {
                    task
                    for task in self._abandoned_policy_tasks
                    if not task.done()
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
                    # 经由 trail 关闭：关闭异常会被标记为审计降级而不是吞掉。
                    self._last_audit_summary = await trail.aclose(
                        self._supervision.audit_flush_seconds
                    )
                else:
                    await self._audit_sink.aclose(self._supervision.audit_flush_seconds)
            except Exception:  # noqa: BLE001 - 冲刷失败不掩盖运行结果
                self._last_audit_summary = None

    def _early_trail(self) -> AuditTrail:
        """初始化早退路径的最小审计链：身份未知时用占位标识。"""

        trail = AuditTrail(
            self._audit_sink,
            run_id=self._run_id,
            tournament_id=self._target.expected_tournament_id,
            participant_id="unknown",
            clock=self._clock,
        )
        self._audit_trail = trail
        return trail

    def _validate_bootstrap(self, bootstrap: SessionBootstrap) -> Optional[ParticipantTerminal]:
        """版本、身份与目标核对；任何错配都是永久性参赛者终态。"""

        if bootstrap.tournament_id != self._target.expected_tournament_id:
            return ParticipantTerminal(
                reason=ParticipantTerminalReason.TARGET_MISMATCH,
                last_snapshot=bootstrap.initial_snapshot,
                detail="目标赛事不匹配: 期望 {} 实际 {}".format(
                    self._target.expected_tournament_id, bootstrap.tournament_id
                ),
            )
        guide = bootstrap.guide
        if (
            guide.version < self._target.known_guide_version
            or guide.has_unknown_breaking_change
        ):
            # 低于已适配版本同样视为不兼容：无法保证规则与时限语义正确。
            return ParticipantTerminal(
                reason=ParticipantTerminalReason.INCOMPATIBLE_GUIDE,
                last_snapshot=bootstrap.initial_snapshot,
                detail="指南版本不兼容: version={} known={} breaking={}".format(
                    guide.version, self._target.known_guide_version,
                    guide.has_unknown_breaking_change,
                ),
            )
        return None

    async def _close_session_quietly(self) -> None:
        try:
            await self._session.aclose()
        except Exception:  # noqa: BLE001 - 关闭失败不影响终态返回
            pass
