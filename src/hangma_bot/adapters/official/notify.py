"""官方 SSE 通知流客户端（SSE Notify Stream，指南 v12 引入、v14 全文确认）。

为 GET /api/games/{id}/notify 提供独立客户端。2026-09-24 起运行配置显式
开启 SSE 时由场次适配器用于帧驱动状态同步；该模式暂不挂 /state 长轮询。
早期客户端集成契约见 doc/implementation/notes/sse-notify-client.md。

实现的协议要点与出处（指南 v14 全文 doc/references/official-guide-v14-content.txt
端点表与 §2.1，2026-09-05 抓取；v12 变更记录 doc/references/official-guide-version-v14.json，
2026-09-04；v13 附注 SSE 只存在于局内）：

1. 连接即收初始帧 {"seq":N}——N 是当前事件水位（包含式），是重连对齐点；
2. 每次状态变更（出牌/摸牌/吃/碰/杠/胡/流局/超时等）推 {"seq":新水位}，
   与 /state 使用同一全局递增水位；
3. 每 30s 一行 ": keepalive" 注释维持连接——注释行一律忽略；
4. 场终/死场/慢消费者断流推 {"seq":N,"closed":true} 后关流，客户端按
   有界退避重连并用新连接的首帧重新对齐；
5. 帧只含 seq，不含牌面/动作/变化内容——本模块绝不解析牌面信息；
6. 每用户 32 并发连接上限（超限 429），不占 /state 的 16/s 频率额度——
   本模块用 StreamBudget 维护本地并发预算，超预算时不发起连接；
7. 游标纪律（官方警告）：/state 的 seq 参数语义 =「N 之后的事件」——
   游标永远是本地已消费 seq；初始帧 seq 是包含式水位，不可直接当轮询
   游标（直接传会跳过 N 之前全部事件）；游标未知请 seq=0 拿快照起步。
   本模块只投递水位，游标由同步工作线维护（见集成契约）。

错误分类复用 errors.py 现有体系（不改冻结契约）：401→AuthError（终态，
不重连）；403/404/400/409/其他官方错误→对应 OfficialError 子类（终态）；
429→RateLimitedError（重连退避至少冷却 retry_after 秒）；断连/读超时/
EOF→UncertainTransportError（可恢复）；帧解析失败→DtoError(recoverable)。
重连有界（max_reconnects + 指数退避），耗尽返回 RECONNECTS_EXHAUSTED
可恢复失败，绝不无限自动重连。所有异常 detail、观察事件与运行结果
均经脱敏，绝不含 Token；SSE 原始行文本只随 NotifyFrame.raw 进入
审计原文（RAW_PROTOCOL_STATE，build_sse_frame_payload），不进异常
与日志。
"""

from __future__ import annotations

import asyncio
import json
import math
import time
from dataclasses import dataclass
from enum import Enum
from typing import Awaitable, Callable, List, Mapping, Optional

from .errors import (
    DtoError,
    OfficialError,
    RateLimitedError,
    RecoverableServerError,
    UncertainTransportError,
    sanitize,
)
from .transport import OfficialTransport

# 官方每用户 SSE 并发连接上限（指南 v14 端点表与 §2.3；超限返回 429）。
OFFICIAL_SSE_CONCURRENT_LIMIT = 32

# 本地并发预算缺省值：官方 M 上限 16 场 × 每场 1 流 + 8 余量。
# 刻意低于官方 32 上限，为官方侧统计与 /state 挂起轮询等留出裕量。
DEFAULT_LOCAL_STREAM_BUDGET = 24

# SSE data 事件行前缀（SSE 规范）；官方帧为单行 JSON。
_DATA_PREFIX = "data:"

# 单条 data 载荷长度上限（W2-3 修复）：防超长/毒化帧拖垮解析与内存。
# 官方帧只有 seq/closed 两个标量，64KB 已是正常帧的数千倍余量；
# 超限按可恢复 DtoError 处理（断开重连），绝不静默截断解析。
_MAX_FRAME_DATA_BYTES = 64 * 1024


@dataclass(frozen=True)
class NotifyFrame:
    """一条通知帧：官方事件水位与关流标记，绝不解析牌面信息。

    seq：与 /state 同一全局递增水位，包含式（服务器已发到 seq）；
    不是轮询游标——/state?seq= 的语义是「N 之后的事件」，游标永远是
    本地已消费 seq（指南 v14 §2.1；游标纪律由同步工作线维护）。
    closed：官方在流终止（场终/死场/慢消费者断流）前推送的关流标记；
    收到后客户端应重连对齐或按需拉终态（指南 v12 变更记录）。
    raw：本条事件 data 载荷原文（多行 data 拼接后的完整文本）；只供
    审计原文留存（RAW_PROTOCOL_STATE，build_sse_frame_payload），
    不进异常、日志与 NotifyStreamEvent。缺省 None 兼容既有调用方。
    """

    seq: int
    closed: bool = False
    raw: Optional[str] = None

    def __post_init__(self) -> None:
        # seq 非负纯 int（bool 拒绝），与 kernel 序号不变量同口径；
        # closed 必须是布尔，杜绝 truthy 值静默归一
        if isinstance(self.seq, bool) or not isinstance(self.seq, int):
            raise DtoError("通知帧 seq 应为整数")
        if self.seq < 0:
            raise DtoError("通知帧 seq 不得为负")
        if not isinstance(self.closed, bool):
            raise DtoError("通知帧 closed 应为布尔")


def parse_notify_frame(data_payload: str, *, raw: Optional[str] = None) -> NotifyFrame:
    """解析一条 data 载荷（官方帧为单行 JSON 对象）；非法抛 DtoError(recoverable)。

    未知新增键一律忽略：v12 引入后官方可能修订帧格式，前向兼容原则与
    dto.py 一致。seq 必须为非负纯 int；closed 存在时必须为布尔。JSON
    非法/形状不符按可恢复协议错误处理（默认 recoverable=True），由
    调用方断开重连，绝不吞帧也绝不解析 seq 以外的任何内容。
    ``raw`` 透传到 NotifyFrame.raw：单条事件 data 载荷原文只供审计
    原文留存，不进异常与日志；缺省 None。
    """

    if len(data_payload) > _MAX_FRAME_DATA_BYTES:
        # W2-3：超长 data 载荷（毒化/异常帧）按可恢复分类，不做截断解析。
        raise DtoError("通知帧 data 载荷超长（>{} 字节）".format(_MAX_FRAME_DATA_BYTES))
    try:
        doc = json.loads(data_payload)
    except ValueError:
        raise DtoError("通知帧不是合法 JSON") from None
    except RecursionError:
        # W2-3：深嵌套毒化帧 json.loads 抛 RecursionError（ValueError 之外），
        # 必须同样收敛为可恢复 DtoError，否则会穿过 run() 裸抛、违反
        # "官方分类错误绝不裸抛/封闭结果"承诺。
        raise DtoError("通知帧 JSON 嵌套过深") from None
    if not isinstance(doc, Mapping):
        raise DtoError("通知帧应为 JSON 对象")
    closed = doc.get("closed")
    if closed is not None and not isinstance(closed, bool):
        raise DtoError("通知帧 closed 应为布尔")
    return NotifyFrame(seq=doc.get("seq"), closed=bool(closed or False), raw=raw)


class _SseEventAccumulator:
    """SSE 事件行累加器：data 行拼接、注释行忽略、空行分发一条事件。

    SSE 规范：事件以空行结束；": keepalive" 是注释行，不参与分发；
    data 可跨多行（官方帧是单行，多行拼接仅为 SSE 规范兼容）；
    event:/id:/retry: 等字段行官方流不使用，容忍忽略。
    返回的 NotifyFrame 携带 raw（拼接后的 data 原文），只供审计
    原文留存，不进异常与日志。
    """

    def __init__(self) -> None:
        self._data_lines: List[str] = []

    def feed(self, line: str) -> Optional[NotifyFrame]:
        """送入一行（不含行尾换行）；整条事件齐备时返回解析帧，否则 None。"""

        if line == "":
            if not self._data_lines:
                return None
            payload = "\n".join(self._data_lines)
            self._data_lines.clear()
            return parse_notify_frame(payload, raw=payload)
        if line.startswith(":"):
            return None  # 注释行（官方 ": keepalive"）
        if line.startswith(_DATA_PREFIX):
            value = line[len(_DATA_PREFIX):]
            if value.startswith(" "):
                value = value[1:]  # SSE 规范：冒号后至多一个空格
            self._data_lines.append(value)
            return None
        return None

    def flush(self) -> Optional[NotifyFrame]:
        """EOF 宽容：末尾未以空行结束的最后一条事件也解析分发。

        官方帧是单行 JSON，部分实现不补结尾空行；宽容解析避免
        把合法帧误判为"EOF 无 closed 帧"的断连。缓存为空返回 None。
        """

        if not self._data_lines:
            return None
        payload = "\n".join(self._data_lines)
        self._data_lines.clear()
        return parse_notify_frame(payload, raw=payload)


class StreamBudget:
    """每用户 SSE 并发连接本地预算（每 Token 一个，全部场次共享）。

    官方每用户并发 SSE 连接上限 32（超限 429）；本地预算默认 24 =
    官方 M 上限 16 场 × 每场 1 流 + 8 余量，可配置 1..32。预算只约束
    "是否发起连接"，不参与 /state 的 16/s 限速（官方明确 notify 不占
    /state 频率额度）。超预算时不连接：由调用方决定等待、稍后重开或
    回退长轮询（等待语义见 SSENotifyClient.run）。
    """

    def __init__(self, max_streams: int = DEFAULT_LOCAL_STREAM_BUDGET) -> None:
        if isinstance(max_streams, bool) or not isinstance(max_streams, int):
            raise ValueError("StreamBudget.max_streams 必须是整数")
        if not 1 <= max_streams <= OFFICIAL_SSE_CONCURRENT_LIMIT:
            raise ValueError(
                "StreamBudget.max_streams 必须在 1..{} 之间（官方每用户并发上限）".format(
                    OFFICIAL_SSE_CONCURRENT_LIMIT
                )
            )
        self._max_streams = max_streams
        self._active = 0

    @property
    def max_streams(self) -> int:
        """预算上限（本地配置值，≤ 官方 32）。"""

        return self._max_streams

    @property
    def active(self) -> int:
        """当前已占用连接数。"""

        return self._active

    @property
    def available(self) -> int:
        """当前可用连接数。"""

        return self._max_streams - self._active

    def try_acquire(self) -> bool:
        """非阻塞占用一个连接槽；预算耗尽返回 False。"""

        if self._active >= self._max_streams:
            return False
        self._active += 1
        return True

    def release(self) -> None:
        """归还连接槽；重复归还安全（幂等，下限 0）。"""

        if self._active > 0:
            self._active -= 1

    async def acquire(
        self,
        *,
        clock: Callable[[], float],
        sleep: Callable[[float], Awaitable[None]],
        wait_sec: Optional[float],
    ) -> bool:
        """占用一个槽；wait_sec=None 时不等待立即返回，否则最多等 wait_sec 秒。

        轮询间隔 0.1s；clock/sleep 可注入，时间测试不依赖真实等待
        （tests/AGENTS.md）。
        """

        if wait_sec is None:
            return self.try_acquire()
        deadline = clock() + max(0.0, wait_sec)
        while True:
            if self.try_acquire():
                return True
            remaining = deadline - clock()
            if remaining <= 0:
                return False
            await sleep(min(0.1, remaining))


class NotifyEndKind(str, Enum):
    """run() 的终局分类；TERMINAL 不可恢复，其余由调用方按策略处置。"""

    CANCELLED = "cancelled"  # aclose()/取消：正常关停，预算槽已归还
    TERMINAL = "terminal"  # 认证/授权/目标不存在等官方终态错误：不再重连
    RECONNECTS_EXHAUSTED = "reconnects_exhausted"  # 有界重连耗尽：可恢复失败，可稍后重开
    BUDGET_UNAVAILABLE = "budget_unavailable"  # 本地并发预算不足：未发起任何连接


@dataclass(frozen=True)
class NotifyRunResult:
    """run() 的封闭终局；全部字段已脱敏，绝不含 Token。

    ``error``（OfficialError 实例）的载体边界（F-14/wv6 注明）：
    ``error.raw_text`` 是传输层已完成 Token 精确替换、未截断的 HTTP
    错误体原文——仅供审计落盘使用（原始事件全量保留），**不得**写入
    日志、异常串或任何面向人的输出；`detail` 与模块其余字段已过
    sanitize、不携带原始行文本。
    """

    kind: NotifyEndKind
    detail: str = ""  # 已脱敏描述
    error: Optional[OfficialError] = None  # TERMINAL/RECONNECTS_EXHAUSTED 时的分类错误
    initial_watermark: Optional[int] = None  # 最近一次连接的首帧水位（重连对齐点）
    last_watermark: Optional[int] = None  # 最近一次投递的水位
    reconnects: int = 0  # 实际发生的重连次数
    frames_delivered: int = 0  # 投递给回调的帧总数（含 closed 帧）


class NotifyEventKind(str, Enum):
    """流生命周期观察事件种类（诊断/审计钩子词表）。"""

    STREAM_OPENED = "stream_opened"  # 一次连接尝试开始
    FRAME = "frame"  # 一条帧已解析并投递
    STREAM_ENDED = "stream_ended"  # 收到 closed:true 后的正常收尾
    RECONNECT_SCHEDULED = "reconnect_scheduled"  # 计划重连（含退避秒数与错误分类）
    RUN_FINISHED = "run_finished"  # run() 终局（run_kind=NotifyEndKind 值）


@dataclass(frozen=True)
class NotifyStreamEvent:
    """流生命周期观察事件；只含脱敏字段，绝不含行原文与 Token。"""

    kind: str  # NotifyEventKind 值
    game_id: str
    attempt: int = 0  # 连接尝试序号，从 1 起
    seq: Optional[int] = None  # frame/stream_ended/run_finished 的水位
    closed: Optional[bool] = None  # frame 的关流标记
    end_reason: Optional[str] = None  # stream_ended 原因（当前恒为 closed_frame）
    backoff_sec: Optional[float] = None  # reconnect_scheduled 的退避秒数
    error_kind: Optional[str] = None  # 触发重连/终局的错误类名（不含消息文本）
    run_kind: Optional[str] = None  # run_finished 的 NotifyEndKind 值


# 帧回调（集成契约）：收到帧后应以 GET /state?seq=<本地已消费游标> 拉增量。
NotifyFrameHandler = Callable[[NotifyFrame], Awaitable[None]]
# 观察者回调（诊断/审计钩子）：只接收 NotifyStreamEvent，不接收原始行。
NotifyEventObserver = Callable[[NotifyStreamEvent], Awaitable[None]]


@dataclass(frozen=True)
class NotifyStreamConfig:
    """SSE 通知流客户端策略；所有时间字段单位为秒。"""

    max_reconnects: int = 5  # 一次 run() 内首连之后的重连上限；耗尽返回可恢复失败
    backoff_base_sec: float = 0.5  # 指数退避起点
    backoff_max_sec: float = 30.0  # 指数退避封顶
    budget_wait_sec: Optional[float] = None  # 预算不足时等待空闲槽的最长秒数；None=立即返回 BUDGET_UNAVAILABLE

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_reconnects, bool)
            or not isinstance(self.max_reconnects, int)
            or self.max_reconnects < 0
        ):
            raise ValueError("NotifyStreamConfig.max_reconnects 必须是非负整数")
        for name in ("backoff_base_sec", "backoff_max_sec"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError(
                    "NotifyStreamConfig.{} 必须是正的有限秒数".format(name)
                )
        if self.backoff_base_sec > self.backoff_max_sec:
            raise ValueError("NotifyStreamConfig 退避起点不得大于封顶")
        if self.budget_wait_sec is not None and (
            isinstance(self.budget_wait_sec, bool)
            or not isinstance(self.budget_wait_sec, (int, float))
            or not math.isfinite(self.budget_wait_sec)
            or self.budget_wait_sec < 0
        ):
            raise ValueError(
                "NotifyStreamConfig.budget_wait_sec 必须是非负的有限秒数或 None"
            )


@dataclass(frozen=True)
class _StreamStats:
    """一次连接读取的帧统计。"""

    first_watermark: Optional[int]
    last_watermark: Optional[int]
    frames: int


class _StreamFailed(Exception):
    """一次连接读取失败：携带分类错误与失败前已投递帧的统计。

    失败流在断连前可能已投递部分帧（如慢消费者场景先收了若干帧才被
    踢掉），这些帧必须并入终局统计——水位对齐点与投递计数不能因
    重连而丢失。
    """

    def __init__(self, error: Exception, stats: _StreamStats) -> None:
        super().__init__(type(error).__name__)
        self.error = error
        self.stats = stats


class _CloseRequested(Exception):
    """aclose() 请求关停的内部信号；由 run() 转换为 CANCELLED 结果。

    流内检查点抛出时携带当前连接已投递帧的统计，关停结果才能保留
    已发生的水位对齐与投递计数。
    """

    def __init__(self, stats: Optional[_StreamStats] = None) -> None:
        super().__init__("aclose")
        self.stats = stats


class SSENotifyClient:
    """单个 game_id 的 SSE 通知流客户端；不接入运行链路（可选能力）。

    一个实例对应一个 game_id 的一条流；同 Token 各场共享 OfficialTransport
    （Bearer 认证、连接池、TLS 白名单语义全部复用传输层）与 StreamBudget。
    run() 执行「连接 → 收帧 → 重连对齐 → 终局」的完整生命周期并返回封闭
    NotifyRunResult，官方分类错误绝不从 run() 裸抛。重连耗尽后可再次
    run()（可恢复失败）；aclose() 后实例不可复用。
    """

    def __init__(
        self,
        game_id: str,
        transport: OfficialTransport,
        *,
        budget: Optional[StreamBudget] = None,
        on_frame: Optional[NotifyFrameHandler] = None,
        audit_emit=None,  # 非阻塞审计函数，连接及取消与普通 HTTP 使用相同 request_id 口径
        on_event: Optional[NotifyEventObserver] = None,
        config: Optional[NotifyStreamConfig] = None,
        monotonic_clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not isinstance(game_id, str) or not game_id.strip():
            raise ValueError("game_id 必须是非空字符串")
        self.game_id = game_id
        self._transport = transport
        # 每 Token 一个预算、各场共享；缺省各自建独立预算（独立使用场景）
        self._budget = budget if budget is not None else StreamBudget()
        self._on_frame = on_frame
        self._audit_emit = audit_emit if audit_emit is not None else lambda *args: None
        self._on_event = on_event
        self._config = config if config is not None else NotifyStreamConfig()
        self._clock = monotonic_clock
        self._sleep = sleep
        self._path = "/api/games/{}/notify".format(game_id)
        self._closed = False
        self._cancel_requested = False
        self._task: Optional[asyncio.Task] = None
        self.event_hook_errors = 0  # 观察者钩子异常计数（诊断用）

    @property
    def path(self) -> str:
        """本场 notify 端点路径（/api/games/{id}/notify）。"""

        return self._path

    @property
    def budget(self) -> StreamBudget:
        """本地并发预算；调用方可先查看可用槽再决定是否 run()。"""

        return self._budget

    async def run(self) -> NotifyRunResult:
        """运行完整流生命周期；官方分类错误封装进结果，不裸抛。

        终局语义：TERMINAL（不可恢复，不再重连）、RECONNECTS_EXHAUSTED
        （有界重连耗尽，调用方可稍后重开或回退 /state 长轮询）、
        BUDGET_UNAVAILABLE（本地预算不足，未发起连接）、CANCELLED
        （aclose() 优雅关停）。集成回调 on_frame 抛出的异常向上传播
        （集成故障必须显式，不允许静默吞掉）；传播前预算槽已归还。
        外部 task.cancel() 按标准协程取消语义抛 CancelledError。
        """

        if self._closed:
            raise RuntimeError("SSENotifyClient 已 aclose，不可复用")
        if self._task is not None and not self._task.done():
            raise RuntimeError("同一 SSENotifyClient 不允许并发 run")
        current = asyncio.current_task()
        if current is None:  # 理论不可达：协程必然运行在任务内
            raise RuntimeError("run 必须在 asyncio 任务内调用")
        self._task = current
        try:
            acquired = await self._budget.acquire(
                clock=self._clock,
                sleep=self._sleep,
                wait_sec=self._config.budget_wait_sec,
            )
            if not acquired:
                result = NotifyRunResult(
                    kind=NotifyEndKind.BUDGET_UNAVAILABLE,
                    detail="budget_unavailable:max_streams={}".format(
                        self._budget.max_streams
                    ),
                )
                await self._notify_event(self._finished_event(result))
                return result
            try:
                result = await self._run_lifecycle()
            finally:
                self._budget.release()
            await self._notify_event(self._finished_event(result))
            return result
        except asyncio.CancelledError:
            if not self._cancel_requested:
                raise  # 外部取消：按标准协程取消语义向上传播
            # 被本客户端 aclose() 取消：转换为 CANCELLED 结果而非向外抛。
            # uncancel() 让等待方拿到结果而不是 CancelledError（3.11+ 语义：
            # 吞掉 CancelledError 后不 uncancel，任务仍会被视为已取消）
            current.uncancel()
            result = NotifyRunResult(kind=NotifyEndKind.CANCELLED, detail="aclose")
            await self._notify_event(self._finished_event(result))
            return result
        finally:
            self._task = None

    async def _run_lifecycle(self) -> NotifyRunResult:
        """持有预算槽的主循环：连接、收帧、分类重连、终局。"""

        initial_watermark: Optional[int] = None
        last_watermark: Optional[int] = None
        frames_delivered = 0
        reconnects = 0
        attempt = 1
        backoff_sec = self._config.backoff_base_sec
        last_error: Optional[OfficialError] = None
        last_end_reason = "initial"
        try:
            while True:
                if self._cancel_requested:
                    raise _CloseRequested()
                try:
                    stats = await self._consume_stream(attempt)
                except _StreamFailed as failure:
                    # 失败流在断连前可能已投递帧：先合并统计再分类，
                    # 水位对齐点与投递计数不因重连而丢失
                    exc = failure.error
                    merged = failure.stats
                    if merged.first_watermark is not None:
                        initial_watermark = merged.first_watermark
                    if merged.last_watermark is not None:
                        last_watermark = merged.last_watermark
                    frames_delivered += merged.frames
                    if isinstance(
                        exc,
                        (
                            RateLimitedError,
                            RecoverableServerError,
                            UncertainTransportError,
                            DtoError,
                        ),
                    ):
                        # 可恢复分类：429（冷却 retry_after）/可恢复 5xx/
                        # 断连/超时/帧解析失败——有界退避后重连，初始帧
                        # 重新对齐水位
                        last_error = exc
                        last_end_reason = "error:{}".format(type(exc).__name__)
                    else:
                        # 401/403/404/400/409 等官方终态错误：不再重连
                        # （模块规范：认证、授权或不可恢复协议错误不得
                        # 伪装成可重试网络故障）。404 GAME_NOT_FOUND 是
                        # 完赛场/死场的自然终态（2026-09 实测参赛者
                        # Token 通过认证层后返回 404）
                        return self._result(
                            NotifyEndKind.TERMINAL,
                            "terminal:{}".format(type(exc).__name__),
                            exc,
                            initial_watermark,
                            last_watermark,
                            reconnects,
                            frames_delivered,
                        )
                else:
                    # 正常收尾（closed:true）：更新水位统计后按官方语义重连。
                    # 清空上次错误分类，避免退避与终局报告携带过期错误
                    if stats.first_watermark is not None:
                        initial_watermark = stats.first_watermark
                    if stats.last_watermark is not None:
                        last_watermark = stats.last_watermark
                    frames_delivered += stats.frames
                    last_error = None
                    last_end_reason = "closed_frame"
                if reconnects >= self._config.max_reconnects:
                    return self._result(
                        NotifyEndKind.RECONNECTS_EXHAUSTED,
                        "reconnects_exhausted:last={}".format(last_end_reason),
                        last_error,
                        initial_watermark,
                        last_watermark,
                        reconnects,
                        frames_delivered,
                    )
                # 429 冷却优先于常规退避：至少等官方建议的 retry_after 秒
                delay = backoff_sec
                if (
                    isinstance(last_error, RateLimitedError)
                    and last_error.retry_after_seconds is not None
                ):
                    delay = max(delay, float(last_error.retry_after_seconds))
                reconnects += 1
                await self._notify_event(
                    NotifyStreamEvent(
                        kind=NotifyEventKind.RECONNECT_SCHEDULED.value,
                        game_id=self.game_id,
                        attempt=attempt,
                        backoff_sec=delay,
                        error_kind=(
                            type(last_error).__name__ if last_error is not None else None
                        ),
                    )
                )
                attempt += 1
                backoff_sec = min(self._config.backoff_max_sec, backoff_sec * 2.0)
                await self._sleep(delay)
        except _CloseRequested as closed:
            # 关停信号携带当前连接已投递帧的统计：并入终局结果，
            # 保留已发生的水位对齐与投递计数
            stats = closed.stats
            if stats is not None:
                if stats.first_watermark is not None:
                    initial_watermark = stats.first_watermark
                if stats.last_watermark is not None:
                    last_watermark = stats.last_watermark
                frames_delivered += stats.frames
            return self._result(
                NotifyEndKind.CANCELLED,
                "aclose",
                None,
                initial_watermark,
                last_watermark,
                reconnects,
                frames_delivered,
            )

    async def _consume_stream(self, attempt: int) -> _StreamStats:
        """读取一次连接直到官方关流（closed 帧）。

        每次读超时与断连由 transport.open_sse_stream 分类抛
        UncertainTransportError；帧解析失败抛 DtoError；closed:true 后
        立即收尾（官方随后会关流，提前收尾避免依赖对端行为）。失败
        （OfficialError/DtoError）包装为 _StreamFailed 携带已投递帧
        统计；on_frame 回调异常与取消信号原样传播。
        """

        await self._notify_event(
            NotifyStreamEvent(
                kind=NotifyEventKind.STREAM_OPENED.value,
                game_id=self.game_id,
                attempt=attempt,
            )
        )
        accumulator = _SseEventAccumulator()
        first_watermark: Optional[int] = None
        last_watermark: Optional[int] = None
        frames = 0
        saw_closed = False

        def _stats() -> _StreamStats:
            return _StreamStats(
                first_watermark=first_watermark,
                last_watermark=last_watermark,
                frames=frames,
            )

        try:
            from .request_audit import audited_sse_stream
            async with audited_sse_stream(self._transport, self._audit_emit, self._clock, self._path) as lines:
                async for line in lines:
                    if self._cancel_requested:
                        raise _CloseRequested(_stats())
                    frame = accumulator.feed(line)
                    if frame is None:
                        continue  # 注释行（": keepalive"）与空行不产生帧
                    if first_watermark is None:
                        first_watermark = frame.seq
                    last_watermark = frame.seq
                    frames += 1
                    await self._deliver_frame(frame)
                    if frame.closed:
                        saw_closed = True
                        break
            # EOF 前可能还有未以空行结束的最后一条事件（单行帧流兼容）
            pending = accumulator.flush()
            if pending is not None:
                if first_watermark is None:
                    first_watermark = pending.seq
                last_watermark = pending.seq
                frames += 1
                await self._deliver_frame(pending)
                if pending.closed:
                    saw_closed = True
            if not saw_closed:
                # EOF 无 closed 帧：服务器未按协议关流（断连/慢消费者被踢），
                # 按可恢复分类，由调用方有界重连并用新连接初始帧重新对齐
                raise UncertainTransportError("sse:eof_without_closed_frame")
        except (OfficialError, DtoError) as exc:
            # 失败流在断连前可能已投递部分帧：包装携带统计，调用方
            # 必须把这些帧并入终局结果（对齐水位与投递计数不丢失）
            raise _StreamFailed(exc, _stats()) from None
        await self._notify_event(
            NotifyStreamEvent(
                kind=NotifyEventKind.STREAM_ENDED.value,
                game_id=self.game_id,
                attempt=attempt,
                seq=last_watermark,
                end_reason="closed_frame",
            )
        )
        return _StreamStats(
            first_watermark=first_watermark,
            last_watermark=last_watermark,
            frames=frames,
        )

    async def _deliver_frame(self, frame: NotifyFrame) -> None:
        """投递一条帧：先记录观察事件（审计钩子），再调用集成回调。

        集成契约（见交付笔记）：收到帧后应以
        GET /state?seq=<本地已消费游标> 拉增量——初始帧 seq 是包含式
        水位，绝不能直接当游标（官方警告，指南 v14 §2.1）。on_frame
        的异常向上传播终止 run()；on_event 的异常只计数降级（诊断
        通道不得影响信号流）。
        """

        await self._notify_event(
            NotifyStreamEvent(
                kind=NotifyEventKind.FRAME.value,
                game_id=self.game_id,
                seq=frame.seq,
                closed=frame.closed,
            )
        )
        if self._on_frame is not None:
            await self._on_frame(frame)

    async def _notify_event(self, event: NotifyStreamEvent) -> None:
        """非阻塞观察钩子；钩子异常只计数，不影响流生命周期。"""

        if self._on_event is None:
            return
        try:
            await self._on_event(event)
        except Exception:
            self.event_hook_errors += 1

    @staticmethod
    def _result(
        kind: NotifyEndKind,
        detail: str,
        error: Optional[OfficialError],
        initial_watermark: Optional[int],
        last_watermark: Optional[int],
        reconnects: int,
        frames_delivered: int,
    ) -> NotifyRunResult:
        """构造终局结果；detail 再经一次 sanitize 防御（绝不含 Token）。"""

        return NotifyRunResult(
            kind=kind,
            detail=sanitize(detail),
            error=error,
            initial_watermark=initial_watermark,
            last_watermark=last_watermark,
            reconnects=reconnects,
            frames_delivered=frames_delivered,
        )

    def _finished_event(self, result: NotifyRunResult) -> NotifyStreamEvent:
        """构造 run_finished 观察事件；只携带脱敏字段。"""

        return NotifyStreamEvent(
            kind=NotifyEventKind.RUN_FINISHED.value,
            game_id=self.game_id,
            seq=result.last_watermark,
            run_kind=result.kind.value,
            error_kind=type(result.error).__name__ if result.error is not None else None,
        )

    async def aclose(self) -> None:
        """优雅关停：请求 run() 结束并取消在途任务；幂等，之后实例不可复用。

        先置关闭标志——run 循环在下一个检查点以 CANCELLED 结果返回；
        再让出一个事件循环周期，若 run 仍阻塞（真实网络读/预算等待），
        取消其任务强制打断。被 aclose 取消的 run() 同样返回 CANCELLED
        结果（不向外抛 CancelledError），预算槽在 finally 归还。
        """

        self._closed = True
        self._cancel_requested = True
        task = self._task
        if task is None or task is asyncio.current_task():
            return
        # 多拍让出：活跃流在每个产出行都有检查点，几个事件循环周期内
        # 即可观察到关闭标志并以 CANCELLED 结果优雅返回；真实网络读
        # 阻塞时退化为强制取消（run 的 uncancel 路径仍返回 CANCELLED）
        for _ in range(50):
            if task.done():
                break
            await asyncio.sleep(0)
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
