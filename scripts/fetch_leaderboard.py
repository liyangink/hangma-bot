#!/usr/bin/env python3
"""门户排行榜快照工具：用人工导出的门户登录态定时拉取排行榜原文，落盘带血缘的快照。

定位（离线辅助，不进线上动作闭环；见
doc/implementation/notes/leaderboard-opponent-tagging-2026-09-09.md）：

1. 登录授权由人工完成一次：浏览器登录门户（OpenID）后，从 DevTools Network 里
   任一 /portal/api/leaderboard 请求复制整行 Cookie 请求头，粘贴到
   .private/portal-session/cookie.txt（单行）。也兼容 Netscape cookie jar
   （制表符 7 列）与 [{"name":..,"value":..}] JSON 数组两种导出格式。
   该路径被 .gitignore 忽略；本脚本绝不打印 Cookie 内容。
2. 串行拉取（间隔 1 秒，尊重门户限速）：
   - GET /portal/api/leaderboard?period=all|today|week（积分总榜三期，门户登录态）；
   - GET /portal/api/leaderboard/huge-win、GET /portal/api/leaderboard/best-game（门户登录态）；
   - GET /portal/api/guide/version（免认证）只为给快照记录 guide 版本血缘。
3. 快照写入 <out>/snapshots/<UTC时间戳>/：各端点原始 JSON + snapshot.json
   （captured_at_unix_ms、guide_version、各端点 HTTP 状态与行数）。
4. 全部排行榜端点 401 = 登录态失效：提示人工重新导出 Cookie，退出码 3；
   其他 HTTP/网络错误写 errors 证据后退出码 4（保留已成功部分）。
5. --min-age-min 节流：最新快照不足该年龄且未 --force 时跳过并打印最新快照路径
   （退出码 0），供 watchdog 高频巡检安全反复调用。

门户会话有效期官方未说明（2026-09-09 实测无登录 401 UNAUTHORIZED）；过期后
重新登录导出、覆盖同一 cookie 文件即可，快照目录只增不改。

TLS：官方赛事内网主机（10.240.169.190，自签证书）自动关闭校验，策略与
scripts/sync_official_guide.py 一致；其他主机默认校验，确需自签才 --insecure。

用法：

  .venv/bin/python3 scripts/fetch_leaderboard.py                    # 日常（60 分钟节流）
  .venv/bin/python3 scripts/fetch_leaderboard.py --force            # 立即刷新
  .venv/bin/python3 scripts/fetch_leaderboard.py --min-age-min 360  # 6 小时一档

退出码：0 成功或节流跳过；2 未配置 Cookie 文件；3 登录态失效（需人工重导）；
4 网络/HTTP 失败。
"""

from __future__ import annotations

import argparse
import calendar
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = SCRIPT_ROOT / "configs" / "auto-match.local.json"
DEFAULT_COOKIE_FILE = SCRIPT_ROOT / ".private" / "portal-session" / "cookie.txt"
DEFAULT_OUT = SCRIPT_ROOT / "datasets" / "leaderboard"
OFFICIAL_INTRANET_HOST = "10.240.169.190"
PERIODS = ("all", "today", "week")
EXTRA_BOARDS = ("huge-win", "best-game")
GUIDE_VERSION_PATH = "/portal/api/guide/version"
LEADERBOARD_PATH = "/portal/api/leaderboard"
REQUEST_INTERVAL_SEC = 1.0
TIMEOUT_SEC = 15


class FetchError(RuntimeError):
    """抓取失败（网络/HTTP/报文形状）。"""


def load_cookie_header(path: Path) -> str:
    """把人工导出的 Cookie 文件解析成请求头 Cookie 值；绝不回显内容。

    支持三种格式（按顺序自动识别）：
    1. 裸 Cookie 头：一行或多行 "k=v; k2=v2"（允许带 Cookie: 前缀）；
    2. Netscape cookie jar：制表符 7 列（含 #HttpOnly_ 前缀行），取第 6/7 列；
    3. JSON 数组：[{"name":..,"value":..}, ...]。
    """
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        raise FetchError(f"Cookie 文件为空：{path}")

    if text.startswith("["):
        items = json.loads(text)
        pairs = [f"{it['name']}={it['value']}" for it in items
                 if isinstance(it, dict) and it.get("name") and it.get("value")]
        if not pairs:
            raise FetchError("JSON Cookie 数组里没有可用 name/value")
        return "; ".join(pairs)

    raw_lines = text.splitlines()
    jar = [ln for ln in raw_lines if "\t" in ln and len(ln.split("\t")) >= 7]
    if jar:
        pairs = []
        for ln in jar:
            cols = ln.split("\t")
            if len(cols) >= 7 and cols[5] and cols[6]:
                pairs.append(f"{cols[5]}={cols[6]}")
        if pairs:
            return "; ".join(pairs)

    lines = [ln.strip() for ln in raw_lines if ln.strip()]
    cleaned = [ln[7:].strip() if ln[:7].lower() == "cookie:" else ln for ln in lines]
    if not cleaned:
        raise FetchError("Cookie 文件没有可解析内容")
    return "; ".join(cleaned)


def http_get(url: str, cookie: str, insecure: bool):
    """GET 一个 JSON 端点；返回 (http_status, body_text, error)。不抛网络异常。

    必须显式绕过环境代理：本项目其余 HTTP 客户端统一以 `trust_env=False`
    建连，而 urllib 的默认 opener 会读取 `http_proxy`/`https_proxy`/`no_proxy`。
    2026-09-25 本机实测——同一 URL 走默认 opener 报
    `_ssl.c:999: The handshake operation timed out`，绕过代理后正常返回
    （HTTP 401，即会话过期），说明失败原因是代理而非网络、DNS 或证书；
    当时五个门户端点全部失败并误报为 TLS 问题。
    """
    headers = {"Accept": "application/json", "User-Agent": "hangma-bot-leaderboard-fetch/1"}
    if cookie:
        headers["Cookie"] = cookie
    req = urllib.request.Request(url, headers=headers)
    ctx = ssl._create_unverified_context() if insecure else None
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),  # 绕过环境代理，与其余客户端口径一致
        urllib.request.HTTPSHandler(context=ctx),  # 仅 insecure 时关闭证书校验
    )
    try:
        with opener.open(req, timeout=TIMEOUT_SEC) as resp:
            return resp.status, resp.read().decode("utf-8", "replace"), None
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace"), None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, "", f"{type(exc).__name__}: {exc}"


def count_top_rows(payload) -> int | None:
    """统计响应里 top 数组行数；形状未知时返回 None 而不是猜。"""
    if isinstance(payload, dict):
        top = payload.get("top")
        if isinstance(top, list):
            return len(top)
    return None


def snapshot_age_minutes(snap_dir: Path) -> float | None:
    """按目录名（UTC yyyymmddTHHMMSSZ）算快照年龄（分钟）；解析失败返回 None。"""
    try:
        epoch = calendar.timegm(time.strptime(snap_dir.name, "%Y%m%dT%H%M%SZ"))
        return (time.time() - epoch) / 60.0
    except ValueError:
        return None


def snapshot_is_usable(snap_dir: Path) -> bool:
    """快照是否含可用榜单数据：至少 all 榜成功且无榜单端点错误。

    只有成功快照才参与节流计时；401/网络失败的残证快照不应阻止下次重试。
    """
    if not (snap_dir / "leaderboard-all.json").is_file():
        return False
    try:
        meta = json.loads((snap_dir / "snapshot.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return not any(k.startswith("leaderboard-") for k in meta.get("errors", {}))


def latest_snapshot(out_root: Path) -> Path | None:
    root = out_root / "snapshots"
    if not root.is_dir():
        return None
    dirs = sorted((d for d in root.iterdir() if d.is_dir() and snapshot_is_usable(d)), reverse=True)
    return dirs[0] if dirs else None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default=str(DEFAULT_CONFIG),
                        help="运行配置（读 base_url 与 insecure_hosts）")
    parser.add_argument("--cookie-file", default=str(DEFAULT_COOKIE_FILE),
                        help="门户登录 Cookie 文件（默认 .private/portal-session/cookie.txt）")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="快照输出根目录")
    parser.add_argument("--base-url", help="覆盖配置里的 base_url")
    parser.add_argument("--insecure", action="store_true",
                        help="对该主机关闭 TLS 校验（内网自签环境）")
    parser.add_argument("--min-age-min", type=float, default=60.0,
                        help="节流：最新快照不足该分钟数时跳过（默认 60）")
    parser.add_argument("--force", action="store_true", help="忽略节流立即刷新")
    args = parser.parse_args(argv)

    out_root = Path(args.out)
    base_url = args.base_url
    insecure = args.insecure
    config = {}
    if Path(args.config).is_file():
        try:
            config = json.loads(Path(args.config).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            config = {}
    if not base_url:
        base_url = config.get("base_url")
    if not base_url:
        print("!! 缺少 base_url（--base-url 或配置文件）", file=sys.stderr)
        return 4
    base_url = base_url.rstrip("/")

    cookie_path = Path(args.cookie_file)
    if not cookie_path.is_file():
        print(f"未配置门户登录态：请人工登录门户后把整行 Cookie 头写入 {cookie_path}"
              f"（详见 .agents/skills/hangma-auto-match/SKILL.md 排行榜打标一节）")
        return 2

    latest = latest_snapshot(out_root)
    if latest and not args.force:
        age = snapshot_age_minutes(latest)
        if age is not None and age < args.min_age_min:
            print(f"最新快照 {latest.name}（{age:.0f} 分钟前）不足 {args.min_age_min:.0f} 分钟，跳过")
            return 0

    host = urlsplit(base_url).hostname or ""
    insecure = insecure or host in (config.get("insecure_hosts") or []) or host == OFFICIAL_INTRANET_HOST

    try:
        cookie = load_cookie_header(cookie_path)
    except (FetchError, json.JSONDecodeError) as exc:
        print(f"!! Cookie 文件解析失败：{exc}", file=sys.stderr)
        return 2

    snap_dir = out_root / "snapshots" / time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    snap_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "snapshot_schema_version": 1,
        "captured_at_unix_ms": int(time.time() * 1000),
        "base_url": base_url,
        "cookie_file": None,  # 不记录私有路径；来源说明见文档
        "auth": "portal-session(人工导出)",
        "guide_version": None,
        "endpoints": {},
        "errors": {},
    }

    # 指南版本：免认证，仅记录血缘；失败不阻断榜单抓取。
    status, body, err = http_get(base_url + GUIDE_VERSION_PATH, "", insecure)
    if status == 200:
        try:
            meta["guide_version"] = json.loads(body).get("version")
        except json.JSONDecodeError:
            meta["errors"]["guide/version"] = "响应不是合法 JSON"
    else:
        meta["errors"]["guide/version"] = err or f"HTTP {status}"

    targets = [(f"leaderboard-{p}", f"{LEADERBOARD_PATH}?period={p}") for p in PERIODS]
    targets += [(f"leaderboard-{b}", f"{LEADERBOARD_PATH}/{b}") for b in EXTRA_BOARDS]

    unauthorized = 0
    for name, path in targets:
        status, body, err = http_get(base_url + path, cookie, insecure)
        entry = {"http_status": status}
        if err:
            entry["error"] = err
            meta["errors"][name] = err
            print(f"!! {name} 网络失败：{err}")
        elif status == 401:
            unauthorized += 1
            entry["error"] = "401 login required"
            meta["errors"][name] = "401 login required"
            print(f"!! {name} 返回 401（登录态失效）")
        elif status != 200:
            meta["errors"][name] = f"HTTP {status}"
            print(f"!! {name} 返回 HTTP {status}")
        else:
            try:
                payload = json.loads(body)
                (snap_dir / f"{name}.json").write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                rows = count_top_rows(payload)
                if rows is not None:
                    entry["top_rows"] = rows
            except json.JSONDecodeError:
                (snap_dir / f"{name}.txt").write_text(body, encoding="utf-8")
                entry["note"] = "响应非 JSON，已存原文 txt"
        meta["endpoints"][name] = entry
        time.sleep(REQUEST_INTERVAL_SEC)

    (snap_dir / "snapshot.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if unauthorized and unauthorized == len(targets):
        print(f"=== 门户登录态失效：全部 {len(targets)} 个榜单端点 401。"
              f"请重新登录门户并把整行 Cookie 头覆盖写入 {cookie_path} 后重跑。===")
        return 3
    if meta["errors"]:
        print(f"快照完成（含 {len(meta['errors'])} 项错误）：{snap_dir}")
        return 4

    guide_tag = f"，guide v{meta['guide_version']}" if meta["guide_version"] else ""
    print(f"快照完成：{snap_dir}{guide_tag}")
    for name, _ in targets:
        entry = meta["endpoints"].get(name, {})
        rows = entry.get("top_rows")
        print(f"  {name}: HTTP {entry.get('http_status')}"
              + (f"，top {rows} 行" if rows is not None else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
