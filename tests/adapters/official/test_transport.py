"""传输层测试：TLS 白名单、认证脱敏与 HTTP 错误分类。"""
from __future__ import annotations

import httpx
import pytest

from hangma_bot.adapters.official.errors import (
    AuthError,
    ConflictError,
    RateLimitedError,
    RecoverableServerError,
    UncertainTransportError,
    sanitize,
)
from hangma_bot.adapters.official.transport import OfficialTransport, TransportConfig


def _transport(base_url: str, insecure_hosts, handler=None) -> OfficialTransport:
    config = TransportConfig(base_url=base_url, insecure_hosts=frozenset(insecure_hosts))
    return OfficialTransport(
        token="secret-token-abcdef123456",
        config=config,
        transport_handler=handler,
    )


class TestTlsPolicy:
    def test_insecure_host_whitelist_disables_verify(self) -> None:
        """仅配置的固定内网主机关闭证书校验。"""

        transport = _transport("https://10.240.169.190:18080", {"10.240.169.190"})
        assert transport.tls_verify is False

    def test_other_hosts_keep_verification(self) -> None:
        """白名单外主机（即使同一配置携带白名单）一律校验。"""

        transport = _transport("https://official.example.com", {"10.240.169.190"})
        assert transport.tls_verify is True

    def test_empty_whitelist_always_verifies(self) -> None:
        transport = _transport("https://10.240.169.190:18080", {})
        assert transport.tls_verify is True

    async def test_configured_internal_host_bypasses_system_proxy(self, monkeypatch) -> None:
        """内网官方主机可直连时，不得被系统代理导向不可达节点。"""

        hits = {"target": 0, "proxy": 0}

        async def serve(reader, writer, *, kind: str, status: int) -> None:
            await reader.readuntil(b"\r\n\r\n")
            hits[kind] += 1
            writer.write(
                f"HTTP/1.1 {status} {'OK' if status == 200 else 'Bad Gateway'}\r\n"
                "Content-Length: 2\r\nConnection: close\r\n\r\n{}".encode()
            )
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        import asyncio

        target = await asyncio.start_server(
            lambda r, w: serve(r, w, kind="target", status=200), "127.0.0.1", 0
        )
        proxy = await asyncio.start_server(
            lambda r, w: serve(r, w, kind="proxy", status=502), "127.0.0.1", 0
        )
        target_port = target.sockets[0].getsockname()[1]
        proxy_port = proxy.sockets[0].getsockname()[1]
        monkeypatch.setenv("HTTP_PROXY", f"http://127.0.0.1:{proxy_port}")
        monkeypatch.setenv("ALL_PROXY", f"http://127.0.0.1:{proxy_port}")
        monkeypatch.setenv("NO_PROXY", "")
        transport = _transport(f"http://127.0.0.1:{target_port}", {"127.0.0.1"})
        try:
            response = await transport.request("GET", "/portal/api/guide/version", with_auth=False)
            assert response.status == 200
            assert hits == {"target": 1, "proxy": 0}
            public_policy = _transport(f"http://127.0.0.1:{target_port}", set())
            try:
                with pytest.raises(RecoverableServerError):
                    await public_policy.request("GET", "/portal/api/guide/version", with_auth=False)
                assert hits == {"target": 1, "proxy": 1}
            finally:
                await public_policy.aclose()
        finally:
            await transport.aclose()
            target.close()
            proxy.close()
            await target.wait_closed()
            await proxy.wait_closed()


class TestErrorClassification:
    async def test_success_returns_result_without_headers(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["Authorization"] == "Bearer secret-token-abcdef123456"
            return httpx.Response(200, json={"ok": True})

        transport = _transport("https://h.example", set(), httpx.MockTransport(handler))
        result = await transport.request("GET", "/api/me")
        assert result.status == 200

    async def test_401_maps_to_auth_error(self) -> None:
        handler = httpx.MockTransport(lambda req: httpx.Response(401, json={"code": "UNAUTHORIZED"}))
        transport = _transport("https://h.example", set(), handler)
        with pytest.raises(AuthError) as exc_info:
            await transport.request("GET", "/api/me")
        assert exc_info.value.official_code == "UNAUTHORIZED"

    async def test_409_maps_to_conflict(self) -> None:
        handler = httpx.MockTransport(lambda req: httpx.Response(409, json={"code": "INVALID_ACTION"}))
        transport = _transport("https://h.example", set(), handler)
        with pytest.raises(ConflictError) as exc_info:
            await transport.request("POST", "/api/games/g/action", json_body={})
        assert exc_info.value.official_code == "INVALID_ACTION"

    async def test_429_carries_retry_after(self) -> None:
        handler = httpx.MockTransport(
            lambda req: httpx.Response(429, headers={"Retry-After": "2"}, json={"code": "RATE_LIMITED"})
        )
        transport = _transport("https://h.example", set(), handler)
        with pytest.raises(RateLimitedError) as exc_info:
            await transport.request("GET", "/api/me")
        assert exc_info.value.retry_after_seconds == 2.0

    @pytest.mark.parametrize(
        ("header", "expected"),
        [
            ("1e999", None),  # inf：曾把调度冷却推成永久挂起、冻结整个 Token（W2-1）
            ("nan", None),
            ("-3", None),
            ("2.5", 2.5),  # 有限非负值照常携带
            ("not-a-number", None),  # 解析失败原有行为
        ],
    )
    async def test_429_retry_after_malformed_values_are_ignored(
        self, header: str, expected: object
    ) -> None:
        """W2-1 回归：畸形 Retry-After 头按"未提供"处理（None），不得为 inf。"""

        handler = httpx.MockTransport(
            lambda req: httpx.Response(429, headers={"Retry-After": header}, json={"code": "RATE_LIMITED"})
        )
        transport = _transport("https://h.example", set(), handler)
        with pytest.raises(RateLimitedError) as exc_info:
            await transport.request("GET", "/api/me")
        assert exc_info.value.retry_after_seconds == expected

    async def test_503_maps_to_recoverable_server_error(self) -> None:
        handler = httpx.MockTransport(lambda req: httpx.Response(503, text="unavailable"))
        transport = _transport("https://h.example", set(), handler)
        with pytest.raises(RecoverableServerError):
            await transport.request("GET", "/api/me")

    async def test_disconnect_maps_to_uncertain(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection reset")

        transport = _transport("https://h.example", set(), httpx.MockTransport(handler))
        with pytest.raises(UncertainTransportError):
            await transport.request("POST", "/api/games/g/action", json_body={})


class TestSanitize:
    def test_bearer_token_never_survives(self) -> None:
        text = "Authorization: Bearer secret-token-abcdef123456 at /api/me"
        assert "secret-token-abcdef123456" not in sanitize(text)
        assert "Bearer ***" in sanitize(text)

    def test_long_random_secret_redacted(self) -> None:
        text = "token=abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJ"
        assert "abcdefghijklmnopqrstuvwxyz" not in sanitize(text)

    def test_detail_is_bounded(self) -> None:
        assert len(sanitize("x" * 10000)) <= 300

    def test_error_messages_do_not_leak_token(self) -> None:
        """构造异常时即使 detail 混入 Token 也会被脱敏。"""

        error = AuthError(401, "UNAUTHORIZED", "bad Bearer secret-token-abcdef123456")
        assert "secret-token-abcdef123456" not in str(error)
        assert "secret-token-abcdef123456" not in error.detail


class TestRawTextSanitization:
    """F-01 回归：异常携带的 raw_text 必须"已脱敏且完整"，红线单点防线有测试。"""

    @pytest.mark.parametrize(
        "body",
        [
            '{"code":"INVALID_ACTION","message":"rejected: secret-token-abcdef123456"}',
            '{"code":"INVALID_ACTION","message":"rejected: Bearer: secret-token-abcdef123456"}',
            '{"code":"INVALID_ACTION","message":"rejected: Bearer secret-token-abcdef123456"}',
            '{"code":"INVALID_ACTION","note":"rejected: secret-token-abcdef123456 was echoed"}',
        ],
    )
    async def test_conflict_raw_text_is_sanitized_and_complete(self, body: str) -> None:
        """4xx 响应体回显我方 Token（裸/冒号/空白 Bearer 形态）时：
        raw_text 不含 Token 原文，且其余原文完整保留（E2 审计存证语义）。"""

        handler = httpx.MockTransport(lambda req: httpx.Response(409, text=body))
        transport = _transport("https://h.example", set(), handler)
        with pytest.raises(ConflictError) as exc_info:
            await transport.request("POST", "/api/games/g/action", json_body={})
        assert exc_info.value.raw_text is not None
        assert "secret-token-abcdef123456" not in exc_info.value.raw_text
        assert '"INVALID_ACTION"' in exc_info.value.raw_text  # 原文其余部分保留
        assert "rejected" in exc_info.value.raw_text
        # str/detail 同样干净（既有边界）
        assert "secret-token-abcdef123456" not in str(exc_info.value)
        assert "secret-token-abcdef123456" not in exc_info.value.detail

    async def test_429_raw_text_is_sanitized_and_complete(self) -> None:
        handler = httpx.MockTransport(
            lambda req: httpx.Response(
                429,
                headers={"Retry-After": "2"},
                text='{"code":"RATE_LIMITED","detail":"Bearer: secret-token-abcdef123456"}',
            )
        )
        transport = _transport("https://h.example", set(), handler)
        with pytest.raises(RateLimitedError) as exc_info:
            await transport.request("GET", "/api/me")
        assert exc_info.value.raw_text is not None
        assert "secret-token-abcdef123456" not in exc_info.value.raw_text
        assert '"RATE_LIMITED"' in exc_info.value.raw_text
        assert exc_info.value.retry_after_seconds == 2.0


async def test_retry_after_http_date_and_diagnostic_headers_are_retained_without_credentials():
    token = 'secret-token-abcdef123456'
    transport = _transport('https://h.example', set(), httpx.MockTransport(lambda req: httpx.Response(
        429, headers={'Date': 'Mon, 07 Sep 2026 05:00:00 GMT',
                      'Retry-After': 'Mon, 07 Sep 2026 05:00:02 GMT',
                      'X-Request-ID': token, 'Set-Cookie': token, 'Authorization': token},
        text='rate limited')))
    try:
        with pytest.raises(RateLimitedError) as raised:
            await transport.request('GET', '/api/me')
        error = raised.value
        assert error.retry_after_seconds == 2
        assert error.response_headers['retry-after'].endswith('05:00:02 GMT')
        assert 'authorization' not in error.response_headers and 'set-cookie' not in error.response_headers
        assert token not in str(error.response_headers)
    finally:
        await transport.aclose()
