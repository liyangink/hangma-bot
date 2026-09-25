"""钉死排行榜抓取器的建连口径：必须绕过环境代理，证书校验只在 insecure 时关闭。

为什么单独测这一条：2026-09-25 实测，同一门户 URL 走 urllib 默认 opener 报
`_ssl.c:999: The handshake operation timed out`，绕过代理后正常返回 HTTP 401
（会话过期）。五个端点全部失败并被误报成 TLS 问题，掩盖了真正的"会话过期"。
本项目其余 HTTP 客户端统一 `trust_env=False`，抓取器必须同口径。

测试只替换 opener 工厂，不联网络。
"""

from __future__ import annotations

import importlib.util
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _load():
    spec = importlib.util.spec_from_file_location(
        "fetch_leaderboard", ROOT / "scripts" / "fetch_leaderboard.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["fetch_leaderboard"] = module
    spec.loader.exec_module(module)
    return module


fetch = _load()


class _FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return b'{"ok": true}'


class _CapturingOpener:
    """记录本次建连用到的 handler，并模拟一次成功响应。"""

    def __init__(self, handlers):
        self.handlers = handlers
        self.opened = []

    def open(self, request, timeout=None):
        self.opened.append((request, timeout))
        return _FakeResponse()


def _install_capture(monkeypatch):
    captured = {}

    def fake_build_opener(*handlers):
        opener = _CapturingOpener(handlers)
        captured["opener"] = opener
        return opener

    monkeypatch.setattr(urllib.request, "build_opener", fake_build_opener)
    return captured


def test_http_get_bypasses_environment_proxies(monkeypatch):
    captured = _install_capture(monkeypatch)
    status, body, error = fetch.http_get("https://example.invalid/x", "session=1", False)
    assert (status, error) == (200, None)
    assert body == '{"ok": true}'
    proxies = [h for h in captured["opener"].handlers if isinstance(h, urllib.request.ProxyHandler)]
    assert len(proxies) == 1, "必须显式安装 ProxyHandler 才会绕过 http_proxy/https_proxy"
    assert proxies[0].proxies == {}, "空 proxies 表示不经过任何环境代理"


def test_http_get_only_disables_certificate_check_when_insecure(monkeypatch):
    captured = _install_capture(monkeypatch)
    fetch.http_get("https://example.invalid/x", "", False)
    handler = next(h for h in captured["opener"].handlers
                   if isinstance(h, urllib.request.HTTPSHandler))
    assert handler._context is None, "非 insecure 时必须使用默认证书校验上下文"

    captured = _install_capture(monkeypatch)
    fetch.http_get("https://example.invalid/x", "", True)
    handler = next(h for h in captured["opener"].handlers
                   if isinstance(h, urllib.request.HTTPSHandler))
    assert handler._context is not None, "insecure 时必须关闭证书校验"
    assert handler._context.verify_mode.name == "CERT_NONE"


def test_http_get_sends_cookie_only_when_present(monkeypatch):
    captured = _install_capture(monkeypatch)
    fetch.http_get("https://example.invalid/x", "a=1; b=2", False)
    request, _ = captured["opener"].opened[0]
    assert request.get_header("Cookie") == "a=1; b=2"

    captured = _install_capture(monkeypatch)
    fetch.http_get("https://example.invalid/x", "", False)
    request, _ = captured["opener"].opened[0]
    assert request.get_header("Cookie") is None


def test_http_get_reports_network_failure_without_raising(monkeypatch):
    def failing_build_opener(*handlers):
        class _Boom:
            def open(self, request, timeout=None):
                raise urllib.error.URLError("handshake operation timed out")
        return _Boom()

    monkeypatch.setattr(urllib.request, "build_opener", failing_build_opener)
    status, body, error = fetch.http_get("https://example.invalid/x", "", False)
    assert status is None and body == ""
    assert "URLError" in error and "handshake" in error


def test_http_get_returns_body_for_http_error(monkeypatch):
    def failing_build_opener(*handlers):
        class _Boom:
            def open(self, request, timeout=None):
                raise urllib.error.HTTPError(
                    "https://example.invalid/x", 401, "Unauthorized", {}, None)
        return _Boom()

    monkeypatch.setattr(urllib.request, "build_opener", failing_build_opener)
    status, body, error = fetch.http_get("https://example.invalid/x", "", False)
    assert status == 401 and error is None
