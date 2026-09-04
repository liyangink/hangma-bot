"""官方场次会话：GameSessionPort 的官方协议实现（v8 快照 + v9–v11 已审查变更）。

同步与提交语义（接口协议 §5/§8、模块 AGENTS）：

- 权威观察永远来自全量快照；增量事件只归并进公开历史并触发快照刷新。
  这与官方 demo 一致：私有字段（my_hand/drawn_tile）只在快照中出现。
- 重复 seq 幂等忽略；缺口、gap=true、未知关键事件用 seq=0 整体重建。
- GET 超时/可恢复 5xx/429 在预算内有界重试；动作 POST 绝不自动重放。
- 409 固定流程：记录明确拒绝 → seq=0 全量刷新 → 比较 WindowKey →
  同窗仍需行动返回 SubmitRejectedRetryable，否则 SubmitRejectedClosed。
- POST 429 与 409 后刷新失败/不可用 → SubmitRejectedNoRefresh：POST 已发出、
  官方明确未执行、无权威刷新，终结原窗口且不允许追加提交（接口协议 §5）。
- POST 结果不确定（超时/断连/5xx）→ SubmitAmbiguous 并封锁同窗。
- 官方可在快照响应附带 gap=true（指南 v10，跨局断链）：快照本身即
  权威全量，直接吸收并记录事实，无需额外重建。
- 同场任意时刻最多一个在途 POST（ActionGate）。
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Callable, Mapping, Optional, Tuple

from hangma_bot.application.contracts import (
    ActionAttempt,
    AuditContext,
    AuditKind,
    AuditRecord,
    AuditSink,
    GameFailed,
    GameFinished,
    GameItem,
    ObservedActionWindow,
    SubmitAccepted,
    SubmitAmbiguous,
    SubmitFatal,
    SubmitNotSent,
    SubmitOutcome,
    SubmitRejectedClosed,
    SubmitRejectedNoRefresh,
    SubmitRejectedRetryable,
)
from hangma_bot.kernel.actions import WindowKey
from hangma_bot.kernel.config import TimingConfig
from hangma_bot.kernel.observation import PlayerObservation

from . import projector
from .action_gate import ActionGate
from .dto import StateResponse, parse_state_response
from .errors import (
    AuthError,
    BadRequestError,
    ConflictError,
    DtoError,
    ForbiddenError,
    NotFoundError,
    OfficialError,
    RateLimitedError,
    RecoverableServerError,
    UncertainTransportError,
)
from .scheduler import DeadlineExceeded, Priority, RequestScheduler
from .sync_state import ProtocolSyncState, SyncDecision
from .transport import OfficialTransport


class OfficialGameSession:
    """一个 game_id 的会话；共享所在 Token 的传输与调度器，独享同步状态与动作门。"""

    def __init__(
        self,
        *,
        game_id: str,
        transport: OfficialTransport,
        scheduler: RequestScheduler,
        timing: TimingConfig,
        monotonic_clock: Callable[[], float],  # 单调时钟秒；deadline 判定与审计时戳
        wall_clock_unix_ms: Callable[[], int],  # 墙上时钟毫秒；仅用于审计信封
        audit: Optional[AuditSink] = None,
        audit_context: Optional[Callable[[], AuditContext]] = None,
        max_get_retries: int = 3,
        retry_backoff_base_sec: float = 0.2,
        retry_sleep: Optional[Callable[[float], Any]] = None,  # 测试注入
    ) -> None:
        self.game_id = game_id
        self._transport = transport
        self._scheduler = scheduler
        self._timing = timing
        self._monotonic = monotonic_clock
        self._wall_ms = wall_clock_unix_ms
        self._audit = audit
        self._audit_context = audit_context
        self._max_retries = max_get_retries
        self._backoff_base = retry_backoff_base_sec
        self._retry_sleep = retry_sleep if retry_sleep is not None else asyncio.sleep
        self._sync = ProtocolSyncState(game_id, timing)
        self._gate = ActionGate()
        self._delivered_windows = set()
        self._final: Optional[GameFinished] = None
        self._closed = False
        self._close_reason = ""
        self._active_tasks = set()
        self._poll_active = False  # next_item 单消费者守卫
        self.audit_degraded_events = 0  # 审计回执降级计数（诊断用）
        self.audit_dropped_events = 0  # 审计发射异常计数（诊断用）

    # ---------- 审计 ----------

    def _emit_audit(self, kind: AuditKind, payload: Mapping[str, Any], **extra: Any) -> None:
        """非阻塞审计；审计失败绝不向动作路径抛异常（接口协议 §7）。"""

        if self._audit is None or self._audit_context is None:
            return
        try:
            context = self._audit_context()
            fields = {**context.__dict__}
            fields["game_id"] = self.game_id
            for key, value in extra.items():
                if value is not None:
                    fields[key] = value
            from dataclasses import replace

            record = AuditRecord(
                schema_version=1,
                kind=kind,
                context=replace(context, **fields),
                wall_time_unix_ms=self._wall_ms(),
                monotonic_ns=int(self._monotonic() * 1e9),
                payload=dict(payload),
            )
            receipt = self._audit.emit(record)
            if receipt is not None and receipt.audit_degraded:
                self.audit_degraded_events += 1
        except Exception:
            # 记录器契约要求不向动作路径抛异常；此为防御双重保障
            self.audit_dropped_events += 1

    # ---------- GameSessionPort ----------

    async def next_item(self) -> GameItem:
        """返回下一动作窗口、终局或分类故障；支持异步取消与 aclose 中断。"""

        if self._final is not None:
            return self._final
        if self._closed:
            return GameFailed(self.game_id, recoverable=False, reason="session_closed:" + self._close_reason)
        if self._poll_active:
            # 契约假定单消费者串行调用；并发调用按分类故障拒绝而非拉起双轮询
            return GameFailed(self.game_id, recoverable=False, reason="next_item_busy")
        self._poll_active = True
        try:
            return await self._poll_once_guarded()
        finally:
            self._poll_active = False

    async def _poll_once_guarded(self) -> GameItem:
        task = asyncio.ensure_future(self._poll_cycle())
        self._active_tasks.add(task)
        task.add_done_callback(self._active_tasks.discard)
        try:
            return await task
        except asyncio.CancelledError:
            # 区分来源：aclose 取消内层轮询时向调用方返回分类故障；
            # 调用方自身的取消则原样传播。uncancel 清除本层误计数。
            if self._closed:
                current = asyncio.current_task()
                if current is not None:
                    current.uncancel()
                return GameFailed(self.game_id, recoverable=False, reason="session_closed:" + self._close_reason)
            raise

    @property
    def closed(self) -> bool:
        """会话是否已关闭；赛事会话用它决定缓存逐出与重建。"""

        return self._closed

    async def aclose(self, reason: str) -> None:
        """取消本场挂起轮询；不触碰同 Token 共享传输与其他场次。"""

        self._closed = True
        self._close_reason = reason
        for task in list(self._active_tasks):
            task.cancel()

    # ---------- 轮询循环 ----------

    async def _poll_cycle(self) -> GameItem:
        """一个完整轮询周期：持续到产出窗口、终局或故障。"""

        rebuild_streak = 0
        while True:
            if self._closed:
                return GameFailed(self.game_id, False, "session_closed:" + self._close_reason)
            if self._final is not None:
                return self._final
            # 本地权威状态已有未终结活窗时先投递再轮询：覆盖 409 刷新发现的
            # 迁移窗口与监督重启场景（官方在等我行动时不会推送新事件，
            # 长轮询只会得到 pending）
            delivered = self._maybe_deliver_window()
            if delivered is not None:
                return delivered
            try:
                response = await self._get_state(long_poll=True)
            except _PollFailure as failure:
                return failure.item
            if response.kind == "pending":
                if response.gap:
                    # pending 响应携带 gap=true：权威序号已断链，必须重建
                    # 而不是继续用旧 seq 长轮询（wv9 阻断项）
                    rebuild_streak += 1
                    self._emit_audit(
                        AuditKind.PROTOCOL_RECOVERED,
                        {"trigger": "pending_gap", "streak": rebuild_streak},
                        trigger_seq=self._sync.last_seq,
                    )
                    if rebuild_streak > 2:
                        return GameFailed(self.game_id, True, "rebuild_loop")
                    try:
                        snapshot_response = await self._get_state(long_poll=False, force_full=True)
                    except _PollFailure as failure:
                        return failure.item
                    if snapshot_response.kind not in ("snapshot", "finished"):
                        return GameFailed(
                            self.game_id, True, "snapshot_expected_got_" + snapshot_response.kind
                        )
                    apply_failure = self._apply_or_fail(snapshot_response, finished=snapshot_response.finished)
                    if apply_failure is not None:
                        return apply_failure
                    if snapshot_response.finished:
                        return self._finish_game()
                    delivered = self._maybe_deliver_window()
                    if delivered is not None:
                        return delivered
                continue
            if response.kind in ("snapshot", "finished"):
                if response.gap:
                    # 指南 v10：官方可在（跨局）快照上附带 gap=true，表示事件流
                    # 曾断链；快照本身即权威全量，直接吸收并记录事实，无需重建
                    self._emit_audit(
                        AuditKind.PROTOCOL_RECOVERED,
                        {
                            "trigger": "rebuild_snapshot_gap",
                            "seq": response.snapshot.seq if response.snapshot else None,
                        },
                        trigger_seq=response.snapshot.seq if response.snapshot else None,
                    )
                apply_failure = self._apply_or_fail(response, finished=response.finished)
                if apply_failure is not None:
                    return apply_failure
                if response.finished:
                    return self._finish_game()
                delivered = self._maybe_deliver_window()
                if delivered is not None:
                    return delivered
                continue
            # 增量事件：归并后立即刷新全量快照（私有信息只在快照中出现）
            result = self._sync.apply_events(response.events, gap=response.gap)
            if result.decision is SyncDecision.NEEDS_REBUILD:
                rebuild_streak += 1
                self._emit_audit(
                    AuditKind.PROTOCOL_RECOVERED,
                    {"trigger": "incremental", "reasons": list(result.reasons), "streak": rebuild_streak},
                    trigger_seq=self._sync.last_seq,
                )
                if rebuild_streak > 2:
                    return GameFailed(self.game_id, True, "rebuild_loop")
                # 未知事件类型先记录，待权威快照成功吸收其效果后才学习忽略；
                # 重建失败时保持"未学习"，重入后仍按未知关键事件保守重建
                unknown_types = [
                    reason.split(":", 1)[1]
                    for reason in result.reasons
                    if reason.startswith("unknown_event:")
                ]
                try:
                    snapshot_response = await self._get_state(long_poll=False, force_full=True)
                except _PollFailure as failure:
                    return failure.item
                if snapshot_response.kind not in ("snapshot", "finished"):
                    # seq=0 按官方语义必须返回全量快照；其他形态属协议异常，
                    # 按可恢复故障上交（应用层重入后自然重试）
                    return GameFailed(
                        self.game_id, True, "snapshot_expected_got_" + snapshot_response.kind
                    )
                apply_failure = self._apply_or_fail(snapshot_response, finished=snapshot_response.finished)
                if apply_failure is not None:
                    return apply_failure
                for event_type in unknown_types:
                    self._sync.note_rebuild_absorbed(event_type)
                if snapshot_response.finished:
                    return self._finish_game()
                delivered = self._maybe_deliver_window()
                if delivered is not None:
                    return delivered
                continue
            rebuild_streak = 0
            try:
                snapshot_response = await self._get_state(long_poll=False, force_full=True)
            except _PollFailure as failure:
                return failure.item
            if snapshot_response.kind not in ("snapshot", "finished"):
                return GameFailed(
                    self.game_id, True, "snapshot_expected_got_" + snapshot_response.kind
                )
            apply_failure = self._apply_or_fail(snapshot_response, finished=snapshot_response.finished)
            if apply_failure is not None:
                return apply_failure
            if snapshot_response.finished:
                return self._finish_game()
            delivered = self._maybe_deliver_window()
            if delivered is not None:
                return delivered

    def _apply_snapshot(self, response: StateResponse, *, finished: bool) -> None:
        if response.snapshot is None:
            raise DtoError("快照响应缺失 snapshot", recoverable=False)
        self._sync.apply_full_snapshot(response.snapshot, finished=finished)
        self._gate.observe_authoritative_window(
            self._sync.current_window().window_key if self._sync.current_window() else None
        )

    def _apply_or_fail(self, response: StateResponse, *, finished: bool) -> Optional[GameFailed]:
        """应用快照；解析/校验失败转分类故障而非裸异常。

        无副作用验证先行：完整投影与窗口判定在提交同步状态之前完成，
        坏快照绝不覆盖已同步状态——否则后续投递路径会在坏数据上裸抛
        （专家裁决：连续 next_item 不得因残留坏快照失败）。验证通过才
        commit 并预热观察缓存。
        """

        if response.snapshot is None:
            return GameFailed(self.game_id, True, "snapshot_apply_failed:快照响应缺失 snapshot")
        snapshot = response.snapshot
        try:
            if not finished:
                # 终局快照（官方 turn=-1）不走 PlayerObservation 投影：
                # GameFinished 只需要积分；非终局快照做完整验证
                projector.observation(snapshot, tuple(self._sync.history), self.game_id)
                projector.detect_window(snapshot, self._timing, self.game_id)
            self._sync.apply_full_snapshot(snapshot, finished=finished)
            if not finished:
                self._sync.current_observation()  # 预热缓存（已验证必成功）
                self._sync.current_window()
        except (DtoError, ValueError) as exc:
            return GameFailed(self.game_id, True, "snapshot_apply_failed:" + str(exc)[:100])
        return None

    def _maybe_deliver_window(self) -> Optional[ObservedActionWindow]:
        """投递当前权威活窗；同一会话内每个 WindowKey 恰好交付一次。

        exactly-once 是有意取舍：重投会刷新 received_at_monotonic，
        应用层据此重建预算，等于变相延长截止时间（审查裁决）。
        监督重启应创建新 GameSession；409 重规划走 refreshed_window。
        循环顶部投递只服务"权威状态已在本地但从未交付"的窗口
        （409 刷新发现的迁移窗口）。
        """

        detected = self._sync.current_window()
        if detected is None:
            return None
        key = detected.window_key
        if key in self._delivered_windows:
            return None
        if self._gate.is_finalized(key):
            return None  # 防御双保险：已终结窗口绝不投递
        observation = self._sync.current_observation()
        if observation is None:
            return None
        window = ObservedActionWindow(
            observation=observation,
            window_key=key,
            authoritative_seq=key.trigger_seq,
            received_at_monotonic=self._monotonic(),
            timeout_seconds=detected.timeout_seconds,
        )
        self._delivered_windows.add(key)
        self._emit_audit(
            AuditKind.AUTHORITATIVE_STATE,
            {
                "seq": window.authoritative_seq,
                "phase": observation.phase,
                "turn": observation.turn_seat,
                "window": {"game_id": detected.window_key.game_id, "round_no": detected.window_key.round_no, "trigger_seq": detected.window_key.trigger_seq, "phase": detected.window_key.phase.value, "seat": detected.window_key.seat},
            },
            trigger_seq=detected.window_key.trigger_seq,
            round_no=detected.window_key.round_no,
        )
        return window

    def _finish_game(self) -> GameFinished:
        scores = self._sync.final_scores() or (0, 0, 0, 0)
        final = GameFinished(
            game_id=self.game_id,
            final_scores=tuple(scores),
            authoritative_seq=self._sync.last_seq,
        )
        self._final = final
        self._emit_audit(
            AuditKind.GAME_FINISHED,
            {"final_scores": list(final.final_scores), "seq": final.authoritative_seq},
        )
        return final

    async def _get_state(
        self,
        *,
        long_poll: bool,
        force_full: bool = False,
        deadline_monotonic: Optional[float] = None,
    ) -> StateResponse:
        """带预算内有界重试的 state 请求；失败升级为 _PollFailure。

        可恢复解析错误（DtoError.recoverable=True，如增量事件负载损坏）在
        重试耗尽前降级一次 seq=0 全量重建——增量损坏大概率可由权威快照修复。
        deadline_monotonic 绑定动作原始预算（409 恢复刷新使用）：预算耗尽
        立即停止重试并按可恢复失败上交，绝不越过 latest_send_at 等待。
        """

        seq = 0 if force_full else self._sync.last_seq
        priority = Priority.RECOVERY if force_full else Priority.POLL
        attempts = 0
        degraded_to_full = False
        while True:
            attempts += 1
            if deadline_monotonic is not None and self._monotonic() >= deadline_monotonic:
                raise _PollFailure(GameFailed(self.game_id, True, "refresh_deadline")) from None
            try:
                lease = await self._scheduler.acquire(
                    priority, deadline_monotonic=deadline_monotonic
                )
            except DeadlineExceeded:
                # 冷却/槽竞争在预算内未让出许可：按预算耗尽上交，
                # 409 路径由调用方保守映射 SubmitRejectedNoRefresh
                raise _PollFailure(GameFailed(self.game_id, True, "refresh_deadline")) from None
            # acquire 等待（429 冷却/槽竞争）会消耗预算：拿到 lease 后必须
            # 复查截止并按最新剩余设置读取超时——不得用过期的估算值发请求
            read_timeout: Optional[float] = None
            if deadline_monotonic is not None:
                remaining = deadline_monotonic - self._monotonic()
                if remaining <= 0:
                    lease.release()
                    raise _PollFailure(GameFailed(self.game_id, True, "refresh_deadline")) from None
                read_timeout = remaining
            try:
                result = await self._transport.request(
                    "GET",
                    "/api/games/{}/state".format(self.game_id),
                    params={"seq": seq},
                    long_poll=long_poll,
                    request_budget_sec=read_timeout,
                )
                return parse_state_response(_loads(result.text))
            except RateLimitedError as exc:
                self._scheduler.note_rate_limited(exc.retry_after_seconds)
            except (UncertainTransportError, RecoverableServerError):
                pass
            except AuthError:
                raise _PollFailure(GameFailed(self.game_id, False, "authentication_failed")) from None
            except ForbiddenError:
                raise _PollFailure(GameFailed(self.game_id, False, "forbidden")) from None
            except NotFoundError:
                raise _PollFailure(GameFailed(self.game_id, True, "game_not_found")) from None
            except BadRequestError:
                raise _PollFailure(GameFailed(self.game_id, False, "bad_request")) from None
            except ConflictError:
                # state GET 不在官方 409 语义内；按不可恢复协议错误终止本场
                raise _PollFailure(GameFailed(self.game_id, False, "state_conflict")) from None
            except OfficialError as exc:
                raise _PollFailure(
                    GameFailed(self.game_id, False, "protocol_error_" + str(exc.http_status))
                ) from None
            except DtoError as exc:
                if not exc.recoverable:
                    raise _PollFailure(GameFailed(self.game_id, False, "fatal_protocol:" + str(exc)[:120])) from None
                if seq != 0 and not degraded_to_full:
                    # 增量负载损坏：降级为 seq=0 权威重建（只降一次）
                    degraded_to_full = True
                    seq = 0
                    continue
                if attempts > self._max_retries:
                    raise _PollFailure(GameFailed(self.game_id, True, "dto_invalid")) from None
            finally:
                lease.release()  # 幂等：deadline 分支已手动释放时为 no-op
            if attempts > self._max_retries:
                raise _PollFailure(GameFailed(self.game_id, True, "get_exhausted")) from None
            await self._retry_sleep(self._backoff_base * (2 ** (attempts - 1)))

    # ---------- 动作提交 ----------

    async def submit(self, attempt: ActionAttempt) -> SubmitOutcome:
        """串行动作提交：门控 → 截止检查 → intent 审计 → POST → 封闭结果。"""

        if self._closed:
            return self._finish_submit(attempt, SubmitNotSent("session_closed"))
        allowed, reason = self._gate.try_enter(attempt.window_key)
        if not allowed:
            return self._finish_submit(attempt, SubmitNotSent(reason))
        self._gate.enter()
        try:
            return await self._submit_locked(attempt)
        finally:
            self._gate.leave()

    async def _submit_locked(self, attempt: ActionAttempt) -> SubmitOutcome:
        detected = self._sync.current_window()
        observation = self._sync.current_observation()
        if detected is None or observation is None or detected.window_key != attempt.window_key:
            return self._finish_submit(attempt, SubmitNotSent("stale_window"))
        body = projector.action_request_body(
            attempt.action,
            last_discard_tile=observation.last_discard.tile if observation.last_discard else None,
            hand=observation.my_hand,
            drawn_tile=observation.drawn_tile,
            catch_play=observation.rule_state.catch_play,
            phase=attempt.window_key.phase,
            responding=attempt.window_key.seat in observation.responding_seats,
        )
        if body is None:
            return self._finish_submit(attempt, SubmitNotSent("malformed_action_body"))
        if self._monotonic() >= attempt.latest_send_at_monotonic:
            return self._finish_submit(attempt, SubmitNotSent("deadline_passed"))
        self._emit_audit(
            AuditKind.SUBMISSION_INTENT,
            {
                "decision_id": attempt.decision_id,
                "attempt_no": attempt.attempt_no,
                "plan_revision": attempt.plan_revision,
                "action_key": attempt.action_key,
                "based_on_authoritative_seq": attempt.based_on_authoritative_seq,
                "window": {"game_id": attempt.window_key.game_id, "round_no": attempt.window_key.round_no, "trigger_seq": attempt.window_key.trigger_seq, "phase": attempt.window_key.phase.value, "seat": attempt.window_key.seat},
                "body": dict(body),
            },
            decision_id=attempt.decision_id,
            attempt_no=attempt.attempt_no,
            trigger_seq=attempt.window_key.trigger_seq,
            round_no=attempt.window_key.round_no,
        )
        try:
            lease = await self._scheduler.acquire(
                Priority.ACTION, deadline_monotonic=attempt.latest_send_at_monotonic
            )
        except DeadlineExceeded:
            # 全局冷却/槽竞争未在预算内让出许可：POST 从未发出，
            # 按未发送处理，保证 GameTask 不在冷却上阻塞到预算外
            return self._finish_submit(attempt, SubmitNotSent("deadline_passed_in_schedule"))
        try:
            if self._monotonic() >= attempt.latest_send_at_monotonic:
                # 调度等待可能耗时；越过截止时间一律不再发出 POST
                return self._finish_submit(attempt, SubmitNotSent("deadline_passed_after_schedule"))
            try:
                await self._transport.request(
                    "POST",
                    "/api/games/{}/action".format(self.game_id),
                    json_body=body,
                )
            except ConflictError as exc:
                # 409 已确认动作未执行：先释放动作槽再刷新，避免在持有
                # ACTION lease 时嵌套等待 RECOVERY 槽造成调度自锁
                lease.release()
                outcome = await self._handle_conflict(attempt, exc)
                return self._finish_submit(attempt, outcome)
            except AuthError as exc:
                return self._finish_submit(
                    attempt,
                    SubmitFatal(exc.official_code, "authentication_failed"),
                )
            except ForbiddenError as exc:
                return self._finish_submit(attempt, SubmitFatal(exc.official_code, "forbidden"))
            except RateLimitedError as exc:
                self._scheduler.note_rate_limited(exc.retry_after_seconds)
                # 429：POST 已发出且官方明确未执行，但限速响应不含权威刷新。
                # 按契约类型 SubmitRejectedNoRefresh 终结原窗口（不追加提交），
                # 审计按实际发送计数（2026-09-04 集成阶段裁定，接口协议 §5）。
                self._gate.mark_closed(attempt.window_key)
                return self._finish_submit(
                    attempt,
                    SubmitRejectedNoRefresh(
                        official_code=exc.official_code or "RATE_LIMITED",
                        rejected_action_key=attempt.action_key,
                        latest_local_seq=self._sync.last_seq,
                        reason="official_rate_limited",
                    ),
                )
            except UncertainTransportError as exc:
                return self._finish_submit(attempt, self._block_ambiguous(attempt, exc.detail))
            except RecoverableServerError as exc:
                return self._finish_submit(attempt, self._block_ambiguous(attempt, "server_error_" + str(exc.http_status)))
            except BadRequestError as exc:
                # 400（如 TOKEN_NOT_SCOPED）：请求/作用域配置错误，重试无意义
                return self._finish_submit(attempt, SubmitFatal(exc.official_code, "bad_request"))
            except NotFoundError as exc:
                # 404：官方明确未执行动作且窗口必然失效；身份未坏，
                # 后续 next_item 的可恢复 game_not_found 会触发重新发现。
                # 门同步终结：窗口关闭后同窗不再接受任何提交
                self._gate.mark_closed(attempt.window_key)
                return self._finish_submit(
                    attempt,
                    SubmitRejectedClosed(
                        official_code=exc.official_code or "GAME_NOT_FOUND",
                        latest_authoritative_seq=self._sync.last_seq,
                    ),
                )
            except OfficialError as exc:
                # 未分类官方状态：保守终止当前身份的提交通道，不误当网络故障重试
                return self._finish_submit(
                    attempt,
                    SubmitFatal(exc.official_code, "protocol_error_" + str(exc.http_status)),
                )
            except asyncio.CancelledError:
                # POST 可能已发出且结果未知：按模糊语义封锁同窗，杜绝非幂等双发；
                # 取消本身继续向外传播（不吞调用方的取消请求）
                self._gate.block(attempt.window_key)
                self._emit_audit(
                    AuditKind.SUBMISSION_OUTCOME,
                    {
                        "decision_id": attempt.decision_id,
                        "attempt_no": attempt.attempt_no,
                        "action_key": attempt.action_key,
                        "outcome_type": "SubmitAmbiguous",
                        "reason": "submit_cancelled_in_flight",
                    },
                    decision_id=attempt.decision_id,
                    attempt_no=attempt.attempt_no,
                    trigger_seq=attempt.window_key.trigger_seq,
                    round_no=attempt.window_key.round_no,
                )
                raise
            self._gate.mark_accepted(attempt.window_key)
            return self._finish_submit(attempt, SubmitAccepted(official_code=None, authoritative_seq=None))
        finally:
            lease.release()

    def _block_ambiguous(self, attempt: ActionAttempt, reason: str) -> SubmitAmbiguous:
        recovery_id = "amb-{}-{}".format(attempt.attempt_no, uuid.uuid4().hex[:8])
        self._gate.block(attempt.window_key)
        return SubmitAmbiguous(recovery_id=recovery_id, reason=reason)

    async def _handle_conflict(self, attempt: ActionAttempt, error: ConflictError) -> SubmitOutcome:
        """409 固定流程：权威刷新后按 WindowKey 判定 retryable/closed；

        刷新失败、不可用或不可解析时返回 SubmitRejectedNoRefresh（接口协议 §5）。
        """

        try:
            response = await self._get_state(
                long_poll=False,
                force_full=True,
                deadline_monotonic=attempt.latest_send_at_monotonic,
            )
        except asyncio.CancelledError:
            # 刷新被取消：409 已确认动作未执行，但窗口状态未知——终结原窗口，
            # 杜绝取消路径绕过封锁后同窗再次提交（专家探针 POST=2）
            self._gate.mark_closed(attempt.window_key)
            self._emit_audit(
                AuditKind.PROTOCOL_RECOVERED,
                {
                    "trigger": "conflict_refresh_cancelled",
                    "official_code": error.official_code,
                    "rejected_action_key": attempt.action_key,
                },
                trigger_seq=attempt.window_key.trigger_seq,
                decision_id=attempt.decision_id,
                attempt_no=attempt.attempt_no,
                round_no=attempt.window_key.round_no,
            )
            raise
        except _PollFailure:
            # 官方已明确未执行动作（409 本身）；但权威刷新失败/不可得，
            # 无法确认窗口是否仍开放：按 SubmitRejectedNoRefresh 终结原窗口，
            # 不把本地保守停窗写成"权威确认关闭"（SubmitRejectedClosed 语义）。
            self._gate.mark_closed(attempt.window_key)
            self._emit_audit(
                AuditKind.PROTOCOL_RECOVERED,
                {
                    "trigger": "conflict_refresh_unavailable",
                    "official_code": error.official_code,
                    "rejected_action_key": attempt.action_key,
                },
                trigger_seq=attempt.window_key.trigger_seq,
                decision_id=attempt.decision_id,
                attempt_no=attempt.attempt_no,
                round_no=attempt.window_key.round_no,
            )
            return SubmitRejectedNoRefresh(
                official_code=error.official_code or "INVALID_ACTION",
                rejected_action_key=attempt.action_key,
                latest_local_seq=self._sync.last_seq,
                reason="conflict_refresh_unavailable",
            )
        apply_failure = self._apply_or_fail(response, finished=response.finished)
        if apply_failure is not None:
            # 刷新响应不可用：与刷新失败同保守路径，绝不在未确认状态上重试
            self._gate.mark_closed(attempt.window_key)
            self._emit_audit(
                AuditKind.PROTOCOL_RECOVERED,
                {
                    "trigger": "rebuild_snapshot_apply_failed",
                    "official_code": error.official_code,
                    "rejected_action_key": attempt.action_key,
                    "reason": apply_failure.reason,
                },
                trigger_seq=attempt.window_key.trigger_seq,
                decision_id=attempt.decision_id,
                attempt_no=attempt.attempt_no,
                round_no=attempt.window_key.round_no,
            )
            return SubmitRejectedNoRefresh(
                official_code=error.official_code or "INVALID_ACTION",
                rejected_action_key=attempt.action_key,
                latest_local_seq=self._sync.last_seq,
                reason="conflict_refresh_invalid_snapshot",
            )
        self._emit_audit(
            AuditKind.PROTOCOL_RECOVERED,
            {"trigger": "conflict_refresh", "official_code": error.official_code, "rejected_action_key": attempt.action_key},
            trigger_seq=attempt.window_key.trigger_seq,
            decision_id=attempt.decision_id,
            attempt_no=attempt.attempt_no,
            round_no=attempt.window_key.round_no,
        )
        detected = self._sync.current_window()
        observation = self._sync.current_observation()
        if (
            detected is not None
            and observation is not None
            and detected.window_key == attempt.window_key
        ):
            refreshed = ObservedActionWindow(
                observation=observation,
                window_key=detected.window_key,
                authoritative_seq=detected.window_key.trigger_seq,
                received_at_monotonic=self._monotonic(),
                timeout_seconds=detected.timeout_seconds,
            )
            return SubmitRejectedRetryable(
                official_code=error.official_code or "INVALID_ACTION",
                rejected_action_key=attempt.action_key,
                refreshed_window=refreshed,
            )
        self._gate.mark_closed(attempt.window_key)
        return SubmitRejectedClosed(
            official_code=error.official_code or "INVALID_ACTION",
            latest_authoritative_seq=self._sync.last_seq,
        )

    def _finish_submit(
        self,
        attempt: ActionAttempt,
        outcome: SubmitOutcome,
        *,
        extra_payload: Optional[Mapping[str, Any]] = None,
    ) -> SubmitOutcome:
        payload = {
            "decision_id": attempt.decision_id,
            "attempt_no": attempt.attempt_no,
            "plan_revision": attempt.plan_revision,
            "action_key": attempt.action_key,
            "outcome_type": type(outcome).__name__,
        }
        if extra_payload:
            payload.update(extra_payload)
        official_code = getattr(outcome, "official_code", None)
        if official_code:
            payload["official_code"] = official_code
        reason = getattr(outcome, "reason", None)
        if reason:
            payload["reason"] = reason
        # 契约字段按类型实际拥有情况入审计（接口协议 §5：rejected_action_key /
        # latest_local_seq 属于 SubmitRejectedNoRefresh 等拒绝结果）
        for field in ("rejected_action_key", "latest_local_seq", "latest_authoritative_seq"):
            value = getattr(outcome, field, None)
            if value is not None:
                payload[field] = value
        self._emit_audit(
            AuditKind.SUBMISSION_OUTCOME,
            payload,
            decision_id=attempt.decision_id,
            attempt_no=attempt.attempt_no,
            trigger_seq=attempt.window_key.trigger_seq,
            round_no=attempt.window_key.round_no,
        )
        return outcome


class _PollFailure(Exception):
    """轮询循环内部的分类故障包装；携带 GameItem 直接上交应用层。"""

    def __init__(self, item: GameFailed) -> None:
        self.item = item
        super().__init__(item.reason)


def _loads(text: str) -> Any:
    import json

    try:
        return json.loads(text)
    except ValueError:
        raise DtoError("state 响应不是合法 JSON", recoverable=True) from None

