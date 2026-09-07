"""单场赛事任务：消费权威条目并驱动决策循环。

监督语义（application 模块规范）：
- 任务异常只影响该场，绝不上抛取消其他场次；
- 可恢复故障交回监督层“权威重新发现”（关闭旧会话、按 active_games
  重开新会话），不在本任务内无上限重启；
- GameFinished / GameFailed 是会话给出的分类结果，异常值之外的
  原生异常按有界退避重试后转可恢复故障。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Callable

from hangma_bot.application.audit import AuditTrail, audit_error_text, audit_text
from hangma_bot.application.contracts import (
    AuditKind,
    GameFailed,
    GameFinished,
    GameSessionPort,
    ObservedActionWindow,
    ParticipantTerminal,
)
from hangma_bot.application.deadline import BoundedBackoff
from hangma_bot.application.decision_loop import FatalIdentityError, RuntimeServices, run_action_window
from hangma_bot.kernel.observation import CompetitionContext


class GameTaskStatus(str, Enum):
    """单场任务结束的可分类状态；监督层据此决定重开、放弃或终止身份。"""

    FINISHED = "finished"  # 官方权威终局
    RECOVERABLE_FAILURE = "recoverable_failure"  # 交回监督层重新发现该场
    UNRECOVERABLE_FAILURE = "unrecoverable_failure"  # 放弃该场，不影响其他场
    FATAL = "fatal"  # 当前身份永久故障（含 SubmitFatal）


@dataclass(frozen=True)
class GameTaskResult:
    """单场任务的结束报告；terminal 仅在 FATAL 时非空。"""

    game_id: str
    status: GameTaskStatus
    detail: str = ""
    terminal: ParticipantTerminal | None = None


class GameTask:
    """一个 game_id 对应的可取消任务；由监督层创建和回收。"""

    def __init__(
        self,
        *,
        game_id: str,
        session: GameSessionPort,
        services: RuntimeServices,
        competition_provider: Callable[[], CompetitionContext],
        stage_attempt_provider: Callable[[], str | None],
        item_backoff: BoundedBackoff,
        sleep: Callable[[float], object],
    ) -> None:
        self._game_id = game_id
        self._session = session
        self._services = services
        self._competition_provider = competition_provider
        self._stage_attempt_provider = stage_attempt_provider
        self._item_backoff = item_backoff
        self._sleep = sleep

    async def run(self, *, read_only: bool = False) -> GameTaskResult:
        """消费权威条目；收尾模式只同步终局，不分析窗口、不调用策略或提交。

        read_only 只能在原动作消费者取消并完成回收后启动。总体收尾截止
        由监督器管理；此处沿用每场有限退避处理短暂读取故障。
        """

        audit = self._services.audit
        while True:
            try:
                item = await self._session.next_item()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - 会话层原生异常按可恢复处理
                delay = self._item_backoff.next_delay_or_none()
                if delay is None:
                    audit.emit(
                        AuditKind.PROTOCOL_RECOVERED,
                        {
                            "area": "game_session",
                            "reason": "next_item 连续失败: {}".format(audit_error_text(exc)),
                            "outcome": "rediscover",
                        },
                        game_id=self._game_id,
                        stage_attempt_id=self._stage_attempt_provider(),
                    )
                    # 会话本身可疑：按可恢复故障交回监督层用全新会话重开，
                    # 重开预算由监督器按 game_id 有界控制（与本类 docstring 一致）。
                    return GameTaskResult(
                        game_id=self._game_id,
                        status=GameTaskStatus.RECOVERABLE_FAILURE,
                        detail="next_item 连续失败",
                    )
                audit.emit(
                    AuditKind.PROTOCOL_RECOVERED,
                    {
                        "area": "game_session",
                        "reason": "next_item 异常: {}".format(audit_error_text(exc)),
                        "retry_delay_seconds": delay,
                    },
                    game_id=self._game_id,
                    stage_attempt_id=self._stage_attempt_provider(),
                )
                await self._sleep(delay)
                continue

            if read_only and isinstance(item, GameFailed) and item.recoverable:
                # 退场后的短暂 GET 故障不能触发重新参赛；在原收尾预算内重读。
                delay = self._item_backoff.next_delay_or_none()
                if delay is not None:
                    await self._sleep(delay)
                    continue
            # 成功取得权威条目即重置退避预算。
            self._item_backoff.reset()

            if isinstance(item, ObservedActionWindow):
                if read_only:
                    # 两个端点到达次序不同，退场后仍可能读到旧动作窗口。
                    # 让出事件循环，使截止/取消在连续缓存条目下也能生效。
                    await asyncio.sleep(0)
                    continue
                try:
                    window_result = await run_action_window(
                        session=self._session,
                        window=item,
                        services=self._services,
                        competition=self._competition_provider(),
                        stage_attempt_id=self._stage_attempt_provider(),
                    )
                except FatalIdentityError as error:
                    return GameTaskResult(
                        game_id=self._game_id,
                        status=GameTaskStatus.FATAL,
                        detail=error.terminal.detail,
                        terminal=error.terminal,
                    )
                if window_result.outcome_kind not in ("accepted",):
                    # 窗口未成功接受的结束（拒绝关闭/模糊/未发送/截止/耗尽）
                    # 已在决策循环内审计；此处补充窗口级摘要供监督与对账。
                    audit.emit(
                        AuditKind.PROTOCOL_RECOVERED,
                        {
                            "area": "decision_window",
                            "reason": "窗口结束: {}".format(window_result.outcome_kind),
                            "sent_attempts": window_result.sent_attempts,
                            "window": {
                                "game_id": window_result.window_key.game_id,
                                "round_no": window_result.window_key.round_no,
                                "trigger_seq": window_result.window_key.trigger_seq,
                                "phase": window_result.window_key.phase.value,
                                "seat": window_result.window_key.seat,
                            },
                        },
                        game_id=self._game_id,
                        stage_attempt_id=self._stage_attempt_provider(),
                        decision_id=window_result.decision_id,
                    )
                # 继续等待下一条目。
                continue
            if isinstance(item, GameFinished):
                audit.emit(
                    AuditKind.GAME_FINISHED,
                    {
                        "final_scores": list(item.final_scores),  # 固定按座位 0—3
                        "authoritative_seq": item.authoritative_seq,
                    },
                    game_id=item.game_id,
                    stage_attempt_id=self._stage_attempt_provider(),
                )
                return GameTaskResult(game_id=item.game_id, status=GameTaskStatus.FINISHED)
            if isinstance(item, GameFailed):
                # reason 来自适配器字符串，入审计前统一截断脱敏。
                safe_reason = audit_text(item.reason)
                audit.emit(
                    AuditKind.PROTOCOL_RECOVERED,
                    {
                        "area": "game_session",
                        "reason": safe_reason,
                        "recoverable": item.recoverable,
                        "outcome": "close_without_result" if read_only else (
                            "rediscover" if item.recoverable else "abandon"
                        ),
                    },
                    game_id=item.game_id,
                    stage_attempt_id=self._stage_attempt_provider(),
                )
                if item.recoverable:
                    return GameTaskResult(
                        game_id=item.game_id,
                        status=GameTaskStatus.RECOVERABLE_FAILURE,
                        detail=safe_reason,
                    )
                return GameTaskResult(
                    game_id=item.game_id,
                    status=GameTaskStatus.UNRECOVERABLE_FAILURE,
                    detail=safe_reason,
                )
            # 未知条目类型属于协议演进；按可恢复故障交回监督层重新发现。
            audit.emit(
                AuditKind.PROTOCOL_RECOVERED,
                {
                    "area": "game_session",
                    "reason": "未知 GameItem 类型: {}".format(type(item).__name__),
                    "outcome": "rediscover",
                },
                game_id=self._game_id,
                stage_attempt_id=self._stage_attempt_provider(),
            )
            return GameTaskResult(
                game_id=self._game_id,
                status=GameTaskStatus.RECOVERABLE_FAILURE,
                detail="未知条目类型",
            )
