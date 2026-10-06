"""P0 本机 HTTP 入口测试。"""

from __future__ import annotations

import json
from contextlib import redirect_stdout
from io import StringIO
import threading
import urllib.error
import urllib.request

from spectator.model import SpectatorRepository
from spectator.server import build_arg_parser, create_server, main


def test_watch_directory_defaults_to_runs_and_explicit_values_replace_it():
    """命令行无目录时观察 ./runs；显式目录不与默认值混合。"""

    parser = build_arg_parser()
    assert parser.parse_args([]).watch_dir is None
    assert parser.parse_args(["--watch-dir", "one", "--watch-dir", "two"]).watch_dir == [
        "one",
        "two",
    ]

    output = StringIO()
    with redirect_stdout(output):
        assert main(["--once"]) == 0
    assert json.loads(output.getvalue())["schema_version"] == 1


def test_server_binds_loopback_and_serves_json(tmp_path):
    """HTTP 只绑定 127.0.0.1，健康检查与观战快照可读取。"""

    server = create_server(SpectatorRepository((tmp_path,)), 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        assert host == "127.0.0.1"
        # 测试运行环境可能设置全局 HTTP 代理；回环验证必须直接连接本机。
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://{host}:{port}/api/snapshot", timeout=2) as response:
            document = json.loads(response.read().decode("utf-8"))
        assert document["schema_version"] == 1
        assert document["sources"] == []
        with opener.open(f"http://{host}:{port}/", timeout=2) as response:
            page = response.read().decode("utf-8")
            policy = response.headers["Content-Security-Policy"]
        assert "活跃官方场次" in page
        assert "观战角色" in page
        assert "connect-src 'self'" in policy
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

def test_server_serves_assets_and_rejects_traversal(tmp_path):
    """只读素材目录可被同源页面引用，且拒绝路径穿越与白名单外后缀。"""

    server = create_server(SpectatorRepository((tmp_path,)), 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        base = f"http://{host}:{port}"
        with opener.open(f"{base}/assets/tiles/Man1.svg", timeout=2) as response:
            body = response.read().decode("utf-8")
            content_type = response.headers["Content-Type"]
            cache_control = response.headers["Cache-Control"]
        assert body.lstrip().startswith("<?xml") or body.lstrip().startswith("<svg")
        assert content_type == "image/svg+xml"
        # 素材是固定插画：允许浏览器缓存，牌桌重绘时不再重新拉取。
        assert "max-age" in cache_control
        for rejected in (
            "/assets/../server.py",
            "/assets/../../AGENTS.md",
            "/assets/tiles/Man1.txt",
            "/assets/tiles/missing.svg",
        ):
            try:
                opener.open(f"{base}{rejected}", timeout=2)
            except urllib.error.HTTPError as error:
                assert error.code == 404
            else:  # pragma: no cover - 放行即失败
                raise AssertionError(f"不应放行 {rejected}")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

