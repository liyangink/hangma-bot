"""从参赛 Token 反查其绑定的锦标赛 ID 与赛况摘要（赛前准备工具）。

为什么需要：`run_participant.py` 的 `expected_tournament_id` 在初始化时与
`GET /api/me` 返回的绑定锦标赛严格核对（错配即 target_mismatch 永久失败，
退出码 10），而官方发放的 Token 文件本身不含锦标赛 id。开赛前需要一条
零侵入路径从 Token 得到 id，避免改动已冻结的 runtime 代码——这是权宜之策：
等 runtime 允许改动后，可考虑把「目标发现」并入正式流程或引导文档。

设计约束（对齐 scripts/AGENTS.md 与根 AGENTS.md 第 6 节）：

- 只依赖标准库，不导入 `hangma_bot` 任何模块（冻结期零改动、零风险）；
- Token 只经 `--token-file` / `--token-env` 进入进程，绝不接受命令行明文，
  绝不打印、不进入异常文本与退出信息；
- 只发起幂等 GET（`/api/me`、`/api/tournaments/me/rules`），不 register、
  不 ready、不影响任何赛事状态，可随时重复执行；
- TLS 证书校验仅对私网/回环地址或 `--config` 内 `insecure_hosts` 白名单
  主机关闭，且只作用于本进程这一次请求（独立 SSLContext，不改全局）。

用法::

    python scripts/resolve_tournament.py --token-file token/20260904测试赛.txt
    python scripts/resolve_tournament.py --token-file <文件> \
        --config configs/test-tournament-20260904-t_dee58824c308.json

`--config` 可选：从任一运行配置 JSON 复用 `base_url` 与 `insecure_hosts`，
与本仓 `configs/`、`archive/` 下的配置文件格式一致（未知键忽略）。

标准输出最后一行 `RESULT <json>` 为机器可读结果（不含 Token）；
时间字段由 Unix 秒转换为本地时区字符串标注。

退出码：0 = 成功；2 = 用法/配置错误；10 = 认证失败（Token 无效）；
11 = 网络或协议错误。
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence
from urllib.parse import urlsplit

DEFAULT_BASE_URL = "https://10.240.169.190:18080"
RESULT_PREFIX = "RESULT "

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_AUTH = 10
EXIT_FATAL = 11

TIMEOUT_SECONDS = 10.0


class ResolveError(Exception):
    """解析失败；message 保证不含 Token 原文。"""

    def __init__(self, exit_code: int, message: str) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def _load_token(token_file: Optional[str], token_env: Optional[str]) -> str:
    """从文件或环境变量读取单行 Token；两者只允许提供一个。"""

    provided = sum(value is not None for value in (token_file, token_env))
    if provided != 1:
        raise ResolveError(
            EXIT_USAGE, "--token-file 与 --token-env 必须且只能提供一个（不接受命令行明文）"
        )
    if token_file is not None:
        try:
            content = Path(token_file).read_text(encoding="utf-8")
        except OSError as exc:
            raise ResolveError(EXIT_USAGE, "读取 Token 文件失败: {0}".format(exc)) from None
    else:
        name = token_env
        content = os.environ.get(name, "")
        if not content.strip():
            raise ResolveError(EXIT_USAGE, "环境变量 {0} 未提供非空 Token".format(name))
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        raise ResolveError(EXIT_USAGE, "Token 文件内容为空")
    if len(lines) > 1:
        raise ResolveError(EXIT_USAGE, "Token 文件包含多行内容；请提供只含单个 Token 的文件")
    return lines[0]


def _load_config_hint(config_path: Optional[str]) -> Mapping[str, Any]:
    """读取运行配置中的 base_url / insecure_hosts；其余键一律忽略。"""

    if config_path is None:
        return {}
    try:
        data = json.loads(Path(config_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResolveError(EXIT_USAGE, "读取 --config 失败: {0}".format(exc)) from None
    if not isinstance(data, Mapping):
        raise ResolveError(EXIT_USAGE, "--config 根必须是 JSON 对象")
    return data


def _resolve_base_url(args: argparse.Namespace, hint: Mapping[str, Any]) -> str:
    """基址优先级：--base-url > --config 的 base_url > 内置默认。"""

    base_url = args.base_url or hint.get("base_url") or DEFAULT_BASE_URL
    if not isinstance(base_url, str) or not urlsplit(base_url).scheme.lower() in ("http", "https"):
        raise ResolveError(EXIT_USAGE, "base_url 必须以 http:// 或 https:// 开头")
    return base_url.rstrip("/")


def _is_private_host(host: str) -> bool:
    """仅字面 IP 判定私网/回环；域名不猜测，需要时用 --insecure 显式声明。"""

    try:
        return ipaddress.ip_address(host).is_private or ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _build_ssl_context(base_url: str, hint: Mapping[str, Any], force_insecure: bool) -> ssl.SSLContext:
    """默认校验证书；仅私网地址、白名单主机或显式 --insecure 时关闭校验。"""

    host = (urlsplit(base_url).hostname or "").lower()
    insecure_hosts = {str(h).lower() for h in hint.get("insecure_hosts", []) if isinstance(h, str)}
    allow = force_insecure or host in insecure_hosts or _is_private_host(host)
    if allow:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return ssl.create_default_context()


def _get_json(url: str, token: str, ctx: ssl.SSLContext) -> Mapping[str, Any]:
    """带鉴权 GET 一个 JSON 端点；HTTP 错误分类为认证/协议失败。

    请求头只含 Bearer Token（不打印）；urllib 的错误对象只携带 URL 与
    状态码，不含请求头，因此异常文本天然不泄漏 Token。
    """

    request = urllib.request.Request(url, headers={
        "Authorization": "Bearer {0}".format(token),
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS, context=ctx) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code in (401,):
            raise ResolveError(EXIT_AUTH, "认证失败（HTTP {0}）：Token 无效或已过期".format(exc.code)) from None
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:120]
        except Exception:  # noqa: BLE001 - 错误体只用于诊断，读取失败不掩盖主因
            pass
        raise ResolveError(
            EXIT_FATAL,
            "官方端点返回 HTTP {0}{1}".format(exc.code, ("：" + detail) if detail else ""),
        ) from None
    except urllib.error.URLError as exc:
        raise ResolveError(EXIT_FATAL, "网络错误（无法连接官方平台）: {0}".format(exc.reason)) from None
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        raise ResolveError(EXIT_FATAL, "官方端点返回了非 JSON 内容") from None
    if not isinstance(parsed, Mapping):
        raise ResolveError(EXIT_FATAL, "官方端点返回了非对象 JSON")
    return parsed


def _fmt_unix(value: Any) -> Optional[str]:
    """Unix 秒 → 本地时区时间串；非正数或非数值返回 None。"""

    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        return None
    return datetime.fromtimestamp(value).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="resolve_tournament.py",
        description="从参赛 Token 反查绑定的锦标赛 ID 与赛况摘要（只读 GET，不 register/ready）",
    )
    parser.add_argument("--token-file", default=None, help="只含单个 Token 的私有文件路径")
    parser.add_argument("--token-env", default=None, help="存放 Token 的环境变量名（与 --token-file 二选一）")
    parser.add_argument("--config", default=None, help="运行配置 JSON 路径；复用其 base_url 与 insecure_hosts")
    parser.add_argument("--base-url", default=None, help="官方平台基址（默认 {0}）".format(DEFAULT_BASE_URL))
    parser.add_argument(
        "--insecure", action="store_true",
        help="对本进程这一次请求关闭 TLS 证书校验（默认仅对私网地址自动关闭）",
    )
    args = parser.parse_args(argv)

    try:
        token = _load_token(args.token_file, args.token_env)
        hint = _load_config_hint(args.config)
        base_url = _resolve_base_url(args, hint)
        ctx = _build_ssl_context(base_url, hint, args.insecure)

        me = _get_json(base_url + "/api/me", token, ctx)
        tournament_id = me.get("tournament_id") or ""
        user_id = me.get("user_id") or ""
        active_games = me.get("active_games") or []
        if not tournament_id:
            raise ResolveError(
                EXIT_FATAL,
                "该 Token 是全局 Token（未绑定锦标赛）；runtime 不支持全局 Token，请使用报名 Token",
            )

        # rules 为增强信息：失败不掩盖已拿到的锦标赛 id（仍以成功退出）。
        rules: Mapping[str, Any] = {}
        rules_error: Optional[str] = None
        try:
            rules = _get_json(base_url + "/api/tournaments/me/rules", token, ctx)
        except ResolveError as exc:
            rules_error = str(exc)

        rules_config = rules.get("config") if isinstance(rules.get("config"), Mapping) else {}
        result = {
            "tournament_id": tournament_id,
            "user_id_prefix": (user_id[:4] or None),
            "name": rules.get("name"),
            "status": rules.get("status"),
            "active_games_count": len(active_games) if isinstance(active_games, list) else 0,
            "config": {
                "M": rules_config.get("M"),
                "Rounds": rules_config.get("Rounds"),
                "BaseScore": rules_config.get("BaseScore"),
                "Kind": rules_config.get("Kind"),
                "PengTimeoutSec": rules_config.get("PengTimeoutSec"),
                "ChiTimeoutSec": rules_config.get("ChiTimeoutSec"),
                "DiscardTimeoutSec": rules_config.get("DiscardTimeoutSec"),
                "StartAt": _fmt_unix(rules_config.get("StartAt")),
                "RegisterDeadlineAt": _fmt_unix(rules_config.get("RegisterDeadlineAt")),
            } if rules_config else None,
        }

        print("平台基址: {0}".format(base_url))
        print("绑定锦标赛: {0}".format(tournament_id))
        if user_id:
            print("身份（脱敏前缀）: {0}*".format(user_id[:4]))
        if rules:
            print("赛事名称: {0}".format(rules.get("name") or "<未提供>"))
            print("状态: {0}".format(rules.get("status") or "<未知>"))
            if rules_config:
                print(
                    "赛制: M={0}（同时场数上限）, Rounds={1}（每场单局数）, 底分={2}, Kind={3!r}".format(
                        rules_config.get("M"), rules_config.get("Rounds"),
                        rules_config.get("BaseScore"), rules_config.get("Kind"),
                    )
                )
                print(
                    "动作窗口: 碰 {0}s / 吃 {1}s / 出牌 {2}s".format(
                        rules_config.get("PengTimeoutSec"), rules_config.get("ChiTimeoutSec"),
                        rules_config.get("DiscardTimeoutSec"),
                    )
                )
                started = _fmt_unix(rules_config.get("StartAt"))
                deadline = _fmt_unix(rules_config.get("RegisterDeadlineAt"))
                if started:
                    print("开赛时间（本地时区）: {0}".format(started))
                if deadline:
                    print("报名截止（本地时区）: {0}".format(deadline))
        elif rules_error:
            print("赛况摘要获取失败（不影响锦标赛 id）: {0}".format(rules_error), file=sys.stderr)
        print(RESULT_PREFIX + json.dumps(result, ensure_ascii=False), flush=True)
        return EXIT_OK
    except ResolveError as exc:
        print("解析失败: {0}".format(exc), file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    sys.exit(main())
