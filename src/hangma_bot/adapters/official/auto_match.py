"""官方自动匹配会话：TournamentSessionPort 的自动匹配（AUTO_MATCH）实现。

协议依据：API 文档 §2.6（POST /api/match，v12 起，v13 全自动语义，v15 默认
配置上调 M=10/Rounds=8）+ 指南 v15 快照（抓取 2026-09-05）。本会话是
TournamentSessionPort 的第二个真实实现（parallel-v1 §3.3 受控扩展）：

- 只接受全局 Token（/api/me.tournament_id 为空）；报名 Token 直接停止；
- ``initialize`` 只服务 ``RuntimeMode.AUTO_MATCH``：目标为空且确认无已有
  自动房归属时，完成一次显式 POST /api/match 入席（受控副作用例外，见接口
  协议 §6 与 SessionBootstrap 注释）；目标非空时只恢复该已知自动房，绝不
  调用 match；
- ``register``/``ready`` 本地拒绝（直接抛 RuntimeError），HTTP 请求数为 0；
  自动房唯一入席入口是 match（对自动房玩家 API 直连 register/ready，官方
  返回 409 AUTO_MATCH_ONLY）；
- ``next_update`` 对房间 finished/closed/void 一律返回普通变化快照，参赛者
  终态判定归 application（AutoMatchRuntime）；只有协议/身份/目标错误才返回
  ``ParticipantTerminal`` 分类故障；
- 房间 finished 后官方约 60 秒宽限再关闭，关闭后该房玩家接口 404：本会话在
  已确认 finished 证据后把 404 合成 closed 变化快照收尾；无 finished 证据的
  404 按恢复证据不足停止（MATCHING_UNAVAILABLE），不伪造完赛。
"""

from __future__ import annotations

import asyncio
import json
from collections import deque
from dataclasses import dataclass, replace
from typing import Any, Callable, Dict, Mapping, Optional, Tuple, Union

from hangma_bot.application.contracts import (
    AuditContext,
    AuditKind,
    AuditRecord,
    AuditSink,
    GameSessionPort,
    GuideVersion,
    InitializeOutcome,
    ParticipantTerminal,
    ParticipantTerminalReason,
    ReadyOutcome,
    RegistrationOutcome,
    RuntimeMode,
    RuntimeTarget,
    SessionBootstrap,
    StageIdentity,
    TournamentSessionPort,
    TournamentSnapshot,
    TournamentStatus,
)
from hangma_bot.kernel.config import TournamentConfig

from .request_audit import audited_request
from . import projector
from .dto import (
    parse_guide_version,
    parse_me,
    parse_rules_config,
    parse_tournament_detail,
)
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
    sanitize,
)
from .game import OfficialGameSession
from .notify import StreamBudget
from .scheduler import (DEFAULT_PRODUCTION_STATE_BURST, DEFAULT_PRODUCTION_STATE_MIN_SPACING_SEC,
                        DEFAULT_STATE_ARRIVAL_GUARD_SEC,
                        Priority, RequestKind, RequestScheduler)
from .transport import OfficialTransport, TransportConfig

_FAST_GAME_START_POLL_SEC = 0.25  # 匹配完成前仅快速检查 /api/me；秒
_TOURNAMENT_GONE_MAX_ATTEMPTS = 8  # v35 暂态 404 的单次调用上限，含首次请求

# 服务端 v15 自动房默认配置（API 文档 §2.6，抓取 2026-09-05）：显式声明上限
# 低于服务默认（M∈1..9 或 Rounds∈1..7）→ 永久 404 NO_ROOM_AVAILABLE。客户端
# 在同一次操作开始前就拦截，避免白费每分钟配额；服务端默认上调属 breaking
# 变更（v15 已审查），更高版本由指南门禁先行拦截。
SERVER_DEFAULT_MAX_GAMES = 10
SERVER_DEFAULT_ROUNDS = 8

# 本会话需要按码分类、但 errors.py 白名单尚未登记（主审集成扩展，见
# handoff free-match.md）的官方错误码。白名单落地前 _match_error_code 在
# 已脱敏正文中匹配这些字面量（detail 上限 300 字符，官方错误体把 code 放在
# JSON 开头）；只有显式声明低于服务默认才永久 404，其余 NO_ROOM_AVAILABLE
# 是建房后入席失败的瞬态兜底，官方以 message 明示原因。
_MATCH_OFFICIAL_CODES = (
    "NO_ROOM_AVAILABLE",
    "MATCH_BUSY",
    "MATCH_LIMIT_REACHED",
    "AUTO_MATCH_ONLY",
    "TOKEN_NOT_SCOPED",
)

# 一次 match 操作重试参数的默认值（时间单位：秒）。
DEFAULT_MATCH_MIN_INTERVAL_SEC = 6.5  # 官方限速 10 次/分/用户 → ≥6s/次并留余量
DEFAULT_MATCH_MAX_ATTEMPTS = 5
DEFAULT_MATCH_BUSY_WAIT_CAP_SEC = 60.0

# 官方自动匹配限速（指南 v15，抓取 2026-09-05）：10 次/分/用户。以下把
# 配额语义固定为常量，不允许配置下调（防击穿）：
# - 任意滑动 60 秒窗口内实际发出的 match POST 至多 QUOTA_MAX_CALLS 次；
# - 相邻 POST 稳态间隔下限 MIN_MATCH_INTERVAL_SEC（= 60s/10 次），默认值
#   DEFAULT_MATCH_MIN_INTERVAL_SEC 再留约 8% 余量；配置只能上调下限。
QUOTA_WINDOW_SEC = 60.0
QUOTA_MAX_CALLS = 10
MIN_MATCH_INTERVAL_SEC = 6.0


def _match_error_code(exc: OfficialError) -> Optional[str]:
    """取出可分类的官方错误码。

    优先使用 ``OfficialError.official_code``（errors.py 白名单）；白名单扩展
    落地前，回退到在已脱敏的 detail 正文中精确匹配官方码字面量（只作过渡
    兜底，见 _MATCH_OFFICIAL_CODES 注释）。
    """

    if exc.official_code is not None:
        return exc.official_code
    if exc.detail:
        for code in _MATCH_OFFICIAL_CODES:
            if code in exc.detail:
                return code
    return None


@dataclass(frozen=True)
class _MatchResult:
    """POST /api/match 成功响应的最小解析结果。

    round_no 保持官方原文，只作关联/审计记录，绝不当成单局号使用；
    config 是响应回显的房间配置（可选，留审计）；运行配置以房间详情内嵌
    config 为准——自动房没有 rules 端点（活场实测 404 NOT_FOUND "bad path"，
    2026-09-06）。
    """

    room_id: str
    round_no: Optional[int]
    config: Optional[Mapping[str, Any]]


@dataclass(frozen=True)
class _Registration:
    """一次初始化确认的房间归属；全部字段为已核实事实，不存放占位。"""

    guide: GuideVersion
    participant_id: str
    room_id: str  # 官方自动房 id；SessionBootstrap.tournament_id 的取值
    config: TournamentConfig
    match_round_no: Optional[int]
    match_response_config: Optional[Mapping[str, Any]]


class OfficialAutoMatchSession:
    """全局 Token 的一次自动匹配房会话；aclose 释放该 Token 全部连接资源。

    一个实例只完成一次自动房操作（initialize→运行/停止），不在适配器内循环
    参加下一间房；是否开始下一次操作由 application/运行入口决定。部署约束：
    同一个全局 Token 只能由一个节点的一个进程持有。
    """

    def __init__(
        self,
        *,
        token: str,
        transport_config: TransportConfig,
        monotonic_clock: Callable[[], float],
        wall_clock_unix_ms: Callable[[], int],
        audit: Optional[AuditSink] = None,
        audit_context: Optional[Callable[[], AuditContext]] = None,
        ruleset_version: str = "hangma-mvp-v1",  # 本地规则语义版本，非官方字段
        room_poll_interval_sec: float = 2.0,
        max_retries: int = 3,
        retry_backoff_base_sec: float = 0.3,
        scheduler: Optional[RequestScheduler] = None,
        retry_sleep: Optional[Callable[[float], Any]] = None,
        sse_enabled: bool = False,  # SSE 帧驱动开关（透传给每场会话）
        sse_budget: Optional[StreamBudget] = None,  # 每 Token 共享 SSE 预算
        discard_pacing_enabled: bool = True,  # 独立弃牌缓发开关，不随 SSE 隐式变化
        # ---- 自动匹配操作参数（运行配置注入；不是官方字段） ----
        declared_max_games: int = 0,  # 请求体声明的可承受 M；0 = 不声明（不限）
        declared_rounds: int = 0,  # 请求体声明的可承受 Rounds；0 = 不声明
        match_min_interval_sec: float = DEFAULT_MATCH_MIN_INTERVAL_SEC,
        match_max_attempts: int = DEFAULT_MATCH_MAX_ATTEMPTS,
        match_busy_wait_cap_sec: float = DEFAULT_MATCH_BUSY_WAIT_CAP_SEC,
    ) -> None:
        if declared_max_games < 0 or declared_rounds < 0:
            raise ValueError("声明上限不得为负（0 = 不声明）")
        if match_min_interval_sec < MIN_MATCH_INTERVAL_SEC:
            # 官方 10 次/分配额的下限换算值是 6s/次；配置只能上调不能下调
            # （下调即击穿配额，默认 6.5s 已留余量）。
            raise ValueError(
                "match_min_interval_sec 不得低于官方配额下限 {:.1f}s".format(
                    MIN_MATCH_INTERVAL_SEC
                )
            )
        if match_max_attempts < 1 or match_busy_wait_cap_sec < 0:
            raise ValueError("匹配重试参数不合法")
        self._transport = OfficialTransport(token, transport_config)
        # 匹配/赛事控制独享连接槽，各场共享用户16/s状态账；新账先跨过
        # 旧进程可能留下的一秒计数窗口，不按config.M静态平分查询次数。
        self._scheduler = scheduler if scheduler is not None else RequestScheduler(
            clock=monotonic_clock, sleep=retry_sleep if retry_sleep is not None else asyncio.sleep,
            max_concurrent=2, state_startup_delay_sec=1.0,
            burst=DEFAULT_PRODUCTION_STATE_BURST,
            state_arrival_guard_sec=DEFAULT_STATE_ARRIVAL_GUARD_SEC,
            state_min_spacing_sec=DEFAULT_PRODUCTION_STATE_MIN_SPACING_SEC)
        self._monotonic = monotonic_clock
        self._wall_ms = wall_clock_unix_ms
        self._audit = audit
        self._audit_context = audit_context
        self._ruleset_version = ruleset_version
        self._poll_interval = room_poll_interval_sec
        self._waiting_for_games = False
        self._max_retries = max_retries
        self._backoff_base = retry_backoff_base_sec
        self._retry_sleep = retry_sleep if retry_sleep is not None else asyncio.sleep
        self._sse_enabled = sse_enabled
        self._sse_budget = sse_budget
        self._discard_pacing_enabled = discard_pacing_enabled
        self._declared_max_games = declared_max_games
        self._declared_rounds = declared_rounds
        self._match_min_interval = match_min_interval_sec
        self._match_max_attempts = match_max_attempts
        self._match_wait_cap = match_busy_wait_cap_sec
        self._match_times: deque = deque()  # 实际发出 match POST 的单调秒时刻（配额窗口）
        self._registration: Optional[_Registration] = None
        self._last_snapshot: Optional[TournamentSnapshot] = None
        self._observed_revision = 0
        self._games: Dict[str, OfficialGameSession] = {}
        self._closed = False
        self._initialized = False
        self.audit_degraded_events = 0  # 审计回执降级计数（诊断用）
        self.audit_dropped_events = 0  # 审计发射异常计数（诊断用）

    # ---------- 审计 ----------

    def _emit_audit(self, kind: AuditKind, payload: Mapping[str, Any]) -> None:
        """非阻塞审计；context/构造/发射的任何失败都不进入运行路径。"""

        if self._audit is None or self._audit_context is None:
            return
        try:
            context = self._audit_context()
            record = AuditRecord(
                schema_version=1,
                kind=kind,
                context=context,
                wall_time_unix_ms=self._wall_ms(),
                monotonic_ns=int(self._monotonic() * 1e9),
                payload=dict(payload),
            )
            receipt = self._audit.emit(record)
            if receipt is not None and receipt.audit_degraded:
                self.audit_degraded_events += 1
        except Exception:  # noqa: BLE001 - 审计失败绝不阻塞初始化/终态路径
            self.audit_dropped_events += 1

    def _emit_auto_lifecycle(self, event: str, **fields: Any) -> None:
        """发射 area=auto_match 生命周期事件（词表见 handoff free-match.md）。"""

        payload: Dict[str, Any] = {"area": "auto_match", "event": event}
        payload.update(fields)
        self._emit_audit(AuditKind.LIFECYCLE_CHANGED, payload)

    def _emit_auto_recovery(self, *, reason: str, **fields: Any) -> None:
        """发射 area=auto_match 协议恢复/诊断事件；room_id 等未知字段为空。"""

        payload: Dict[str, Any] = {"area": "auto_match", "reason": reason}
        payload.update(fields)
        self._emit_audit(AuditKind.PROTOCOL_RECOVERED, payload)

    # ---------- HTTP 帮助 ----------

    async def _request_with_retry(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[Mapping[str, Any]] = None,
        priority: Priority = Priority.BACKGROUND,
        with_auth: bool = True,
    ) -> Any:
        """有界重试的 JSON 请求；返回解析后的 JSON 对象（与旧会话同口径）。"""

        attempts = 0
        last_exc: Optional[BaseException] = None
        while True:
            attempts += 1
            try:
                lease = await self._scheduler.acquire(priority, request_kind=RequestKind.OTHER)
                try:
                    result = await audited_request(self._transport, self._emit_audit, self._monotonic,
                        method, path, json_body=json_body, with_auth=with_auth
                    )
                finally:
                    lease.release()
                return json.loads(result.text)
            except RateLimitedError as exc:
                self._scheduler.note_rate_limited(exc.retry_after_seconds, request_kind=RequestKind.OTHER)
                last_exc = exc
            except (UncertainTransportError, RecoverableServerError) as exc:
                last_exc = exc
            except NotFoundError as exc:
                detail_get = (method == "GET" and path.startswith("/api/tournaments/")
                              and path.count("/") == 3)
                if exc.official_code != "TOURNAMENT_GONE" or not detail_get:
                    raise
                # 仅赛事详情 GET 的明确暂态 404 重读；每次间隔房详情
                # 轮询周期。耗尽后保留 GONE 原码交调用方，不伪造永久消失。
                self._emit_auto_recovery(
                    reason="room_temporarily_unavailable",
                    official_code=exc.official_code,
                    path=path,
                )
                if attempts >= _TOURNAMENT_GONE_MAX_ATTEMPTS:
                    raise
                await self._retry_sleep(self._poll_interval)
                continue
            if attempts > self._max_retries:
                if last_exc is not None:
                    raise last_exc
                raise OfficialError(None, None, "retry_exhausted_without_error")
            await self._retry_sleep(self._backoff_base * (2 ** (attempts - 1)))

    async def _get_me(self) -> Any:
        """GET /api/me 原始 JSON；401 归 AuthError，其余交由调用方分类。"""

        return await self._request_with_retry("GET", "/api/me", priority=Priority.RECOVERY)

    # ---------- TournamentSessionPort ----------

    async def initialize(self, target: RuntimeTarget) -> InitializeOutcome:
        """发现并（空目标时）入席一次自动房；成功返回已核实 room_id 的引导。

        AUTO_MATCH 模式的受控副作用例外：目标为空、Token 为全局且无活动
        归属时才允许 POST /api/match；同一次操作的协议恢复有界（配额与尝试
        上限），恢复非空目标绝不调用 match。任何失败返回分类终态。
        """

        if self._initialized:
            raise RuntimeError("OfficialAutoMatchSession.initialize 只能调用一次")
        if target.mode is not RuntimeMode.AUTO_MATCH:
            raise ValueError("OfficialAutoMatchSession 只服务 RuntimeMode.AUTO_MATCH")
        self._initialized = True

        try:
            guide_raw = await self._request_with_retry(
                "GET", "/portal/api/guide/version", priority=Priority.BACKGROUND, with_auth=False
            )
            guide_parsed = parse_guide_version(guide_raw, auto_match=True)
        except AuthError:
            return self._terminal(ParticipantTerminalReason.AUTHENTICATION_FAILED, "guide/version 401")
        except (OfficialError, DtoError, ValueError) as exc:
            return self._terminal(
                ParticipantTerminalReason.FATAL_PROTOCOL_ERROR, "guide/version: " + str(exc)[:120]
            )
        if guide_parsed.has_unknown_breaking_change:
            return self._terminal(
                ParticipantTerminalReason.INCOMPATIBLE_GUIDE,
                "指南 v{} 存在未审查 breaking 变更".format(guide_parsed.version),
            )
        guide = projector.guide_version(guide_parsed)

        try:
            me = parse_me(await self._get_me())
        except AuthError:
            return self._terminal(ParticipantTerminalReason.AUTHENTICATION_FAILED, "/api/me 401")
        except (OfficialError, DtoError, ValueError) as exc:
            return self._terminal(
                ParticipantTerminalReason.FATAL_PROTOCOL_ERROR, "/api/me: " + str(exc)[:120]
            )
        if me.tournament_id:
            # 报名 Token 不能调用 match（官方 400 TOKEN_NOT_SCOPED）；本地先行
            # 拦截，不消费配额也不换凭证。
            return self._terminal(
                ParticipantTerminalReason.TARGET_MISMATCH,
                "自动匹配只接受全局 Token；当前 Token 绑定赛事 {}".format(me.tournament_id),
            )

        if not target.expected_tournament_id:
            # 发现模式：确认无活动归属才允许一次 match（防止与其它进程/已丢失
            # 会话抢占第二个房间）。active_games 无法归属到房间（官方没有
            # game→room 映射端点），有活动场次就缺恢复证据，按契约停止。
            if me.active_games:
                return self._terminal(
                    ParticipantTerminalReason.MATCHING_UNAVAILABLE,
                    "全局 Token 已有 {} 场进行中且缺少可确认的自动房 room_id；"
                    "请以已知 room_id 显式恢复，禁止凭 game_id 猜房再 match".format(len(me.active_games)),
                )
            terminal_or_room = await self._match_operation()
            if isinstance(terminal_or_room, ParticipantTerminal):
                return terminal_or_room
            room_id = terminal_or_room
        else:
            room_id = target.expected_tournament_id  # 恢复模式：不调用 match

        registration = await self._verify_room_and_build(guide, me.user_id, room_id)
        if isinstance(registration, ParticipantTerminal):
            return registration
        self._registration = registration
        self._waiting_for_games = bool(
            self._last_snapshot is not None
            and not self._last_snapshot.active_games
            and self._last_snapshot.status not in (
                TournamentStatus.FINISHED, TournamentStatus.CLOSED, TournamentStatus.VOID,
            )
        )
        self._emit_audit(
            AuditKind.AUTHORITATIVE_STATE,
            {
                "guide_version": guide.version,
                "guide_updated_at": guide.updated_at,
                "room_id": registration.room_id,
                "checked_at": "initialize",
            },
        )
        return SessionBootstrap(
            guide=guide,
            participant_id=registration.participant_id,
            tournament_id=registration.room_id,
            config=registration.config,
            initial_snapshot=self._last_snapshot,
        )

    async def register(self) -> RegistrationOutcome:
        """本地拒绝：自动房不使用报名（官方 409 AUTO_MATCH_ONLY）。"""

        raise RuntimeError(
            "AUTO_MATCH 自动房不使用 register（官方 409 AUTO_MATCH_ONLY）；"
            "本会话本地拒绝，HTTP 请求数为 0"
        )

    async def ready(self, expected_stage: StageIdentity) -> ReadyOutcome:
        """本地拒绝：自动房不使用到位（官方 409 AUTO_MATCH_ONLY）。"""

        raise RuntimeError(
            "AUTO_MATCH 自动房不使用 ready（官方 409 AUTO_MATCH_ONLY）；"
            "本会话本地拒绝，HTTP 请求数为 0"
        )

    async def next_update(self) -> Union[TournamentSnapshot, ParticipantTerminal]:
        """等待房间事实变化；finished/closed/void 返回普通变化快照。

        active_games 取 /api/me.active_games 与房间 my_games 的交集（全局
        Token 可能同时属于其它赛事，交集之外的场次不是本进程可运行集合，
        只做诊断记录）。房间 404：只有此前确认过 finished 才按官方关停语义
        合成 closed 变化快照；否则按恢复证据不足停止。
        """

        reg = self._require_registration()
        exhausted_rounds = 0
        next_detail_at = self._monotonic()
        while not self._closed:
            request_path = "/api/me"
            try:
                me = parse_me(await self._get_me())
                # 身份绑定每轮核验：全局 Token 被改绑为报名 Token 后，其它
                # 赛事的场次不得进入本房快照（与 initialize 同判据）。
                if me.tournament_id:
                    return self._terminal(
                        ParticipantTerminalReason.TARGET_MISMATCH,
                        "Token 绑定漂移：自动匹配要求全局 Token，当前绑定 {}".format(
                            me.tournament_id
                        ),
                    )
                if (self._waiting_for_games and not me.active_games
                        and self._monotonic() < next_detail_at):
                    # 房间详情仍按原间隔检查无场次的终态；场次出现前
                    # 加快 /api/me，避免 2 秒发现间隔吞掉第一张弃牌。
                    await self._retry_sleep(min(self._poll_interval, _FAST_GAME_START_POLL_SEC))
                    continue
                request_path = "/api/tournaments/{}".format(reg.room_id)
                detail_doc = await self._request_with_retry("GET", request_path, priority=Priority.BACKGROUND)
                next_detail_at = self._monotonic() + self._poll_interval
            except AuthError:
                return self._terminal(ParticipantTerminalReason.AUTHENTICATION_FAILED, "next_update 401")
            except NotFoundError as exc:
                if request_path == "/api/me":
                    return self._terminal(
                        ParticipantTerminalReason.FATAL_PROTOCOL_ERROR,
                        "next_update /api/me 404：code={}".format(exc.official_code or "?"),
                    )
                # 房间 404：官方 finished 后约 60 秒关闭的正常形态。只有本进程
                # 已确认过 finished（或已按同样证据合成 closed）才能按"已按
                # 证据收尾"继续；404 本身不能证明正常完赛（API 文档 §2.6）。
                last = self._last_snapshot
                if last is not None and last.status in (
                    TournamentStatus.FINISHED,
                    TournamentStatus.CLOSED,
                ):
                    if last.status is TournamentStatus.FINISHED:
                        closed_snapshot = replace(
                            last,
                            status=TournamentStatus.CLOSED,
                            active_games=(),
                            observed_at_unix_ms=self._wall_ms(),
                            stage=StageIdentity(
                                stage_no=last.stage.stage_no,
                                observed_revision=last.stage.observed_revision + 1,
                            ),
                        )
                        if self._snapshot_changed(closed_snapshot):
                            self._adopt_snapshot(closed_snapshot)
                            return closed_snapshot
                else:
                    if exc.official_code == "TOURNAMENT_GONE":
                        return self._terminal(
                            ParticipantTerminalReason.MATCHING_UNAVAILABLE,
                            "目标房 {} 暂态 TOURNAMENT_GONE 连续读取耗尽：结果仍未知".format(reg.room_id),
                        )
                    return self._terminal(
                        ParticipantTerminalReason.MATCHING_UNAVAILABLE,
                        "目标房 {} 404 且无此前 finished 证据：结果缺失/未知".format(reg.room_id),
                    )
                continue  # 已按既有证据收尾（closed 已交付）：继续轮询等待关停
            except ForbiddenError:
                # 授权类错误不得伪装成可重试网络故障（模块规范）。
                return self._terminal(
                    ParticipantTerminalReason.TARGET_MISMATCH,
                    "房间 {} 拒绝访问（可能已不是本 Token 的入席房）".format(reg.room_id),
                )
            except (RateLimitedError, UncertainTransportError, RecoverableServerError) as exc:
                exhausted_rounds += 1
                prefix = self._exhaustion_prefix(exc)
                if exhausted_rounds >= 5:
                    return self._terminal(
                        ParticipantTerminalReason.FATAL_PROTOCOL_ERROR,
                        "next_update {}: round={} {}".format(prefix, exhausted_rounds, str(exc)[:100]),
                    )
                await self._retry_sleep(self._poll_interval)
                continue
            except (DtoError, ValueError, OfficialError) as exc:
                return self._terminal(
                    ParticipantTerminalReason.FATAL_PROTOCOL_ERROR,
                    "next_update protocol: " + str(exc)[:120],
                )
            exhausted_rounds = 0
            try:
                parsed = parse_tournament_detail(detail_doc)
                snapshot = self._project_snapshot(parsed, me.active_games, reg=reg)
            except (DtoError, ValueError) as exc:
                return self._terminal(
                    ParticipantTerminalReason.FATAL_PROTOCOL_ERROR,
                    "next_update projection: " + str(exc)[:120],
                )
            if self._snapshot_changed(snapshot):
                self._adopt_snapshot(snapshot)
                if snapshot.active_games or snapshot.status in (
                    TournamentStatus.FINISHED, TournamentStatus.CLOSED, TournamentStatus.VOID,
                ):
                    self._waiting_for_games = False
                return snapshot
            await self._retry_sleep(min(self._poll_interval, _FAST_GAME_START_POLL_SEC)
                                    if self._waiting_for_games else self._poll_interval)
        return self._terminal(ParticipantTerminalReason.FATAL_PROTOCOL_ERROR, "session_closed_by_aclose")

    def open_game(self, game_id: str) -> GameSessionPort:
        """创建共享本 Token 传输与限速器的单场会话（复用既有安全路径）。"""

        reg = self._require_registration()
        cached = self._games.get(game_id)
        if cached is not None and not getattr(cached, "closed", False):
            return cached
        if cached is not None:
            del self._games[game_id]
        session = OfficialGameSession(
            game_id=game_id,
            transport=self._transport,
            scheduler=self._scheduler.for_game(game_id, max_games=reg.config.max_games),
            timing=reg.config.timing,
            monotonic_clock=self._monotonic,
            wall_clock_unix_ms=self._wall_ms,
            retry_sleep=self._retry_sleep,
            audit=self._audit,
            audit_context=self._audit_context,
            sse_enabled=self._sse_enabled,
            sse_budget=self._sse_budget,
            discard_pacing_enabled=self._discard_pacing_enabled,
        )
        self._games[game_id] = session
        return session

    async def aclose(self) -> None:
        """取消所有挂起请求并释放当前 Token 的连接池。"""

        self._closed = True
        for session in self._games.values():
            await session.aclose("auto_match_session_closed")
        self._games.clear()
        await self._transport.aclose()

    # ---------- match 操作 ----------

    async def _match_operation(self) -> Union[str, ParticipantTerminal]:
        """完成一次受配额约束的 match 操作；成功返回 room_id，失败返回终态。

        重试策略（API 文档 §2.6 / free-match-start.md §3）：
        - 显式声明上限低于服务默认（M=10/Rounds=8）是永久容量不符，先于任何
          POST 本地拦截为 CAPACITY_LIMIT，不消费每分钟配额；
        - MATCH_BUSY / 瞬态 NO_ROOM_AVAILABLE / 429 有界等待后重试同一次
          匹配，请求间隔至少覆盖 10 次/分配额（滑动窗口 + 余量），遵守
          Retry-After（匹配控制通道冷却）；
        - MATCH_LIMIT_REACHED 停止新增入席（CAPACITY_LIMIT），不帮用户退出
          其他赛事；
        - POST 结果不确定（超时/断连/5xx）不盲目重发：核验身份后按
          MATCHING_UNAVAILABLE 停止，保留恢复信息供下次以已知 room_id 恢复。
        """

        if 0 < self._declared_max_games < SERVER_DEFAULT_MAX_GAMES or (
            0 < self._declared_rounds < SERVER_DEFAULT_ROUNDS
        ):
            return self._terminal(
                ParticipantTerminalReason.CAPACITY_LIMIT,
                "显式声明上限低于服务默认（M={}/Rounds={}）属永久容量不符（官方"
                " 404 NO_ROOM_AVAILABLE）：请把声明提高到默认值以上或改为不声明（0）".format(
                    SERVER_DEFAULT_MAX_GAMES, SERVER_DEFAULT_ROUNDS
                ),
            )
        self._emit_auto_lifecycle(
            "matching_started",
            declared_max_games=self._declared_max_games,
            declared_rounds=self._declared_rounds,
        )
        attempts = 0
        while True:
            attempts += 1
            # 配额（_wait_for_quota）：60s 窗口 ≤10 次实际 POST + 相邻间隔下限
            # min_interval（默认 6.5s，构造时已校验 ≥ 官方 6s/次，防配置击穿）。
            wait_seconds = await self._wait_for_quota()
            # 记录本次实际发出的时刻（含随后被拒绝/重试的尝试：官方按调用计数）。
            self._match_times.append(self._monotonic())
            body: Dict[str, Any] = {}
            if self._declared_max_games > 0:
                body["M"] = self._declared_max_games
            if self._declared_rounds > 0:
                body["Rounds"] = self._declared_rounds
            try:
                lease = await self._scheduler.acquire(Priority.RECOVERY, request_kind=RequestKind.OTHER)
                try:
                    result = await audited_request(self._transport, self._emit_audit, self._monotonic,
                        "POST", "/api/match", json_body=body or None,
                        raw_source="match_response", raw_fields={"attempt": attempts}
                    )
                finally:
                    lease.release()
            except RateLimitedError as exc:
                self._scheduler.note_rate_limited(exc.retry_after_seconds, request_kind=RequestKind.OTHER)
                self._emit_auto_recovery(
                    reason="match_rate_limited_retry",
                    official_code="RATE_LIMITED",
                    attempt_no=attempts,
                    wait_seconds=wait_seconds,
                    room_id="",
                )
            except ConflictError as exc:
                code = _match_error_code(exc)
                if code == "MATCH_LIMIT_REACHED":
                    return self._terminal(
                        ParticipantTerminalReason.CAPACITY_LIMIT,
                        "达到同时 16 场上限（MATCH_LIMIT_REACHED）：停止新增入席，"
                        "报告已有占用与容量；不代用户退出其他赛事",
                    )
                if code == "MATCH_BUSY":
                    self._emit_auto_recovery(
                        reason="match_busy_retry",
                        official_code="MATCH_BUSY",
                        attempt_no=attempts,
                        wait_seconds=wait_seconds,
                        room_id="",
                    )
                else:
                    return self._terminal(
                        ParticipantTerminalReason.MATCHING_UNAVAILABLE,
                        "match 409 无法继续：code={} detail={}".format(
                            code or "?", sanitize(str(exc))[:200]
                        ),
                    )
            except NotFoundError as exc:
                # 声明下限已在本地拦截；到达这里的 404 NO_ROOM_AVAILABLE 是
                # 建房后入席失败的瞬态兜底（官方 message 附原因），有界重试。
                code = _match_error_code(exc)
                if code == "NO_ROOM_AVAILABLE":
                    self._emit_auto_recovery(
                        reason="no_room_retry",
                        official_code="NO_ROOM_AVAILABLE",
                        attempt_no=attempts,
                        wait_seconds=wait_seconds,
                        room_id="",
                    )
                else:
                    return self._terminal(
                        ParticipantTerminalReason.MATCHING_UNAVAILABLE,
                        "match 404：code={} detail={}".format(
                            code or "?", sanitize(str(exc))[:200]
                        ),
                    )
            except ForbiddenError as exc:
                if exc.official_code == "PORTAL_BINDING_REQUIRED":
                    # v24：/api/me 不暴露门户绑定状态，以入口的权威拒绝为准。
                    # 这是身份条件，等待和重试都无法恢复；在途房间恢复不走 match。
                    return self._terminal(
                        ParticipantTerminalReason.TARGET_MISMATCH,
                        "match 403 PORTAL_BINDING_REQUIRED：当前全局 Token 未绑定门户身份；"
                        "请通过门户「我的 AI 身份」取得绑定的全局 Token。此条件不会重试。",
                    )
                if exc.official_code == "FEATURE_DISABLED":
                    # v29：管理面「设置」可全服关闭自由匹配。关闭后新匹配一律
                    # 403 FEATURE_DISABLED——**永久条件**，等待与重试都不会恢复，
                    # 且不是身份/房态问题。必须与 PORTAL_BINDING_REQUIRED 区分，
                    # 否则会把"平台已关功能"误报成"令牌没绑定门户"。
                    # 在途照常：已在房中的用户重调仍 200 返回原房。
                    return self._terminal(
                        ParticipantTerminalReason.MATCHING_UNAVAILABLE,
                        "match 403 FEATURE_DISABLED：平台已关闭自由匹配（管理面开关）；"
                        "这是永久条件，不重试。已在房中的对局不受影响。",
                    )
                return self._terminal(
                    ParticipantTerminalReason.TARGET_MISMATCH,
                    "match 403：code={} detail={}".format(
                        exc.official_code or "?", sanitize(str(exc))[:200]
                    ),
                )
            except BadRequestError as exc:
                code = _match_error_code(exc)
                if code == "TOKEN_NOT_SCOPED":
                    return self._terminal(
                        ParticipantTerminalReason.TARGET_MISMATCH,
                        "match 400 TOKEN_NOT_SCOPED：需要全局 Token",
                    )
                return self._terminal(
                    ParticipantTerminalReason.FATAL_PROTOCOL_ERROR,
                    "match 400：code={} detail={}".format(
                        exc.official_code or "?", sanitize(str(exc))[:200]
                    ),
                )
            except AuthError as exc:
                return self._terminal(ParticipantTerminalReason.AUTHENTICATION_FAILED, "match 401")
            except (UncertainTransportError, RecoverableServerError) as exc:
                # 结果不确定（超时/断连/明确 5xx）不得盲目重发：等待期幂等
                # 不代表运行期也可重发。核验身份归属后按证据不足停止。
                evidence = await self._verify_uncertain_match()
                if evidence is not None:
                    return evidence
                return self._terminal(
                    ParticipantTerminalReason.MATCHING_UNAVAILABLE,
                    "match 结果不确定：{}；已保留恢复信息，请以已知 room_id 恢复".format(
                        sanitize(str(exc))[:200]
                    ),
                )
            except (OfficialError, DtoError, ValueError) as exc:
                return self._terminal(
                    ParticipantTerminalReason.FATAL_PROTOCOL_ERROR,
                    "match: " + sanitize(str(exc))[:200],
                )
            else:
                # 2xx：解析最小事实（room_id 必填），其余未知字段忽略。
                try:
                    parsed = self._parse_match_response(result.text)
                except (DtoError, ValueError) as exc:
                    return self._terminal(
                        ParticipantTerminalReason.MATCHING_UNAVAILABLE,
                        "match 响应无法解析出 room_id：" + str(exc)[:200],
                    )
                self._emit_auto_lifecycle(
                    "matched",
                    room_id=parsed.room_id,
                    match_round_no=parsed.round_no,
                    declared_max_games=self._declared_max_games,
                    declared_rounds=self._declared_rounds,
                )
                return parsed.room_id
            if attempts >= self._match_max_attempts:
                return self._terminal(
                    ParticipantTerminalReason.MATCHING_UNAVAILABLE,
                    "match 重试耗尽：attempts={} 上限={}；保留恢复信息，"
                    "请以已知 room_id 显式恢复".format(attempts, self._match_max_attempts),
                )
            # 有界等待后重试同一次匹配（Retry-After 已计入匹配控制通道冷却）。
            bounded = min(max(self._match_min_interval, wait_seconds or 0.0), self._match_wait_cap)
            if bounded > 0:
                await self._retry_sleep(bounded)

    async def _wait_for_quota(self) -> float:
        """按官方 10 次/分配额等待下一次 match POST；返回实际等待秒数（诊断用）。

        约束（常量定义见模块顶部，任何配置都不能放宽）：
        - 任意 60 秒滑动窗口内实际发出的 POST 至多 10 次（满窗时等到
          窗口最早一次 +60s 之后）；
        - 相邻 POST 间隔 ≥ match_min_interval_sec（构造校验 ≥ 6.0s）。
        等待是配额强制等待，不受 match_busy_wait_cap 截断（后者只约束
        MATCH_BUSY/限速重试的退避）。
        """

        if not self._match_times:
            return 0.0
        now = self._monotonic()
        next_at = 0.0
        if len(self._match_times) >= QUOTA_MAX_CALLS:
            next_at = self._match_times[0] + QUOTA_WINDOW_SEC
        interval_at = self._match_times[-1] + self._match_min_interval
        if interval_at > next_at:
            next_at = interval_at
        remaining = next_at - now
        if remaining <= 0:
            # 窗口已让开：滑出窗口外的旧时刻，避免长进程内无限增长。
            while self._match_times and self._match_times[0] + QUOTA_WINDOW_SEC <= now:
                self._match_times.popleft()
            return 0.0
        await self._retry_sleep(remaining)
        return remaining

    async def _verify_uncertain_match(self) -> Optional[ParticipantTerminal]:
        """match 结果不确定后的身份核验：只做一次只读检查并记录证据。

        返回 None 表示核验本身无异常（是否已入席仍无法确定），调用方按
        MATCHING_UNAVAILABLE 停止；返回终态表示核验发现 401 等硬错误。
        """

        try:
            me = parse_me(await self._get_me())
        except AuthError:
            return self._terminal(ParticipantTerminalReason.AUTHENTICATION_FAILED, "核验 /api/me 401")
        except (OfficialError, DtoError, ValueError) as exc:
            self._emit_auto_recovery(
                reason="match_uncertain_verify_failed",
                official_code="",
                wait_seconds="",
                room_id="",
                detail=sanitize(str(exc))[:200],
            )
            return None
        self._emit_auto_recovery(
            reason="match_uncertain_evidence",
            official_code="",
            wait_seconds="",
            room_id="",
            active_games_count=len(me.active_games),
            tournament_bound=bool(me.tournament_id),
        )
        return None

    def _parse_match_response(self, text: str) -> _MatchResult:
        """解析 match 成功响应；未知扩展字段忽略，只要求可确认的 room_id。"""

        try:
            doc = json.loads(text)
        except ValueError as exc:
            raise DtoError("match 响应非 JSON: " + str(exc)) from None
        if not isinstance(doc, Mapping):
            raise DtoError("match 响应应为对象")
        room_id = doc.get("room_id")
        if not isinstance(room_id, str) or not room_id.strip():
            raise DtoError("match 响应缺少非空 room_id")
        round_no = doc.get("round_no")
        if round_no is not None and (isinstance(round_no, bool) or not isinstance(round_no, int)):
            raise DtoError("match.round_no 应为整数")
        config = doc.get("config")
        if config is not None and not isinstance(config, Mapping):
            raise DtoError("match.config 应为对象")
        return _MatchResult(
            room_id=room_id, round_no=round_no, config=dict(config) if config else None
        )

    # ---------- 房间核验与投影 ----------

    async def _verify_room_and_build(
        self,
        guide: GuideVersion,
        participant_id: str,
        room_id: str,
    ) -> Union[_Registration, ParticipantTerminal]:
        """核验目标房归属与配置并构造注册事实（失败不留半初始化状态）。

        核验项：房间详情可达（本人入席，非参赛者 403）、配置来自详情内嵌
        ``config`` 块（自动房无 rules 端点：活场实测 404 NOT_FOUND "bad path"，
        2026-09-06，config 与 rules 响应同构）、config.Kind=auto（Kind 缺失时
        记录未确认证据但不阻断——全局 Token 只能通过 match 入席，详情可达
        本身已限定自动房）、详情 tournament_id 归属一致；随后投影首张快照。
        """

        try:
            # 自动房无 /rules 端点；配置一律取自房间详情内嵌 config 块。
            detail_doc = await self._request_with_retry(
                "GET", "/api/tournaments/{}".format(room_id), priority=Priority.RECOVERY
            )
        except AuthError:
            return self._terminal(ParticipantTerminalReason.AUTHENTICATION_FAILED, "房间核验 401")
        except NotFoundError as exc:
            if exc.official_code == "TOURNAMENT_GONE":
                return self._terminal(
                    ParticipantTerminalReason.MATCHING_UNAVAILABLE,
                    "房间 {} 暂态 TOURNAMENT_GONE 连续核验耗尽：归属/结果仍未知".format(room_id),
                )
            return self._terminal(
                ParticipantTerminalReason.MATCHING_UNAVAILABLE,
                "房间 {} 不存在/已关闭（code={}）：恢复证据不足".format(
                    room_id, exc.official_code or "?"
                ),
            )
        except ForbiddenError as exc:
            return self._terminal(
                ParticipantTerminalReason.TARGET_MISMATCH,
                "房间 {} 拒绝访问（code={}）：本 Token 未入席或目标不是本人房间".format(
                    room_id, exc.official_code or "?"
                ),
            )
        except (OfficialError, DtoError, ValueError) as exc:
            return self._terminal(
                ParticipantTerminalReason.FATAL_PROTOCOL_ERROR,
                "房间核验失败: " + sanitize(str(exc))[:200],
            )

        if not isinstance(detail_doc, Mapping):
            return self._terminal(ParticipantTerminalReason.FATAL_PROTOCOL_ERROR, "房间详情非对象")
        # 自动房详情把 kind 放在内嵌 config.Kind（活场实测 2026-09-06），
        # 顶层没有 kind 字段。
        room_config_block = detail_doc.get("config")
        kind = room_config_block.get("Kind") if isinstance(room_config_block, Mapping) else None
        if kind is not None and kind != "auto":
            return self._terminal(
                ParticipantTerminalReason.TARGET_MISMATCH,
                "目标 {} 不是自动房（kind={}）：AUTO_MATCH 生命周期不适用于普通赛事".format(
                    room_id, kind
                ),
            )
        if kind is None:
            self._emit_auto_recovery(
                reason="room_kind_unconfirmed",
                official_code="",
                wait_seconds="",
                room_id=room_id,
                detail="房间详情 config 未携带 Kind 字段；全局 Token 只能经 match 入席，按自动房继续",
            )

        try:
            # detail.config 与 rules 响应同构（M/Rounds/BaseScore/YouCaiBiKao/时限）；
            # 自动房实测无 /rules 端点，房间详情 config 是唯一配置来源。
            parsed = parse_rules_config(detail_doc)
            if parsed.tournament_id != room_id:
                return self._terminal(
                    ParticipantTerminalReason.TARGET_MISMATCH,
                    "详情归属 {} 与目标房 {} 不符".format(parsed.tournament_id, room_id),
                )
            if (self._declared_max_games > 0 and parsed.max_games != self._declared_max_games) or (
                self._declared_rounds > 0 and parsed.rounds_per_game != self._declared_rounds
            ):
                # 显式诊断：返回配置与声明不一致时不能静默按某个口径继续。
                self._emit_auto_recovery(
                    reason="room_config_mismatch",
                    official_code="",
                    wait_seconds="",
                    room_id=room_id,
                    declared_max_games=self._declared_max_games,
                    declared_rounds=self._declared_rounds,
                    actual_max_games=parsed.max_games,
                    actual_rounds=parsed.rounds_per_game,
                )
            config = projector.rules_config(parsed, self._ruleset_version)
            parsed_detail = parse_tournament_detail(detail_doc)
            # 核验晚期的 /api/me 刷新：match/核验期间新开场的次可能已出现，
            # 用最新活跃场次与房间 my_games 求交集后投影首张快照。
            me = parse_me(await self._get_me())
            snapshot = self._project_snapshot(
                parsed_detail, me.active_games, room_id=room_id, participant_id=participant_id
            )
        except AuthError:
            return self._terminal(ParticipantTerminalReason.AUTHENTICATION_FAILED, "核验请求 401")
        except ForbiddenError as exc:
            return self._terminal(
                ParticipantTerminalReason.TARGET_MISMATCH,
                "核验请求被拒（code={}）".format(exc.official_code or "?"),
            )
        except NotFoundError as exc:
            return self._terminal(
                ParticipantTerminalReason.MATCHING_UNAVAILABLE,
                "核验请求 404（code={}）：房间可能已关闭".format(exc.official_code or "?"),
            )
        except (OfficialError, DtoError, ValueError) as exc:
            return self._terminal(
                ParticipantTerminalReason.FATAL_PROTOCOL_ERROR,
                "核验请求失败: " + sanitize(str(exc))[:200],
            )

        # 全部成功后才写入状态：失败路径不留下半初始化会话。
        self._adopt_snapshot(snapshot)
        return _Registration(
            guide=guide,
            participant_id=participant_id,
            room_id=room_id,
            config=config,
            match_round_no=None,
            match_response_config=None,
        )

    def _project_snapshot(
        self,
        detail_parsed: Any,
        active_games: Tuple[str, ...],
        *,
        reg: Optional["_Registration"] = None,
        room_id: Optional[str] = None,
        participant_id: Optional[str] = None,
    ) -> TournamentSnapshot:
        """构造候选快照（纯投影）。active_games 只取本房交集并做显式诊断。

        reg 为 None 时（初始化核验期）必须显式传 room_id/participant_id。
        """

        if reg is not None:
            rid = reg.room_id
            pid = reg.participant_id
        else:
            if room_id is None or participant_id is None:
                raise RuntimeError("投影必须提供注册或显式房间身份")
            rid = room_id
            pid = participant_id
        room_my_games = detail_parsed.my_games
        room_active = tuple(g for g in active_games if g in room_my_games)
        foreign = tuple(g for g in active_games if g not in room_my_games)
        if foreign:
            # 全局 Token 其它赛事/会话的进行中场次不进入本房快照；显式诊断。
            self._emit_auto_recovery(
                reason="foreign_active_games_ignored",
                official_code="",
                wait_seconds="",
                room_id=rid,
                ignored_count=len(foreign),
            )
        return projector.tournament_snapshot(
            detail_parsed,
            tournament_id=rid,
            participant_id=pid,
            active_games=room_active,
            observed_revision=self._observed_revision + 1,
            observed_at_unix_ms=self._wall_ms(),
        ).snapshot

    # ---------- 内部 ----------

    def _require_registration(self) -> _Registration:
        if self._registration is None:
            raise RuntimeError("必须先 initialize() 才能调用该方法")
        return self._registration

    def _adopt_snapshot(self, snapshot: TournamentSnapshot) -> None:
        """采纳候选快照：推进修订号、记录最近快照。"""

        self._observed_revision = snapshot.stage.observed_revision
        self._last_snapshot = snapshot

    def _snapshot_changed(self, snapshot: TournamentSnapshot) -> bool:
        last = self._last_snapshot
        if last is None:
            return True
        return (
            last.status != snapshot.status
            or last.stage.stage_no != snapshot.stage.stage_no
            or last.stage_role != snapshot.stage_role
            or last.stage_total != snapshot.stage_total
            or last.qualify_role != snapshot.qualify_role
            or last.stage_crashed != snapshot.stage_crashed
            or last.qualified != snapshot.qualified
            or last.active_games != snapshot.active_games
            or last.my_games != snapshot.my_games
            or last.competition.ranking != snapshot.competition.ranking
        )

    @staticmethod
    def _exhaustion_prefix(exc: Exception) -> str:
        from .errors import RateLimitedError, RecoverableServerError, UncertainTransportError

        if isinstance(exc, RateLimitedError):
            return "rate_limit_exhausted"
        if isinstance(exc, (UncertainTransportError, RecoverableServerError)):
            return "transport_exhausted"
        return "protocol_error"

    def _terminal(
        self,
        reason: ParticipantTerminalReason,
        detail: str,
        last_snapshot: Optional[TournamentSnapshot] = None,
    ) -> ParticipantTerminal:
        """构造分类终态并返回；不在本层发射终态事件。

        matching_stopped / PARTICIPANT_FINISHED 唯一归应用层发射（接口协议
        §7：PARTICIPANT_FINISHED 是 runtime 出口记录）：本层只返回终态值，
        应用层采纳后统一落审计，避免同一终态双层重复（活场实测 2026-09-06
        发现双层重复后修正）。
        """

        snapshot = last_snapshot if last_snapshot is not None else self._last_snapshot
        return ParticipantTerminal(reason=reason, last_snapshot=snapshot, detail=sanitize(detail))
