"""把赛前准备收进 check，把参赛交给原单身份入口；不实现 HTTP 或赛事生命周期。

由 participate.sh 准备兼容解释器后调用。默认正式赛事，--test 选择独立
测试赛事配置。Token 只保存在本机专用私有目录，不进入命令参数或配置。
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import fcntl
import getpass
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Optional, Sequence

import resolve_tournament
import run_participant


def read_token(path: Path) -> str:
    """读取单行凭证；格式错误不在异常中回显原文。"""
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    if len(lines) != 1 or not lines[0].strip():
        raise ValueError("Token 文件必须只含一个非空 Token")
    return lines[0].strip()


def save_token(path: Path, token: str) -> None:
    """以仅本人可读权限原子保存 Token；调用方持有该身份的排他锁。"""
    fd, name = tempfile.mkstemp(prefix=".token-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(token + "\n")
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def main(argv: Optional[Sequence[str]] = None, *, root: Optional[Path] = None) -> int:
    """执行检查或原入口，返回其退出码；root 指向源码树，供离线接线验证。

check 只查询并保存准备结果；start 需要检查生成的配置。两者共用身份锁，
防止检查覆盖正在参赛的凭证，或同时启动同一身份的两个进程。
"""
    parser = argparse.ArgumentParser(description="检查赛事或启动单身份比赛")
    parser.add_argument("command", choices=("check", "start"))
    parser.add_argument("--test", action="store_true", help="使用测试赛事 Token 与独立配置")
    parser.add_argument("--token-file", type=Path, help="可选：从已有单行文件读取 Token")
    args = parser.parse_args(argv)
    root = root or Path(__file__).resolve().parents[1]
    kind = "test" if args.test else "official"
    folder = root / ".private/participate" / kind
    config_path = folder / "participant.json"
    token_path = folder / "participant.token"
    # 实验/测试默认RF1；正式锦标赛继续使用稳定P0，不跨模式复用包。
    template_name = ("vip-g37-rf1-v2.test-tournament.example.json" if args.test
                     else "vip-s03-rulefix-p0-approved-v5.official-tournament.example.json")
    template = root / "configs" / template_name
    token = ""
    try:
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        with (folder / "participant.lock").open("a") as lock:
            os.chmod(lock.name, 0o600)
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("该模式已有检查或参赛进程运行，请勿重复启动") from None
            if args.command == "start" and not config_path.exists():
                raise ValueError("请先执行检查命令：bash participate.sh check" + (" --test" if args.test else ""))
            if args.token_file:
                token = read_token(args.token_file)
            else:
                token = os.environ.get(f"HM_{kind.upper()}_TOURNAMENT_TOKEN", "").strip()
                if not token and token_path.exists():
                    token = read_token(token_path)
                if not token:
                    if not sys.stdin.isatty():
                        raise ValueError("请在终端输入 Token，或使用 --token-file")
                    token = getpass.getpass("报名 Token（输入不回显，检查通过后保存在本机私有目录）：").strip()
                if not token or len(token.splitlines()) != 1:
                    raise ValueError("报名 Token 必须是单个非空 Token")

            # 临时凭证只供既有工具读取，结束后删除；配置不会含 Token 原文。
            with tempfile.TemporaryDirectory(prefix=".prepare-", dir=folder) as temporary:
                temporary = Path(temporary)
                credential = temporary / "participant.token"
                save_token(credential, token)
                approved = json.loads(template.read_text(encoding="utf-8"))
                prepared_template = temporary / "template.json"
                template_data = dict(approved)
                template_data.pop("token_env", None)
                template_data.pop("token", None)
                prepared_template.write_text(json.dumps(template_data), encoding="utf-8")
                selected = config_path if config_path.exists() else prepared_template
                config = run_participant.load_config(selected, token_file=str(credential))
                if (config.mode.value != approved["mode"] or config.strategy != approved["strategy"]
                        or config.expected_policy_release_id != approved["expected_policy_release_id"]):
                    raise ValueError("现有参赛配置与所选模式的正式策略包不符")
                if args.command == "start":
                    return run_participant.main(["--config", str(config_path), "--token-file", str(credential)])

                output = io.StringIO()
                resolver_args = ["--config", str(selected), "--token-file", str(credential)]
                staged_config = temporary / "participant.json"
                if not config_path.exists():
                    resolver_args += ["--write-config", str(staged_config)]
                with redirect_stdout(output), redirect_stderr(output):
                    code = resolve_tournament.main(resolver_args)
                if code:
                    print(output.getvalue().replace(token, "<redacted>"), end="", file=sys.stderr)
                    return code
                results = [line[len(resolve_tournament.RESULT_PREFIX):] for line in output.getvalue().splitlines()
                           if line.startswith(resolve_tournament.RESULT_PREFIX)]
                if len(results) != 1:
                    raise ValueError("赛事查询未返回唯一检查结果")
                result = json.loads(results[0])
                if config_path.exists() and config.expected_tournament_id != result["tournament_id"]:
                    print("现有配置绑定另一个赛事；请核对 Token，或移走私有参赛配置后重新检查。", file=sys.stderr)
                    return run_participant.EXIT_PERMANENT
                if not config_path.exists():
                    # 硬链接原子发布，已有目标绝不覆盖。
                    os.link(staged_config, config_path)
                save_token(token_path, token)
                name = str(result.get("name") or "<未提供>").replace(token, "<redacted>")
                tournament = str(result["tournament_id"]).replace(token, "<redacted>")
                status = str(result.get("status") or "<未知>").replace(token, "<redacted>")
                print(f"赛事：{name}（{tournament}）\n状态：{status}")
                print("检查通过，尚未启动比赛。")
                print("启动比赛：bash participate.sh start" + (" --test" if args.test else ""))
                return 0
    except (OSError, ValueError, RuntimeError, EOFError) as exc:
        message = str(exc).replace(token, "<redacted>") if token else str(exc)
        print("参赛准备失败：" + message, file=sys.stderr)
        return run_participant.EXIT_USAGE
    except KeyboardInterrupt:
        return run_participant.EXIT_SIGINT


if __name__ == "__main__":
    sys.exit(main())
