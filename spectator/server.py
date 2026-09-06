"""本机 P0 观战器 HTTP 入口。

只提供静态页面和 ``/api/snapshot``。服务器固定绑定回环地址，不接受远程
监听参数，也不实现任何动作提交、认证或官方 HTTP 请求。
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Sequence


def _ensure_project_import_path() -> None:
    """直接执行本文件时把仓库根目录加入 import path。"""

    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


_ensure_project_import_path()

from spectator.model import SpectatorRepository  # noqa: E402 直接运行脚本时需先调整路径


_STATIC_DIR = Path(__file__).with_name("static")
_STATIC_FILES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/app.js": "app.js",
    "/style.css": "style.css",
}


def make_handler(repository: SpectatorRepository):
    """为一个只读仓库创建 HTTP Handler；供测试使用而不启动真实命令行。"""

    class SpectatorHandler(BaseHTTPRequestHandler):
        """只读本地 Handler；审计内容均以 JSON 或 textContent 供页面处理。"""

        server_version = "HangmaSpectatorP0/1"

        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler 固定入口名
            if self.path == "/api/snapshot":
                self._send_json(repository.snapshot())
                return
            if self.path == "/healthz":
                self._send_json({"ok": True})
                return
            filename = _STATIC_FILES.get(self.path)
            if filename is None:
                self.send_error(HTTPStatus.NOT_FOUND, "not found")
                return
            self._send_static(filename)

        def _send_json(self, document: object) -> None:
            payload = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _send_static(self, filename: str) -> None:
            path = _STATIC_DIR / filename
            try:
                payload = path.read_bytes()
            except OSError:
                self.send_error(HTTPStatus.NOT_FOUND, "static asset missing")
                return
            content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; connect-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, _format: str, *_args: object) -> None:
            """浏览器轮询不打印访问审计，避免淹没人工运行输出。"""

    return SpectatorHandler


def create_server(repository: SpectatorRepository, port: int) -> ThreadingHTTPServer:
    """创建固定绑定 ``127.0.0.1`` 的线程 HTTP 服务器。

    ``port=0`` 交给操作系统分配空闲端口，主要用于自动化测试；真实命令行默认
    8765。绑定回环地址是手牌审计不被局域网暴露的安全边界。
    """

    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(repository))


def build_arg_parser() -> argparse.ArgumentParser:
    """构造 P0 命令行；``--watch-dir`` 可重复传入多个审计父目录。"""

    parser = argparse.ArgumentParser(
        description="杭麻 Bot P0 本地观战器（只读审计目录，不请求官方平台）"
    )
    parser.add_argument(
        "--watch-dir",
        action="append",
        required=True,
        metavar="PATH",
        help="运行目录、audit_root 或测试房间 slot 父目录；可重复，自动发现 runs/{run_id}",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="本机回环端口（默认 8765；0 表示自动选择）",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="只输出一次观战 JSON 后退出，用于诊断目录识别",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """启动本机只读网页；Ctrl-C 只关闭观战器自身。"""

    args = build_arg_parser().parse_args(argv)
    if args.port < 0 or args.port > 65535:
        raise SystemExit("--port 必须在 0—65535")
    repository = SpectatorRepository(args.watch_dir)
    if args.once:
        print(json.dumps(repository.snapshot(), ensure_ascii=False, indent=2))
        return 0
    server = create_server(repository, args.port)
    host, port = server.server_address[:2]
    print("观战器仅在本机监听：http://{}:{}/".format(host, port))
    print("只读审计目录；关闭此进程不会影响赛事 Bot。")
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\n观战器已关闭。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
