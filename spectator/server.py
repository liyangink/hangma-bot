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
_ASSET_ROOT = _STATIC_DIR / "assets"
# 素材只按扩展名放行（牌面、头像、纹理等插画与样式），不放行任意文件。
_ASSET_SUFFIXES = {".svg", ".png", ".webp", ".jpg", ".jpeg", ".css", ".woff2"}
_ASSET_TYPES = {
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".webp": "image/webp",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".css": "text/css",
    ".woff2": "font/woff2",
}
# 素材是固定插画：允许浏览器缓存，避免牌桌重绘时重新拉取同一批牌面。
_ASSET_CACHE_CONTROL = "public, max-age=86400"
_PAGE_CACHE_CONTROL = "no-store"


def resolve_asset(request_path: str) -> Path | None:
    """把 ``/assets/...`` 解析为静态素材目录内的文件。

    返回 ``None`` 表示这不是可服务的素材请求（调用方按普通路径继续处理）。
    显式拒绝路径穿越与不在扩展名白名单内的文件，保证只读服务不会外泄仓库文件。
    """

    prefix = "/assets/"
    if not request_path.startswith(prefix):
        return None
    relative = request_path[len(prefix):]
    if not relative or ".." in Path(relative).parts:
        return None
    root = _ASSET_ROOT.resolve()
    candidate = (_ASSET_ROOT / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    if candidate.suffix.lower() not in _ASSET_SUFFIXES or not candidate.is_file():
        return None
    return candidate


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
            asset = resolve_asset(self.path)
            if asset is not None:
                self._send_file(asset, cache_control=_ASSET_CACHE_CONTROL)
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
            self._write_quietly(payload)

        def _write_quietly(self, payload: bytes) -> None:
            """写出响应体；浏览器关页、刷新或切换场次会中断轮询连接。

            客户端断开属正常现象：只丢弃本次响应，不把 BrokenPipeError 抛给
            socketserver——否则每个断开的轮询都会打印一段疑似崩溃的 traceback。
            """

            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _send_static(self, filename: str) -> None:
            self._send_file(_STATIC_DIR / filename, cache_control=_PAGE_CACHE_CONTROL)

        def _send_file(self, path: Path, *, cache_control: str) -> None:
            """发送一个静态文件；缺失按 404 处理，客户端断开由写入层静默丢弃。"""

            try:
                payload = path.read_bytes()
            except OSError:
                self.send_error(HTTPStatus.NOT_FOUND, "static asset missing")
                return
            content_type = _ASSET_TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if content_type.startswith("text/"):
                content_type += "; charset=utf-8"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", cache_control)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; connect-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self._write_quietly(payload)

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
        default=None,
        metavar="PATH",
        help="运行目录、audit_root 或测试房间 slot 父目录；可重复。省略时默认 ./runs",
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
    parser.add_argument(
        "--follow-live-sessions",
        default=None,
        metavar="PATH",
        help="赛事父目录（如 artifacts/sessions）：运行时自动跟随仍在写入的批次，换批无需重启",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """启动本机只读网页；Ctrl-C 只关闭观战器自身。"""

    args = build_arg_parser().parse_args(argv)
    if args.port < 0 or args.port > 65535:
        raise SystemExit("--port 必须在 0—65535")
    # 普通开发与赛事运行目录默认都放在仓库 ./runs；显式传参则完全由用户选择，
    # 不把默认目录混进多目录观察列表，以免误显示无关审计。
    # 跟随模式下目录由运行时重新发现：自由赛换批后新批次写在兄弟目录，
    # 只固定一个批次目录会让页面停在换批那一刻。
    repository = SpectatorRepository(
        args.watch_dir or (() if args.follow_live_sessions else ("runs",)),
        follow_sessions_root=args.follow_live_sessions,
    )
    if args.follow_live_sessions is not None:
        # 启动提示走 stderr，保证 --once 的 stdout 仍是纯 JSON。
        roots = repository.followed_roots
        if roots:
            print(
                "自动跟随活跃批次：{}".format("，".join(str(item) for item in roots)),
                file=sys.stderr,
            )
        else:
            print(
                "跟随目录下暂未发现仍在写入的批次（{}），换批开始后会自动接入。".format(
                    args.follow_live_sessions
                ),
                file=sys.stderr,
            )
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
