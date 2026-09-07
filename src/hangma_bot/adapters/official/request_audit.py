"""每次真实 HTTP 调用的开始与终结存证；不负责重试或动作决策。

请求编号按实际调用生成，取消也必须终结。短元数据走高优先级审计，
响应正文走原始事件流；正文被记录器淘汰时仍能发现具体缺失请求。
"""
from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager, contextmanager

from hangma_bot.application.contracts import AuditKind


@contextmanager
def request_trace(emit, clock, method, path, *, timing=None, params=None, json_body=None,
                  raw_source=None, raw_fields=None):
    """围绕实际传输调用存证；调用方填 result，失败和取消自动保留分类。

timing 的值使用本进程单调时钟秒；queued_at 是调度排队起点，
transport_started_at 只是客户端调用时刻，并不冒充服务器收包时刻。
raw_source 为空时由既有 state/action 解析路径保存同 request_id 的正文。
emit 必须遵循审计非阻塞、失败不抛的契约。
"""
    timing = timing if timing is not None else {}
    timing.update(request_id=uuid.uuid4().hex, transport_started_at_monotonic=clock())
    trace = {"result": None}
    common = {"request_id": timing["request_id"], "endpoint": method + " " + path,
              "method": method, "params": dict(params or {}), "body": dict(json_body or {})}
    emit(AuditKind.HTTP_REQUEST, {**common, "phase": "started", "request_timing": dict(timing)})
    status, raw, error, outcome, headers = None, "", None, "response", {}
    try:
        yield trace
        result = trace["result"]
        if result is not None:
            status, raw = result.status, result.text
            headers = dict(getattr(result, "response_headers", {}))
    except BaseException as exc:
        outcome = "cancelled" if isinstance(exc, asyncio.CancelledError) else "error"
        if hasattr(exc, "retry_after_seconds"):
            timing["retry_after_seconds"] = exc.retry_after_seconds
        error = type(exc).__name__  # 异常文本可能含凭证；分类名足够关联失败路径。
        opened = trace["result"]
        status = getattr(exc, "http_status", None) or getattr(opened, "status", None)
        raw = getattr(exc, "raw_text", None) or ""
        headers = dict(getattr(exc, "response_headers", {}) or getattr(opened, "response_headers", {}))
        raise
    finally:
        timing.update(completed_at_monotonic=clock(), response_headers=headers,
                      outcome=outcome, error_type=error)
        emit(AuditKind.HTTP_REQUEST, {**common, "phase": "finished", "outcome": outcome,
             "http_status": status, "error_type": error, "request_timing": dict(timing)})
        if raw_source is not None:
            emit(AuditKind.RAW_PROTOCOL_STATE, {**common, **(raw_fields or {}),
                 "payload_schema_version": 1, "source": raw_source,
                 "http_status": status, "raw": raw, "request_timing": dict(timing)})


async def audited_request(transport, emit, clock, method, path, *, timing=None,
                          raw_source="http_response", raw_fields=None, **kwargs):
    """单次传输原样返回/抛出；全部出口有 request_id、耗时与脱敏原文。"""
    with request_trace(emit, clock, method, path, timing=timing,
                       params=kwargs.get("params"), json_body=kwargs.get("json_body"),
                       raw_source=raw_source, raw_fields=raw_fields) as trace:
        result = await transport.request(method, path, **kwargs)
        trace["result"] = result
        return result


@asynccontextmanager
async def audited_sse_stream(transport, emit, clock, path):
    """通知流记录真实连接生命周期；逐帧正文仍由通知客户端单独存证。"""
    with request_trace(emit, clock, "GET", path, raw_source="notify_response") as trace:
        async with transport.open_sse_stream(path) as lines:
            # 正式传输返回含状态码/白名单头的可迭代流，测试流可只实现迭代。
            if hasattr(lines, "status"):
                trace["result"] = lines
            yield lines
