"""从参赛 Token 反查其绑定的锦标赛 ID 与赛况摘要（赛前准备工具）。

默认只查询；加 ``--write-config`` 则从模板生成可直接启动的私有配置，
填入绑定赛事 ID 和独立审计目录，消除手工抄写。正式赛和测试赛事共用此
准备流程，开赛仍由已冻结的 ``run_participant.py`` 核对目标和发布包。

设计约束（对齐 scripts/AGENTS.md 与根 AGENTS.md 第 6 节）：

- 查询只依赖标准库；生成配置时复用组合根的配置校验，不装配运行单元；
- Token 只经 `--token-file` / `--token-env` 进入进程，绝不接受命令行明文，
  绝不打印、不进入异常文本与退出信息；
- 只发起幂等 GET（`/api/me`、`/api/tournaments/me/rules`），不 register、
  不 ready、不影响任何赛事状态，可随时重复执行；
- 配置中的内网白名单主机直连；证书例外仅限该白名单。未提供配置时
  使用内置官方主机白名单，独立 SSLContext 不改全局。

用法::

    python scripts/resolve_tournament.py --token-file token/20260904测试赛.txt
    python scripts/resolve_tournament.py --token-file <文件> \
        --config <已批准的赛事模板> --write-config .private/participant.json

`--config` 可选：从任一运行配置 JSON 复用 `base_url` 与 `insecure_hosts`，
与本仓运行配置格式一致。查询时忽略其余键；生成时校验全部字段。
生成文件不含 Token 原文、不覆盖已有文件；文件 Token 仍以启动参数注入，
环境变量 Token 则只保存变量名。

标准输出最后一行 `RESULT <json>` 为机器可读结果（不含 Token）；
时间字段由 Unix 秒转换为本地时区字符串标注。

退出码：0 = 成功；2 = 用法/配置错误；10 = 认证失败（Token 无效）；
11 = 网络或协议错误。
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import shlex
import ssl
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence
from urllib.parse import urlsplit
from uuid import uuid4

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
        except (OSError, UnicodeError):
            raise ResolveError(EXIT_USAGE, "读取 Token 文件失败，请检查路径、权限和 UTF-8 编码") from None
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
    if not isinstance(base_url, str):
        raise ResolveError(EXIT_USAGE, "base_url 必须是字符串")
    try:
        parsed = urlsplit(base_url)
        parsed.port
    except ValueError:
        raise ResolveError(EXIT_USAGE, "base_url 主机或端口格式无效") from None
    if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
        raise ResolveError(EXIT_USAGE, "base_url 必须包含 http(s) 协议和有效主机")
    if parsed.username or parsed.password or parsed.fragment:
        raise ResolveError(EXIT_USAGE, "base_url 不能含内嵌凭证或片段")
    return base_url.rstrip("/")


def _build_ssl_context(base_url: str, hint: Mapping[str, Any], force_insecure: bool) -> ssl.SSLContext:
    """与运行客户端同口径：仅配置的官方内网主机享有证书例外。"""

    host = (urlsplit(base_url).hostname or "").lower()
    defaults = [urlsplit(DEFAULT_BASE_URL).hostname] if not hint else []
    hosts = hint.get("insecure_hosts", defaults)
    if not isinstance(hosts, list) or any(not isinstance(h, str) or not h.strip() for h in hosts):
        raise ResolveError(EXIT_USAGE, "insecure_hosts 必须是非空主机名组成的数组")
    insecure_hosts = {h.lower() for h in hosts}
    if force_insecure and host not in insecure_hosts:
        raise ResolveError(EXIT_USAGE, "--insecure 仅允许配置的 insecure_hosts 主机")
    if host in insecure_hosts:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return ssl.create_default_context()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """拒绝重定向，避免认证头和内网证书例外流向其他主机。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _get_json(url: str, token: str, ctx: ssl.SSLContext) -> Mapping[str, Any]:
    """带鉴权 GET 一个 JSON 端点；HTTP 错误分类为认证/协议失败。

    请求头中的 Bearer Token 不打印；错误体和底层异常不原样输出，避免
    服务端或代理回显凭证。拒绝重定向，保持与运行客户端相同的主机边界。
    """

    request = urllib.request.Request(url, headers={
        "Authorization": "Bearer {0}".format(token),
        "Accept": "application/json",
    })
    try:
        handlers = [urllib.request.HTTPSHandler(context=ctx), _NoRedirect()]
        if ctx.verify_mode == ssl.CERT_NONE:
            # 与 OfficialTransport 一致：仅配置的内网主机绕过环境/系统代理。
            handlers.append(urllib.request.ProxyHandler({}))
        opener = urllib.request.build_opener(*handlers)
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code in (401,):
            raise ResolveError(EXIT_AUTH, "认证失败（HTTP {0}）：Token 无效或已过期".format(exc.code)) from None
        raise ResolveError(
            EXIT_FATAL, "官方端点返回 HTTP {0}".format(exc.code),
        ) from None
    except (urllib.error.URLError, OSError, http.client.HTTPException):
        raise ResolveError(EXIT_FATAL, "网络错误（无法连接官方平台）") from None
    except UnicodeError:
        raise ResolveError(EXIT_FATAL, "官方端点返回了非 UTF-8 内容") from None
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        raise ResolveError(EXIT_FATAL, "官方端点返回了非 JSON 内容") from None
    if not isinstance(parsed, Mapping):
        raise ResolveError(EXIT_FATAL, "官方端点返回了非对象 JSON")
    return parsed


def _write_start_config(
    args: argparse.Namespace, hint: Mapping[str, Any], base_url: str,
    tournament_id: str, token: str,
) -> Mapping[str, str]:
    """生成兼容既有入口的配置；校验失败不写文件，不装配或启动赛事。

    保留模板策略、发布包及运行参数，只替换赛事、基址、审计目录与凭证
    来源。已填写的真实赛事必须与 Token 绑定相符；不会用发现结果掩盖错配。
    """

    data = dict(hint)
    if data.get("mode") not in ("official_tournament", "test_tournament"):
        raise ResolveError(EXIT_USAGE, "生成配置仅支持正式赛事或测试赛事模板")
    expected = data.get("expected_tournament_id")
    placeholder = isinstance(expected, str) and (
        expected.startswith("t_REPLACE") or (expected.startswith("<") and expected.endswith(">"))
    )
    if expected != tournament_id and not placeholder:
        raise ResolveError(EXIT_USAGE, "模板目标赛事与 Token 绑定赛事不一致；请核对模板和 Token")
    data["base_url"] = base_url
    data["expected_tournament_id"] = tournament_id
    # 会话名称使用 UTC 墙上时钟；随机后缀避免同秒准备时复用审计目录。
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    session = "{0}-{1}-{2}".format(data["mode"].replace("_", "-"), stamp, uuid4().hex[:8])
    data["audit_root"] = args.audit_root or "artifacts/sessions/{0}/audit".format(session)
    data.pop("token", None)
    data.pop("token_env", None)
    if args.token_env:
        data["token_env"] = args.token_env

    # 校验只使用内存中的凭证；配置和异常文本不保存凭证原文。
    src = str(Path(__file__).resolve().parents[1] / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    try:
        from hangma_bot.bootstrap import runtime_config_from_mapping

        checked = dict(data)
        checked.pop("token_env", None)
        checked["token"] = token
        runtime_config_from_mapping(checked)
    except (ImportError, ValueError, RuntimeError, OSError) as exc:
        message = str(exc).replace(token, "<redacted>")
        raise ResolveError(EXIT_USAGE, "模板配置校验失败: {0}".format(message)) from None

    destination = Path(args.write_config)
    try:
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
    except FileExistsError:
        raise ResolveError(EXIT_USAGE, "输出配置已存在，不覆盖；请换一个 --write-config 路径") from None
    except (OSError, ValueError):
        raise ResolveError(EXIT_USAGE, "写入参赛配置失败，请检查路径和权限") from None
    command = [".venv/bin/python", "scripts/run_participant.py", "--config", str(destination)]
    if args.token_file:
        command.extend(["--token-file", args.token_file])
    return {"config_path": str(destination), "audit_root": data["audit_root"],
            "start_command": shlex.join(command)}


def _fmt_unix(value: Any) -> Optional[str]:
    """Unix 秒 → 本地时区时间串；非正数或非数值返回 None。"""

    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        return None
    return datetime.fromtimestamp(value).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="resolve_tournament.py",
        description="查询 Token 绑定赛事，可从模板生成参赛配置（只读 GET，不 register/ready）",
    )
    parser.add_argument("--token-file", default=None, help="只含单个 Token 的私有文件路径")
    parser.add_argument("--token-env", default=None, help="存放 Token 的环境变量名（与 --token-file 二选一）")
    parser.add_argument("--config", default=None, help="运行配置 JSON 路径；复用其 base_url 与 insecure_hosts")
    parser.add_argument("--write-config", default=None, help="生成新的私有参赛配置（须提供 --config 模板，不覆盖已有文件）")
    parser.add_argument("--audit-root", default=None, help="生成配置的审计根目录；默认自动创建独立会话名称")
    parser.add_argument("--base-url", default=None, help="官方平台基址（默认 {0}）".format(DEFAULT_BASE_URL))
    parser.add_argument(
        "--insecure", action="store_true",
        help="兼容选项：仅允许对 insecure_hosts 中的官方主机关闭证书校验",
    )
    args = parser.parse_args(argv)

    try:
        if args.write_config and not args.config:
            raise ResolveError(EXIT_USAGE, "--write-config 必须同时提供 --config 模板")
        if args.audit_root and not args.write_config:
            raise ResolveError(EXIT_USAGE, "--audit-root 仅用于 --write-config")
        if args.write_config and Path(args.write_config).exists():
            raise ResolveError(EXIT_USAGE, "输出配置已存在，不覆盖；请换一个 --write-config 路径")
        token = _load_token(args.token_file, args.token_env)
        hint = _load_config_hint(args.config)
        base_url = _resolve_base_url(args, hint)
        ctx = _build_ssl_context(base_url, hint, args.insecure)

        me = _get_json(base_url + "/api/me", token, ctx)
        tournament_id = me.get("tournament_id") or ""
        user_id = me.get("user_id") or ""
        active_games = me.get("active_games") or []
        if not isinstance(tournament_id, str) or not tournament_id.strip():
            raise ResolveError(
                EXIT_FATAL,
                "该 Token 未绑定赛事；请使用报名 Token。自由赛全局 Token 使用 run_auto_match.py",
            )
        if not isinstance(user_id, str):
            raise ResolveError(EXIT_FATAL, "官方身份字段 user_id 必须是字符串")

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
        if args.write_config:
            result.update(_write_start_config(args, hint, base_url, tournament_id, token))

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
        if args.write_config:
            print("已生成参赛配置: {0}".format(result["config_path"]))
            print("审计根目录: {0}".format(result["audit_root"]))
            print("启动命令: {0}".format(result["start_command"]))
        print(RESULT_PREFIX + json.dumps(result, ensure_ascii=False), flush=True)
        return EXIT_OK
    except ResolveError as exc:
        print("解析失败: {0}".format(exc), file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    sys.exit(main())
