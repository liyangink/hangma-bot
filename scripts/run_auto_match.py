"""全局 Token 自动匹配（AUTO_MATCH）单会话入口：只运行一个自动房到终态。

职责（scripts/AGENTS.md）：只解析配置、核对模式并调用组合根；不得包含
规则、策略、官方 DTO、match 协议或生命周期实现（均在 bootstrap/官方适配器/
application 内）。默认完成一个自动房会话后退出（free-match-start.md §2）。

配置 JSON 结构（示例见 configs/auto-match.example.json；Token 只经
token/token_env/--token-file 提供，绝不作为命令行参数或日志内容）：

.. code-block:: jsonc

    {
      // 固定 auto_match；token_kind 必须为 official（全局 Token）
      "mode": "auto_match",
      "base_url": "https://<官方平台内网地址>",
      // 可选：空/缺省 = 本次由 POST /api/match 发现自动房；非空 = 只恢复
      // 该已知自动房 room_id（不创建新房）
      "expected_tournament_id": null,
      "known_guide_version": 15,
      "token_env": "HM_AUTO_MATCH_TOKEN",      // token / token_env / --token-file 三选一
      "token_kind": "official",
      "audit_root": "./runs",
      "strategy": "weighted_heuristic",        // 可选
      "insecure_hosts": ["<官方内网主机>"],     // 可选
      "sse_enabled": true,                     // 可选
      "source_namespace": "hangma-official",   // 逻辑平台实例名（必填）
      "auto_match": {                          // 可选；缺省用 AutoMatchSettings 默认值
        "declared_max_games": 10,              // 请求体声明上限；0 = 不声明
        "declared_rounds": 8,                  // 低于服务默认（10/8）会被本地拦截
        "drain_grace_seconds": 45.0            // 房间 finished 后收尾宽限
      }
    }

用法：``python scripts/run_auto_match.py --config <path> [--token-file <私有Token文件>]``

退出码契约（与 run_participant.py 对齐并扩展自动匹配终态）：

========  ============================================================
  0       正常终态（自动房 finished/closed/void）
  2       配置或用法错误（组装前拒绝，不建立网络连接）
  10      身份/容量/证据类永久停止（认证失败 / 指南不兼容 / 目标错配 /
          匹配不可用 MATCHING_UNAVAILABLE / 资源上限 CAPACITY_LIMIT），
          不自动重启
  11      致命协议错误或未预期异常
  130     收到 SIGINT；143 收到 SIGTERM（会话已关闭、审计已尽力冲刷）
========  ============================================================

标准输出最后一行打印 ``RESULT <json>`` 机器可读结果（不含 Token）。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import signal
import sys
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Tuple

_AUTO_SPECIFIC_TOP_KEYS = ("source_namespace", "auto_match")
_AUTO_SETTINGS_KEYS = frozenset(
    {
        "source_namespace",
        "declared_max_games",
        "declared_rounds",
        "match_min_interval_sec",
        "match_max_attempts",
        "match_busy_wait_cap_sec",
        "drain_grace_seconds",
        "room_poll_interval_sec",
    }
)


def _ensure_import_path() -> None:
    """脚本以源码树方式运行时的导入引导；安装态下无需处理。"""

    src = Path(__file__).resolve().parents[1] / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


_ensure_import_path()

import hangma_bot.bootstrap as bootstrap_module  # noqa: E402
from hangma_bot.application.audit import audit_text  # noqa: E402
from hangma_bot.application.auto_match_runtime import AutoMatchSettings  # noqa: E402
from hangma_bot.bootstrap import (  # noqa: E402
    DEFAULT_RULESET_VERSION,
    RuntimeConfig,
    runtime_config_from_mapping,
)

RESULT_PREFIX = "RESULT "

EXIT_COMPLETED = 0
EXIT_USAGE = 2
EXIT_PERMANENT = 10
EXIT_FATAL = 11
EXIT_SIGINT = 130
EXIT_SIGTERM = 143

# 参赛者终态 → 退出码；自动匹配新增的永久停止原因（matching_unavailable /
# capacity_limit）与身份类失败同级：守护器不得自动重启。
_TERMINAL_EXIT_CODES = {
    "tournament_finished": EXIT_COMPLETED,
    "tournament_closed": EXIT_COMPLETED,
    "tournament_void": EXIT_COMPLETED,
    "authentication_failed": EXIT_PERMANENT,
    "incompatible_guide": EXIT_PERMANENT,
    "target_mismatch": EXIT_PERMANENT,
    "matching_unavailable": EXIT_PERMANENT,
    "capacity_limit": EXIT_PERMANENT,
    "fatal_protocol_error": EXIT_FATAL,
}


def load_config(
    path: Path,
    environ: Optional[Mapping[str, str]] = None,
    token_file: Optional[str] = None,
) -> Tuple[RuntimeConfig, AutoMatchSettings]:
    """读取 JSON 运行配置并转成已校验的 RuntimeConfig + AutoMatchSettings。

    Token 三种提供方式（互斥）：配置内 token 内联、token_env 环境变量名、
    --token-file 指向只含单个 Token 的私有文件（多行拒绝，猜测私有格式有
    风险）。配置中的未知键由 bootstrap 白名单拒绝；auto 专用键在此本地校验。
    """

    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, Mapping):
        raise ValueError("运行配置根必须是 JSON 对象")

    auto_raw = data.get("auto_match")
    if auto_raw is None:
        auto_raw = {}
    if not isinstance(auto_raw, Mapping):
        raise ValueError("auto_match 必须是 JSON 对象")
    unknown_auto = sorted(set(auto_raw) - _AUTO_SETTINGS_KEYS)
    if unknown_auto:
        raise ValueError("auto_match 含未知字段: " + ",".join(unknown_auto))

    source_namespace = data.get("source_namespace")
    if not isinstance(source_namespace, str) or not source_namespace.strip():
        raise ValueError("source_namespace 必须是非空字符串（部署逻辑平台实例名）")
    settings = AutoMatchSettings(source_namespace=source_namespace.strip(), **dict(auto_raw))

    # 共享字段交给 bootstrap 白名单解析（它会拒绝未知键并交叉核对 mode/token_kind）。
    shared = {k: v for k, v in data.items() if k not in _AUTO_SPECIFIC_TOP_KEYS}
    if token_file is not None:
        if "token" in shared or "token_env" in shared:
            raise ValueError("--token-file 与配置内的 token/token_env 互斥")
        content = Path(token_file).read_text(encoding="utf-8").strip()
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        if not lines:
            raise ValueError("Token 文件内容为空")
        if len(lines) > 1:
            raise ValueError(
                "Token 文件包含多行内容；请提供只含单个 Token 的文件或改用 token_env"
            )
        shared = dict(shared)
        shared["token"] = lines[0]
    config = runtime_config_from_mapping(shared, environ=environ)
    if config.mode.value != "auto_match":
        raise ValueError("run_auto_match.py 只服务 mode=auto_match，得到 " + config.mode.value)
    return config, settings


def build_composed(config: RuntimeConfig, settings: AutoMatchSettings):
    """调用组合根的自动匹配装配入口（主审集成后存在）。

    集成前给出明确指引而不是 ImportError 崩溃；集成后本函数退化为普通调用，
    可被主审按 handoff 差异收编。
    """

    factory = getattr(bootstrap_module, "build_auto_match_runtime", None)
    if factory is None:
        raise RuntimeError(
            "组合根尚未集成 build_auto_match_runtime（等待主审按 "
            "doc/implementation/handoffs/free-match.md 的共享差异合入）"
        )
    return factory(config, settings)


def banner_lines(assembled: Any) -> Sequence[str]:
    """启动前核对清单（验收：模式、目标房、脱敏身份、版本与运行预算）。"""

    config: RuntimeConfig = assembled.config
    settings: AutoMatchSettings = assembled.settings
    room = config.expected_tournament_id or "（空：本次经 POST /api/match 发现）"
    declared = "M={}/Rounds={}".format(
        settings.declared_max_games or "不限",
        settings.declared_rounds or "不限",
    )
    return [
        "运行模式: {0}（Token 类别: {1}）".format(config.mode.value, config.token_kind.value),
        "平台基址: {0}".format(config.base_url),
        "目标自动房: {0}".format(room),
        "已适配指南版本下限: {0}".format(config.known_guide_version),
        "本地规则语义版本: {0}".format(DEFAULT_RULESET_VERSION),
        "策略: {0}".format(config.strategy),
        "声明上限: {0}（低于服务默认 M=10/Rounds=8 会被拦截）".format(declared),
        "SSE 帧驱动: {0}".format("开启" if config.sse_enabled else "关闭"),
        "source_namespace: {0}".format(settings.source_namespace),
        "审计根目录: {0}".format(config.audit_root),
        "本次 run_id: {0}".format(assembled.run_id),
        "审计目录: {0}".format(assembled.sink.run_dir),
    ]


def mask_participant(participant_id: Optional[str]) -> Optional[str]:
    """脱敏展示：只保留前 4 字符前缀；无法脱敏时返回 None。"""

    if not participant_id:
        return None
    return participant_id[:4]


async def _announce_identity(assembled: Any, stop: asyncio.Event) -> None:
    """初始化完成后打印脱敏身份前缀；运行结束前未发现则静默退出。"""

    while not stop.is_set():
        prefix = mask_participant(getattr(assembled, "participant_id", None))
        if prefix is not None:
            print("已发现身份（脱敏前缀）: {0}*".format(prefix), flush=True)
            return
        await asyncio.sleep(0.05)


async def _run_with_signals(assembled: Any):
    """运行到终态；首个 SIGINT/SIGTERM 取消运行并等待审计冲刷。"""

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


def _result_line(assembled: Any, terminal, signal_number: Optional[int]) -> str:
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
            "run_id": assembled.run_id,
            "audit_dir": str(assembled.sink.run_dir),
            "participant_id_prefix": mask_participant(
                getattr(assembled, "participant_id", None)
            ),
            "terminal_reason": reason,
            "detail": detail,
            "audit_degraded": assembled.audit_degraded,
            "audit_summary": audit,
            "decision_compute": (assembled.compute.snapshot()
                if getattr(assembled, "compute", None) is not None else None),
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
        prog="run_auto_match.py",
        description="运行一个全局 Token 的自动匹配房会话（AUTO_MATCH；默认完成一个自动房后退出）",
    )
    parser.add_argument("--config", required=True, help="JSON 运行配置路径")
    parser.add_argument(
        "--token-file",
        default=None,
        help="只含单个全局 Token 的私有文件路径（与配置内 token/token_env 互斥；内容绝不显示）",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        config, settings = load_config(Path(args.config), token_file=args.token_file)
        assembled = build_composed(config, settings)
    except Exception as exc:  # noqa: BLE001 - 配置/装配错误统一转为退出码 2
        print("配置错误: {0}: {1}".format(type(exc).__name__, exc), file=sys.stderr)
        return EXIT_USAGE

    for line in banner_lines(assembled):
        print(line)
    print("启动运行（Ctrl-C 安全停止；完成一个自动房后退出）...", flush=True)
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
