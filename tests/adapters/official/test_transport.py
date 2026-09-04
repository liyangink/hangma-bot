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
