"""单 Token 参赛入口：正式赛事 / 测试赛事 / 测试房间单身份冒烟共用同一入口。

职责（scripts/AGENTS.md）：只解析配置、核对模式并调用 ``bootstrap``；
不得包含规则、策略、官方 DTO 或生命周期实现。

配置 JSON 结构（示例）：

```jsonc
{
  // 运行模式：test_room / test_tournament / official_tournament；
  // 与 token_kind 交叉核对，防止测试/正式身份混接
  "mode": "official_tournament",
  "base_url": "https://<官方平台内网地址>",
  "expected_tournament_id": "<目标赛事 id>",
  "known_guide_version": 15,
  // Token 二选一：token 内联（私有配置注意权限）或 token_env 环境变量名
  "token_env": "HM_PARTICIPANT_TOKEN",
  "token_kind": "official",   // test / official
  "audit_root": "./runs",      // 其下生成 runs/{run_id}/... 审计目录
  "strategy": "weighted_heuristic",  // 可选；weighted_heuristic / safe_fallback
  "expected_policy_release_id": "<发布策略专用完整 SHA-256>", // 普通策略省略
  "insecure_hosts": ["<官方内网主机>"],  // 可选；仅白名单内网主机允许关闭 TLS 校验
  "slot": "A"                  // 可选；测试房间身份槽位标签，仅用于日志
}
```

用法：``python scripts/run_participant.py --config <path> [--token-file <私有Token文件>] [--slot <标签>]``

退出码契约（与 run_test_room.py 的守护逻辑对齐）：

========  ============================================================
  0       参赛者正常终态（淘汰 / 赛事 finished/closed/void）
  2       配置或用法错误（组装前拒绝，不建立网络连接）
  10      身份永久失败（认证失败 / 指南不兼容 / 目标赛事错配），守护器不得重启
  11      致命协议错误或未预期异常，测试房间守护器可按配置有界重启
  130     收到 SIGINT；143 收到 SIGTERM（会话已关闭、审计已尽力冲刷）
========  ============================================================

标准输出最后一行打印 ``RESULT <json>`` 机器可读结果（不含 Token），
测试房间编排器据此汇总每身份终态；其余行均为人类可读运行日志。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import signal
import sys
from dataclasses import replace
from pathlib import Path
from typing import Mapping, Optional, Sequence


def _ensure_import_path() -> None:
    """脚本以源码树方式运行时的导入引导；安装态下无需处理。"""

    src = Path(__file__).resolve().parents[1] / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


_ensure_import_path()

from hangma_bot.application.audit import audit_text  # noqa: E402  入口脚本可读的公共消毒辅助
from hangma_bot.bootstrap import (  # noqa: E402
    DEFAULT_RULESET_VERSION,
    AssembledRuntime,
    RuntimeConfig,
    build_runtime,
    runtime_config_from_mapping,
)

RESULT_PREFIX = "RESULT "

EXIT_COMPLETED = 0
EXIT_USAGE = 2
EXIT_PERMANENT = 10
EXIT_FATAL = 11
EXIT_SIGINT = 130
EXIT_SIGTERM = 143

# 参赛者终态 → 退出码；未知原因按致命错误处理（守护器可有界重启）。
_TERMINAL_EXIT_CODES = {
    "eliminated": EXIT_COMPLETED,
    "tournament_finished": EXIT_COMPLETED,
    "tournament_closed": EXIT_COMPLETED,
    "tournament_void": EXIT_COMPLETED,
    "authentication_failed": EXIT_PERMANENT,
    "incompatible_guide": EXIT_PERMANENT,
    "target_mismatch": EXIT_PERMANENT,
    "fatal_protocol_error": EXIT_FATAL,
}


def load_config(
    path: Path,
    environ: Optional[Mapping[str, str]] = None,
    token_file: Optional[str] = None,
) -> RuntimeConfig:
    """读取 JSON 运行配置并转成已校验的 RuntimeConfig。

    token_file（对应 --token-file）指向只含单个 Token 的私有文件：
    内容只取首尾空白后的单行文本，绝不进入日志、异常或审计；多行文件
    直接拒绝（避免猜测私有文件格式）。与配置内的 token/token_env 互斥。
    """

    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, Mapping):
        raise ValueError("运行配置根必须是 JSON 对象")
    if token_file is not None:
        if "token" in data or "token_env" in data:
            raise ValueError("--token-file 与配置内的 token/token_env 互斥")
        content = Path(token_file).read_text(encoding="utf-8").strip()
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        if not lines:
            raise ValueError("Token 文件内容为空")
        if len(lines) > 1:
            raise ValueError("Token 文件包含多行内容；请提供只含单个 Token 的文件或改用 token_env")
        data = dict(data)
        data["token"] = lines[0]
    return runtime_config_from_mapping(data, environ=environ)


def banner_lines(assembled: AssembledRuntime) -> Sequence[str]:
    """启动前核对清单（验收：显示模式、目标赛事、脱敏身份、版本与策略）。"""

    config = assembled.config
    return [
        "运行模式: {0}（Token 类别: {1}）".format(config.mode.value, config.token_kind.value),
        "平台基址: {0}".format(config.base_url),
        "目标赛事: {0}".format(config.expected_tournament_id),
        "已适配指南版本下限: {0}".format(config.known_guide_version),
        "本地规则语义版本: {0}".format(DEFAULT_RULESET_VERSION),
        "策略: {0}".format(config.strategy),
        "状态接线: {0}；普通弃牌缓发: {1}".format(
            "SSE 通知＋权威快照" if config.sse_enabled else "状态长轮询",
            "开" if config.discard_pacing_enabled else "关",
        ),
        "身份槽位: {0}（Token 不显示）".format(config.slot or "<未指定>"),
        "审计根目录: {0}".format(config.audit_root),
        "本次 run_id: {0}".format(assembled.run_id),
        "审计目录: {0}".format(assembled.sink.run_dir),
    ]


def mask_participant(participant_id: Optional[str]) -> Optional[str]:
    """脱敏展示：只保留前 4 字符前缀；无法脱敏时返回 None。"""

    if not participant_id:
        return None
    return participant_id[:4]


async def _announce_identity(assembled: AssembledRuntime, stop: asyncio.Event) -> None:
    """初始化完成后打印脱敏身份前缀；运行结束前未发现则静默退出。

    participant_id 由平台 /api/me 在 initialize 阶段返回，启动打印前
    必然已知；本协程只做只读轮询，不参与任何动作路径。
    """

    while not stop.is_set():
        prefix = mask_participant(assembled.participant_id)
        if prefix is not None:
            print("已发现身份（脱敏前缀）: {0}*".format(prefix), flush=True)
            return
        await asyncio.sleep(0.05)


async def _run_with_signals(assembled: AssembledRuntime):
    """运行到终态；首个 SIGINT/SIGTERM 取消运行并等待审计冲刷。

    返回 ``(terminal, signal_number)``：正常终态时 signal_number 为 None，
    被信号中断时 terminal 为 None。取消传播到 ParticipantRuntime.run()，
    其 finally 统一关闭会话并尽力冲刷审计（接口协议第 8 节）。
    """

    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    received: list[int] = []

    def _on_signal(signum: int) -> None:
        received.append(signum)
        stop.set()

    registered: list[int] = []
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, _on_signal, signum)
            registered.append(signum)
        except NotImplementedError:
            pass  # 无信号处理平台（如 Windows）退化为不注册

    run_task = asyncio.ensure_future(assembled.run())
    stop_task = asyncio.ensure_future(stop.wait())
    identity_task = asyncio.ensure_future(_announce_identity(assembled, stop))
    try:
        done, _pending = await asyncio.wait(
            {run_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
        )
        if run_task not in done:
            run_task.cancel()
        try:
            terminal = await run_task
        except asyncio.CancelledError:
            return None, received[0] if received else signal.SIGTERM
        return terminal, None
    finally:
        stop_task.cancel()
        identity_task.cancel()
        for signum in registered:
            try:
                loop.remove_signal_handler(signum)
            except Exception:  # noqa: BLE001 - 清理失败不影响退出码
                pass


def _result_line(
    assembled: AssembledRuntime,
    terminal,
    signal_number: Optional[int],
) -> str:
    """构造机器可读结果行；detail 经消毒截断，绝不包含 Token。"""

    if terminal is not None:
        reason = terminal.reason.value
        detail = audit_text(terminal.detail)
    else:
        reason = "cancelled"
        detail = "收到信号 {0}".format(signal_number)
    summary = assembled.last_audit_summary
    audit = None
    if summary is not None:
        audit = {
            "written": summary.written,
            "dropped_low_priority": summary.dropped_low_priority,
            "missing_high_priority": summary.missing_high_priority,
            "serialization_failures": summary.serialization_failures,
            "audit_degraded": summary.audit_degraded,
        }
    return RESULT_PREFIX + json.dumps(
        {
            "slot": assembled.config.slot,
            "run_id": assembled.run_id,
            "audit_dir": str(assembled.sink.run_dir),
            "participant_id_prefix": mask_participant(assembled.participant_id),
            "terminal_reason": reason,
            "detail": detail,
            "audit_degraded": assembled.audit_degraded,
            "audit_summary": audit,
        },
        ensure_ascii=False,
    )


def terminal_exit_code(terminal, signal_number: Optional[int]) -> int:
    """终态/信号 → 退出码；未知终态原因按致命错误处理。"""

    if signal_number is not None:
        return EXIT_SIGINT if signal_number == signal.SIGINT else EXIT_SIGTERM
    if terminal is None:
        return EXIT_FATAL
    return _TERMINAL_EXIT_CODES.get(terminal.reason.value, EXIT_FATAL)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_participant.py",
        description="运行一个参赛身份到参赛者终态（正式赛事 / 测试赛事 / 测试房间单身份）",
    )
    parser.add_argument("--config", required=True, help="JSON 运行配置路径")
    parser.add_argument(
        "--token-file",
        default=None,
        help="只含单个 Token 的私有文件路径（与配置内 token/token_env 互斥；内容绝不显示）",
    )
    parser.add_argument("--slot", default=None, help="可选身份槽位标签（测试房间 A—D）")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        config = load_config(Path(args.config), token_file=args.token_file)
        if args.slot is not None:
            config = replace(config, slot=args.slot)
        assembled = build_runtime(config)
    except Exception as exc:  # noqa: BLE001 - 配置错误统一转为退出码 2
        print("配置错误: {0}: {1}".format(type(exc).__name__, exc), file=sys.stderr)
        return EXIT_USAGE

    for line in banner_lines(assembled):
        print(line)
    print("启动运行（Ctrl-C 安全停止）...", flush=True)
    try:
        terminal, signal_number = asyncio.run(_run_with_signals(assembled))
    except Exception as exc:  # noqa: BLE001 - 入口级兜底，保证进程有明确退出码
        print("运行异常: {0}: {1}".format(type(exc).__name__, exc), file=sys.stderr)
        print(_result_line(assembled, None, None), flush=True)
        return EXIT_FATAL
    print(_result_line(assembled, terminal, signal_number), flush=True)
    return terminal_exit_code(terminal, signal_number)


if __name__ == "__main__":
    sys.exit(main())
