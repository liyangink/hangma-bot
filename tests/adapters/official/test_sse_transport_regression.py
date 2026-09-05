"""open_sse_stream 的 httpx extensions 形态回归（2026-09-05 活场实测缺陷）。

缺陷：request.extensions["timeout"] 直接放 httpx.Timeout 对象，httpcore
在连接池层执行 timeouts.get("pool") 时 AttributeError（SSE 首连即失败，
集成层降级长轮询兜住）。修复：转为 dict（timeout.as_dict()）。
本测试在真实 httpx AsyncClient 层拦截 send，验证 extensions 形态。
"""

from __future__ import annotations

import asyncio
import httpx
import pytest

from hangma_bot.adapters.official.transport import OfficialTransport, TransportConfig


class _CapturingSend:
    """拦截 httpx AsyncClient.send，捕获 request.extensions 后返回 401 终态。"""

    def __init__(self) -> None:
        self.captured_extensions = None

    async def __call__(self, request, *, stream=False, **kw):
        self.captured_extensions = dict(request.extensions)
        return httpx.Response(401, request=request)


class TestSseTimeoutExtensions:
    @pytest.mark.asyncio
    async def test_extensions_timeout_is_dict(self) -> None:
        transport = OfficialTransport(
            "token-x",
            TransportConfig(base_url="https://127.0.0.1:1", insecure_hosts=frozenset({"127.0.0.1"})),
        )
        capture = _CapturingSend()
        transport._client.send = capture  # 拦截真实 httpx 客户端层
        with pytest.raises(Exception):
            async with transport.open_sse_stream("/api/games/g/notify"):
                pass
        assert capture.captured_extensions is not None, "send 应被调用"
        timeout_ext = capture.captured_extensions.get("timeout")
        assert isinstance(timeout_ext, dict), (
            "extensions['timeout'] 必须是 dict（httpcore 以 .get('pool') 读取），"
            "得到 {0!r}".format(type(timeout_ext))
        )
        assert set(timeout_ext) >= {"connect", "read", "write", "pool"}
        await transport.aclose()
