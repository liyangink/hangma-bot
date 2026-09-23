"""官方场次会话：GameSessionPort 的官方协议实现（v8 快照 + v9–v15 已审查变更）。

同步与提交语义（接口协议 §5/§8、模块 AGENTS）：

- 客户端局面 = 全量快照 + 后续增量事件（指南 v14 §2.1）：增量事件是
  权威公开事实，事件流只含自己的摸牌。本人摸牌窗口直接由增量事件送达
  （游标纪律修复，量化与口径见 doc/implementation/notes/cursor-discipline.md），
  不再逐批 seq=0 刷新；快照刷新只在事件流无法推导权威事实、或事实可能
  与我校行动相关时发生（2026-09-18 复盘修订，review/test-tournament-
  20260917 §8.2/§9.3）：与我校无鸣牌兴趣的他家弃牌/timeout 标记走纯增量
  （可鸣率实测仅 4-6%），副露（重置牌河/副露投影基线）、本人副露（手牌
  张数不进入事件流）、跨局边界 v10 快照与失步重建仍无条件刷新。
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
- 响应阶段（response_peng/response_chi）轮询时长轮询为主、看门狗兜底
  （2026-09-18 复盘修订）：官方在窗口走满的边界发出 timeout/pass 标记
  事件（5,343 次切换 99.6% 携带、挂起长轮询到达滞后实测最差 +26ms），
  边界发现由长轮询事件承担；仅对可能开我校响应窗的周期（鸣牌兴趣保守
  超集）在"权威截止晚界+0.20s 容错"挂看门狗，标记迟到才主动 seq=0
  捕获切换（39+11 例真沉默尾部与平台行为再变的保险）。竞速结构与槽位
  回收复用 _long_poll_racing_boundary。
- 响应窗口 WindowKey.trigger_seq 取触发弃牌事件序号（事件流最近一次
  tile_discarded，重建后回退结构化 last_discard 的官方 seq），同物理窗口
  身份稳定、每窗恰好交付一次（集成阶段第二轮 R2）。
"""

from __future__ import annotations

import asyncio
import math
import uuid
from dataclasses import replace
from typing import Any, Callable, Mapping, Optional, Tuple

from hangma_bot.application.contracts import (
    DEFAULT_POST_NETWORK_RESERVE_SEC,
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
    SubmissionCancelledBeforeSend,
    SUBMISSION_CANCELLED_IN_FLIGHT,
)
from hangma_bot.kernel.actions import Discard, Pass, WindowKey, WindowPhase
from hangma_bot.hangma.catch_play import analyze_catch_play
from hangma_bot.kernel.config import TimingConfig
from hangma_bot.kernel.observation import PlayerObservation
from hangma_bot.kernel.serialization import observation_to_json, public_event_to_json, window_key_to_json

from .request_audit import audited_request
from . import projector
from .action_gate import ActionGate
from .dto import StateResponse, parse_state_response
from .discard_pacing import DiscardPacing, plan_discard_pacing
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
from hangma_bot.adapters.recording import (
    build_action_response_payload,
    build_sse_frame_payload,
    build_state_response_payload,
)
from .notify import SSENotifyClient, StreamBudget
from .scheduler import DeadlineExceeded, Priority, RequestKind, RequestScheduler, StateQueryReservation
from .sync_state import KNOWN_EVENT_TYPES, ProtocolSyncState, SyncDecision
from .transport import OfficialTransport

# 阶段边界定时器的余量（秒）：官方响应窗口（peng/chi）固定走满配置秒数后
# 无事件切换阶段，定时器按"窗口秒数 + 本余量"与长轮询竞速，保证刷新落在
# 下一阶段已经生效之后（捕获 peng->chi 转换）而不截断原窗口。
_BOUNDARY_MARGIN_SEC = 0.05

_BOUNDARY_WATCHDOG_TOLERANCE_SEC = 0.20
# 边界看门狗容错（2026-09-18，review/test-tournament-20260917）：全 10 场
# 2,587 个"挂起长轮询带回边界标记事件"样本的到达滞后最差 +26ms（p99
# −95ms，负值为本机钟滞后平台 ~200ms 所致；发射侧 4,708 标记 99.9% 不晚
# 于截止所在秒）。0.20s ≈ 实测最差值的 8 倍余量；误触发只多一次 GET。

# 查询发起和响应完成是两个截止：GET至少预留100ms，收到状态后再留
# 50ms本地处理和共享的100ms动作网络预算，不宣称最坏耗时或服务器保证。
_STATE_RESPONSE_RESERVE_SEC = 0.10
_ACTION_AFTER_STATE_RESERVE_SEC = DEFAULT_POST_NETWORK_RESERVE_SEC + 0.05

# 跨局边界无进度 gap 快照的轮询退避（官方依据：指南 v14 §2.1——round_ended
# 后新局发牌不产生事件，旧游标轮询会立即收到 gap=true 全量快照且不会挂起）。
# 新局首事件产生前，反复原速轮询只会重复收到同 seq 快照（2026-09-04 测试赛
# 实测同一边界重复 5~47 次），既浪费 16/s 限速额度也刷爆恢复审计。
# 前 FAST 次保持原速：覆盖庄家常规思考窗口，保证边界后他家弃牌所开启的
# 响应窗口发现时延不回退；此后按表退避（秒）直至首事件推进快照水位。
# 封顶取 1.0s（P2-N4 修复）：原 2.0s 封顶使"庄家长考后弃牌"的窗口发现时延
# 最坏 ≈2s，1s 吃碰响应窗口在退避睡眠内开启时必然错过；封顶 1.0s 后最坏
# 发现时延 ≈1s+往返，错过概率显著下降（SSE 帧唤醒接入前的最优工程折衷；
# 无进度重复轮询在 16/s 限速预算内仍收敛到个位数）。
_BOUNDARY_STALL_FAST_POLLS = 2
_BOUNDARY_STALL_BACKOFF_SEC = (0.5, 1.0)

# SSE 帧驱动模式下的静默对齐周期（秒）：帧通道无帧时按此周期短拉对齐水位，
# 防御帧丢失（服务端 keepalive 30s 之外的极端静默）导致的漂移。
_SSE_IDLE_POLL_SEC = 5.0


class OfficialGameSession:
    """共享用户状态额度，独享本场连接槽、同步状态与动作门的官方会话。"""

    def __init__(
        self,
        *,
        game_id: str,
        transport: OfficialTransport,
        scheduler: RequestScheduler,
        timing: TimingConfig,
        monotonic_clock: Callable[[], float],  # 单调时钟秒；deadline 判定与审计时戳
        wall_clock_unix_ms: Callable[[], int],  # Unix毫秒；审计与校准不足时的期限估计
        audit: Optional[AuditSink] = None,
        audit_context: Optional[Callable[[], AuditContext]] = None,
        max_get_retries: int = 3,
        retry_backoff_base_sec: float = 0.2,
        retry_sleep: Optional[Callable[[float], Any]] = None,  # 测试注入
        sse_enabled: bool = False,  # SSE 帧驱动开关（默认关=行为与现状一致）
        sse_budget: Optional[StreamBudget] = None,  # 每 Token 共享的 SSE 并发预算
        discard_pacing_enabled: bool = True,  # 只缓发有时间依据的普通弃牌；内部诊断可关闭
        ordinary_long_poll_min_interval_ms: int = 0,  # 同场普通增量长轮询响应至下次发起的最短毫秒数
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
        self._discard_pacing_enabled = discard_pacing_enabled
        if isinstance(ordinary_long_poll_min_interval_ms, bool) or not isinstance(
            ordinary_long_poll_min_interval_ms, int
        ) or not 0 <= ordinary_long_poll_min_interval_ms <= 1000:
            raise ValueError("ordinary_long_poll_min_interval_ms 必须是 0..1000 的整数")
        self._ordinary_long_poll_min_interval_sec = ordinary_long_poll_min_interval_ms / 1000
        self._last_ordinary_long_poll_completed_at: Optional[float] = None
        self._state_request_no = 0  # /state 请求单调计数（原始事件对账键，跨会话重启归零安全）
        self._last_state_started_at = None  # 最近响应对应的请求开始时刻，单调秒
        self._last_clock_response = None  # 已收到但尚待投影验证的响应与单调起止时刻
        self._watermark_known_since = None  # 已消费水位形成时间的保守下界，单调秒
        self._last_state_history_only = False  # 只补旧历史的响应不能提供新的动作时间下界
        self._event_time_floors = {}  # 后续新事件不可能早于已证明水位的形成时间
        self._gate = ActionGate()
        self._delivered_windows = set()
        self._window_received_at = {}  # 首次交付动作窗的本机单调秒；缓发不得重新起算
        self._window_expiries = {}  # 每 WindowKey 首次单调截止，只允许收紧；单位秒
        self._boundary_expiries = {}  # 同弃牌同阶段的边界截止，防无事件/重复 pass 重开计时
        self._final: Optional[GameFinished] = None
        self._closed = False
        self._close_reason = ""
        self._active_tasks = set()
        self._sealed_history_rounds = set()
        self._poll_active = False  # next_item 单消费者守卫
        # SSE 帧驱动（可选能力，2026-09-05 接入）：帧到达 → 唤醒短拉增量；
        # 流终局/异常 → 永久降级回长轮询（sse_degraded 审计）。任务登记进
        # _active_tasks，aclose 统一取消；预算归还由 notify 客户端全出口保证
        self._sse_enabled = sse_enabled
        self._sse_budget = sse_budget
        self._sse_event: Optional[asyncio.Event] = asyncio.Event() if sse_enabled else None
        self._sse_healthy = sse_enabled
        self._sse_task: Optional[asyncio.Future] = None
        # 唤醒挂起标志：帧/自唤醒置位后、等待方消费前的信号保留——
        # 纯 Event 在"等待入口 clear()"时会把未消费的唤醒抹掉（回归
        # test_sse_self_wake 行为用例锁定该竞态）
        self._sse_wake_pending = False
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

        self._seal_history("session_closed:" + reason)
        self._closed = True
        self._close_reason = reason
        for task in list(self._active_tasks):
            task.cancel()

    # ---------- 轮询循环 ----------

    async def _poll_cycle(self) -> GameItem:
        """一个完整轮询周期：持续到产出窗口、终局或故障。"""

        rebuild_streak = 0
        boundary_stalls = 0  # 跨局边界连续无进度 gap 快照计数（退避用，见 _boundary_stall_sleep）
        # next_item 每次交付动作窗后都会重新进入本循环。若本人刚提交弃牌
        # 或过牌，他家可能立即鸣牌再弃牌，首个查询不能因局部标志重置而降级。
        watch_opponent_discard = self._sync.has_snapshot and not self._sync.finished
        imminent_discard = self._snapshot_imminent_discard(self._sync.snapshot)
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
                self._ensure_sse_task()
                boundary_timeout = self._phase_boundary_timeout()
                if self._sse_enabled and self._sse_healthy:
                    # SSE 帧驱动（开关开启且流健康）：帧到短拉增量；
                    # 静默/边界/降级路径见 _sse_or_boundary_wait
                    response = await self._sse_or_boundary_wait(boundary_timeout)
                elif boundary_timeout is None:
                    # 他家摸牌/副露或响应标记后，下一次增量查询是发现未知弃牌
                    # 的唯一入口。响应标记可能是下一位对手摸牌之前的最后
                    # 可见事件；若等看见摸牌才提高优先级，同一响应窗口内的
                    # 摸打会在普通查询排队时一起积压。
                    # 响应窗尚未可见，不能依赖已有窗口的恢复优先级；长轮询
                    # 返回 pending 时保持此用途，直到事件或快照确认阶段改变。
                    # 任一活跃场的长轮询都可能发现新的 1 秒响应窗，包含局间
                    # 进入下一局的首个事件。已看到他家摸牌的查询风险更高；
                    # 一般监听与普通同步等久后晋级，避免长期饥饿。
                    response = await self._get_state(
                        long_poll=True, priority=(Priority.DRAW_WATCH if imminent_discard
                                                 else Priority.DISCARD_WATCH if watch_opponent_discard
                                                 else Priority.POLL),
                        query_purpose="discard_watch" if watch_opponent_discard else "state_sync")
                else:
                    response = await self._long_poll_racing_boundary(boundary_timeout)
            except _PollFailure as failure:
                return failure.item
            if response.kind == "pending":
                if not response.gap and self._sync.has_snapshot and not self._last_state_history_only:
                    self._watermark_known_since = self._last_state_started_at
                if response.gap:
                    # pending 响应携带 gap=true：权威序号已断链，必须重建
                    # 而不是继续用旧 seq 长轮询（wv9 阻断项）
                    pre_seq = self._sync.last_seq
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
                    # pending+gap 连续无进度由上方 rebuild_streak>2 保护性上交
                    # （有界快速失败，可恢复重入）；v10 边界无进度的退避只走
                    # snapshot+gap 分支。此处不做退避睡眠，避免与 rebuild_loop
                    # 保护重复实现造成语义漂移（F-15 复核结论）。
                    if self._sync.last_seq > pre_seq:
                        # wv6：水位前进 = 断链已修复，重置恢复计数，防跨轮累积
                        # （否则间歇性进展的长边界会因 streak 累积误判 rebuild_loop）
                        boundary_stalls = 0
                        rebuild_streak = 0
                    snapshot = self._sync.snapshot
                    watch_opponent_discard = self._snapshot_needs_discard_watch(snapshot)
                    imminent_discard = self._snapshot_imminent_discard(snapshot)
                continue
            if response.kind in ("snapshot", "finished"):
                pre_seq = self._sync.last_seq
                pre_round = self._sync.snapshot.round_no if self._sync.snapshot else None
                pre_phase = self._sync.snapshot.phase if self._sync.snapshot else None
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
                if (response.gap and self._sync.last_seq <= pre_seq
                        and self._sync.snapshot.round_no == pre_round
                        and self._sync.snapshot.phase == pre_phase):
                    # v10 跨局边界无进度快照：新局首事件尚未产生，旧游标轮询
                    # 会立即再次命中同一规则返回同 seq 快照（实测同边界重复
                    # 5~47 次）。前 FAST 次原速、此后退避（见常量注释）。
                    boundary_stalls += 1
                    await self._boundary_stall_sleep(boundary_stalls)
                else:
                    boundary_stalls = 0
                snapshot = self._sync.snapshot
                watch_opponent_discard = self._snapshot_needs_discard_watch(snapshot)
                imminent_discard = self._snapshot_imminent_discard(snapshot)
                continue
            # 增量事件：按事件是否可推导权威事实决定投递路径（游标纪律修复）。
            # 弃牌/timeout/本人副露等触发权威快照刷新；否则直接走增量投递，
            # 正常事件流（连续摸牌/过牌）零重建，摸牌窗口不再依赖快照送达。
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
                snapshot = self._sync.snapshot
                watch_opponent_discard = self._snapshot_needs_discard_watch(snapshot)
                imminent_discard = self._snapshot_imminent_discard(snapshot)
                continue
            rebuild_streak = 0
            boundary_stalls = 0
            if self._watermark_known_since is not None:
                for event in response.events:
                    self._event_time_floors.setdefault(event.seq, self._watermark_known_since)
            if not self._last_state_history_only:
                self._watermark_known_since = self._last_state_started_at
            my_seat = self._sync.snapshot.seat
            for event in response.events:
                if event.type == "tile_drawn":
                    watch_opponent_discard = event.seat != my_seat
                    imminent_discard = event.seat != my_seat
                elif event.type in ("chi", "peng") and event.seat != my_seat:
                    watch_opponent_discard = True
                    imminent_discard = True
                elif event.type == "tile_discarded":
                    # 他家可立即碰/吃后再弃牌；即使当前弃牌与我无鸣牌兴趣，
                    # 后续新弃牌仍可能给我打开一秒响应窗。
                    watch_opponent_discard = True
                    imminent_discard = False
                elif event.type in ("round_ended", "game_ended"):
                    watch_opponent_discard = False
                    imminent_discard = False
                elif event.type in ("pass", "timeout"):
                    # 无鸣牌兴趣的响应周期不拉边界快照；其末尾标记可能直接
                    # 交接到对手摸打。提前保护下一次增量查询，不增添 GET。
                    watch_opponent_discard = True
                    imminent_discard = False
            if self._sync.events_need_authoritative_refresh(response.events):
                self._emit_audit(AuditKind.AUTHORITATIVE_STATE, {
                    "snapshot_refresh_reason": "events_require_snapshot",
                    "event_types": sorted({event.type for event in response.events}),
                    "consumed_seq": self._sync.last_seq,
                }, trigger_seq=self._sync.last_seq)
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
                snapshot = self._sync.snapshot
                watch_opponent_discard = (snapshot is not None and snapshot.phase == "draw"
                                          and snapshot.turn != snapshot.seat)
                imminent_discard = self._snapshot_imminent_discard(snapshot)
                continue
            rescue_deadline = self._estimated_response_rescue_deadline()
            if rescue_deadline is not None:
                # 增量牌面可直接投影，但整秒事件时间与较早的已知水位只能
                # 给出过早截止。只有本地估算已不足以发动作且仍可能鸣牌时，
                # 再花一次 state 额度读取官方毫秒截止；未知窗若已关闭由快照
                # 纠正，绝不据乐观时间直接 POST。
                self._emit_audit(AuditKind.AUTHORITATIVE_STATE, {
                    "snapshot_refresh_reason": "estimated_deadline_rescue",
                    "consumed_seq": self._sync.last_seq,
                }, trigger_seq=self._sync.last_seq)
                try:
                    snapshot_response = await self._get_state(
                        long_poll=False, force_full=True,
                        deadline_monotonic=rescue_deadline - _ACTION_AFTER_STATE_RESERVE_SEC,
                        priority=Priority.RECOVERY,
                        query_purpose="estimated_deadline_rescue")
                except _PollFailure as failure:
                    return failure.item
                if snapshot_response.kind not in ("snapshot", "finished"):
                    return GameFailed(self.game_id, True, "snapshot_expected_got_" + snapshot_response.kind)
                apply_failure = self._apply_or_fail(snapshot_response, finished=snapshot_response.finished)
                if apply_failure is not None:
                    return apply_failure
                if snapshot_response.finished:
                    return self._finish_game()
                delivered = self._maybe_deliver_window()
                if delivered is not None:
                    return delivered
                watch_opponent_discard = self._snapshot_needs_discard_watch(self._sync.snapshot)
                imminent_discard = self._snapshot_imminent_discard(self._sync.snapshot)
                continue
            if any(event.type in ("tile_discarded", "timeout") for event in response.events):
                # 2026-09-18：与我校无鸣牌兴趣的弃牌/标记事件不再触发全量
                # 快照（review/test-tournament-20260917 §8.2/§9.3）；留审计
                # 便于赛后按同一口径复核节省量与漏刷案例。沿用 AUTHORITATIVE_STATE
                # 的 snapshot_refresh_reason 决策族（同 events_require_snapshot
                # 先例）：按 kind 统计权威刷新次数的消费方必须同时过滤
                # reason 前缀 skipped_，此约定与本条审计互为契约。标签细分：
                # 本批弃牌全为本人回显时记 skipped_own_discard_echo（S5 口径），
                # 其余记 skipped_no_claim_interest，复核口径不混计。
                _discards = [e for e in response.events if e.type == "tile_discarded"]
                _skip_reason = (
                    "skipped_own_discard_echo"
                    if _discards and all(e.seat == self._sync.snapshot.seat for e in _discards if e.seat is not None)
                    else "skipped_no_claim_interest"
                )
                self._emit_audit(AuditKind.AUTHORITATIVE_STATE, {
                    "snapshot_refresh_reason": _skip_reason,
                    "event_types": sorted({event.type for event in response.events}),
                    "consumed_seq": self._sync.last_seq,
                }, trigger_seq=self._sync.last_seq)
            delivered = self._maybe_deliver_incremental_draw_window()
            if delivered is not None:
                return delivered

    @staticmethod
    def _snapshot_needs_discard_watch(snapshot) -> bool:
        """响应阶段可由他家立即鸣牌再弃牌；对手摸牌阶段也须盯首次弃牌。"""
        return snapshot is not None and (
            snapshot.phase in ("response_peng", "response_chi")
            or (snapshot.phase == "draw" and snapshot.turn != snapshot.seat))

    @staticmethod
    def _snapshot_imminent_discard(snapshot) -> bool:
        """已知他家正持摸牌行动权时，下一条公开事件大概率是弃牌。"""
        return (snapshot is not None and snapshot.phase == "draw"
                and snapshot.turn != snapshot.seat)

    def _estimated_response_rescue_deadline(self) -> Optional[float]:
        """仅在增量响应的早界已无动作预算时，给权威 GET 一个宽松完成上限。

        官方事件 ts 仅到整秒；[ts, ts+1) 内的弃牌都可能对应本窗口。
        晚界只约束这次 GET 的等待，不能作为 POST 截止。POST 随后必须
        使用快照的 window_deadline_ms；无事件 ts 时只给 GET 一次窗口时长。
        """
        detected = self._sync.incremental_response_window()
        if detected is None or not self._sync.claim_interest_for_cycle():
            return None
        timing = self._window_timing(detected)
        now = self._monotonic()
        if (not timing["deadline_is_estimated"]
                or timing["expires_at_monotonic"] - now > _ACTION_AFTER_STATE_RESERVE_SEC):
            return None
        event = next((e for e in reversed(self._sync.history)
                      if e.seq == detected.window_key.trigger_seq), None)
        if event is None or event.occurred_at_unix_sec is None or event.occurred_at_unix_sec <= 0:
            return now + detected.timeout_seconds
        latest_unix_ms = int((event.occurred_at_unix_sec + 1 + detected.timeout_seconds) * 1000)
        wall_estimate = now + (latest_unix_ms - self._wall_ms()) / 1000.0
        interval = self._scheduler.deadline_clock.deadline(latest_unix_ms, now)
        estimate = max(wall_estimate, interval.latest) if interval is not None else wall_estimate
        return min(estimate, now + detected.timeout_seconds)

    def _ensure_sse_task(self) -> None:
        """SSE 帧监听任务懒启动（首次 next_item 时）；降级后不再重启。"""

        if (
            not self._sse_enabled
            or not self._sse_healthy
            or self._sse_task is not None
            or self._closed
        ):
            return
        client = SSENotifyClient(
            self.game_id,
            self._transport,
            budget=self._sse_budget,
            on_frame=self._on_sse_frame,
            audit_emit=self._emit_audit,
            monotonic_clock=self._monotonic,
        )
        self._sse_task = asyncio.ensure_future(self._sse_run(client))
        self._active_tasks.add(self._sse_task)
        self._sse_task.add_done_callback(self._active_tasks.discard)

    async def _on_sse_frame(self, frame) -> None:
        """帧到达回调（notify 客户端以 await 调用，必须为协程）：唤醒帧驱动短拉。

        顺手把帧原文留进审计原文流（RAW_PROTOCOL_STATE，source=sse_frame）：
        raw 只进审计、不进异常与日志（notify 模块契约）；发射在 SSE 监听
        任务上且非阻塞，不触碰动作窗口的提交路径。
        """

        self._emit_audit(
            AuditKind.RAW_PROTOCOL_STATE,
            build_sse_frame_payload(
                endpoint="GET /api/games/{}/notify".format(self.game_id),
                seq=frame.seq,
                closed=frame.closed,
                raw=getattr(frame, "raw", None) or "",
            ),
            trigger_seq=frame.seq,
        )
        if self._sse_event is not None:
            self._sse_wake_pending = True
            self._sse_event.set()

    async def _sse_run(self, client: SSENotifyClient) -> None:
        """SSE 流生命周期守护；任何终局都降级为长轮询并留审计。

        RECONNECTS_EXHAUSTED / BUDGET_UNAVAILABLE / TERMINAL / 异常一律
        视为"本会话不再使用 SSE"——有界回退，不自动重开（重开交给监督层
        重建会话的自然路径）；取消（aclose）原样传播。
        """

        try:
            result = await client.run()
            reason = result.kind.value
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - SSE 失败绝不阻塞动作路径
            reason = "client_error:" + type(exc).__name__
        self._sse_healthy = False
        if self._sse_event is not None:
            self._sse_event.set()  # 唤醒可能在等待的帧通道 → 走降级回退
        self._emit_audit(
            AuditKind.PROTOCOL_RECOVERED,
            {"trigger": "sse_degraded", "reason": reason},
            trigger_seq=self._sync.last_seq,
        )

    async def _sse_or_boundary_wait(self, boundary_timeout):
        """帧驱动模式下的等待与拉取；静默/边界超时与降级自动回退长轮询。

        - 帧到达 → 短拉增量（GET /state?seq=本地已消费游标，游标纪律不变）；
        - 静默超时（无边界时 _SSE_IDLE_POLL_SEC）→ 短拉对齐水位（防帧丢失漂移）；
        - 边界超时（响应阶段官方 deadline 推导）→ 对齐边界定时器语义，
          主动 seq=0 权威刷新捕获无事件的阶段切换（普通优先级）；
        - SSE 降级（等待期间流终局）→ 回退既有边界竞速/长轮询路径。
        """

        timeout = boundary_timeout if boundary_timeout is not None else _SSE_IDLE_POLL_SEC
        assert self._sse_event is not None  # sse_enabled 时必有
        if not self._sse_wake_pending:
            # 无挂起唤醒才进入等待；挂起信号直接消费（clear 前置检查，
            # 不会抹掉未消费的帧/自唤醒——回归 test_sse_self_wake）
            self._sse_event.clear()
            try:
                await asyncio.wait_for(self._sse_event.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                pass
        self._sse_wake_pending = False
        if not self._sse_healthy:
            fallback_boundary = self._phase_boundary_timeout()
            if fallback_boundary is None:
                return await self._get_state(long_poll=True)
            return await self._long_poll_racing_boundary(fallback_boundary)
        if boundary_timeout is not None:
            return await self._get_state(
                long_poll=False, force_full=True, priority=Priority.POLL
            )
        return await self._get_state(long_poll=False)

    def _phase_boundary_timeout(self) -> Optional[float]:
        """响应阶段的边界看门狗定时时长；其余阶段与无关周期为 None。

        2026-09-18 复盘修订（review/test-tournament-20260917/REPORT.md
        §8.2 与边界标记实测）：官方在窗口走满的边界时刻发出 timeout/pass
        标记事件——全 10 场 5,343 次 peng→chi 切换 99.6% 携带标记，挂起
        长轮询的标记到达滞后实测最差 +26ms。因此边界发现以长轮询事件为
        主、定时器降级为看门狗：

        - 与我校无鸣牌兴趣的周期不设定时器（标记事件由投影消费，占
          ~94-96% 的响应窗，不再每个边界刷一次全量）；
        - 有兴趣的周期在"权威截止（晚界）+ _BOUNDARY_WATCHDOG_TOLERANCE_SEC"
          看门狗到点仍未等来标记事件时，才主动 seq=0 捕获切换——覆盖
          39+11 例真沉默尾部与未来平台行为再变的保险。

        竞速结构与槽位回收复用 _long_poll_racing_boundary：正常路径长轮询
        先返回（标记准时），看门狗被取消；仅标记迟到时看门狗取消长轮询。
        仅在 response 阶段挂起，draw 阶段维持现状。
        """

        snapshot = self._sync.snapshot
        if snapshot is None or self._sync.finished:
            return None
        if snapshot.phase in ("response_peng", "response_chi"):
            # 增量摸牌已证明旧响应周期结束；本人摸牌窗口交付并提交后，
            # 快照仍可能停在旧吃窗。继续用它的截止定时器会取消新长轮询，
            # 再把无关的 phase_boundary 快照排进普通额度队列。
            for event in reversed(self._sync.history):
                if event.seq <= snapshot.seq:
                    break
                if event.kind == "tile_drawn":
                    return None
        if not self._sync.claim_interest_for_cycle():
            return None  # 无关周期：标记事件推进投影即可，不做边界刷新
        incremental = self._sync.incremental_response_window()
        if incremental is not None:
            # 偏差说明：事件推导窗无官方截止，这里沿用 _window_timing 的
            # 保守早界（提交口径）而非晚界——看门狗偏早只多一次 GET
            # （安全侧）。有兴趣弃牌通常已先触发权威刷新进入下方快照
            # 分支（权威晚界+容错），本分支仅在投影路径覆盖时可达。
            expiry = self._window_timing(incremental)["expires_at_monotonic"]
            return max(expiry - self._monotonic(), 0.0) + _BOUNDARY_WATCHDOG_TOLERANCE_SEC
        if snapshot.phase in ("response_peng", "response_chi"):
            # F4（2026-09-05）：优先官方绝对截止 window_deadline_ms（实测
            # 4264/4264 响应快照携带）——绝对值天然不被 pass 推进后的刷新
            # 重置（旧相对猜测式的核心缺陷）；看门狗取晚界（宁晚勿早，
            # 标记事件未到才算迟到），官方未提供时退回窗口秒数+容错
            expiry, _ = self._snapshot_expiry(for_boundary=True)
            return max(expiry - self._monotonic(), 0.0) + _BOUNDARY_WATCHDOG_TOLERANCE_SEC
        return None

    def _snapshot_expiry(self, *, for_boundary=False):
        """把同阶段官方 Unix 毫秒截止只向单调时钟收紧；无字段时显式估计。

        可用区间的早界给提交、晚界给阶段等待；各自只收紧，不能相互借用。
        样本不足仍用原墙钟估计，审计显式标明校准是否可用。
        """
        snapshot = self._sync.snapshot
        phase = snapshot.phase
        duration = (self._timing.peng_timeout_sec if phase == "response_peng" else
                    self._timing.chi_timeout_sec if phase == "response_chi" else
                    self._timing.discard_timeout_sec)
        identity = (self._sync.response_cycle_key if phase.startswith("response_") else snapshot.seq)
        key = (snapshot.round_no, phase, snapshot.turn, identity, for_boundary)
        official = snapshot.window_deadline_ms
        estimated = official is None or official <= 0
        expiry = self._monotonic() + (duration if estimated else (official - self._wall_ms()) / 1000.0)
        if not estimated:
            interval = self._scheduler.deadline_clock.deadline(official, self._monotonic())
            if interval is not None:
                expiry = interval.latest if for_boundary else min(expiry, interval.earliest)
        previous = self._boundary_expiries.get(key)
        if previous is not None:
            expiry = min(previous[0], expiry)
            estimated = previous[1] and estimated
        result = (expiry, estimated)
        self._boundary_expiries[key] = result
        return result

    def _window_timing(self, detected):
        """统一投递和409刷新截止；旧响应阶段截止不能借给增量摸牌。"""
        key = detected.window_key
        snapshot = self._sync.snapshot
        if (snapshot is not None and snapshot.phase == key.phase.value
                and snapshot.round_no == key.round_no
                and key.trigger_seq <= snapshot.seq):
            expiry, estimated = self._snapshot_expiry()
        else:
            # 只有事件且无权威截止时仍是估计；事件 Unix 秒可提供保守起点。
            expiry = self._monotonic() + detected.timeout_seconds
            estimated = True
            event = next((e for e in reversed(self._sync.history) if e.seq == key.trigger_seq), None)
            floor = self._event_time_floors.get(key.trigger_seq)
            if event is not None and event.occurred_at_unix_sec is not None:
                from_event = self._monotonic() + event.occurred_at_unix_sec - self._wall_ms() / 1000.0
                interval = self._scheduler.deadline_clock.deadline(
                    event.occurred_at_unix_sec * 1000, self._monotonic())
                if interval is not None:
                    from_event = min(from_event, interval.earliest)
                floor = from_event if floor is None else max(floor, from_event)
            if floor is not None:
                # ts 只有整秒。上一次水位的查询开始时间也是事件时间的下界，
                # 可避免把整秒截断当成精确时间而损失几乎整个吃碰窗口。
                expiry = min(expiry, floor + detected.timeout_seconds)
        previous = self._window_expiries.get(key)
        if previous is not None:
            if not (previous[1] and not estimated and key not in self._delivered_windows):
                # 已交付窗口的应用预算只能收紧；两份同级估计或权威值
                # 也按旧值收紧。唯有尚未交付的暂定估计可被官方毫秒截止纠正。
                expiry = min(expiry, previous[0])
                estimated = estimated and previous[1]
        self._window_expiries[key] = (expiry, estimated)
        return {"expires_at_monotonic": expiry, "deadline_is_estimated": estimated}

    async def _long_poll_racing_boundary(self, timeout_seconds: float) -> StateResponse:
        """长轮询与阶段边界定时器竞速；返回两者中先到的权威结果。

        - 长轮询先到：取消定时器，结果（pending/events/snapshot/异常）原样返回；
        - 定时器先到：取消挂起的长轮询，主动拉一次 seq=0 权威快照
          （非阻塞刷新，恢复类请求走普通优先级，不挤占动作 POST 与
          紧急恢复通道）。两个子任务都登记进 _active_tasks：
          aclose 可以取消它们，不留下悬挂的长轮询或定时器。
        """

        reservation, response_deadline, window_end = self._protect_next_chi_query(timeout_seconds)
        # 已临近边界时不再挂一条几乎必被取消的GET；阈值只由查询往返
        # 余量决定。令牌桶的平均间隔不是这条请求实际入队后的等待时长，
        # 将其乘二用作边界阈值会在M=10时过早跳过必要的进度长轮询。
        # 2026-09-18：timeout_seconds 已含看门狗容错，判定须用扣除容错后
        # 的真实边界剩余，否则短路永假、临近边界反而先挂必被取消的轮询。
        boundary_remaining = timeout_seconds - _BOUNDARY_WATCHDOG_TOLERANCE_SEC
        if boundary_remaining < _STATE_RESPONSE_RESERVE_SEC:
            try:
                await self._boundary_timer(timeout_seconds)
                return await self._get_state(
                    long_poll=False, force_full=True, priority=Priority.POLL,
                    deadline_monotonic=response_deadline, state_reservation=reservation,
                    obsolete_window_end=window_end, query_purpose="phase_boundary")
            finally:
                if reservation is not None:
                    reservation.cancel()
        # 已确认处在我方有鸣牌兴趣的响应周期：标记事件一到就需要判断
        # 下一吃窗。此时状态长轮询的额度许可优先于无关场的普通轮询；
        # 仍受同用户总额与既有边界保留约束，不提前假定吃窗已经存在。
        poll_task = asyncio.ensure_future(self._get_state(
            long_poll=True, priority=Priority.RECOVERY,
            query_purpose="response_progress"))
        timer_task = asyncio.ensure_future(self._boundary_timer(timeout_seconds))
        for task in (poll_task, timer_task):
            self._active_tasks.add(task)
            task.add_done_callback(self._active_tasks.discard)
        try:
            done, _pending = await asyncio.wait(
                (poll_task, timer_task), return_when=asyncio.FIRST_COMPLETED
            )
            if poll_task in done:
                # 同时完成时先消费已收到的权威事件，不能被边界计时器丢弃。
                # 新状态若仍过边界，下一次等待会立即进行边界查询。
                return poll_task.result()
            if timer_task in done:
                poll_task.cancel()
                # 必须先收回本场唯一state槽。若取消与响应同时完成，优先消费
                # 已取得的权威结果，不能为了查边界而丢掉它或跳过事件水位。
                await asyncio.gather(poll_task, return_exceptions=True)
                if not poll_task.cancelled():
                    return poll_task.result()
                self._emit_audit(AuditKind.AUTHORITATIVE_STATE, {
                    "snapshot_refresh_reason": "phase_boundary",
                    "consumed_seq": self._sync.last_seq,
                }, trigger_seq=self._sync.last_seq)
                # 定时器先到：非阻塞权威刷新，捕获无事件的 peng->chi 切换
                return await self._get_state(
                    long_poll=False, force_full=True, priority=Priority.POLL,
                    deadline_monotonic=response_deadline, state_reservation=reservation,
                    obsolete_window_end=window_end, query_purpose="phase_boundary",
                )
            return poll_task.result()  # 轮询先到；异常（含 _PollFailure）原样传播
        finally:
            for task in (poll_task, timer_task):
                if not task.done():
                    task.cancel()
            # 回收两个子任务的结果：被取消的挂起轮询与已完成的定时器都不得
            # 留下未检索的取消/异常（避免事件循环告警与资源悬挂）。
            await asyncio.gather(poll_task, timer_task, return_exceptions=True)
            if reservation is not None:
                reservation.cancel()

    def _protect_next_chi_query(self, timeout_seconds: float):
        """仅用已见权威碰窗保护我方可能吃的边界，不预知对手动作或牌面。"""
        snapshot = self._sync.snapshot
        if (snapshot is None or snapshot.phase != "response_peng"
                or (snapshot.turn + 1) % 4 != snapshot.seat
                or self._sync.response_suppressed_for_self):
            return None, None, None
        expiry, estimated = self._snapshot_expiry()
        if estimated:
            return None, None, None
        window_end = expiry + self._timing.chi_timeout_sec
        response_deadline = window_end - _ACTION_AFTER_STATE_RESERVE_SEC
        latest_start = response_deadline - _STATE_RESPONSE_RESERVE_SEC
        ready = self._monotonic() + timeout_seconds
        if ready >= latest_start:
            return None, None, None
        reservation = self._scheduler.protect_state_query(
            ready_at_monotonic=ready, latest_start_at_monotonic=latest_start)
        return reservation, response_deadline, window_end

    async def _boundary_timer(self, timeout_seconds: float) -> None:
        """阶段边界定时器；用 retry_sleep 实现以支持测试注入假时钟。"""

        await self._retry_sleep(timeout_seconds)

    async def _boundary_stall_sleep(self, stalls: int) -> None:
        """跨局边界无进度 gap 快照后的轮询退避；前 FAST 次原速，此后指数退避。

        官方依据（指南 v14 §2.1）：round_ended 后新局发牌不产生任何事件，
        此时旧游标轮询会立即收到 gap=true 全量快照且不会挂起——新局首事件
        （庄家出牌）产生前，每次原速轮询都重复收到同 seq 快照。退避把边界
        等待的请求数收敛到个位数（2026-09-04 测试赛实测同边界重复 5~47 次），
        并保留前 FAST 次原速轮询：覆盖庄家常规思考窗口，不延迟边界后他家
        弃牌所开启响应窗口的发现。任何进度（事件流或快照 seq 前进）由调用
        方清零计数。sleep 用 retry_sleep 注入，测试假时钟可精确推进。
        """

        if stalls <= _BOUNDARY_STALL_FAST_POLLS:
            return
        index = min(
            stalls - _BOUNDARY_STALL_FAST_POLLS - 1,
            len(_BOUNDARY_STALL_BACKOFF_SEC) - 1,
        )
        await self._retry_sleep(_BOUNDARY_STALL_BACKOFF_SEC[index])

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
            previous = self._sync.snapshot
            closing_payload = None
            if previous is not None and previous.round_no != snapshot.round_no:
                tail = ()
                if snapshot.round_no == previous.round_no + 1:
                    endings = sorted({e.seq for e in response.events if e.type == "round_ended"})
                    end = None
                    if endings and not finished and snapshot.phase not in ("settled", "finished"):
                        end = endings[-1]
                    elif len(endings) > 1:
                        end = endings[-2]
                    if end is not None:
                        floor = self._sync.history_floor_seq
                        tail = tuple(e for e in response.events if (floor is None or e.seq > floor) and e.seq <= end)
                closing_payload = self._history_closure_payload("round_changed", extra_events=tail)
            self._sync.apply_full_snapshot(snapshot, finished=finished, events=response.events)
            self._watermark_known_since = self._last_state_started_at
            if previous is None or previous.round_no != snapshot.round_no:
                self._event_time_floors.clear()
            if closing_payload is not None:
                self._commit_history_closure(closing_payload)
            if not finished:
                sample = self._last_clock_response
                if sample is not None and sample[0] is response:
                    duration = {"response_peng": self._timing.peng_timeout_sec,
                                "response_chi": self._timing.chi_timeout_sec,
                                "draw": self._timing.discard_timeout_sec}.get(snapshot.phase)
                    if duration is not None and self._scheduler.deadline_clock.observe(
                            deadline_unix_ms=snapshot.window_deadline_ms, duration_sec=duration,
                            started_at=sample[1], completed_at=sample[2]):
                        self._emit_audit(AuditKind.AUTHORITATIVE_STATE, {
                            "deadline_clock": self._scheduler.deadline_clock.metadata(self._monotonic()),
                        }, trigger_seq=snapshot.seq, round_no=snapshot.round_no)
                    self._last_clock_response = None
                self._snapshot_expiry()
                self._sync.current_observation()  # 预热缓存（已验证必成功）
                if self._sync.last_transition_checks:
                    self._emit_audit(AuditKind.AUTHORITATIVE_STATE, {
                        "observation_transition_checks": list(self._sync.last_transition_checks),
                        "consumed_seq": self._sync.last_seq,
                    }, trigger_seq=self._sync.last_seq, round_no=snapshot.round_no)
                window_key = self._sync.current_window()
                # F-23：每个权威快照归并后通知动作门——窗口已迁移时解除
                # 模糊封锁标记（ActionGate.observe_authoritative_window；
                # 已响应集合保留，"同窗零次追加提交"不变量不受影响）。
                self._gate.observe_authoritative_window(
                    window_key.window_key if window_key is not None else None
                )
                # last_discard 纯牌码形态的重建提示进审计（不改变观察内容）：
                # 牌河与 turn 交叉验证不一致时记录，供赛后核对官方 turn 语义。
                _, discard_notes = projector.project_last_discard(snapshot)
                for note in discard_notes:
                    self._emit_audit(
                        AuditKind.AUTHORITATIVE_STATE,
                        {"last_discard_projection_note": note},
                        trigger_seq=snapshot.seq,
                        round_no=snapshot.round_no,
                    )
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
        if (
            detected.window_key.phase in (WindowPhase.RESPONSE_PENG, WindowPhase.RESPONSE_CHI)
            and self._sync.response_suppressed_for_self
        ):
            # F2（2026-09-05 取证修复）：本人已对当前响应周期表态（自己的
            # pass 事件回显或 POST 接受回执）——官方 responding_seats 不随
            # pass 收缩，此守卫是"我已表态"的唯一可靠判据，杜绝同窗二次
            # 投递与二次提交
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
            # authoritative_seq 契约要求与 observation.snapshot_seq 一致
            # （ObservedActionWindow.__post_init__）。响应窗口身份稳定化后
            # trigger_seq 指向触发弃牌事件（如 182），而快照权威 seq 会随
            # 他家 pass 推进（如 185）：二者语义不同，authoritative_seq
            # 必须是本次观察所基于的权威状态序号。
            authoritative_seq=observation.snapshot_seq,
            received_at_monotonic=self._monotonic(),
            timeout_seconds=detected.timeout_seconds,
            **self._window_timing(detected),
        )
        self._delivered_windows.add(key)
        self._window_received_at[key] = window.received_at_monotonic
        if detected.trigger_projection_note is not None:
            # 触发序号退化兜底（事件历史空 + 纯牌码 last_discard）：
            # 与 last_discard_projection_note 同款审计，供赛后核对身份稳定性
            self._emit_audit(
                AuditKind.AUTHORITATIVE_STATE,
                {"trigger_seq_projection_note": detected.trigger_projection_note},
                trigger_seq=key.trigger_seq,
                round_no=key.round_no,
            )
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

    def _maybe_deliver_incremental_draw_window(self) -> Optional[ObservedActionWindow]:
        """增量与快照共用一个观察、窗口和截止投递入口。"""
        return self._maybe_deliver_window()

    def _finish_game(self) -> GameFinished:
        self._seal_history("game_finished")
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

    def _emit_raw_state(self, result, seq_requested: int, parsed: Optional[StateResponse], *, request_timing=None) -> None:
        """E1：/state 响应原文全量落审计；解析失败时 parsed=None 只记原文。

        request_timing 的时间点为本进程单调时钟秒；传输开始不等于服务器收包。
        raw 是未经解析的官方原文（传输层已做 Token 精确替换，记录层入队
        前还有第二层脱敏）；坏报文照样落盘供赛后诊断。非阻塞：RAW 类走
        低优先级队列，绝不影响动作窗口。
        """

        snapshot = parsed.snapshot if parsed is not None else None
        self._emit_audit(
            AuditKind.RAW_PROTOCOL_STATE,
            {**build_state_response_payload(
                endpoint="GET /api/games/{}/state".format(self.game_id),
                http_status=result.status,
                seq_requested=seq_requested,
                seq_observed=snapshot.seq if snapshot is not None else None,
                request_no=self._state_request_no,
                raw=result.text,
            ), "request_timing": {**(request_timing or {}),
                "completed_at_monotonic": self._monotonic()}},
            trigger_seq=snapshot.seq if snapshot is not None else None,
            round_no=snapshot.round_no if snapshot is not None else None,
        )

    def _emit_raw_state_error(self, exc: OfficialError, seq_requested: int, *, request_timing=None) -> None:
        """F-05：非 2xx / 响应未到达的 /state 失败也发射原始事件。

        429/401/403/404/5xx 等失败响应体（传输层已完成 Token 精确替换的
        原文在 exc.raw_text）是限速与认证故障诊断的关键证据；超时/断连
        （UncertainTransportError，无响应体）记 http_status=None + raw=""
        表示"原文不存在"（与 E3 同口径）。request_no 沿用当前成功计数、
        不递增——验证器连续性检查只按成功响应集合判定，不受影响。
        """

        self._emit_audit(
            AuditKind.RAW_PROTOCOL_STATE,
            {**build_state_response_payload(
                endpoint="GET /api/games/{}/state".format(self.game_id),
                http_status=exc.http_status,
                seq_requested=seq_requested,
                seq_observed=None,
                request_no=self._state_request_no,
                raw=exc.raw_text or "",
            ), "request_timing": {**(request_timing or {}),
                "completed_at_monotonic": self._monotonic()}},
        )

    def _emit_raw_action(
        self,
        http_status: Optional[int],
        raw_text: Optional[str],
        attempt: ActionAttempt,
        *, request_timing=None,
    ) -> None:
        """E3：动作提交响应原文落审计；409/429 拒绝体完整保留。

        raw_text 为 None/空串表示响应从未到达（如 POST 超时/断连），记录
        本身证明"该次尝试的响应原文不存在"，验证器按 SubmitAmbiguous
        语义要求该键存在、对账不悬空。
        """

        self._emit_audit(
            AuditKind.RAW_PROTOCOL_STATE,
            {**build_action_response_payload(
                endpoint="POST /api/games/{}/action".format(self.game_id),
                http_status=http_status,
                decision_id=attempt.decision_id,
                attempt_no=attempt.attempt_no,
                raw=raw_text or "",
            ), "request_timing": {**(request_timing or {}),
                "completed_at_monotonic": self._monotonic()}},
            decision_id=attempt.decision_id,
            attempt_no=attempt.attempt_no,
            trigger_seq=attempt.window_key.trigger_seq,
            round_no=attempt.window_key.round_no,
        )

    def _history_closure_payload(self, reason: str, *, extra_events=()):
        """在换手提交前构造旧手封存数据；尾事件须由调用方证明属于旧手。"""
        snapshot = self._sync.snapshot
        if snapshot is None or snapshot.round_no in self._sealed_history_rounds:
            return None
        history = {e.seq: e for e in self._sync.history}
        closure_issues = set()
        for event in extra_events:
            public = projector.public_event(event)
            if event.type not in KNOWN_EVENT_TYPES:
                closure_issues.add("unknown_snapshot_event")
            if (public.kind == "chi" and len(public.tiles) != 3) or (
                    public.kind in ("gang", "timeout") and public.detail_kind is None):
                closure_issues.add("event_detail_incomplete:" + public.kind)
            if public.kind == "tile_drawn" and public.seat != snapshot.seat:
                if public.tiles:
                    closure_issues.add("unexpected_other_draw")
                public = replace(public, tiles=())
            if public.seq in history and history[public.seq] != public:
                raise DtoError("收尾事件与已有历史冲突")
            history[public.seq] = public
        # 水位以内连续只证明已知区间完整；封存整手还须实际收到终局原事件。
        kinds = {event.kind for event in history.values()}
        if "round_ended" not in kinds:
            closure_issues.add("round_ended_not_observed")
        if (reason == "game_finished" or self._sync.finished) and "game_ended" not in kinds:
            closure_issues.add("game_ended_not_observed")
        through = max([self._sync.last_seq] + list(history))
        floor = self._sync.history_floor_seq
        missing = []
        if floor is not None:
            cursor = floor + 1
            for seq in sorted(seq for seq in history if floor < seq <= through):
                if seq > cursor:
                    missing.append([cursor, seq - 1])
                cursor = seq + 1
            if cursor <= through:
                missing.append([cursor, through])
        try:
            observation = self._sync.current_observation()
            encoded = observation_to_json(observation) if observation is not None else None
        except (ValueError, DtoError):
            encoded = None  # 官方终态可能 turn=-1，不能伪造成可行动的玩家观察
        return {
            "history_closure": reason, "round_no": snapshot.round_no,
            "state_seq": self._sync.last_seq, "snapshot_seq": snapshot.seq,
            "history_through_seq": through,
            "snapshot_phase": snapshot.phase, "scores": list(snapshot.scores),
            "history_origin_known": self._sync.history_origin_known,
            "history_floor_seq": floor,
            "history_complete": self._sync.history_complete and not missing and not closure_issues,
            "closure_issues": sorted(closure_issues),
            "missing_ranges": missing,
            "public_history": [public_event_to_json(history[seq]) for seq in sorted(history)],
            "observation": encoded,
        }

    def _commit_history_closure(self, payload) -> None:
        """新快照确认成功后才提交旧手封存；错误响应不得提前标记旧手已关闭。"""
        if payload is None:
            return
        self._emit_audit(AuditKind.AUTHORITATIVE_STATE, payload,
                         trigger_seq=payload["history_through_seq"], round_no=payload["round_no"])
        self._sealed_history_rounds.add(payload["round_no"])

    def _seal_history(self, reason: str) -> None:
        """高优先级封存本手已知事实与缺口；不为终局伪造一个策略动作窗口。"""
        self._commit_history_closure(self._history_closure_payload(reason))

    async def _get_state(
        self, *, long_poll: bool, force_full: bool = False,
        deadline_monotonic: Optional[float] = None,
        priority: Optional[Priority] = None,
        latest_start_monotonic: Optional[float] = None,
        state_reservation: Optional[StateQueryReservation] = None,
        obsolete_window_end: Optional[float] = None,
        query_purpose: str = "state_sync",
    ) -> StateResponse:
        """一次状态查询：快照立即成为基线，普通查询顺带领取已知历史缺口。

        seq=0 返回当前快照；其水位以内的效果已经包含在牌面中。
        当前活窗先交付，不串行追加补史。后续普通查询可使用历史游标，
        返回的旧事件只合并历史，新事件继续按已消费水位推进。
        """
        # 完成预算与发起截止分离。409由调用方提供原动作预算，不能在过期后
        # 自动跨窗重试；普通阶段刷新可以丢弃旧目的后同步现状。
        explicit_budget = deadline_monotonic is not None
        purpose_started = self._monotonic()
        detected = self._sync.current_window()
        query_window = detected.window_key if detected is not None else None
        if state_reservation is not None:
            latest_start_monotonic = state_reservation.latest_start_at_monotonic
            snapshot = self._sync.snapshot
            if snapshot is not None:
                # 提示针对预期下一吃窗，仅用于查询审计；真实动作权仍须快照确认。
                cycle = self._sync.response_cycle_key
                query_window = WindowKey(
                    game_id=self.game_id, round_no=snapshot.round_no,
                    trigger_seq=cycle[1] if cycle is not None else snapshot.seq,
                    phase=WindowPhase.RESPONSE_CHI, seat=snapshot.seat)
        elif deadline_monotonic is not None and latest_start_monotonic is None:
            latest_start_monotonic = deadline_monotonic - _STATE_RESPONSE_RESERVE_SEC
        elif force_full and deadline_monotonic is None:
            detected = self._sync.incremental_response_window() or self._sync.current_window()
            if detected is not None and not self._gate.is_finalized(detected.window_key):
                timing = self._window_timing(detected)
                obsolete_window_end = timing["expires_at_monotonic"]
                deadline_monotonic = obsolete_window_end - _ACTION_AFTER_STATE_RESERVE_SEC
                latest_start_monotonic = deadline_monotonic - _STATE_RESPONSE_RESERVE_SEC
                query_purpose = "known_window_refresh"
        try:
            return await self._request_state(
                long_poll=long_poll, force_full=force_full,
                deadline_monotonic=deadline_monotonic, priority=priority,
                latest_start_monotonic=latest_start_monotonic,
                state_reservation=state_reservation, query_purpose=query_purpose)
        except _PollFailure as failure:
            if (failure.item.reason != "refresh_deadline"
                    or (explicit_budget and state_reservation is None)):
                raise
            # 旧目的已过最迟安全发起时刻，不能继续排队重试。若旧窗口尚未
            # 结束，等到其边界后只留一次当前快照需求，不积压历次抢窗请求。
            self._emit_audit(AuditKind.AUTHORITATIVE_STATE, {
                "state_query_cancel_reason": "expired_window_purpose",
                "query_purpose": query_purpose,
                "window": window_key_to_json(query_window) if query_window is not None else None,
                "window_is_expected": state_reservation is not None,
                "latest_start_monotonic": latest_start_monotonic,
                "obsolete_window_end_monotonic": obsolete_window_end,
                "purpose_started_at_monotonic": purpose_started,
                # 用途自建立到取消的等待秒数，包含排队、退避及可能的已发尝试。
                "purpose_wait_sec": max(0.0, self._monotonic() - purpose_started),
                "replacement_purpose": "current_state_sync",
                "consumed_seq": self._sync.last_seq,
            }, trigger_seq=query_window.trigger_seq if query_window is not None else self._sync.last_seq,
                round_no=query_window.round_no if query_window is not None else None)
            if state_reservation is not None:
                state_reservation.cancel()
            if obsolete_window_end is not None:
                delay = max(0.0, obsolete_window_end + _BOUNDARY_MARGIN_SEC - self._monotonic())
                if delay:
                    await self._retry_sleep(delay)
            return await self._request_state(
                long_poll=False, force_full=True, query_purpose="current_state_sync")

    async def _request_state(
        self,
        *,
        long_poll: bool,
        force_full: bool = False,
        deadline_monotonic: Optional[float] = None,
        priority: Optional[Priority] = None,
        latest_start_monotonic: Optional[float] = None,
        state_reservation: Optional[StateQueryReservation] = None,
        query_purpose: str = "state_sync",
    ) -> StateResponse:
        """带预算内有界重试的 state 请求；失败升级为 _PollFailure。

        可恢复解析错误（DtoError.recoverable=True，如增量事件负载损坏）在
        重试耗尽前降级一次 seq=0 全量重建——增量损坏大概率可由权威快照修复。
        deadline_monotonic 绑定动作原始预算（409 恢复刷新使用）：预算耗尽
        立即停止重试并按可恢复失败上交，绝不越过 latest_send_at 等待。
        priority 缺省时按 force_full 选 RECOVERY/POLL；边界定时刷新等
        计划性恢复类请求可显式走普通优先级（POLL），不占紧急恢复通道。
        """

        chosen_priority = priority if priority is not None else (
            Priority.RECOVERY if force_full else Priority.POLL
        )
        attempts = 0
        degraded_to_full = False
        while True:
            attempts += 1
            request_timing = {"queued_at_monotonic": self._monotonic(),
                              "query_purpose": query_purpose,
                              "scheduler_priority": chosen_priority.name,
                              "latest_start_monotonic": latest_start_monotonic,
                              "response_deadline_monotonic": deadline_monotonic}
            # 只整形同场连续普通增量长轮询。立即入队，让 50ms 与共享额度
            # 排队重叠；已知期限、摸牌预警、恢复与 seq=0 快照不附加等待。
            ordinary_long_poll = (
                long_poll and not force_full and not degraded_to_full
                and chosen_priority is Priority.DISCARD_WATCH
                and query_purpose == "discard_watch"
                and latest_start_monotonic is None and deadline_monotonic is None
                and self._sync.history_query_seq() > 0
            )
            last_completed = self._last_ordinary_long_poll_completed_at
            not_before = (
                last_completed + self._ordinary_long_poll_min_interval_sec
                if ordinary_long_poll and last_completed is not None
                and self._ordinary_long_poll_min_interval_sec > 0 else None
            )
            if not_before is not None:
                request_timing["ordinary_long_poll_not_before_monotonic"] = not_before
                request_timing["ordinary_long_poll_min_interval_ms"] = (
                    self._ordinary_long_poll_min_interval_sec * 1000
                )
            if latest_start_monotonic is not None and self._monotonic() >= latest_start_monotonic:
                raise _PollFailure(GameFailed(self.game_id, True, "refresh_deadline"), request_sent=False) from None
            try:
                lease = await self._scheduler.acquire(
                    chosen_priority, deadline_monotonic=latest_start_monotonic, request_kind=RequestKind.STATE,
                    not_before_monotonic=not_before, reservation=state_reservation, reserve_only=True,
                )
            except DeadlineExceeded:
                # 冷却/槽竞争在预算内未让出许可：按预算耗尽上交，
                # 409 路径由调用方保守映射 SubmitRejectedNoRefresh
                raise _PollFailure(GameFailed(self.game_id, True, "refresh_deadline"), request_sent=False) from None
            request_timing["granted_at_monotonic"] = self._monotonic()
            # acquire 等待（429 冷却/槽竞争）会消耗预算：拿到 lease 后必须
            # 复查截止并按最新剩余设置读取超时——不得用过期的估算值发请求
            read_timeout: Optional[float] = None
            if deadline_monotonic is not None:
                remaining = deadline_monotonic - self._monotonic()
                if remaining <= 0:
                    lease.release()
                    raise _PollFailure(GameFailed(self.game_id, True, "refresh_deadline"), request_sent=False) from None
                read_timeout = remaining
            try:
                if latest_start_monotonic is not None and self._monotonic() >= latest_start_monotonic:
                    raise _PollFailure(GameFailed(self.game_id, True, "refresh_deadline"), request_sent=False)
                # 发送时同时读取当前状态与历史进度；强制恢复仍必须 seq=0。
                state_seq = self._sync.last_seq
                round_no = self._sync.snapshot.round_no if self._sync.snapshot is not None else None
                seq = 0 if force_full or degraded_to_full else self._sync.history_query_seq()
                recovering_history = 0 < seq < state_seq
                if recovering_history:
                    request_timing["history_after_seq"] = seq
                    request_timing["state_consumed_seq"] = state_seq
                def state_started(at):
                    lease.mark_sent(at)
                    self._last_state_started_at = at
                result = await audited_request(self._transport, self._emit_audit, self._monotonic,
                    "GET",
                    "/api/games/{}/state".format(self.game_id),
                    params={"seq": seq}, timing=request_timing, raw_source=None, on_start=state_started,
                    wall_clock=self._wall_ms,
                    long_poll=long_poll,
                    request_budget_sec=read_timeout,
                )
                self._last_ordinary_long_poll_completed_at = (
                    request_timing["completed_at_monotonic"] if ordinary_long_poll else None
                )
                self._state_request_no += 1
                try:
                    parsed = parse_state_response(_loads(result.text))
                except DtoError:
                    # 坏报文也必须留原文（E1）：seq_observed 未知记 None，
                    # 异常沿原分支继续处理（可恢复降级/重试/终态判定不变）
                    self._emit_raw_state(result, seq, None, request_timing=request_timing)
                    raise
                self._emit_raw_state(result, seq, parsed, request_timing=request_timing)
                if recovering_history:
                    if parsed.kind == "events" and not parsed.gap and parsed.events:
                        newer = self._sync.recover_snapshot_history(
                            parsed.events, after_seq=seq, round_no=round_no)
                        self._emit_audit(AuditKind.AUTHORITATIVE_STATE, {
                            "history_recovery": "merged", "requested_seq": seq,
                            "state_consumed_seq": state_seq,
                            "recovered_through_seq": min(state_seq, max(e.seq for e in parsed.events)),
                            "remaining_ranges": [list(r) for r in self._sync.history_missing_ranges()],
                        }, trigger_seq=state_seq, round_no=round_no)
                        # 原文已完整审计。旧 chi/gang 不再触发牌面刷新或重复窗口。
                        parsed = replace(parsed, events=newer)
                    else:
                        through = max(state_seq, parsed.snapshot.seq if parsed.snapshot is not None else state_seq)
                        self._sync.abandon_history_query(through)
                        self._emit_audit(AuditKind.AUTHORITATIVE_STATE, {
                            "history_recovery": "unavailable", "requested_seq": seq,
                            "abandoned_through_seq": through, "response_kind": parsed.kind,
                            "gap": parsed.gap,
                        }, trigger_seq=state_seq, round_no=round_no)
                # 旧事件或补史pending不能证明当前水位形成于本次请求时刻。
                # 保留原时间下界，避免给随后发现的新动作延长估算预算。
                self._last_state_history_only = (
                    recovering_history and parsed.kind in ("pending", "events") and not parsed.events)
                self._last_clock_response = (parsed, request_timing["transport_started_at_monotonic"],
                                             request_timing["completed_at_monotonic"])
                return parsed
            except asyncio.CancelledError:
                self._emit_raw_state_error(UncertainTransportError("cancelled"), seq, request_timing=request_timing)
                raise
            except RateLimitedError as exc:
                retry_after = exc.retry_after_seconds
                request_timing["retry_after_seconds"] = (retry_after if retry_after is not None
                    and math.isfinite(retry_after) and retry_after >= 0 else None)
                # F-05：非 2xx 响应原文（限速拒绝体等诊断证据）也落审计，
                # request_no 不递增（只随成功计数，连续性检查不受影响）
                self._emit_raw_state_error(exc, seq, request_timing=request_timing)
                self._scheduler.note_rate_limited(exc.retry_after_seconds, request_kind=RequestKind.STATE)
            except (UncertainTransportError, RecoverableServerError) as exc:
                # 超时/断连无响应体：raw="" + http_status=None 记录"原文不存在"
                self._emit_raw_state_error(exc, seq, request_timing=request_timing)
            except AuthError as exc:
                self._emit_raw_state_error(exc, seq, request_timing=request_timing)
                raise _PollFailure(GameFailed(self.game_id, False, "authentication_failed")) from None
            except ForbiddenError as exc:
                self._emit_raw_state_error(exc, seq, request_timing=request_timing)
                raise _PollFailure(GameFailed(self.game_id, False, "forbidden")) from None
            except NotFoundError as exc:
                self._emit_raw_state_error(exc, seq, request_timing=request_timing)
                raise _PollFailure(GameFailed(self.game_id, True, "game_not_found")) from None
            except BadRequestError as exc:
                self._emit_raw_state_error(exc, seq, request_timing=request_timing)
                raise _PollFailure(GameFailed(self.game_id, False, "bad_request")) from None
            except ConflictError as exc:
                # state GET 不在官方 409 语义内；按不可恢复协议错误终止本场
                self._emit_raw_state_error(exc, seq, request_timing=request_timing)
                raise _PollFailure(GameFailed(self.game_id, False, "state_conflict")) from None
            except OfficialError as exc:
                self._emit_raw_state_error(exc, seq, request_timing=request_timing)
                raise _PollFailure(
                    GameFailed(self.game_id, False, "protocol_error_" + str(exc.http_status))
                ) from None
            except DtoError as exc:
                if recovering_history:
                    self._sync.abandon_history_query(state_seq)
                    self._emit_audit(AuditKind.AUTHORITATIVE_STATE, {
                        "history_recovery": "rejected", "requested_seq": seq,
                        "abandoned_through_seq": state_seq,
                        "reason": "invalid_event_batch",
                    }, trigger_seq=state_seq, round_no=round_no)
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
            delay = self._backoff_base * (2 ** (attempts - 1))
            if latest_start_monotonic is not None:
                delay = min(delay, max(0.0, latest_start_monotonic - self._monotonic()))
            await self._retry_sleep(delay)

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
            outcome = await self._submit_locked(attempt)
        finally:
            self._gate.leave()
        if isinstance(outcome, SubmitAccepted) and self._sse_event is not None:
            # 自唤醒（2026-09-05 r5 取证：暗杠后补牌出牌窗 3 秒被代打）：
            # 服务端对"本人动作产生的事件"不推 SSE 帧（杠@341+补牌@342 无帧，
            # 直到 3s 超时代打@344 才有帧）——自己动作被接受后立即唤醒短拉
            # 增量，不等帧/不等 5s 静默周期
            self._sse_wake_pending = True
            self._sse_event.set()
        return outcome

    def _discard_pacing_plan(self, attempt, detected, observation, timing, backlog_delay_sec):
        """普通弃牌按首次见到动作窗缓发；重试和本人特殊动作链直接跳过。"""
        now = self._monotonic()
        if not self._discard_pacing_enabled:
            return DiscardPacing(now, "disabled")
        if attempt.attempt_no != 1:
            return DiscardPacing(now, "retry_attempt")
        if (attempt.window_key.phase is not WindowPhase.DRAW
                or attempt.action.tile == observation.rule_state.wealth_god
                or observation.rule_state.chain_count > 0 or observation.gang_draw is True):
            return DiscardPacing(now, "special_action")
        observed_at = self._window_received_at.get(attempt.window_key)
        if observed_at is None:
            return DiscardPacing(now, "missing_local_observation")
        expiry = timing["expires_at_monotonic"]
        incremental = self._sync.incremental_draw_window()
        if incremental is not None and incremental.window_key == attempt.window_key:
            # 整秒服务端时间可能偏快；保留上一次已知水位的本地时间下界，
            # 不能因快事件迟到而把三秒弃牌窗从本次收包时刻重新起算。
            start_floor = self._event_time_floors.get(attempt.window_key.trigger_seq)
            if start_floor is None and timing["deadline_is_estimated"]:
                return DiscardPacing(now, "missing_local_time_bound")
            if start_floor is not None:
                expiry = min(expiry, start_floor + detected.timeout_seconds)
        elif timing["deadline_is_estimated"]:
            # 快照恢复后的窗口若无官方截止，无法证明还剩0.5秒安全等待。
            return DiscardPacing(now, "snapshot_estimated_deadline")
        return plan_discard_pacing(
            now=now, observed_at=observed_at,
            expires_lower_bound=expiry,
            latest_send=attempt.latest_send_at_monotonic)

    async def _wait_discard_pacing(self, attempt, plan, state_used, backlog_delay_sec):
        """等到一次性目标；关会话可取消，等待不占HTTP槽或state额度。"""
        started = self._monotonic()
        payload = {"discard_pacing_status": "scheduled", "reason": plan.reason,
                   "target_at_monotonic": plan.target_at_monotonic,
                   "started_at_monotonic": started, "state_used": state_used,
                   "state_backlog_delay_sec": backlog_delay_sec,
                   "latest_send_at_monotonic": attempt.latest_send_at_monotonic}
        context = dict(decision_id=attempt.decision_id, attempt_no=attempt.attempt_no,
                       trigger_seq=attempt.window_key.trigger_seq, round_no=attempt.window_key.round_no)
        self._emit_audit(AuditKind.AUTHORITATIVE_STATE, payload, **context)
        try:
            while self._monotonic() < plan.target_at_monotonic and not self._closed:
                task = asyncio.ensure_future(self._retry_sleep(plan.target_at_monotonic - self._monotonic()))
                self._active_tasks.add(task)
                try:
                    await task
                finally:
                    self._active_tasks.discard(task)
        except asyncio.CancelledError:
            self._emit_audit(AuditKind.AUTHORITATIVE_STATE, {
                **payload, "discard_pacing_status": "cancelled",
                "waited_sec": max(0.0, self._monotonic() - started)}, **context)
            if not self._closed:
                raise SubmissionCancelledBeforeSend() from None
        else:
            self._emit_audit(AuditKind.AUTHORITATIVE_STATE, {
                **payload, "discard_pacing_status": "completed",
                "waited_sec": max(0.0, self._monotonic() - started)}, **context)

    async def _submit_locked(self, attempt: ActionAttempt, *, pacing_checked: bool = False) -> SubmitOutcome:
        if self._closed:
            return self._finish_submit(attempt, SubmitNotSent("session_closed"))
        detected = self._sync.current_window()
        if detected is None or detected.window_key != attempt.window_key:
            return self._finish_submit(attempt, SubmitNotSent("stale_window"))
        observation = self._sync.current_observation()
        if observation is None:
            return self._finish_submit(attempt, SubmitNotSent("stale_window"))
        # 网络余量从会话截止扣一次，再与调用方预算取最小值；不能从
        # 已扣网络的attempt截止再扣一次。保留固定余量也保护过宽调用方。
        timing = self._window_timing(detected)
        attempt = replace(attempt, latest_send_at_monotonic=min(
            attempt.latest_send_at_monotonic,
            timing["expires_at_monotonic"] - DEFAULT_POST_NETWORK_RESERVE_SEC))
        body = projector.action_request_body(
            attempt.action,
            last_discard_tile=observation.last_discard.tile if observation.last_discard else None,
            hand=observation.my_hand,
            drawn_tile=observation.drawn_tile,
            catch_play=analyze_catch_play(observation).restricts(observation.seat),
            phase=attempt.window_key.phase,
            responding=attempt.window_key.seat in observation.responding_seats,
        )
        if body is None:
            return self._finish_submit(attempt, SubmitNotSent("malformed_action_body"))
        if self._monotonic() >= attempt.latest_send_at_monotonic:
            return self._finish_submit(attempt, SubmitNotSent("deadline_passed"))
        # 碰阶段的过只表示本阶段无动作；不提前向官方声明整个响应周期放弃。
        # 等官方真实吃阶段再提交，避免依赖“peng pass 后还能 chi”的未确认语义。
        if isinstance(attempt.action, Pass) and attempt.window_key.phase is WindowPhase.RESPONSE_PENG:
            return self._finish_submit(attempt, SubmitNotSent("pass_deferred_until_chi"))
        if not pacing_checked and isinstance(attempt.action, Discard):
            state_used = self._scheduler.state_used_count
            backlog_delay_sec = self._scheduler.state_backlog_delay_sec
            plan = self._discard_pacing_plan(
                attempt, detected, observation, timing, backlog_delay_sec)
            if plan.target_at_monotonic > self._monotonic():
                attempt = replace(attempt, latest_send_at_monotonic=plan.latest_send_at_monotonic)
                await self._wait_discard_pacing(attempt, plan, state_used, backlog_delay_sec)
                # 等待期间可能关场、窗口迁移或期限收紧；重新校验且不再补时。
                return await self._submit_locked(attempt, pacing_checked=True)
            self._emit_audit(AuditKind.AUTHORITATIVE_STATE, {
                "discard_pacing_status": "skipped", "reason": plan.reason,
                "state_used": state_used,
                "state_backlog_delay_sec": backlog_delay_sec}, decision_id=attempt.decision_id,
                attempt_no=attempt.attempt_no, trigger_seq=attempt.window_key.trigger_seq,
                round_no=attempt.window_key.round_no)
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
        request_timing = {"queued_at_monotonic": self._monotonic()}
        try:
            lease = await self._scheduler.acquire(
                Priority.ACTION, deadline_monotonic=attempt.latest_send_at_monotonic, request_kind=RequestKind.OTHER
            )
        except DeadlineExceeded:
            # 本场冷却/槽竞争未在预算内让出许可：POST 从未发出，
            # 按未发送处理，保证 GameTask 不在冷却上阻塞到预算外
            return self._finish_submit(attempt, SubmitNotSent("deadline_passed_in_schedule"))
        request_timing["granted_at_monotonic"] = self._monotonic()
        try:
            current = self._sync.current_window()
            if self._closed or current is None or current.window_key != attempt.window_key:
                return self._finish_submit(attempt, SubmitNotSent("session_closed" if self._closed else "stale_window"))
            if self._monotonic() >= attempt.latest_send_at_monotonic:
                # 调度等待可能耗时；越过截止时间一律不再发出 POST
                return self._finish_submit(attempt, SubmitNotSent("deadline_passed_after_schedule"))
            try:
                request_timing["transport_started_at_monotonic"] = self._monotonic()
                result = await audited_request(self._transport, self._emit_audit, self._monotonic,
                    "POST",
                    "/api/games/{}/action".format(self.game_id),
                    json_body=body, timing=request_timing, raw_source=None,
                    wall_clock=self._wall_ms,
                )
            except ConflictError as exc:
                # 409 已确认动作未执行：先释放动作槽再刷新，避免在持有
                # ACTION lease 时嵌套等待 RECOVERY 槽造成调度自锁；
                # 拒绝体原文在释放动作槽前落审计（E3）
                self._emit_raw_action(exc.http_status, exc.raw_text, attempt, request_timing=request_timing)
                lease.release()
                outcome = await self._handle_conflict(attempt, exc)
                return self._finish_submit(attempt, outcome)
            except AuthError as exc:
                self._emit_raw_action(exc.http_status, exc.raw_text, attempt, request_timing=request_timing)
                return self._finish_submit(
                    attempt,
                    SubmitFatal(exc.official_code, "authentication_failed"),
                )
            except ForbiddenError as exc:
                self._emit_raw_action(exc.http_status, exc.raw_text, attempt, request_timing=request_timing)
                return self._finish_submit(attempt, SubmitFatal(exc.official_code, "forbidden"))
            except RateLimitedError as exc:
                self._scheduler.note_rate_limited(exc.retry_after_seconds, request_kind=RequestKind.OTHER)
                self._emit_raw_action(exc.http_status, exc.raw_text, attempt, request_timing=request_timing)
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
                # 响应从未到达：http_status=None + raw="" 记录"原文不存在"，
                # 对账不悬空（E3；验证器按 SubmitAmbiguous 语义要求该键存在）
                self._emit_raw_action(None, "", attempt, request_timing=request_timing)
                return self._finish_submit(attempt, self._block_ambiguous(attempt, exc.detail))
            except RecoverableServerError as exc:
                self._emit_raw_action(exc.http_status, exc.raw_text, attempt, request_timing=request_timing)
                return self._finish_submit(attempt, self._block_ambiguous(attempt, "server_error_" + str(exc.http_status)))
            except BadRequestError as exc:
                # 400（如 TOKEN_NOT_SCOPED）：请求/作用域配置错误，重试无意义
                self._emit_raw_action(exc.http_status, exc.raw_text, attempt, request_timing=request_timing)
                return self._finish_submit(attempt, SubmitFatal(exc.official_code, "bad_request"))
            except NotFoundError as exc:
                # 404：官方明确未执行动作且窗口必然失效；身份未坏，
                # 后续 next_item 的可恢复 game_not_found 会触发重新发现。
                # 门同步终结：窗口关闭后同窗不再接受任何提交
                self._emit_raw_action(exc.http_status, exc.raw_text, attempt, request_timing=request_timing)
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
                self._emit_raw_action(exc.http_status, exc.raw_text, attempt, request_timing=request_timing)
                return self._finish_submit(
                    attempt,
                    SubmitFatal(exc.official_code, "protocol_error_" + str(exc.http_status)),
                )
            except asyncio.CancelledError:
                # POST 可能已发出且结果未知：按模糊语义封锁同窗，杜绝非幂等双发；
                # 取消本身继续向外传播（不吞调用方的取消请求）
                self._emit_raw_action(None, "", attempt, request_timing=request_timing)
                self._gate.block(attempt.window_key)
                self._emit_audit(
                    AuditKind.SUBMISSION_OUTCOME,
                    {
                        "decision_id": attempt.decision_id,
                        "attempt_no": attempt.attempt_no,
                        "action_key": attempt.action_key,
                        "outcome_type": "SubmitAmbiguous",
                        "reason": SUBMISSION_CANCELLED_IN_FLIGHT,
                    },
                    decision_id=attempt.decision_id,
                    attempt_no=attempt.attempt_no,
                    trigger_seq=attempt.window_key.trigger_seq,
                    round_no=attempt.window_key.round_no,
                )
                raise
            self._emit_raw_action(result.status, result.text, attempt, request_timing=request_timing)
            self._gate.mark_accepted(attempt.window_key)
            self._sync.note_accepted_action(attempt.action, observation)
            if attempt.action_key == "pass":
                # 本人 pass 被官方接受：本响应周期对我关闭（pass 覆盖
                # peng+chi 两窗——2026-09-05 取证），登记以抑制后续投递（F2）
                self._sync.note_self_response()
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
                # 与 _maybe_deliver_window 同口径：authoritative_seq 必须等于
                # observation.snapshot_seq（契约校验），响应窗口 trigger_seq
                # 稳定为触发弃牌序号后二者不再恒等。
                authoritative_seq=observation.snapshot_seq,
                received_at_monotonic=self._monotonic(),
                timeout_seconds=detected.timeout_seconds,
                **self._window_timing(detected),
            )
            if attempt.action_key == "pass":
                # F3（2026-09-05 取证修复）：本人 pass 被 409 = 官方确认我
                # 已对本响应周期表态（pass 覆盖 peng+chi）。改提"下一个
                # pass"只会再吃 409——按"本窗对我关闭"收口并登记表态，
                # 抑制后续重复投递
                self._sync.note_self_response()
                self._gate.mark_closed(attempt.window_key)
                return SubmitRejectedClosed(
                    official_code=error.official_code or "INVALID_ACTION",
                    latest_authoritative_seq=self._sync.last_seq,
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

    def __init__(self, item: GameFailed, *, request_sent: bool = True) -> None:
        self.item = item
        self.request_sent = request_sent  # False：尚未调用传输层，区分排队超时与已发请求失败
        super().__init__(item.reason)


def _loads(text: str) -> Any:
    import json

    try:
        return json.loads(text)
    except ValueError:
        raise DtoError("state 响应不是合法 JSON", recoverable=True) from None
