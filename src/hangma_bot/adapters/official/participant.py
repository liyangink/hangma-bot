"""官方赛事会话：TournamentSessionPort 的官方协议实现（v8 快照 + v9–v15 已审查变更）。

一个实例对应一个 Token：内部恰好创建一个 OfficialTransport 与一个
RequestScheduler，该 Token 的赛事与全部场次共享（接口协议 §6）。

初始化只做发现（版本、身份、目标、规则、初始快照），不报名不到位；
报名/到位/开关场次由应用层决定。初始化网络失败在内部有界重试，
耗尽后返回 ParticipantTerminal(FATAL_PROTOCOL_ERROR)：契约没有可重试
初始化通道，保守终态比静默循环重试更安全（工程取舍，见接口协议 §8）。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Tuple, Union

from hangma_bot.application.contracts import (
    ActionAttempt,
    AuditContext,
    AuditKind,
    AuditRecord,
    AuditSink,
    GameSessionPort,
    GuideVersion,
    InitializeOutcome,
    OperationStatus,
    ParticipantTerminal,
    ParticipantTerminalReason,
    ReadyOutcome,
    ReadyResult,
    RegistrationOutcome,
    RegistrationResult,
    RuntimeTarget,
    SessionBootstrap,
    StageIdentity,
    TournamentSessionPort,
    TournamentSnapshot,
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
from .scheduler import DEFAULT_STATE_ARRIVAL_GUARD_SEC, Priority, RequestKind, RequestScheduler
from .transport import OfficialTransport, TransportConfig


#: 赛事详情端点 GET /api/tournaments/{id} 的偶发 404 容忍次数（2026-09-17 真实平台证据）。
#:
#: 【证据】测试赛事 t_65d538e905c5 于 2026-09-17 18:39—18:45 CST 的正常 2 秒轮询中，
#: 5 次独立运行共命中 4 次：同一端点连续若干次 200 后**单次**返回 404
#: TOURNAMENT_GONE，而同时刻 /api/me 为 200，随后同一端点又恢复 200
#: （命中点在 +100.1s、+8.2s、+125.2s、+38.4s，全部孤立单发）。
#: 因此单次 404 只说明该次读取失败，不足以判定"赛事消失"。
#:
#: 【语义边界】本容忍只改变**尝试次数**，不改变结论：连续耗尽后仍按原有永久
#: 语义终结为 TARGET_MISMATCH。身份绑定与规则归属仍由 /api/me 与
#: /api/tournaments/me/rules 的强校验负责，不受本容忍放宽。
TOURNAMENT_DETAIL_NOT_FOUND_TOLERANCE = 5


@dataclass(frozen=True)
class _Registration:
    """初始化发现结果；不含 Token 原文。"""

    guide: GuideVersion
    participant_id: str
    tournament_id: str
    scoped: bool  # True 表示报名 Token，可使用 /me/* 直达端点
    config: TournamentConfig


class OfficialTournamentSession:
    """单 Token 跨阶段赛事会话；aclose 释放该 Token 的全部连接资源。"""

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
        tournament_poll_interval_sec: float = 2.0,
        max_retries: int = 3,
        retry_backoff_base_sec: float = 0.3,
        scheduler: Optional[RequestScheduler] = None,
        retry_sleep: Optional[Callable[[float], Any]] = None,
        sse_enabled: bool = False,  # SSE 帧驱动开关（透传给每场会话）
        sse_budget: Optional[StreamBudget] = None,  # 每 Token 共享 SSE 预算
    ) -> None:
        self._transport = OfficialTransport(token, transport_config)
        # 控制面独享连接槽，各场共享用户16/s状态账；新账先跨过旧进程
        # 可能留下的一秒计数窗口。初始化控制请求与动作POST无需等待。
        self._scheduler = scheduler if scheduler is not None else RequestScheduler(
            clock=monotonic_clock, sleep=retry_sleep if retry_sleep is not None else asyncio.sleep,
            max_concurrent=2, state_startup_delay_sec=1.0,
            state_arrival_guard_sec=DEFAULT_STATE_ARRIVAL_GUARD_SEC)
        self._monotonic = monotonic_clock
        self._wall_ms = wall_clock_unix_ms
        self._audit = audit
        self._audit_context = audit_context
        self._ruleset_version = ruleset_version
        self._poll_interval = tournament_poll_interval_sec
        self._max_retries = max_retries
        self._backoff_base = retry_backoff_base_sec
        self._sse_enabled = sse_enabled
        self._sse_budget = sse_budget
        self._retry_sleep = retry_sleep if retry_sleep is not None else asyncio.sleep
        self._registration: Optional[_Registration] = None
        self._last_snapshot: Optional[TournamentSnapshot] = None
        self._observed_revision = 0
        self._games: Dict[str, OfficialGameSession] = {}
        self._closed = False
        self._guide_checked_revisions = set()  # 已做过版本门检查的观察修订号
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
        except Exception:
            # 审计失败绝不阻塞初始化/报名/到位/终态等关键路径
            self.audit_dropped_events += 1

    def _base_context(self) -> AuditContext:
        if self._audit_context is None:
            raise RuntimeError("审计上下文未配置")
        return self._audit_context()

    # ---------- HTTP 帮助 ----------

    async def _tournament_detail(self, tournament_id: str, *, priority: Priority) -> Any:
        """读取赛事详情；偶发 404 有界重试后才上抛，其余异常原样透传。

        为什么不能一见 404 就判"赛事消失"：见模块常量
        TOURNAMENT_DETAIL_NOT_FOUND_TOLERANCE 记录的真实平台证据——
        同一端点前后请求均 200、中间单次 404，属平台侧瞬时读取失败。
        每次容忍都发一条 PROTOCOL_RECOVERED 审计，让"忽略过哪些 404"
        可回放；重试间隔用赛事轮询间隔，不额外占用请求额度。
        """

        last: Optional[NotFoundError] = None
        for attempt in range(1, TOURNAMENT_DETAIL_NOT_FOUND_TOLERANCE + 1):
            try:
                return await self._request_with_retry(
                    "GET",
                    "/api/tournaments/{}".format(tournament_id),
                    priority=priority,
                )
            except NotFoundError as exc:
                last = exc
                self._emit_audit(
                    AuditKind.PROTOCOL_RECOVERED,
                    {
                        "area": "tournament_detail_not_found",
                        "reason": "详情端点返回 404，按瞬时读取失败有界重试",
                        "tournament_id": tournament_id,
                        "attempt": attempt,
                        "tolerance": TOURNAMENT_DETAIL_NOT_FOUND_TOLERANCE,
                        "official_code": exc.official_code,
                    },
                )
                if attempt >= TOURNAMENT_DETAIL_NOT_FOUND_TOLERANCE:
                    break
                await self._retry_sleep(self._poll_interval)
        if last is None:  # 循环结构保证不可达；显式失败优于静默返回 None
            raise RuntimeError("赛事详情读取未产生结果也未产生异常")
        raise last

    async def _request_with_retry(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[Mapping[str, Any]] = None,
        priority: Priority = Priority.BACKGROUND,
        with_auth: bool = True,
    ) -> Any:
        """有界重试的 JSON GET；返回解析后的 JSON 对象。"""

        attempts = 0
        last_exc: Optional[BaseException] = None
        while True:
            attempts += 1
            try:
                lease = await self._scheduler.acquire(priority, request_kind=RequestKind.OTHER)
                try:
                    result = await audited_request(self._transport, self._emit_audit, self._monotonic,method, path, json_body=json_body, with_auth=with_auth)
                finally:
                    lease.release()
                import json

                return json.loads(result.text)
            except RateLimitedError as exc:
                self._scheduler.note_rate_limited(exc.retry_after_seconds, request_kind=RequestKind.OTHER)
                last_exc = exc
            except (UncertainTransportError, RecoverableServerError) as exc:
                last_exc = exc
            if attempts > self._max_retries:
                # 重试耗尽：显式重抛最后分类异常（裸 raise 在异常已被
                # except 处理后会变成 RuntimeError，无活动异常可重抛）
                if last_exc is not None:
                    raise last_exc
                raise OfficialError(None, None, "retry_exhausted_without_error")
            await self._retry_sleep(self._backoff_base * (2 ** (attempts - 1)))

    # ---------- TournamentSessionPort ----------

    async def initialize(self, target: RuntimeTarget) -> InitializeOutcome:
        try:
            guide_raw = await self._request_with_retry(
                "GET",
                "/portal/api/guide/version",
                priority=Priority.BACKGROUND,
                with_auth=False,
            )
            guide_parsed = parse_guide_version(guide_raw, scoped_tournament=True)
        except AuthError:
            return self._terminal(ParticipantTerminalReason.AUTHENTICATION_FAILED, "guide/version 401")
        except (OfficialError, DtoError, ValueError) as exc:
            return self._terminal(ParticipantTerminalReason.FATAL_PROTOCOL_ERROR, "guide/version: " + str(exc)[:120])
        if guide_parsed.has_unknown_breaking_change:
            return self._terminal(
                ParticipantTerminalReason.INCOMPATIBLE_GUIDE,
                "指南 v{} 存在未审查 breaking 变更".format(guide_parsed.version),
            )
        guide = projector.guide_version(guide_parsed)

        try:
            me = parse_me(await self._request_with_retry("GET", "/api/me", priority=Priority.RECOVERY))
        except AuthError:
            return self._terminal(ParticipantTerminalReason.AUTHENTICATION_FAILED, "/api/me 401")
        except (OfficialError, DtoError, ValueError) as exc:
            return self._terminal(ParticipantTerminalReason.FATAL_PROTOCOL_ERROR, "/api/me: " + str(exc)[:120])

        scoped = bool(me.tournament_id)
        if scoped and me.tournament_id != target.expected_tournament_id:
            return self._terminal(
                ParticipantTerminalReason.TARGET_MISMATCH,
                "Token 绑定 {} 与目标 {} 不符".format(me.tournament_id, target.expected_tournament_id),
            )
        if not scoped:
            # 全局 Token 不承诺支持（技术方案）：其 active_games 跨锦标赛，
            # 详情端点又仅参赛者可见——半支持会破坏目标隔离，按目标不符终止。
            # 测试房间与正式赛事均发放报名 Token（绑定单一锦标赛）。
            return self._terminal(
                ParticipantTerminalReason.TARGET_MISMATCH,
                "全局 Token 不受支持：请使用绑定 {} 的报名 Token".format(target.expected_tournament_id),
            )
        tournament_id = target.expected_tournament_id

        try:
            rules_path = "/api/tournaments/me/rules" if scoped else "/api/tournaments/{}/rules".format(tournament_id)
            rules_raw = await self._request_with_retry("GET", rules_path, priority=Priority.RECOVERY)
            rules_parsed = parse_rules_config(rules_raw)
            if rules_parsed.tournament_id != tournament_id:
                # rules 端点返回的归属必须与目标一致：错误赛事的 M/Rounds/
                # 时限会直接污染 1s/3s 截止计算，按目标错配终止
                return self._terminal(
                    ParticipantTerminalReason.TARGET_MISMATCH,
                    "rules 归属 {} 与目标 {} 不符".format(rules_parsed.tournament_id, tournament_id),
                )
            # 偶发 404 由 _tournament_detail 有界容忍；持续 404 仍→TARGET_MISMATCH
            detail_raw = await self._tournament_detail(tournament_id, priority=Priority.RECOVERY)
            detail_parsed = parse_tournament_detail(detail_raw)
            # 配置构造（M/Rounds/时限约束）与初始投影都在 try 内完成：
            # 坏配置（如 M=0）必须是 ParticipantTerminal 而非裸 ValueError
            config = projector.rules_config(rules_parsed, self._ruleset_version)
            candidate = _Registration(
                guide=guide,
                participant_id=me.user_id,
                tournament_id=tournament_id,
                scoped=scoped,
                config=config,
            )
            projection = self._project_snapshot(detail_parsed, me.active_games, reg=candidate)
        except AuthError:
            return self._terminal(ParticipantTerminalReason.AUTHENTICATION_FAILED, "发现请求 401")
        except (ForbiddenError, NotFoundError) as exc:
            return self._terminal(ParticipantTerminalReason.TARGET_MISMATCH, "目标赛事不可访问: " + (exc.official_code or str(exc.http_status)))
        except (OfficialError, DtoError, ValueError) as exc:
            return self._terminal(ParticipantTerminalReason.FATAL_PROTOCOL_ERROR, "发现请求失败: " + str(exc)[:120])

        # 全部成功后才写入注册状态：失败路径不留下半初始化会话
        self._registration = candidate
        self._adopt(projection)
        # 启动时的版本检查覆盖初始观察修订号；后续新阶段边界由 ready 重查。
        # API 文档 §3.1：完整变更响应保存进启动审计——未来兼容版本的放行
        # 依据可回放（changes 为官方结构化文本，经脱敏后记录）
        self._guide_checked_revisions.add(projection.stage.observed_revision)
        self._emit_audit(
            AuditKind.AUTHORITATIVE_STATE,
            {
                "guide_version": guide.version,
                "guide_updated_at": guide.updated_at,
                "online_confirm": rules_parsed.online_confirm,  # v13 分桌语义判别（存量赛=false）
                "guide_changes": [
                    {
                        "version": change.get("version"),
                        "type": change.get("type"),
                        "summary": sanitize(str(change.get("summary") or ""))[:200],
                    }
                    for change in guide_parsed.changes
                ],
                "checked_at": "initialize",
            },
        )
        return SessionBootstrap(
            guide=guide,
            participant_id=me.user_id,
            tournament_id=tournament_id,
            config=config,
            initial_snapshot=projection,
        )

    async def register(self) -> RegistrationOutcome:
        reg = self._require_registration()
        path = "/api/tournaments/{}/register".format(reg.tournament_id)
        try:
            await self._request_with_retry("POST", path, priority=Priority.RECOVERY)
            return RegistrationResult(status=OperationStatus.ACCEPTED)
        except AuthError:
            return self._terminal(ParticipantTerminalReason.AUTHENTICATION_FAILED, "register 401")
        except ConflictError as exc:
            # 幂等报名：已报名等竞态按官方 409 码分类返回，由应用层结合状态处理
            return RegistrationResult(status=OperationStatus.REJECTED, official_code=exc.official_code)
        except (OfficialError, DtoError, ValueError) as exc:
            return self._terminal(ParticipantTerminalReason.FATAL_PROTOCOL_ERROR, "register: " + str(exc)[:120])

    async def _check_guide_at_boundary(self) -> Optional[ParticipantTerminal]:
        """阶段边界版本门（API 文档 §3.1：报名/ready 前与阶段边界重查一次）。

        多阶段赛事若在阶段间发布未审查的 breaking 指南版本，必须在
        确认出席前拒绝进入未知协议；检查到的版本纳入审计。
        """

        try:
            guide_raw = await self._request_with_retry(
                "GET",
                "/portal/api/guide/version",
                priority=Priority.BACKGROUND,
                with_auth=False,
            )
            guide_parsed = parse_guide_version(guide_raw, scoped_tournament=True)
        except AuthError:
            return self._terminal(ParticipantTerminalReason.AUTHENTICATION_FAILED, "guide/version 401")
        except (OfficialError, DtoError, ValueError) as exc:
            return self._terminal(ParticipantTerminalReason.FATAL_PROTOCOL_ERROR, "guide/version: " + str(exc)[:120])
        self._emit_audit(
            AuditKind.AUTHORITATIVE_STATE,
            {"guide_version": guide_parsed.version, "guide_updated_at": guide_parsed.updated_at, "checked_at": "stage_boundary"},
        )
        if guide_parsed.has_unknown_breaking_change:
            return self._terminal(
                ParticipantTerminalReason.INCOMPATIBLE_GUIDE,
                "阶段边界发现指南 v{} 存在未审查 breaking 变更".format(guide_parsed.version),
            )
        return None

    async def ready(self, expected_stage: StageIdentity) -> ReadyOutcome:
        reg = self._require_registration()
        if expected_stage.observed_revision != self._observed_revision:
            # 陈旧到位：应用层观察已过期，防止把旧阶段命令提交到新阶段
            return ReadyResult(status=OperationStatus.REJECTED, official_code="STALE_STAGE")
        if expected_stage.observed_revision not in self._guide_checked_revisions:
            # 新阶段首次 ready 前重查版本；同阶段幂等 ready 不重复检查
            terminal = await self._check_guide_at_boundary()
            if terminal is not None:
                return terminal
            self._guide_checked_revisions.add(expected_stage.observed_revision)
        path = (
            "/api/tournaments/me/ready"
            if reg.scoped
            else "/api/tournaments/{}/ready".format(reg.tournament_id)
        )
        try:
            await self._request_with_retry("POST", path, priority=Priority.RECOVERY)
            return ReadyResult(status=OperationStatus.ACCEPTED)
        except AuthError:
            return self._terminal(ParticipantTerminalReason.AUTHENTICATION_FAILED, "ready 401")
        except ConflictError as exc:
            return ReadyResult(status=OperationStatus.REJECTED, official_code=exc.official_code)
        except ForbiddenError as exc:
            if exc.official_code == "FEATURE_DISABLED":
                # v29：管理面可全服关闭自建测试房；关闭后已完结测试房的「重开下一轮」
                # （四个令牌各 ready 一次）返回 403 FEATURE_DISABLED——注意该路径此前
                # 返回 409（房态类），现在是 403（**永久条件**）。重试不会恢复。
                return self._terminal(
                    ParticipantTerminalReason.MATCHING_UNAVAILABLE,
                    "ready 403 FEATURE_DISABLED：平台已关闭自建测试房（管理面开关）；"
                    "这是永久条件，不重试。",
                )
            return self._terminal(
                ParticipantTerminalReason.TARGET_MISMATCH,
                "ready 403：code={} detail={}".format(
                    exc.official_code or "?", str(exc)[:200]
                ),
            )
        except (OfficialError, DtoError, ValueError) as exc:
            return self._terminal(ParticipantTerminalReason.FATAL_PROTOCOL_ERROR, "ready: " + str(exc)[:120])

    async def next_update(self) -> Union[TournamentSnapshot, ParticipantTerminal]:
        reg = self._require_registration()
        exhausted_rounds = 0
        while not self._closed:
            try:
                me = parse_me(await self._request_with_retry("GET", "/api/me", priority=Priority.BACKGROUND))
                # 身份绑定每轮核验：Token 被改绑/重置后，他赛事的 active_games
                # 不得进入目标快照（R2：与 initialize 同判据，漂移即终态）
                if me.tournament_id != reg.tournament_id:
                    return self._terminal(
                        ParticipantTerminalReason.TARGET_MISMATCH,
                        "Token 绑定漂移：{} → {}".format(reg.tournament_id, me.tournament_id or "(空)"),
                    )
                detail_parsed = parse_tournament_detail(
                    # 偶发 404 不是"赛事消失"（同端点前后均 200）：容忍见模块常量；
                    # 持续 404 由下面的 except NotFoundError 按永久语义终结
                    await self._tournament_detail(reg.tournament_id, priority=Priority.BACKGROUND)
                )
            except AuthError:
                return self._terminal(ParticipantTerminalReason.AUTHENTICATION_FAILED, "next_update 401")
            except NotFoundError:
                return self._terminal(ParticipantTerminalReason.TARGET_MISMATCH, "tournament gone")
            except ForbiddenError:
                # 授权类永久终态：不得伪装成可重试网络故障（模块规范）
                return self._terminal(ParticipantTerminalReason.TARGET_MISMATCH, "next_update forbidden")
            except (RateLimitedError, UncertainTransportError, RecoverableServerError) as exc:
                # 瞬时网络抖动/限速的整轮耗尽不立即终态化：冷却后继续轮询，
                # 连续多轮（默认 5 轮）仍失败才判定为不可恢复故障
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
                # 协议状态与解析错误没有瞬时性，重试只会得到同样结果：
                # 立即按不可恢复协议错误终结，不占用抖动恢复额度
                return self._terminal(
                    ParticipantTerminalReason.FATAL_PROTOCOL_ERROR,
                    "next_update protocol: " + str(exc)[:120],
                )
            exhausted_rounds = 0
            try:
                snapshot = self._project_snapshot(detail_parsed, me.active_games, reg=reg)
            except (DtoError, ValueError) as exc:
                # 投影失败（未知状态等）与解析同权封闭，不裸抛穿透 next_update
                return self._terminal(
                    ParticipantTerminalReason.FATAL_PROTOCOL_ERROR,
                    "next_update projection: " + str(exc)[:120],
                )
            # finished/closed/void 一律作为普通变化快照返回：赛事何时退出
            # 是应用层（supervisor）的生命周期判定（architecture.md 模块表），
            # 适配器只做协议投影，不重复实现终态化。
            if self._snapshot_changed(snapshot):
                self._adopt(snapshot)
                return snapshot
            await self._retry_sleep(self._poll_interval)
        # 正常关停（aclose）不是协议错误；detail 约定供应用层区分
        return self._terminal(ParticipantTerminalReason.FATAL_PROTOCOL_ERROR, "session_closed_by_aclose")

    def open_game(self, game_id: str) -> GameSessionPort:
        """创建共享本 Token 传输与限速器的单场会话。

        已关闭的旧会话被逐出并重建：应用层监督对可恢复故障的
        重开会话必须拿到全新会话，而不是复用 session_closed 状态。
        """

        reg = self._require_registration()
        cached = self._games.get(game_id)
        if cached is not None and not getattr(cached, "closed", False):
            return cached
        if cached is not None:
            del self._games[game_id]
        # 注：open_game 不做本地归属预校验——active/my 集合在快照间隙可能
        # 合法新增场，预校验会误拒；错配场由官方 403 走 Forbidden 分类兜底
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
        )
        self._games[game_id] = session
        return session

    async def aclose(self) -> None:
        """取消所有挂起请求并释放当前 Token 的连接池。"""

        self._closed = True
        for session in self._games.values():
            await session.aclose("tournament_session_closed")
        self._games.clear()
        await self._transport.aclose()

    # ---------- 内部 ----------

    def _require_registration(self) -> _Registration:
        if self._registration is None:
            raise RuntimeError("必须先 initialize() 才能调用该方法")
        return self._registration

    def _project_snapshot(
        self,
        detail_parsed: Any,
        active_games: Tuple[str, ...],
        *,
        reg: "_Registration",
    ) -> TournamentSnapshot:
        """构造候选快照（纯投影，显式传入注册上下文，不读会话状态）。

        initialize 在提交注册状态之前就要完成投影验证（先验证后提交，
        失败不留半初始化会话）；观察修订号推进到候选值，采纳与否由调用方决定。
        """

        projection = projector.tournament_snapshot(
            detail_parsed,
            tournament_id=reg.tournament_id,
            participant_id=reg.participant_id,
            active_games=active_games,
            observed_revision=self._observed_revision + 1,
            observed_at_unix_ms=self._wall_ms(),
        )
        snapshot = projection.snapshot
        return snapshot

    @staticmethod
    def _exhaustion_prefix(exc: Exception) -> str:
        """重试耗尽的分类前缀，便于赛后归因（限速误杀 vs 协议漂移）。"""

        from .errors import RateLimitedError, RecoverableServerError, UncertainTransportError

        if isinstance(exc, RateLimitedError):
            return "rate_limit_exhausted"
        if isinstance(exc, (UncertainTransportError, RecoverableServerError)):
            return "transport_exhausted"
        return "protocol_error"

    def _adopt(self, snapshot: TournamentSnapshot) -> None:
        """采纳候选快照：推进观察修订号、记录最近快照并发射生命周期审计。

        审计只在真实采纳（变化或终态）时发射，轮询无变化不再产生噪声。
        """

        self._observed_revision = snapshot.stage.observed_revision
        self._last_snapshot = snapshot
        self._emit_audit(
            AuditKind.LIFECYCLE_CHANGED,
            {
                "status": snapshot.status.value,
                "stage_no": snapshot.stage.stage_no,
                "stage_crashed": snapshot.stage_crashed,
                "qualified": snapshot.qualified,
                "active_games": list(snapshot.active_games),
                "observed_revision": snapshot.stage.observed_revision,
            },
        )

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

    def _terminal(
        self,
        reason: ParticipantTerminalReason,
        detail: str,
        last_snapshot: Optional[TournamentSnapshot] = None,
    ) -> ParticipantTerminal:
        snapshot = last_snapshot if last_snapshot is not None else self._last_snapshot
        self._emit_audit(
            AuditKind.PARTICIPANT_FINISHED,
            {"reason": reason.value, "detail": sanitize(detail)},
        )
        return ParticipantTerminal(reason=reason, last_snapshot=snapshot, detail=sanitize(detail))
