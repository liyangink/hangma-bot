"""每 Token 一个的官方 HTTP 传输（官方适配器内部实现）。

职责：Bearer 认证注入、连接池生命周期、单次请求执行与错误分类。
不做重试（重试属于调用方与调度器的预算决策），不记录 Token——
Token 只存在于实例属性与请求头，异常与结果对象均不携带。

TLS：仅当 base_url 主机命中配置的固定内网主机白名单时关闭证书校验；
禁止全局关闭（根 AGENTS.md §6、API 文档 §1）。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, FrozenSet, Mapping, Optional, Tuple
from urllib.parse import urlparse

import httpx

from .errors import (
    AuthError,
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    OfficialError,
    RateLimitedError,
    RecoverableServerError,
    UncertainTransportError,
    sanitize,
)
from .dto import extract_error_code


@dataclass(frozen=True)
class TransportConfig:
    """传输配置；所有时间字段单位为秒。"""

    base_url: str
    insecure_hosts: FrozenSet[str]  # 允许关闭 TLS 校验的官方内网主机集合
    connect_timeout_sec: float = 3.0
    read_timeout_sec: float = 10.0
    long_poll_read_timeout_sec: float = 35.0  # 30 秒长轮询挂起 + 余量（API 文档 §5.1）
    write_timeout_sec: float = 5.0
    pool_timeout_sec: float = 5.0
    max_connections: int = 40  # 覆盖 1 赛事 + M 场并发（上限 16 场 × 轮询 + 动作）
    max_keepalive_connections: int = 24


@dataclass(frozen=True)
class TransportResult:
    """单次成功响应；只保留状态码与文本，不含响应头（防凭证泄漏）。"""

    status: int
    text: str


class OfficialTransport:
    """一个 Token 恰好一个实例；其赛事与全部场次共享（接口协议 §6）。"""

    def __init__(
        self,
        token: str,
        config: TransportConfig,
        *,
        transport_handler: Optional[httpx.AsyncBaseTransport] = None,  # 测试注入
    ) -> None:
        self._token = token
        self._config = config
        host = (urlparse(config.base_url).hostname or "").lower()
        # 仅对白名单内的固定内网主机关闭校验；其余主机一律校验
        self._tls_verify: bool = host not in {h.lower() for h in config.insecure_hosts}
        timeout = httpx.Timeout(
            connect=config.connect_timeout_sec,
            read=config.read_timeout_sec,
            write=config.write_timeout_sec,
            pool=config.pool_timeout_sec,
        )
        self._client = httpx.AsyncClient(
            base_url=config.base_url,
            verify=self._tls_verify,
            timeout=timeout,
            limits=httpx.Limits(
                max_connections=config.max_connections,
                max_keepalive_connections=config.max_keepalive_connections,
            ),
            transport=transport_handler,
        )

    @property
    def tls_verify(self) -> bool:
        """当前 TLS 校验状态；启动日志据此记录 tls_verify=false。"""

        return self._tls_verify

    async def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[Mapping[str, Any]] = None,
        params: Optional[Mapping[str, Any]] = None,
        with_auth: bool = True,
        long_poll: bool = False,
        request_budget_sec: Optional[float] = None,
    ) -> TransportResult:
        """执行单次请求；任何失败都以 OfficialError 子类抛出，不重试。

        request_budget_sec 是整次请求的墙钟预算：各阶段超时收紧到
        min(配置值, 预算)，并用 asyncio.timeout 对整个请求兜底——
        分阶段上限可累计越界，总预算由外部取消保证。预算耗尽的取消
        按结果不确定处理（对 GET 只是可重试分类，对 POST 由调用方
        的模糊封锁路径接管）。默认按 long_poll 选择预设。
        """

        headers = {"Content-Type": "application/json"}
        if with_auth:
            headers["Authorization"] = "Bearer {}".format(self._token)
        default_read = (
            self._config.long_poll_read_timeout_sec
            if long_poll
            else self._config.read_timeout_sec
        )

        def _clamp(configured: float) -> float:
            if request_budget_sec is None:
                return configured
            return min(configured, request_budget_sec)

        timeout = httpx.Timeout(
            connect=_clamp(self._config.connect_timeout_sec),
            read=_clamp(default_read),
            write=_clamp(self._config.write_timeout_sec),
            pool=_clamp(self._config.pool_timeout_sec),
        )

        async def _send() -> "httpx.Response":
            if request_budget_sec is not None:
                # 整次请求的硬预算兜底（含连接池等待）
                async with asyncio.timeout(request_budget_sec):
                    return await self._client.request(
                        method, path, json=json_body, params=params, headers=headers, timeout=timeout
                    )
            return await self._client.request(
                method, path, json=json_body, params=params, headers=headers, timeout=timeout
            )

        try:
            response = await _send()
        except asyncio.TimeoutError:
            raise UncertainTransportError("timeout:request_budget") from None
        except httpx.TimeoutException as exc:
            raise UncertainTransportError("timeout:{}".format(type(exc).__name__)) from None
        except httpx.TransportError as exc:
            raise UncertainTransportError("transport:{}".format(type(exc).__name__)) from None
        text = response.text
        status = response.status_code
        # 持有 Token 的边界对所有响应体（含 2xx）先做精确替换：协议错误
        # 消息（DtoError/GameFailed.reason）可能回显字段值，任何形态的
        # 当前 Token 都不得离开传输层
        if self._token:
            text = text.replace(self._token, "***")
        if 200 <= status < 300:
            return TransportResult(status=status, text=text)
        code = extract_error_code(status, text)
        detail = sanitize(text or "")
        if status == 401:
            raise AuthError(status, code, detail)
        if status == 400:
            raise BadRequestError(status, code, detail)
        if status == 403:
            raise ForbiddenError(status, code, detail)
        if status == 404:
            raise NotFoundError(status, code, detail)
        if status == 409:
            raise ConflictError(status, code, detail)
        if status == 429:
            retry_after: Optional[float] = None
            header_value = response.headers.get("Retry-After")
            if header_value:
                try:
                    retry_after = float(header_value)
                except ValueError:
                    retry_after = None
            raise RateLimitedError(status, code, detail, retry_after)
        if 500 <= status < 600:
            raise RecoverableServerError(status, code, detail)
        raise OfficialError(status, code, detail)

    async def aclose(self) -> None:
        """释放当前 Token 的连接池；关闭后实例不可复用。"""

        await self._client.aclose()

