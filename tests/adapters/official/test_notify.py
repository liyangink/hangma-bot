"""SSE 通知流客户端测试（fake 流，无网络依赖）。

通过真实 OfficialTransport + httpx.MockTransport 注入脚本化假 SSE 流，
覆盖：happy path（初始帧/变更帧/keepalive）、closed 后重连对齐、
慢消费者断连、429 退避与本地预算、认证失败终态、有界重连耗尽、
帧解析与脱敏契约、优雅关停与取消。时间测试全部注入假时钟与假 sleep，
不使用真实等待（tests/AGENTS.md）。
"""
from __future__ import annotations

import asyncio
from typing import List, Optional, Tuple

import httpx
import pytest

from _official_testkit import FakeClock, instant_sleep
from hangma_bot.adapters.official.errors import (
    AuthError,
    ConflictError,
    DtoError,
    ForbiddenError,
    NotFoundError,
    RateLimitedError,
    UncertainTransportError,
)
from hangma_bot.adapters.official.notify import (
    DEFAULT_LOCAL_STREAM_BUDGET,
    OFFICIAL_SSE_CONCURRENT_LIMIT,
    NotifyEndKind,
    NotifyEventKind,
    NotifyFrame,
    NotifyStreamConfig,
    NotifyStreamEvent,
    SSENotifyClient,
    StreamBudget,
    parse_notify_frame,
)
from hangma_bot.adapters.official.transport import OfficialTransport, TransportConfig

TOKEN = "notify-test-token-0123456789abcdef"
GAME_ID = "g_test_game"


class FakeSseStream(httpx.AsyncByteStream):
    """脚本化假 SSE 流：逐行产出文本（无行尾），可模拟断连/静默挂起/无限流。

    fail_after：产出该行数后抛 httpx.ReadError（模拟服务器断连/慢消费者被踢）；
    repeat：到达末尾后循环产出（模拟长连接，供优雅关停测试）；
    block_event：先等待永不被触发的 Event（模拟静默挂起的真实网络读）。
    """

    def __init__(
        self,
        lines: List[str],
        *,
        fail_after: Optional[int] = None,
        repeat: bool = False,
        block_event: Optional[asyncio.Event] = None,
    ) -> None:
        self._lines = lines
        self._fail_after = fail_after
        self._repeat = repeat
        self._block_event = block_event

    async def __aiter__(self):
        if self._block_event is not None:
            await self._block_event.wait()  # 永不完成：模拟静默挂起的读
            return
        if not self._lines:
            return
        index = 0
        while True:
            if self._fail_after is not None and index >= self._fail_after:
                raise httpx.ReadError("connection reset by peer")
            line = (
                self._lines[index % len(self._lines)]
                if self._repeat
                else self._lines[index]
            )
            yield (line + "\n").encode("utf-8")
            await asyncio.sleep(0)  # 每个检查点让出事件循环（可取消/可观察标志）
            index += 1
            if not self._repeat and index >= len(self._lines):
                return

    def close(self) -> None:
        return None


def sse_response(lines: List[str], **stream_kw) -> httpx.Response:
    """构造 SSE 200 假响应（Content-Type: text/event-stream）。"""

    return httpx.Response(
        200,
        headers={"Content-Type": "text/event-stream"},
        stream=FakeSseStream(lines, **stream_kw),
    )


class ScriptedNotifyTransport:
    """按剧本服务 open_sse_stream 的假传输（真实 OfficialTransport + MockTransport）。

    剧本项：httpx.Response / BaseException 实例 / callable(attempt)→以上二者。
    每次流式请求消耗一条剧本；记录请求路径与认证头供断言。
    """

    def __init__(self, token: str, script: list) -> None:
        self._token = token
        self._script = list(script)
        self.open_count = 0
        self.seen_paths: List[str] = []
        self.seen_auth: List[Optional[str]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            self.open_count += 1
            self.seen_paths.append(request.url.path)
            self.seen_auth.append(request.headers.get("Authorization"))
            item = self._script[min(self.open_count - 1, len(self._script) - 1)]
            if callable(item):
                item = item(self.open_count)
            if isinstance(item, BaseException):
                raise item
            return item

        config = TransportConfig(
            base_url="https://notify.test", insecure_hosts=frozenset()
        )
        self.transport = OfficialTransport(
            token=token,
            config=config,
            transport_handler=httpx.MockTransport(handler),
        )


class FrameRecorder:
    """记录投递给集成回调的帧（seq, closed）序列。"""

    def __init__(self) -> None:
        self.frames: List[Tuple[int, bool]] = []
        self.error: Optional[BaseException] = None

    async def __call__(self, frame: NotifyFrame) -> None:
        self.frames.append((frame.seq, frame.closed))


class EventRecorder:
    """记录观察者事件。"""

    def __init__(self) -> None:
        self.events: List[NotifyStreamEvent] = []

    async def __call__(self, event: NotifyStreamEvent) -> None:
        self.events.append(event)


def make_client(
    script: list,
    *,
    budget: Optional[StreamBudget] = None,
    frames: Optional[FrameRecorder] = None,
    events: Optional[EventRecorder] = None,
    on_frame=None,
    config: Optional[NotifyStreamConfig] = None,
    clock: Optional[FakeClock] = None,
):
    """构造脚本化传输、时钟与客户端，返回 (client, fake_transport, clock)。"""

    fake = ScriptedNotifyTransport(TOKEN, script)
    test_clock = clock if clock is not None else FakeClock()
    client = SSENotifyClient(
        GAME_ID,
        fake.transport,
        budget=budget,
        on_frame=on_frame if on_frame is not None else frames,
        on_event=events,
        config=config,
        monotonic_clock=test_clock.monotonic,
        sleep=instant_sleep(test_clock),
    )
    return client, fake, test_clock


def closed_line(seq: int, closed: bool = False) -> str:
    if closed:
        return 'data: {"seq": %d, "closed": true}' % seq
    return 'data: {"seq": %d}' % seq


NOT_FOUND = lambda attempt: httpx.Response(404, json={"code": "GAME_NOT_FOUND"})


class TestParseNotifyFrame:
    def test_frame_seq_only(self) -> None:
        frame = parse_notify_frame('{"seq": 7}')
        assert frame.seq == 7
        assert frame.closed is False

    def test_frame_closed_markers(self) -> None:
        assert parse_notify_frame('{"seq": 3, "closed": true}').closed is True
        assert parse_notify_frame('{"seq": 3, "closed": false}').closed is False

    def test_unknown_keys_tolerated_for_forward_compat(self) -> None:
        # v12 引入后官方可能修订帧格式：未知键忽略（与 dto.py 同原则）
        frame = parse_notify_frame('{"seq": 1, "extra": {"a": 1}, "note": "x"}')
        assert frame.seq == 1
        assert frame.closed is False

    @pytest.mark.parametrize("payload", ["{}", '{"seq": "3"}', '{"seq": true}', '{"seq": 1.5}', '{"seq": -1}'])
    def test_bad_seq_rejected(self, payload: str) -> None:
        with pytest.raises(DtoError):
            parse_notify_frame(payload)

    def test_closed_must_be_bool(self) -> None:
        with pytest.raises(DtoError):
            parse_notify_frame('{"seq": 1, "closed": 1}')

    @pytest.mark.parametrize("payload", ["not-json", "[1, 2]", '"seq"'])
    def test_bad_shape_rejected(self, payload: str) -> None:
        with pytest.raises(DtoError):
            parse_notify_frame(payload)


class TestStreamBudget:
    def test_defaults_and_official_cap(self) -> None:
        assert OFFICIAL_SSE_CONCURRENT_LIMIT == 32
        assert DEFAULT_LOCAL_STREAM_BUDGET == 24  # M 上限 16 场 × 1 流 + 8 余量
        budget = StreamBudget()
        assert budget.max_streams == 24
        assert budget.active == 0
        assert budget.available == 24

    def test_acquire_release_roundtrip(self) -> None:
        budget = StreamBudget(max_streams=2)
        assert budget.try_acquire() is True
        assert budget.try_acquire() is True
        assert budget.try_acquire() is False  # 预算耗尽
        budget.release()
        assert budget.available == 1
        assert budget.try_acquire() is True
        budget.release()
        budget.release()  # 重复归还幂等，不低于 0
        assert budget.active == 0

    @pytest.mark.parametrize("bad", [0, 33, -1, True, "32", 1.5])
    def test_validation_rejects(self, bad) -> None:
        with pytest.raises(ValueError):
            StreamBudget(max_streams=bad)


class TestHappyPath:
    async def test_initial_change_keepalive_then_game_gone(self) -> None:
        frames = FrameRecorder()
        events = EventRecorder()
        client, fake, clock = make_client(
            [
                sse_response(
                    [
                        'data: {"seq": 10}',
                        "",  # SSE 事件分隔空行
                        ": keepalive",
                        'data: {"seq": 11}',
                        "",
                        ": keepalive",
                        'data: {"seq": 12}',
                        "",
                        closed_line(12, closed=True),
                        "",
                    ]
                ),
                NOT_FOUND,
            ],
            frames=frames,
            events=events,
        )
        result = await client.run()
        # 初始帧(10)+两条变更帧(11,12)+closed 帧(12)；keepalive 与空行不产生帧
        assert frames.frames == [(10, False), (11, False), (12, False), (12, True)]
        assert result.kind is NotifyEndKind.TERMINAL
        assert isinstance(result.error, NotFoundError)
        assert result.error.official_code == "GAME_NOT_FOUND"
        assert result.initial_watermark == 10
        assert result.last_watermark == 12
        assert result.frames_delivered == 4
        assert result.reconnects == 1
        assert fake.open_count == 2
        assert fake.seen_paths == [
            "/api/games/{}/notify".format(GAME_ID),
            "/api/games/{}/notify".format(GAME_ID),
        ]
        assert all(auth == "Bearer " + TOKEN for auth in fake.seen_auth)
        kinds = [e.kind for e in events.events]
        assert kinds == [
            NotifyEventKind.STREAM_OPENED.value,
            NotifyEventKind.FRAME.value,
            NotifyEventKind.FRAME.value,
            NotifyEventKind.FRAME.value,
            NotifyEventKind.FRAME.value,
            NotifyEventKind.STREAM_ENDED.value,
            NotifyEventKind.RECONNECT_SCHEDULED.value,
            NotifyEventKind.STREAM_OPENED.value,
            NotifyEventKind.RUN_FINISHED.value,
        ]
        assert events.events[-1].run_kind == NotifyEndKind.TERMINAL.value
        assert events.events[-1].error_kind == "NotFoundError"
        # 水位只在帧事件中携带；closed 帧的标记随事件可见
        assert events.events[4].seq == 12
        assert events.events[4].closed is True
        assert events.events[5].end_reason == "closed_frame"
        # 重连后 404 是终态：时钟只前进了第一次退避
        assert clock.monotonic() == 1000.0 + 0.5


class TestClosedReconnectAlignment:
    async def test_closed_reconnects_and_realigns_on_initial_frame(self) -> None:
        frames = FrameRecorder()
        events = EventRecorder()
        client, fake, clock = make_client(
            [
                sse_response([closed_line(5), "", closed_line(5, closed=True), ""]),
                sse_response([closed_line(9), "", closed_line(10), ""]),  # EOF 无 closed：断连分类
                NOT_FOUND,
            ],
            frames=frames,
            events=events,
            config=NotifyStreamConfig(max_reconnects=2, backoff_base_sec=0.5),
        )
        result = await client.run()
        # 第二条流 EOF 断连后重连：新流初始帧 seq=9 是对齐点
        assert frames.frames == [(5, False), (5, True), (9, False), (10, False)]
        assert result.initial_watermark == 9
        assert result.last_watermark == 10
        assert result.reconnects == 2
        assert result.kind is NotifyEndKind.TERMINAL
        scheduled = [e for e in events.events if e.kind == NotifyEventKind.RECONNECT_SCHEDULED.value]
        assert len(scheduled) == 2
        assert scheduled[0].error_kind is None  # closed 帧后的正常重连
        assert scheduled[1].error_kind == "UncertainTransportError"  # EOF 断连
        assert clock.monotonic() == 1000.0 + 0.5 + 1.0


class TestSlowConsumerDisconnect:
    async def test_midstream_disconnect_is_recoverable_and_reconnects(self) -> None:
        frames = FrameRecorder()
        events = EventRecorder()
        client, fake, clock = make_client(
            [
                sse_response(
                    [closed_line(1), "", closed_line(2), ""], fail_after=2
                ),  # 第 3 行产出前断连（慢消费者被服务器踢掉）
                sse_response([closed_line(3), "", closed_line(3, closed=True), ""]),
                NOT_FOUND,
            ],
            frames=frames,
            events=events,
            config=NotifyStreamConfig(max_reconnects=2, backoff_base_sec=0.5),
        )
        result = await client.run()
        assert frames.frames == [(1, False), (3, False), (3, True)]
        assert result.reconnects == 2
        assert result.kind is NotifyEndKind.TERMINAL
        scheduled = [e for e in events.events if e.kind == NotifyEventKind.RECONNECT_SCHEDULED.value]
        assert scheduled[0].error_kind == "UncertainTransportError"
        assert scheduled[0].backoff_sec == 0.5
        # 断连退避 0.5 + closed 后重连退避 1.0
        assert clock.monotonic() == 1000.0 + 1.5
        assert client.event_hook_errors == 0


class TestRateLimitBackoff:
    async def test_429_backs_off_at_least_retry_after(self) -> None:
        frames = FrameRecorder()
        events = EventRecorder()
        client, fake, clock = make_client(
            [
                lambda attempt: httpx.Response(
                    429,
                    headers={"Retry-After": "2.5"},
                    json={"code": "RATE_LIMITED"},
                ),
                sse_response([closed_line(1), "", closed_line(1, closed=True), ""]),
                NOT_FOUND,
            ],
            frames=frames,
            events=events,
            config=NotifyStreamConfig(max_reconnects=2, backoff_base_sec=0.5),
        )
        result = await client.run()
        assert frames.frames == [(1, False), (1, True)]
        assert result.reconnects == 2
        assert result.kind is NotifyEndKind.TERMINAL
        scheduled = [e for e in events.events if e.kind == NotifyEventKind.RECONNECT_SCHEDULED.value]
        assert len(scheduled) == 2
        assert scheduled[0].error_kind == "RateLimitedError"
        assert scheduled[0].backoff_sec == 2.5  # max(退避 0.5, Retry-After 2.5)
        assert scheduled[1].error_kind is None  # closed 帧后的正常重连
        assert clock.monotonic() == 1000.0 + 2.5 + 1.0


class TestBudget:
    async def test_budget_exhausted_never_connects(self) -> None:
        budget = StreamBudget(max_streams=1)
        assert budget.try_acquire() is True  # 模拟同 Token 他场占满预算
        frames = FrameRecorder()
        client, fake, clock = make_client(
            [sse_response([closed_line(1), closed_line(1, closed=True)]), NOT_FOUND],
            budget=budget,
            frames=frames,
        )
        result = await client.run()  # 默认 budget_wait_sec=None：立即返回，不等待
        assert result.kind is NotifyEndKind.BUDGET_UNAVAILABLE
        assert result.reconnects == 0
        assert frames.frames == []
        assert fake.open_count == 0  # 超预算不发起任何连接
        assert budget.active == 1  # 测试占用的槽不受影响

    async def test_budget_wait_acquires_slot_when_released(self) -> None:
        budget = StreamBudget(max_streams=1)
        assert budget.try_acquire() is True
        frames = FrameRecorder()
        client, fake, clock = make_client(
            [sse_response([closed_line(7), "", closed_line(7, closed=True), ""]), NOT_FOUND],
            budget=budget,
            frames=frames,
            config=NotifyStreamConfig(budget_wait_sec=10.0, backoff_base_sec=0.5),
        )
        task = asyncio.ensure_future(client.run())
        await asyncio.sleep(0)  # 让 run 进入等待预算的轮询
        budget.release()  # 他场归还槽位
        result = await task
        assert result.kind is NotifyEndKind.TERMINAL
        assert frames.frames == [(7, False), (7, True)]
        assert fake.open_count == 2
        assert budget.active == 0  # run 结束归还自己的槽


class TestTerminalErrors:
    async def test_auth_failure_is_terminal_without_reconnect(self) -> None:
        events = EventRecorder()
        client, fake, clock = make_client(
            [lambda attempt: httpx.Response(401, json={"code": "UNAUTHORIZED"})],
            events=events,
        )
        result = await client.run()
        assert result.kind is NotifyEndKind.TERMINAL
        assert isinstance(result.error, AuthError)
        assert result.error.official_code == "UNAUTHORIZED"
        assert result.reconnects == 0
        assert result.frames_delivered == 0
        assert fake.open_count == 1  # 认证失败绝不重连
        assert events.events[-1].run_kind == NotifyEndKind.TERMINAL.value
        assert events.events[-1].error_kind == "AuthError"
        assert clock.monotonic() == 1000.0  # 无退避等待

    async def test_forbidden_is_terminal(self) -> None:
        client, fake, clock = make_client(
            [lambda attempt: httpx.Response(403, json={"code": "FORBIDDEN"})]
        )
        result = await client.run()
        assert result.kind is NotifyEndKind.TERMINAL
        assert isinstance(result.error, ForbiddenError)
        assert fake.open_count == 1

    async def test_conflict_is_terminal(self) -> None:
        client, fake, clock = make_client(
            [lambda attempt: httpx.Response(409, json={"code": "INVALID_ACTION"})]
        )
        result = await client.run()
        assert result.kind is NotifyEndKind.TERMINAL
        assert isinstance(result.error, ConflictError)
        assert fake.open_count == 1


class TestReconnectExhaustion:
    async def test_bounded_reconnect_exhaustion_returns_recoverable_failure(self) -> None:
        events = EventRecorder()
        client, fake, clock = make_client(
            [sse_response([]), sse_response([]), sse_response([])],  # 三次 EOF 断连
            events=events,
            config=NotifyStreamConfig(max_reconnects=2, backoff_base_sec=0.5),
        )
        result = await client.run()
        assert result.kind is NotifyEndKind.RECONNECTS_EXHAUSTED  # 可恢复失败，非终态
        assert isinstance(result.error, UncertainTransportError)
        assert result.error.detail == "sse:eof_without_closed_frame"
        assert result.reconnects == 2
        assert fake.open_count == 3  # 1 次首连 + 2 次有界重连
        assert clock.monotonic() == 1000.0 + 0.5 + 1.0  # 指数退避 0.5 → 1.0
        assert events.events[-1].run_kind == NotifyEndKind.RECONNECTS_EXHAUSTED.value
        assert events.events[-1].error_kind == "UncertainTransportError"
        assert client.event_hook_errors == 0

    async def test_exhausted_client_can_rerun(self) -> None:
        """耗尽是可恢复失败：调用方可稍后再次 run()（不终态化实例）。"""

        frames = FrameRecorder()
        script = [sse_response([]), sse_response([]), sse_response([]), NOT_FOUND]
        client, fake, clock = make_client(
            script, frames=frames, config=NotifyStreamConfig(max_reconnects=2)
        )
        first = await client.run()
        assert first.kind is NotifyEndKind.RECONNECTS_EXHAUSTED
        second = await client.run()
        assert second.kind is NotifyEndKind.TERMINAL
        assert isinstance(second.error, NotFoundError)


class TestMalformedFrame:
    async def test_malformed_frame_is_recoverable_and_reconnects(self) -> None:
        frames = FrameRecorder()
        events = EventRecorder()
        client, fake, clock = make_client(
            [
                sse_response(["data: not-json"]),
                sse_response([closed_line(7), "", closed_line(7, closed=True), ""]),
                NOT_FOUND,
            ],
            frames=frames,
            events=events,
        )
        result = await client.run()
        assert frames.frames == [(7, False), (7, True)]
        assert result.kind is NotifyEndKind.TERMINAL
        scheduled = [e for e in events.events if e.kind == NotifyEventKind.RECONNECT_SCHEDULED.value]
        assert scheduled[0].error_kind == "DtoError"


class TestDesensitization:
    async def test_token_never_leaks_through_frames_events_or_results(self) -> None:
        frames = FrameRecorder()
        events = EventRecorder()
        client, fake, clock = make_client(
            [
                sse_response(
                    [
                        'data: {"seq": 1, "note": "%s"}' % TOKEN,  # 帧内回显 Token
                        "",
                        closed_line(1, closed=True),
                        "",
                    ]
                ),
                lambda attempt: httpx.Response(
                    404,
                    json={"code": "GAME_NOT_FOUND", "note": TOKEN},  # 错误体回显 Token
                ),
            ],
            frames=frames,
            events=events,
        )
        result = await client.run()
        # 帧只投递 seq/closed：未知键（含 Token）被丢弃
        assert frames.frames == [(1, False), (1, True)]
        assert result.kind is NotifyEndKind.TERMINAL
        for blob in [repr(result), str(result.error)] + [repr(e) for e in events.events]:
            assert TOKEN not in blob
        assert isinstance(result.error, NotFoundError)
        assert result.error.official_code == "GAME_NOT_FOUND"


class TestCallbackAndGuards:
    async def test_on_frame_exception_propagates_and_budget_released(self) -> None:
        budget = StreamBudget(max_streams=2)

        async def broken(frame: NotifyFrame) -> None:
            raise RuntimeError("consumer broken")

        client, fake, clock = make_client(
            [sse_response([closed_line(1), "", closed_line(1, closed=True), ""])],
            budget=budget,
            on_frame=broken,
        )
        with pytest.raises(RuntimeError, match="consumer broken"):
            await client.run()
        assert budget.available == budget.max_streams  # 槽已归还
        assert fake.open_count == 1

    async def test_concurrent_run_rejected(self) -> None:
        gate = asyncio.Event()
        client, fake, clock = make_client(
            [sse_response([], block_event=gate)]
        )
        task = asyncio.ensure_future(client.run())
        await asyncio.sleep(0)
        with pytest.raises(RuntimeError, match="不允许并发"):
            await client.run()
        await client.aclose()
        result = await task
        assert result.kind is NotifyEndKind.CANCELLED

    async def test_run_after_aclose_rejected(self) -> None:
        client, fake, clock = make_client([sse_response([])])
        await client.aclose()
        with pytest.raises(RuntimeError, match="不可复用"):
            await client.run()

    def test_game_id_validated(self) -> None:
        fake = ScriptedNotifyTransport(TOKEN, [sse_response([])])
        with pytest.raises(ValueError):
            SSENotifyClient("   ", fake.transport)


class TestCancellation:
    async def test_graceful_aclose_returns_cancelled_result(self) -> None:
        budget = StreamBudget(max_streams=2)
        frames = FrameRecorder()
        client, fake, clock = make_client(
            [sse_response([closed_line(1), ""], repeat=True)],  # 无限流，逐行让出
            budget=budget,
            frames=frames,
        )
        task = asyncio.ensure_future(client.run())
        for _ in range(10):
            await asyncio.sleep(0)
        assert len(frames.frames) >= 2
        await client.aclose()
        result = await task
        assert result.kind is NotifyEndKind.CANCELLED
        assert budget.available == budget.max_streams
        assert result.last_watermark == 1

    async def test_aclose_force_cancels_blocked_read(self) -> None:
        """静默挂起的读无法优雅返回：aclose 强制取消任务，run 仍返回 CANCELLED。"""

        budget = StreamBudget(max_streams=2)
        client, fake, clock = make_client(
            [sse_response([], block_event=asyncio.Event())],
            budget=budget,
        )
        task = asyncio.ensure_future(client.run())
        await asyncio.sleep(0)
        await client.aclose()
        result = await task  # uncancel 后返回结果而非抛 CancelledError
        assert result.kind is NotifyEndKind.CANCELLED
        assert budget.available == budget.max_streams

    async def test_external_cancel_propagates_and_releases_budget(self) -> None:
        budget = StreamBudget(max_streams=2)
        client, fake, clock = make_client(
            [sse_response([], block_event=asyncio.Event())],
            budget=budget,
        )
        task = asyncio.ensure_future(client.run())
        await asyncio.sleep(0)
        task.cancel()  # 外部取消（非 aclose）：按标准协程语义传播
        with pytest.raises(asyncio.CancelledError):
            await task
        assert budget.available == budget.max_streams


class TestTransportSseStream:
    """传输层 open_sse_stream 的行为（fake 流）。"""

    def _transport(self, script: list):
        return ScriptedNotifyTransport(TOKEN, script)

    async def test_stream_yields_raw_lines(self) -> None:
        fake = self._transport(
            [sse_response([": keepalive", 'data: {"seq": 1}', ""])]
        )
        async with fake.transport.open_sse_stream("/api/games/g/notify") as lines:
            got = [line async for line in lines]
        assert got == [": keepalive", 'data: {"seq": 1}', ""]

    async def test_401_classified(self) -> None:
        fake = self._transport(
            [lambda attempt: httpx.Response(401, json={"code": "UNAUTHORIZED"})]
        )
        with pytest.raises(AuthError) as exc_info:
            async with fake.transport.open_sse_stream("/api/games/g/notify"):
                pass
        assert exc_info.value.official_code == "UNAUTHORIZED"

    async def test_429_carries_retry_after(self) -> None:
        fake = self._transport(
            [
                lambda attempt: httpx.Response(
                    429,
                    headers={"Retry-After": "3"},
                    json={"code": "RATE_LIMITED"},
                )
            ]
        )
        with pytest.raises(RateLimitedError) as exc_info:
            async with fake.transport.open_sse_stream("/api/games/g/notify"):
                pass
        assert exc_info.value.retry_after_seconds == 3.0

    async def test_404_classified(self) -> None:
        fake = self._transport([NOT_FOUND])
        with pytest.raises(NotFoundError) as exc_info:
            async with fake.transport.open_sse_stream("/api/games/g/notify"):
                pass
        assert exc_info.value.official_code == "GAME_NOT_FOUND"

    async def test_midstream_disconnect_maps_to_uncertain(self) -> None:
        fake = self._transport(
            [sse_response(['data: {"seq": 1}', 'data: {"seq": 2}'], fail_after=1)]
        )
        with pytest.raises(UncertainTransportError) as exc_info:
            async with fake.transport.open_sse_stream("/api/games/g/notify") as lines:
                async for _ in lines:
                    pass
        assert exc_info.value.detail == "transport:ReadError"

    async def test_connect_error_maps_to_uncertain(self) -> None:
        fake = self._transport([httpx.ConnectError("connection refused")])
        with pytest.raises(UncertainTransportError):
            async with fake.transport.open_sse_stream("/api/games/g/notify"):
                pass

    async def test_error_body_token_redacted(self) -> None:
        fake = self._transport(
            [
                lambda attempt: httpx.Response(
                    429,
                    headers={"Retry-After": "1"},
                    json={"code": "RATE_LIMITED", "note": TOKEN},
                )
            ]
        )
        with pytest.raises(RateLimitedError) as exc_info:
            async with fake.transport.open_sse_stream("/api/games/g/notify"):
                pass
        assert TOKEN not in str(exc_info.value)
        assert TOKEN not in exc_info.value.detail

    def test_sse_read_timeout_default(self) -> None:
        config = TransportConfig(base_url="https://x", insecure_hosts=frozenset())
        assert config.sse_read_timeout_sec == 75.0  # 30s keepalive × 2 + 余量
